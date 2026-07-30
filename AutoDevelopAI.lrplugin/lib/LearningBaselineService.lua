local ExifMapper = ModuleLoader.load("lib/ExifMapper.lua")
local LearningClient = ModuleLoader.load("lib/LearningClient.lua")
local LearningPhotoIdentity =
    ModuleLoader.load("lib/LearningPhotoIdentity.lua")
local LearningSessionStore =
    ModuleLoader.load("lib/LearningSessionStore.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")

local LearningBaselineService = {}

local function requestFor(operation)
    local sessionId = Utils.newUuid()
    local photoKey = LearningPhotoIdentity.forPhoto(operation.photo)
    local applied = ExifMapper.mapDevelopSettings(operation.photo)
    if not applied then
        return nil
    end
    return {
        schema_version = 1,
        session_id = sessionId,
        request_id = operation.requestId,
        photo_key = photoKey,
        filename = operation.filename,
        local_identifier =
            LearningPhotoIdentity.localIdentifier(operation.photo),
        profile = operation.profileId,
        model = operation.model,
        resolved_model = operation.resolvedModel,
        original_settings = Utils.deepCopy(operation.originalSettings),
        recommendation = Utils.deepCopy(operation.mappedSettings),
        applied_baseline = applied,
        exif_context = Utils.deepCopy(operation.exifContext or {}),
        validation_summary =
            Utils.deepCopy(operation.validationSummary or {}),
    }
end

function LearningBaselineService.recordApplied(operations, preferences)
    local result = { saved = 0, failed = 0 }
    for _, operation in ipairs(operations or {}) do
        if operation.applicationStatus == "applied" then
            local request = requestFor(operation)
            if not request then
                result.failed = result.failed + 1
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
                        filename = operation.filename,
                    })
                    result.saved = result.saved + 1
                else
                    result.failed = result.failed + 1
                end
            end
        end
    end
    return result
end

return LearningBaselineService
