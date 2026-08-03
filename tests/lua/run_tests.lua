package.path = "AutoDevelopAI.lrplugin/?.lua;"
    .. "AutoDevelopAI.lrplugin/?/init.lua;"
    .. package.path

local assertions = 0
local fakePreferences = {}
local fakeDevelopPresetFolders = {}
local logged = {
    error = {},
    warning = {},
    info = {},
    debug = {},
}
local lastDialog = nil
local lastModalDialogOptions = nil
local lastPropertyTable = nil
local modalDialogResult = "ok"
local modalDialogMutator = nil
local fakeHttpResponseBody = nil
local fakeHttpResponseHeaders = { status = 200 }
local fakeHttpResponder = nil
local lastHttpPostBody = nil
local lastHttpPostHeaders = nil
local fakePreviewFiles = {}

_G._PLUGIN = {
    path = "AutoDevelopAI.lrplugin",
}

_G.import = function(name)
    if name == "LrPathUtils" then
        return {
            child = function(parent, child)
                return parent .. "/" .. child
            end,
        }
    end
    if name == "LrApplication" then
        return {
            activeCatalog = function()
                return {}
            end,
            developPresetFolders = function()
                return fakeDevelopPresetFolders
            end,
        }
    end
    if name == "LrProgressScope" then
        return function()
            return {}
        end
    end
    if name == "LrFileUtils" then
        return {
            readFile = function(path)
                return fakePreviewFiles[path]
            end,
        }
    end
    if name == "LrStringUtils" then
        return {
            encodeBase64 = function(value)
                return "encoded:" .. value
            end,
        }
    end
    if name == "LrExportSession" then
        return function()
            return {}
        end
    end
    if name == "LrPrefs" then
        return {
            prefsForPlugin = function()
                return fakePreferences
            end,
        }
    end
    if name == "LrDate" then
        return {
            currentTime = function()
                return 1000
            end,
        }
    end
    if name == "LrLogger" then
        return function()
            return {
                enable = function()
                end,
                error = function(_, message)
                    logged.error[#logged.error + 1] = message
                end,
                warn = function(_, message)
                    logged.warning[#logged.warning + 1] = message
                end,
                info = function(_, message)
                    logged.info[#logged.info + 1] = message
                end,
                debug = function(_, message)
                    logged.debug[#logged.debug + 1] = message
                end,
            }
        end
    end
    if name == "LrDialogs" then
        return {
            message = function(title, message, style)
                lastDialog = {
                    title = title,
                    message = message,
                    style = style,
                }
            end,
            presentModalDialog = function(options)
                lastModalDialogOptions = options
                if modalDialogMutator then
                    modalDialogMutator(options, lastPropertyTable)
                end
                return modalDialogResult
            end,
            stopModalWithResult = function(_, result)
                modalDialogResult = result
            end,
        }
    end
    if name == "LrBinding" then
        return {
            makePropertyTable = function()
                local properties = {
                    _observers = {},
                }
                function properties:addObserver(key, observer)
                    self._observers[key] = observer
                end
                lastPropertyTable = properties
                return properties
            end,
        }
    end
    if name == "LrFunctionContext" then
        return {
            callWithContext = function(_, fn)
                return fn({})
            end,
        }
    end
    if name == "LrView" then
        local factory = {}
        function factory:control_spacing()
            return 1
        end
        for _, method in ipairs({
            "column",
            "row",
            "static_text",
            "popup_menu",
            "checkbox",
            "push_button",
            "scrolled_view",
        }) do
            factory[method] = function(_, specification)
                return specification
            end
        end
        return {
            bind = function(key)
                return { key = key }
            end,
            osFactory = function()
                return factory
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
    if name == "LrHttp" then
        return {
            post = function(_, body, headers)
                lastHttpPostBody = body
                lastHttpPostHeaders = headers
                if fakeHttpResponder then
                    return fakeHttpResponder(body, headers)
                end
                return fakeHttpResponseBody, fakeHttpResponseHeaders
            end,
            get = function()
                return fakeHttpResponseBody, fakeHttpResponseHeaders
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

local ModuleLoader = require("ModuleLoader")
local Utils = ModuleLoader.load("lib/Utils.lua")
local Config = ModuleLoader.load("lib/Config.lua")
local Json = ModuleLoader.load("lib/Json.lua")
local Preferences = ModuleLoader.load("lib/Preferences.lua")
local StyleProfiles = ModuleLoader.load("lib/StyleProfiles.lua")
local StyleRunCoordinator =
    ModuleLoader.load("lib/RunSettingsCoordinator.lua")
local StyleSelectionDialog =
    ModuleLoader.load("dialogs/RunSettingsDialog.lua")
local ModelProfiles = ModuleLoader.load("lib/ModelProfiles.lua")
local PluginManagerController =
    ModuleLoader.load("lib/PluginManagerController.lua")
local ExifMapper = ModuleLoader.load("lib/ExifMapper.lua")
local RequestBuilder = ModuleLoader.load("lib/RequestBuilder.lua")
local PreviewTransport =
    ModuleLoader.load("lib/PreviewTransport.lua")
local Validation = ModuleLoader.load("lib/Validation.lua")
local BatchPolicy = ModuleLoader.load("lib/BatchPolicy.lua")
local BatchSummary = ModuleLoader.load("lib/BatchSummary.lua")
local ErrorClassifier = ModuleLoader.load("lib/ErrorClassifier.lua")
local ApiClient = ModuleLoader.load("lib/ApiClient.lua")
local ApplicationGate = ModuleLoader.load("lib/ApplicationGate.lua")
local BatchOperationRecorder =
    ModuleLoader.load("lib/BatchOperationRecorder.lua")
local ProgressTracker = ModuleLoader.load("lib/ProgressTracker.lua")
local Logger = ModuleLoader.load("lib/Logger.lua")
local ErrorDialog = ModuleLoader.load("dialogs/ErrorDialog.lua")
local AutoDevelopConfirmationDialog =
    ModuleLoader.load("dialogs/AutoDevelopConfirmationDialog.lua")
local AnalysisSummaryDialog =
    ModuleLoader.load("dialogs/AnalysisSummaryDialog.lua")
local ResultStore = ModuleLoader.load("lib/ResultStore.lua")
local DevelopSettingsMapper =
    ModuleLoader.load("lib/DevelopSettingsMapper.lua")
local CropMapper = ModuleLoader.load("lib/CropMapper.lua")
local DevelopModeMapper =
    ModuleLoader.load("lib/DevelopModeMapper.lua")
local PendingOperation = ModuleLoader.load("lib/PendingOperation.lua")
local ApplyService = ModuleLoader.load("lib/ApplyService.lua")
local DenoisePresetService =
    ModuleLoader.load("lib/DenoisePresetService.lua")
local Sha256 = ModuleLoader.load("lib/Sha256.lua")
local LearningPhotoIdentity =
    ModuleLoader.load("lib/LearningPhotoIdentity.lua")
local LearningSessionStore =
    ModuleLoader.load("lib/LearningSessionStore.lua")
local LearningClient = ModuleLoader.load("lib/LearningClient.lua")
local LearningBaselineService =
    ModuleLoader.load("lib/LearningBaselineService.lua")
local AutoDevelopCommand =
    ModuleLoader.load("lib/AutoDevelopCommand.lua")
local PendingOperationReview =
    ModuleLoader.load("lib/PendingOperationReview.lua")
local LearningFeedbackDialog =
    ModuleLoader.load("dialogs/LearningFeedbackDialog.lua")

local uprightMappings = {
    off = 0,
    auto = 1,
    full = 2,
    level = 3,
    vertical = 4,
}
for mode, rawValue in pairs(uprightMappings) do
    local encoded, encodeError = DevelopModeMapper.encodeUpright(mode)
    assertEqual(encoded, rawValue)
    assertTrue(encodeError == nil)
    local decoded = DevelopModeMapper.decodeUpright(rawValue)
    assertEqual(decoded.mode, mode)
    assertEqual(decoded.rawValue, rawValue)
    assertEqual(decoded.supported, true)
end
local unknownUpright = DevelopModeMapper.decodeUpright(99)
assertEqual(unknownUpright.mode, "unknown")
assertEqual(unknownUpright.rawValue, 99)
assertEqual(unknownUpright.supported, false)
local invalidUpright, invalidUprightError =
    DevelopModeMapper.encodeUpright("guided")
assertTrue(invalidUpright == nil)
assertEqual(invalidUprightError, "unknown_upright_mode")
local hdrOff = DevelopModeMapper.decodeHdr(0)
assertEqual(hdrOff.enabled, false)
assertEqual(hdrOff.rawValue, 0)
assertEqual(hdrOff.supported, true)
local hdrOn = DevelopModeMapper.decodeHdr(1)
assertEqual(hdrOn.enabled, true)
assertEqual(hdrOn.rawValue, 1)
assertEqual(hdrOn.supported, true)
local unknownHdr = DevelopModeMapper.decodeHdr(2)
assertTrue(unknownHdr.enabled == nil)
assertEqual(unknownHdr.rawValue, 2)
assertEqual(unknownHdr.supported, false)
assertEqual(DevelopModeMapper.encodeHdr(false), 0)
assertEqual(DevelopModeMapper.encodeHdr(true), 1)
local invalidHdr, invalidHdrError =
    DevelopModeMapper.encodeHdr("true")
assertTrue(invalidHdr == nil)
assertEqual(invalidHdrError, "invalid_hdr_enabled")

assertTrue(
    Utils == ModuleLoader.load("lib/Utils.lua"),
    "module loader must cache successful loads"
)
local unsafeLoadOk = pcall(ModuleLoader.load, "../outside.lua")
assertTrue(not unsafeLoadOk, "module loader must reject path traversal")

local function gateState(overrides)
    local state = {
        confirmationMode = "never",
        preparationCancelled = false,
        progressCancelled = false,
        terminalFailure = false,
        readyCount = 1,
    }
    for key, value in pairs(overrides or {}) do
        state[key] = value
    end
    return state
end

local neverReady = ApplicationGate.evaluate(gateState())
assertEqual(neverReady.shouldApply, true)
assertEqual(neverReady.reason, "ready")
assertEqual(neverReady.cancelled, false)
assertEqual(neverReady.terminalFailure, false)

local finalPhotoCancelled = ApplicationGate.evaluate(gateState({
    preparationCancelled = true,
}))
assertEqual(finalPhotoCancelled.shouldApply, false)
assertEqual(finalPhotoCancelled.reason, "cancelled")
assertEqual(finalPhotoCancelled.cancelled, true)
assertEqual(finalPhotoCancelled.terminalFailure, false)

local afterLoopCancelled = ApplicationGate.evaluate(gateState({
    progressCancelled = true,
}))
assertEqual(afterLoopCancelled.shouldApply, false)
assertEqual(afterLoopCancelled.reason, "cancelled")

local immediatelyBeforeApplyCancelled =
    ApplicationGate.evaluate(gateState({ progressCancelled = true }))
assertEqual(immediatelyBeforeApplyCancelled.shouldApply, false)

local confirmationDeclined = ApplicationGate.evaluate(gateState({
    confirmationMode = "always",
    confirmationAccepted = false,
}))
assertEqual(confirmationDeclined.shouldApply, false)
assertEqual(confirmationDeclined.reason, "confirmation_declined")
assertEqual(confirmationDeclined.cancelled, false)

local cancelledAfterConfirmation = ApplicationGate.evaluate(gateState({
    confirmationMode = "always",
    confirmationAccepted = true,
    progressCancelled = true,
}))
assertEqual(cancelledAfterConfirmation.shouldApply, false)
assertEqual(cancelledAfterConfirmation.reason, "cancelled")

local noOperations = ApplicationGate.evaluate(gateState({
    readyCount = 0,
}))
assertEqual(noOperations.shouldApply, false)
assertEqual(noOperations.reason, "no_operations")

local terminalBackend = ApplicationGate.evaluate(gateState({
    terminalFailure = true,
}))
assertEqual(terminalBackend.shouldApply, false)
assertEqual(terminalBackend.reason, "terminal_failure")
assertEqual(terminalBackend.cancelled, false)
assertEqual(terminalBackend.terminalFailure, true)

local invalidProfile = ApplicationGate.evaluate(gateState({
    confirmationMode = "always",
    terminalFailure = true,
}))
assertEqual(invalidProfile.shouldApply, false)
assertEqual(invalidProfile.reason, "terminal_failure")

local cancelledAndTerminal = ApplicationGate.evaluate(gateState({
    preparationCancelled = true,
    terminalFailure = true,
}))
assertEqual(cancelledAndTerminal.shouldApply, false)
assertEqual(cancelledAndTerminal.reason, "cancelled")
assertEqual(cancelledAndTerminal.cancelled, true)
assertEqual(cancelledAndTerminal.terminalFailure, false)

local cancelledSummary = { cancelled = false }
if finalPhotoCancelled.cancelled then
    cancelledSummary.cancelled = true
end
assertEqual(cancelledSummary.cancelled, true)

local rejectedApplyCalls = 0
if immediatelyBeforeApplyCancelled.shouldApply
    or cancelledAndTerminal.shouldApply then
    rejectedApplyCalls = rejectedApplyCalls + 1
end
assertEqual(rejectedApplyCalls, 0)

local function recordableOperation(filename)
    return {
        photo = {},
        filename = filename or "Ready.NEF",
        requestId = "12345678-1234-4abc-8abc-1234567890ab",
        originalSettings = {},
        mappedSettings = { Exposure2012 = 0 },
        applicationStatus = "pending",
    }
end

local recordedOperations = {}
local recordedOperation = recordableOperation()
assertEqual(
    BatchOperationRecorder.tryRecord({
        cancelled = false,
        terminalFailure = false,
        preparationResult = "ready",
        operation = recordedOperation,
        operations = recordedOperations,
    }),
    "recorded"
)
assertEqual(#recordedOperations, 1)
assertTrue(recordedOperations[1] == recordedOperation)

local function assertOperationRejected(state, expected)
    local operations = {}
    state.operations = operations
    local status = BatchOperationRecorder.tryRecord(state)
    assertEqual(status, expected)
    assertEqual(#operations, 0)
end

assertOperationRejected({
    preparationResult = "cancelled",
    operation = recordableOperation("Cancelled.NEF"),
}, "cancelled")
assertOperationRejected({
    cancelled = true,
    preparationResult = "ready",
    operation = recordableOperation("Late.NEF"),
}, "cancelled")
assertOperationRejected({
    terminalFailure = true,
    preparationResult = "ready",
    operation = recordableOperation("Terminal.NEF"),
}, "terminal_failure")
assertOperationRejected({
    preparationResult = "ready",
    operation = nil,
}, "invalid_operation")
assertOperationRejected({
    cancelled = true,
    preparationResult = "ready",
    operation = recordableOperation("Final-photo.NEF"),
}, "cancelled")

for _, identifier in ipairs({
    "gemma-4-31b",
    "qwen/qwen3-vl-32b-instruct",
    "local:gemma-4-31b",
    "local:gemma",
    "provider:model",
    "lmstudio:qwen/model",
    "ab:model",
    "model_v2.1",
    "vendor/model+quant",
}) do
    assertEqual(Validation.validateModelIdentifier(identifier), identifier)
end
for _, identifier in ipairs({
    "C:secret",
    "c:model",
    "Z:anything",
    "C:\\Users\\Name\\model",
    "C:\\secret",
    "C:/Users/Name/model",
    "C:/secret",
    "a:model",
    "/home/user/model",
    "https://user:pass@example.com/model?token=abc",
    "model?token=abc",
    "model name",
    "traceback\nline 1",
    "../../secret",
    "@model",
    "vendor//model",
    "local::model",
    string.rep("a", 129),
}) do
    assertTrue(Validation.validateModelIdentifier(identifier) == nil)
end

for _, unsafeValue in ipairs({
    "C:\\Users\\Person\\secret-preview.jpg",
    "/home/person/private/preview.jpg",
    "https://user:password@example.test/health",
    "https://example.test/api?token=secret",
    "stack traceback:\n\tprivate.lua:42",
}) do
    local code = Utils.safeErrorCode(unsafeValue, "unexpected_exception")
    assertEqual(code, "unexpected_exception")
    assertTrue(code:find(unsafeValue, 1, true) == nil)
    Logger.error(
        "operation=test category=internal_error code=" .. code
    )
    local logRecord = logged.error[#logged.error]
    assertTrue(logRecord:find(unsafeValue, 1, true) == nil)
end
assertEqual(
    Utils.safeErrorCode("apply_failed", "internal_error"),
    "apply_failed"
)

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
local rawFilenameFallback = photo({
    localIdentifier = 19,
    fileName = "Raw_Fallback.JPG",
}, {
    fileName = "",
})
local rawIdentity = Utils.capturePhotoIdentity(rawFilenameFallback)
assertEqual(rawIdentity.photoId, "photo_19")
assertEqual(rawIdentity.displayFilename, "Raw_Fallback.JPG")

local pathFallback = photo({
    localIdentifier = 20,
    fileName = "",
    path = "C:\\Photos\\Path_Fallback.DNG",
}, {
    fileName = "",
})
local pathIdentity = Utils.capturePhotoIdentity(pathFallback)
assertEqual(pathIdentity.photoId, "photo_20")
assertEqual(pathIdentity.displayFilename, "Path_Fallback.DNG")

local internalOnly = photo({
    localIdentifier = 283285,
    fileName = "",
}, {
    fileName = "",
})
local internalIdentity = Utils.capturePhotoIdentity(internalOnly)
assertEqual(internalIdentity.photoId, "photo_283285")
assertEqual(internalIdentity.displayFilename, "photo_283285")

local formattedReadCount = 0
local rawFilenameReadCount = 0
local capturedOncePhoto = {
    localIdentifier = 21,
    getFormattedMetadata = function(_, key)
        if key == "fileName" then
            formattedReadCount = formattedReadCount + 1
            return "Captured_Once.NEF"
        end
        return nil
    end,
    getRawMetadata = function(_, key)
        if key == "fileName" then
            rawFilenameReadCount = rawFilenameReadCount + 1
        end
        return nil
    end,
}
local capturedOnceIdentity =
    Utils.capturePhotoIdentity(capturedOncePhoto)
assertEqual(capturedOnceIdentity.displayFilename, "Captured_Once.NEF")
assertEqual(formattedReadCount, 1)
assertEqual(rawFilenameReadCount, 0)
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
    PerspectiveUpright = 4,
    HDREditMode = 0,
    HDRMaxValue = 2.3,
    UnsupportedSetting = 99,
    Tint = 0 / 0,
})
local exif = ExifMapper.mapExif(mappedPhoto)
assertEqual(exif.file_format, "RAW")
assertEqual(exif.camera, "Nikon Z 8")
assertEqual(exif.iso, 800)
assertTrue(exif.shutter_speed == nil, "missing EXIF must be omitted")
local stringIsoExif = ExifMapper.mapExif(photo({
    isoSpeedRating = "3600",
}))
assertEqual(stringIsoExif.iso, 3600)
local formattedIsoExif = ExifMapper.mapExif(photo({}, {
    isoSpeedRating = "ISO 3,600",
}))
assertEqual(formattedIsoExif.iso, 3600)
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

local denoisePreset50 = {
    getName = function()
        return "AutoDevelop AI - Denoise 50"
    end,
}
fakeDevelopPresetFolders = {
    {
        getDevelopPresets = function()
            return { denoisePreset50 }
        end,
    },
}
local denoiseSource = photo({
    localIdentifier = 70,
    fileName = "Denoise_Source.NEF",
    fileFormat = "RAW",
}, nil, {
    ColorNoiseReduction = 25,
    FilterList = {},
})
local denoiseCapability = DenoisePresetService.prepare(
    denoiseSource,
    denoiseSource:getDevelopSettings(),
    50
)
assertEqual(denoiseCapability.ready, true)
assertEqual(denoiseCapability.amount, 50)
assertTrue(denoiseCapability.preset == denoisePreset50)
assertEqual(
    denoiseCapability.presetName,
    "AutoDevelop AI - Denoise 50"
)
assertEqual(denoiseCapability.originalSettings.ColorNoiseReduction, 25)
assertTrue(type(denoiseCapability.originalSettings.FilterList) == "table")

local implicitEmptyDenoiseBaseline = DenoisePresetService.prepare(
    denoiseSource,
    { ColorNoiseReduction = 20 },
    50
)
assertEqual(implicitEmptyDenoiseBaseline.ready, true)
assertTrue(
    type(
        implicitEmptyDenoiseBaseline.originalSettings.FilterList
    ) == "table"
)
assertEqual(
    next(implicitEmptyDenoiseBaseline.originalSettings.FilterList),
    nil
)
assertEqual(
    implicitEmptyDenoiseBaseline.originalSettings.ColorNoiseReduction,
    20
)

local malformedDenoiseBaseline = DenoisePresetService.prepare(
    denoiseSource,
    { FilterList = "invalid" },
    50
)
assertEqual(malformedDenoiseBaseline.ready, false)
assertEqual(
    malformedDenoiseBaseline.code,
    "denoise_baseline_unavailable"
)

local missingDenoisePreset = DenoisePresetService.prepare(
    denoiseSource,
    denoiseSource:getDevelopSettings(),
    25
)
assertEqual(missingDenoisePreset.ready, false)
assertEqual(missingDenoisePreset.code, "denoise_preset_missing")

local jpegDenoise = DenoisePresetService.prepare(
    photo({ fileFormat = "JPEG", fileName = "not-raw.jpg" }),
    { FilterList = {} },
    50
)
assertEqual(jpegDenoise.ready, false)
assertEqual(jpegDenoise.code, "denoise_source_unsupported")

local alreadyDenoised = DenoisePresetService.prepare(
    denoiseSource,
    {
        FilterList = {
            Filters = { { Title = "Denoise" } },
        },
    },
    50
)
assertEqual(alreadyDenoised.ready, false)
assertEqual(alreadyDenoised.code, "denoise_already_enabled")
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
local learningState = ExifMapper.mapLearningDevelopState(mappedPhoto)
assertEqual(learningState.settings.Contrast2012, 12)
assertEqual(learningState.modes.upright, "vertical")
assertEqual(learningState.modes.hdr_enabled, false)
assertEqual(learningState.diagnostics.HDRMaxValue, 2.3)
assertTrue(learningState.settings.HDRMaxValue == nil)
local filteredLearningSettings = ExifMapper.filterLearningSettings({
    Exposure2012 = 0.4,
    EnableTransform = true,
    PerspectiveUpright = 2,
    HDREditMode = 1,
})
assertEqual(filteredLearningSettings.Exposure2012, 0.4)
assertTrue(filteredLearningSettings.EnableTransform == nil)
assertTrue(filteredLearningSettings.PerspectiveUpright == nil)
assertTrue(filteredLearningSettings.HDREditMode == nil)
local manuallyEditedValues = {
    Contrast2012 = 25,
    Clarity2012 = 32,
    Dehaze = 18,
    Vibrance = 38,
}
local manuallyEditedPhoto = photo({
    localIdentifier = 70,
    fileName = "Manual_Edit.NEF",
    fileFormat = "RAW",
}, nil, manuallyEditedValues)
local currentFeedbackSettings =
    ExifMapper.mapDevelopSettings(manuallyEditedPhoto)
assertEqual(currentFeedbackSettings.Contrast2012, 25)
assertEqual(currentFeedbackSettings.Clarity2012, 32)
assertEqual(currentFeedbackSettings.Dehaze, 18)
assertEqual(currentFeedbackSettings.Vibrance, 38)

fakeHttpResponseBody = assert(Json.encode({
    schema_version = 1,
    session_id = "11111111-1111-4111-8111-111111111111",
    has_significant_changes = true,
    accepted_without_change = false,
    significant_changes = {
        Contrast2012 = {
            baseline = 12,
            current = 25,
            delta = 13,
            threshold = 2,
            significant = true,
        },
        Clarity2012 = {
            baseline = 18,
            current = 32,
            delta = 14,
            threshold = 2,
            significant = true,
        },
        Dehaze = {
            baseline = 6,
            current = 18,
            delta = 12,
            threshold = 1,
            significant = true,
        },
        Vibrance = {
            baseline = 18,
            current = 38,
            delta = 20,
            threshold = 2,
            significant = true,
        },
    },
    ignored_changes = {},
    crop_changes = {},
    leveling_changes = {},
    mode_changes = {
        upright = "vertical",
        hdr_enabled = true,
    },
}))
local previewResult = LearningClient.previewFeedback({
    schema_version = 1,
    session_id = "11111111-1111-4111-8111-111111111111",
    photo_key = string.rep("a", 64),
    final_settings = currentFeedbackSettings,
}, {
    baseUrl = "http://127.0.0.1:8005",
    timeoutSeconds = 120,
})
assertTrue(previewResult.ok)
assertEqual(previewResult.significantChanges.Contrast2012.delta, 13)
assertEqual(previewResult.significantChanges.Clarity2012.delta, 14)
assertEqual(previewResult.significantChanges.Dehaze.delta, 12)
assertEqual(previewResult.significantChanges.Vibrance.delta, 20)
assertEqual(previewResult.modeChanges.upright, "vertical")
assertEqual(previewResult.modeChanges.hdr_enabled, true)
local postedPreview = assert(Json.decode(lastHttpPostBody))
assertEqual(postedPreview.final_settings.Contrast2012, 25)
assertEqual(postedPreview.final_settings.Clarity2012, 32)
assertEqual(postedPreview.final_settings.Dehaze, 18)
assertEqual(postedPreview.final_settings.Vibrance, 38)
assertTrue(postedPreview.final_settings.Contrast == nil)
assertTrue(postedPreview.final_settings.Clarity == nil)
assertTrue(type(postedPreview.final_modes) == "table")

local request = assert(RequestBuilder.build(
    mappedPhoto,
    "cHJldmlldy1ieXRlcw==",
    {
        styleProfileId = "natural_travel",
        modelProfileId = "gemma",
        uuidFactory = function()
            return "12345678-1234-4abc-8abc-1234567890ab"
        end,
    }
))
assertEqual(request.schema_version, "1.0")
assertEqual(request.options.style_profile, "natural_travel")
assertEqual(request.model, "gemma")
assertEqual(request.current_settings.Exposure2012, 0)
assertEqual(request.preview_base64, "cHJldmlldy1ieXRlcw==")
assertTrue(request.preview_path == nil)
assertEqual(StyleProfiles.getDefaultId(), "auto")
assertTrue(
    RequestBuilder.build(mappedPhoto, "cHJldmlldw==", {
        uuidFactory = function()
            return "12345678-1234-4abc-8abc-1234567890ab"
        end,
    }) == nil,
    "request building must require an explicit style"
)
fakePreferences.styleProfileId = nil
assertEqual(
    Preferences.getStyleProfileId(),
    StyleProfiles.getDefaultId()
)
fakePreferences.styleProfileId = "architecture"
assertEqual(Preferences.getStyleProfileId(), "architecture")

local configured = assert(RequestBuilder.build(
    mappedPhoto,
    "Y29uZmlndXJlZC1wcmV2aWV3",
    {
        styleProfileId = "architecture",
        modelProfileId = "qwen",
        uuidFactory = function()
            return "22345678-1234-4abc-8abc-1234567890ab"
        end,
    }
))
assertEqual(configured.options.style_profile, "architecture")
assertEqual(configured.model, "qwen")

local developRequest = assert(RequestBuilder.buildDevelop(
    mappedPhoto,
    "ZGV2ZWxvcC1wcmV2aWV3",
    {
        styleProfileId = "portrait",
        modelProfileId = "gpt_oss",
        includeCrop = true,
        includeDenoise = true,
        uuidFactory = function()
            return "33345678-1234-4abc-8abc-1234567890ab"
        end,
    }
))
assertEqual(developRequest.options.style_profile, "portrait")
assertEqual(developRequest.model, "gpt_oss")
assertEqual(developRequest.options.include_crop, true)
assertEqual(developRequest.options.include_denoise, true)
assertEqual(developRequest.options.dry_run, false)
assertEqual(developRequest.options.preserve_current_adjustments, true)
assertEqual(developRequest.options.hdr_edit_supported, true)
assertEqual(developRequest.options.hdr_workflow, "unknown")
assertEqual(developRequest.preview_base64, "ZGV2ZWxvcC1wcmV2aWV3")
assertTrue(developRequest.preview_path == nil)
assertTrue(
    RequestBuilder.buildDevelop(mappedPhoto, "", {
        styleProfileId = "portrait",
        modelProfileId = "gpt_oss",
    }) == nil,
    "request building must reject missing preview content"
)
fakePreviewFiles["D:\\Temp\\transport-preview.jpg"] = "jpeg-bytes"
local encodedPreview, encodedError, encodedDiagnostics =
    PreviewTransport.encodeFile("D:\\Temp\\transport-preview.jpg")
assertEqual(encodedPreview, "encoded:jpeg-bytes")
assertTrue(encodedError == nil)
assertEqual(encodedDiagnostics.rawBytes, 10)
assertEqual(encodedDiagnostics.encodedBytes, 18)
assertEqual(PreviewTransport.estimatedBase64Bytes(1), 4)
assertEqual(PreviewTransport.estimatedBase64Bytes(2), 4)
assertEqual(PreviewTransport.estimatedBase64Bytes(3), 4)
assertEqual(PreviewTransport.estimatedBase64Bytes(4), 8)
local missingEncoded, missingEncodeError =
    PreviewTransport.encodeFile("D:\\Temp\\missing-preview.jpg")
assertTrue(missingEncoded == nil)
assertEqual(missingEncodeError, "preview_read_failed")
assertEqual(Config.apiPaths.develop, "/autodevelop/v1/develop")
assertEqual(Config.defaults.backendBaseUrl, "http://127.0.0.1:8005")
assertEqual(Config.defaults.learningShowSummary, true)
assertEqual(Config.SCHEMA_VERSION, "1.0")
fakePreferences.backendBaseUrl = nil
fakePreferences.styleProfileId = nil
fakePreferences.modelProfileId = nil
fakePreferences.requestTimeoutSeconds = nil
fakePreferences.applyCrop = false
fakePreferences.applyCompositionCrop = nil
fakePreferences.applyLeveling = nil
fakePreferences.confirmationMode = nil
fakePreferences.loggingLevel = nil
assertEqual(
    Preferences.getBackendBaseUrl(),
    "http://127.0.0.1:8005"
)
assertEqual(Preferences.getStyleProfileId(), "auto")
assertEqual(Preferences.getRequestTimeoutSeconds(), 120)
Preferences.initializeDefaults()
assertEqual(Preferences.getApplyCompositionCrop(), false)
assertEqual(Preferences.getApplyLeveling(), false)
assertEqual(Preferences.getConfirmationMode(), "always")
assertEqual(Preferences.getLoggingLevel(), "info")
fakePreferences.applyCrop = nil
fakePreferences.applyCompositionCrop = nil
fakePreferences.applyLeveling = nil
Preferences.initializeDefaults()
assertEqual(Preferences.getApplyCompositionCrop(), true)
assertEqual(Preferences.getApplyLeveling(), true)

local normalizedUrl = assert(Preferences.set(
    "backendBaseUrl",
    "  HTTP://127.0.0.1:8005///  "
))
assertEqual(normalizedUrl, "HTTP://127.0.0.1:8005")
local lastValidUrl = fakePreferences.backendBaseUrl
local invalidUrl, invalidUrlReason =
    Preferences.set("backendBaseUrl", "ftp://127.0.0.1")
assertTrue(invalidUrl == nil)
assertTrue(type(invalidUrlReason) == "string")
assertEqual(fakePreferences.backendBaseUrl, lastValidUrl)
assertEqual(
    Preferences.set("backendBaseUrl", "https://autodevelop.example.com/"),
    "https://autodevelop.example.com"
)
assertTrue(Preferences.set("backendBaseUrl", "   ") == nil)
assertTrue(Preferences.set("backendBaseUrl", "127.0.0.1:8005") == nil)
assertTrue(Preferences.set("backendBaseUrl", "ftp://127.0.0.1") == nil)
assertTrue(Preferences.set(
    "backendBaseUrl",
    "http://127.0.0.1:8005/autodevelop/v1"
) == nil)
assertTrue(Preferences.set("requestTimeoutSeconds", 10) ~= nil)
assertTrue(Preferences.set("requestTimeoutSeconds", 600) ~= nil)
assertTrue(Preferences.set("requestTimeoutSeconds", 9) == nil)
assertTrue(Preferences.set("requestTimeoutSeconds", 601) == nil)
assertTrue(Preferences.set("requestTimeoutSeconds", 10.5) == nil)
assertTrue(Preferences.set("requestTimeoutSeconds", "120") == nil)
for _, choice in ipairs(Preferences.getStyleProfileChoices()) do
    assertEqual(
        Preferences.set("styleProfileId", choice.value),
        choice.value
    )
end
assertTrue(Preferences.set("styleProfileId", "unknown") == nil)
assertEqual(Preferences.set("confirmationMode", "never"), "never")
assertTrue(Preferences.set("confirmationMode", "sometimes") == nil)
for _, level in ipairs({ "error", "warning", "info", "debug" }) do
    assertEqual(Preferences.set("loggingLevel", level), level)
end
assertTrue(Preferences.set("loggingLevel", "trace") == nil)
fakePreferences.loggingLevel = "invalid"
assertEqual(Preferences.getRuntimeLoggingLevel(), "info")
assertEqual(fakePreferences.loggingLevel, "invalid")
fakePreferences.loggingLevel = "info"
local defaults = Preferences.resetDefaults()
assertEqual(defaults.backendBaseUrl, "http://127.0.0.1:8005")
assertEqual(defaults.styleProfileId, "natural_travel")
assertEqual(defaults.requestTimeoutSeconds, 120)
assertEqual(defaults.applyCompositionCrop, true)
assertEqual(defaults.applyLeveling, true)
assertEqual(defaults.confirmationMode, "always")
assertEqual(defaults.loggingLevel, "info")

local profileChoices = Preferences.getStyleProfileChoices()
assertEqual(#profileChoices, 8)
assertEqual(profileChoices[1].title, "Auto")
assertEqual(profileChoices[1].value, "auto")
assertEqual(profileChoices[2].value, "natural_travel")
assertEqual(profileChoices[3].value, "landscape_impact")
assertEqual(profileChoices[4].value, "architecture")
assertEqual(profileChoices[5].value, "stock_neutral")
assertEqual(profileChoices[6].value, "portrait")
assertEqual(profileChoices[7].value, "night")
assertEqual(profileChoices[8].value, "documentary")
profileChoices[1].title = "Mutated"
assertEqual(
    Preferences.getStyleProfileChoices()[1].title,
    "Auto",
    "choice getters must return defensive copies"
)

assertEqual(StyleProfiles.getDefaultId(), "auto")
assertEqual(StyleProfiles.getDisplayName("documentary"), "Documentary")
assertTrue(StyleProfiles.getDescription("documentary") ~= nil)
assertTrue(StyleProfiles.isValidId("architecture"))
assertTrue(not StyleProfiles.isValidId("unknown"))
assertTrue(StyleProfiles.getById("unknown") == nil)
local initialStyle, invalidStored =
    StyleProfiles.resolveInitialSelection("portrait")
assertEqual(initialStyle, "portrait")
assertEqual(invalidStored, false)
initialStyle, invalidStored =
    StyleProfiles.resolveInitialSelection("removed_profile")
assertEqual(initialStyle, "auto")
assertEqual(invalidStored, true)
local copiedStyle = StyleProfiles.getById("natural_travel")
copiedStyle.displayName = "Mutated"
assertEqual(
    StyleProfiles.getDisplayName("natural_travel"),
    "Natural Travel",
    "style metadata getters must return defensive copies"
)
local modelChoices = ModelProfiles.getChoices()
assertEqual(#modelChoices, 5)
assertEqual(modelChoices[1].value, "gemma")
assertEqual(modelChoices[5].value, "claude")
assertEqual(#ModelProfiles.getSelectableChoices(), 4)
assertEqual(ModelProfiles.getDefaultId(), "gemma")
assertTrue(ModelProfiles.isSelectableId("gemma"))
assertTrue(not ModelProfiles.isSelectableId("claude"))
local copiedModel = ModelProfiles.getById("gemma")
copiedModel.displayName = "Mutated"
assertEqual(ModelProfiles.getDisplayName("gemma"), "Gemma")

fakePreferences.styleProfileId = "natural_travel"
modalDialogResult = "cancel"
modalDialogMutator = nil
local cancelledDialogResult =
    StyleSelectionDialog.show("natural_travel", "gemma")
assertEqual(cancelledDialogResult.confirmed, false)
assertEqual(fakePreferences.styleProfileId, "natural_travel")

modalDialogResult = "ok"
modalDialogMutator = function(_, properties)
    properties.selectedProfileId = "documentary"
    properties._observers.selectedProfileId()
    properties.selectedModelId = "qwen"
    properties._observers.selectedModelId()
    properties.rememberProfileAsDefault = false
    properties.rememberModelAsDefault = false
end
local documentaryDialogResult =
    StyleSelectionDialog.show("natural_travel", "gemma")
assertEqual(documentaryDialogResult.confirmed, true)
assertEqual(documentaryDialogResult.profileId, "documentary")
assertEqual(documentaryDialogResult.modelId, "qwen")
assertEqual(documentaryDialogResult.rememberProfileAsDefault, false)
assertEqual(documentaryDialogResult.rememberModelAsDefault, false)
assertEqual(
    lastPropertyTable.selectedDescription,
    StyleProfiles.getDescription("documentary")
)
assertEqual(
    fakePreferences.styleProfileId,
    "natural_travel",
    "per-run selection must not persist when remember is off"
)

modalDialogMutator = function(_, properties)
    properties.selectedProfileId = "architecture"
    properties._observers.selectedProfileId()
    properties.rememberProfileAsDefault = true
    properties.rememberModelAsDefault = true
end
local rememberedDialogResult =
    StyleSelectionDialog.show("natural_travel", "gemma")
assertEqual(rememberedDialogResult.profileId, "architecture")
assertEqual(rememberedDialogResult.rememberProfileAsDefault, true)
assertEqual(rememberedDialogResult.rememberModelAsDefault, true)
assertEqual(
    fakePreferences.styleProfileId,
    "natural_travel",
    "the UI-only dialog must not persist preferences"
)

modalDialogMutator = function(_, properties)
    properties.selectedProfileId = "documentary"
    properties._observers.selectedProfileId()
end
modalDialogResult = "cancel"
StyleSelectionDialog.show("removed_profile", "removed_model")
assertEqual(lastPropertyTable.selectedProfileId, "documentary")
assertTrue(lastPropertyTable.invalidStoredProfileMessage ~= "")
assertTrue(
    lastPropertyTable.invalidStoredProfileMessage:find(
        "Choose a style for this run.",
        1,
        true
    ) ~= nil,
    "invalid-profile notice must remain accurate after selection changes"
)
assertTrue(
    lastPropertyTable.invalidStoredProfileMessage:find(
        "Natural Travel is selected",
        1,
        true
    ) == nil,
    "invalid-profile notice must not claim a stale selection"
)
assertEqual(
    fakePreferences.styleProfileId,
    "natural_travel",
    "invalid stored profile fallback must not persist silently"
)
modalDialogMutator = nil
modalDialogResult = "ok"

local function beginStyleRun(dialogResult, persistDefault, snapshotFactory)
    if dialogResult.confirmed and dialogResult.modelId == nil then
        dialogResult.modelId = "gemma"
    end
    return StyleRunCoordinator.begin({
        dialogResult = dialogResult,
        validateProfile = StyleProfiles.isValidId,
        validateModel = ModelProfiles.isSelectableId,
        persistProfileDefault = persistDefault or function()
            return true
        end,
        persistModelDefault = function()
            return true
        end,
        snapshotFactory = snapshotFactory or function(profileId, modelId)
            return {
                styleProfileId = profileId,
                modelProfileId = modelId,
                backendBaseUrl = "http://127.0.0.1:8005",
            }
        end,
    })
end

local analyzePreparationCalls = 0
local analyzeCancelled = beginStyleRun({
    confirmed = false,
})
local analyzeCancelPreparation = StyleRunCoordinator.prepare(
    analyzeCancelled,
    { "analyze-photo" },
    function()
        analyzePreparationCalls = analyzePreparationCalls + 1
        return true
    end
)
assertEqual(analyzeCancelled.status, "cancelled")
assertEqual(analyzeCancelPreparation.status, "cancelled")
assertEqual(analyzePreparationCalls, 0)

local developPreparationCalls = 0
local developCancelled = beginStyleRun({
    confirmed = false,
})
StyleRunCoordinator.prepare(
    developCancelled,
    { "develop-photo" },
    function()
        developPreparationCalls = developPreparationCalls + 1
        return true
    end
)
assertEqual(developPreparationCalls, 0)

local persistedProfiles = {}
local documentaryRun = beginStyleRun(
    {
        confirmed = true,
        profileId = "documentary",
        modelId = "qwen",
        rememberProfileAsDefault = false,
        rememberModelAsDefault = false,
    },
    function(profileId)
        persistedProfiles[#persistedProfiles + 1] = profileId
        return true
    end,
    function()
        return {
            styleProfileId = "night",
            backendBaseUrl = "http://127.0.0.1:8005",
        }
    end
)
assertEqual(documentaryRun.status, "ready")
assertEqual(#persistedProfiles, 0)
local receivedProfiles = {}
local receivedModels = {}
local photos = { "one", "two", "three" }
local documentaryPreparation = StyleRunCoordinator.prepare(
    documentaryRun,
    photos,
    function(runPhotos, snapshot)
        for index = 1, #runPhotos do
            receivedProfiles[index] = snapshot.styleProfileId
            receivedModels[index] = snapshot.modelProfileId
        end
        snapshot.styleProfileId = "mutated"
        return #runPhotos
    end
)
assertEqual(documentaryPreparation.status, "completed")
assertEqual(documentaryPreparation.prepared, 3)
for index = 1, #photos do
    assertEqual(receivedProfiles[index], "documentary")
    assertEqual(receivedModels[index], "qwen")
end
assertEqual(
    StyleRunCoordinator.getSnapshot(documentaryRun).styleProfileId,
    "documentary",
    "preparation callback must not mutate the run snapshot"
)

local invalidPreparationCalls = 0
local invalidRun = beginStyleRun({
    confirmed = true,
    profileId = "unknown",
})
StyleRunCoordinator.prepare(
    invalidRun,
    { "photo" },
    function()
        invalidPreparationCalls = invalidPreparationCalls + 1
        return true
    end
)
assertEqual(invalidRun.status, "invalid_profile")
assertEqual(invalidPreparationCalls, 0)

local rememberCalls = 0
local rememberedRun = beginStyleRun(
    {
        confirmed = true,
        profileId = "architecture",
        modelId = "gemma",
        rememberProfileAsDefault = true,
    },
    function(profileId)
        rememberCalls = rememberCalls + 1
        assertEqual(profileId, "architecture")
        return true
    end
)
assertEqual(rememberedRun.status, "ready")
assertEqual(rememberCalls, 1)

local emptyPreparationCalls = 0
local emptyResult = StyleRunCoordinator.prepare(
    documentaryRun,
    {},
    function()
        emptyPreparationCalls = emptyPreparationCalls + 1
        return true
    end
)
assertEqual(emptyResult.status, "empty")
assertEqual(emptyResult.photoCount, 0)
assertEqual(emptyPreparationCalls, 0)

local failedPreparation = StyleRunCoordinator.prepare(
    documentaryRun,
    { "photo" },
    function()
        return nil, "private preparation detail"
    end
)
assertEqual(failedPreparation.status, "preparation_failed")
assertTrue(
    failedPreparation.failure == nil,
    "raw preparation failure must not be retained"
)

local confirmationChoices = Preferences.getConfirmationChoices()
assertEqual(#confirmationChoices, 2)
assertEqual(confirmationChoices[1].title, "Always")
assertEqual(confirmationChoices[1].value, "always")
assertEqual(confirmationChoices[2].title, "Never")
assertEqual(confirmationChoices[2].value, "never")

local loggingChoices = Preferences.getLoggingChoices()
assertEqual(#loggingChoices, 4)
assertEqual(loggingChoices[1].title, "Error")
assertEqual(loggingChoices[1].value, "error")
assertEqual(loggingChoices[2].title, "Warning")
assertEqual(loggingChoices[2].value, "warning")
assertEqual(loggingChoices[3].title, "Info")
assertEqual(loggingChoices[3].value, "info")
assertEqual(loggingChoices[4].title, "Debug")
assertEqual(loggingChoices[4].value, "debug")

for _, text in ipairs({ "100", "120", "600" }) do
    assertEqual(
        Preferences.validateRequestTimeoutText(text),
        tonumber(text)
    )
end
for _, text in ipairs({
    "",
    "9",
    "601",
    "10.5",
    "1 20",
    " 120 ",
    "NaN",
    "Infinity",
}) do
    assertTrue(Preferences.validateRequestTimeoutText(text) == nil)
end

local managerProperties = {}
PluginManagerController.populate(managerProperties)
assertEqual(managerProperties.backendBaseUrl, defaults.backendBaseUrl)
assertEqual(managerProperties.styleProfileId, defaults.styleProfileId)
assertEqual(managerProperties.requestTimeoutText, "120")
assertEqual(
    managerProperties.applyCompositionCrop,
    defaults.applyCompositionCrop
)
assertEqual(managerProperties.applyLeveling, defaults.applyLeveling)
assertEqual(
    managerProperties.confirmationMode,
    defaults.confirmationMode
)
assertEqual(managerProperties.loggingLevel, defaults.loggingLevel)
assertEqual(managerProperties.connectionState, "idle")
assertEqual(managerProperties.connectionStatusText, "Not tested")
assertEqual(managerProperties.connectionTestRunning, false)
assertEqual(managerProperties.canTestConnection, true)
assertEqual(managerProperties.validationMessage, "")

managerProperties.requestTimeoutText = "601"
local invalidManagerSettings =
    PluginManagerController.validateAndSave(managerProperties)
assertTrue(invalidManagerSettings == nil)
assertEqual(
    fakePreferences.requestTimeoutSeconds,
    120,
    "invalid timeout text must preserve the stored timeout"
)
managerProperties.requestTimeoutText = "120"
local validManagerSettings =
    assert(PluginManagerController.validateAndSave(managerProperties))
assertEqual(validManagerSettings.requestTimeoutSeconds, 120)

local connectedOutcome =
    PluginManagerController.classifyConnectionResult(
        true,
        { ok = true }
    )
assertEqual(connectedOutcome.state, "connected")
assertEqual(connectedOutcome.text, "Connected")
local stoppedOutcome =
    PluginManagerController.classifyConnectionResult(
        true,
        { ok = false, category = "backend_not_running" }
    )
assertEqual(stoppedOutcome.state, "backend_not_running")
assertEqual(stoppedOutcome.text, "Backend not running")
local timeoutOutcome =
    PluginManagerController.classifyConnectionResult(
        true,
        { ok = false, category = "model_timeout" }
    )
assertEqual(timeoutOutcome.state, "timeout")
assertEqual(timeoutOutcome.text, "Timed out")
local invalidResponseOutcome =
    PluginManagerController.classifyConnectionResult(
        true,
        { ok = false, category = "invalid_response" }
    )
assertEqual(invalidResponseOutcome.state, "invalid_response")
assertEqual(invalidResponseOutcome.text, "Invalid response")
local networkOutcome =
    PluginManagerController.classifyConnectionResult(
        true,
        { ok = false, category = "network_error" }
    )
assertEqual(networkOutcome.state, "network_error")
assertEqual(networkOutcome.text, "Network error")
local internalOutcome =
    PluginManagerController.classifyConnectionResult(false, nil)
assertEqual(internalOutcome.state, "internal_error")
assertTrue(internalOutcome.text:find("failed safely", 1, true) ~= nil)

fakePreferences.loggingLevel = "error"
Logger.info("suppressed info")
Logger.error("visible error")
assertEqual(#logged.info, 0)
assertEqual(#logged.error, 1)
fakePreferences.loggingLevel = "debug"
Logger.debug("safe debug event")
assertEqual(#logged.debug, 1)
assertTrue(logged.debug[1]:find("preview_path", 1, true) == nil)
fakePreferences.loggingLevel = "info"

local successfulResponse = {
    status = "success",
    schema_version = "1.0",
    request_id = request.request_id,
    filename = request.filename,
    analysis = {},
    edit_plan = { style_profile = "natural_travel" },
    requested_style_id = "natural_travel",
    effective_style_id = "natural_travel",
    style_selection_mode = "manual",
    style_selection_reason = "Manual style override",
    editing_intensity = "moderate",
    scene_confidence = 0.9,
    leveling = {
        recommended = false,
        angle = 0,
        mode = "none",
    },
    model = "gemma",
    resolved_model = "fake-autodevelop-v1",
}
assertTrue(Validation.validateAnalyzeResponse(successfulResponse, request))
local invalidAnalyzeModel = Utils.deepCopy(successfulResponse)
invalidAnalyzeModel.model =
    "https://user:pass@example.com/model?token=secret"
assertTrue(
    not Validation.validateAnalyzeResponse(invalidAnalyzeModel, request)
)
local autoAnalyzeRequest = Utils.deepCopy(request)
autoAnalyzeRequest.options.style_profile = "auto"
local autoAnalyzeResponse = Utils.deepCopy(successfulResponse)
autoAnalyzeResponse.requested_style_id = "auto"
autoAnalyzeResponse.effective_style_id = "architecture"
autoAnalyzeResponse.style_selection_mode = "auto"
autoAnalyzeResponse.style_selection_reason = "Architectural study"
autoAnalyzeResponse.editing_intensity = "moderate"
autoAnalyzeResponse.edit_plan.style_profile = "architecture"
assertTrue(
    Validation.validateAnalyzeResponse(
        autoAnalyzeResponse,
        autoAnalyzeRequest
    )
)
local unsupportedEffectiveStyle = Utils.deepCopy(autoAnalyzeResponse)
unsupportedEffectiveStyle.effective_style_id = "provider_invented"
unsupportedEffectiveStyle.edit_plan.style_profile = "provider_invented"
assertTrue(
    not Validation.validateAnalyzeResponse(
        unsupportedEffectiveStyle,
        autoAnalyzeRequest
    )
)

local cancelledDialogSummary = BatchSummary.new(1, "develop")
cancelledDialogSummary.cancelled = true
cancelledDialogSummary.profileId = "natural_travel"
cancelledDialogSummary.confirmationMode = "never"
cancelledDialogSummary.terminalCategory =
    ErrorClassifier.codes.backendNotRunning
cancelledDialogSummary.models = {
    ["vendor/model+quant"] = true,
    ["https://user:password@example.com/model?token=secret"] = true,
}
cancelledDialogSummary.examples = {}
lastDialog = nil
AutoDevelopConfirmationDialog.showFinal(
    cancelledDialogSummary,
    {
        applied = 0,
        notApplied = 0,
        userCancelled = true,
    }
)
assertTrue(lastDialog ~= nil)
assertTrue(lastDialog.message:find("vendor/model+quant", 1, true) ~= nil)
assertTrue(lastDialog.message:find("user:password", 1, true) == nil)
assertTrue(lastDialog.message:find("token=secret", 1, true) == nil)
assertTrue(
    lastDialog.message:find(
        "Could not connect to the AutoDevelop AI backend.",
        1,
        true
    ) == nil
)

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
    edit_plan = { style_profile = "portrait" },
    requested_style_id = "portrait",
    effective_style_id = "portrait",
    style_selection_mode = "manual",
    style_selection_reason = "Manual style override",
    editing_intensity = "conservative",
    scene_confidence = Json.null,
    model = "gpt_oss",
    resolved_model = "fake-autodevelop-v1",
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
        confidence = 0.9,
    },
    leveling = {
        recommended = false,
        angle = 0,
        mode = "none",
    },
    denoise = {
        recommended = true,
        amount = 20,
        confidence = 0.9,
    },
    upright = {
        recommended = false,
        mode = "off",
        confidence = 0,
        reason = Json.null,
    },
    enable_hdr = {
        recommended = false,
        enabled = false,
        confidence = 0,
        reason = Json.null,
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
local developLearning = Utils.deepCopy(developResponse)
developLearning.learning = {
    enabled = true,
    personalization_applied = false,
    usable_sample_count = 2,
    retrieved_sample_count = 0,
    minimum_sample_count = 3,
    average_similarity = Json.null,
    feature_type = "local_color_luminance",
    reason = "insufficient_samples",
}
assertTrue(
    Validation.validateDevelopResponse(developLearning, developRequest)
)
local developFractionalLearningCount = Utils.deepCopy(developLearning)
developFractionalLearningCount.learning.usable_sample_count = 1.5
assertTrue(
    not Validation.validateDevelopResponse(
        developFractionalLearningCount,
        developRequest
    )
)
local developInfiniteLearningCount = Utils.deepCopy(developLearning)
developInfiniteLearningCount.learning.retrieved_sample_count = math.huge
assertTrue(
    not Validation.validateDevelopResponse(
        developInfiniteLearningCount,
        developRequest
    )
)
local developInvalidLearningMinimum = Utils.deepCopy(developLearning)
developInvalidLearningMinimum.learning.minimum_sample_count = 0
assertTrue(
    not Validation.validateDevelopResponse(
        developInvalidLearningMinimum,
        developRequest
    )
)
local developInvalidLearningSimilarity = Utils.deepCopy(developLearning)
developInvalidLearningSimilarity.learning.average_similarity = 1.01
assertTrue(
    not Validation.validateDevelopResponse(
        developInvalidLearningSimilarity,
        developRequest
    )
)
local developUnknownLearningReason = Utils.deepCopy(developLearning)
developUnknownLearningReason.learning.reason = "private_provider_detail"
assertTrue(
    not Validation.validateDevelopResponse(
        developUnknownLearningReason,
        developRequest
    )
)

local developMissingHdr = Utils.deepCopy(developResponse)
developMissingHdr.enable_hdr = nil
assertTrue(
    not Validation.validateDevelopResponse(developMissingHdr, developRequest)
)
local developInvalidHdrReason = Utils.deepCopy(developResponse)
developInvalidHdrReason.enable_hdr.reason = 123
assertTrue(
    not Validation.validateDevelopResponse(
        developInvalidHdrReason,
        developRequest
    )
)
local developInvalidHdrFlag = Utils.deepCopy(developResponse)
developInvalidHdrFlag.enable_hdr.recommended = 1
assertTrue(
    not Validation.validateDevelopResponse(
        developInvalidHdrFlag,
        developRequest
    )
)
local developInvalidUpright = Utils.deepCopy(developResponse)
developInvalidUpright.upright.mode = "guided"
assertTrue(
    not Validation.validateDevelopResponse(
        developInvalidUpright,
        developRequest
    )
)

local fixtureFile = assert(io.open(
    "tests/fixtures/develop_response.json",
    "rb"
))
local fixtureJson = fixtureFile:read("*a")
fixtureFile:close()
local wireDevelopResponse = assert(Json.decode(fixtureJson))
local wireDevelopRequest = Utils.deepCopy(developRequest)
wireDevelopRequest.options.style_profile = "natural_travel"
local wireValid, wireValidationError, wireModel =
    Validation.validateDevelopResponse(
        wireDevelopResponse,
        wireDevelopRequest
    )
assertTrue(wireValid, wireValidationError)
assertEqual(wireModel, "gpt_oss")
assertEqual(#wireDevelopResponse.warnings, 0)
assertEqual(wireDevelopResponse.crop.recommended, false)
assertTrue(wireDevelopResponse.crop.left == nil)
assertEqual(wireDevelopResponse.denoise.recommended, false)
assertTrue(wireDevelopResponse.denoise.amount == nil)

local wireCurrentSettings = {
    Exposure2012 = 0,
    Contrast2012 = 0,
    Highlights2012 = 0,
    Shadows2012 = 0,
    Whites2012 = 0,
    Blacks2012 = 0,
    Texture = 0,
    Clarity2012 = 0,
    Dehaze = 0,
    Vibrance = 0,
    Saturation = 0,
    Temperature = 5500,
    Tint = 0,
    CropLeft = 0,
    CropRight = 1,
    CropTop = 0,
    CropBottom = 1,
    CropAngle = 0,
}
local wireMappedSettings = DevelopSettingsMapper.map(
    wireDevelopResponse.develop_settings,
    wireCurrentSettings
)
assertEqual(wireMappedSettings.Exposure2012, 0)
assertEqual(wireMappedSettings.Highlights2012, -5)
assertEqual(wireMappedSettings.Vibrance, 3)
assertTrue(wireMappedSettings.Temperature == nil)
assertTrue(
    CropMapper.map(
        wireDevelopResponse.crop,
        wireDevelopResponse.leveling,
        {
            applyCompositionCrop = true,
            applyLeveling = true,
        },
        wireCurrentSettings
    ) == nil
)
local wireOriginalSettings = ApplyService.captureOriginal(
    wireCurrentSettings,
    wireMappedSettings
)
local wireOperation = PendingOperation.new({
    photo = mappedPhoto,
    photoKey = Utils.photoKey(mappedPhoto),
    filename = wireDevelopResponse.filename,
    requestId = wireDevelopResponse.request_id,
    profileId = developRequest.options.style_profile,
    originalSettings = wireOriginalSettings,
    mappedSettings = wireMappedSettings,
    compositionCropIncluded = false,
    levelingIncluded = false,
    denoiseRecommended =
        wireDevelopResponse.denoise.recommended == true,
    warnings = wireDevelopResponse.warnings,
    model = wireModel,
    resolvedModel = wireDevelopResponse.resolved_model,
    processingDurationMs =
        wireDevelopResponse.processing_duration_ms,
})
local wireOperations = {}
local wireRecordStatus = BatchOperationRecorder.tryRecord({
    cancelled = false,
    terminalFailure = false,
    preparationResult = "ready",
    operation = wireOperation,
    operations = wireOperations,
})
assertEqual(wireRecordStatus, "recorded")
assertEqual(#wireOperations, 1)
local wireSummary = {
    ready = 0,
    models = {},
}
if wireRecordStatus == "recorded" then
    wireSummary.ready = wireSummary.ready + 1
    wireSummary.models[wireOperation.model] = true
end
assertEqual(wireSummary.ready, 1)
assertEqual(
    wireSummary.models["gpt_oss"],
    true
)

local wireUnknownTopLevel = Utils.deepCopy(wireDevelopResponse)
wireUnknownTopLevel.validation_metadata = {}
assertTrue(
    not Validation.validateDevelopResponse(
        wireUnknownTopLevel,
        developRequest
    )
)
local wireIncompleteCrop = Utils.deepCopy(wireDevelopResponse)
wireIncompleteCrop.crop.recommended = true
wireIncompleteCrop.crop.left = 0.1
assertTrue(
    not Validation.validateDevelopResponse(
        wireIncompleteCrop,
        developRequest
    )
)
local wireUnsafeModel = Utils.deepCopy(wireDevelopResponse)
wireUnsafeModel.model = "https://user:secret@example.test/model"
assertTrue(
    not Validation.validateDevelopResponse(
        wireUnsafeModel,
        developRequest
    )
)
local wireUnknownSetting = Utils.deepCopy(wireDevelopResponse)
wireUnknownSetting.develop_settings.UnsafeSetting = 99
local wireAllowListed = DevelopSettingsMapper.map(
    wireUnknownSetting.develop_settings,
    wireCurrentSettings
)
assertTrue(wireAllowListed.UnsafeSetting == nil)

local nullOptionalDevelop = Utils.deepCopy(developResponse)
nullOptionalDevelop.crop = Json.null
nullOptionalDevelop.denoise = Json.null
assertTrue(
    Validation.validateDevelopResponse(
        nullOptionalDevelop,
        developRequest
    )
)
local developInvalidModel = Utils.deepCopy(developResponse)
developInvalidModel.model = "../../secret"
assertTrue(
    not Validation.validateDevelopResponse(
        developInvalidModel,
        developRequest
    )
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
}
local noLeveling = {
    recommended = false,
    angle = 0,
    mode = "none",
}
local mappedCrop = CropMapper.map(validCrop, noLeveling, {
    applyCompositionCrop = true,
    applyLeveling = true,
}, currentSettings)
assertEqual(mappedCrop.CropLeft, 0)
assertEqual(mappedCrop.CropRight, 0.95)
assertEqual(mappedCrop.CropTop, 0)
assertEqual(mappedCrop.CropBottom, 0.9)
assertEqual(mappedCrop.CropAngle, 0)
local rotatedCurrent = Utils.deepCopy(currentSettings)
rotatedCurrent.CropAngle = 1.25
local cropOnly = CropMapper.map(validCrop, noLeveling, {
    applyCompositionCrop = true,
    applyLeveling = true,
}, rotatedCurrent)
assertEqual(cropOnly.CropLeft, 0)
assertEqual(cropOnly.CropBottom, 0.9)
assertEqual(cropOnly.CropAngle, 1.25)
local horizonLeveling = {
    recommended = true,
    angle = -0.72,
    mode = "horizon",
}
local levelOnly = CropMapper.map(nil, horizonLeveling, {
    applyCompositionCrop = true,
    applyLeveling = true,
}, rotatedCurrent)
assertEqual(levelOnly.CropLeft, rotatedCurrent.CropLeft)
assertEqual(levelOnly.CropRight, rotatedCurrent.CropRight)
assertEqual(levelOnly.CropTop, rotatedCurrent.CropTop)
assertEqual(levelOnly.CropBottom, rotatedCurrent.CropBottom)
assertEqual(levelOnly.CropAngle, -0.72)
local cropAndLevel = CropMapper.map(validCrop, horizonLeveling, {
    applyCompositionCrop = true,
    applyLeveling = true,
}, rotatedCurrent)
assertEqual(cropAndLevel.CropRight, validCrop.right)
assertEqual(cropAndLevel.CropBottom, validCrop.bottom)
assertEqual(cropAndLevel.CropAngle, -0.72)
local cropPreferenceOff = CropMapper.map(validCrop, horizonLeveling, {
    applyCompositionCrop = false,
    applyLeveling = true,
}, rotatedCurrent)
assertEqual(cropPreferenceOff.CropLeft, rotatedCurrent.CropLeft)
assertEqual(cropPreferenceOff.CropAngle, -0.72)
local levelingPreferenceOff = CropMapper.map(validCrop, horizonLeveling, {
    applyCompositionCrop = true,
    applyLeveling = false,
}, rotatedCurrent)
assertEqual(levelingPreferenceOff.CropRight, validCrop.right)
assertEqual(levelingPreferenceOff.CropAngle, rotatedCurrent.CropAngle)
assertTrue(CropMapper.map(nil, noLeveling, {
    applyCompositionCrop = true,
    applyLeveling = true,
}, currentSettings) == nil)
assertTrue(CropMapper.map(validCrop, noLeveling, {
    applyCompositionCrop = false,
    applyLeveling = true,
}, currentSettings) == nil)
local incompleteCrop = Utils.deepCopy(validCrop)
incompleteCrop.bottom = nil
assertTrue(CropMapper.map(incompleteCrop, noLeveling, {
    applyCompositionCrop = true,
    applyLeveling = true,
}, currentSettings) == nil)
local outsideCrop = Utils.deepCopy(validCrop)
outsideCrop.left = -0.01
assertTrue(CropMapper.map(outsideCrop, noLeveling, {
    applyCompositionCrop = true,
    applyLeveling = true,
}, currentSettings) == nil)
local reversedHorizontalCrop = Utils.deepCopy(validCrop)
reversedHorizontalCrop.left = 0.9
reversedHorizontalCrop.right = 0.2
assertTrue(
    CropMapper.map(reversedHorizontalCrop, noLeveling, {
        applyCompositionCrop = true,
        applyLeveling = true,
    }, currentSettings) == nil
)
local reversedVerticalCrop = Utils.deepCopy(validCrop)
reversedVerticalCrop.top = 0.9
reversedVerticalCrop.bottom = 0.2
assertTrue(
    CropMapper.map(reversedVerticalCrop, noLeveling, {
        applyCompositionCrop = true,
        applyLeveling = true,
    }, currentSettings) == nil
)
local infiniteLeveling = {
    recommended = true,
    angle = math.huge,
    mode = "horizon",
}
assertTrue(
    CropMapper.map(nil, infiniteLeveling, {
        applyCompositionCrop = true,
        applyLeveling = true,
    }, currentSettings) == nil
)
local excessiveLeveling = {
    recommended = true,
    angle = 45.1,
    mode = "horizon",
}
assertTrue(
    CropMapper.map(nil, excessiveLeveling, {
        applyCompositionCrop = true,
        applyLeveling = true,
    }, currentSettings) == nil
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
    compositionCropIncluded = true,
    denoise = {
        recommended = true,
        included = true,
        amount = 50,
        confidence = 0.9,
        reason = "ISO 3600 indicates strong high-ISO noise risk.",
        presetName = "AutoDevelop AI - Denoise 50",
    },
    denoisePreset = denoisePreset50,
    denoiseOriginalSettings = { FilterList = {} },
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
    finalSettings = {
        Exposure2012 = 0,
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

local denoiseApplyEvents = {}
local denoiseApplyPhoto = {
    applyDevelopPreset = function(_, preset, plugin)
        assertTrue(insideWrite, "preset apply must run inside write access")
        assertTrue(preset == denoisePreset50)
        assertTrue(plugin == nil, "global presets must not receive a plugin")
        denoiseApplyEvents[#denoiseApplyEvents + 1] = "preset"
    end,
    applyDevelopSettings = function(_, values)
        assertTrue(insideWrite, "settings apply must run inside write access")
        denoiseApplyEvents[#denoiseApplyEvents + 1] = "settings"
        appliedSettings = Utils.deepCopy(values)
    end,
}
local denoiseApplyOperation = PendingOperation.new({
    photo = denoiseApplyPhoto,
    mappedSettings = { Exposure2012 = 0.4 },
    finalSettings = { Exposure2012 = 0.4 },
    originalSettings = { Exposure2012 = 0 },
    denoise = {
        recommended = true,
        included = true,
        amount = 50,
        confidence = 0.9,
        reason = "ISO 3600 indicates strong high-ISO noise risk.",
        presetName = "AutoDevelop AI - Denoise 50",
    },
    denoisePreset = denoisePreset50,
    denoiseOriginalSettings = {
        FilterList = {},
        ColorNoiseReduction = 25,
    },
})
local denoiseApplyResult = ApplyService.applyOne(
    fakeCatalog,
    denoiseApplyOperation
)
assertEqual(denoiseApplyResult.applied, 1)
assertEqual(denoiseApplyEvents[1], "preset")
assertEqual(denoiseApplyEvents[2], "settings")
assertEqual(denoiseApplyOperation.denoiseApplied, true)

local denoiseOnlyOperation = PendingOperation.new({
    photo = denoiseApplyPhoto,
    finalSettings = {},
    originalSettings = {},
    denoise = {
        recommended = true,
        included = true,
        amount = 50,
        confidence = 0.9,
        presetName = "AutoDevelop AI - Denoise 50",
    },
    denoisePreset = denoisePreset50,
    denoiseOriginalSettings = { FilterList = {} },
})
local denoiseOnlyDisplay =
    PendingOperation.inspectDisplayContract(denoiseOnlyOperation)
assertEqual(denoiseOnlyDisplay.canApply, true)
assertEqual(denoiseOnlyDisplay.finalCount, 1)
local denoiseOnlyResult = ApplyService.applyOne(
    fakeCatalog,
    denoiseOnlyOperation
)
assertEqual(denoiseOnlyResult.applied, 1)
assertEqual(denoiseOnlyOperation.denoiseApplied, true)

appliedSettings = nil
local hdrOperation = PendingOperation.new({
    photo = successfulPhoto,
    enableHdr = true,
    mappedSettings = {
        Exposure2012 = 0.25,
        HDREditMode = 99,
    },
    finalSettings = {
        Exposure2012 = 0.25,
        HDREditMode = 1,
    },
    originalSettings = {
        Exposure2012 = 0,
        HDREditMode = 0,
    },
})
local hdrApplyResult = ApplyService.applyBatch(
    fakeCatalog,
    { hdrOperation }
)
assertEqual(hdrApplyResult.applied, 1)
assertEqual(appliedSettings.Exposure2012, 0.25)
assertEqual(appliedSettings.HDREditMode, 1)

local preparedFinalSettings = ApplyService.prepareFinalSettings(
    { Exposure2012 = 0.35 },
    {
        Exposure2012 = 0,
        EnableTransform = false,
        PerspectiveUpright = 0,
        HDREditMode = 0,
    },
    "vertical",
    true
)
assertEqual(preparedFinalSettings.Exposure2012, 0.35)
assertEqual(preparedFinalSettings.EnableTransform, true)
assertEqual(preparedFinalSettings.PerspectiveUpright, 4)
assertEqual(preparedFinalSettings.HDREditMode, 1)
assertTrue(ApplyService.validateFinalSettings(preparedFinalSettings))
assertTrue(not ApplyService.validateFinalSettings({
    Exposure2012 = 0.35,
    UnsupportedSetting = 1,
}))
assertTrue(not ApplyService.validateFinalSettings({
    PerspectiveUpright = 5,
}))

local exactSettingsReceived = nil
local exactFinalSettings = { Exposure2012 = 0.45 }
local exactOperation = PendingOperation.new({
    photo = {
        applyDevelopSettings = function(_, settings)
            exactSettingsReceived = settings
        end,
    },
    mappedSettings = { Exposure2012 = 0.4 },
    finalSettings = exactFinalSettings,
    originalSettings = { Exposure2012 = 0 },
})
local exactApplyResult =
    ApplyService.applyOne(fakeCatalog, exactOperation)
assertEqual(exactApplyResult.applied, 1)
assertTrue(exactSettingsReceived == exactOperation.finalSettings)
assertEqual(exactSettingsReceived.Exposure2012, 0.45)

do
local reviewOperation = PendingOperation.new({
    originalSettings = {
        Exposure2012 = 0,
        Contrast2012 = 2,
        Temperature = 5200,
        Tint = 3,
        CropLeft = 0,
        CropRight = 1,
        CropTop = 0,
        CropBottom = 1,
        CropAngle = 0,
        EnableTransform = false,
        PerspectiveUpright = 0,
        HDREditMode = 0,
    },
    mappedSettings = {
        Exposure2012 = 9,
    },
    finalSettings = {
        Exposure2012 = 0.35,
        Contrast2012 = 18,
        Temperature = 5480,
        Tint = 5,
        CropLeft = 0.035,
        CropRight = 0.972,
        CropTop = 0.018,
        CropBottom = 0.965,
        CropAngle = -1.2,
        EnableTransform = true,
        PerspectiveUpright = 4,
        HDREditMode = 1,
    },
    cropRecommended = true,
    compositionCropIncluded = true,
    levelingRecommended = true,
    levelingIncluded = true,
    levelingMode = "horizon",
    uprightRecommended = true,
    uprightMode = "vertical",
    uprightConfidence = 0.91,
    hdrRecommended = true,
    enableHdr = true,
    denoise = {
        recommended = true,
        included = true,
        amount = 50,
        confidence = 0.9,
        reason = "ISO 3600 indicates strong high-ISO noise risk.",
        presetName = "AutoDevelop AI - Denoise 50",
    },
    denoisePreset = denoisePreset50,
    denoiseOriginalSettings = { FilterList = {} },
    learning = {
        enabled = true,
        retrieved_sample_count = 5,
        average_similarity = 1,
        personalization_applied = true,
    },
    warnings = {
        { message = "Warning 1" },
        { message = "Warning 2" },
        { message = "Warning 3" },
        { message = "Warning 4" },
        { message = "Warning 5" },
        { message = "Warning 6" },
    },
})
local review = PendingOperationReview.build(reviewOperation)
assertEqual(reviewOperation.finalSettings.Exposure2012, 0.35)
assertTrue(reviewOperation.finalSettings.change == nil)
assertEqual(review.settingCount, 12)
assertEqual(#review.developRows, 4)
assertEqual(review.developRows[1].label, "Exposure")
assertEqual(review.developRows[1].current, "0.00")
assertEqual(review.developRows[1].proposed, "+0.35")
assertEqual(review.developRows[1].change, "+0.35")
assertEqual(review.developRows[1].proposedValue, 0.35)
assertEqual(review.developRows[2].label, "Contrast")
assertEqual(review.developRows[2].change, "+16")
assertEqual(review.developRows[3].current, "5200 K")
assertEqual(review.developRows[3].proposed, "5480 K")
assertEqual(review.developRows[3].change, "+280 K")
assertEqual(review.developRows[4].current, "+3")
assertEqual(review.developRows[4].proposed, "+5")
assertEqual(review.developRows[4].change, "+2")
for _, settingRow in ipairs(review.developRows) do
    assertTrue(settingRow.key ~= "Dehaze")
end
assertEqual(#review.geometryRows, 5)
assertEqual(review.geometryRows[1].current, "0.000")
assertEqual(review.geometryRows[1].proposed, "0.035")
assertEqual(review.geometryRows[5].proposed, "-1.20\194\176")
assertTrue(
    table.concat(review.geometryLines, "\n"):find(
        "Composition crop: Recommended - prepared for application",
        1,
        true
    ) ~= nil
)
assertTrue(
    table.concat(review.geometryLines, "\n"):find(
        "Leveling: Recommended - prepared for application",
        1,
        true
    ) ~= nil
)
assertTrue(
    table.concat(review.uprightLines, "\n"):find(
        "Current -> proposed: off -> vertical",
        1,
        true
    ) ~= nil
)
assertTrue(
    table.concat(review.hdrLines, "\n"):find(
        "Enabled: Yes",
        1,
        true
    ) ~= nil
)
assertTrue(
    table.concat(review.processingLines, "\n"):find(
        "Denoise will be applied: Yes",
        1,
        true
    ) ~= nil
)
assertTrue(
    table.concat(review.processingLines, "\n"):find(
        "Denoise amount: 50",
        1,
        true
    ) ~= nil
)
assertTrue(
    table.concat(review.processingLines, "\n"):find(
        "Denoise preset: AutoDevelop AI - Denoise 50",
        1,
        true
    ) ~= nil
)
assertTrue(
    table.concat(review.processingLines, "\n"):find(
        "Dust removal: Not part of this prepared operation",
        1,
        true
    ) ~= nil
)
assertTrue(
    table.concat(review.learningLines, "\n"):find(
        "Average similarity: 1.00",
        1,
        true
    ) ~= nil
)
assertEqual(#review.warningLines, 6)
assertEqual(review.warningLines[6], "+1 more warnings")

local inactiveUprightOff = PendingOperationReview.build(
    PendingOperation.new({
        originalSettings = { Exposure2012 = 0 },
        finalSettings = { Exposure2012 = 0.2 },
        upright = {
            recommended = false,
            mode = "off",
            confidence = 0,
            reason = nil,
        },
        modeDiagnostics = { perspectiveUpright = 0 },
    })
)
local inactiveUprightOffText =
    table.concat(inactiveUprightOff.uprightLines, "\n")
assertTrue(
    inactiveUprightOffText:find(
        "Current -> proposed: off -> off",
        1,
        true
    ) ~= nil
)
assertTrue(
    inactiveUprightOffText:find(
        "Reason: No Upright correction recommended",
        1,
        true
    ) ~= nil
)
assertTrue(inactiveUprightOffText:find("unknown", 1, true) == nil)

local inactiveUprightVertical = PendingOperationReview.build(
    PendingOperation.new({
        originalSettings = { Exposure2012 = 0 },
        finalSettings = { Exposure2012 = 0.2 },
        upright = {
            recommended = false,
            mode = "off",
            confidence = 0,
            reason = nil,
        },
        modeDiagnostics = { perspectiveUpright = 4 },
    })
)
local inactiveUprightVerticalText =
    table.concat(inactiveUprightVertical.uprightLines, "\n")
assertTrue(
    inactiveUprightVerticalText:find(
        "Mode: vertical",
        1,
        true
    ) ~= nil
)
assertTrue(
    inactiveUprightVerticalText:find(
        "Current -> proposed: vertical -> vertical",
        1,
        true
    ) ~= nil
)

local unavailableUpright = PendingOperationReview.build(
    PendingOperation.new({
        originalSettings = { Exposure2012 = 0 },
        finalSettings = { Exposure2012 = 0.2 },
    })
)
local unavailableUprightText =
    table.concat(unavailableUpright.uprightLines, "\n")
assertTrue(
    unavailableUprightText:find(
        "Current -> proposed: Unavailable (no change proposed)",
        1,
        true
    ) ~= nil
)
assertTrue(unavailableUprightText:find("unknown", 1, true) == nil)

local inactiveHdr = PendingOperationReview.build(
    PendingOperation.new({
        originalSettings = { Exposure2012 = 0 },
        finalSettings = { Exposure2012 = 0.2 },
        hdr = {
            recommended = false,
            enabled = false,
            confidence = 0.20,
            reason = nil,
        },
        hdrDecision = {
            scene_hdr_candidate = false,
            scene_hdr_confidence = 0.20,
            base_scene_evidence_score = 0.18,
            learning_bonus = 0.10,
            user_preference_bonus = 0.08,
            combined_evidence_score = 0.36,
            decision_basis = "disabled",
            decision_confidence = Json.null,
            scene_hdr_inconsistent = false,
            contraindications = {},
            visual_evidence_score = 0.18,
            hdr_evidence_score = 0.36,
            hdr_learning_applied = true,
            hdr_learning_enable_rate = 1.0,
            hdr_learning_sample_count = 4,
            raw_hdr_recommended = false,
            raw_hdr_confidence = 0.20,
            validated_hdr_enabled = false,
            validated_hdr_confidence = 0.20,
            hdr_rejected = false,
            hdr_rejection_reason = "insufficient_evidence",
        },
        modeDiagnostics = { hdrEditMode = 0 },
    })
)
local inactiveHdrText = table.concat(inactiveHdr.hdrLines, "\n")
for _, expectedText in ipairs({
    "Base scene evidence: 18%",
    "Learning bonus: 10%",
    "Preference bonus: 8%",
    "Combined evidence: 36%",
    "Decision basis: Disabled",
    "Current -> proposed: Disabled -> Disabled",
}) do
    assertTrue(inactiveHdrText:find(expectedText, 1, true) ~= nil)
end
assertTrue(inactiveHdrText:find("nil", 1, true) == nil)

local cropOnly = PendingOperationReview.build(
    PendingOperation.new({
        originalSettings = {
            CropLeft = 0,
            CropRight = 1,
            CropTop = 0,
            CropBottom = 1,
            CropAngle = 0,
        },
        finalSettings = {
            CropLeft = 0.1,
            CropRight = 0.9,
            CropTop = 0.1,
            CropBottom = 0.9,
            CropAngle = 0,
        },
        cropRecommended = true,
        compositionCropIncluded = true,
    })
)
assertTrue(
    table.concat(cropOnly.geometryLines, "\n"):find(
        "Leveling: Not needed",
        1,
        true
    ) ~= nil
)

local levelOnly = PendingOperationReview.build(
    PendingOperation.new({
        originalSettings = {
            CropLeft = 0,
            CropRight = 1,
            CropTop = 0,
            CropBottom = 1,
            CropAngle = 0,
        },
        finalSettings = {
            CropLeft = 0,
            CropRight = 1,
            CropTop = 0,
            CropBottom = 1,
            CropAngle = -0.6,
        },
        levelingRecommended = true,
        levelingIncluded = true,
    })
)
assertTrue(
    table.concat(levelOnly.geometryLines, "\n"):find(
        "Current crop bounds will be preserved",
        1,
        true
    ) ~= nil
)

local neither = PendingOperationReview.build(PendingOperation.new({}))
assertEqual(#neither.geometryRows, 0)
assertTrue(
    table.concat(neither.geometryLines, "\n"):find(
        "Composition crop: Not needed",
        1,
        true
    ) ~= nil
)
assertTrue(
    table.concat(neither.geometryLines, "\n"):find(
        "Leveling: Not needed",
        1,
        true
    ) ~= nil
)

local suppressed = PendingOperationReview.build({
    originalSettings = {},
    finalSettings = {},
    cropRecommended = true,
    cropDisabled = true,
    levelingRecommended = true,
    levelingDisabled = true,
})
assertTrue(
    table.concat(suppressed.geometryLines, "\n"):find(
        "Composition crop: Recommended - suppressed by preference",
        1,
        true
    ) ~= nil
)
assertTrue(
    table.concat(suppressed.geometryLines, "\n"):find(
        "Leveling: Recommended - suppressed by preference",
        1,
        true
    ) ~= nil
)

local displayFixture = PendingOperation.new({
    photo = {},
    photoId = "photo_283285",
    displayFilename = "DSC_2841.NEF",
    filename = "DSC_2841.NEF",
    requestId = "display-fixture",
    requestedStyleId = "auto",
    effectiveStyleId = "architecture",
    editingIntensity = "moderate",
    originalSettings = {
        Exposure2012 = 0.0,
        Contrast2012 = 0,
        Highlights2012 = 0,
        Shadows2012 = 0,
        Whites2012 = 0,
        Blacks2012 = 0,
        Texture = 0,
        Clarity2012 = 0,
        Dehaze = 0,
        Vibrance = 0,
        Saturation = 0,
        Temperature = 5200,
        Tint = 3,
    },
    finalSettings = {
        Exposure2012 = 0.35,
        Contrast2012 = 18,
        Highlights2012 = -42,
        Shadows2012 = 31,
        Whites2012 = 14,
        Blacks2012 = -17,
        Texture = 12,
        Clarity2012 = 9,
        Dehaze = 7,
        Vibrance = 21,
        Saturation = 2,
        Temperature = 5480,
        Tint = 5,
    },
})
local displayReview = PendingOperationReview.build(displayFixture)
assertEqual(#displayReview.developRows, 13)
local displayText = table.concat(
    AutoDevelopConfirmationDialog.photoLines(displayFixture, 1, 1),
    "\n"
)
for _, expected in ipairs({
    "Exposure",
    "0.00",
    "+0.35",
    "Contrast",
    "+18",
    "Highlights",
    "-42",
    "Temperature",
    "5200 K",
    "5480 K",
    "+280 K",
    "Tint",
    "+3",
    "+5",
}) do
    assertTrue(displayText:find(expected, 1, true) ~= nil)
end
assertTrue(#displayText > #"Photo 1 of 1" + 500)
assertTrue(displayText:find("Filename: DSC_2841.NEF", 1, true) ~= nil)
assertTrue(displayText:find("Filename: photo_283285", 1, true) == nil)

local displayContract =
    PendingOperation.inspectDisplayContract(displayFixture)
assertTrue(displayContract.canApply)
assertTrue(displayContract.finalSettings == displayFixture.finalSettings)
assertEqual(displayContract.finalCount, 13)

local displayFailureSummary = BatchSummary.new(1, "develop")
BatchSummary.recordApplication(
    displayFailureSummary,
    {
        displayFilename = displayFixture.displayFilename,
        filename = displayFixture.photoId,
        applicationStatus = "not_applied",
    },
    {
        applied = 0,
        restoredAfterFailure = 0,
        failedNotRestored = 0,
        notApplied = 1,
        cancelled = false,
    }
)
assertEqual(
    displayFailureSummary.failures[1].filename,
    "DSC_2841.NEF"
)

local missingOriginal = {
    filename = "Missing-Original.NEF",
    originalSettings = {},
    finalSettings = { Exposure2012 = 0.4 },
}
local missingOriginalReview =
    PendingOperationReview.build(missingOriginal)
assertEqual(missingOriginalReview.developRows[1].current, "\226\128\148")
assertEqual(missingOriginalReview.developRows[1].proposed, "+0.40")
assertTrue(missingOriginalReview.comparisonUnavailable)
assertTrue(
    table.concat(missingOriginalReview.warningLines, "\n"):find(
        "Current-value comparison is unavailable",
        1,
        true
    ) ~= nil
)
local missingOriginalText = table.concat(
    AutoDevelopConfirmationDialog.photoLines(missingOriginal, 1, 1),
    "\n"
)
for _, section in ipairs({
    "Develop Settings",
    "Geometry",
    "Processing",
    "Learning",
    "Warnings",
}) do
    assertTrue(missingOriginalText:find(section, 1, true) ~= nil)
end

local responseInsteadOfOperation = {
    filename = "Response.NEF",
    result = { develop_settings = { Exposure2012 = 0.4 } },
}
local responseDisplay =
    PendingOperation.inspectDisplayContract(responseInsteadOfOperation)
assertEqual(
    responseDisplay.diagnosticCode,
    "missing_final_settings"
)
local namingMismatchDisplay =
    PendingOperation.inspectDisplayContract({
        filename = "Naming-Mismatch.NEF",
        originalSettings = { Exposure2012 = 0 },
        finalDevelopSettings = { Exposure2012 = 0.4 },
    })
assertEqual(
    namingMismatchDisplay.diagnosticCode,
    "missing_final_settings"
)
end

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
local cancelledWriteCalls = 0
local cancelledPhoto = {
    applyDevelopSettings = function()
        cancelledCalls = cancelledCalls + 1
    end,
}
local cancelledResult = ApplyService.applyBatch(
    {
        withWriteAccessDo = function()
            cancelledWriteCalls = cancelledWriteCalls + 1
        end,
    },
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
assertEqual(cancelledWriteCalls, 0)
assertEqual(cancelledResult.notApplied, 1)
assertEqual(cancelledResult.cancelled, true)

local writeFailureOperation = PendingOperation.new({
    photo = successfulPhoto,
    mappedSettings = { Exposure2012 = 1 },
    originalSettings = { Exposure2012 = 0 },
})
local writeFailureResult = ApplyService.applyBatch(
    {
        withWriteAccessDo = function()
            error("/home/person/private/catalog?token=secret")
        end,
    },
    { writeFailureOperation }
)
assertEqual(writeFailureResult.writeErrorCategory, "write_access_failed")
assertEqual(
    writeFailureResult.writeErrorCode,
    "catalog_write_access_failed"
)
assertTrue(
    writeFailureResult.writeError:find("/home/person", 1, true) == nil
)
assertTrue(
    writeFailureResult.writeError:find("token=secret", 1, true) == nil
)

local restoreCalls = 0
local restoredValue = nil
local restoredHdrValue = nil
local failingPhoto = {
    applyDevelopSettings = function(_, values)
        restoreCalls = restoreCalls + 1
        if restoreCalls == 1 then
            error("C:\\Users\\Person\\secret-preview.jpg?token=secret")
        end
        restoredValue = values.Exposure2012
        restoredHdrValue = values.HDREditMode
    end,
}
local restoreOperation = PendingOperation.new({
    photo = failingPhoto,
    mappedSettings = { Exposure2012 = 1 },
    originalSettings = { Exposure2012 = 0, HDREditMode = 0 },
    enableHdr = true,
})
local restoreResult = ApplyService.applyBatch(
    fakeCatalog,
    { restoreOperation }
)
assertEqual(restoreResult.restoredAfterFailure, 1)
assertEqual(restoreResult.failedNotRestored, 0)
assertEqual(restoredValue, 0)
assertEqual(restoredHdrValue, 0)
assertEqual(restoreOperation.applyErrorCategory, "apply_failed")
assertEqual(restoreOperation.applyErrorCode, "lightroom_apply_failed")
assertTrue(
    restoreOperation.applyError:find(
        "C:\\Users\\Person",
        1,
        true
    ) == nil
)
assertTrue(restoreOperation.applyError:find("token=secret", 1, true) == nil)

local denoiseRestoreCalls = 0
local restoredDenoiseFilter = nil
local denoiseFailingPhoto = {
    applyDevelopPreset = function()
        assertTrue(insideWrite)
    end,
    applyDevelopSettings = function(_, values)
        denoiseRestoreCalls = denoiseRestoreCalls + 1
        if denoiseRestoreCalls == 1 then
            error("simulated Develop failure after Denoise preset")
        end
        restoredValue = values.Exposure2012
        restoredDenoiseFilter = values.FilterList
    end,
}
local denoiseRestoreOperation = PendingOperation.new({
    photo = denoiseFailingPhoto,
    finalSettings = { Exposure2012 = 0.5 },
    originalSettings = { Exposure2012 = 0 },
    denoise = {
        recommended = true,
        included = true,
        amount = 50,
        confidence = 0.9,
    },
    denoisePreset = denoisePreset50,
    denoiseOriginalSettings = { FilterList = {} },
})
local denoiseRestoreResult = ApplyService.applyOne(
    fakeCatalog,
    denoiseRestoreOperation
)
assertEqual(denoiseRestoreResult.restoredAfterFailure, 1)
assertEqual(denoiseRestoreOperation.denoiseApplied, false)
assertEqual(restoredValue, 0)
assertTrue(type(restoredDenoiseFilter) == "table")
assertEqual(next(restoredDenoiseFilter), nil)

local singleApplyOperation = PendingOperation.new({
    photo = successfulPhoto,
    mappedSettings = { Exposure2012 = 0.5 },
    originalSettings = { Exposure2012 = 0 },
})
local singleApplyResult =
    ApplyService.applyOne(fakeCatalog, singleApplyOperation)
assertEqual(singleApplyResult.applied, 1)
assertEqual(singleApplyOperation.applicationStatus, "applied")
assertEqual(appliedSettings.Exposure2012, 0.5)

local singleRestoreOperation = PendingOperation.new({
    photo = failingPhoto,
    mappedSettings = { Exposure2012 = 0.75 },
    originalSettings = { Exposure2012 = 0 },
})
restoreCalls = 0
local singleRestoreResult =
    ApplyService.applyOne(fakeCatalog, singleRestoreOperation)
assertEqual(singleRestoreResult.restoredAfterFailure, 1)
assertEqual(singleRestoreOperation.applicationStatus, "restored")

local invalidSingleApply = ApplyService.applyOne(fakeCatalog, nil)
assertEqual(invalidSingleApply.applied, 0)
assertEqual(invalidSingleApply.notApplied, 1)
assertEqual(invalidSingleApply.writeErrorCode, "invalid_operation")

local ignoredBaseline = LearningBaselineService.recordOne(
    PendingOperation.new({
        applicationStatus = "pending",
    }),
    {
        backendBaseUrl = "http://127.0.0.1:8005",
        requestTimeoutSeconds = 120,
    }
)
assertEqual(ignoredBaseline.saved, 0)
assertEqual(ignoredBaseline.failed, 0)

local baselinePhoto = photo({
    localIdentifier = 8247,
    fileName = "DSC_8247.NEF",
    fileFormat = "RAW",
}, nil, {
    Exposure2012 = 0.45,
    PerspectiveUpright = 2,
    HDREditMode = 1,
})
local baselineOperation = PendingOperation.new({
    photo = baselinePhoto,
    displayFilename = "DSC_8247.NEF",
    filename = "DSC_8247.NEF",
    requestId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    profileId = "documentary",
    model = "qwen",
    resolvedModel = "qwen_qwen3-vl-32b-instruct",
    originalSettings = {
        Exposure2012 = 0.1,
        EnableTransform = false,
        PerspectiveUpright = 0,
        HDREditMode = 0,
    },
    mappedSettings = {
        Exposure2012 = 0.45,
        EnableTransform = true,
        PerspectiveUpright = 2,
        HDREditMode = 1,
    },
    upright = {
        recommended = true,
        mode = "full",
        confidence = 0.8,
    },
    hdr = {
        recommended = true,
        enabled = true,
        confidence = 0.75,
    },
    hdrDecision = {
        contraindications = {},
    },
    exifContext = {
        file_format = "RAW",
        iso = 3600,
    },
})
baselineOperation.applicationStatus = "applied"
fakeHttpResponder = function(body)
    local posted = assert(Json.decode(body))
    return assert(Json.encode({
        schema_version = 1,
        session_id = posted.session_id,
        state = "pending_feedback",
        stored = true,
    })), { status = 200 }
end
local storedBaseline = LearningBaselineService.recordOne(
    baselineOperation,
    {
        backendBaseUrl = "http://127.0.0.1:8005",
        requestTimeoutSeconds = 120,
    }
)
assertEqual(storedBaseline.saved, 1)
assertEqual(storedBaseline.failed, 0)
local postedBaseline = assert(Json.decode(lastHttpPostBody))
assertEqual(postedBaseline.original_settings.Exposure2012, 0.1)
assertTrue(postedBaseline.original_settings.EnableTransform == nil)
assertTrue(postedBaseline.original_settings.PerspectiveUpright == nil)
assertTrue(postedBaseline.original_settings.HDREditMode == nil)
assertEqual(postedBaseline.recommendation.Exposure2012, 0.45)
assertTrue(postedBaseline.recommendation.EnableTransform == nil)
assertTrue(postedBaseline.recommendation.PerspectiveUpright == nil)
assertTrue(postedBaseline.recommendation.HDREditMode == nil)
assertEqual(postedBaseline.original_modes.upright, "off")
assertEqual(postedBaseline.original_modes.hdr_enabled, false)
assertEqual(postedBaseline.recommendation_modes.upright, "full")
assertEqual(postedBaseline.recommendation_modes.hdr_enabled, true)
assertEqual(postedBaseline.applied_modes.upright, "full")
assertEqual(postedBaseline.applied_modes.hdr_enabled, true)
assertEqual(postedBaseline.exif_context.file_format, "RAW")
assertEqual(postedBaseline.exif_context.iso, 3600)
assertTrue(postedBaseline.hdr_decision ~= nil)
assertTrue(postedBaseline.hdr_decision.contraindications == nil)

baselineOperation.hdrDecision.contraindications = {
    "high_noise_risk",
}
local storedBaselineWithContraindication =
    LearningBaselineService.recordOne(
        baselineOperation,
        {
            backendBaseUrl = "http://127.0.0.1:8005",
            requestTimeoutSeconds = 120,
        }
    )
assertEqual(storedBaselineWithContraindication.saved, 1)
assertEqual(storedBaselineWithContraindication.failed, 0)
local postedBaselineWithContraindication =
    assert(Json.decode(lastHttpPostBody))
assertEqual(
    postedBaselineWithContraindication.hdr_decision.contraindications[1],
    "high_noise_risk"
)

local warningsBeforeBaselineFailure = #logged.warning
fakeHttpResponder = function()
    return assert(Json.encode({
        error = {
            code = "request_validation_failed",
            message = "private backend validation detail",
            retryable = false,
        },
    })), { status = 422 }
end
local rejectedBaseline = LearningBaselineService.recordOne(
    baselineOperation,
    {
        backendBaseUrl = "http://127.0.0.1:8005",
        requestTimeoutSeconds = 120,
    }
)
assertEqual(rejectedBaseline.saved, 0)
assertEqual(rejectedBaseline.failed, 1)
assertEqual(#logged.warning, warningsBeforeBaselineFailure + 1)
local baselineFailureLog = logged.warning[#logged.warning]
assertTrue(baselineFailureLog:find("filename=DSC_8247.NEF", 1, true) ~= nil)
assertTrue(baselineFailureLog:find("status=422", 1, true) ~= nil)
assertTrue(
    baselineFailureLog:find("category=validation_error", 1, true) ~= nil
)
assertTrue(
    baselineFailureLog:find("code=request_validation_failed", 1, true) ~= nil
)
assertTrue(
    baselineFailureLog:find("private backend", 1, true) == nil
)
fakeHttpResponder = nil
LearningSessionStore.remove(LearningPhotoIdentity.forPhoto(baselinePhoto))

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

assertTrue(BatchPolicy.shouldRetry(
    {
        ok = false,
        status = 500,
        category = "backend_error",
        retryable = true,
    },
    0,
    false
))
assertTrue(BatchPolicy.shouldRetry(
    {
        ok = false,
        status = 502,
        category = "backend_error",
        retryable = true,
    },
    0,
    false
))
assertTrue(BatchPolicy.shouldRetry(
    {
        ok = false,
        category = "model_timeout",
        retryable = true,
    },
    0,
    false
))
assertTrue(not BatchPolicy.shouldRetry(
    { ok = false, status = 400, category = "validation_error" },
    0,
    false
))
assertTrue(not BatchPolicy.shouldRetry(
    {
        ok = false,
        status = 500,
        category = "backend_error",
        retryable = true,
    },
    1,
    false
))
assertTrue(not BatchPolicy.shouldRetry(
    {
        ok = false,
        status = 502,
        category = "backend_error",
        retryable = true,
    },
    0,
    true
))
assertTrue(not BatchPolicy.shouldRetry(
    {
        ok = false,
        status = 502,
        category = "invalid_response",
        retryable = false,
    },
    0,
    false
))

fakeHttpResponseBody = Json.encode({
    error = {
        code = "provider_schema_mismatch",
        message = "The selected model response did not match.",
        retryable = false,
    },
})
fakeHttpResponseHeaders = { status = 502 }
local deterministicInvalid = ApiClient.develop(
    { request_id = "attempt-test" },
    {
        baseUrl = "http://127.0.0.1:8005",
        timeoutSeconds = 120,
        endpointAttempt = 2,
    }
)
assertEqual(deterministicInvalid.retryable, false)
assertEqual(deterministicInvalid.category, "invalid_response")
local attemptHeader = nil
for _, header in ipairs(lastHttpPostHeaders or {}) do
    if header.field == "X-Autodevelop-Attempt" then
        attemptHeader = header.value
    end
end
assertEqual(attemptHeader, "2")

local summary = BatchSummary.new(5, "analyze")
summary.analyzed = 2
summary.skipped = 1
BatchSummary.addFailure(summary, "bad.nef", {
    category = "internal_error",
    code = "failed",
})
BatchSummary.markNotProcessed(summary, 1)
assertEqual(summary.selected, 5)
assertEqual(summary.analyzed, 2)
assertEqual(summary.failed, 1)
assertEqual(summary.skipped, 1)
assertEqual(summary.notProcessed, 1)

do
local incrementalSummary = BatchSummary.new(4, "develop")
local incrementalOperation = PendingOperation.new({
    photo = {},
    filename = "Incremental.NEF",
    requestId = "incremental-request",
    requestedStyleId = "auto",
    effectiveStyleId = "architecture",
    editingIntensity = "strong",
    originalSettings = { Exposure2012 = 0 },
    mappedSettings = { Exposure2012 = 0.35 },
    finalSettings = { Exposure2012 = 0.35 },
    cropRecommended = true,
    compositionCropIncluded = true,
    levelingRecommended = true,
    levelingIncluded = true,
    levelingAngle = -0.6,
    hdrRecommended = true,
    enableHdr = true,
    denoiseRecommended = true,
    warnings = { { code = "test" } },
    model = "gpt_oss",
    resolvedModel = "test-model",
    learning = {
        enabled = true,
        personalization_applied = true,
        usable_sample_count = 5,
        retrieved_sample_count = 5,
        minimum_sample_count = 3,
        average_similarity = 0.91,
    },
})
BatchSummary.markAttempted(incrementalSummary)
BatchSummary.recordPrepared(incrementalSummary, incrementalOperation)
assertEqual(incrementalSummary.attempted, 1)
assertEqual(incrementalSummary.prepared, 1)
assertEqual(incrementalSummary.ready, 1)
assertEqual(incrementalSummary.effectiveStyles.architecture, 1)
assertEqual(incrementalSummary.editingIntensities.strong, 1)
assertEqual(incrementalSummary.cropRecommendedCount, 1)
assertEqual(incrementalSummary.levelingRecommendedCount, 1)
assertEqual(incrementalSummary.hdrRecommendedCount, 1)
assertEqual(incrementalSummary.denoiseRecommendedCount, 1)
assertEqual(incrementalSummary.personalizationApplied, 1)
assertEqual(incrementalSummary.warningCount, 1)
assertEqual(incrementalSummary.models.gpt_oss, true)
assertEqual(incrementalSummary.resolvedModels["test-model"], true)

incrementalOperation.applicationStatus = "applied"
BatchSummary.recordApplication(
    incrementalSummary,
    incrementalOperation,
    {
        applied = 1,
        restoredAfterFailure = 0,
        failedNotRestored = 0,
        notApplied = 0,
    }
)
assertEqual(incrementalSummary.processed, 1)
assertEqual(incrementalSummary.applied, 1)
assertEqual(incrementalSummary.cropAppliedCount, 1)
assertEqual(incrementalSummary.levelingAppliedCount, 1)
assertEqual(incrementalSummary.hdrAppliedCount, 1)
assertEqual(incrementalSummary.denoiseAppliedCount, 0)

local denoiseDiagnosticSummary = BatchSummary.new(1, "develop")
denoiseDiagnosticSummary.profileId = "natural_travel"
denoiseDiagnosticSummary.models = {}
denoiseDiagnosticSummary.resolvedModels = {}
BatchSummary.recordPrepared(
    denoiseDiagnosticSummary,
    PendingOperation.new({
        denoise = {
            recommended = true,
            included = false,
            amount = 25,
            unavailableCode = "denoise_preset_missing",
            unavailableReason = "Required Lightroom preset was not found.",
        },
    })
)
assertEqual(denoiseDiagnosticSummary.denoiseIgnored, 1)
assertEqual(
    denoiseDiagnosticSummary
        .denoiseExclusionReasons
        .denoise_preset_missing,
    1
)
lastDialog = nil
AutoDevelopConfirmationDialog.showFinal(
    denoiseDiagnosticSummary,
    {}
)
assertTrue(
    lastDialog.message:find("Denoise excluded: 1", 1, true) ~= nil
)
assertTrue(
    lastDialog.message:find(
        "Denoise exclusion reasons: Required preset missing (1)",
        1,
        true
    ) ~= nil
)

BatchSummary.recordSkipped(incrementalSummary)
assertEqual(incrementalSummary.processed, 2)
assertEqual(incrementalSummary.skipped, 1)

for index = 1, 8 do
    BatchSummary.recordProcessedFailure(
        incrementalSummary,
        "Failure-" .. tostring(index) .. ".NEF",
        {
            category = "internal_error",
            code = "bounded_failure",
        }
    )
end
assertEqual(incrementalSummary.failed, 8)
assertEqual(#incrementalSummary.failures, 5)

local photoDialogText = table.concat(
    AutoDevelopConfirmationDialog.photoLines(
        incrementalOperation,
        12,
        100
    ),
    "\n"
)
for _, expected in ipairs({
    "Photo 12 of 100",
    "Filename: Incremental.NEF",
    "Selection: Auto",
    "Applied style: Architecture",
    "Editing intensity: Strong",
    "Develop Settings",
    "Composition crop: Recommended - prepared for application",
    "Leveling: Recommended - prepared for application",
    "Leveling mode: Rotation",
    "Transform Upright",
    "HDR",
    "Recommended: Yes",
    "Enabled: Unchanged",
    "Denoise: Recommended",
    "Denoise will be applied: No",
    "Warnings: 1",
    "Similar samples found: 5",
    "Average similarity: 0.91",
    "Personalization: Applied",
}) do
    assertTrue(photoDialogText:find(expected, 1, true) ~= nil)
end

modalDialogResult = "ok"
assertEqual(
    AutoDevelopConfirmationDialog.confirmPhoto(
        incrementalOperation,
        1,
        4
    ),
    "apply"
)
assertEqual(lastModalDialogOptions.actionVerb, "Apply")
assertEqual(lastModalDialogOptions.otherVerb, "Skip")
local normalScrollView = lastModalDialogOptions.contents[1]
local normalDetailsControl = normalScrollView[1]
assertEqual(normalDetailsControl.height_in_lines, -1)
assertEqual(normalDetailsControl.title, photoDialogText:gsub(
    "Photo 12 of 100",
    "Photo 1 of 4",
    1
))
assertTrue(lastModalDialogOptions.contents[2] ~= nil)

local invalidDisplayOperation = {
    photo = {},
    filename = "Invalid.NEF",
    originalSettings = { Exposure2012 = 0 },
    finalSettings = {},
}
modalDialogResult = "ok"
assertEqual(
    AutoDevelopConfirmationDialog.confirmPhoto(
        invalidDisplayOperation,
        1,
        1
    ),
    "skip"
)
assertEqual(lastModalDialogOptions.actionVerb, "Skip")
assertTrue(lastModalDialogOptions.otherVerb == nil)
assertTrue(lastModalDialogOptions.contents[2] == nil)
local invalidDetailsControl = lastModalDialogOptions.contents[1][1]
assertEqual(invalidDetailsControl.height_in_lines, -1)
assertTrue(
    invalidDetailsControl.title:find(
        "Pending operation contains no final develop settings.",
        1,
        true
    ) ~= nil
)
assertTrue(
    invalidDetailsControl.title:find(
        "Diagnostic code: missing_final_settings",
        1,
        true
    ) ~= nil
)

local unrenderableOperation = {
    photo = {},
    filename = "Unrenderable.NEF",
    originalSettings = { UnknownSetting = 0 },
    finalSettings = { UnknownSetting = 1 },
}
modalDialogResult = "ok"
assertEqual(
    AutoDevelopConfirmationDialog.confirmPhoto(
        unrenderableOperation,
        1,
        1
    ),
    "skip"
)
assertEqual(lastModalDialogOptions.actionVerb, "Skip")
assertTrue(
    lastModalDialogOptions.contents[1][1].title:find(
        "Diagnostic code: unrenderable_final_settings",
        1,
        true
    ) ~= nil
)

local originalReviewBuild = PendingOperationReview.build
PendingOperationReview.build = function()
    error("forced formatter failure")
end
modalDialogResult = "ok"
assertEqual(
    AutoDevelopConfirmationDialog.confirmPhoto(
        incrementalOperation,
        1,
        1
    ),
    "skip"
)
PendingOperationReview.build = originalReviewBuild
assertEqual(lastModalDialogOptions.actionVerb, "Skip")
assertTrue(lastModalDialogOptions.otherVerb == nil)
assertTrue(
    lastModalDialogOptions.contents[1][1].title:find(
        "Diagnostic code: confirmation_render_failed",
        1,
        true
    ) ~= nil
)
modalDialogResult = "other"
assertEqual(
    AutoDevelopConfirmationDialog.confirmPhoto(
        incrementalOperation,
        2,
        4
    ),
    "skip"
)
modalDialogResult = "cancel"
assertEqual(
    AutoDevelopConfirmationDialog.confirmPhoto(
        incrementalOperation,
        3,
        4
    ),
    "cancel_batch"
)
modalDialogResult = "apply_remaining"
assertEqual(
    AutoDevelopConfirmationDialog.confirmPhoto(
        incrementalOperation,
        4,
        4
    ),
    "apply_remaining"
)
modalDialogResult = "ok"
end

do
local function flowProgress()
    return {
        cancelled = false,
        captions = {},
        portions = {},
        isCanceled = function(self)
            return self.cancelled
        end,
        setCaption = function(self, caption)
            self.captions[#self.captions + 1] = caption
        end,
        setPortionComplete = function(self, complete, total)
            self.portions[#self.portions + 1] = {
                complete = complete,
                total = total,
            }
        end,
    }
end

local function flowPhotos(count)
    local photos = {}
    for index = 1, count do
        photos[index] = photo({
            localIdentifier = 1000 + index,
            fileName = "Flow-" .. tostring(index) .. ".NEF",
            fileFormat = "RAW",
        }, nil, {
            Exposure2012 = 0,
        })
    end
    return photos
end

local function flowOperation(currentPhoto, index)
    return PendingOperation.new({
        photo = currentPhoto,
        filename = "Flow-" .. tostring(index) .. ".NEF",
        requestId = "request-" .. tostring(index),
        requestedStyleId = "auto",
        effectiveStyleId = "architecture",
        editingIntensity = "strong",
        originalSettings = { Exposure2012 = 0 },
        mappedSettings = { Exposure2012 = 0.5 },
        model = "gpt_oss",
        resolvedModel = "test-model",
    })
end

local function flowOptions(count, confirmationMode)
    local flow = {
        events = {},
        decisions = {},
        confirmedOperations = {},
        appliedOperations = {},
        photos = flowPhotos(count),
        progress = flowProgress(),
    }
    local clock = 100
    flow.summary = BatchSummary.new(count, "develop")
    flow.preferences = {
        confirmationMode = confirmationMode,
        learningEnabled = true,
        learningCaptureBaseline = true,
        backendBaseUrl = "http://127.0.0.1:8005",
        requestTimeoutSeconds = 120,
    }
    flow.tracker = ProgressTracker.new(
        count,
        "Preparing recommendation",
        function()
            return clock
        end
    )
    flow.options = {
        photos = flow.photos,
        catalog = {},
        batchDirectory = "temporary-batch",
        progressScope = flow.progress,
        tracker = flow.tracker,
        summary = flow.summary,
        preferences = flow.preferences,
        preparePhoto = function(currentPhoto)
            local index = tonumber(
                Utils.photoFilename(currentPhoto):match("(%d+)")
            )
            flow.events[#flow.events + 1] =
                "prepare" .. tostring(index)
            return "ready", flowOperation(currentPhoto, index)
        end,
        confirmPhoto = function(operation, index)
            flow.events[#flow.events + 1] =
                "confirm" .. tostring(index)
            flow.confirmedOperations[index] = operation
            return flow.decisions[index] or "apply"
        end,
        applyOne = function(_, operation)
            local index = tonumber(operation.filename:match("(%d+)"))
            flow.events[#flow.events + 1] =
                "apply" .. tostring(index)
            flow.appliedOperations[index] = operation
            operation.applicationStatus = "applied"
            return {
                applied = 1,
                restoredAfterFailure = 0,
                failedNotRestored = 0,
                notApplied = 0,
                cancelled = false,
            }
        end,
        recordBaseline = function(operation)
            local index = tonumber(operation.filename:match("(%d+)"))
            flow.events[#flow.events + 1] =
                "baseline" .. tostring(index)
            return { saved = 1, failed = 0 }
        end,
        onRelease = function(operation)
            local index = tonumber(operation.filename:match("(%d+)"))
            flow.events[#flow.events + 1] =
                "release" .. tostring(index)
        end,
    }
    return flow
end

local confirmedFlow = flowOptions(3, "always")
confirmedFlow.decisions[2] = "skip"
AutoDevelopCommand.processSequential(confirmedFlow.options)
assertEqual(
    table.concat(confirmedFlow.events, ","),
    table.concat({
        "prepare1",
        "confirm1",
        "apply1",
        "baseline1",
        "release1",
        "prepare2",
        "confirm2",
        "release2",
        "prepare3",
        "confirm3",
        "apply3",
        "baseline3",
        "release3",
    }, ",")
)
assertEqual(confirmedFlow.summary.processed, 3)
assertEqual(confirmedFlow.summary.applied, 2)
assertEqual(confirmedFlow.summary.skipped, 1)
assertEqual(confirmedFlow.summary.learningBaselineSaved, 2)
assertTrue(
    confirmedFlow.confirmedOperations[1]
        == confirmedFlow.appliedOperations[1]
)
assertTrue(
    confirmedFlow.confirmedOperations[3]
        == confirmedFlow.appliedOperations[3]
)

local cancelledFlow = flowOptions(3, "always")
cancelledFlow.decisions[2] = "cancel_batch"
AutoDevelopCommand.processSequential(cancelledFlow.options)
assertEqual(cancelledFlow.summary.applied, 1)
assertEqual(cancelledFlow.summary.processed, 1)
assertEqual(cancelledFlow.summary.notProcessed, 2)
assertEqual(cancelledFlow.summary.cancelled, true)
assertTrue(
    table.concat(cancelledFlow.events, ","):find(
        "prepare3",
        1,
        true
    ) == nil
)

local remainingFlow = flowOptions(3, "always")
remainingFlow.decisions[1] = "apply_remaining"
AutoDevelopCommand.processSequential(remainingFlow.options)
assertEqual(remainingFlow.summary.applied, 3)
assertEqual(remainingFlow.preferences.confirmationMode, "always")
local remainingEvents = table.concat(remainingFlow.events, ",")
assertTrue(remainingEvents:find("confirm1", 1, true) ~= nil)
assertTrue(remainingEvents:find("confirm2", 1, true) == nil)
assertTrue(remainingEvents:find("confirm3", 1, true) == nil)
assertTrue(
    remainingFlow.confirmedOperations[1]
        == remainingFlow.appliedOperations[1]
)

local automaticFlow = flowOptions(3, "never")
automaticFlow.options.confirmPhoto = function()
    error("automatic mode must not display a confirmation")
end
AutoDevelopCommand.processSequential(automaticFlow.options)
assertEqual(automaticFlow.summary.applied, 3)
local automaticEvents = table.concat(automaticFlow.events, ",")
assertTrue(
    automaticEvents:find("apply1,baseline1,release1,prepare2", 1, true)
        ~= nil
)

local failureFlow = flowOptions(3, "never")
local defaultPrepare = failureFlow.options.preparePhoto
failureFlow.options.preparePhoto = function(currentPhoto)
    local filename = Utils.photoFilename(currentPhoto)
    if filename == "Flow-1.NEF" then
        failureFlow.events[#failureFlow.events + 1] = "prepare1"
        return "failed", {
            category = "invalid_response",
            code = "photo_failure",
        }
    end
    return defaultPrepare(currentPhoto)
end
AutoDevelopCommand.processSequential(failureFlow.options)
assertEqual(failureFlow.summary.failed, 1)
assertEqual(failureFlow.summary.applied, 2)
assertEqual(failureFlow.summary.processed, 3)

local terminalFlow = flowOptions(3, "never")
terminalFlow.options.preparePhoto = function()
    terminalFlow.events[#terminalFlow.events + 1] = "prepare1"
    return "failed", {
        category = "backend_not_running",
        code = "cannot_connect",
    }
end
AutoDevelopCommand.processSequential(terminalFlow.options)
assertEqual(terminalFlow.summary.failed, 1)
assertEqual(terminalFlow.summary.processed, 1)
assertEqual(terminalFlow.summary.notProcessed, 2)
assertEqual(terminalFlow.summary.terminalCategory, "backend_not_running")

local applyFailureFlow = flowOptions(2, "never")
applyFailureFlow.options.applyOne = function(_, operation)
    local index = tonumber(operation.filename:match("(%d+)"))
    applyFailureFlow.events[#applyFailureFlow.events + 1] =
        "apply" .. tostring(index)
    operation.applicationStatus = "restored"
    operation.applyErrorCategory = "apply_failed"
    operation.applyErrorCode = "lightroom_apply_failed"
    return {
        applied = 0,
        restoredAfterFailure = 1,
        failedNotRestored = 0,
        notApplied = 0,
        cancelled = false,
    }
end
AutoDevelopCommand.processSequential(applyFailureFlow.options)
assertEqual(applyFailureFlow.summary.failed, 2)
assertEqual(applyFailureFlow.summary.restoredAfterFailure, 2)
assertEqual(applyFailureFlow.summary.learningBaselineSaved, 0)
assertTrue(
    table.concat(applyFailureFlow.events, ","):find(
        "baseline",
        1,
        true
    ) == nil
)

local safePointFlow = flowOptions(2, "always")
safePointFlow.options.preparePhoto = function(currentPhoto)
    safePointFlow.events[#safePointFlow.events + 1] = "prepare1"
    safePointFlow.progress.cancelled = true
    return "ready", flowOperation(currentPhoto, 1)
end
AutoDevelopCommand.processSequential(safePointFlow.options)
assertEqual(safePointFlow.summary.applied, 0)
assertEqual(safePointFlow.summary.notProcessed, 2)
assertEqual(safePointFlow.summary.cancelled, true)
assertEqual(
    table.concat(safePointFlow.events, ","),
    "prepare1,release1"
)
end

assertEqual(
    ErrorClassifier.fromNetworkInfo({
        error = { errorCode = "timedOut" },
    }),
    "model_timeout"
)
assertEqual(
    ErrorClassifier.fromNetworkInfo({
        error = { errorCode = "networkConnectionLost" },
    }),
    "network_error"
)
assertEqual(
    ErrorClassifier.fromNetworkInfo({
        error = { errorCode = "cannotConnectToHost" },
    }),
    "backend_not_running"
)
assertEqual(
    ErrorClassifier.fromHttp(400, "profile_not_found"),
    "invalid_profile"
)
assertEqual(
    ErrorClassifier.fromHttp(400, "model_request_error"),
    "validation_error"
)
assertEqual(ErrorClassifier.fromHttp(500, "http_error"), "backend_error")
assertEqual(ErrorClassifier.fromHttp(502, "model_client_error"), "backend_error")
assertEqual(
    ErrorClassifier.fromHttp(502, "provider_unavailable"),
    "backend_error"
)
local now = 100
local tracker = ProgressTracker.new(4, "Analyzing", function()
    return now
end)
tracker:setCurrent("photo.nef")
assertTrue(tracker:estimatedRemainingSeconds() == nil)
now = 110
tracker:markCompleted(1)
assertEqual(tracker:estimatedRemainingSeconds(), 30)
assertEqual(ProgressTracker.formatDuration(65), "01:05")
assertEqual(ProgressTracker.formatDuration(0), "00:00")
assertEqual(ProgressTracker.formatDuration(5), "00:05")
assertEqual(ProgressTracker.formatDuration(3661), "1:01:01")
assertEqual(ProgressTracker.formatDuration(-10), "00:00")
assertTrue(tracker:caption():find("photo.nef", 1, true) ~= nil)
assertTrue(tracker:caption():find("1 / 4", 1, true) ~= nil)
tracker:setCurrent("current.nef", 2)
tracker:setBatchCounts({
    applied = 1,
    skipped = 0,
    failed = 1,
    processed = 2,
})
local batchCaption = tracker:caption()
assertTrue(batchCaption:find("Processing photo 2 of 4", 1, true) ~= nil)
assertTrue(batchCaption:find("Current: current.nef", 1, true) ~= nil)
assertTrue(batchCaption:find("Applied: 1", 1, true) ~= nil)
assertTrue(batchCaption:find("Skipped: 0", 1, true) ~= nil)
assertTrue(batchCaption:find("Failed: 1", 1, true) ~= nil)
assertTrue(batchCaption:find("Remaining: 2", 1, true) ~= nil)
now = 130
tracker:markCompleted(2)
assertEqual(tracker:estimatedRemainingSeconds(), 30)
tracker:markCompleted(99)
assertEqual(tracker.completed, 4)
assertTrue(tracker:estimatedRemainingSeconds() == nil)
local zeroTracker = ProgressTracker.new(0, "Applying", function()
    return 50
end)
zeroTracker:markCompleted(1)
assertEqual(zeroTracker.completed, 0)
assertTrue(zeroTracker:caption():find("Applying", 1, true) ~= nil)

local safeInternal = ErrorDialog.messageFor("internal_error", {
    raw = "<html>secret traceback</html>",
})
assertTrue(safeInternal:find("<html>", 1, true) == nil)
ErrorDialog.show("backend_not_running", {
    backendBaseUrl = "http://127.0.0.1:8005",
})
assertEqual(lastDialog.title, "AutoDevelop AI Backend Not Available")
assertTrue(
    lastDialog.message:find("http://127.0.0.1:8005", 1, true) ~= nil
)

local phaseSummary = BatchSummary.new(3, "analyze")
BatchSummary.addFailure(phaseSummary, "one.nef", {
    category = "network_error",
    code = "networkConnectionLost",
})
BatchSummary.addFailure(phaseSummary, "two.nef", {
    category = "invalid_response",
    code = "malformed_json",
})
local categories = BatchSummary.sortedCategories(phaseSummary)
assertEqual(categories[1], "invalid_response")
assertEqual(categories[2], "network_error")

local diagnosticSummary = BatchSummary.new(1, "develop")
diagnosticSummary.profileId = "natural_travel"
diagnosticSummary.confirmationMode = "always"
diagnosticSummary.models = {}
diagnosticSummary.examples = {}
BatchSummary.addFailure(diagnosticSummary, "photo.nef", {
    category = "internal_error",
    code = "preview_export_failed",
    stage = "preview_export_started",
})
lastDialog = nil
AutoDevelopConfirmationDialog.showFinal(diagnosticSummary, {
    applied = 0,
})
assertTrue(
    lastDialog.message:find(
        "Diagnostic code: preview_export_failed",
        1,
        true
    ) ~= nil
)
assertTrue(
    lastDialog.message:find(
        "Diagnostic stage: preview_export_started",
        1,
        true
    ) ~= nil
)

local unsafeDiagnosticSummary = BatchSummary.new(1, "develop")
unsafeDiagnosticSummary.profileId = "natural_travel"
unsafeDiagnosticSummary.confirmationMode = "always"
unsafeDiagnosticSummary.models = {}
unsafeDiagnosticSummary.examples = {}
BatchSummary.addFailure(unsafeDiagnosticSummary, "photo.nef", {
    category = "internal_error",
    code = "C:\\Users\\Person\\private.lua?token=secret",
    stage = "https://user:secret@example.test/private",
})
lastDialog = nil
AutoDevelopConfirmationDialog.showFinal(
    unsafeDiagnosticSummary,
    { applied = 0 }
)
assertTrue(
    lastDialog.message:find(
        "Diagnostic code: internal_error",
        1,
        true
    ) ~= nil
)
assertTrue(
    lastDialog.message:find(
        "Diagnostic stage: internal_error",
        1,
        true
    ) ~= nil
)
assertTrue(lastDialog.message:find("Users", 1, true) == nil)
assertTrue(lastDialog.message:find("token", 1, true) == nil)
assertTrue(lastDialog.message:find("example.test", 1, true) == nil)

local appliedLearningSummary = BatchSummary.new(1, "develop")
appliedLearningSummary.profileId = "natural_travel"
appliedLearningSummary.confirmationMode = "always"
appliedLearningSummary.models = {}
appliedLearningSummary.examples = {}
appliedLearningSummary.showLearningSummary = true
BatchSummary.recordLearning(appliedLearningSummary, {
    enabled = true,
    personalization_applied = true,
    usable_sample_count = 18,
    retrieved_sample_count = 5,
    minimum_sample_count = 3,
    average_similarity = 0.86,
})
lastDialog = nil
AutoDevelopConfirmationDialog.showFinal(
    appliedLearningSummary,
    { applied = 1 }
)
assertTrue(lastDialog.message:find("Learning\n---------", 1, true) ~= nil)
assertTrue(lastDialog.message:find("Enabled: Yes", 1, true) ~= nil)
assertTrue(
    lastDialog.message:find(
        "Usable feedback samples: 18",
        1,
        true
    ) ~= nil
)
assertTrue(
    lastDialog.message:find("Similar samples found: 5", 1, true) ~= nil
)
assertTrue(
    lastDialog.message:find("Average similarity: 0.86", 1, true) ~= nil
)
assertTrue(
    lastDialog.message:find("Personalization: Applied", 1, true) ~= nil
)

local insufficientLearningSummary = BatchSummary.new(1, "develop")
insufficientLearningSummary.profileId = "natural_travel"
insufficientLearningSummary.confirmationMode = "always"
insufficientLearningSummary.models = {}
insufficientLearningSummary.examples = {}
insufficientLearningSummary.showLearningSummary = true
BatchSummary.recordLearning(insufficientLearningSummary, {
    enabled = true,
    personalization_applied = false,
    usable_sample_count = 2,
    retrieved_sample_count = 0,
    minimum_sample_count = 3,
    average_similarity = nil,
    reason = "insufficient_samples",
})
lastDialog = nil
AutoDevelopConfirmationDialog.showFinal(
    insufficientLearningSummary,
    { applied = 1 }
)
assertTrue(
    lastDialog.message:find(
        "Usable feedback samples: 2",
        1,
        true
    ) ~= nil
)
assertTrue(lastDialog.message:find("Required: 3", 1, true) ~= nil)
assertTrue(
    lastDialog.message:find(
        "Personalization: Not applied",
        1,
        true
    ) ~= nil
)
assertTrue(
    lastDialog.message:find(
        "Reason: Insufficient feedback",
        1,
        true
    ) ~= nil
)

local mixedLearningSummary = BatchSummary.new(2, "develop")
mixedLearningSummary.profileId = "natural_travel"
mixedLearningSummary.confirmationMode = "always"
mixedLearningSummary.models = {}
mixedLearningSummary.examples = {}
mixedLearningSummary.showLearningSummary = true
BatchSummary.recordLearning(mixedLearningSummary, {
    enabled = true,
    personalization_applied = true,
    usable_sample_count = 18,
    retrieved_sample_count = 5,
    minimum_sample_count = 3,
    average_similarity = 0.86,
})
BatchSummary.recordLearning(mixedLearningSummary, {
    enabled = true,
    personalization_applied = false,
    usable_sample_count = 2,
    retrieved_sample_count = 0,
    minimum_sample_count = 3,
    reason = "insufficient_samples",
})
lastDialog = nil
AutoDevelopConfirmationDialog.showFinal(
    mixedLearningSummary,
    { applied = 2 }
)
assertTrue(
    lastDialog.message:find(
        "Usable feedback samples: 2-18",
        1,
        true
    ) ~= nil
)
assertTrue(
    lastDialog.message:find(
        "Similar samples found: 0-5",
        1,
        true
    ) ~= nil
)
assertTrue(
    lastDialog.message:find(
        "Personalization: Applied for 1 of 2 photos",
        1,
        true
    ) ~= nil
)

local disabledLearningSummary = BatchSummary.new(1, "develop")
disabledLearningSummary.profileId = "natural_travel"
disabledLearningSummary.confirmationMode = "always"
disabledLearningSummary.models = {}
disabledLearningSummary.examples = {}
disabledLearningSummary.showLearningSummary = true
BatchSummary.recordLearning(disabledLearningSummary, {
    enabled = false,
    personalization_applied = false,
    usable_sample_count = 0,
    retrieved_sample_count = 0,
    minimum_sample_count = 3,
    reason = "disabled",
})
lastDialog = nil
AutoDevelopConfirmationDialog.showFinal(
    disabledLearningSummary,
    { applied = 1 }
)
assertTrue(lastDialog.message:find("Enabled: No", 1, true) ~= nil)
assertTrue(
    lastDialog.message:find(
        "Reason: Disabled for this request",
        1,
        true
    ) ~= nil
)

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

local encoded = assert(Json.encode(request))
assertTrue(
    encoded:find("D:\\\\Temp", 1, true) ~= nil,
    "Windows path must be escaped in JSON"
)
local decodedRequest = assert(Json.decode(encoded))
assertEqual(decodedRequest.request_id, request.request_id)
assertEqual(decodedRequest.options.style_profile, "natural_travel")
assertEqual(decodedRequest.learning.enabled, true)

assertEqual(
    Sha256.digest(""),
    "e3b0c44298fc1c149afbf4c8996fb924"
        .. "27ae41e4649b934ca495991b7852b855"
)
assertEqual(
    Sha256.digest("abc"),
    "ba7816bf8f01cfea414140de5dae2223"
        .. "b00361a396177a9cb410ff61f20015ad"
)
assertEqual(
    LearningPhotoIdentity.forPhoto(mappedPhoto),
    "e88323fa27386e5982646f71b81d06c7"
        .. "c4dd78b7ddb4ee01d666170bc218b82b"
)
LearningSessionStore.put(
    LearningPhotoIdentity.forPhoto(mappedPhoto),
    {
        sessionId = "11111111-1111-4111-8111-111111111111",
        baselineTimestamp = "2026-07-29T00:00:00Z",
        profileId = "natural_travel",
        modelId = "qwen",
        filename = "Mapped.NEF",
    }
)
local learningPending = LearningSessionStore.get(
    LearningPhotoIdentity.forPhoto(mappedPhoto)
)
assertEqual(
    learningPending.sessionId,
    "11111111-1111-4111-8111-111111111111"
)
learningPending.filename = "Changed.NEF"
assertEqual(
    LearningSessionStore.get(
        LearningPhotoIdentity.forPhoto(mappedPhoto)
    ).filename,
    "Mapped.NEF"
)
assertTrue(learningPending.baselineSettings == nil)
LearningSessionStore.remove(LearningPhotoIdentity.forPhoto(mappedPhoto))
assertTrue(
    LearningSessionStore.get(
        LearningPhotoIdentity.forPhoto(mappedPhoto)
    ) == nil
)

local decodedValues = assert(Json.decode(
    '{"array":[1,false,null],"false_value":false,'
        .. '"null_value":null,"unicode":"\\u0041","zero":0}'
))
assertEqual(decodedValues.zero, 0)
assertEqual(decodedValues.false_value, false)
assertTrue(decodedValues.null_value == nil)
assertEqual(decodedValues.unicode, "A")
assertEqual(decodedValues.array[1], 1)
assertEqual(decodedValues.array[2], false)
assertTrue(decodedValues.array[3] == Json.null)

local deterministic = assert(Json.encode({ b = 2, a = 1 }))
assertEqual(deterministic, '{"a":1,"b":2}')
assertTrue(Json.decode('{"value":1} trailing') == nil)
assertTrue(Json.decode('{"value":}') == nil)
assertTrue(Json.encode({ value = 0 / 0 }) == nil)
assertTrue(Json.encode({ value = math.huge }) == nil)

local circular = {}
circular.self = circular
assertTrue(Json.encode(circular) == nil)

local diagnosticOperation = PendingOperation.new({
    requestedStyleId = "auto",
    effectiveStyleId = "natural_travel",
    styleSelectionMode = "auto",
    styleSelectionReason = "Scenic travel subject",
    editingIntensity = "strong",
    sceneConfidence = 0.91,
})
assertEqual(diagnosticOperation.requestedStyleId, "auto")
assertEqual(diagnosticOperation.effectiveStyleId, "natural_travel")
assertEqual(diagnosticOperation.editingIntensity, "strong")

local styleSummary = BatchSummary.new(2, "develop")
styleSummary.profileId = "auto"
styleSummary.confirmationMode = "always"
styleSummary.models = {}
styleSummary.resolvedModels = {}
styleSummary.examples = {}
BatchSummary.recordStyle(styleSummary, diagnosticOperation)
BatchSummary.recordStyle(styleSummary, PendingOperation.new({
    effectiveStyleId = "architecture",
    editingIntensity = "moderate",
}))
assertEqual(styleSummary.effectiveStyles.natural_travel, 1)
assertEqual(styleSummary.effectiveStyles.architecture, 1)
assertEqual(styleSummary.editingIntensities.strong, 1)
lastDialog = nil
AutoDevelopConfirmationDialog.showFinal(styleSummary, {})
assertTrue(lastDialog.message:find("Selection: Auto", 1, true) ~= nil)
assertTrue(
    lastDialog.message:find(
        "Style distribution: Architecture (1), Natural Travel (1)",
        1,
        true
    ) ~= nil
)
assertTrue(
    lastDialog.message:find(
        "Editing intensity distribution: Moderate (1), Strong (1)",
        1,
        true
    ) ~= nil
)

local analysisSummary = BatchSummary.new(1, "analyze")
analysisSummary.analyzed = 1
analysisSummary.profileId = "auto"
analysisSummary.styleDisplayName = "Auto"
analysisSummary.modelDisplayName = "Gemma"
analysisSummary.modelId = "gemma"
analysisSummary.resolvedModels = { ["gemma-4-31b"] = true }
analysisSummary.analysisExamples = {
    {
        filename = "photo_98765",
        photoId = "photo_98765",
        displayFilename = "Scenic.NEF",
        primarySubject = "Mountain landscape",
        lighting = "daylight",
        sceneCategory = "scenic_travel",
        effectiveStyleId = "natural_travel",
        editingIntensity = "strong",
        priorities = { "Recover sky detail", "Improve tonal separation" },
    },
}
lastDialog = nil
AnalysisSummaryDialog.show(analysisSummary)
assertTrue(lastDialog.message:find("Photo Analysis", 1, true) ~= nil)
assertTrue(lastDialog.message:find("Photo: Scenic.NEF", 1, true) ~= nil)
assertTrue(lastDialog.message:find("Photo: photo_98765", 1, true) == nil)
assertTrue(lastDialog.message:find("Mountain landscape", 1, true) ~= nil)
assertTrue(lastDialog.message:find("Natural Travel", 1, true) ~= nil)

modalDialogResult = "cancel"
LearningFeedbackDialog.confirm({
    selected = 1,
    pending = 1,
    changed = 0,
    unchanged = 1,
    missing = 0,
    previewFailed = 0,
    photoId = "photo_283285",
    displayFilename = "Feedback.JPG",
})
assertTrue(
    lastModalDialogOptions.contents[1].title:find(
        "Photo: Feedback.JPG",
        1,
        true
    ) ~= nil
)
assertTrue(
    lastModalDialogOptions.contents[1].title:find(
        "Photo: photo_283285",
        1,
        true
    ) == nil
)
modalDialogResult = "ok"

print("Lua assertions passed: " .. tostring(assertions))
