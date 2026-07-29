local Utils = require("lib.Utils")

local DevelopSettingsMapper = {}

local supportedKeys = {
    "Exposure2012",
    "Contrast2012",
    "Highlights2012",
    "Shadows2012",
    "Whites2012",
    "Blacks2012",
    "Texture",
    "Clarity2012",
    "Dehaze",
    "Vibrance",
    "Saturation",
    "Temperature",
    "Tint",
}

local supportedSet = {}
for _, key in ipairs(supportedKeys) do
    supportedSet[key] = true
end

function DevelopSettingsMapper.map(backendSettings, currentSettings)
    local mapped = {}
    if type(backendSettings) ~= "table"
        or type(currentSettings) ~= "table" then
        return mapped
    end

    for _, key in ipairs(supportedKeys) do
        local recommended = backendSettings[key]
        local original = currentSettings[key]
        if Utils.isFiniteNumber(recommended)
            and Utils.isFiniteNumber(original) then
            mapped[key] = recommended
        end
    end
    return mapped
end

function DevelopSettingsMapper.isSupportedKey(key)
    return supportedSet[key] == true
end

function DevelopSettingsMapper.keys()
    return Utils.deepCopy(supportedKeys)
end

return DevelopSettingsMapper
