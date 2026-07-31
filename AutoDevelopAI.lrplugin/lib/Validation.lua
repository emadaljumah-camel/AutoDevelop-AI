local Json = ModuleLoader.load("lib/Json.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")
local StyleProfiles = ModuleLoader.load("lib/StyleProfiles.lua")

local Validation = {}

local developResponseFields = {
    schema_version = true,
    request_id = true,
    filename = true,
    status = true,
    analysis = true,
    edit_plan = true,
    crop = true,
    leveling = true,
    denoise = true,
    warnings = true,
    model = true,
    resolved_model = true,
    processing_duration_ms = true,
    develop_settings = true,
    learning = true,
    requested_style_id = true,
    effective_style_id = true,
    style_selection_mode = true,
    style_selection_reason = true,
    editing_intensity = true,
    scene_confidence = true,
    upright = true,
    enable_hdr = true,
    hdr_decision = true,
}

local function hasOnlyFields(value, allowed)
    for key in pairs(value) do
        if type(key) ~= "string" or not allowed[key] then
            return false
        end
    end
    return true
end

local function validUnitNumber(value)
    return Utils.isFiniteNumber(value) and value >= 0 and value <= 1
end

local function validNonNegativeInteger(value)
    return Utils.isFiniteNumber(value)
        and value >= 0
        and value == math.floor(value)
end

local function validPositiveInteger(value)
    return validNonNegativeInteger(value) and value >= 1
end

local function isAbsent(value)
    return value == nil or value == Json.null
end

function Validation.validateModelIdentifier(value)
    if type(value) ~= "string"
        or #value < 1
        or #value > 128
        or Utils.trim(value) ~= value then
        return nil
    end
    -- Single-letter prefixes followed by `:` are reserved because they are
    -- indistinguishable from Windows drive-relative paths.
    if value:match("^[A-Za-z]:") then
        return nil
    end
    if not value:match("^[A-Za-z0-9_%.%-%/%:%+]+$") then
        return nil
    end
    if value:find("://", 1, true)
        or value:find("..", 1, true)
        or value:find("//", 1, true)
        or value:find("::", 1, true)
        or value:sub(1, 1) == "/"
        or value:sub(-1) == "/" then
        return nil
    end
    return value
end

local function validateCrop(crop)
    if isAbsent(crop) then
        return true
    end
    if type(crop) ~= "table"
        or not hasOnlyFields(crop, {
            recommended = true,
            left = true,
            right = true,
            top = true,
            bottom = true,
            confidence = true,
            reason = true,
        })
        or type(crop.recommended) ~= "boolean" then
        return false
    end
    if not isAbsent(crop.confidence)
        and not validUnitNumber(crop.confidence) then
        return false
    end
    if not crop.recommended then
        return isAbsent(crop.left)
            and isAbsent(crop.right)
            and isAbsent(crop.top)
            and isAbsent(crop.bottom)
    end
    if not validUnitNumber(crop.left)
        or not validUnitNumber(crop.right)
        or not validUnitNumber(crop.top)
        or not validUnitNumber(crop.bottom) then
        return false
    end
    return crop.left < crop.right and crop.top < crop.bottom
end

local function validateLeveling(leveling)
    if type(leveling) ~= "table"
        or not hasOnlyFields(leveling, {
            recommended = true,
            angle = true,
            mode = true,
        })
        or type(leveling.recommended) ~= "boolean"
        or not Utils.isFiniteNumber(leveling.angle) then
        return false
    end
    local activeModes = {
        horizon = true,
        vertical = true,
        both = true,
    }
    if leveling.recommended then
        return activeModes[leveling.mode] == true
    end
    return leveling.angle == 0 and leveling.mode == "none"
end

local function validateDenoise(denoise)
    if isAbsent(denoise) then
        return true
    end
    if type(denoise) ~= "table"
        or type(denoise.recommended) ~= "boolean" then
        return false
    end
    if not isAbsent(denoise.amount)
        and not Utils.isFiniteNumber(denoise.amount) then
        return false
    end
    return isAbsent(denoise.confidence)
        or validUnitNumber(denoise.confidence)
end

local function validateHdr(enableHdr)
    if type(enableHdr) ~= "table" then
        return false
    end
    return hasOnlyFields(enableHdr, {
        recommended = true,
        enabled = true,
        confidence = true,
        reason = true,
    })
        and type(enableHdr.recommended) == "boolean"
        and type(enableHdr.enabled) == "boolean"
        and validUnitNumber(enableHdr.confidence)
        and (
            isAbsent(enableHdr.reason)
            or type(enableHdr.reason) == "string"
        )
        and (
            enableHdr.recommended
            or enableHdr.enabled == false
        )
end

local function validateUpright(upright)
    if type(upright) ~= "table" then
        return false
    end
    local modes = {
        off = true,
        auto = true,
        full = true,
        level = true,
        vertical = true,
    }
    return hasOnlyFields(upright, {
        recommended = true,
        mode = true,
        confidence = true,
        reason = true,
    })
        and type(upright.recommended) == "boolean"
        and modes[upright.mode] == true
        and validUnitNumber(upright.confidence)
        and (
            isAbsent(upright.reason)
            or type(upright.reason) == "string"
        )
        and (
            upright.recommended
            or upright.mode == "off"
        )
end

local function validateWarnings(warnings)
    if warnings == nil then
        return true
    end
    if type(warnings) ~= "table" then
        return false
    end
    local itemCount = 0
    local highestIndex = 0
    for index, warning in pairs(warnings) do
        if type(index) ~= "number"
            or index < 1
            or index ~= math.floor(index) then
            return false
        end
        itemCount = itemCount + 1
        highestIndex = math.max(highestIndex, index)
        if type(warning) ~= "table"
            or not Utils.trim(warning.code)
            or not Utils.trim(warning.message)
            or (
                warning.severity ~= "info"
                and warning.severity ~= "warning"
                and warning.severity ~= "error"
            ) then
            return false
        end
    end
    return itemCount == highestIndex
end

local function validateLearning(learning)
    if isAbsent(learning) then
        return true
    end
    if type(learning) ~= "table" then
        return false
    end
    local allowed = {
        enabled = true,
        personalization_applied = true,
        usable_sample_count = true,
        retrieved_sample_count = true,
        minimum_sample_count = true,
        average_similarity = true,
        feature_type = true,
        hdr_personalization_applied = true,
        hdr_learning_enable_rate = true,
        hdr_learning_sample_count = true,
        reason = true,
    }
    local reasons = {
        disabled = true,
        database_unavailable = true,
        embedding_unavailable = true,
        insufficient_samples = true,
        no_similar_samples = true,
        retrieval_unavailable = true,
    }
    if not hasOnlyFields(learning, allowed)
        or type(learning.enabled) ~= "boolean"
        or type(learning.personalization_applied) ~= "boolean"
        or not validNonNegativeInteger(learning.usable_sample_count)
        or not validNonNegativeInteger(learning.retrieved_sample_count)
        or not validPositiveInteger(learning.minimum_sample_count)
        or type(learning.hdr_personalization_applied) ~= "boolean"
        or not validNonNegativeInteger(
            learning.hdr_learning_sample_count
        )
        or (
            not isAbsent(learning.hdr_learning_enable_rate)
            and not validUnitNumber(
                learning.hdr_learning_enable_rate
            )
        )
        or (
            not isAbsent(learning.average_similarity)
            and not validUnitNumber(learning.average_similarity)
        ) then
        return false
    end
    if not isAbsent(learning.feature_type)
        and (
            type(learning.feature_type) ~= "string"
            or not Utils.trim(learning.feature_type)
            or #learning.feature_type > 100
        ) then
        return false
    end
    return isAbsent(learning.reason)
        or (
            type(learning.reason) == "string"
            and reasons[learning.reason] == true
        )
end

local function validateHdrDecision(value)
    if isAbsent(value) then
        return true
    end
    if type(value) ~= "table" then
        return false
    end
    local allowed = {
        scene_hdr_candidate = true,
        scene_hdr_confidence = true,
        base_scene_evidence_score = true,
        learning_bonus = true,
        user_preference_bonus = true,
        combined_evidence_score = true,
        decision_basis = true,
        decision_confidence = true,
        scene_hdr_inconsistent = true,
        contraindications = true,
        visual_evidence_score = true,
        hdr_evidence_score = true,
        hdr_learning_applied = true,
        hdr_learning_enable_rate = true,
        hdr_learning_sample_count = true,
        raw_hdr_recommended = true,
        raw_hdr_confidence = true,
        validated_hdr_enabled = true,
        validated_hdr_confidence = true,
        hdr_rejected = true,
        hdr_rejection_reason = true,
    }
    local reasons = {
        profile_disallowed = true,
        insufficient_dynamic_range = true,
        insufficient_evidence = true,
        confidence_below_threshold = true,
        high_noise_risk = true,
        severe_underexposure = true,
        portrait_without_hdr_need = true,
        documentary_authenticity = true,
        model_not_recommended = true,
        caller_unsupported = true,
        sdr_only_workflow = true,
        unsupported_source_format = true,
    }
    local decisionBases = {
        disabled = true,
        model = true,
        objective_evidence = true,
        learned_preference = true,
    }
    if not hasOnlyFields(value, allowed)
        or type(value.scene_hdr_candidate) ~= "boolean"
        or not validUnitNumber(value.scene_hdr_confidence)
        or not validUnitNumber(value.base_scene_evidence_score)
        or not validUnitNumber(value.learning_bonus)
        or not validUnitNumber(value.user_preference_bonus)
        or not validUnitNumber(value.combined_evidence_score)
        or type(value.decision_basis) ~= "string"
        or decisionBases[value.decision_basis] ~= true
        or (
            not isAbsent(value.decision_confidence)
            and not validUnitNumber(value.decision_confidence)
        )
        or type(value.scene_hdr_inconsistent) ~= "boolean"
        or type(value.contraindications) ~= "table"
        or not validUnitNumber(value.visual_evidence_score)
        or not validUnitNumber(value.hdr_evidence_score)
        or type(value.hdr_learning_applied) ~= "boolean"
        or not validNonNegativeInteger(value.hdr_learning_sample_count)
        or (
            not isAbsent(value.hdr_learning_enable_rate)
            and not validUnitNumber(value.hdr_learning_enable_rate)
        )
        or (
            not isAbsent(value.raw_hdr_recommended)
            and type(value.raw_hdr_recommended) ~= "boolean"
        )
        or (
            not isAbsent(value.raw_hdr_confidence)
            and not validUnitNumber(value.raw_hdr_confidence)
        )
        or type(value.validated_hdr_enabled) ~= "boolean"
        or (
            not isAbsent(value.validated_hdr_confidence)
            and not validUnitNumber(value.validated_hdr_confidence)
        )
        or type(value.hdr_rejected) ~= "boolean" then
        return false
    end
    for _, reason in ipairs(value.contraindications) do
        if type(reason) ~= "string" or reasons[reason] ~= true then
            return false
        end
    end
    return isAbsent(value.hdr_rejection_reason)
        or reasons[value.hdr_rejection_reason] == true
end

local function validateStyleDiagnostics(response, request)
    if response.requested_style_id ~= request.options.style_profile
        or not StyleProfiles.isValidId(response.requested_style_id)
        or not StyleProfiles.isConcreteId(response.effective_style_id)
        or type(response.style_selection_reason) ~= "string"
        or not Utils.trim(response.style_selection_reason)
        or #response.style_selection_reason > 200 then
        return false
    end
    if response.style_selection_mode == "manual" then
        if response.requested_style_id ~= response.effective_style_id then
            return false
        end
    elseif response.style_selection_mode == "auto" then
        if response.requested_style_id ~= "auto" then
            return false
        end
    else
        return false
    end
    local intensities = {
        conservative = true,
        moderate = true,
        strong = true,
        very_strong = true,
    }
    if not intensities[response.editing_intensity]
        or (
            not isAbsent(response.scene_confidence)
            and not validUnitNumber(response.scene_confidence)
        )
        or type(response.edit_plan) ~= "table"
        or response.edit_plan.style_profile ~= response.effective_style_id then
        return false
    end
    return true
end

function Validation.validateAnalyzeResponse(response, request)
    if type(response) ~= "table" then
        return false, "Response was not a JSON object."
    end
    if response.status ~= "success" then
        return false, "Response status was not success."
    end
    if response.schema_version ~= "1.0" then
        return false, "Response schema_version was not 1.0."
    end
    if response.request_id ~= request.request_id then
        return false, "Response request_id did not match the request."
    end
    if not Utils.trim(response.filename)
        or response.filename ~= request.filename then
        return false, "Response filename did not match the request."
    end
    if type(response.analysis) ~= "table" then
        return false, "Response analysis was missing."
    end
    if type(response.edit_plan) ~= "table" then
        return false, "Response edit_plan was missing."
    end
    if not validateCrop(response.crop) then
        return false, "Response crop recommendation was invalid."
    end
    if not validateLeveling(response.leveling) then
        return false, "Response leveling recommendation was invalid."
    end
    if not validateDenoise(response.denoise) then
        return false, "Response denoise recommendation was invalid."
    end
    if not validateWarnings(response.warnings) then
        return false, "Response warnings were invalid."
    end
    if not validateStyleDiagnostics(response, request) then
        return false, "Response style diagnostics were invalid."
    end
    local modelIdentifier =
        Validation.validateModelIdentifier(response.model)
    if not modelIdentifier then
        return false, "Response model identifier was invalid."
    end
    if modelIdentifier ~= request.model then
        return false, "Response model did not match the request."
    end
    local resolvedModel =
        Validation.validateModelIdentifier(response.resolved_model)
    if not resolvedModel then
        return false, "Response resolved_model was invalid."
    end
    return true, nil, modelIdentifier, resolvedModel
end

function Validation.validateDevelopResponse(response, request)
    if type(response) ~= "table" then
        return false, "Response was not a JSON object."
    end
    if not hasOnlyFields(response, developResponseFields) then
        return false, "Response contained an unknown top-level field."
    end
    if response.status ~= "success" then
        return false, "Response status was not success."
    end
    if response.schema_version ~= "1.0" then
        return false, "Response schema_version was not 1.0."
    end
    if response.request_id ~= request.request_id then
        return false, "Response request_id did not match the request."
    end
    if not Utils.trim(response.filename)
        or response.filename ~= request.filename then
        return false, "Response filename did not match the request."
    end
    local modelIdentifier =
        Validation.validateModelIdentifier(response.model)
    if not modelIdentifier then
        return false, "Response model identifier was invalid."
    end
    if modelIdentifier ~= request.model then
        return false, "Response model did not match the request."
    end
    local resolvedModel =
        Validation.validateModelIdentifier(response.resolved_model)
    if not resolvedModel then
        return false, "Response resolved_model was invalid."
    end
    if type(response.develop_settings) ~= "table" then
        return false, "Response develop_settings was missing."
    end
    if not validateCrop(response.crop) then
        return false, "Response crop recommendation was invalid."
    end
    if not validateLeveling(response.leveling) then
        return false, "Response leveling recommendation was invalid."
    end
    if not validateDenoise(response.denoise) then
        return false, "Response denoise recommendation was invalid."
    end
    if not validateUpright(response.upright) then
        return false, "Response Upright recommendation was invalid."
    end
    if not validateHdr(response.enable_hdr) then
        return false, "Response HDR recommendation was invalid."
    end
    if not validateHdrDecision(response.hdr_decision) then
        return false, "Response HDR decision diagnostics were invalid."
    end
    if not validateWarnings(response.warnings) then
        return false, "Response warnings were invalid."
    end
    if not validateLearning(response.learning) then
        return false, "Response learning diagnostics were invalid."
    end
    if not validateStyleDiagnostics(response, request) then
        return false, "Response style diagnostics were invalid."
    end
    return true, nil, modelIdentifier, resolvedModel
end

function Validation.parseErrorResponse(decoded, httpStatus)
    local fallback = {
        code = "http_error",
        message = "The backend returned HTTP " .. tostring(httpStatus or 0) .. ".",
        retryable = false,
    }
    if type(decoded) ~= "table" or type(decoded.error) ~= "table" then
        return fallback
    end

    local errorInfo = decoded.error
    return {
        code = Utils.trim(errorInfo.code) or fallback.code,
        message = Utils.safeMessage(errorInfo.message, fallback.message),
        retryable = errorInfo.retryable == true,
    }
end

return Validation
