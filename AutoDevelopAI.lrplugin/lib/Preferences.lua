local LrPrefs = import("LrPrefs")

local Config = ModuleLoader.load("lib/Config.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")

local Preferences = {}

Preferences.profileChoices = {
    { title = "Natural Travel", value = "natural_travel" },
    { title = "Stock Neutral", value = "stock_neutral" },
    { title = "Landscape Impact", value = "landscape_impact" },
    { title = "Architecture", value = "architecture" },
    { title = "Portrait", value = "portrait" },
    { title = "Night", value = "night" },
}

Preferences.confirmationChoices = {
    { title = "Always ask", value = "always" },
    { title = "Never ask", value = "never" },
}

Preferences.loggingChoices = {
    { title = "Errors only", value = "error" },
    { title = "Warnings and errors", value = "warning" },
    { title = "Information", value = "info" },
    { title = "Debug", value = "debug" },
}

local profileIds = {}
for _, choice in ipairs(Preferences.profileChoices) do
    profileIds[choice.value] = true
end

local confirmationModes = {
    always = true,
    never = true,
}

local loggingLevels = {
    error = true,
    warning = true,
    info = true,
    debug = true,
}

local function store()
    return LrPrefs.prefsForPlugin()
end

local function validateBackendBaseUrl(value)
    local normalized = Utils.trim(value)
    if not normalized then
        return nil, "Backend URL is required."
    end
    normalized = normalized:gsub("/+$", "")
    local lower = normalized:lower()
    if not lower:match("^https?://") then
        return nil, "Backend URL must start with http:// or https://."
    end
    if lower:sub(-#Config.API_PREFIX) == Config.API_PREFIX then
        return nil, "Enter the backend base URL without "
            .. Config.API_PREFIX .. "."
    end
    local schemeEnd = normalized:find("://", 1, true)
    local remainder = schemeEnd and normalized:sub(schemeEnd + 3) or ""
    local authority = remainder:match("^([^/%s]+)")
    if not authority
        or authority == ""
        or authority:find("@", 1, true)
        or normalized:find("%s")
        or normalized:find("?", 1, true)
        or normalized:find("#", 1, true) then
        return nil, "Backend URL must contain a valid host."
    end
    return normalized
end

local function validateStyleProfileId(value)
    local normalized = Utils.trim(value)
    if not normalized or not profileIds[normalized] then
        return nil, "Select one of the six built-in style profiles."
    end
    return normalized
end

local function validateRequestTimeoutSeconds(value)
    local normalized = value
    if not Utils.isFiniteNumber(normalized)
        or normalized % 1 ~= 0
        or normalized < 10
        or normalized > 600 then
        return nil, "Request timeout must be a whole number from 10 to 600."
    end
    return normalized
end

local function validateBoolean(value, label)
    if type(value) ~= "boolean" then
        return nil, label .. " must be on or off."
    end
    return value
end

local function validateConfirmationMode(value)
    if type(value) ~= "string" or not confirmationModes[value] then
        return nil, "Confirmation must be Always ask or Never ask."
    end
    return value
end

local function validateLoggingLevel(value)
    if type(value) ~= "string" or not loggingLevels[value] then
        return nil, "Select a valid logging level."
    end
    return value
end

local validators = {
    backendBaseUrl = validateBackendBaseUrl,
    styleProfileId = validateStyleProfileId,
    requestTimeoutSeconds = validateRequestTimeoutSeconds,
    applyCrop = function(value)
        return validateBoolean(value, "Apply crop")
    end,
    confirmationMode = validateConfirmationMode,
    loggingLevel = validateLoggingLevel,
}

function Preferences.initializeDefaults()
    local preferences = store()
    for key, value in pairs(Config.defaults) do
        if preferences[key] == nil then
            preferences[key] = value
        end
    end
end

function Preferences.validate(key, value)
    local validator = validators[key]
    if not validator then
        return nil, "Unknown preference: " .. tostring(key)
    end
    return validator(value)
end

function Preferences.set(key, value)
    local normalized, reason = Preferences.validate(key, value)
    if normalized == nil then
        return nil, reason
    end
    store()[key] = normalized
    return normalized
end

function Preferences.get(key)
    local default = Config.defaults[key]
    if default == nil then
        return nil, "Unknown preference: " .. tostring(key)
    end
    local value = store()[key]
    if value == nil then
        value = default
    end
    return Preferences.validate(key, value)
end

function Preferences.getBackendBaseUrl()
    return Preferences.get("backendBaseUrl")
end

function Preferences.getStyleProfileId()
    return Preferences.get("styleProfileId")
end

function Preferences.getRequestTimeoutSeconds()
    return Preferences.get("requestTimeoutSeconds")
end

function Preferences.getApplyCrop()
    return Preferences.get("applyCrop")
end

function Preferences.getConfirmationMode()
    return Preferences.get("confirmationMode")
end

function Preferences.getLoggingLevel()
    return Preferences.get("loggingLevel")
end

function Preferences.getRuntimeLoggingLevel()
    local level = Preferences.getLoggingLevel()
    if not level then
        return Config.defaults.loggingLevel
    end
    return level
end

function Preferences.valuesForUi()
    local preferences = store()
    local values = {}
    for key, default in pairs(Config.defaults) do
        local value = preferences[key]
        if value == nil then
            value = default
        end
        values[key] = value
    end
    return values
end

function Preferences.validatedSnapshot()
    local snapshot = {}
    for key in pairs(Config.defaults) do
        local value, reason = Preferences.get(key)
        if value == nil then
            return nil, reason, key
        end
        snapshot[key] = value
    end
    return snapshot
end

function Preferences.resetDefaults()
    local preferences = store()
    for key, value in pairs(Config.defaults) do
        preferences[key] = value
    end
    return Preferences.valuesForUi()
end

return Preferences
