local Utils = ModuleLoader.load("lib/Utils.lua")

local ExifMapper = {}

local developKeys = {
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
    "CropLeft",
    "CropRight",
    "CropTop",
    "CropBottom",
    "CropAngle",
}

local function putFinite(target, key, value, integerOnly)
    if not Utils.isFiniteNumber(value) then
        return
    end
    if integerOnly and value ~= math.floor(value) then
        return
    end
    target[key] = value
end

local function putPositive(target, key, value, integerOnly)
    if not Utils.isFiniteNumber(value) or value <= 0 then
        return
    end
    if integerOnly and value ~= math.floor(value) then
        return
    end
    target[key] = value
end

local function cameraName(photo)
    local make = Utils.trim(Utils.safeRawMetadata(photo, "cameraMake"))
    local model = Utils.trim(Utils.safeRawMetadata(photo, "cameraModel"))
    if make and model then
        if model:lower():find(make:lower(), 1, true) == 1 then
            return model
        end
        return make .. " " .. model
    end
    return model or make
end

local function captureDate(photo)
    local isoDate = Utils.trim(
        Utils.safeRawMetadata(photo, "dateTimeOriginalISO8601")
    )
    local hasDateTime = isoDate and isoDate:match(
        "^%d%d%d%d%-%d%d%-%d%d[Tt]%d%d:%d%d:%d%d"
    )
    local hasTimeZone = isoDate
        and (
            isoDate:match("[Zz]$")
            or isoDate:match("[+-]%d%d:%d%d$")
        )
    if hasDateTime and hasTimeZone then
        return isoDate
    end
    return nil
end

local function validLatitude(value)
    return Utils.isFiniteNumber(value)
        and value >= -90
        and value <= 90
end

local function validLongitude(value)
    return Utils.isFiniteNumber(value)
        and value >= -180
        and value <= 180
end

function ExifMapper.mapExif(photo)
    local exif = {}
    exif.camera = cameraName(photo)
    exif.lens = Utils.trim(Utils.safeRawMetadata(photo, "lens"))

    putPositive(
        exif,
        "iso",
        Utils.safeRawMetadata(photo, "isoSpeedRating"),
        true
    )
    putPositive(exif, "aperture", Utils.safeRawMetadata(photo, "aperture"))
    putPositive(
        exif,
        "focal_length",
        Utils.safeRawMetadata(photo, "focalLength")
    )
    putPositive(exif, "width", Utils.safeRawMetadata(photo, "width"), true)
    putPositive(exif, "height", Utils.safeRawMetadata(photo, "height"), true)
    putFinite(
        exif,
        "orientation",
        Utils.safeRawMetadata(photo, "orientation"),
        true
    )
    putFinite(
        exif,
        "exposure_compensation",
        Utils.safeRawMetadata(photo, "exposureBias")
    )

    local shutterSpeed = Utils.safeRawMetadata(photo, "shutterSpeed")
    if type(shutterSpeed) == "string" then
        exif.shutter_speed = Utils.trim(shutterSpeed)
    elseif Utils.isFiniteNumber(shutterSpeed) then
        exif.shutter_speed = tostring(shutterSpeed)
    end

    exif.capture_date = captureDate(photo)

    local gps = Utils.safeRawMetadata(photo, "gps")
    if type(gps) == "table"
        and validLatitude(gps.latitude)
        and validLongitude(gps.longitude) then
        exif.latitude = gps.latitude
        exif.longitude = gps.longitude
    end

    return exif
end

function ExifMapper.mapDevelopSettings(photo)
    local mapped = {}
    if not photo or type(photo.getDevelopSettings) ~= "function" then
        return mapped
    end

    local ok, source = pcall(function()
        return photo:getDevelopSettings()
    end)
    if not ok or type(source) ~= "table" then
        return mapped
    end

    for _, key in ipairs(developKeys) do
        local value = source[key]
        if Utils.isFiniteNumber(value) then
            mapped[key] = value
        end
    end
    return mapped
end

function ExifMapper.isSupportedPhoto(photo)
    local format = Utils.trim(Utils.safeRawMetadata(photo, "fileFormat"))
    return not format or format:upper() ~= "VIDEO"
end

return ExifMapper
