local LrApplication = import("LrApplication")
local LrBinding = import("LrBinding")
local LrDialogs = import("LrDialogs")
local LrFunctionContext = import("LrFunctionContext")
local LrPathUtils = import("LrPathUtils")
local LrPrefs = import("LrPrefs")
local LrTasks = import("LrTasks")
local LrView = import("LrView")

local preferences = LrPrefs.prefsForPlugin()

local function canonicalMapperPath()
    local toolsDirectory = LrPathUtils.parent(_PLUGIN.path)
    local repositoryDirectory = LrPathUtils.parent(toolsDirectory)
    return LrPathUtils.child(
        LrPathUtils.child(
            LrPathUtils.child(repositoryDirectory, "AutoDevelopAI.lrplugin"),
            "lib"
        ),
        "DevelopModeMapper.lua"
    )
end

local mapperOk, DevelopModeMapper = pcall(dofile, canonicalMapperPath())
if not mapperOk or type(DevelopModeMapper) ~= "table" then
    LrDialogs.message(
        "Develop Mode Application Probe",
        "The canonical DevelopModeMapper.lua could not be loaded. "
            .. "Add this diagnostic plug-in directly from the repository.",
        "critical"
    )
    return
end

local function safeDevelopSettings(photo)
    local ok, settings = LrTasks.pcall(function()
        return photo:getDevelopSettings()
    end)
    if not ok or type(settings) ~= "table" then
        return nil
    end
    return settings
end

local function photoFilename(photo)
    local ok, filename = LrTasks.pcall(function()
        return photo:getFormattedMetadata("fileName")
    end)
    if ok and type(filename) == "string" and filename ~= "" then
        return filename
    end
    return "unknown"
end

local function photoIdentity(photo)
    local ok, localIdentifier = LrTasks.pcall(function()
        return photo:getRawMetadata("localIdentifier")
    end)
    if ok and localIdentifier ~= nil then
        return "local:" .. tostring(localIdentifier)
    end
    local pathOk, path = LrTasks.pcall(function()
        return photo:getRawMetadata("path")
    end)
    if pathOk and type(path) == "string" and path ~= "" then
        return "path:" .. path
    end
    return nil
end

local function chooseOperation()
    local selected = nil
    LrFunctionContext.callWithContext(
        "developModeApplicationProbe",
        function(context)
            local properties = LrBinding.makePropertyTable(context)
            properties.operation = "upright:auto"
            local factory = LrView.osFactory()
            local result = LrDialogs.presentModalDialog({
                title = "Develop Mode Application Probe",
                contents = factory:column({
                    bind_to_object = properties,
                    spacing = factory:control_spacing(),
                    factory:static_text({
                        title = "Select the Lightroom mode to apply temporarily:",
                    }),
                    factory:popup_menu({
                        value = LrView.bind("operation"),
                        items = {
                            {
                                title = "Upright Off",
                                value = "upright:off",
                            },
                            {
                                title = "Upright Auto",
                                value = "upright:auto",
                            },
                            {
                                title = "Upright Full",
                                value = "upright:full",
                            },
                            {
                                title = "Upright Level",
                                value = "upright:level",
                            },
                            {
                                title = "Upright Vertical",
                                value = "upright:vertical",
                            },
                            { title = "HDR Off", value = "hdr:false" },
                            { title = "HDR On", value = "hdr:true" },
                        },
                    }),
                }),
                actionVerb = "Apply Temporarily",
            })
            if result == "ok" then
                selected = properties.operation
            end
        end
    )
    return selected
end

local function operationSettings(operation, original)
    local kind, value = operation:match("^([^:]+):(.+)$")
    if kind == "upright" then
        if type(original.EnableTransform) ~= "boolean"
            or type(original.PerspectiveUpright) ~= "number" then
            return nil, nil, nil,
                "Lightroom did not expose restorable Upright values."
        end
        local rawValue, reason = DevelopModeMapper.encodeUpright(value)
        if rawValue == nil then
            return nil, nil, nil, reason
        end
        return {
            EnableTransform = true,
            PerspectiveUpright = rawValue,
        }, {
            EnableTransform = original.EnableTransform,
            PerspectiveUpright = original.PerspectiveUpright,
        }, "PerspectiveUpright", nil
    end
    if kind == "hdr" then
        local decoded = DevelopModeMapper.decodeHdr(original.HDREditMode)
        if not decoded.supported then
            return nil, nil, nil,
                "Lightroom did not expose a restorable HDREditMode value."
        end
        local rawValue, reason =
            DevelopModeMapper.encodeHdr(value == "true")
        if rawValue == nil then
            return nil, nil, nil, reason
        end
        return {
            HDREditMode = rawValue,
        }, {
            HDREditMode = original.HDREditMode,
        }, "HDREditMode", nil
    end
    return nil, nil, nil, "Unknown diagnostic operation."
end

local function applySettings(catalog, photo, settings, label)
    local ok, result = LrTasks.pcall(function()
        return catalog:withWriteAccessDo(label, function()
            photo:applyDevelopSettings(settings, label)
        end)
    end)
    return ok, result
end

local function appendResult(lines)
    local documents = LrPathUtils.getStandardFilePath("documents")
    local logPath = LrPathUtils.child(
        documents,
        "AutoDevelopAI-DevelopSettingsProbe.log"
    )
    local handle, openError = io.open(logPath, "a")
    if not handle then
        return nil, tostring(openError or "Could not open the probe log.")
    end
    handle:write(table.concat(lines, "\n") .. "\n")
    handle:close()
    return logPath, nil
end

LrTasks.startAsyncTask(function()
    if preferences.applicationProbeActive == true then
        LrDialogs.message(
            "Develop Mode Application Probe",
            "A temporary probe setting is already active. Run "
                .. "'Record Upright/HDR Result and Restore' first.",
            "warning"
        )
        return
    end

    local catalog = LrApplication.activeCatalog()
    local photo = catalog and catalog:getTargetPhoto() or nil
    if not photo then
        LrDialogs.message(
            "Develop Mode Application Probe",
            "Select one disposable test RAW and try again.",
            "warning"
        )
        return
    end

    local operation = chooseOperation()
    if not operation then
        return
    end
    local original = safeDevelopSettings(photo)
    if not original then
        LrDialogs.message(
            "Develop Mode Application Probe",
            "Lightroom did not return the original Develop settings.",
            "critical"
        )
        return
    end

    local target, restore, field, preparationError =
        operationSettings(operation, original)
    if not target then
        LrDialogs.message(
            "Develop Mode Application Probe",
            tostring(preparationError),
            "critical"
        )
        return
    end

    local applyOk, applyResult = applySettings(
        catalog,
        photo,
        target,
        "AutoDevelop AI: Verify Develop Mode"
    )
    local applied = safeDevelopSettings(photo)
    local expected = target[field]
    local actual = applied and applied[field] or nil
    local readbackMatches = applyOk and actual == expected

    local lines = {
        "=== AutoDevelop AI Develop Mode Application Probe Start ===",
        "captured_at = " .. os.date("!%Y-%m-%dT%H:%M:%SZ"),
        "filename = " .. photoFilename(photo),
        "operation = " .. operation,
        "field = " .. field,
        "original_value = " .. tostring(original[field]),
        "expected_value = " .. tostring(expected),
        "apply_ok = " .. tostring(applyOk),
        "apply_result = " .. tostring(applyResult),
        "readback_value = " .. tostring(actual),
        "readback_matches = " .. tostring(readbackMatches),
        "",
    }
    local logPath, logError = appendResult(lines)

    if not readbackMatches then
        applySettings(
            catalog,
            photo,
            restore,
            "AutoDevelop AI: Restore Failed Develop Mode Probe"
        )
        LrDialogs.message(
            "Develop Mode Application Probe",
            "The raw Lightroom value did not match. The probe attempted "
                .. "an immediate restore.\n\nLog: "
                .. tostring(logPath or logError),
            "critical"
        )
        return
    end

    local identity = photoIdentity(photo)
    if not identity then
        applySettings(
            catalog,
            photo,
            restore,
            "AutoDevelop AI: Restore Untracked Develop Mode Probe"
        )
        LrDialogs.message(
            "Develop Mode Application Probe",
            "The selected photo could not be identified safely. "
                .. "The original values were restored.",
            "critical"
        )
        return
    end

    preferences.applicationProbeActive = true
    preferences.applicationProbeOperation = operation
    preferences.applicationProbeField = field
    preferences.applicationProbeExpectedValue = expected
    preferences.applicationProbeOriginalValue = restore[field]
    preferences.applicationProbeOriginalEnableTransform =
        restore.EnableTransform
    preferences.applicationProbePhotoIdentity = identity
    preferences.applicationProbeFilename = photoFilename(photo)

    LrDialogs.message(
        "Temporary Develop Mode Applied",
        "Operation: " .. operation
            .. "\nRead-back matched: true"
            .. "\n\nDismiss this dialog, switch to Develop, and inspect "
            .. "the Transform or HDR UI. Then run "
            .. "'Record Upright/HDR Result and Restore'."
            .. "\n\nDo not change the selected photo.",
        "info"
    )
end)
