local ExifMapper = ModuleLoader.load("lib/ExifMapper.lua")
local LearningClient = ModuleLoader.load("lib/LearningClient.lua")
local LearningPhotoIdentity =
    ModuleLoader.load("lib/LearningPhotoIdentity.lua")
local LearningSessionStore =
    ModuleLoader.load("lib/LearningSessionStore.lua")
local Logger = ModuleLoader.load("lib/Logger.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")
local DevelopModeMapper =
    ModuleLoader.load("lib/DevelopModeMapper.lua")

local LearningBaselineService = {}

local function logFilename(operation)
    return Utils.safeMessage(
        operation.displayFilename or operation.filename,
        "unknown"
    )
end

local function logFailure(operation, response)
    response = type(response) == "table" and response or {}
    Logger.warn(
        "learning_baseline_save_failed filename="
            .. logFilename(operation)
            .. " status="
            .. tostring(response.status or "unavailable")
            .. " category="
            .. Utils.safeErrorCode(
                response.category,
                "learning_baseline_failed"
            )
            .. " code="
            .. Utils.safeErrorCode(
                response.code,
                "learning_baseline_failed"
            )
    )
end

local function operationModes(settings)
    settings = type(settings) == "table" and settings or {}
    local upright = DevelopModeMapper.decodeUpright(
        settings.PerspectiveUpright
    )
    local hdr = DevelopModeMapper.decodeHdr(settings.HDREditMode)
    local modes = {}
    if upright.supported then
        modes.upright = upright.mode
        modes.upright_raw_value = upright.rawValue
    end
    if hdr.supported then
        modes.hdr_enabled = hdr.enabled
        modes.hdr_raw_value = hdr.rawValue
    end
    return modes
end

local function fillMissingModes(target, fallback)
    for key, value in pairs(fallback or {}) do
        if target[key] == nil then
            target[key] = value
        end
    end
    return target
end

local function recommendationModes(operation)
    local modes = operationModes(operation.finalSettings)
    local upright = operation.upright or {}
    local hdr = operation.hdr or {}
    if type(upright.mode) == "string" then
        local rawValue = DevelopModeMapper.encodeUpright(upright.mode)
        if rawValue ~= nil then
            modes.upright = upright.mode
            modes.upright_raw_value = rawValue
        end
    end
    if type(hdr.enabled) == "boolean" then
        modes.hdr_enabled = hdr.enabled
        modes.hdr_raw_value =
            DevelopModeMapper.encodeHdr(hdr.enabled)
    end
    return modes
end

local function baselineHdrDecision(value)
    if type(value) ~= "table" then
        return nil
    end
    local normalized = Utils.deepCopy(value)
    if type(normalized.contraindications) == "table"
        and next(normalized.contraindications) == nil then
        normalized.contraindications = nil
    end
    return normalized
end

local function requestFor(operation)
    local sessionId = Utils.newUuid()
    local photoKey = LearningPhotoIdentity.forPhoto(operation.photo)
    local captured = ExifMapper.mapLearningDevelopState(operation.photo)
    if not captured then
        return nil
    end
    return {
        schema_version = 1,
        session_id = sessionId,
        request_id = operation.requestId,
        photo_key = photoKey,
        filename = operation.displayFilename or operation.filename,
        local_identifier =
            LearningPhotoIdentity.localIdentifier(operation.photo),
        profile = operation.profileId,
        model = operation.model,
        resolved_model = operation.resolvedModel,
        original_settings = ExifMapper.filterLearningSettings(
            operation.originalSettings
        ),
        recommendation = ExifMapper.filterLearningSettings(
            operation.mappedSettings
        ),
        applied_baseline = ExifMapper.filterLearningSettings(
            captured.settings
        ),
        original_modes = fillMissingModes(
            operationModes(operation.originalSettings),
            captured.modes
        ),
        recommendation_modes = recommendationModes(operation),
        applied_modes = captured.modes,
        exif_context = Utils.deepCopy(operation.exifContext or {}),
        validation_summary =
            Utils.deepCopy(operation.validationSummary or {}),
        hdr_decision = baselineHdrDecision(operation.hdrDecision),
    }
end

function LearningBaselineService.recordOne(operation, preferences)
    local result = { saved = 0, failed = 0 }
    if type(operation) ~= "table"
        or operation.applicationStatus ~= "applied" then
        return result
    end

    local request = requestFor(operation)
    if not request then
        result.failed = result.failed + 1
        logFailure(operation, {
            category = "validation_error",
            code = "develop_settings_unavailable",
        })
    else
        local response = LearningClient.storeBaseline(request, {
            baseUrl = preferences.backendBaseUrl,
            timeoutSeconds = preferences.requestTimeoutSeconds,
        })
        if response.ok then
            LearningSessionStore.put(request.photo_key, {
                sessionId = request.session_id,
                baselineTimestamp = Utils.nowIso(),
                profileId = operation.profileId,
                modelId = operation.model,
                filename = operation.displayFilename or operation.filename,
            })
            result.saved = result.saved + 1
            Logger.info(
                "learning_baseline_saved filename="
                    .. logFilename(operation)
            )
        else
            result.failed = result.failed + 1
            logFailure(operation, response)
        end
    end
    return result
end

function LearningBaselineService.recordApplied(operations, preferences)
    local result = { saved = 0, failed = 0 }
    for _, operation in ipairs(operations or {}) do
        local current =
            LearningBaselineService.recordOne(operation, preferences)
        result.saved = result.saved + current.saved
        result.failed = result.failed + current.failed
    end
    return result
end

return LearningBaselineService
