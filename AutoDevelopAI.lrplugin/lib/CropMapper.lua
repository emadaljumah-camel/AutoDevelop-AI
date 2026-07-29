local Utils = require("lib.Utils")

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

function CropMapper.map(crop, applyCrop, currentSettings)
    if applyCrop ~= true or crop == nil then
        return nil
    end
    if type(crop) ~= "table" or crop.recommended ~= true then
        return nil
    end
    if not validUnit(crop.left)
        or not validUnit(crop.right)
        or not validUnit(crop.top)
        or not validUnit(crop.bottom)
        or not Utils.isFiniteNumber(crop.angle) then
        return nil
    end
    if crop.left >= crop.right or crop.top >= crop.bottom then
        return nil
    end
    if math.abs(crop.angle) > CropMapper.MAX_ABSOLUTE_ANGLE then
        return nil
    end
    if type(currentSettings) ~= "table" then
        return nil
    end
    for _, key in ipairs(cropKeys) do
        if not Utils.isFiniteNumber(currentSettings[key]) then
            return nil
        end
    end

    return {
        CropLeft = crop.left,
        CropRight = crop.right,
        CropTop = crop.top,
        CropBottom = crop.bottom,
        CropAngle = crop.angle,
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
