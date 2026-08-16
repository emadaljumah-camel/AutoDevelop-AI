local LrApplication = import("LrApplication")
local LrDialogs = import("LrDialogs")
local LrFunctionContext = import("LrFunctionContext")
local LrPathUtils = import("LrPathUtils")
local LrProgressScope = import("LrProgressScope")
local LrTasks = import("LrTasks")

local Config = ModuleLoader.load("lib/Config.lua")
local ErrorClassifier = ModuleLoader.load("lib/ErrorClassifier.lua")
local ErrorDialog = ModuleLoader.load("dialogs/ErrorDialog.lua")
local ExifMapper = ModuleLoader.load("lib/ExifMapper.lua")
local JobClient = ModuleLoader.load("lib/JobClient.lua")
local JobState = ModuleLoader.load("lib/JobState.lua")
local Logger = ModuleLoader.load("lib/Logger.lua")
local ModelProfiles = ModuleLoader.load("lib/ModelProfiles.lua")
local Preferences = ModuleLoader.load("lib/Preferences.lua")
local PreviewExporter = ModuleLoader.load("lib/PreviewExporter.lua")
local RequestBuilder = ModuleLoader.load("lib/RequestBuilder.lua")
local RunSettingsCoordinator = ModuleLoader.load("lib/RunSettingsCoordinator.lua")
local StyleProfiles = ModuleLoader.load("lib/StyleProfiles.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")
local RunSettingsDialog = ModuleLoader.load("dialogs/RunSettingsDialog.lua")

local DurableDevelopCommand = {}

local function safeCatalogPath(catalog)
    local ok, value = LrTasks.pcall(function()
        return catalog:getPath()
    end)
    if ok and type(value) == "string" then
        return value
    end
    return ""
end

local function safeFailureCode(failure)
    if type(failure) == "table" then
        return Utils.safeErrorCode(failure.code, "job_submission_failed")
    end
    return "job_submission_failed"
end

local function finishProgress(progressScope)
    local ok = LrTasks.pcall(function()
        progressScope:done()
    end)
    if not ok then
        Logger.warn(
            "operation=durable_job_progress_cleanup "
                .. "category=cleanup_failed code=progress_cleanup_failed"
        )
    end
end

local function removeUncommittedJob(jobFolder)
    if not jobFolder then
        return
    end
    local ok, removed = LrTasks.pcall(PreviewExporter.cleanupBatch, jobFolder)
    if not ok or not removed then
        Logger.warn(
            "operation=durable_job_cleanup category=cleanup_failed "
                .. "code=uncommitted_job_cleanup_failed"
        )
    end
end

local function chooseRunSettings()
    local current = Preferences.valuesForUi()
    local dialogResult = RunSettingsDialog.show(
        current.styleProfileId,
        current.modelProfileId
    )
    local run = RunSettingsCoordinator.begin({
        dialogResult = dialogResult,
        validateProfile = StyleProfiles.isValidId,
        validateModel = ModelProfiles.isSelectableId,
        persistProfileDefault = function(profileId)
            return Preferences.set("styleProfileId", profileId)
        end,
        persistModelDefault = function(modelId)
            return Preferences.set("modelProfileId", modelId)
        end,
        snapshotFactory = function(profileId, modelId)
            return Preferences.validatedSnapshot({
                styleProfileId = profileId,
                modelProfileId = modelId,
            })
        end,
    })
    return run, current
end

local function buildManifest(
    photos,
    catalog,
    jobFolder,
    clientJobId,
    preferences,
    progressScope
)
    local manifest = {
        schema_version = Config.SCHEMA_VERSION,
        client_job_id = clientJobId,
        plugin_version = Config.PLUGIN_VERSION,
        catalog_path = safeCatalogPath(catalog),
        endpoint_url = preferences.backendBaseUrl,
        submitted_settings = {
            styleProfileId = preferences.styleProfileId,
            modelProfileId = preferences.modelProfileId,
            applyCompositionCrop = preferences.applyCompositionCrop,
            applyLeveling = preferences.applyLeveling,
            hdrPreference = preferences.hdrPreference,
            confirmationMode = preferences.confirmationMode,
            learningEnabled = preferences.learningEnabled,
            learningCaptureBaseline = preferences.learningCaptureBaseline,
            learningShowSummary = preferences.learningShowSummary,
        },
        photos = {},
    }
    local previewRoot = LrPathUtils.child(jobFolder, "previews")
    local seenPhotoIds = {}
    local skipped = 0
    for index, photo in ipairs(photos) do
        if progressScope:isCanceled() then
            return nil, "cancelled"
        end
        progressScope:setPortionComplete(index - 1, #photos)
        local identity = Utils.capturePhotoIdentity(photo)
        if not ExifMapper.isSupportedPhoto(photo) then
            skipped = skipped + 1
        elseif seenPhotoIds[identity.photoId] then
            return nil, "duplicate_photo_id"
        else
            seenPhotoIds[identity.photoId] = true
            progressScope:setCaption("Exporting " .. identity.displayFilename)
            local preview, previewError = PreviewExporter.exportPhoto(
                photo,
                previewRoot,
                progressScope,
                { encode = false }
            )
            if not preview then
                return nil, previewError or "preview_export_failed"
            end
            local request, requestError = RequestBuilder.buildDevelopJob(
                photo,
                {
                    styleProfileId = preferences.styleProfileId,
                    modelProfileId = preferences.modelProfileId,
                    includeCrop = true,
                    includeDenoise = true,
                    preserveCurrentAdjustments = true,
                    learningEnabled = preferences.learningEnabled,
                    hdrPreference = preferences.hdrPreference,
                    photoIdentity = identity,
                }
            )
            if not request then
                return nil, requestError or "request_build_failed"
            end
            local developState, developStateError =
                ExifMapper.mapLearningDevelopState(photo)
            if not developState then
                return nil, developStateError
                    or "submitted_develop_state_unavailable"
            end
            manifest.photos[#manifest.photos + 1] = {
                photo_id = identity.photoId,
                filename = identity.displayFilename,
                preview_path = preview.path,
                local_identifier = tostring(
                    Utils.safePhotoProperty(photo, "localIdentifier") or ""
                ),
                catalog_uuid = tostring(
                    Utils.safeRawMetadata(photo, "uuid") or ""
                ),
                request = request,
                develop_state = developState,
            }
        end
    end
    manifest.skipped_photos = skipped
    if #manifest.photos == 0 then
        return nil, "no_supported_photos"
    end
    return manifest
end

local function runCommand(context)
    local catalog = LrApplication.activeCatalog()
    local photos = catalog:getTargetPhotos()
    if not photos or #photos == 0 then
        LrDialogs.message(
            "AutoDevelop AI",
            "Select one or more photos to auto develop.",
            "warning"
        )
        return
    end

    local run, current = chooseRunSettings()
    if run.cancelled then
        return
    end
    if run.status ~= "ready" then
        ErrorDialog.show(
            run.status == "invalid_profile"
                and ErrorClassifier.codes.invalidProfile
                or ErrorClassifier.codes.validationError,
            {
                backendBaseUrl = current.backendBaseUrl,
                requestTimeoutSeconds = current.requestTimeoutSeconds,
                profileId = run.profileId or current.styleProfileId,
            }
        )
        return
    end
    local preferences = RunSettingsCoordinator.getSnapshot(run)
    local active, activeError = JobState.loadActive(preferences.jobRoot)
    if activeError then
        LrDialogs.message(
            "AutoDevelop AI job error",
            "The local active-job state could not be read.",
            "critical"
        )
        return
    end
    if active and active.status ~= "applied" and active.closed ~= true then
        LrDialogs.message(
            "AutoDevelop AI job pending",
            "Job " .. tostring(active.job_id)
                .. " has not been applied. Use "
                .. "'Check AutoDevelop Job / Apply Results' first.",
            "warning"
        )
        return
    end

    local clientJobId = os.date("%Y%m%d-%H%M%S")
        .. "-" .. Utils.newUuid()
    local jobFolder, folderError = JobState.createFolder(
        preferences.jobRoot,
        clientJobId
    )
    if not jobFolder then
        Logger.error(
            "operation=durable_job_create category=internal_error code="
                .. Utils.safeErrorCode(folderError, "job_directory_failed")
        )
        LrDialogs.message(
            "AutoDevelop AI job error",
            "The local durable job folder could not be created.",
            "critical"
        )
        return
    end

    local committed = false
    context:addCleanupHandler(function()
        if not committed then
            removeUncommittedJob(jobFolder)
        end
    end)
    local progressScope = LrProgressScope({
        title = "Submit AutoDevelop AI job",
        caption = "Preparing persistent previews",
    })
    local progressFinished = false
    context:addCleanupHandler(function()
        if not progressFinished then
            progressFinished = true
            finishProgress(progressScope)
        end
    end)
    progressScope:setCancelable(true)

    local manifest, manifestError = buildManifest(
        photos,
        catalog,
        jobFolder,
        clientJobId,
        preferences,
        progressScope
    )
    if not manifest then
        if manifestError ~= "cancelled" then
            Logger.error(
                "operation=durable_job_prepare category=internal_error code="
                    .. Utils.safeErrorCode(manifestError, "job_preparation_failed")
            )
            LrDialogs.message(
                "AutoDevelop AI job error",
                manifestError == "no_supported_photos"
                    and "No supported photos were selected."
                    or "The durable job could not be prepared.",
                manifestError == "no_supported_photos" and "warning" or "critical"
            )
        end
        return
    end

    local manifestSaved, manifestSaveError = JobState.writeJson(
        LrPathUtils.child(jobFolder, "job.json"),
        manifest
    )
    if not manifestSaved then
        Logger.error(
            "operation=durable_job_manifest category=internal_error code="
                .. Utils.safeErrorCode(manifestSaveError, "job_manifest_save_failed")
        )
        LrDialogs.message(
            "AutoDevelop AI job error",
            "The durable job manifest could not be saved.",
            "critical"
        )
        return
    end

    local activeState = {
        schema_version = Config.SCHEMA_VERSION,
        job_id = clientJobId,
        client_job_id = clientJobId,
        job_folder = jobFolder,
        catalog_path = manifest.catalog_path,
        endpoint_url = preferences.backendBaseUrl,
        status = "submitting",
        closed = false,
        submitted_at = os.time(),
        applied_photo_ids = {},
    }
    local activeSaved, activeSaveError = JobState.saveActive(
        preferences.jobRoot,
        activeState
    )
    if not activeSaved then
        Logger.error(
            "operation=durable_job_active_state category=internal_error code="
                .. Utils.safeErrorCode(activeSaveError, "active_job_save_failed")
        )
        LrDialogs.message(
            "AutoDevelop AI job error",
            "The active job pointer could not be saved.",
            "critical"
        )
        return
    end
    committed = true

    progressScope:setCaption("Submitting durable job")
    local response, submitError = JobClient.submit(
        preferences,
        manifest,
        progressScope
    )
    if not response then
        Logger.warn(
            "operation=durable_job_submit category=network_error code="
                .. safeFailureCode(submitError)
        )
        LrDialogs.message(
            "AutoDevelop AI submission interrupted",
            "The local job is saved and can be resumed. Use "
                .. "'Check AutoDevelop Job / Apply Results' after reconnecting.",
            "warning"
        )
        return
    end

    activeState.job_id = response.job_id or clientJobId
    activeState.status = response.status or "running"
    local stateUpdated = JobState.saveActive(preferences.jobRoot, activeState)
    if not stateUpdated then
        LrDialogs.message(
            "AutoDevelop AI job queued",
            "The server queued the job, but the local status update failed. "
                .. "The saved manifest can be used for recovery.",
            "warning"
        )
        return
    end
    progressScope:setPortionComplete(1, 1)
    LrDialogs.message(
        "AutoDevelop AI job submitted",
        "Job " .. activeState.job_id
            .. " is processing on the server. It is safe to disconnect. "
            .. "Reconnect later and use "
            .. "'Check AutoDevelop Job / Apply Results'.\n\nQueued: "
            .. tostring(#manifest.photos)
            .. "\nSkipped unsupported: "
            .. tostring(manifest.skipped_photos),
        "info"
    )
end

function DurableDevelopCommand.start()
    LrTasks.startAsyncTask(function()
        local ok = LrTasks.pcall(function()
            return LrFunctionContext.callWithContext(
                "AutoDevelop AI Submit Durable Job",
                runCommand
            )
        end)
        if not ok then
            Logger.error(
                "operation=durable_job_command category=internal_error "
                    .. "code=unexpected_exception"
            )
            ErrorDialog.show(ErrorClassifier.codes.internalError)
        end
    end)
end

DurableDevelopCommand.buildManifest = buildManifest

return DurableDevelopCommand
