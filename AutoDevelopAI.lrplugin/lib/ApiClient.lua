local LrHttp = import("LrHttp")
local LrTasks = import("LrTasks")

local Config = ModuleLoader.load("lib/Config.lua")
local Json = ModuleLoader.load("lib/Json.lua")

local ApiClient = {}

local jsonHeaders = {
    {
        field = "Content-Type",
        value = "application/json",
    },
    {
        field = "Accept",
        value = "application/json",
    },
}

local function postJson(path, request)
    local encoded, encodeError = Json.encode(request)
    if not encoded then
        return {
            status = nil,
            headers = nil,
            body = nil,
            transportError = "Could not encode request JSON: "
                .. tostring(encodeError),
        }
    end

    local url = Config.getBackendBaseUrl() .. path
    local ok, responseBody, responseHeaders = LrTasks.pcall(function()
        return LrHttp.post(
            url,
            encoded,
            jsonHeaders,
            "POST",
            Config.getRequestTimeoutSeconds()
        )
    end)

    if not ok then
        return {
            status = nil,
            headers = nil,
            body = nil,
            transportError = tostring(responseBody),
        }
    end

    local status = nil
    if type(responseHeaders) == "table" then
        status = tonumber(responseHeaders.status)
    end
    if not status then
        return {
            status = nil,
            headers = responseHeaders,
            body = responseBody,
            transportError = "Backend did not return an HTTP status.",
        }
    end

    return {
        status = status,
        headers = responseHeaders,
        body = responseBody,
        transportError = nil,
    }
end

function ApiClient.analyze(request)
    return postJson(Config.apiPaths.analyze, request)
end

function ApiClient.develop(request)
    return postJson(Config.apiPaths.develop, request)
end

function ApiClient.decodeBody(response)
    return Json.decode(response and response.body)
end

return ApiClient
