local LrApplication = import("LrApplication")
local LrDialogs = import("LrDialogs")
local LrPathUtils = import("LrPathUtils")
local LrPrefs = import("LrPrefs")
local LrTasks = import("LrTasks")

local preferences = LrPrefs.prefsForPlugin()

local function safeDevelopSettings(photo)
    local ok, settings = LrTasks.pcall(function()
        return photo:getDevelopSettings()
    end)
    if not ok or type(settings) ~= "table" then
        return nil
    end
    return settings
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

local function applySettings(catalog, photo, settings)
    local ok, result = LrTasks.pcall(function()
        return catalog:withWriteAccessDo(
            "AutoDevelop AI: Restore Develop Mode Probe",
            function()
                photo:applyDevelopSettings(
                    settings,
                    "AutoDevelop AI: Restore Develop Mode Probe"
                )
            end
        )
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

local function clearState()
    preferences.applicationProbeActive = nil
    preferences.applicationProbeOperation = nil
    preferences.applicationProbeField = nil
    preferences.applicationProbeExpectedValue = nil
    preferences.applicationProbeOriginalValue = nil
    preferences.applicationProbeOriginalEnableTransform = nil
    preferences.applicationProbePhotoIdentity = nil
    preferences.applicationProbeFilename = nil
end

LrTasks.startAsyncTask(function()
    if preferences.applicationProbeActive ~= true then
        LrDialogs.message(
            "Develop Mode Application Probe",
            "No temporary application probe is active.",
            "info"
        )
        return
    end

    local catalog = LrApplication.activeCatalog()
    local photo = catalog and catalog:getTargetPhoto() or nil
    if not photo
        or photoIdentity(photo)
            ~= preferences.applicationProbePhotoIdentity then
        LrDialogs.message(
            "Develop Mode Application Probe",
            "Select the same test photo before restoring the probe.",
            "critical"
        )
        return
    end

    local operation = preferences.applicationProbeOperation
    local field = preferences.applicationProbeField
    local expected = preferences.applicationProbeExpectedValue
    local beforeRestore = safeDevelopSettings(photo)
    local observedValue = beforeRestore and beforeRestore[field] or nil

    local verdict = LrDialogs.confirm(
        "Record Lightroom UI Result",
        "Did Lightroom's Develop UI show " .. tostring(operation) .. "?",
        "UI Matches",
        "UI Does Not Match",
        "Could Not Verify"
    )

    local restore = {
        [field] = preferences.applicationProbeOriginalValue,
    }
    if field == "PerspectiveUpright" then
        restore.EnableTransform =
            preferences.applicationProbeOriginalEnableTransform
    end
    local restoreOk, restoreResult =
        applySettings(catalog, photo, restore)
    local restored = safeDevelopSettings(photo)
    local restoredValue = restored and restored[field] or nil
    local restoreMatches = restoreOk
        and restoredValue == preferences.applicationProbeOriginalValue

    local lines = {
        "=== AutoDevelop AI Develop Mode Application Probe Result ===",
        "captured_at = " .. os.date("!%Y-%m-%dT%H:%M:%SZ"),
        "filename = " .. tostring(preferences.applicationProbeFilename),
        "operation = " .. tostring(operation),
        "field = " .. tostring(field),
        "expected_value = " .. tostring(expected),
        "value_before_restore = " .. tostring(observedValue),
        "value_still_matches = " .. tostring(observedValue == expected),
        "ui_verdict = " .. tostring(verdict),
        "restore_ok = " .. tostring(restoreOk),
        "restore_result = " .. tostring(restoreResult),
        "restored_value = " .. tostring(restoredValue),
        "restore_matches = " .. tostring(restoreMatches),
        "",
    }
    local logPath, logError = appendResult(lines)
    if restoreMatches then
        clearState()
    end
    LrDialogs.message(
        "Develop Mode Application Probe Complete",
        "Restore match: " .. tostring(restoreMatches)
            .. "\n\nLog: " .. tostring(logPath or logError),
        restoreMatches and "info" or "critical"
    )
end)
