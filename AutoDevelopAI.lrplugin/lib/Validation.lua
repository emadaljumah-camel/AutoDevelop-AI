local Utils = require("lib.Utils")

local Validation = {}

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
    if not Utils.trim(response.model) then
        return false, "Response model name was missing."
    end
    return true
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
