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

function PreparationService.failure(category, code)
    return {
        ok = false,
        category = category or ErrorClassifier.codes.internalError,
        code = code or "operation_failed",
        retryable = false,
    }
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
    tracker
)
    if not ExifMapper.isSupportedPhoto(photo) then
        return "skipped", "Videos are not supported."
    end
    if progressScope:isCanceled() then
        return "cancelled", PreparationService.failure(
            ErrorClassifier.codes.cancelled,
            "user_cancelled"
        )
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
            "operation=develop_preview_export category=internal_error "
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
        Logger.warn(
            "operation=build_develop_request category=validation_error "
                .. "code=request_build_failed"
        )
        return "failed", PreparationService.failure(
            ErrorClassifier.codes.validationError,
            "request_build_failed"
        )
    end

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
            "Develop response JSON failure request_id="
                .. request.request_id
                .. " category=invalid_response code=malformed_json"
        )
        return "failed", PreparationService.failure(
            ErrorClassifier.codes.invalidResponse,
            "malformed_json"
        )
    end

    local valid, validationError, validatedModel =
        Validation.validateDevelopResponse(decoded, request)
    if not valid then
        Logger.warn(
            "Develop response validation failed request_id="
                .. request.request_id
                .. " category=invalid_response "
                .. "code=response_validation_failed"
        )
        return "failed", PreparationService.failure(
            ErrorClassifier.codes.invalidResponse,
            "response_validation_failed"
        )
    end

    local currentSettings = currentDevelopSettings(photo)
    if not currentSettings then
        return "failed", PreparationService.failure(
            ErrorClassifier.codes.internalError,
            "current_settings_unavailable"
        )
    end

    local mappedSettings = DevelopSettingsMapper.map(
        decoded.develop_settings,
        currentSettings
    )
    local mappedCrop = CropMapper.map(
        decoded.crop,
        preferences.applyCrop,
        currentSettings
    )
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

    local originalSettings = ApplyService.captureOriginal(
        currentSettings,
        mappedSettings
    )
    if countSettings(originalSettings) ~= settingCount then
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
    local ok, outcome, value = LrTasks.pcall(function()
        return LrFunctionContext.callWithContext(
            "AutoDevelop AI Prepare Photo",
            function(context)
                return prepareDevelopPhotoBody(
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
            "operation=prepare_develop_photo category=internal_error "
                .. "code=unexpected_exception"
        )
        return "failed", PreparationService.failure(
            ErrorClassifier.codes.internalError,
            "unexpected_plugin_error"
        )
    end
    return outcome, value
end

return PreparationService
