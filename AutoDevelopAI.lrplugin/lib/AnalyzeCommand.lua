local LrApplication = import("LrApplication")
local LrDialogs = import("LrDialogs")
local LrFunctionContext = import("LrFunctionContext")
local LrProgressScope = import("LrProgressScope")
local LrTasks = import("LrTasks")

local ApiClient = ModuleLoader.load("lib/ApiClient.lua")
local BatchSummary = ModuleLoader.load("lib/BatchSummary.lua")
local ErrorClassifier = ModuleLoader.load("lib/ErrorClassifier.lua")
local ExifMapper = ModuleLoader.load("lib/ExifMapper.lua")
local Logger = ModuleLoader.load("lib/Logger.lua")
local Preferences = ModuleLoader.load("lib/Preferences.lua")
local PreparationService = ModuleLoader.load("lib/PreparationService.lua")
local PreviewExporter = ModuleLoader.load("lib/PreviewExporter.lua")
local ProgressTracker = ModuleLoader.load("lib/ProgressTracker.lua")
local RequestBuilder = ModuleLoader.load("lib/RequestBuilder.lua")
local ResultStore = ModuleLoader.load("lib/ResultStore.lua")
local StyleProfiles = ModuleLoader.load("lib/StyleProfiles.lua")
local RunSettingsCoordinator =
    ModuleLoader.load("lib/RunSettingsCoordinator.lua")
local ModelProfiles = ModuleLoader.load("lib/ModelProfiles.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")
local Validation = ModuleLoader.load("lib/Validation.lua")
local AnalysisSummaryDialog =
    ModuleLoader.load("dialogs/AnalysisSummaryDialog.lua")
local ErrorDialog = ModuleLoader.load("dialogs/ErrorDialog.lua")
local RunSettingsDialog =
    ModuleLoader.load("dialogs/RunSettingsDialog.lua")

local AnalyzeCommand = {}

local function cleanupPreview(preview)
    local ok, cleaned, reason = LrTasks.pcall(
        PreviewExporter.cleanupPreview,
        preview
    )
    if not ok then
        Logger.warn(
            "operation=analyze_preview_cleanup category=cleanup_failed "
                .. "code=preview_cleanup_exception"
        )
        return
    end
    if not cleaned then
        Logger.warn(
            "operation=analyze_preview_cleanup category=cleanup_failed "
                .. "code=preview_cleanup_failed"
        )
    end
end

local function cleanupBatch(batchDirectory)
    local ok, cleaned, reason = LrTasks.pcall(
        PreviewExporter.cleanupBatch,
        batchDirectory
    )
    if not ok then
        Logger.warn(
            "operation=analyze_batch_cleanup category=cleanup_failed "
                .. "code=batch_cleanup_exception"
        )
        return
    end
    if not cleaned then
        Logger.warn(
            "operation=analyze_batch_cleanup category=cleanup_failed "
                .. "code=batch_cleanup_failed"
        )
    end
end

local function finishProgress(progressScope)
    local ok, reason = LrTasks.pcall(function()
        progressScope:done()
    end)
    if not ok then
        Logger.warn(
            "operation=analyze_progress_cleanup category=cleanup_failed "
                .. "code=progress_cleanup_failed"
        )
    end
end

local function processPhotoBody(
    photo,
    batchDirectory,
    progressScope,
    context,
    preferences,
    tracker
)
    if not ExifMapper.isSupportedPhoto(photo) then
        return "skipped", "Videos are not supported."
    end

    local preview, previewError = PreviewExporter.exportPhoto(
        photo,
        batchDirectory,
        progressScope
    )
    if not preview then
        if progressScope:isCanceled() then
            return "cancelled", PreparationService.failure(
                ErrorClassifier.codes.cancelled,
                "user_cancelled"
            )
        end
        Logger.warn(
            "operation=analyze_preview_export category=internal_error "
                .. "code=preview_export_failed"
        )
        return "failed", PreparationService.failure(
            ErrorClassifier.codes.internalError,
            "preview_export_failed"
        )
    end
    local previewCleaned = false
    context:addCleanupHandler(function()
        if previewCleaned then
            return
        end
        previewCleaned = true
        cleanupPreview(preview)
    end)

    if progressScope:isCanceled() then
        return "cancelled", PreparationService.failure(
            ErrorClassifier.codes.cancelled,
            "user_cancelled"
        )
    end

    local request, requestError = RequestBuilder.build(photo, preview.path, {
        styleProfileId = preferences.styleProfileId,
        modelProfileId = preferences.modelProfileId,
    })
    if not request then
        Logger.warn(
            "operation=build_analyze_request category=validation_error "
                .. "code=request_build_failed"
        )
        return "failed", PreparationService.failure(
            ErrorClassifier.codes.validationError,
            "request_build_failed"
        )
    end

    Logger.info(
        "Analyze request start request_id="
            .. request.request_id
            .. " filename="
            .. request.filename
    )

    local response, requestFailure = PreparationService.request(
        "analyze",
        request,
        progressScope,
        {
            baseUrl = preferences.backendBaseUrl,
            timeoutSeconds = preferences.requestTimeoutSeconds,
        },
        tracker
    )
    if not response then
        if requestFailure.category == ErrorClassifier.codes.cancelled then
            return "cancelled", requestFailure
        end
        return "failed", requestFailure
    end
    if progressScope:isCanceled() then
        return "cancelled", PreparationService.failure(
            ErrorClassifier.codes.cancelled,
            "user_cancelled"
        )
    end

    local decoded, decodeError = ApiClient.decodeBody(response)
    if not decoded then
        Logger.warn(
            "Analyze response JSON failure request_id="
                .. request.request_id
                .. " category=invalid_response code=malformed_json"
        )
        return "failed", PreparationService.failure(
            ErrorClassifier.codes.invalidResponse,
            "malformed_json"
        )
    end

    local valid, validationError, validatedModel, resolvedModel =
        Validation.validateAnalyzeResponse(decoded, request)
    if not valid then
        Logger.warn(
            "Analyze response validation failed request_id="
                .. request.request_id
                .. " category=invalid_response "
                .. "code=response_validation_failed"
        )
        return "failed", PreparationService.failure(
            ErrorClassifier.codes.invalidResponse,
            "response_validation_failed"
        )
    end

    ResultStore.put(Utils.photoKey(photo), {
        request_id = request.request_id,
        filename = request.filename,
        style_profile = request.options.style_profile,
        analyzed_at = Utils.nowIso(),
        response = decoded,
    })
    Logger.info(
        "Analyze request complete request_id="
            .. request.request_id
            .. " model="
            .. validatedModel
            .. " duration_ms="
            .. tostring(decoded.processing_duration_ms or "unavailable")
    )
    return "success", {
        model = validatedModel,
        resolvedModel = resolvedModel,
        requestedStyleId = decoded.requested_style_id,
        effectiveStyleId = decoded.effective_style_id,
        styleSelectionMode = decoded.style_selection_mode,
        editingIntensity = decoded.editing_intensity,
        primarySubject = decoded.analysis.main_subject,
        sceneCategory = decoded.analysis.scene_type,
        lighting = decoded.analysis.lighting,
        priorities = Utils.deepCopy(decoded.edit_plan.goals or {}),
        cropRecommended = type(decoded.crop) == "table"
            and decoded.crop.recommended == true,
        levelingRecommended = decoded.leveling.recommended == true,
        levelingMode = decoded.leveling.mode,
        levelingAngle = decoded.leveling.angle,
        processingDurationMs = decoded.processing_duration_ms,
        filename = request.filename,
    }
end

local function processPhoto(
    photo,
    batchDirectory,
    progressScope,
    preferences,
    tracker
)
    local ok, outcome, reason = LrTasks.pcall(function()
        return LrFunctionContext.callWithContext(
            "AutoDevelop AI Analyze Photo",
            function(context)
                return processPhotoBody(
                    photo,
                    batchDirectory,
                    progressScope,
                    context,
                    preferences,
                    tracker
                )
            end
        )
    end)

    if not ok then
        Logger.error(
            "operation=analyze_photo category=internal_error "
                .. "code=unexpected_exception"
        )
        return "failed", PreparationService.failure(
            ErrorClassifier.codes.internalError,
            "unexpected_plugin_error"
        )
    end
    return outcome, reason
end

local function runBatch(
    photos,
    progressScope,
    batchDirectory,
    preferences,
    tracker
)
    local summary = BatchSummary.new(#photos, "analyze")
    summary.backendBaseUrl = preferences.backendBaseUrl
    summary.requestTimeoutSeconds = preferences.requestTimeoutSeconds
    summary.profileId = preferences.styleProfileId
    summary.styleDisplayName =
        StyleProfiles.getDisplayName(preferences.styleProfileId)
    summary.modelId = preferences.modelProfileId
    summary.modelDisplayName =
        ModelProfiles.getDisplayName(preferences.modelProfileId)
    summary.resolvedModels = {}
    summary.analysisExamples = {}

    for index, photo in ipairs(photos) do
        if progressScope:isCanceled() then
            summary.cancelled = true
            BatchSummary.markNotProcessed(summary, #photos - index + 1)
            break
        end

        local filename = Utils.photoFilename(photo)
        tracker:setPhase("Preparing analysis")
        tracker:setCurrent(filename, index)
        progressScope:setCaption(tracker:caption())

        local outcome, reason = processPhoto(
            photo,
            batchDirectory,
            progressScope,
            preferences,
            tracker
        )
        if progressScope:isCanceled() then
            summary.cancelled = true
            BatchSummary.markNotProcessed(summary, #photos - index + 1)
            break
        end
        if outcome == "success" then
            summary.analyzed = summary.analyzed + 1
            BatchSummary.recordStyle(summary, reason)
            BatchSummary.recordGeometry(summary, reason)
            if type(reason) == "table" and reason.resolvedModel then
                summary.resolvedModels[reason.resolvedModel] = true
            end
            if type(reason) == "table"
                and #summary.analysisExamples < 5 then
                summary.analysisExamples[#summary.analysisExamples + 1] =
                    Utils.deepCopy(reason)
            end
        elseif outcome == "skipped" then
            summary.skipped = summary.skipped + 1
        elseif outcome == "cancelled" then
            summary.cancelled = true
            BatchSummary.markNotProcessed(summary, #photos - index + 1)
            break
        else
            BatchSummary.addFailure(summary, filename, reason)
            if ErrorClassifier.isTerminalForBatch(reason.category) then
                summary.terminalCategory = reason.category
                BatchSummary.markNotProcessed(summary, #photos - index)
                tracker:markCompleted(index)
                progressScope:setPortionComplete(index, #photos)
                progressScope:setCaption(tracker:caption())
                break
            end
        end
        tracker:markCompleted(index)
        progressScope:setPortionComplete(index, #photos)
        progressScope:setCaption(tracker:caption())
    end

    summary.elapsedSeconds = tracker:elapsedSeconds()
    return summary
end

local function runCommand(context)
    local catalog = LrApplication.activeCatalog()
    local photos = catalog:getTargetPhotos()
    if not photos or #photos == 0 then
        LrDialogs.message(
            "AutoDevelop AI",
            "Select one or more photos to analyze.",
            "warning"
        )
        return
    end

    local current = Preferences.valuesForUi()
    local dialogResult =
        RunSettingsDialog.show(
            current.styleProfileId,
            current.modelProfileId
        )
    local styleRun = RunSettingsCoordinator.begin({
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
    if styleRun.cancelled then
        return
    end
    if styleRun.status ~= "ready" then
        ErrorDialog.show(
            styleRun.status == "invalid_profile"
                and ErrorClassifier.codes.invalidProfile
                or ErrorClassifier.codes.validationError,
            {
                backendBaseUrl = current.backendBaseUrl,
                requestTimeoutSeconds = current.requestTimeoutSeconds,
                profileId = styleRun.profileId or current.styleProfileId,
            }
        )
        return
    end
    local preferences = RunSettingsCoordinator.getSnapshot(styleRun)

    Logger.info(
        "Analyze Selected Photos start selected="
            .. tostring(#photos)
            .. " profile="
            .. styleRun.profileId
    )
    local batchDirectory, directoryError =
        PreviewExporter.createBatchDirectory()
    if not batchDirectory then
        Logger.error(
            "operation=create_analyze_preview_directory "
                .. "category=internal_error code=preview_directory_failed"
        )
        LrDialogs.message(
            "AutoDevelop AI",
            "Could not create temporary previews for analysis.",
            "critical"
        )
        return
    end
    local batchCleaned = false
    local function releaseBatch()
        if batchCleaned then
            return
        end
        batchCleaned = true
        cleanupBatch(batchDirectory)
    end
    context:addCleanupHandler(releaseBatch)

    local progressScope = LrProgressScope({
        title = "Analyzing selected photos",
        caption = "Preparing analysis",
    })
    local progressFinished = false
    local function releaseProgress()
        if progressFinished then
            return
        end
        progressFinished = true
        finishProgress(progressScope)
    end
    context:addCleanupHandler(releaseProgress)
    progressScope:setCancelable(true)

    local tracker = ProgressTracker.new(#photos, "Analyzing")
    local preparation = RunSettingsCoordinator.prepare(
        styleRun,
        photos,
        function(runPhotos, runPreferences)
            return runBatch(
                runPhotos,
                progressScope,
                batchDirectory,
                runPreferences,
                tracker
            )
        end
    )
    if preparation.status ~= "completed" then
        releaseBatch()
        releaseProgress()
        ErrorDialog.show(ErrorClassifier.codes.internalError)
        return
    end
    local summary = preparation.prepared
    releaseBatch()
    releaseProgress()

    Logger.info(
        "Analyze Selected Photos complete analyzed="
            .. tostring(summary.analyzed)
            .. " failed="
            .. tostring(summary.failed)
            .. " skipped="
            .. tostring(summary.skipped)
            .. " not_processed="
            .. tostring(summary.notProcessed)
    )
    if summary.terminalCategory then
        ErrorDialog.show(summary.terminalCategory, summary)
    else
        AnalysisSummaryDialog.show(summary)
    end
end

function AnalyzeCommand.start()
    LrTasks.startAsyncTask(function()
        local ok, failure = LrTasks.pcall(function()
            return LrFunctionContext.callWithContext(
                "AutoDevelop AI Analyze Selected Photos",
                runCommand
            )
        end)
        if not ok then
            Logger.error(
                "operation=analyze_command category=internal_error "
                    .. "code=unexpected_exception"
            )
            ErrorDialog.show(ErrorClassifier.codes.internalError)
        end
    end)
end

AnalyzeCommand.runBatch = runBatch

return AnalyzeCommand
