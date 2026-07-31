local LrApplication = import("LrApplication")
local LrDialogs = import("LrDialogs")
local LrFunctionContext = import("LrFunctionContext")
local LrProgressScope = import("LrProgressScope")
local LrTasks = import("LrTasks")

local ApplyService = ModuleLoader.load("lib/ApplyService.lua")
local BatchSummary = ModuleLoader.load("lib/BatchSummary.lua")
local ErrorClassifier = ModuleLoader.load("lib/ErrorClassifier.lua")
local Logger = ModuleLoader.load("lib/Logger.lua")
local LearningBaselineService =
    ModuleLoader.load("lib/LearningBaselineService.lua")
local Preferences = ModuleLoader.load("lib/Preferences.lua")
local PendingOperation = ModuleLoader.load("lib/PendingOperation.lua")
local PreparationService = ModuleLoader.load("lib/PreparationService.lua")
local PreviewExporter = ModuleLoader.load("lib/PreviewExporter.lua")
local ProgressTracker = ModuleLoader.load("lib/ProgressTracker.lua")
local StyleProfiles = ModuleLoader.load("lib/StyleProfiles.lua")
local ModelProfiles = ModuleLoader.load("lib/ModelProfiles.lua")
local RunSettingsCoordinator =
    ModuleLoader.load("lib/RunSettingsCoordinator.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")
local AutoDevelopConfirmationDialog =
    ModuleLoader.load("dialogs/AutoDevelopConfirmationDialog.lua")
local ErrorDialog = ModuleLoader.load("dialogs/ErrorDialog.lua")
local RunSettingsDialog =
    ModuleLoader.load("dialogs/RunSettingsDialog.lua")

local AutoDevelopCommand = {}

local function cleanupBatch(batchDirectory)
    local ok, cleaned, reason = LrTasks.pcall(
        PreviewExporter.cleanupBatch,
        batchDirectory
    )
    if not ok or not cleaned then
        Logger.warn(
            "operation=develop_batch_cleanup category=cleanup_failed "
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
            "operation=develop_progress_cleanup category=cleanup_failed "
                .. "code=progress_cleanup_failed"
        )
    end
end

local function newSummary(selected, profileId, modelId)
    local summary = BatchSummary.new(selected, "develop")
    summary.profileId = profileId
    summary.styleDisplayName = StyleProfiles.getDisplayName(profileId)
    summary.modelId = modelId
    summary.modelDisplayName = ModelProfiles.getDisplayName(modelId)
    return summary
end

local function validPreparedOperation(operation)
    local display = PendingOperation.inspectDisplayContract(operation)
    return type(operation) == "table"
        and operation.photo ~= nil
        and type(operation.filename) == "string"
        and operation.filename ~= ""
        and Utils.trim(operation.filename) == operation.filename
        and type(operation.requestId) == "string"
        and operation.requestId ~= ""
        and Utils.trim(operation.requestId) == operation.requestId
        and type(operation.originalSettings) == "table"
        and type(operation.mappedSettings) == "table"
        and display.canApply
        and ApplyService.validateFinalSettings(operation.finalSettings)
        and operation.applicationStatus == "pending"
end

local function updateProgress(progressScope, tracker, summary, index)
    tracker:setCurrent(tracker.filename, index)
    tracker:markCompleted(summary.processed)
    tracker:setBatchCounts(summary)
    progressScope:setCaption(tracker:caption())
    progressScope:setPortionComplete(summary.processed, summary.selected)
end

local function recordPreparationSkip(summary, value)
    BatchSummary.recordSkipped(summary)
    if type(value) ~= "table" then
        return
    end
    BatchSummary.recordGeometry(summary, value)
    if value.hdrRecommended then
        summary.hdrRecommendedCount =
            (summary.hdrRecommendedCount or 0) + 1
    end
    if value.denoiseRecommended then
        summary.denoiseRecommendedCount =
            (summary.denoiseRecommendedCount or 0) + 1
        summary.denoiseIgnored = (summary.denoiseIgnored or 0) + 1
    end
end

local function processSequential(options)
    options = options or {}
    local photos = options.photos or {}
    local summary = options.summary
    local preferences = options.preferences
    local progressScope = options.progressScope
    local tracker = options.tracker
    local preparePhoto = options.preparePhoto
    local confirmPhoto = options.confirmPhoto
    local applyOne = options.applyOne
    local recordBaseline = options.recordBaseline
    local onRelease = options.onRelease or function()
    end
    local automatic = preferences.confirmationMode == "never"

    for index, photo in ipairs(photos) do
        if progressScope:isCanceled() then
            summary.cancelled = true
            BatchSummary.markNotProcessed(summary, #photos - index + 1)
            break
        end

        local photoIdentity = Utils.capturePhotoIdentity(photo)
        local filename = photoIdentity.displayFilename
        tracker:setPhase("Preparing recommendation")
        tracker:setCurrent(filename, index)
        tracker:setBatchCounts(summary)
        progressScope:setCaption(tracker:caption())
        progressScope:setPortionComplete(summary.processed, #photos)
        BatchSummary.markAttempted(summary)

        local outcome, value = preparePhoto(
            photo,
            options.batchDirectory,
            progressScope,
            preferences,
            tracker,
            photoIdentity
        )

        if outcome == "cancelled" or progressScope:isCanceled() then
            summary.cancelled = true
            BatchSummary.markNotProcessed(summary, #photos - index + 1)
            if outcome == "ready" and type(value) == "table" then
                onRelease(value)
            end
            break
        elseif outcome == "failed" then
            BatchSummary.recordProcessedFailure(summary, filename, value)
            if type(value) == "table"
                and ErrorClassifier.isTerminalForBatch(value.category) then
                summary.terminalCategory = value.category
                BatchSummary.markNotProcessed(
                    summary,
                    #photos - index
                )
                updateProgress(progressScope, tracker, summary, index)
                break
            end
        elseif outcome == "skipped" then
            recordPreparationSkip(summary, value)
        elseif outcome ~= "ready"
            or not validPreparedOperation(value) then
            BatchSummary.recordProcessedFailure(
                summary,
                filename,
                PreparationService.failure(
                    ErrorClassifier.codes.internalError,
                    "invalid_prepared_operation"
                )
            )
        else
            local operation = value
            BatchSummary.recordPrepared(summary, operation)
            tracker:setPhase("Reviewing recommendation")
            tracker:setBatchCounts(summary)
            progressScope:setCaption(tracker:caption())

            local decision = "apply"
            if not automatic then
                decision = confirmPhoto(operation, index, #photos)
            end

            if decision == "cancel_batch"
                or progressScope:isCanceled() then
                summary.cancelled = true
                BatchSummary.markNotProcessed(
                    summary,
                    #photos - index + 1
                )
                onRelease(operation)
                operation = nil
                break
            elseif decision == "skip" then
                BatchSummary.recordSkipped(summary)
            elseif decision == "apply"
                or decision == "apply_remaining" then
                if decision == "apply_remaining" then
                    automatic = true
                end
                tracker:setPhase("Applying recommendation")
                progressScope:setCaption(tracker:caption())
                local application = applyOne(
                    options.catalog,
                    operation
                )
                BatchSummary.recordApplication(
                    summary,
                    operation,
                    application
                )
                if operation.applicationStatus == "applied"
                    and preferences.learningEnabled
                    and preferences.learningCaptureBaseline then
                    local learningResult =
                        recordBaseline(operation, preferences)
                    summary.learningBaselineSaved =
                        (summary.learningBaselineSaved or 0)
                        + learningResult.saved
                    summary.learningBaselineFailed =
                        (summary.learningBaselineFailed or 0)
                        + learningResult.failed
                    summary.warningCount =
                        (summary.warningCount or 0)
                        + learningResult.failed
                end
            else
                BatchSummary.recordProcessedFailure(
                    summary,
                    filename,
                    PreparationService.failure(
                        ErrorClassifier.codes.internalError,
                        "invalid_confirmation_result"
                    )
                )
            end
            onRelease(operation)
            operation = nil
        end

        updateProgress(progressScope, tracker, summary, index)
        if progressScope:isCanceled() then
            summary.cancelled = true
            BatchSummary.markNotProcessed(summary, #photos - index)
            break
        end
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
            "Select one or more photos to auto develop.",
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
    local summary = newSummary(
        #photos,
        preferences.styleProfileId,
        preferences.modelProfileId
    )
    summary.backendBaseUrl = preferences.backendBaseUrl
    summary.requestTimeoutSeconds = preferences.requestTimeoutSeconds
    summary.confirmationMode = preferences.confirmationMode
    summary.showLearningSummary = preferences.learningShowSummary
    Logger.info(
        "Auto Develop Selected Photos start selected="
            .. tostring(#photos)
            .. " profile="
            .. preferences.styleProfileId
    )
    local batchDirectory, directoryError =
        PreviewExporter.createBatchDirectory()
    if not batchDirectory then
        Logger.error(
            "operation=create_develop_preview_directory "
                .. "category=internal_error code=preview_directory_failed"
        )
        LrDialogs.message(
            "AutoDevelop AI",
            "Could not create temporary previews for Auto Develop.",
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
        title = "AutoDevelop AI",
        caption = "Preparing selected photos",
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
    local tracker =
        ProgressTracker.new(#photos, "Preparing recommendation")
    tracker:setBatchCounts(summary)

    summary = processSequential({
        photos = photos,
        catalog = catalog,
        batchDirectory = batchDirectory,
        progressScope = progressScope,
        tracker = tracker,
        summary = summary,
        preferences = preferences,
        preparePhoto = PreparationService.prepareDevelopPhoto,
        confirmPhoto = AutoDevelopConfirmationDialog.confirmPhoto,
        applyOne = ApplyService.applyOne,
        recordBaseline = LearningBaselineService.recordOne,
    })
    releaseBatch()
    releaseProgress()
    AutoDevelopConfirmationDialog.showFinal(summary, {
        applied = summary.applied,
        cropApplied = summary.cropAppliedCount,
        levelingApplied = summary.levelingAppliedCount,
        restoredAfterFailure = summary.restoredAfterFailure,
        failedNotRestored = summary.failedNotRestored,
        notApplied = summary.notProcessed,
    })
    Logger.info(
        "Auto Develop complete applied="
            .. tostring(summary.applied)
            .. " restored="
            .. tostring(summary.restoredAfterFailure)
            .. " failed_not_restored="
            .. tostring(summary.failedNotRestored)
            .. " not_processed="
            .. tostring(summary.notProcessed)
    )
end

function AutoDevelopCommand.start()
    LrTasks.startAsyncTask(function()
        local ok, failure = LrTasks.pcall(function()
            return LrFunctionContext.callWithContext(
                "AutoDevelop AI Auto Develop Selected Photos",
                runCommand
            )
        end)
        if not ok then
            Logger.error(
                "operation=auto_develop_command category=internal_error "
                    .. "code=unexpected_exception"
            )
            ErrorDialog.show(ErrorClassifier.codes.internalError)
        end
    end)
end

AutoDevelopCommand.processSequential = processSequential
AutoDevelopCommand.newSummary = newSummary

return AutoDevelopCommand
