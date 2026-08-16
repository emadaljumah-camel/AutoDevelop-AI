local LrFunctionContext = import("LrFunctionContext")
local LrTasks = import("LrTasks")

local ApiClient = ModuleLoader.load("lib/ApiClient.lua")
local ApplyService = ModuleLoader.load("lib/ApplyService.lua")
local BatchPolicy = ModuleLoader.load("lib/BatchPolicy.lua")
local CropMapper = ModuleLoader.load("lib/CropMapper.lua")
local DevelopSettingsMapper =
    ModuleLoader.load("lib/DevelopSettingsMapper.lua")
local DevelopModeMapper =
    ModuleLoader.load("lib/DevelopModeMapper.lua")
local DenoisePresetService =
    ModuleLoader.load("lib/DenoisePresetService.lua")
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
        local requestOptions = Utils.deepCopy(connectionOptions or {})
        requestOptions.endpointAttempt = retriesUsed + 1
        local result = requestFunction(request, requestOptions)
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
                .. " endpoint_attempt="
                .. tostring(retriesUsed + 1)
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
    photoIdentity,
    lifecycle
)
    markLifecycle(lifecycle, "develop_preparation_started")
    photoIdentity = photoIdentity
        or Utils.capturePhotoIdentity(photo)
    if not ExifMapper.isSupportedPhoto(photo) then
        return "skipped", "Videos are not supported."
    end
    if progressScope:isCanceled() then
        return "cancelled", PreparationService.failure(
            ErrorClassifier.codes.cancelled,
            "user_cancelled"
        )
    end

    local request = lifecycle.downloadedRequest
    local decoded = lifecycle.downloadedResponse
    local validatedModel
    if request == nil or decoded == nil then
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
    local requestError
    request, requestError = RequestBuilder.buildDevelop(
        photo,
        preview.base64,
        {
            styleProfileId = preferences.styleProfileId,
            modelProfileId = preferences.modelProfileId,
            includeCrop = true,
            includeDenoise = true,
            preserveCurrentAdjustments = true,
            learningEnabled = preferences.learningEnabled,
            hdrPreference = preferences.hdrPreference,
            photoIdentity = photoIdentity,
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
    local decodeError
    decoded, decodeError = ApiClient.decodeBody(response)
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
    local valid, validationError
    valid, validationError, validatedModel =
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
    else
        markLifecycle(lifecycle, "response_validation_started")
        local valid, validationError
        valid, validationError, validatedModel =
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
    end

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

    markLifecycle(lifecycle, "geometry_mapping_started")
    local cropRecommended = type(decoded.crop) == "table"
        and decoded.crop.recommended == true
    local levelingRecommended = type(decoded.leveling) == "table"
        and decoded.leveling.recommended == true
    local mappedGeometry = CropMapper.map(
        decoded.crop,
        decoded.leveling,
        {
            applyCompositionCrop = preferences.applyCompositionCrop,
            applyLeveling = preferences.applyLeveling,
        },
        currentSettings
    )
    markLifecycle(lifecycle, "geometry_mapping_completed")
    local cropDisabled = preferences.applyCompositionCrop == false
        and cropRecommended
    local levelingDisabled = preferences.applyLeveling == false
        and levelingRecommended
    local denoiseRecommended = type(decoded.denoise) == "table"
        and decoded.denoise.recommended == true
    local denoiseCapability = {
        ready = false,
        code = "denoise_not_recommended",
    }
    if denoiseRecommended then
        denoiseCapability = DenoisePresetService.prepare(
            photo,
            currentSettings,
            decoded.denoise.amount
        )
    end
    local denoiseIncluded = denoiseRecommended
        and denoiseCapability.ready == true
    if denoiseRecommended then
        Logger.info(
            "denoise_preparation filename="
                .. Utils.safeMessage(
                    photoIdentity.displayFilename,
                    "Photo"
                )
                .. " amount="
                .. tostring(decoded.denoise.amount or "<none>")
                .. " source_format="
                .. tostring(request.exif.file_format or "<none>")
                .. " included="
                .. tostring(denoiseIncluded)
                .. " code="
                .. Utils.safeErrorCode(
                    denoiseCapability.code,
                    denoiseIncluded
                        and "denoise_ready"
                        or "denoise_unavailable"
                )
                .. " preset="
                .. Utils.safeMessage(
                    denoiseCapability.presetName,
                    "<none>"
                )
        )
    end
    local operationWarnings = Utils.deepCopy(decoded.warnings or {})
    if denoiseRecommended and not denoiseIncluded then
        operationWarnings[#operationWarnings + 1] = {
            code = denoiseCapability.code or "denoise_unavailable",
            message = denoiseCapability.reason
                or "Lightroom AI Denoise could not be prepared.",
            field = "denoise",
            severity = "warning",
        }
    end
    mappedSettings = mergeSettings(mappedSettings, mappedGeometry)
    local uprightRecommended = type(decoded.upright) == "table"
        and decoded.upright.recommended == true
    local currentUpright = DevelopModeMapper.decodeUpright(
        currentSettings.PerspectiveUpright
    )
    local uprightMode = uprightRecommended
        and currentUpright.supported
        and decoded.upright.mode
        or nil
    local hdrRecommended = type(decoded.enable_hdr) == "table"
        and decoded.enable_hdr.recommended == true
    local currentHdr = DevelopModeMapper.decodeHdr(
        currentSettings.HDREditMode
    )
    local enableHdr = hdrRecommended
        and decoded.enable_hdr.enabled == true
        and currentHdr.supported
    if progressScope:isCanceled() then
        return "cancelled", PreparationService.failure(
            ErrorClassifier.codes.cancelled,
            "user_cancelled"
        )
    end
    local finalSettings = ApplyService.prepareFinalSettings(
        mappedSettings,
        currentSettings,
        uprightMode,
        enableHdr
    )
    local settingCount = countSettings(finalSettings)
    if settingCount == 0 and not denoiseIncluded then
        return "skipped", {
            cropDisabled = cropDisabled,
            cropRecommended = cropRecommended,
            levelingDisabled = levelingDisabled,
            levelingRecommended = levelingRecommended,
            levelingAngle = levelingRecommended
                and decoded.leveling.angle or nil,
            denoiseRecommended = denoiseRecommended,
            denoiseIncluded = false,
            uprightRecommended = uprightRecommended,
            hdrRecommended = hdrRecommended,
        }
    end

    markLifecycle(lifecycle, "pending_operation_build_started")
    local originalSettings = ApplyService.captureOriginal(
        currentSettings,
        finalSettings
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
        photoId = photoIdentity.photoId,
        displayFilename = photoIdentity.displayFilename,
        filename = request.filename,
        requestId = request.request_id,
        profileId = decoded.effective_style_id,
        requestedStyleId = decoded.requested_style_id,
        effectiveStyleId = decoded.effective_style_id,
        styleSelectionMode = decoded.style_selection_mode,
        styleSelectionReason = decoded.style_selection_reason,
        editingIntensity = decoded.editing_intensity,
        sceneConfidence = decoded.scene_confidence,
        originalSettings = originalSettings,
        mappedSettings = mappedSettings,
        finalSettings = finalSettings,
        cropRecommended = cropRecommended,
        compositionCropIncluded = mappedGeometry ~= nil
            and cropRecommended
            and preferences.applyCompositionCrop == true,
        levelingRecommended = levelingRecommended,
        levelingIncluded = mappedGeometry ~= nil
            and levelingRecommended
            and preferences.applyLeveling == true,
        levelingMode = decoded.leveling.mode,
        levelingAngle = decoded.leveling.angle,
        denoiseRecommended = denoiseRecommended,
        denoise = {
            recommended = denoiseRecommended,
            included = denoiseIncluded,
            amount = type(decoded.denoise) == "table"
                and decoded.denoise.amount or nil,
            confidence = type(decoded.denoise) == "table"
                and decoded.denoise.confidence or nil,
            reason = type(decoded.denoise) == "table"
                and decoded.denoise.reason or nil,
            unavailableReason = denoiseCapability.reason,
            unavailableCode = denoiseCapability.code,
            presetName = denoiseCapability.presetName,
        },
        denoisePreset = denoiseCapability.preset,
        denoiseOriginalSettings = denoiseCapability.originalSettings,
        upright = {
            recommended = uprightRecommended,
            mode = decoded.upright.mode,
            confidence = decoded.upright.confidence,
            reason = decoded.upright.reason,
        },
        hdr = {
            recommended = hdrRecommended,
            enabled = enableHdr,
            confidence = decoded.enable_hdr.confidence,
            reason = decoded.enable_hdr.reason,
        },
        hdrDecision = decoded.hdr_decision,
        modeDiagnostics = {
            perspectiveUpright = currentSettings.PerspectiveUpright,
            hdrEditMode = currentSettings.HDREditMode,
            hdrMaxValue = currentSettings.HDRMaxValue,
        },
        warnings = operationWarnings,
        model = validatedModel,
        resolvedModel = decoded.resolved_model,
        processingDurationMs = decoded.processing_duration_ms,
        exifContext = {
            file_format = request.exif.file_format,
            camera = request.exif.camera,
            lens = request.exif.lens,
            iso = request.exif.iso,
            aperture = request.exif.aperture,
            shutter_speed = request.exif.shutter_speed,
            focal_length = request.exif.focal_length,
            orientation = request.exif.orientation,
            width = request.exif.width,
            height = request.exif.height,
            capture_time_category = "unknown",
        },
        validationSummary = {
            issue_count = #(decoded.warnings or {}),
            crop_rejected = decoded.crop == nil,
            leveling_rejected = decoded.leveling == nil,
            clamped_count = 0,
            removed_count = 0,
        },
        learning = decoded.learning,
    })
    operation.cropDisabled = cropDisabled
    operation.levelingDisabled = levelingDisabled
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
    tracker,
    photoIdentity
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
                    photoIdentity,
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

function PreparationService.prepareDevelopResult(
    photo,
    request,
    decoded,
    progressScope,
    preferences,
    photoIdentity
)
    local lifecycle = {
        stage = "downloaded_develop_entry",
        downloadedRequest = request,
        downloadedResponse = decoded,
    }
    local ok, result = LrTasks.pcall(function()
        return LrFunctionContext.callWithContext(
            "AutoDevelop AI Prepare Downloaded Result",
            function(context)
                local outcome, value = prepareDevelopPhotoBody(
                    photo,
                    nil,
                    progressScope,
                    context,
                    preferences,
                    nil,
                    photoIdentity,
                    lifecycle
                )
                return {
                    outcome = outcome,
                    value = value,
                }
            end
        )
    end)
    if not ok or type(result) ~= "table" then
        logStageFailure(
            lifecycle.stage,
            ErrorClassifier.codes.internalError
        )
        return "failed", stagedFailure(
            ErrorClassifier.codes.internalError,
            "unexpected_downloaded_result_error",
            lifecycle
        )
    end
    return result.outcome, result.value
end

return PreparationService
