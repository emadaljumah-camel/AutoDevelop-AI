local LrFunctionContext = import("LrFunctionContext")
local LrTasks = import("LrTasks")

local ApiClient = ModuleLoader.load("lib/ApiClient.lua")
local ApplyService = ModuleLoader.load("lib/ApplyService.lua")
local BatchPolicy = ModuleLoader.load("lib/BatchPolicy.lua")
local CropMapper = ModuleLoader.load("lib/CropMapper.lua")
local DevelopSettingsMapper =
    ModuleLoader.load("lib/DevelopSettingsMapper.lua")
local ErrorClassifier = ModuleLoader.load("lib/ErrorClassifier.lua")
local ExifMapper = ModuleLoader.load("lib/ExifMapper.lua")
local Logger = ModuleLoader.load("lib/Logger.lua")
local PendingOperation = ModuleLoader.load("lib/PendingOperation.lua")
local PreviewExporter = ModuleLoader.load("lib/PreviewExporter.lua")
local RequestBuilder = ModuleLoader.load("lib/RequestBuilder.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")
local Validation = ModuleLoader.load("lib/Validation.lua")

local PreparationService = {}

local function markLifecycle(lifecycle, stage)
    lifecycle.stage = stage
    Logger.info(stage)
end

local function logStageFailure(stage, category)
    Logger.warn(
        "stage="
            .. tostring(stage or "post_response")
            .. " category="
            .. tostring(category or ErrorClassifier.codes.internalError)
    )
end

function PreparationService.failure(category, code)
    return {
        ok = false,
        category = category or ErrorClassifier.codes.internalError,
        code = code or "operation_failed",
        retryable = false,
    }
end

local function stagedFailure(category, code, lifecycle)
    local failure = PreparationService.failure(category, code)
    failure.stage = Utils.safeErrorCode(
        lifecycle and lifecycle.stage,
        "develop_preparation_entry"
    )
    return failure
end

function PreparationService.request(
    requestKind,
    request,
    progressScope,
    connectionOptions,
    tracker
)
    local requestFunction = ApiClient[requestKind]
    if type(requestFunction) ~= "function" then
        return nil, PreparationService.failure(
            ErrorClassifier.codes.internalError,
            "unknown_request_kind"
        )
    end

    local retriesUsed = 0
    while true do
        if progressScope:isCanceled() then
            return nil, PreparationService.failure(
                ErrorClassifier.codes.cancelled,
                "user_cancelled"
            )
        end

        if tracker then
            tracker:setPhase("Contacting AutoDevelop AI")
            tracker:setCurrent(request.filename)
            progressScope:setCaption(tracker:caption())
        end
        local result = requestFunction(request, connectionOptions)
        if progressScope:isCanceled() then
            return nil, PreparationService.failure(
                ErrorClassifier.codes.cancelled,
                "user_cancelled"
            )
        end
        Logger.info(
            requestKind
                .. " HTTP request_id="
                .. request.request_id
                .. " filename="
                .. request.filename
                .. " status="
                .. tostring(
                    result.status
                        or Utils.safeErrorCode(result.code, "network")
                )
        )
        if result.ok then
            return result
        end
        if progressScope:isCanceled() then
            return nil, PreparationService.failure(
                ErrorClassifier.codes.cancelled,
                "user_cancelled"
            )
        end
        if BatchPolicy.shouldRetry(
            result,
            retriesUsed,
            progressScope:isCanceled()
        ) then
            retriesUsed = retriesUsed + 1
            if progressScope:isCanceled() then
                return nil, PreparationService.failure(
                    ErrorClassifier.codes.cancelled,
                    "user_cancelled"
                )
            end
            LrTasks.sleep(0.5)
        else
            result.requestId = request.request_id
            result.filename = request.filename
            return nil, result
        end
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
        return nil
    end
    return Utils.deepCopy(settings)
end

local function cleanupPreview(preview)
    local ok, cleaned, reason = LrTasks.pcall(
        PreviewExporter.cleanupPreview,
        preview
    )
    if not ok or not cleaned then
        Logger.warn(
            "operation=develop_preview_cleanup category=cleanup_failed "
                .. "code=preview_cleanup_failed"
        )
    end
end

local function prepareDevelopPhotoBody(
    photo,
    batchDirectory,
    progressScope,
    context,
    preferences,
    tracker,
    lifecycle
)
    markLifecycle(lifecycle, "develop_preparation_started")
    if not ExifMapper.isSupportedPhoto(photo) then
        return "skipped", "Videos are not supported."
    end
    if progressScope:isCanceled() then
        return "cancelled", PreparationService.failure(
            ErrorClassifier.codes.cancelled,
            "user_cancelled"
        )
    end

    markLifecycle(lifecycle, "preview_export_started")
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
        logStageFailure(
            lifecycle.stage,
            ErrorClassifier.codes.internalError
        )
        return "failed", PreparationService.failure(
            ErrorClassifier.codes.internalError,
            "preview_export_failed"
        )
    end
    markLifecycle(lifecycle, "preview_export_completed")

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

    markLifecycle(lifecycle, "request_build_started")
    local request, requestError = RequestBuilder.buildDevelop(
        photo,
        preview.path,
        {
            styleProfileId = preferences.styleProfileId,
            includeCrop = true,
            includeDenoise = true,
            preserveCurrentAdjustments = true,
        }
    )
    if not request then
        logStageFailure(
            lifecycle.stage,
            ErrorClassifier.codes.validationError
        )
        return "failed", PreparationService.failure(
            ErrorClassifier.codes.validationError,
            "request_build_failed"
        )
    end
    markLifecycle(lifecycle, "request_build_completed")

    markLifecycle(lifecycle, "api_request_started")
    local response, requestFailure = PreparationService.request(
        "develop",
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
        logStageFailure(lifecycle.stage, requestFailure.category)
        return "failed", requestFailure
    end
    markLifecycle(lifecycle, "api_response_received")
    if progressScope:isCanceled() then
        return "cancelled", PreparationService.failure(
            ErrorClassifier.codes.cancelled,
            "user_cancelled"
        )
    end

    markLifecycle(lifecycle, "json_decode_started")
    local decoded, decodeError = ApiClient.decodeBody(response)
    if not decoded then
        logStageFailure(
            lifecycle.stage,
            ErrorClassifier.codes.invalidResponse
        )
        return "failed", PreparationService.failure(
            ErrorClassifier.codes.invalidResponse,
            "malformed_json"
        )
    end
    markLifecycle(lifecycle, "json_decode_completed")

    markLifecycle(lifecycle, "response_validation_started")
    local valid, validationError, validatedModel =
        Validation.validateDevelopResponse(decoded, request)
    if not valid then
        logStageFailure(
            lifecycle.stage,
            ErrorClassifier.codes.invalidResponse
        )
        return "failed", PreparationService.failure(
            ErrorClassifier.codes.invalidResponse,
            "response_validation_failed"
        )
    end
    markLifecycle(lifecycle, "response_validation_completed")

    markLifecycle(lifecycle, "develop_mapping_started")
    local currentSettings = currentDevelopSettings(photo)
    if not currentSettings then
        logStageFailure(
            lifecycle.stage,
            ErrorClassifier.codes.internalError
        )
        return "failed", PreparationService.failure(
            ErrorClassifier.codes.internalError,
            "current_settings_unavailable"
        )
    end

    local mappedSettings = DevelopSettingsMapper.map(
        decoded.develop_settings,
        currentSettings
    )
    markLifecycle(lifecycle, "develop_mapping_completed")

    markLifecycle(lifecycle, "crop_mapping_started")
    local mappedCrop = CropMapper.map(
        decoded.crop,
        preferences.applyCrop,
        currentSettings
    )
    markLifecycle(lifecycle, "crop_mapping_completed")
    local cropDisabled = preferences.applyCrop == false
        and type(decoded.crop) == "table"
        and decoded.crop.recommended == true
    local denoiseRecommended = type(decoded.denoise) == "table"
        and decoded.denoise.recommended == true
    mappedSettings = mergeSettings(mappedSettings, mappedCrop)
    if progressScope:isCanceled() then
        return "cancelled", PreparationService.failure(
            ErrorClassifier.codes.cancelled,
            "user_cancelled"
        )
    end
    local settingCount = countSettings(mappedSettings)
    if settingCount == 0 then
        return "skipped", {
            cropDisabled = cropDisabled,
            denoiseRecommended = denoiseRecommended,
        }
    end

    markLifecycle(lifecycle, "pending_operation_build_started")
    local originalSettings = ApplyService.captureOriginal(
        currentSettings,
        mappedSettings
    )
    if countSettings(originalSettings) ~= settingCount then
        logStageFailure(
            lifecycle.stage,
            ErrorClassifier.codes.internalError
        )
        return "failed", PreparationService.failure(
            ErrorClassifier.codes.internalError,
            "original_settings_unavailable"
        )
    end

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
        warnings = Utils.deepCopy(decoded.warnings or {}),
        model = validatedModel,
        processingDurationMs = decoded.processing_duration_ms,
    })
    operation.cropDisabled = cropDisabled
    markLifecycle(lifecycle, "pending_operation_build_completed")
    if progressScope:isCanceled() then
        PendingOperation.clear({ operation })
        return "cancelled", PreparationService.failure(
            ErrorClassifier.codes.cancelled,
            "user_cancelled"
        )
    end
    return "ready", operation
end

function PreparationService.prepareDevelopPhoto(
    photo,
    batchDirectory,
    progressScope,
    preferences,
    tracker
)
    local lifecycle = {
        stage = "develop_preparation_entry",
    }
    local ok, result = LrTasks.pcall(function()
        return LrFunctionContext.callWithContext(
            "AutoDevelop AI Prepare Photo",
            function(context)
                local outcome, value = prepareDevelopPhotoBody(
                    photo,
                    batchDirectory,
                    progressScope,
                    context,
                    preferences,
                    tracker,
                    lifecycle
                )
                return {
                    outcome = outcome,
                    value = value,
                }
            end
        )
    end)
    if not ok then
        logStageFailure(
            lifecycle.stage,
            ErrorClassifier.codes.internalError
        )
        return "failed", stagedFailure(
            ErrorClassifier.codes.internalError,
            "unexpected_plugin_error",
            lifecycle
        )
    end
    if type(result) ~= "table"
        or type(result.outcome) ~= "string" then
        logStageFailure(
            lifecycle.stage,
            ErrorClassifier.codes.internalError
        )
        return "failed", stagedFailure(
            ErrorClassifier.codes.internalError,
            "invalid_preparation_result",
            lifecycle
        )
    end
    return result.outcome, result.value
end

return PreparationService
