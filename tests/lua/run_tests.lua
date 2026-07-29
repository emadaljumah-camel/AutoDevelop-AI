package.path = "AutoDevelopAI.lrplugin/?.lua;"
    .. "AutoDevelopAI.lrplugin/?/init.lua;"
    .. package.path

local assertions = 0
local fakePreferences = {}
local encodedValue = nil

_G.import = function(name)
    if name == "LrPrefs" then
        return {
            prefsForPlugin = function()
                return fakePreferences
            end,
        }
    end
    if name == "LrJson" then
        return {
            encode = function(value)
                encodedValue = value
                return "{\"preview_path\":\"D:\\\\Temp\\\\preview.jpg\"}"
            end,
            decode = function()
                return {}
            end,
        }
    end
    error("Unexpected Lightroom import in pure Lua tests: " .. tostring(name))
end

local function assertTrue(value, message)
    assertions = assertions + 1
    if not value then
        error(message or "expected true", 2)
    end
end

local function assertEqual(actual, expected, message)
    assertions = assertions + 1
    if actual ~= expected then
        error(
            (message or "values differ")
                .. ": expected "
                .. tostring(expected)
                .. ", got "
                .. tostring(actual),
            2
        )
    end
end

local Utils = require("lib.Utils")
local Config = require("lib.Config")
local ExifMapper = require("lib.ExifMapper")
local RequestBuilder = require("lib.RequestBuilder")
local Validation = require("lib.Validation")
local BatchPolicy = require("lib.BatchPolicy")
local ResultStore = require("lib.ResultStore")

local function photo(raw, formatted, develop)
    formatted = formatted or {}
    if formatted.fileName == nil then
        formatted.fileName = raw.fileName
    end
    return {
        localIdentifier = raw.localIdentifier,
        getRawMetadata = function(_, key)
            return raw[key]
        end,
        getFormattedMetadata = function(_, key)
            return formatted[key]
        end,
        getDevelopSettings = function()
            return develop or {}
        end,
    }
end

local randomValue = 0
local function deterministicRandom(minimum, maximum)
    randomValue = randomValue + 1
    return minimum + ((randomValue - 1) % (maximum - minimum + 1))
end

local firstUuid = Utils.newUuid(deterministicRandom)
local secondUuid = Utils.newUuid(deterministicRandom)
assertTrue(Utils.isUuid(firstUuid), "UUID must be version 4")
assertTrue(Utils.isUuid(secondUuid), "second UUID must be version 4")
assertTrue(firstUuid ~= secondUuid, "request UUIDs must be unique")

local master = photo({
    localIdentifier = 42,
    fileName = "DSC_0042.NEF",
    fileFormat = "RAW",
})
local virtual = photo({
    localIdentifier = 43,
    fileName = "DSC_0042.NEF",
    fileFormat = "RAW",
    isVirtualCopy = true,
}, {
    copyName = "Black and White",
})
assertTrue(
    Utils.photoKey(master) ~= Utils.photoKey(virtual),
    "virtual copy key must be distinct"
)
assertEqual(Utils.photoKey(master), "local:42")
assertEqual(Utils.photoKey(virtual), "local:43")
assertEqual(Utils.photoFilename(master), "DSC_0042.NEF")
assertEqual(
    Utils.photoFilename(photo({ localIdentifier = 17 })),
    "photo_17"
)
local formattedFilename = photo({
    localIdentifier = 18,
    fileName = "wrong-raw-name.nef",
}, {
    fileName = "Formatted Name.NEF",
})
assertEqual(
    Utils.photoFilename(formattedFilename),
    "Formatted Name.NEF",
    "filename must come from formatted metadata"
)
local sameNameFirst = photo({
    localIdentifier = 50,
    fileName = "same.nef",
})
local sameNameSecond = photo({
    localIdentifier = 51,
    fileName = "same.nef",
})
assertTrue(
    Utils.photoKey(sameNameFirst) ~= Utils.photoKey(sameNameSecond),
    "same-name photos must have distinct local identifier keys"
)
local uuidFallback = photo({
    uuid = "ABCDEF12-3456-7890-ABCD-EF1234567890",
    fileName = "",
})
assertEqual(
    Utils.photoKey(uuidFallback),
    "uuid:ABCDEF12-3456-7890-ABCD-EF1234567890"
)
assertEqual(
    Utils.photoFilename(uuidFallback),
    "photo_ABCDEF12-3456-7890-ABCD-EF1234567890"
)

local mappedPhoto = photo({
    localIdentifier = 7,
    fileName = "Mapped.NEF",
    cameraMake = "Nikon",
    cameraModel = "Z 8",
    isoSpeedRating = 800,
    aperture = 5.6,
    focalLength = 50,
    exposureBias = 0,
    width = 8256,
    height = 5504,
    fileFormat = "RAW",
}, nil, {
    Exposure2012 = 0,
    Contrast2012 = 12,
    Temperature = 5500,
    UnsupportedSetting = 99,
    Tint = 0 / 0,
})
local exif = ExifMapper.mapExif(mappedPhoto)
assertEqual(exif.camera, "Nikon Z 8")
assertEqual(exif.iso, 800)
assertTrue(exif.shutter_speed == nil, "missing EXIF must be omitted")
local datedExif = ExifMapper.mapExif(photo({
    dateTimeOriginalISO8601 = "2026-07-29T10:30:15+03:00",
}))
assertEqual(
    datedExif.capture_date,
    "2026-07-29T10:30:15+03:00",
    "documented ISO capture date must pass through"
)
local missingDateExif = ExifMapper.mapExif(photo({
    captureTime = 123456789,
}))
assertTrue(
    missingDateExif.capture_date == nil,
    "unsupported captureTime must not be used"
)
local zeroGps = ExifMapper.mapExif(photo({
    gps = { latitude = 0, longitude = 0 },
}))
assertEqual(zeroGps.latitude, 0)
assertEqual(zeroGps.longitude, 0)
local boundaryGps = ExifMapper.mapExif(photo({
    gps = { latitude = -90, longitude = 180 },
}))
assertEqual(boundaryGps.latitude, -90)
assertEqual(boundaryGps.longitude, 180)
local otherBoundaryGps = ExifMapper.mapExif(photo({
    gps = { latitude = 90, longitude = -180 },
}))
assertEqual(otherBoundaryGps.latitude, 90)
assertEqual(otherBoundaryGps.longitude, -180)
local invalidLatitudeGps = ExifMapper.mapExif(photo({
    gps = { latitude = 90.1, longitude = 0 },
}))
assertTrue(invalidLatitudeGps.latitude == nil)
assertTrue(invalidLatitudeGps.longitude == nil)
local invalidLongitudeGps = ExifMapper.mapExif(photo({
    gps = { latitude = 0, longitude = -180.1 },
}))
assertTrue(invalidLongitudeGps.latitude == nil)
assertTrue(invalidLongitudeGps.longitude == nil)
local nonFiniteGps = ExifMapper.mapExif(photo({
    gps = { latitude = 0 / 0, longitude = math.huge },
}))
assertTrue(nonFiniteGps.latitude == nil)
assertTrue(nonFiniteGps.longitude == nil)
local invalidExif = ExifMapper.mapExif(photo({
    isoSpeedRating = 0,
    aperture = -1,
    focalLength = math.huge,
    width = -20,
    height = 0 / 0,
}))
assertTrue(invalidExif.iso == nil, "non-positive ISO must be omitted")
assertTrue(invalidExif.aperture == nil, "non-positive aperture must be omitted")
assertTrue(
    invalidExif.focal_length == nil,
    "infinite focal length must be omitted"
)
assertTrue(invalidExif.width == nil, "non-positive width must be omitted")
assertTrue(invalidExif.height == nil, "NaN height must be omitted")
local settings = ExifMapper.mapDevelopSettings(mappedPhoto)
assertEqual(settings.Exposure2012, 0, "zero must be preserved")
assertEqual(settings.Contrast2012, 12)
assertTrue(settings.Tint == nil, "NaN must be omitted")
assertTrue(
    settings.UnsupportedSetting == nil,
    "unsupported settings must be omitted"
)

local request = assert(RequestBuilder.build(
    mappedPhoto,
    "D:\\Temp\\AutoDevelopAI\\preview.jpg",
    {
        uuidFactory = function()
            return "12345678-1234-4abc-8abc-1234567890ab"
        end,
    }
))
assertEqual(request.schema_version, "1.0")
assertEqual(request.options.style_profile, "natural_travel")
assertEqual(request.current_settings.Exposure2012, 0)
assertEqual(request.preview_path, "D:\\Temp\\AutoDevelopAI\\preview.jpg")
assertEqual(Config.DEFAULT_STYLE_PROFILE, "natural_travel")
fakePreferences.styleProfileId = nil
assertEqual(Config.getStyleProfileId(), Config.DEFAULT_STYLE_PROFILE)
fakePreferences.styleProfileId = "architecture"
assertEqual(Config.getStyleProfileId(), "architecture")

local configured = assert(RequestBuilder.build(
    mappedPhoto,
    "D:\\Temp\\preview.jpg",
    {
        styleProfileId = "architecture",
        uuidFactory = function()
            return "22345678-1234-4abc-8abc-1234567890ab"
        end,
    }
))
assertEqual(configured.options.style_profile, "architecture")

local successfulResponse = {
    status = "success",
    schema_version = "1.0",
    request_id = request.request_id,
    filename = request.filename,
    analysis = {},
    edit_plan = {},
    model = "fake-autodevelop-v1",
}
assertTrue(Validation.validateAnalyzeResponse(successfulResponse, request))

local mismatched = Utils.deepCopy(successfulResponse)
mismatched.request_id = "32345678-1234-4abc-8abc-1234567890ab"
assertTrue(
    not Validation.validateAnalyzeResponse(mismatched, request),
    "mismatched request ID must fail"
)
local wrongSchema = Utils.deepCopy(successfulResponse)
wrongSchema.schema_version = "2.0"
assertTrue(
    not Validation.validateAnalyzeResponse(wrongSchema, request),
    "wrong schema must fail"
)
local missingAnalysis = Utils.deepCopy(successfulResponse)
missingAnalysis.analysis = nil
assertTrue(
    not Validation.validateAnalyzeResponse(missingAnalysis, request),
    "missing analysis must fail"
)
local mismatchedFilename = Utils.deepCopy(successfulResponse)
mismatchedFilename.filename = " " .. request.filename .. " "
assertTrue(
    not Validation.validateAnalyzeResponse(mismatchedFilename, request),
    "response filename must match exactly"
)

local parsedError = Validation.parseErrorResponse({
    error = {
        code = "profile_not_found",
        message = "Profile does not exist.",
        retryable = false,
    },
}, 400)
assertEqual(parsedError.code, "profile_not_found")
assertEqual(parsedError.retryable, false)

assertTrue(BatchPolicy.shouldRetry(500, 0, false))
assertTrue(BatchPolicy.shouldRetry(502, 0, false))
assertTrue(not BatchPolicy.shouldRetry(500, 1, false))
assertTrue(not BatchPolicy.shouldRetry(502, 0, true))

local summary = BatchPolicy.newSummary(5)
summary.analyzed = 2
summary.skipped = 1
BatchPolicy.addFailure(summary, "bad.nef", "failed")
BatchPolicy.markNotProcessed(summary, 1)
assertEqual(summary.selected, 5)
assertEqual(summary.analyzed, 2)
assertEqual(summary.failed, 1)
assertEqual(summary.skipped, 1)
assertEqual(summary.notProcessed, 1)

ResultStore.clear()
local resultPhotoKey = Utils.photoKey(mappedPhoto)
assertEqual(resultPhotoKey, "local:7")
ResultStore.put(resultPhotoKey, {
    request_id = request.request_id,
})
local stored = ResultStore.get(resultPhotoKey)
stored.request_id = "changed"
assertEqual(ResultStore.count(), 1)
assertEqual(
    ResultStore.get(resultPhotoKey).request_id,
    request.request_id,
    "result store must return defensive copies"
)
ResultStore.remove(resultPhotoKey)
assertEqual(ResultStore.count(), 0)

local Json = require("lib.Json")
local encoded = assert(Json.encode(request))
assertTrue(encodedValue == request, "LrJson must receive the request table")
assertTrue(
    encoded:find("D:\\\\Temp", 1, true) ~= nil,
    "Windows path must be escaped by LrJson"
)

print("Lua assertions passed: " .. tostring(assertions))
