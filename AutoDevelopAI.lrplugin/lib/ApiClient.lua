local LrHttp = import("LrHttp")
local LrTasks = import("LrTasks")

local Config = ModuleLoader.load("lib/Config.lua")
local ErrorClassifier = ModuleLoader.load("lib/ErrorClassifier.lua")
local Json = ModuleLoader.load("lib/Json.lua")
local Preferences = ModuleLoader.load("lib/Preferences.lua")
local Validation = ModuleLoader.load("lib/Validation.lua")

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

local function failure(category, fields)
    fields = fields or {}
    fields.ok = false
    fields.category = category
    return fields
end

local function networkFailure(headers)
    return failure(ErrorClassifier.fromNetworkInfo(headers), {
        status = nil,
        headers = headers,
        code = type(headers) == "table"
            and type(headers.error) == "table"
            and headers.error.errorCode or nil,
        retryable = false,
    })
end

local function httpResult(responseBody, responseHeaders)
    if responseBody == nil then
        return networkFailure(responseHeaders)
    end
    local status = type(responseHeaders) == "table"
        and tonumber(responseHeaders.status) or nil
    if not status then
        return failure(ErrorClassifier.codes.invalidResponse, {
            status = nil,
            headers = responseHeaders,
            body = responseBody,
            code = "missing_http_status",
            retryable = false,
        })
    end
    if status >= 200 and status < 300 then
        return {
            ok = true,
            status = status,
            headers = responseHeaders,
            body = responseBody,
        }
    end

    local decoded = Json.decode(responseBody)
    local backendError = Validation.parseErrorResponse(decoded, status)
    return failure(
        ErrorClassifier.fromHttp(status, backendError.code),
        {
            status = status,
            headers = responseHeaders,
            body = responseBody,
            code = backendError.code,
            message = backendError.message,
            retryable = backendError.retryable == true,
        }
    )
end

local function resolveConnection(options)
    options = options or {}
    local baseUrl = options.baseUrl
    local timeout = options.timeoutSeconds
    if baseUrl == nil then
        baseUrl = Preferences.getBackendBaseUrl()
    end
    if timeout == nil then
        timeout = Preferences.getRequestTimeoutSeconds()
    end
    if not baseUrl or not timeout then
        return nil, nil
    end
    return baseUrl, timeout
end

local function postJson(path, request, options)
    local encoded, encodeError = Json.encode(request)
    if not encoded then
        return failure(ErrorClassifier.codes.internalError, {
            code = "request_encoding_failed",
            retryable = false,
        })
    end

    local baseUrl, timeout = resolveConnection(options)
    if not baseUrl or not timeout then
        return failure(ErrorClassifier.codes.validationError, {
            code = "invalid_preferences",
            retryable = false,
        })
    end
    local url = Config.apiUrl(baseUrl, path)
    local ok, responseBody, responseHeaders = LrTasks.pcall(function()
        return LrHttp.post(
            url,
            encoded,
            jsonHeaders,
            "POST",
            timeout
        )
    end)

    if not ok then
        return failure(ErrorClassifier.codes.networkError, {
            status = nil,
            code = "http_call_failed",
            retryable = false,
        })
    end
    return httpResult(responseBody, responseHeaders)
end

function ApiClient.analyze(request, options)
    return postJson(Config.apiPaths.analyze, request, options)
end

function ApiClient.develop(request, options)
    return postJson(Config.apiPaths.develop, request, options)
end

function ApiClient.health(options)
    local baseUrl, timeout = resolveConnection(options)
    if not baseUrl or not timeout then
        return failure(ErrorClassifier.codes.validationError, {
            code = "invalid_preferences",
            retryable = false,
        })
    end
    local ok, responseBody, responseHeaders = LrTasks.pcall(function()
        return LrHttp.get(
            Config.apiUrl(baseUrl, Config.apiPaths.health),
            jsonHeaders,
            timeout
        )
    end)
    if not ok then
        return failure(ErrorClassifier.codes.networkError, {
            code = "http_call_failed",
            retryable = false,
        })
    end
    return httpResult(responseBody, responseHeaders)
end

function ApiClient.decodeBody(response)
    return Json.decode(response and response.body)
end

return ApiClient
