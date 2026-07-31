local LrApplication = import("LrApplication")
local LrBinding = import("LrBinding")
local LrDialogs = import("LrDialogs")
local LrFunctionContext = import("LrFunctionContext")
local LrPathUtils = import("LrPathUtils")
local LrTasks = import("LrTasks")
local LrView = import("LrView")

local function safeCall(callback)
    local ok, value = LrTasks.pcall(callback)
    if ok then
        return value
    end
    return nil
end

local function lightroomVersion()
    local version = safeCall(function()
        return LrApplication.versionTable()
    end)
    if type(version) ~= "table" then
        return "unknown"
    end
    local parts = {}
    for _, key in ipairs({ "major", "minor", "revision", "build" }) do
        if version[key] ~= nil then
            parts[#parts + 1] = tostring(version[key])
        end
    end
    if #parts == 0 then
        return "unknown"
    end
    return table.concat(parts, ".")
end

local function photoFilename(photo)
    local formatted = safeCall(function()
        return photo:getFormattedMetadata("fileName")
    end)
    if type(formatted) == "string" and formatted ~= "" then
        return formatted
    end

    local raw = safeCall(function()
        return photo:getRawMetadata("fileName")
    end)
    if type(raw) == "string" and raw ~= "" then
        return raw
    end

    local path = safeCall(function()
        return photo:getRawMetadata("path")
    end)
    if type(path) == "string" and path ~= "" then
        return LrPathUtils.leafName(path)
    end
    return "unknown"
end

local function sortedKeys(value)
    local keys = {}
    for key in pairs(value) do
        keys[#keys + 1] = key
    end
    table.sort(keys, function(left, right)
        local leftType = type(left)
        local rightType = type(right)
        if leftType == rightType then
            return tostring(left) < tostring(right)
        end
        return leftType < rightType
    end)
    return keys
end

local function scalarText(value)
    if type(value) == "string" then
        return string.format("%q", value)
    end
    return tostring(value)
end

local function appendValue(lines, path, value, seen)
    local valueType = type(value)
    if valueType ~= "table" then
        lines[#lines + 1] = string.format(
            "%s [%s] = %s",
            path,
            valueType,
            scalarText(value)
        )
        return
    end

    if seen[value] then
        lines[#lines + 1] = string.format(
            "%s [table] = <cycle:%s>",
            path,
            seen[value]
        )
        return
    end

    seen[value] = path
    local keys = sortedKeys(value)
    lines[#lines + 1] = string.format(
        "%s [table] = <%d entries>",
        path,
        #keys
    )
    for _, key in ipairs(keys) do
        appendValue(
            lines,
            path .. "[" .. scalarText(key) .. "]",
            value[key],
            seen
        )
    end
end

local function buildSnapshot(label, photo, settings)
    local lines = {
        "=== AutoDevelop AI Develop Settings Probe ===",
        "captured_at = " .. os.date("!%Y-%m-%dT%H:%M:%SZ"),
        "lightroom_version = " .. lightroomVersion(),
        "scenario = " .. label,
        "filename = " .. photoFilename(photo),
        "setting_count = " .. tostring(#sortedKeys(settings)),
        "--- settings begin ---",
    }

    local seen = {}
    for _, key in ipairs(sortedKeys(settings)) do
        appendValue(
            lines,
            "settings[" .. scalarText(key) .. "]",
            settings[key],
            seen
        )
    end
    lines[#lines + 1] = "--- settings end ---"
    lines[#lines + 1] = ""
    return table.concat(lines, "\n")
end

local function appendSnapshot(snapshot)
    local documents = LrPathUtils.getStandardFilePath("documents")
    if type(documents) ~= "string" or documents == "" then
        return nil, "Lightroom could not resolve the Documents folder."
    end

    local logPath = LrPathUtils.child(
        documents,
        "AutoDevelopAI-DevelopSettingsProbe.log"
    )
    local handle, openError = io.open(logPath, "a")
    if not handle then
        return nil, tostring(openError or "Could not open the log file.")
    end

    local ok, writeError = handle:write(snapshot)
    handle:close()
    if not ok then
        return nil, tostring(writeError or "Could not write the log file.")
    end
    return logPath, nil
end

local function promptForScenario()
    local selected = nil
    LrFunctionContext.callWithContext(
        "developSettingsProbeScenario",
        function(context)
            local properties = LrBinding.makePropertyTable(context)
            properties.scenario = "Baseline"
            local factory = LrView.osFactory()
            local result = LrDialogs.presentModalDialog({
                title = "Develop Settings Probe",
                contents = factory:column({
                    bind_to_object = properties,
                    spacing = factory:control_spacing(),
                    factory:static_text({
                        title = "Select the state currently shown "
                            .. "in Lightroom:",
                    }),
                    factory:popup_menu({
                        value = LrView.bind("scenario"),
                        items = {
                            { title = "Baseline", value = "Baseline" },
                            {
                                title = "Upright Auto",
                                value = "Upright Auto",
                            },
                            {
                                title = "Upright Level",
                                value = "Upright Level",
                            },
                            {
                                title = "Upright Vertical",
                                value = "Upright Vertical",
                            },
                            {
                                title = "Upright Full",
                                value = "Upright Full",
                            },
                            { title = "HDR On", value = "HDR On" },
                            { title = "HDR Off", value = "HDR Off" },
                        },
                    }),
                }),
                actionVerb = "Capture",
            })
            if result == "ok" then
                selected = properties.scenario
            end
        end
    )
    return selected
end

LrTasks.startAsyncTask(function()
    local catalog = LrApplication.activeCatalog()
    local photo = catalog and catalog:getTargetPhoto() or nil
    if not photo then
        LrDialogs.message(
            "Develop Settings Probe",
            "Select one photo in Lightroom and try again.",
            "warning"
        )
        return
    end

    local label = promptForScenario()
    if type(label) ~= "string" or label == "" then
        return
    end

    local settings = safeCall(function()
        return photo:getDevelopSettings()
    end)
    if type(settings) ~= "table" then
        LrDialogs.message(
            "Develop Settings Probe",
            "Lightroom did not return a Develop settings table.",
            "critical"
        )
        return
    end

    local snapshot = buildSnapshot(label, photo, settings)
    local logPath, writeError = appendSnapshot(snapshot)
    if not logPath then
        LrDialogs.message(
            "Develop Settings Probe",
            writeError,
            "critical"
        )
        return
    end

    LrDialogs.message(
        "Develop Settings Probe",
        "Captured " .. tostring(#sortedKeys(settings))
            .. " settings for " .. photoFilename(photo)
            .. ".\n\nLog: " .. logPath,
        "info"
    )
end)
