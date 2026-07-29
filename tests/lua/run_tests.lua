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
    if name == "LrTasks" then
        return {
            pcall = function(fn, ...)
                return pcall(fn, ...)
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
local DevelopSettingsMapper = require("lib.DevelopSettingsMapper")
local CropMapper = require("lib.CropMapper")
local PendingOperation = require("lib.PendingOperation")
local ApplyService = require("lib.ApplyService")

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

local developRequest = assert(RequestBuilder.buildDevelop(
    mappedPhoto,
    "D:\\Temp\\develop-preview.jpg",
    {
        styleProfileId = "portrait",
        includeCrop = true,
        includeDenoise = true,
        uuidFactory = function()
            return "33345678-1234-4abc-8abc-1234567890ab"
        end,
    }
))
assertEqual(developRequest.options.style_profile, "portrait")
assertEqual(developRequest.options.include_crop, true)
assertEqual(developRequest.options.include_denoise, true)
assertEqual(developRequest.options.dry_run, false)
assertEqual(developRequest.options.preserve_current_adjustments, true)
assertEqual(Config.apiPaths.develop, "/autodevelop/v1/develop")
assertEqual(Config.defaults.backendBaseUrl, "http://127.0.0.1:8005")
fakePreferences.applyCrop = nil
assertEqual(Config.getApplyCrop(), true)
fakePreferences.applyCrop = false
assertEqual(Config.getApplyCrop(), false)
fakePreferences.applyCrop = nil

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

local developResponse = {
    status = "success",
    schema_version = "1.0",
    request_id = developRequest.request_id,
    filename = developRequest.filename,
    analysis = {},
    edit_plan = {},
    model = "fake-autodevelop-v1",
    processing_duration_ms = 3,
    develop_settings = {
        Exposure2012 = 0,
        Contrast2012 = 10,
    },
    crop = {
        recommended = true,
        left = 0,
        right = 0.95,
        top = 0,
        bottom = 0.95,
        angle = 0,
        confidence = 0.9,
    },
    denoise = {
        recommended = true,
        amount = 20,
        confidence = 0.9,
    },
    warnings = {
        {
            code = "example",
            message = "Example warning.",
            severity = "warning",
        },
    },
}
assertTrue(
    Validation.validateDevelopResponse(developResponse, developRequest)
)
local developRequestMismatch = Utils.deepCopy(developResponse)
developRequestMismatch.request_id =
    "43345678-1234-4abc-8abc-1234567890ab"
assertTrue(
    not Validation.validateDevelopResponse(
        developRequestMismatch,
        developRequest
    )
)
local developFilenameMismatch = Utils.deepCopy(developResponse)
developFilenameMismatch.filename = "Different.NEF"
assertTrue(
    not Validation.validateDevelopResponse(
        developFilenameMismatch,
        developRequest
    )
)
local developWrongSchema = Utils.deepCopy(developResponse)
developWrongSchema.schema_version = "2.0"
assertTrue(
    not Validation.validateDevelopResponse(developWrongSchema, developRequest)
)
local developMissingSettings = Utils.deepCopy(developResponse)
developMissingSettings.develop_settings = nil
assertTrue(
    not Validation.validateDevelopResponse(
        developMissingSettings,
        developRequest
    )
)
local developUnknownShape = Utils.deepCopy(developResponse)
developUnknownShape.untrusted = true
assertTrue(
    not Validation.validateDevelopResponse(
        developUnknownShape,
        developRequest
    )
)
local developInvalidWarnings = Utils.deepCopy(developResponse)
developInvalidWarnings.warnings = {
    invalid = {
        code = "bad",
        message = "Not an array.",
        severity = "warning",
    },
}
assertTrue(
    not Validation.validateDevelopResponse(
        developInvalidWarnings,
        developRequest
    )
)

local currentSettings = {
    Exposure2012 = 1,
    Contrast2012 = 2,
    Highlights2012 = 3,
    Shadows2012 = 4,
    Whites2012 = 5,
    Blacks2012 = 6,
    Texture = 7,
    Clarity2012 = 8,
    Dehaze = 9,
    Vibrance = 10,
    Saturation = 11,
    Temperature = 5500,
    Tint = 4,
    CropLeft = 0,
    CropRight = 1,
    CropTop = 0,
    CropBottom = 1,
    CropAngle = 0,
    ProcessVersion = "15.4",
}
local backendSettings = {
    Exposure2012 = 0,
    Contrast2012 = 12,
    Highlights2012 = -20,
    Shadows2012 = 20,
    Whites2012 = 8,
    Blacks2012 = -8,
    Texture = 5,
    Clarity2012 = 4,
    Dehaze = 3,
    Vibrance = 10,
    Saturation = 0,
    Temperature = 5200,
    Tint = 0,
    UnknownSetting = 99,
    ProcessVersion = "99.0",
}
local mappedDevelop = DevelopSettingsMapper.map(
    backendSettings,
    currentSettings
)
assertEqual(mappedDevelop.Exposure2012, 0, "mapped zero must be preserved")
assertEqual(mappedDevelop.Contrast2012, 12)
assertEqual(mappedDevelop.Highlights2012, -20)
assertEqual(mappedDevelop.Shadows2012, 20)
assertEqual(mappedDevelop.Whites2012, 8)
assertEqual(mappedDevelop.Blacks2012, -8)
assertEqual(mappedDevelop.Texture, 5)
assertEqual(mappedDevelop.Clarity2012, 4)
assertEqual(mappedDevelop.Dehaze, 3)
assertEqual(mappedDevelop.Vibrance, 10)
assertEqual(mappedDevelop.Saturation, 0)
assertEqual(mappedDevelop.Temperature, 5200)
assertEqual(mappedDevelop.Tint, 0)
assertTrue(mappedDevelop.UnknownSetting == nil)
assertTrue(mappedDevelop.ProcessVersion == nil)

local invalidBackendSettings = Utils.deepCopy(backendSettings)
invalidBackendSettings.Exposure2012 = 0 / 0
invalidBackendSettings.Contrast2012 = math.huge
invalidBackendSettings.Highlights2012 = nil
local invalidMapped = DevelopSettingsMapper.map(
    invalidBackendSettings,
    currentSettings
)
assertTrue(invalidMapped.Exposure2012 == nil)
assertTrue(invalidMapped.Contrast2012 == nil)
assertTrue(invalidMapped.Highlights2012 == nil)
local missingWhiteBalanceValues = Utils.deepCopy(currentSettings)
missingWhiteBalanceValues.Temperature = nil
missingWhiteBalanceValues.Tint = nil
local conservativeWhiteBalance = DevelopSettingsMapper.map(
    backendSettings,
    missingWhiteBalanceValues
)
assertTrue(conservativeWhiteBalance.Temperature == nil)
assertTrue(conservativeWhiteBalance.Tint == nil)

local validCrop = {
    recommended = true,
    left = 0,
    right = 0.95,
    top = 0,
    bottom = 0.9,
    angle = 0,
}
local mappedCrop = CropMapper.map(validCrop, true, currentSettings)
assertEqual(mappedCrop.CropLeft, 0)
assertEqual(mappedCrop.CropRight, 0.95)
assertEqual(mappedCrop.CropTop, 0)
assertEqual(mappedCrop.CropBottom, 0.9)
assertEqual(mappedCrop.CropAngle, 0)
assertTrue(CropMapper.map(nil, true, currentSettings) == nil)
assertTrue(CropMapper.map(validCrop, false, currentSettings) == nil)
local incompleteCrop = Utils.deepCopy(validCrop)
incompleteCrop.angle = nil
assertTrue(CropMapper.map(incompleteCrop, true, currentSettings) == nil)
local outsideCrop = Utils.deepCopy(validCrop)
outsideCrop.left = -0.01
assertTrue(CropMapper.map(outsideCrop, true, currentSettings) == nil)
local reversedHorizontalCrop = Utils.deepCopy(validCrop)
reversedHorizontalCrop.left = 0.9
reversedHorizontalCrop.right = 0.2
assertTrue(
    CropMapper.map(reversedHorizontalCrop, true, currentSettings) == nil
)
local reversedVerticalCrop = Utils.deepCopy(validCrop)
reversedVerticalCrop.top = 0.9
reversedVerticalCrop.bottom = 0.2
assertTrue(
    CropMapper.map(reversedVerticalCrop, true, currentSettings) == nil
)
local infiniteAngleCrop = Utils.deepCopy(validCrop)
infiniteAngleCrop.angle = math.huge
assertTrue(
    CropMapper.map(infiniteAngleCrop, true, currentSettings) == nil
)
local excessiveAngleCrop = Utils.deepCopy(validCrop)
excessiveAngleCrop.angle = 45.1
assertTrue(
    CropMapper.map(excessiveAngleCrop, true, currentSettings) == nil
)

local originalForApply = ApplyService.captureOriginal(
    currentSettings,
    mappedDevelop
)
local pending = PendingOperation.new({
    photo = mappedPhoto,
    photoKey = Utils.photoKey(mappedPhoto),
    filename = "Mapped.NEF",
    requestId = developRequest.request_id,
    profileId = "portrait",
    originalSettings = originalForApply,
    mappedSettings = mappedDevelop,
    cropIncluded = true,
    denoiseRecommended = true,
    warnings = developResponse.warnings,
    model = developResponse.model,
})
pending.mappedSettings.Exposure2012 = 99
assertEqual(mappedDevelop.Exposure2012, 0)
pending.originalSettings.Exposure2012 = 99
assertEqual(originalForApply.Exposure2012, 1)
assertEqual(pending.photoKey, "local:7")
assertEqual(pending.denoiseRecommended, true)

local insideWrite = false
local writeAction = nil
local appliedSettings = nil
local fakeCatalog = {
    withWriteAccessDo = function(_, action, callback)
        writeAction = action
        insideWrite = true
        callback()
        insideWrite = false
    end,
}
local successfulPhoto = {
    applyDevelopSettings = function(_, values)
        assertTrue(insideWrite, "apply must run inside catalog write access")
        appliedSettings = Utils.deepCopy(values)
    end,
}
local safeOperation = PendingOperation.new({
    photo = successfulPhoto,
    mappedSettings = {
        Exposure2012 = 0,
        UnknownSetting = 123,
    },
    originalSettings = {
        Exposure2012 = 1,
    },
})
local applyResult = ApplyService.applyBatch(
    fakeCatalog,
    { safeOperation }
)
assertEqual(writeAction, "AutoDevelop AI: Apply Develop Settings")
assertEqual(applyResult.applied, 1)
assertEqual(safeOperation.applicationStatus, "applied")
assertEqual(appliedSettings.Exposure2012, 0)
assertTrue(appliedSettings.UnknownSetting == nil)
assertEqual(safeOperation.mappedSettings.UnknownSetting, 123)

local partialCropSettings = ApplyService.sanitize({
    Exposure2012 = 0,
    CropLeft = 0.1,
})
assertEqual(partialCropSettings.Exposure2012, 0)
assertTrue(partialCropSettings.CropLeft == nil)
local completeCropSettings = ApplyService.sanitize(mappedCrop)
assertEqual(completeCropSettings.CropLeft, 0)
assertEqual(completeCropSettings.CropRight, 0.95)
assertEqual(completeCropSettings.CropTop, 0)
assertEqual(completeCropSettings.CropBottom, 0.9)
assertEqual(completeCropSettings.CropAngle, 0)

local cancelledCalls = 0
local cancelledPhoto = {
    applyDevelopSettings = function()
        cancelledCalls = cancelledCalls + 1
    end,
}
local cancelledResult = ApplyService.applyBatch(
    fakeCatalog,
    {
        PendingOperation.new({
            photo = cancelledPhoto,
            mappedSettings = { Exposure2012 = 1 },
            originalSettings = { Exposure2012 = 0 },
        }),
    },
    {
        isCancelled = function()
            return true
        end,
    }
)
assertEqual(cancelledCalls, 0)
assertEqual(cancelledResult.notApplied, 1)
assertEqual(cancelledResult.cancelled, true)

local restoreCalls = 0
local restoredValue = nil
local failingPhoto = {
    applyDevelopSettings = function(_, values)
        restoreCalls = restoreCalls + 1
        if restoreCalls == 1 then
            error("simulated apply failure")
        end
        restoredValue = values.Exposure2012
    end,
}
local restoreResult = ApplyService.applyBatch(
    fakeCatalog,
    {
        PendingOperation.new({
            photo = failingPhoto,
            mappedSettings = { Exposure2012 = 1 },
            originalSettings = { Exposure2012 = 0 },
        }),
    }
)
assertEqual(restoreResult.restoredAfterFailure, 1)
assertEqual(restoreResult.failedNotRestored, 0)
assertEqual(restoredValue, 0)

local failedRestorePhoto = {
    applyDevelopSettings = function()
        error("simulated apply and restore failure")
    end,
}
local failedRestoreResult = ApplyService.applyBatch(
    fakeCatalog,
    {
        PendingOperation.new({
            photo = failedRestorePhoto,
            mappedSettings = { Exposure2012 = 1 },
            originalSettings = { Exposure2012 = 0 },
        }),
    }
)
assertEqual(failedRestoreResult.restoredAfterFailure, 0)
assertEqual(failedRestoreResult.failedNotRestored, 1)

local pendingList = { pending, safeOperation }
PendingOperation.clear(pendingList)
assertEqual(#pendingList, 0)

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
