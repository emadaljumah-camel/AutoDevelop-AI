local LrApplication = import("LrApplication")
local LrDialogs = import("LrDialogs")
local LrFunctionContext = import("LrFunctionContext")
local LrProgressScope = import("LrProgressScope")
local LrTasks = import("LrTasks")

local ApiClient = ModuleLoader.load("lib/ApiClient.lua")
local ApplyService = ModuleLoader.load("lib/ApplyService.lua")
local BatchPolicy = ModuleLoader.load("lib/BatchPolicy.lua")
local Config = ModuleLoader.load("lib/Config.lua")
local CropMapper = ModuleLoader.load("lib/CropMapper.lua")
local DevelopSettingsMapper =
    ModuleLoader.load("lib/DevelopSettingsMapper.lua")
local ExifMapper = ModuleLoader.load("lib/ExifMapper.lua")
local Logger = ModuleLoader.load("lib/Logger.lua")
local PendingOperation = ModuleLoader.load("lib/PendingOperation.lua")
local PreviewExporter = ModuleLoader.load("lib/PreviewExporter.lua")
local RequestBuilder = ModuleLoader.load("lib/RequestBuilder.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")
local Validation = ModuleLoader.load("lib/Validation.lua")
local AutoDevelopConfirmationDialog =
    ModuleLoader.load("dialogs/AutoDevelopConfirmationDialog.lua")

local AutoDevelopCommand = {}

local function cleanupPreview(preview)
    local ok, cleaned, reason = LrTasks.pcall(
        PreviewExporter.cleanupPreview,
        preview
    )
    if not ok or not cleaned then
        Logger.warn(
            "Temporary develop preview cleanup failed: "
                .. Utils.safeMessage(reason or cleaned, "unknown cleanup error")
        )
    end
end

local function cleanupBatch(batchDirectory)
    local ok, cleaned, reason = LrTasks.pcall(
        PreviewExporter.cleanupBatch,
        batchDirectory
    )
    if not ok or not cleaned then
        Logger.warn(
            "Develop batch cleanup failed: "
                .. Utils.safeMessage(reason or cleaned, "unknown cleanup error")
        )
    end
end

local function finishProgress(progressScope)
    local ok, reason = LrTasks.pcall(function()
        progressScope:done()
    end)
    if not ok then
        Logger.warn(
            "Develop progress cleanup failed: "
                .. Utils.safeMessage(reason, "unknown progress error")
        )
    end
end

local function newSummary(selected, profileId)
    return {
        selected = selected,
        ready = 0,
        failed = 0,
        skipped = 0,
        notProcessed = 0,
        cancelled = false,
        backendUnavailable = false,
        profileId = profileId,
        cropCount = 0,
        denoiseIgnored = 0,
        warningCount = 0,
        models = {},
        failures = {},
        examples = {},
    }
end

local function addFailure(summary, filename, reason)
    summary.failed = summary.failed + 1
    if #summary.failures < 5 then
        summary.failures[#summary.failures + 1] = {
            filename = filename,
            reason = reason,
        }
    end
end

local function countSettings(settings)
    local count = 0
    for _ in pairs(settings or {}) do
        count = count + 1
    end
    return count
end

local function mergeSettings(first, second)
    local merged = Utils.deepCopy(first or {})
    for key, value in pairs(second or {}) do
        merged[key] = value
    end
    return merged
end

local function currentDevelopSettings(photo)
    local ok, settings = LrTasks.pcall(function()
        return photo:getDevelopSettings()
    end)
    if not ok or type(settings) ~= "table" then
        return nil, "Could not capture the current develop settings."
    end
    return Utils.deepCopy(settings)
end

local function requestBackend(request, progressScope)
    local retriesUsed = 0
    while true do
        if progressScope:isCanceled() then
            return nil, "cancelled", "Preparation was cancelled."
        end
        local response = ApiClient.develop(request)
        Logger.info(
            "Develop HTTP request_id="
                .. request.request_id
                .. " filename="
                .. request.filename
                .. " profile="
                .. request.options.style_profile
                .. " status="
                .. tostring(response.status or "transport-error")
        )
        if response.transportError then
            return nil,
                "connection",
                "The AutoDevelop AI backend is unavailable."
        end
        if progressScope:isCanceled() then
            return nil, "cancelled", "Preparation was cancelled."
        end
        if BatchPolicy.shouldRetry(
            response.status,
            retriesUsed,
            progressScope:isCanceled()
        ) then
            retriesUsed = retriesUsed + 1
            LrTasks.sleep(0.5)
        else
            return response
        end
    end
end

local function processPhotoBody(
    photo,
    batchDirectory,
    progressScope,
    context
)
    if not ExifMapper.isSupportedPhoto(photo) then
        return "skipped", "Videos are not supported."
    end
    if progressScope:isCanceled() then
        return "cancelled", "Preparation was cancelled."
    end

    local preview, previewError = PreviewExporter.exportPhoto(
        photo,
        batchDirectory,
        progressScope
    )
    if not preview then
        if progressScope:isCanceled() then
            return "cancelled", "Preparation was cancelled."
        end
        return "failed", Utils.safeMessage(
            previewError,
            "Could not create a temporary preview."
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
        return "cancelled", "Preparation was cancelled."
    end

    local request, requestError = RequestBuilder.buildDevelop(
        photo,
        preview.path,
        {
            styleProfileId = Config.getStyleProfileId(),
            includeCrop = true,
            includeDenoise = true,
            preserveCurrentAdjustments = true,
        }
    )
    if not request then
        return "failed", Utils.safeMessage(
            requestError,
            "Could not build the Develop request."
        )
    end

    Logger.info(
        "Develop request start request_id="
            .. request.request_id
            .. " filename="
            .. request.filename
    )
    local response, connectionOutcome, connectionReason = requestBackend(
        request,
        progressScope
    )
    if not response then
        return connectionOutcome, connectionReason
    end

    local decoded, decodeError = ApiClient.decodeBody(response)
    if response.status < 200 or response.status >= 300 then
        local parsed = Validation.parseErrorResponse(decoded, response.status)
        return "failed", parsed.message
    end
    if not decoded then
        Logger.warn(
            "Develop response JSON failure request_id="
                .. request.request_id
                .. " reason="
                .. Utils.safeMessage(decodeError, "invalid JSON")
        )
        return "failed", "The backend returned malformed JSON."
    end

    local valid, validationError =
        Validation.validateDevelopResponse(decoded, request)
    if not valid then
        Logger.warn(
            "Develop response validation failed request_id="
                .. request.request_id
                .. " reason="
                .. Utils.safeMessage(validationError, "invalid response")
        )
        return "failed", validationError
    end

    local currentSettings, currentError = currentDevelopSettings(photo)
    if not currentSettings then
        return "failed", currentError
    end
    local mappedSettings = DevelopSettingsMapper.map(
        decoded.develop_settings,
        currentSettings
    )
    local mappedCrop = CropMapper.map(
        decoded.crop,
        Config.getApplyCrop(),
        currentSettings
    )
    mappedSettings = mergeSettings(mappedSettings, mappedCrop)
    local settingCount = countSettings(mappedSettings)
    if settingCount == 0 then
        return "skipped", "No safely applicable develop settings remained."
    end

    local originalSettings = ApplyService.captureOriginal(
        currentSettings,
        mappedSettings
    )
    if countSettings(originalSettings) ~= settingCount then
        return "failed", "Original settings could not be captured safely."
    end

    local warnings = Utils.deepCopy(decoded.warnings or {})
    local denoiseRecommended = type(decoded.denoise) == "table"
        and decoded.denoise.recommended == true
    local operation = PendingOperation.new({
        photo = photo,
        photoKey = Utils.photoKey(photo),
        filename = request.filename,
        requestId = request.request_id,
        profileId = request.options.style_profile,
        originalSettings = originalSettings,
        mappedSettings = mappedSettings,
        cropIncluded = mappedCrop ~= nil,
        denoiseRecommended = denoiseRecommended,
        warnings = warnings,
        model = decoded.model,
        processingDurationMs = decoded.processing_duration_ms,
    })
    Logger.info(
        "Develop response prepared request_id="
            .. request.request_id
            .. " settings="
            .. tostring(settingCount)
            .. " crop="
            .. tostring(operation.cropIncluded)
            .. " denoise_ignored="
            .. tostring(operation.denoiseRecommended)
    )
    return "ready", operation
end

local function processPhoto(photo, batchDirectory, progressScope)
    local ok, outcome, value = LrTasks.pcall(function()
        return LrFunctionContext.callWithContext(
            "AutoDevelop AI Prepare Photo",
            function(context)
                return processPhotoBody(
                    photo,
                    batchDirectory,
                    progressScope,
                    context
                )
            end
        )
    end)
    if not ok then
        Logger.error(
            "Unexpected develop preparation error: " .. tostring(outcome)
        )
        return "failed", "An unexpected plug-in error occurred."
    end
    return outcome, value
end

local function prepareBatch(
    photos,
    progressScope,
    batchDirectory,
    summary,
    operations
)
    for index, photo in ipairs(photos) do
        if progressScope:isCanceled() then
            summary.cancelled = true
            BatchPolicy.markNotProcessed(summary, #photos - index + 1)
            break
        end

        local filename = Utils.photoFilename(photo)
        progressScope:setCaption(
            "Preparing "
                .. tostring(index)
                .. " of "
                .. tostring(#photos)
                .. ": "
                .. filename
        )
        local outcome, value = processPhoto(
            photo,
            batchDirectory,
            progressScope
        )
        if outcome == "ready" then
            operations[#operations + 1] = value
            summary.ready = summary.ready + 1
            if value.cropIncluded then
                summary.cropCount = summary.cropCount + 1
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
        elseif outcome == "skipped" then
            summary.skipped = summary.skipped + 1
        elseif outcome == "connection" then
            addFailure(summary, filename, value)
            summary.backendUnavailable = true
            BatchPolicy.markNotProcessed(summary, #photos - index)
            progressScope:setPortionComplete(index, #photos)
            break
        elseif outcome == "cancelled" then
            summary.cancelled = true
            BatchPolicy.markNotProcessed(summary, #photos - index + 1)
            break
        else
            addFailure(summary, filename, value)
        end
        progressScope:setPortionComplete(index, #photos)
    end
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

    local profileId = Config.getStyleProfileId()
    local summary = newSummary(#photos, profileId)
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
            .. profileId
    )
    local batchDirectory, directoryError =
        PreviewExporter.createBatchDirectory()
    if not batchDirectory then
        Logger.error(
            "Could not create develop preview directory: "
                .. Utils.safeMessage(directoryError, "unknown error")
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

    prepareBatch(
        photos,
        preparationProgress,
        batchDirectory,
        summary,
        operations
    )
    releaseBatch()
    releasePreparationProgress()

    if summary.cancelled then
        local application = defaultApplication(#operations)
        application.userCancelled = true
        AutoDevelopConfirmationDialog.showFinal(summary, application)
        releaseOperations()
        return
    end
    if #operations == 0 then
        AutoDevelopConfirmationDialog.showFinal(
            summary,
            defaultApplication(0)
        )
        releaseOperations()
        return
    end

    local confirmed = AutoDevelopConfirmationDialog.confirm(summary)
    Logger.info("Auto Develop confirmation apply=" .. tostring(confirmed))
    if not confirmed then
        local application = defaultApplication(#operations)
        application.userCancelled = true
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

    local application
    if applyProgress:isCanceled() then
        application = defaultApplication(#operations)
        application.cancelled = true
    else
        application = ApplyService.applyBatch(catalog, operations, {
            isCancelled = function()
                return applyProgress:isCanceled()
            end,
            onProgress = function(index, total, operation)
                applyProgress:setCaption(
                    "Applying "
                        .. tostring(index)
                        .. " of "
                        .. tostring(total)
                        .. ": "
                        .. operation.filename
                )
                applyProgress:setPortionComplete(index - 1, total)
            end,
        })
    end
    releaseApplyProgress()
    for _, operation in ipairs(operations) do
        local message = "Auto Develop application filename="
            .. operation.filename
            .. " status="
            .. tostring(operation.applicationStatus)
        if operation.applicationStatus == "applied" then
            Logger.info(message)
        else
            Logger.warn(
                message
                    .. " reason="
                    .. Utils.safeMessage(
                        operation.applyError,
                        "not applied"
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
                "Auto Develop Selected Photos failed: " .. tostring(failure)
            )
            LrDialogs.message(
                "AutoDevelop AI",
                "Auto Develop Selected Photos encountered an unexpected error.",
                "critical"
            )
        end
    end)
end

AutoDevelopCommand.prepareBatch = prepareBatch
AutoDevelopCommand.newSummary = newSummary

return AutoDevelopCommand
