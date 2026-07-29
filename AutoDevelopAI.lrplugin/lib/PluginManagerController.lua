local Preferences = ModuleLoader.load("lib/Preferences.lua")

local PluginManagerController = {}

local preferenceKeys = {
    "backendBaseUrl",
    "styleProfileId",
    "applyCrop",
    "confirmationMode",
    "loggingLevel",
}

local getters = {
    backendBaseUrl = Preferences.getBackendBaseUrl,
    styleProfileId = Preferences.getStyleProfileId,
    applyCrop = Preferences.getApplyCrop,
    confirmationMode = Preferences.getConfirmationMode,
    loggingLevel = Preferences.getLoggingLevel,
}

local function addValidationError(errors, reason)
    if reason and reason ~= "" then
        errors[#errors + 1] = reason
    end
end

function PluginManagerController.populate(properties)
    local raw = Preferences.valuesForUi()
    local errors = {}

    for _, key in ipairs(preferenceKeys) do
        local value, reason = getters[key]()
        properties[key] = value ~= nil and value or raw[key]
        addValidationError(errors, reason)
    end

    local timeout, timeoutReason = Preferences.getRequestTimeoutSeconds()
    local timeoutValue = timeout ~= nil and timeout
        or raw.requestTimeoutSeconds
    properties.requestTimeoutText = tostring(timeoutValue or "")
    addValidationError(errors, timeoutReason)

    properties.connectionState = "idle"
    properties.connectionStatusText = "Not tested"
    properties.connectionTestRunning = false
    properties.canTestConnection = true
    properties.validationMessage = errors[1] or ""
end

local function normalizedProperties(properties)
    local values = {}
    local reason

    for _, key in ipairs(preferenceKeys) do
        values[key], reason = Preferences.validate(key, properties[key])
        if values[key] == nil then
            return nil, reason
        end
    end

    values.requestTimeoutSeconds, reason =
        Preferences.validateRequestTimeoutText(
            properties.requestTimeoutText
        )
    if values.requestTimeoutSeconds == nil then
        return nil, reason
    end
    return values
end

function PluginManagerController.validateAndSave(properties)
    local values, reason = normalizedProperties(properties)
    if not values then
        properties.validationMessage = reason
        return nil, reason
    end

    for _, key in ipairs(preferenceKeys) do
        Preferences.set(key, values[key])
        properties[key] = values[key]
    end
    Preferences.set(
        "requestTimeoutSeconds",
        values.requestTimeoutSeconds
    )
    properties.requestTimeoutText =
        tostring(values.requestTimeoutSeconds)
    properties.validationMessage = ""
    return values
end

function PluginManagerController.saveField(properties, key)
    local value = properties[key]
    local storedKey = key
    local normalized
    local reason

    if key == "requestTimeoutText" then
        storedKey = "requestTimeoutSeconds"
        normalized, reason =
            Preferences.validateRequestTimeoutText(value)
    else
        normalized, reason = Preferences.validate(key, value)
    end

    if normalized == nil then
        properties.validationMessage = reason
        return nil, reason
    end
    Preferences.set(storedKey, normalized)
    properties.validationMessage = ""
    return normalized
end

function PluginManagerController.classifyConnectionResult(callOk, result)
    if not callOk then
        return {
            state = "internal_error",
            text = "Connection test failed safely. Check the plug-in log.",
            category = "internal_error",
        }
    end
    if result and result.ok then
        return {
            state = "connected",
            text = "Connected",
            category = "connected",
        }
    end

    local category = result and result.category
    if category == "model_timeout" or category == "timeout" then
        return {
            state = "timeout",
            text = "Timed out",
            category = "timeout",
        }
    end
    if category == "backend_not_running" then
        return {
            state = "backend_not_running",
            text = "Backend not running",
            category = "backend_not_running",
        }
    end
    if category == "invalid_response" then
        return {
            state = "invalid_response",
            text = "Invalid response",
            category = "invalid_response",
        }
    end
    return {
        state = "network_error",
        text = "Network error",
        category = "network_error",
    }
end

return PluginManagerController
