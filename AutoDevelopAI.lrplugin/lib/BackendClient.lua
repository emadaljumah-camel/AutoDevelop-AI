local ApiClient = ModuleLoader.load("lib/ApiClient.lua")
local ErrorClassifier = ModuleLoader.load("lib/ErrorClassifier.lua")

local BackendClient = {}

function BackendClient.getHealth(baseUrl, timeoutSeconds)
    local result = ApiClient.health({
        baseUrl = baseUrl,
        timeoutSeconds = timeoutSeconds,
    })
    if not result.ok then
        return result
    end

    local decoded = ApiClient.decodeBody(result)
    if type(decoded) ~= "table"
        or decoded.status ~= "ok"
        or decoded.service ~= "AutoDevelop AI"
        or type(decoded.version) ~= "string"
        or decoded.version == "" then
        return {
            ok = false,
            status = result.status,
            category = ErrorClassifier.codes.invalidResponse,
            code = "invalid_health_response",
            retryable = false,
        }
    end
    return {
        ok = true,
        status = result.status,
        service = decoded.service,
        version = decoded.version,
    }
end

return BackendClient
