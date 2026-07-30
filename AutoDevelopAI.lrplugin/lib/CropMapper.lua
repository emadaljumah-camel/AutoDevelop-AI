local Utils = ModuleLoader.load("lib/Utils.lua")

local CropMapper = {}

CropMapper.MAX_ABSOLUTE_ANGLE = 45

local cropKeys = {
    "CropLeft",
    "CropRight",
    "CropTop",
    "CropBottom",
    "CropAngle",
}

local cropSet = {}
for _, key in ipairs(cropKeys) do
    cropSet[key] = true
end

local function validUnit(value)
    return Utils.isFiniteNumber(value) and value >= 0 and value <= 1
end

local function validBounds(source)
    return type(source) == "table"
        and validUnit(source.left or source.CropLeft)
        and validUnit(source.right or source.CropRight)
        and validUnit(source.top or source.CropTop)
        and validUnit(source.bottom or source.CropBottom)
        and (source.left or source.CropLeft)
            < (source.right or source.CropRight)
        and (source.top or source.CropTop)
            < (source.bottom or source.CropBottom)
end

function CropMapper.map(crop, leveling, options, currentSettings)
    options = options or {}
    if type(currentSettings) ~= "table" then
        return nil
    end
    for _, key in ipairs(cropKeys) do
        if not Utils.isFiniteNumber(currentSettings[key]) then
            return nil
        end
    end

    local applyCrop = options.applyCompositionCrop == true
        and type(crop) == "table"
        and crop.recommended == true
        and validBounds(crop)
    local applyLeveling = options.applyLeveling == true
        and type(leveling) == "table"
        and leveling.recommended == true
        and Utils.isFiniteNumber(leveling.angle)
        and math.abs(leveling.angle) <= CropMapper.MAX_ABSOLUTE_ANGLE
    if not applyCrop and not applyLeveling then
        return nil
    end

    return {
        CropLeft = applyCrop and crop.left or currentSettings.CropLeft,
        CropRight = applyCrop and crop.right or currentSettings.CropRight,
        CropTop = applyCrop and crop.top or currentSettings.CropTop,
        CropBottom = applyCrop and crop.bottom or currentSettings.CropBottom,
        CropAngle = applyLeveling
            and leveling.angle or currentSettings.CropAngle,
    }
end

function CropMapper.isSupportedKey(key)
    return cropSet[key] == true
end

function CropMapper.sanitizeMapped(settings)
    local mapped = {}
    if type(settings) ~= "table" then
        return mapped
    end
    local hasCrop = false
    for _, key in ipairs(cropKeys) do
        if settings[key] ~= nil then
            hasCrop = true
        end
    end
    if not hasCrop then
        return mapped
    end
    for _, key in ipairs(cropKeys) do
        if not Utils.isFiniteNumber(settings[key]) then
            return {}
        end
    end
    if not validUnit(settings.CropLeft)
        or not validUnit(settings.CropRight)
        or not validUnit(settings.CropTop)
        or not validUnit(settings.CropBottom)
        or settings.CropLeft >= settings.CropRight
        or settings.CropTop >= settings.CropBottom
        or math.abs(settings.CropAngle) > CropMapper.MAX_ABSOLUTE_ANGLE then
        return {}
    end
    for _, key in ipairs(cropKeys) do
        mapped[key] = settings[key]
    end
    return mapped
end

function CropMapper.keys()
    return Utils.deepCopy(cropKeys)
end

return CropMapper
