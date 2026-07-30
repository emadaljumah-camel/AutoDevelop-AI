local ApiClient = ModuleLoader.load("lib/ApiClient.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")

local LearningClient = {}

local canonicalSettings = {
    Exposure2012 = true,
    Contrast2012 = true,
    Highlights2012 = true,
    Shadows2012 = true,
    Whites2012 = true,
    Blacks2012 = true,
    Texture = true,
    Clarity2012 = true,
    Dehaze = true,
    Vibrance = true,
    Saturation = true,
    Temperature = true,
    Tint = true,
    CropLeft = true,
    CropRight = true,
    CropTop = true,
    CropBottom = true,
    CropAngle = true,
}

local function uuid(value)
    return Utils.isUuid(value)
end

local function comparisonMap(value, expectedSignificant)
    if type(value) ~= "table" then
        return false
    end
    for key, detail in pairs(value) do
        if not canonicalSettings[key]
            or type(detail) ~= "table"
            or not Utils.isFiniteNumber(detail.baseline)
            or not Utils.isFiniteNumber(detail.current)
            or not Utils.isFiniteNumber(detail.delta)
            or not Utils.isFiniteNumber(detail.threshold)
            or detail.threshold < 0
            or detail.significant ~= expectedSignificant then
            return false
        end
        for field in pairs(detail) do
            if field ~= "baseline"
                and field ~= "current"
                and field ~= "delta"
                and field ~= "threshold"
                and field ~= "significant" then
                return false
            end
        end
    end
    return true
end

function LearningClient.storeBaseline(request, options)
    local result = ApiClient.learningBaseline(request, options)
    if not result.ok then
        return result
    end
    local decoded = ApiClient.decodeBody(result)
    if type(decoded) ~= "table"
        or decoded.schema_version ~= 1
        or decoded.session_id ~= request.session_id
        or decoded.state ~= "pending_feedback"
        or type(decoded.stored) ~= "boolean" then
        return {
            ok = false,
            category = "invalid_response",
            code = "invalid_learning_baseline_response",
        }
    end
    return {
        ok = true,
        sessionId = decoded.session_id,
        stored = decoded.stored,
    }
end

function LearningClient.captureFeedback(request, options)
    local result = ApiClient.learningFeedback(request, options)
    if not result.ok then
        return result
    end
    local decoded = ApiClient.decodeBody(result)
    if type(decoded) ~= "table"
        or decoded.schema_version ~= 1
        or not uuid(decoded.feedback_id)
        or decoded.session_id ~= request.session_id
        or decoded.state ~= "feedback_captured"
        or type(decoded.usable) ~= "boolean"
        or type(decoded.accepted_without_change) ~= "boolean"
        or type(decoded.significant_changes) ~= "table"
        or type(decoded.ignored_changes) ~= "table"
        or type(decoded.crop_changes) ~= "table"
        or type(decoded.leveling_changes) ~= "table" then
        return {
            ok = false,
            category = "invalid_response",
            code = "invalid_learning_feedback_response",
        }
    end
    return {
        ok = true,
        feedbackId = decoded.feedback_id,
        acceptedWithoutChange = decoded.accepted_without_change,
        significantChanges = Utils.deepCopy(decoded.significant_changes),
        cropChanges = Utils.deepCopy(decoded.crop_changes),
        levelingChanges = Utils.deepCopy(decoded.leveling_changes),
    }
end

function LearningClient.previewFeedback(request, options)
    local result = ApiClient.learningFeedbackPreview(request, options)
    if not result.ok then
        return result
    end
    local decoded = ApiClient.decodeBody(result)
    if type(decoded) ~= "table"
        or decoded.schema_version ~= 1
        or decoded.session_id ~= request.session_id
        or type(decoded.has_significant_changes) ~= "boolean"
        or type(decoded.accepted_without_change) ~= "boolean"
        or decoded.has_significant_changes
            == decoded.accepted_without_change
        or not comparisonMap(decoded.significant_changes, true)
        or not comparisonMap(decoded.ignored_changes, false)
        or not comparisonMap(decoded.crop_changes, true)
        or not comparisonMap(decoded.leveling_changes, true) then
        return {
            ok = false,
            category = "invalid_response",
            code = "invalid_learning_feedback_preview_response",
        }
    end
    return {
        ok = true,
        sessionId = decoded.session_id,
        hasSignificantChanges = decoded.has_significant_changes,
        acceptedWithoutChange = decoded.accepted_without_change,
        significantChanges = Utils.deepCopy(decoded.significant_changes),
        ignoredChanges = Utils.deepCopy(decoded.ignored_changes),
        cropChanges = Utils.deepCopy(decoded.crop_changes),
        levelingChanges = Utils.deepCopy(decoded.leveling_changes),
    }
end

function LearningClient.status(options)
    local result = ApiClient.learningStatus(options)
    if not result.ok then
        return result
    end
    local decoded = ApiClient.decodeBody(result)
    if type(decoded) ~= "table"
        or decoded.schema_version ~= 1
        or type(decoded.enabled) ~= "boolean"
        or type(decoded.database_available) ~= "boolean"
        or type(decoded.embedding_available) ~= "boolean"
        or type(decoded.pending_sessions) ~= "number"
        or type(decoded.feedback_samples) ~= "number"
        or type(decoded.usable_samples) ~= "number"
        or type(decoded.minimum_samples) ~= "number" then
        return {
            ok = false,
            category = "invalid_response",
            code = "invalid_learning_status_response",
        }
    end
    decoded.ok = true
    return decoded
end

return LearningClient
