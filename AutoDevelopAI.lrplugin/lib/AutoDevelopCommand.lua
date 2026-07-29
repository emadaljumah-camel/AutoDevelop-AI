local LrApplication = import("LrApplication")
local LrDialogs = import("LrDialogs")
local LrFunctionContext = import("LrFunctionContext")
local LrProgressScope = import("LrProgressScope")
local LrTasks = import("LrTasks")

local ApplicationGate = ModuleLoader.load("lib/ApplicationGate.lua")
local ApplyService = ModuleLoader.load("lib/ApplyService.lua")
local BatchOperationRecorder =
    ModuleLoader.load("lib/BatchOperationRecorder.lua")
local BatchSummary = ModuleLoader.load("lib/BatchSummary.lua")
local ErrorClassifier = ModuleLoader.load("lib/ErrorClassifier.lua")
local Logger = ModuleLoader.load("lib/Logger.lua")
local PendingOperation = ModuleLoader.load("lib/PendingOperation.lua")
local Preferences = ModuleLoader.load("lib/Preferences.lua")
local PreparationService = ModuleLoader.load("lib/PreparationService.lua")
local PreviewExporter = ModuleLoader.load("lib/PreviewExporter.lua")
local ProgressTracker = ModuleLoader.load("lib/ProgressTracker.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")
local AutoDevelopConfirmationDialog =
    ModuleLoader.load("dialogs/AutoDevelopConfirmationDialog.lua")
local ErrorDialog = ModuleLoader.load("dialogs/ErrorDialog.lua")

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

local function newSummary(selected, profileId)
    local summary = BatchSummary.new(selected, "develop")
    summary.profileId = profileId
    summary.models = {}
    summary.examples = {}
    return summary
end

local function addFailure(summary, filename, failure)
    BatchSummary.addFailure(summary, filename, failure)
end

local function countSettings(settings)
    local count = 0
    for _ in pairs(settings or {}) do
        count = count + 1
    end
    return count
end

local function prepareBatch(
    photos,
    progressScope,
    batchDirectory,
    summary,
    operations,
    preferences,
    tracker
)
    for index, photo in ipairs(photos) do
        if progressScope:isCanceled() then
            summary.cancelled = true
            BatchSummary.markNotProcessed(summary, #photos - index + 1)
            break
        end

        local filename = Utils.photoFilename(photo)
        tracker:setPhase("Preparing recommendations")
        tracker:setCurrent(filename, index)
        progressScope:setCaption(tracker:caption())
        local outcome, value = PreparationService.prepareDevelopPhoto(
            photo,
            batchDirectory,
            progressScope,
            preferences,
            tracker
        )
        local terminalFailure = outcome == "failed"
            and type(value) == "table"
            and ErrorClassifier.isTerminalForBatch(value.category)
        local recordingStatus = BatchOperationRecorder.tryRecord({
            cancelled = progressScope:isCanceled(),
            terminalFailure = terminalFailure,
            preparationResult = outcome,
            operation = value,
            operations = operations,
        })
        if recordingStatus == "recorded" then
            summary.ready = summary.ready + 1
            if value.cropIncluded then
                summary.cropCount = summary.cropCount + 1
            end
            if value.cropDisabled then
                summary.cropDisabled = summary.cropDisabled + 1
            end
            if value.denoiseRecommended then
                summary.denoiseIgnored = summary.denoiseIgnored + 1
            end
            summary.warningCount =
                summary.warningCount + #(value.warnings or {})
            summary.models[value.model] = true
            if #summary.examples < 5 then
                summary.examples[#summary.examples + 1] = {
                    filename = value.filename,
                    settingCount = countSettings(value.mappedSettings),
                    cropIncluded = value.cropIncluded,
                    warningCount = #(value.warnings or {}),
                }
            end
        elseif recordingStatus == "cancelled" then
            summary.cancelled = true
            BatchSummary.markNotProcessed(summary, #photos - index + 1)
            break
        elseif recordingStatus == "terminal_failure" then
            addFailure(summary, filename, value)
            summary.terminalCategory = value.category
            BatchSummary.markNotProcessed(summary, #photos - index)
            tracker:markCompleted(index)
            progressScope:setPortionComplete(index, #photos)
            progressScope:setCaption(tracker:caption())
            break
        elseif outcome == "skipped" then
            summary.skipped = summary.skipped + 1
            if type(value) == "table" and value.cropDisabled then
                summary.cropDisabled = summary.cropDisabled + 1
            end
            if type(value) == "table" and value.denoiseRecommended then
                summary.denoiseIgnored = summary.denoiseIgnored + 1
            end
        elseif outcome == "ready" then
            addFailure(
                summary,
                filename,
                PreparationService.failure(
                    ErrorClassifier.codes.internalError,
                    "invalid_prepared_operation"
                )
            )
        else
            addFailure(summary, filename, value)
        end
        tracker:markCompleted(index)
        progressScope:setPortionComplete(index, #photos)
        progressScope:setCaption(tracker:caption())
    end
    if progressScope:isCanceled() then
        summary.cancelled = true
    end
    summary.elapsedSeconds = tracker:elapsedSeconds()
end

local function defaultApplication(notApplied)
    return {
        applied = 0,
        restoredAfterFailure = 0,
        failedNotRestored = 0,
        notApplied = notApplied or 0,
        cancelled = false,
        userCancelled = false,
    }
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

    local preferences, _, invalidKey = Preferences.validatedSnapshot()
    if not preferences then
        local current = Preferences.valuesForUi()
        ErrorDialog.show(
            invalidKey == "styleProfileId"
                and ErrorClassifier.codes.invalidProfile
                or ErrorClassifier.codes.validationError,
            {
                backendBaseUrl = current.backendBaseUrl,
                requestTimeoutSeconds = current.requestTimeoutSeconds,
                profileId = current.styleProfileId,
            }
        )
        return
    end
    local summary = newSummary(#photos, preferences.styleProfileId)
    summary.backendBaseUrl = preferences.backendBaseUrl
    summary.requestTimeoutSeconds = preferences.requestTimeoutSeconds
    summary.confirmationMode = preferences.confirmationMode
    local operations = {}
    local operationsCleared = false
    local function releaseOperations()
        if operationsCleared then
            return
        end
        operationsCleared = true
        PendingOperation.clear(operations)
    end
    context:addCleanupHandler(releaseOperations)

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

    local preparationProgress = LrProgressScope({
        title = "Preparing AutoDevelop recommendations",
        caption = "Preparing selected photos",
    })
    local preparationFinished = false
    local function releasePreparationProgress()
        if preparationFinished then
            return
        end
        preparationFinished = true
        finishProgress(preparationProgress)
    end
    context:addCleanupHandler(releasePreparationProgress)
    preparationProgress:setCancelable(true)
    local preparationTracker =
        ProgressTracker.new(#photos, "Preparing recommendations")

    prepareBatch(
        photos,
        preparationProgress,
        batchDirectory,
        summary,
        operations,
        preferences,
        preparationTracker
    )
    local preparationDecision = ApplicationGate.evaluate({
        confirmationMode = preferences.confirmationMode,
        preparationCancelled = summary.cancelled,
        progressCancelled = preparationProgress:isCanceled(),
        terminalFailure = summary.terminalCategory ~= nil,
        readyCount = #operations,
    })
    if preparationDecision.cancelled then
        summary.cancelled = true
    end
    releaseBatch()
    releasePreparationProgress()

    if preparationDecision.cancelled then
        if summary.terminalCategory then
            Logger.info(
                "operation=prepare_batch category=cancelled "
                    .. "code=cancelled_precedes_terminal "
                    .. "terminal_category="
                    .. Utils.safeErrorCode(
                        summary.terminalCategory,
                        "internal_error"
                    )
            )
        end
        local application = defaultApplication(#operations)
        application.userCancelled = true
        AutoDevelopConfirmationDialog.showFinal(summary, application)
        releaseOperations()
        return
    elseif preparationDecision.terminalFailure then
        local application = defaultApplication(#operations)
        ErrorDialog.show(summary.terminalCategory, summary)
        releaseOperations()
        return
    end
    if preparationDecision.reason == "no_operations" then
        AutoDevelopConfirmationDialog.showFinal(
            summary,
            defaultApplication(0)
        )
        releaseOperations()
        return
    end

    local confirmed = true
    if preparationDecision.reason == "confirmation_required" then
        confirmed = AutoDevelopConfirmationDialog.confirm(summary)
    end
    Logger.info(
        "Auto Develop confirmation_mode="
            .. preferences.confirmationMode
            .. " apply="
            .. tostring(confirmed)
    )
    local confirmedDecision = ApplicationGate.evaluate({
        confirmationMode = preferences.confirmationMode,
        preparationCancelled = summary.cancelled,
        progressCancelled = false,
        terminalFailure = summary.terminalCategory ~= nil,
        readyCount = #operations,
        confirmationAccepted = confirmed,
    })
    if not confirmedDecision.shouldApply then
        if confirmedDecision.cancelled then
            summary.cancelled = true
        end
        local application = defaultApplication(#operations)
        application.userCancelled =
            confirmedDecision.reason == "confirmation_declined"
                or confirmedDecision.cancelled
        AutoDevelopConfirmationDialog.showFinal(summary, application)
        releaseOperations()
        return
    end

    local applyProgress = LrProgressScope({
        title = "Applying AutoDevelop recommendations",
        caption = "Preparing to apply settings",
    })
    local applyFinished = false
    local function releaseApplyProgress()
        if applyFinished then
            return
        end
        applyFinished = true
        finishProgress(applyProgress)
    end
    context:addCleanupHandler(releaseApplyProgress)
    applyProgress:setCancelable(true)
    local applyTracker =
        ProgressTracker.new(#operations, "Applying recommendations")

    local application
    local finalDecision = ApplicationGate.evaluate({
        confirmationMode = preferences.confirmationMode,
        preparationCancelled = summary.cancelled,
        progressCancelled = applyProgress:isCanceled(),
        terminalFailure = summary.terminalCategory ~= nil,
        readyCount = #operations,
        confirmationAccepted = confirmed,
    })
    if not finalDecision.shouldApply then
        if finalDecision.cancelled then
            summary.cancelled = true
        end
        application = defaultApplication(#operations)
        application.cancelled = finalDecision.cancelled
        application.userCancelled = finalDecision.cancelled
    else
        application = ApplyService.applyBatch(catalog, operations, {
            isCancelled = function()
                return applyProgress:isCanceled()
            end,
            onProgress = function(index, total, operation)
                applyTracker:setCurrent(operation.filename, index)
                applyTracker:markCompleted(index - 1)
                applyProgress:setCaption(applyTracker:caption())
                applyProgress:setPortionComplete(index - 1, total)
            end,
        })
    end
    if application.cancelled then
        summary.cancelled = true
    end
    summary.elapsedSeconds = preparationTracker:elapsedSeconds()
    releaseApplyProgress()
    application.cropApplied = 0
    for _, operation in ipairs(operations) do
        local message = "Auto Develop application filename="
            .. operation.filename
            .. " status="
            .. tostring(operation.applicationStatus)
        if operation.applicationStatus == "applied" then
            if operation.cropIncluded then
                application.cropApplied = application.cropApplied + 1
            end
            Logger.info(message)
        else
            Logger.warn(
                message
                    .. " category="
                    .. Utils.safeErrorCode(
                        operation.applyErrorCategory,
                        "apply_failed"
                    )
                    .. " code="
                    .. Utils.safeErrorCode(
                        operation.applyErrorCode,
                        "operation_not_applied"
                    )
            )
        end
    end
    AutoDevelopConfirmationDialog.showFinal(summary, application)
    Logger.info(
        "Auto Develop complete applied="
            .. tostring(application.applied)
            .. " restored="
            .. tostring(application.restoredAfterFailure)
            .. " failed_not_restored="
            .. tostring(application.failedNotRestored)
            .. " not_applied="
            .. tostring(application.notApplied)
    )
    releaseOperations()
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

AutoDevelopCommand.prepareBatch = prepareBatch
AutoDevelopCommand.newSummary = newSummary

return AutoDevelopCommand
