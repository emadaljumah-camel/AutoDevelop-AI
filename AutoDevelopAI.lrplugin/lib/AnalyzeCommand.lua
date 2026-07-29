local LrApplication = import("LrApplication")
local LrDialogs = import("LrDialogs")
local LrFunctionContext = import("LrFunctionContext")
local LrProgressScope = import("LrProgressScope")
local LrTasks = import("LrTasks")

local ApiClient = require("lib.ApiClient")
local BatchPolicy = require("lib.BatchPolicy")
local Config = require("lib.Config")
local ExifMapper = require("lib.ExifMapper")
local Logger = require("lib.Logger")
local PreviewExporter = require("lib.PreviewExporter")
local RequestBuilder = require("lib.RequestBuilder")
local ResultStore = require("lib.ResultStore")
local Utils = require("lib.Utils")
local Validation = require("lib.Validation")
local AnalysisSummaryDialog = require("dialogs.AnalysisSummaryDialog")

local AnalyzeCommand = {}

local function cleanupPreview(preview)
    local ok, cleaned, reason = LrTasks.pcall(
        PreviewExporter.cleanupPreview,
        preview
    )
    if not ok then
        Logger.warn(
            "Temporary preview cleanup raised an error: "
                .. Utils.safeMessage(cleaned, "unknown cleanup error")
        )
        return
    end
    if not cleaned then
        Logger.warn(
            "Temporary preview cleanup failed: "
                .. Utils.safeMessage(reason, "unknown cleanup error")
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
            "Batch preview cleanup raised an error: "
                .. Utils.safeMessage(cleaned, "unknown cleanup error")
        )
        return
    end
    if not cleaned then
        Logger.warn(
            "Batch preview cleanup failed: "
                .. Utils.safeMessage(reason, "unknown cleanup error")
        )
    end
end

local function finishProgress(progressScope)
    local ok, reason = LrTasks.pcall(function()
        progressScope:done()
    end)
    if not ok then
        Logger.warn(
            "Progress cleanup failed: "
                .. Utils.safeMessage(reason, "unknown progress error")
        )
    end
end

local function requestBackend(request, progressScope)
    local retriesUsed = 0
    while true do
        if progressScope:isCanceled() then
            return nil, "cancelled", "Analysis was cancelled."
        end
        local response = ApiClient.analyze(request)
        Logger.info(
            "Analyze HTTP request_id="
                .. request.request_id
                .. " filename="
                .. request.filename
                .. " status="
                .. tostring(response.status or "transport-error")
        )

        if response.transportError then
            return nil, "connection", "The AutoDevelop AI backend is unavailable."
        end
        if progressScope:isCanceled() then
            return nil, "cancelled", "Analysis was cancelled."
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

    local preview, previewError = PreviewExporter.exportPhoto(
        photo,
        batchDirectory,
        progressScope
    )
    if not preview then
        if progressScope:isCanceled() then
            return "cancelled", "Analysis was cancelled."
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
        return "cancelled", "Analysis was cancelled."
    end

    local request, requestError = RequestBuilder.build(photo, preview.path, {
        styleProfileId = Config.getStyleProfileId(),
    })
    if not request then
        return "failed",
            Utils.safeMessage(requestError, "Could not build the request.")
    end

    Logger.info(
        "Analyze request start request_id="
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
            "Analyze response JSON failure request_id="
                .. request.request_id
                .. " reason="
                .. Utils.safeMessage(decodeError, "invalid JSON")
        )
        return "failed", "The backend returned malformed JSON."
    end

    local valid, validationError =
        Validation.validateAnalyzeResponse(decoded, request)
    if not valid then
        Logger.warn(
            "Analyze response validation failed request_id="
                .. request.request_id
                .. " reason="
                .. Utils.safeMessage(validationError, "invalid response")
        )
        return "failed", validationError
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
            .. tostring(decoded.model)
            .. " duration_ms="
            .. tostring(decoded.processing_duration_ms or "unavailable")
    )
    return "success"
end

local function processPhoto(photo, batchDirectory, progressScope)
    local ok, outcome, reason = LrTasks.pcall(function()
        return LrFunctionContext.callWithContext(
            "AutoDevelop AI Analyze Photo",
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
            "Unexpected per-photo analysis error: " .. tostring(outcome)
        )
        return "failed", "An unexpected plug-in error occurred."
    end
    return outcome, reason
end

local function runBatch(photos, progressScope, batchDirectory)
    local summary = BatchPolicy.newSummary(#photos)

    for index, photo in ipairs(photos) do
        if progressScope:isCanceled() then
            summary.cancelled = true
            BatchPolicy.markNotProcessed(summary, #photos - index + 1)
            break
        end

        local filename = Utils.photoFilename(photo)
        progressScope:setCaption(
            "Analyzing "
                .. tostring(index)
                .. " of "
                .. tostring(#photos)
                .. ": "
                .. filename
        )

        local outcome, reason = processPhoto(
            photo,
            batchDirectory,
            progressScope
        )
        if outcome == "success" then
            summary.analyzed = summary.analyzed + 1
        elseif outcome == "skipped" then
            summary.skipped = summary.skipped + 1
            if #summary.failures < 5 then
                summary.failures[#summary.failures + 1] = {
                    filename = filename,
                    reason = reason,
                }
            end
        elseif outcome == "connection" then
            BatchPolicy.addFailure(summary, filename, reason)
            summary.backendUnavailable = true
            BatchPolicy.markNotProcessed(summary, #photos - index)
            progressScope:setPortionComplete(index, #photos)
            break
        elseif outcome == "cancelled" then
            summary.cancelled = true
            BatchPolicy.markNotProcessed(summary, #photos - index + 1)
            break
        else
            BatchPolicy.addFailure(summary, filename, reason)
        end
        progressScope:setPortionComplete(index, #photos)
    end

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

    Logger.info("Analyze Selected Photos start selected=" .. tostring(#photos))
    local batchDirectory, directoryError =
        PreviewExporter.createBatchDirectory()
    if not batchDirectory then
        Logger.error(
            "Could not create batch preview directory: "
                .. Utils.safeMessage(directoryError, "unknown error")
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

    local summary = runBatch(photos, progressScope, batchDirectory)
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
    AnalysisSummaryDialog.show(summary)
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
                "Analyze Selected Photos failed: " .. tostring(failure)
            )
            LrDialogs.message(
                "AutoDevelop AI",
                "Analyze Selected Photos encountered an unexpected error.",
                "critical"
            )
        end
    end)
end

AnalyzeCommand.runBatch = runBatch

return AnalyzeCommand
