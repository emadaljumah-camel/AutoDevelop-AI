package.path = "AutoDevelopAI.lrplugin/?.lua;"
    .. "AutoDevelopAI.lrplugin/?/init.lua;"
    .. package.path

local assertions = 0
local fakePreferences = {}
local logged = {
    error = {},
    warning = {},
    info = {},
    debug = {},
}
local lastDialog = nil
local lastPropertyTable = nil
local modalDialogResult = "ok"
local modalDialogMutator = nil

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
                if modalDialogMutator then
                    modalDialogMutator(options, lastPropertyTable)
                end
                return modalDialogResult
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
    ModuleLoader.load("lib/StyleRunCoordinator.lua")
local StyleSelectionDialog =
    ModuleLoader.load("dialogs/StyleSelectionDialog.lua")
local PluginManagerController =
    ModuleLoader.load("lib/PluginManagerController.lua")
local ExifMapper = ModuleLoader.load("lib/ExifMapper.lua")
local RequestBuilder = ModuleLoader.load("lib/RequestBuilder.lua")
local Validation = ModuleLoader.load("lib/Validation.lua")
local BatchPolicy = ModuleLoader.load("lib/BatchPolicy.lua")
local BatchSummary = ModuleLoader.load("lib/BatchSummary.lua")
local ErrorClassifier = ModuleLoader.load("lib/ErrorClassifier.lua")
local ApplicationGate = ModuleLoader.load("lib/ApplicationGate.lua")
local BatchOperationRecorder =
    ModuleLoader.load("lib/BatchOperationRecorder.lua")
local ProgressTracker = ModuleLoader.load("lib/ProgressTracker.lua")
local Logger = ModuleLoader.load("lib/Logger.lua")
local ErrorDialog = ModuleLoader.load("dialogs/ErrorDialog.lua")
local AutoDevelopConfirmationDialog =
    ModuleLoader.load("dialogs/AutoDevelopConfirmationDialog.lua")
local ResultStore = ModuleLoader.load("lib/ResultStore.lua")
local DevelopSettingsMapper =
    ModuleLoader.load("lib/DevelopSettingsMapper.lua")
local CropMapper = ModuleLoader.load("lib/CropMapper.lua")
local PendingOperation = ModuleLoader.load("lib/PendingOperation.lua")
local ApplyService = ModuleLoader.load("lib/ApplyService.lua")

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
        styleProfileId = "natural_travel",
        uuidFactory = function()
            return "12345678-1234-4abc-8abc-1234567890ab"
        end,
    }
))
assertEqual(request.schema_version, "1.0")
assertEqual(request.options.style_profile, "natural_travel")
assertEqual(request.current_settings.Exposure2012, 0)
assertEqual(request.preview_path, "D:\\Temp\\AutoDevelopAI\\preview.jpg")
assertEqual(StyleProfiles.getDefaultId(), "natural_travel")
assertTrue(
    RequestBuilder.build(mappedPhoto, "D:\\Temp\\missing-style.jpg", {
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
assertEqual(Config.SCHEMA_VERSION, "1.0")
fakePreferences.backendBaseUrl = nil
fakePreferences.styleProfileId = nil
fakePreferences.requestTimeoutSeconds = nil
fakePreferences.applyCrop = nil
fakePreferences.confirmationMode = nil
fakePreferences.loggingLevel = nil
assertEqual(
    Preferences.getBackendBaseUrl(),
    "http://127.0.0.1:8005"
)
assertEqual(Preferences.getStyleProfileId(), "natural_travel")
assertEqual(Preferences.getRequestTimeoutSeconds(), 120)
assertEqual(Preferences.getApplyCrop(), true)
assertEqual(Preferences.getConfirmationMode(), "always")
assertEqual(Preferences.getLoggingLevel(), "info")
fakePreferences.applyCrop = nil
assertEqual(Preferences.getApplyCrop(), true)
fakePreferences.applyCrop = false
assertEqual(Preferences.getApplyCrop(), false)
fakePreferences.applyCrop = nil

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
assertEqual(defaults.applyCrop, true)
assertEqual(defaults.confirmationMode, "always")
assertEqual(defaults.loggingLevel, "info")

local profileChoices = Preferences.getStyleProfileChoices()
assertEqual(#profileChoices, 7)
assertEqual(profileChoices[1].title, "Natural Travel")
assertEqual(profileChoices[1].value, "natural_travel")
assertEqual(profileChoices[2].value, "landscape_impact")
assertEqual(profileChoices[3].value, "architecture")
assertEqual(profileChoices[4].value, "stock_neutral")
assertEqual(profileChoices[5].value, "portrait")
assertEqual(profileChoices[6].value, "night")
assertEqual(profileChoices[7].value, "documentary")
profileChoices[1].title = "Mutated"
assertEqual(
    Preferences.getStyleProfileChoices()[1].title,
    "Natural Travel",
    "choice getters must return defensive copies"
)

assertEqual(StyleProfiles.getDefaultId(), "natural_travel")
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
assertEqual(initialStyle, "natural_travel")
assertEqual(invalidStored, true)
local copiedStyle = StyleProfiles.getById("natural_travel")
copiedStyle.displayName = "Mutated"
assertEqual(
    StyleProfiles.getDisplayName("natural_travel"),
    "Natural Travel",
    "style metadata getters must return defensive copies"
)

fakePreferences.styleProfileId = "natural_travel"
modalDialogResult = "cancel"
modalDialogMutator = nil
local cancelledDialogResult =
    StyleSelectionDialog.show("natural_travel")
assertEqual(cancelledDialogResult.confirmed, false)
assertEqual(fakePreferences.styleProfileId, "natural_travel")

modalDialogResult = "ok"
modalDialogMutator = function(_, properties)
    properties.selectedProfileId = "documentary"
    properties._observers.selectedProfileId()
    properties.rememberAsDefault = false
end
local documentaryDialogResult =
    StyleSelectionDialog.show("natural_travel")
assertEqual(documentaryDialogResult.confirmed, true)
assertEqual(documentaryDialogResult.profileId, "documentary")
assertEqual(documentaryDialogResult.rememberAsDefault, false)
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
    properties.rememberAsDefault = true
end
local rememberedDialogResult =
    StyleSelectionDialog.show("natural_travel")
assertEqual(rememberedDialogResult.profileId, "architecture")
assertEqual(rememberedDialogResult.rememberAsDefault, true)
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
StyleSelectionDialog.show("removed_profile")
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
    return StyleRunCoordinator.begin({
        dialogResult = dialogResult,
        validateProfile = StyleProfiles.isValidId,
        persistDefault = persistDefault or function()
            return true
        end,
        snapshotFactory = snapshotFactory or function(profileId)
            return {
                styleProfileId = profileId,
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
        rememberAsDefault = false,
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
local photos = { "one", "two", "three" }
local documentaryPreparation = StyleRunCoordinator.prepare(
    documentaryRun,
    photos,
    function(runPhotos, snapshot)
        for index = 1, #runPhotos do
            receivedProfiles[index] = snapshot.styleProfileId
        end
        snapshot.styleProfileId = "mutated"
        return #runPhotos
    end
)
assertEqual(documentaryPreparation.status, "completed")
assertEqual(documentaryPreparation.prepared, 3)
for index = 1, #photos do
    assertEqual(receivedProfiles[index], "documentary")
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
        rememberAsDefault = true,
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
assertEqual(managerProperties.applyCrop, defaults.applyCrop)
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
    edit_plan = {},
    model = "fake-autodevelop-v1",
}
assertTrue(Validation.validateAnalyzeResponse(successfulResponse, request))
local invalidAnalyzeModel = Utils.deepCopy(successfulResponse)
invalidAnalyzeModel.model =
    "https://user:pass@example.com/model?token=secret"
assertTrue(
    not Validation.validateAnalyzeResponse(invalidAnalyzeModel, request)
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

local fixtureFile = assert(io.open(
    "tests/fixtures/develop_response.json",
    "rb"
))
local fixtureJson = fixtureFile:read("*a")
fixtureFile:close()
local wireDevelopResponse = assert(Json.decode(fixtureJson))
local wireValid, wireValidationError, wireModel =
    Validation.validateDevelopResponse(
        wireDevelopResponse,
        developRequest
    )
assertTrue(wireValid, wireValidationError)
assertEqual(wireModel, "fake-autodevelop-v1")
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
        true,
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
    cropIncluded = false,
    denoiseRecommended =
        wireDevelopResponse.denoise.recommended == true,
    warnings = wireDevelopResponse.warnings,
    model = wireModel,
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
    wireSummary.models["fake-autodevelop-v1"],
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
local failingPhoto = {
    applyDevelopSettings = function(_, values)
        restoreCalls = restoreCalls + 1
        if restoreCalls == 1 then
            error("C:\\Users\\Person\\secret-preview.jpg?token=secret")
        end
        restoredValue = values.Exposure2012
    end,
}
local restoreOperation = PendingOperation.new({
    photo = failingPhoto,
    mappedSettings = { Exposure2012 = 1 },
    originalSettings = { Exposure2012 = 0 },
})
local restoreResult = ApplyService.applyBatch(
    fakeCatalog,
    { restoreOperation }
)
assertEqual(restoreResult.restoredAfterFailure, 1)
assertEqual(restoreResult.failedNotRestored, 0)
assertEqual(restoredValue, 0)
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
    { ok = false, status = 500, category = "backend_error" },
    0,
    false
))
assertTrue(BatchPolicy.shouldRetry(
    { ok = false, status = 502, category = "backend_error" },
    0,
    false
))
assertTrue(BatchPolicy.shouldRetry(
    { ok = false, category = "model_timeout" },
    0,
    false
))
assertTrue(not BatchPolicy.shouldRetry(
    { ok = false, status = 400, category = "validation_error" },
    0,
    false
))
assertTrue(not BatchPolicy.shouldRetry(
    { ok = false, status = 500, category = "backend_error" },
    1,
    false
))
assertTrue(not BatchPolicy.shouldRetry(
    { ok = false, status = 502, category = "backend_error" },
    0,
    true
))

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

print("Lua assertions passed: " .. tostring(assertions))
