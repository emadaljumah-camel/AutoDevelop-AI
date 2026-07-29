local LrPrefs = import("LrPrefs")

local Utils = require("lib.Utils")

local Config = {}

Config.DEFAULT_STYLE_PROFILE = "natural_travel"

Config.defaults = {
    backendBaseUrl = "http://127.0.0.1:8005",
    styleProfileId = Config.DEFAULT_STYLE_PROFILE,
    requestTimeoutSeconds = 120,
    applyCrop = true,
}

Config.apiBaseUrl = Config.defaults.backendBaseUrl .. "/autodevelop/v1"
Config.apiPaths = {
    analyze = "/autodevelop/v1/analyze",
    develop = "/autodevelop/v1/develop",
}
Config.logPath = "logs/autodevelop.log"
Config.tempDirectory = "temp"

local function preferences()
    return LrPrefs.prefsForPlugin()
end

function Config.getBackendBaseUrl()
    local value = Utils.trim(preferences().backendBaseUrl)
        or Config.defaults.backendBaseUrl
    return value:gsub("/+$", "")
end

function Config.getStyleProfileId()
    return Utils.trim(preferences().styleProfileId)
        or Config.defaults.styleProfileId
end

function Config.getRequestTimeoutSeconds()
    local value = preferences().requestTimeoutSeconds
    if Utils.isFiniteNumber(value) and value > 0 then
        return value
    end
    return Config.defaults.requestTimeoutSeconds
end

function Config.getApplyCrop()
    local value = preferences().applyCrop
    if type(value) == "boolean" then
        return value
    end
    return Config.defaults.applyCrop
end

return Config
