local LrApplication = import("LrApplication")
local LrDialogs = import("LrDialogs")
local LrFileUtils = import("LrFileUtils")
local LrFunctionContext = import("LrFunctionContext")
local LrPathUtils = import("LrPathUtils")
local LrProgressScope = import("LrProgressScope")
local LrTasks = import("LrTasks")

local ApplyService = ModuleLoader.load("lib/ApplyService.lua")
local AutoDevelopCommand = ModuleLoader.load("lib/AutoDevelopCommand.lua")
local AutoDevelopConfirmationDialog =
    ModuleLoader.load("dialogs/AutoDevelopConfirmationDialog.lua")
local ErrorClassifier = ModuleLoader.load("lib/ErrorClassifier.lua")
local ExifMapper = ModuleLoader.load("lib/ExifMapper.lua")
local JobClient = ModuleLoader.load("lib/JobClient.lua")
local JobState = ModuleLoader.load("lib/JobState.lua")
local Json = ModuleLoader.load("lib/Json.lua")
local LearningBaselineService =
    ModuleLoader.load("lib/LearningBaselineService.lua")
local Logger = ModuleLoader.load("lib/Logger.lua")
local PendingOperation = ModuleLoader.load("lib/PendingOperation.lua")
local Preferences = ModuleLoader.load("lib/Preferences.lua")
local PreparationService = ModuleLoader.load("lib/PreparationService.lua")
local ProgressTracker = ModuleLoader.load("lib/ProgressTracker.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")

local DevelopJobReviewCommand = {}

local function safeCatalogPath(catalog)
    local ok, value = LrTasks.pcall(function()
        return catalog:getPath()
    end)
    return ok and type(value) == "string" and value or ""
end

local function finishProgress(progressScope)
    LrTasks.pcall(function()
        progressScope:done()
    end)
end

local function saveActive(jobRoot, active)
    local saved = JobState.saveActive(jobRoot, active)
    if not saved then
        Logger.error(
            "operation=job_review_state category=internal_error "
                .. "code=active_job_save_failed"
        )
    end
    return saved
end

local function resolvePhotos(catalog, manifest)
    local byId = {}
    local wantedByLocalId = {}
    for _, entry in ipairs(manifest.photos or {}) do
        if type(entry.catalog_uuid) == "string"
            and entry.catalog_uuid ~= "" then
            local ok, photo = LrTasks.pcall(function()
                return catalog:findPhotoByUuid(entry.catalog_uuid)
            end)
            if ok and photo then
                byId[entry.photo_id] = photo
            end
        end
        if not byId[entry.photo_id]
            and type(entry.local_identifier) == "string"
            and entry.local_identifier ~= "" then
            wantedByLocalId[entry.local_identifier] = entry.photo_id
        end
    end
    if next(wantedByLocalId) then
        local ok, photos = LrTasks.pcall(function()
            return catalog:getAllPhotos()
        end)
        if ok and type(photos) == "table" then
            for _, photo in ipairs(photos) do
                local identifier = tostring(
                    Utils.safePhotoProperty(photo, "localIdentifier") or ""
                )
                local photoId = wantedByLocalId[identifier]
                if photoId and not byId[photoId] then
                    byId[photoId] = photo
                end
            end
        end
    end
    local ordered = {}
    local missing = {}
    for _, entry in ipairs(manifest.photos or {}) do
        local photo = byId[entry.photo_id]
        if photo then
            ordered[#ordered + 1] = photo
        else
            missing[#missing + 1] = entry.photo_id
        end
    end
    return byId, ordered, missing
end

local function validateResult(result, active, manifest, photoById)
    if type(result) ~= "table"
        or result.status ~= "completed"
        or type(result.results) ~= "table"
        or result.job_id ~= active.job_id then
        return nil, "completed_job_result_invalid"
    end
    if #result.results ~= #(manifest.photos or {}) then
        return nil, "completed_job_result_count_mismatch"
    end
    local expected = {}
    for _, entry in ipairs(manifest.photos or {}) do
        expected[entry.photo_id] = true
    end
    local byId = {}
    for _, item in ipairs(result.results) do
        if type(item) ~= "table"
            or type(item.photo_id) ~= "string"
            or type(item.http_status) ~= "number"
            or type(item.response) ~= "table"
            or not expected[item.photo_id]
            or byId[item.photo_id]
            or not photoById[item.photo_id] then
            return nil, "completed_job_photo_result_invalid"
        end
        byId[item.photo_id] = item
    end
    return byId
end

local function stateMatches(photo, entry)
    if type(entry.develop_state) ~= "table" then
        return false, "submitted_develop_state_missing"
    end
    local current, currentError = ExifMapper.mapLearningDevelopState(photo)
    if not current then
        return false, currentError or "current_develop_state_unavailable"
    end
    local expectedJson = Json.encode(entry.develop_state)
    local currentJson = Json.encode(current)
    if not expectedJson or not currentJson or expectedJson ~= currentJson then
        return false, "develop_settings_changed_after_submission"
    end
    return true
end

local function preferencesFor(manifest, active)
    local preferences = Preferences.validatedSnapshot(
        manifest.submitted_settings or {}
    )
    if not preferences then
        return nil
    end
    preferences.backendBaseUrl = active.endpoint_url
        or manifest.endpoint_url
        or preferences.backendBaseUrl
    return preferences
end

local function showRunning(status, manifest)
    local progress = status.progress or {}
    LrDialogs.message(
        "AutoDevelop AI job still running",
        "Stage: " .. tostring(progress.stage or "unknown")
            .. "\nProgress: "
            .. tostring(progress.processed_photos or 0)
            .. "/"
            .. tostring(progress.total_photos or #(manifest.photos or {})),
        "info"
    )
end

local function obtainResult(
    jobRoot,
    active,
    manifest,
    preferences,
    progressScope
)
    local resultPath = LrPathUtils.child(
        active.job_folder,
        "completed_result.json"
    )
    if active.status == "downloaded" and LrFileUtils.exists(resultPath) then
        return JobState.readJson(resultPath)
    end

    if active.status == "submitting" then
        local submitted, submitError = JobClient.submit(
            preferences,
            manifest,
            progressScope
        )
        if not submitted then
            return nil, type(submitError) == "table"
                and submitError.code or "job_submission_failed"
        end
        active.job_id = submitted.job_id or active.job_id
        active.status = submitted.status or "running"
        if not saveActive(jobRoot, active) then
            return nil, "active_job_save_failed"
        end
    end

    progressScope:setCaption("Checking server job status")
    local status, statusError = JobClient.status(
        preferences,
        active.job_id
    )
    if not status then
        return nil, type(statusError) == "table"
            and statusError.code or "job_status_failed"
    end
    active.status = status.status
    if not saveActive(jobRoot, active) then
        return nil, "active_job_save_failed"
    end
    if status.status == "created" or status.status == "running" then
        showRunning(status, manifest)
        return nil, "job_still_running"
    end
    if status.status == "failed" or status.status == "interrupted" then
        local resume = LrDialogs.confirm(
            "AutoDevelop AI job interrupted",
            "The server job can resume from its last completed photo.",
            "Resume Job",
            "Cancel"
        )
        if resume == "ok" then
            local resumed, resumeError = JobClient.run(
                preferences,
                active.job_id
            )
            if not resumed then
                return nil, type(resumeError) == "table"
                    and resumeError.code or "job_resume_failed"
            end
            active.status = resumed.status or "running"
            saveActive(jobRoot, active)
            LrDialogs.message(
                "AutoDevelop AI job resumed",
                "The server resumed job " .. active.job_id .. ".",
                "info"
            )
        end
        return nil, "job_resume_pending"
    end
    if status.status ~= "completed" then
        return nil, "unknown_job_status"
    end

    progressScope:setCaption("Downloading completed recommendations")
    local result, downloadError = JobClient.result(
        preferences,
        active.job_id
    )
    if not result then
        return nil, type(downloadError) == "table"
            and downloadError.code or "job_result_download_failed"
    end
    local saved, saveError = JobState.writeJson(resultPath, result)
    if not saved then
        return nil, saveError or "job_result_cache_failed"
    end
    active.status = "downloaded"
    if not saveActive(jobRoot, active) then
        return nil, "active_job_save_failed"
    end
    return result
end

local function appliedSet(active)
    local values = {}
    for _, photoId in ipairs(active.applied_photo_ids or {}) do
        values[photoId] = true
    end
    return values
end

local function runReview(context)
    local jobRoot = Preferences.getJobRoot()
    if not jobRoot then
        LrDialogs.message(
            "AutoDevelop AI job error",
            "The local job storage preference is invalid.",
            "critical"
        )
        return
    end
    local active, activeError = JobState.loadActive(jobRoot)
    if not active then
        LrDialogs.message(
            "AutoDevelop AI",
            activeError and "The active job state could not be read."
                or "There is no active AutoDevelop AI job.",
            activeError and "critical" or "info"
        )
        return
    end
    if active.status == "applied" or active.closed == true then
        LrDialogs.message(
            "AutoDevelop AI",
            "Job " .. tostring(active.job_id)
                .. " has already been closed.",
            "info"
        )
        return
    end
    local manifest = JobState.readJson(
        LrPathUtils.child(active.job_folder, "job.json")
    )
    if not manifest then
        LrDialogs.message(
            "AutoDevelop AI job error",
            "The saved job manifest could not be read.",
            "critical"
        )
        return
    end
    local preferences = preferencesFor(manifest, active)
    if not preferences then
        LrDialogs.message(
            "AutoDevelop AI job error",
            "The saved job settings are invalid.",
            "critical"
        )
        return
    end

    local progressScope = LrProgressScope({
        title = "Check AutoDevelop AI job",
        caption = "Loading durable job",
    })
    local progressFinished = false
    context:addCleanupHandler(function()
        if not progressFinished then
            progressFinished = true
            finishProgress(progressScope)
        end
    end)
    progressScope:setCancelable(true)

    local result, resultError = obtainResult(
        jobRoot,
        active,
        manifest,
        preferences,
        progressScope
    )
    if not result then
        if resultError ~= "job_still_running"
            and resultError ~= "job_resume_pending" then
            Logger.warn(
                "operation=job_review_result category=network_error code="
                    .. Utils.safeErrorCode(resultError, "job_result_failed")
            )
            LrDialogs.message(
                "AutoDevelop AI job unavailable",
                "The saved job could not be checked. It remains available for retry.",
                "warning"
            )
        end
        return
    end

    local catalog = LrApplication.activeCatalog()
    if active.catalog_path ~= ""
        and safeCatalogPath(catalog) ~= active.catalog_path then
        LrDialogs.message(
            "AutoDevelop AI catalog mismatch",
            "Open the Lightroom catalog that submitted this job before applying it.",
            "critical"
        )
        return
    end
    local photoById, orderedPhotos, missing = resolvePhotos(catalog, manifest)
    if #missing > 0 then
        LrDialogs.message(
            "AutoDevelop AI photos missing",
            "Could not find " .. tostring(#missing)
                .. " original photo(s). No recommendations were applied.",
            "critical"
        )
        return
    end
    local resultById, validationError = validateResult(
        result,
        active,
        manifest,
        photoById
    )
    if not resultById then
        Logger.warn(
            "operation=job_review_validation category=invalid_response code="
                .. validationError
        )
        LrDialogs.message(
            "Invalid AutoDevelop AI result",
            "The downloaded result failed validation. No recommendations were applied.",
            "critical"
        )
        return
    end

    local manifestById = {}
    for _, entry in ipairs(manifest.photos) do
        manifestById[entry.photo_id] = entry
    end
    local alreadyApplied = appliedSet(active)
    active.status = "applying"
    if not saveActive(jobRoot, active) then
        LrDialogs.message(
            "AutoDevelop AI job error",
            "Application could not start because its durable state was unavailable.",
            "critical"
        )
        return
    end

    local summary = AutoDevelopCommand.newSummary(
        #orderedPhotos,
        preferences.styleProfileId,
        preferences.modelProfileId
    )
    summary.backendBaseUrl = preferences.backendBaseUrl
    summary.requestTimeoutSeconds = preferences.requestTimeoutSeconds
    summary.confirmationMode = preferences.confirmationMode
    summary.showLearningSummary = preferences.learningShowSummary
    local tracker = ProgressTracker.new(
        #orderedPhotos,
        "Preparing downloaded recommendation"
    )

    local function prepareDownloaded(photo, _, scope, _, _, identity)
        local entry = manifestById[identity.photoId]
        local item = resultById[identity.photoId]
        if alreadyApplied[identity.photoId] then
            return "skipped", { alreadyApplied = true }
        end
        if item.response.status == "error" then
            local error = item.response.error or {}
            return "failed", PreparationService.failure(
                ErrorClassifier.fromHttp(item.http_status, error.code),
                error.code or "job_photo_failed"
            )
        end
        local unchanged, staleCode = stateMatches(photo, entry)
        if not unchanged then
            return "failed", PreparationService.failure(
                ErrorClassifier.codes.validationError,
                staleCode
            )
        end
        return PreparationService.prepareDevelopResult(
            photo,
            entry.request,
            item.response,
            scope,
            preferences,
            identity
        )
    end

    local function applyAndCheckpoint(applyCatalog, operation)
        local application = ApplyService.applyOne(applyCatalog, operation)
        if operation.applicationStatus == "applied" then
            alreadyApplied[operation.photoId] = true
            active.applied_photo_ids = active.applied_photo_ids or {}
            active.applied_photo_ids[#active.applied_photo_ids + 1] =
                operation.photoId
            if not saveActive(jobRoot, active) then
                application.writeError = "Applied result checkpoint failed."
                application.writeErrorCategory = "write_access_failed"
                application.writeErrorCode = "applied_checkpoint_failed"
            end
        end
        return application
    end

    summary = AutoDevelopCommand.processSequential({
        photos = orderedPhotos,
        catalog = catalog,
        progressScope = progressScope,
        tracker = tracker,
        summary = summary,
        preferences = preferences,
        preparePhoto = prepareDownloaded,
        confirmPhoto = AutoDevelopConfirmationDialog.confirmPhoto,
        applyOne = applyAndCheckpoint,
        recordBaseline = LearningBaselineService.recordOne,
        onRelease = function(operation)
            PendingOperation.clear({ operation })
        end,
    })
    AutoDevelopConfirmationDialog.showFinal(summary, {
        applied = summary.applied,
        cropApplied = summary.cropAppliedCount,
        levelingApplied = summary.levelingAppliedCount,
        restoredAfterFailure = summary.restoredAfterFailure,
        failedNotRestored = summary.failedNotRestored,
        notApplied = summary.notProcessed,
    })

    if not summary.cancelled
        and summary.failed == 0
        and summary.notProcessed == 0 then
        active.status = "applied"
        active.applied_at = os.time()
        if not saveActive(jobRoot, active) then
            LrDialogs.message(
                "AutoDevelop AI state warning",
                "Recommendations were reviewed, but final local state could not be saved.",
                "warning"
            )
        end
        return
    end

    active.status = "downloaded"
    saveActive(jobRoot, active)
    if summary.failed > 0 then
        local close = LrDialogs.confirm(
            "AutoDevelop AI job requires attention",
            "Some recommendations could not be applied. Keep the job for retry, "
                .. "or close it to submit a replacement job.",
            "Close Job",
            "Keep for Retry"
        )
        if close == "ok" then
            active.closed = true
            active.status = "closed"
            active.closed_at = os.time()
            saveActive(jobRoot, active)
        end
    end
end

function DevelopJobReviewCommand.start()
    LrTasks.startAsyncTask(function()
        local ok = LrTasks.pcall(function()
            return LrFunctionContext.callWithContext(
                "AutoDevelop AI Review Durable Job",
                runReview
            )
        end)
        if not ok then
            Logger.error(
                "operation=job_review_command category=internal_error "
                    .. "code=unexpected_exception"
            )
            LrDialogs.message(
                "AutoDevelop AI job error",
                "The job review encountered an unexpected error. No unsafe changes were applied.",
                "critical"
            )
        end
    end)
end

DevelopJobReviewCommand.resolvePhotos = resolvePhotos
DevelopJobReviewCommand.validateResult = validateResult
DevelopJobReviewCommand.stateMatches = stateMatches

return DevelopJobReviewCommand
