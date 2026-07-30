local LrPrefs = import("LrPrefs")

local Config = ModuleLoader.load("lib/Config.lua")
local StyleProfiles = ModuleLoader.load("lib/StyleProfiles.lua")
local ModelProfiles = ModuleLoader.load("lib/ModelProfiles.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")

local Preferences = {}

local function defaultValues()
    local defaults = {}
    for key, value in pairs(Config.defaults) do
        defaults[key] = value
    end
    defaults.styleProfileId = StyleProfiles.getDefaultId()
    defaults.modelProfileId = ModelProfiles.getDefaultId()
    return defaults
end

local confirmationChoices = {
    { title = "Always", value = "always" },
    { title = "Never", value = "never" },
}

local loggingChoices = {
    { title = "Error", value = "error" },
    { title = "Warning", value = "warning" },
    { title = "Info", value = "info" },
    { title = "Debug", value = "debug" },
}

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
    if not normalized or not StyleProfiles.isValidId(normalized) then
        return nil, "Select Auto or one of the seven built-in style profiles."
    end
    return normalized
end

local function validateModelProfileId(value)
    local normalized = Utils.trim(value)
    if not normalized or not ModelProfiles.isSelectableId(normalized) then
        return nil, "Select an available AI model."
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

local function validateRequestTimeoutText(value)
    if type(value) ~= "string" or not value:match("^%d+$") then
        return nil, "Request timeout must be integer text from 10 to 600."
    end
    return validateRequestTimeoutSeconds(tonumber(value))
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
    modelProfileId = validateModelProfileId,
    requestTimeoutSeconds = validateRequestTimeoutSeconds,
    applyCompositionCrop = function(value)
        return validateBoolean(value, "Apply composition crop")
    end,
    applyLeveling = function(value)
        return validateBoolean(value, "Apply leveling correction")
    end,
    confirmationMode = validateConfirmationMode,
    loggingLevel = validateLoggingLevel,
    learningEnabled = function(value)
        return validateBoolean(value, "Personalized learning")
    end,
    learningCaptureBaseline = function(value)
        return validateBoolean(value, "Learning baseline capture")
    end,
    learningShowSummary = function(value)
        return validateBoolean(value, "Learning summary")
    end,
}

local function migrateGeometryPreferences(preferences)
    local legacyApplyCrop = preferences.applyCrop
    if type(legacyApplyCrop) ~= "boolean" then
        legacyApplyCrop = Config.defaults.applyCompositionCrop
    end
    if preferences.applyCompositionCrop == nil then
        preferences.applyCompositionCrop = legacyApplyCrop
    end
    if preferences.applyLeveling == nil then
        preferences.applyLeveling = legacyApplyCrop
    end
end

function Preferences.initializeDefaults()
    local preferences = store()
    migrateGeometryPreferences(preferences)
    for key, value in pairs(defaultValues()) do
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
    local default = defaultValues()[key]
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

function Preferences.getModelProfileId()
    return Preferences.get("modelProfileId")
end

function Preferences.getRequestTimeoutSeconds()
    return Preferences.get("requestTimeoutSeconds")
end

function Preferences.getApplyCompositionCrop()
    return Preferences.get("applyCompositionCrop")
end

function Preferences.getApplyLeveling()
    return Preferences.get("applyLeveling")
end

function Preferences.getConfirmationMode()
    return Preferences.get("confirmationMode")
end

function Preferences.getLoggingLevel()
    return Preferences.get("loggingLevel")
end

function Preferences.getLearningEnabled()
    return Preferences.get("learningEnabled")
end

function Preferences.getLearningCaptureBaseline()
    return Preferences.get("learningCaptureBaseline")
end

function Preferences.getLearningShowSummary()
    return Preferences.get("learningShowSummary")
end

function Preferences.getLearningPendingSessions()
    local value = store().learningPendingSessions
    return Utils.deepCopy(type(value) == "table" and value or {})
end

function Preferences.setLearningPendingSessions(value)
    store().learningPendingSessions =
        Utils.deepCopy(type(value) == "table" and value or {})
end

function Preferences.getRuntimeLoggingLevel()
    local level = Preferences.getLoggingLevel()
    if not level then
        return Config.defaults.loggingLevel
    end
    return level
end

local function copyChoices(choices)
    local copied = {}
    for index, choice in ipairs(choices) do
        copied[index] = {
            title = choice.title,
            value = choice.value,
        }
    end
    return copied
end

function Preferences.getStyleProfileChoices()
    return StyleProfiles.getChoices()
end

function Preferences.getModelProfileChoices()
    return ModelProfiles.getSelectableChoices()
end

function Preferences.getConfirmationChoices()
    return copyChoices(confirmationChoices)
end

function Preferences.getLoggingChoices()
    return copyChoices(loggingChoices)
end

function Preferences.validateRequestTimeoutText(value)
    return validateRequestTimeoutText(value)
end

function Preferences.valuesForUi()
    local preferences = store()
    migrateGeometryPreferences(preferences)
    local values = {}
    for key, default in pairs(defaultValues()) do
        local value = preferences[key]
        if value == nil then
            value = default
        end
        values[key] = value
    end
    return values
end

function Preferences.validatedSnapshot(overrides)
    overrides = overrides or {}
    migrateGeometryPreferences(store())
    local snapshot = {}
    local defaults = defaultValues()
    for key in pairs(defaults) do
        local rawValue = overrides[key]
        if rawValue == nil then
            rawValue = store()[key]
        end
        if rawValue == nil then
            rawValue = defaults[key]
        end
        local value, reason = Preferences.validate(key, rawValue)
        if value == nil then
            return nil, reason, key
        end
        snapshot[key] = value
    end
    return snapshot
end

function Preferences.resetDefaults()
    local preferences = store()
    for key, value in pairs(defaultValues()) do
        preferences[key] = value
    end
    return Preferences.valuesForUi()
end

return Preferences
