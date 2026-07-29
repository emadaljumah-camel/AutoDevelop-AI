local LrPrefs = import("LrPrefs")

local Utils = require("lib.Utils")

local Config = {}

Config.DEFAULT_STYLE_PROFILE = "natural_travel"

Config.defaults = {
    backendBaseUrl = "http://127.0.0.1:8005",
    styleProfileId = Config.DEFAULT_STYLE_PROFILE,
    requestTimeoutSeconds = 120,
}

Config.apiBaseUrl = Config.defaults.backendBaseUrl .. "/autodevelop/v1"
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

return Config
