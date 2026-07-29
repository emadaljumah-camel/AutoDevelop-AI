local Json = ModuleLoader.load("lib/Json.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")

local Validation = {}

local developResponseFields = {
    schema_version = true,
    request_id = true,
    filename = true,
    status = true,
    analysis = true,
    edit_plan = true,
    crop = true,
    denoise = true,
    warnings = true,
    model = true,
    resolved_model = true,
    processing_duration_ms = true,
    develop_settings = true,
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
    if type(crop) ~= "table" or type(crop.recommended) ~= "boolean" then
        return false
    end
    if not isAbsent(crop.confidence)
        and not validUnitNumber(crop.confidence) then
        return false
    end
    if not isAbsent(crop.angle)
        and not Utils.isFiniteNumber(crop.angle) then
        return false
    end
    if not crop.recommended then
        return true
    end
    if not validUnitNumber(crop.left)
        or not validUnitNumber(crop.right)
        or not validUnitNumber(crop.top)
        or not validUnitNumber(crop.bottom) then
        return false
    end
    return crop.left < crop.right and crop.top < crop.bottom
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
    if not validateDenoise(response.denoise) then
        return false, "Response denoise recommendation was invalid."
    end
    if not validateWarnings(response.warnings) then
        return false, "Response warnings were invalid."
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
