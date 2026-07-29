local ErrorClassifier = {}

ErrorClassifier.codes = {
    backendNotRunning = "backend_not_running",
    invalidProfile = "invalid_profile",
    modelNotFound = "model_not_found",
    modelUnavailable = "model_unavailable",
    modelNotConfigured = "model_not_configured",
    modelTimeout = "model_timeout",
    networkError = "network_error",
    invalidResponse = "invalid_response",
    backendError = "backend_error",
    validationError = "validation_error",
    cancelled = "cancelled",
    internalError = "internal_error",
}

local unavailableCodes = {
    cannotFindHost = true,
    cannotConnectToHost = true,
    resourceUnavailable = true,
}

function ErrorClassifier.fromNetworkInfo(info)
    local errorInfo = type(info) == "table" and info.error or nil
    local errorCode = type(errorInfo) == "table"
        and errorInfo.errorCode or nil

    if errorCode == "timedOut" then
        return ErrorClassifier.codes.modelTimeout
    end
    if errorCode == "cancelled" then
        return ErrorClassifier.codes.cancelled
    end
    if unavailableCodes[errorCode] then
        return ErrorClassifier.codes.backendNotRunning
    end
    if errorCode == "badURL" then
        return ErrorClassifier.codes.validationError
    end
    return ErrorClassifier.codes.networkError
end

function ErrorClassifier.fromHttp(status, backendCode)
    if backendCode == "profile_not_found" then
        return ErrorClassifier.codes.invalidProfile
    end
    if backendCode == "model_request_error" then
        return ErrorClassifier.codes.validationError
    end
    if backendCode == "model_not_found" then
        return ErrorClassifier.codes.modelNotFound
    end
    if backendCode == "model_unavailable" then
        return ErrorClassifier.codes.modelUnavailable
    end
    if backendCode == "model_not_configured" then
        return ErrorClassifier.codes.modelNotConfigured
    end
    if backendCode == "provider_timeout" then
        return ErrorClassifier.codes.modelTimeout
    end
    if backendCode == "provider_unavailable" then
        return ErrorClassifier.codes.backendNotRunning
    end
    if backendCode == "invalid_model_response"
        or backendCode == "inference_failed" then
        return ErrorClassifier.codes.invalidResponse
    end
    if backendCode == "model_response_error"
        or backendCode == "invalid_response_metadata" then
        return ErrorClassifier.codes.invalidResponse
    end
    if status == 400 or status == 422 then
        return ErrorClassifier.codes.validationError
    end
    if status == 500 or status == 502 or status == 503 then
        return ErrorClassifier.codes.backendError
    end
    return ErrorClassifier.codes.backendError
end

function ErrorClassifier.isTerminalForBatch(category)
    return category == ErrorClassifier.codes.backendNotRunning
        or category == ErrorClassifier.codes.invalidProfile
        or category == ErrorClassifier.codes.modelNotFound
        or category == ErrorClassifier.codes.modelUnavailable
        or category == ErrorClassifier.codes.modelNotConfigured
end

function ErrorClassifier.isRetryable(result)
    if not result or result.ok then
        return false
    end
    return result.category == ErrorClassifier.codes.modelTimeout
        or result.status == 500
        or result.status == 502
end

return ErrorClassifier
