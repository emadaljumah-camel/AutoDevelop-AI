local LrTasks = import("LrTasks")

local CropMapper = ModuleLoader.load("lib/CropMapper.lua")
local DevelopSettingsMapper =
    ModuleLoader.load("lib/DevelopSettingsMapper.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")

local ApplyService = {}

local function isAllowedKey(key)
    return DevelopSettingsMapper.isSupportedKey(key)
        or CropMapper.isSupportedKey(key)
end

local function sanitize(settings)
    local safe = {}
    if type(settings) ~= "table" then
        return safe
    end
    for key, value in pairs(settings) do
        if DevelopSettingsMapper.isSupportedKey(key)
            and Utils.isFiniteNumber(value) then
            safe[key] = value
        end
    end
    local safeCrop = CropMapper.sanitizeMapped(settings)
    for key, value in pairs(safeCrop) do
        safe[key] = value
    end
    return safe
end

local function countSettings(settings)
    local count = 0
    for _ in pairs(settings) do
        count = count + 1
    end
    return count
end

function ApplyService.captureOriginal(currentSettings, mappedSettings)
    local original = {}
    if type(currentSettings) ~= "table"
        or type(mappedSettings) ~= "table" then
        return original
    end
    for key in pairs(mappedSettings) do
        local value = currentSettings[key]
        if isAllowedKey(key) and Utils.isFiniteNumber(value) then
            original[key] = value
        end
    end
    return original
end

function ApplyService.sanitize(settings)
    return sanitize(settings)
end

function ApplyService.applyBatch(catalog, operations, options)
    options = options or {}
    local isCancelled = options.isCancelled or function()
        return false
    end
    local onProgress = options.onProgress or function()
    end
    local result = {
        applied = 0,
        restoredAfterFailure = 0,
        failedNotRestored = 0,
        notApplied = 0,
        cancelled = false,
        writeError = nil,
    }

    local writeOk, writeError = LrTasks.pcall(function()
        return catalog:withWriteAccessDo(
            "AutoDevelop AI: Apply Develop Settings",
            function()
                for index, operation in ipairs(operations) do
                    if isCancelled() then
                        result.cancelled = true
                        result.notApplied =
                            result.notApplied + (#operations - index + 1)
                        break
                    end
                    onProgress(index, #operations, operation)

                    local safeSettings = sanitize(operation.mappedSettings)
                    if countSettings(safeSettings) == 0 then
                        operation.applicationStatus = "not_applied"
                        result.notApplied = result.notApplied + 1
                    else
                        local applyOk, applyError = LrTasks.pcall(function()
                            operation.photo:applyDevelopSettings(
                                safeSettings,
                                "AutoDevelop AI"
                            )
                        end)
                        if applyOk then
                            operation.applicationStatus = "applied"
                            result.applied = result.applied + 1
                        else
                            local restoreSettings =
                                sanitize(operation.originalSettings)
                            local restoreOk = false
                            if countSettings(restoreSettings) > 0 then
                                restoreOk = LrTasks.pcall(function()
                                    operation.photo:applyDevelopSettings(
                                        restoreSettings,
                                        "AutoDevelop AI: Restore"
                                    )
                                end)
                            end
                            operation.applyError = Utils.safeMessage(
                                applyError,
                                "Develop settings could not be applied."
                            )
                            if restoreOk then
                                operation.applicationStatus = "restored"
                                result.restoredAfterFailure =
                                    result.restoredAfterFailure + 1
                            else
                                operation.applicationStatus =
                                    "failed_not_restored"
                                result.failedNotRestored =
                                    result.failedNotRestored + 1
                            end
                        end
                    end
                end
            end
        )
    end)

    if not writeOk then
        result.writeError = Utils.safeMessage(
            writeError,
            "Could not obtain Lightroom catalog write access."
        )
        result.notApplied = #operations
        result.applied = 0
        result.restoredAfterFailure = 0
        result.failedNotRestored = 0
        for _, operation in ipairs(operations) do
            operation.applicationStatus = "not_applied"
        end
    end
    return result
end

return ApplyService
