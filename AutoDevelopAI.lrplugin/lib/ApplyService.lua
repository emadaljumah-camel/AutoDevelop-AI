local LrTasks = import("LrTasks")

local CropMapper = ModuleLoader.load("lib/CropMapper.lua")
local DevelopModeMapper =
    ModuleLoader.load("lib/DevelopModeMapper.lua")
local DevelopSettingsMapper =
    ModuleLoader.load("lib/DevelopSettingsMapper.lua")
local DenoisePresetService =
    ModuleLoader.load("lib/DenoisePresetService.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")

local ApplyService = {}

local function isAllowedKey(key)
    return DevelopSettingsMapper.isSupportedKey(key)
        or CropMapper.isSupportedKey(key)
        or key == "EnableTransform"
        or key == "PerspectiveUpright"
        or key == "HDREditMode"
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

local function sanitizeRestore(settings)
    local safe = sanitize(settings)
    if type(settings) == "table" then
        if type(settings.EnableTransform) == "boolean" then
            safe.EnableTransform = settings.EnableTransform
        end
        local upright = DevelopModeMapper.decodeUpright(
            settings.PerspectiveUpright
        )
        if upright.supported then
            safe.PerspectiveUpright = upright.rawValue
        end
    end
    if type(settings) == "table"
        and Utils.isFiniteNumber(settings.HDREditMode)
        and (
            settings.HDREditMode == 0
            or settings.HDREditMode == 1
        ) then
        safe.HDREditMode = settings.HDREditMode
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

local function restoreForOperation(operation)
    local restore = sanitizeRestore(operation.originalSettings)
    local denoiseRestore = DenoisePresetService.sanitizeRestore(
        operation.denoiseOriginalSettings
    )
    for key, value in pairs(denoiseRestore) do
        restore[key] = value
    end
    return restore
end

local function validDenoiseOperation(operation)
    if operation.denoiseIncluded ~= true then
        return true
    end
    return operation.denoisePreset ~= nil
        and type(operation.denoise) == "table"
        and DenoisePresetService.isSupportedAmount(
            operation.denoise.amount
        )
        and type(operation.denoiseOriginalSettings) == "table"
        and type(operation.denoiseOriginalSettings.FilterList) == "table"
end

function ApplyService.captureOriginal(currentSettings, mappedSettings)
    local original = {}
    if type(currentSettings) ~= "table"
        or type(mappedSettings) ~= "table" then
        return original
    end
    for key in pairs(mappedSettings) do
        local value = currentSettings[key]
        if isAllowedKey(key)
            and (
                Utils.isFiniteNumber(value)
                or type(value) == "boolean"
            ) then
            original[key] = value
        end
    end
    return original
end

function ApplyService.sanitize(settings)
    return sanitize(settings)
end

function ApplyService.prepareFinalSettings(
    mappedSettings,
    currentSettings,
    uprightMode,
    enableHdr
)
    local finalSettings = sanitize(mappedSettings)
    local currentUpright = type(currentSettings) == "table"
        and DevelopModeMapper.decodeUpright(
            currentSettings.PerspectiveUpright
        ) or { supported = false }
    local mappedUpright = DevelopModeMapper.encodeUpright(uprightMode)
    if currentUpright.supported and mappedUpright ~= nil then
        finalSettings.EnableTransform = true
        finalSettings.PerspectiveUpright = mappedUpright
    end
    if enableHdr == true
        and type(currentSettings) == "table"
        and (
            currentSettings.HDREditMode == 0
            or currentSettings.HDREditMode == 1
        ) then
        finalSettings.HDREditMode = 1
    end
    return finalSettings
end

function ApplyService.validateFinalSettings(settings)
    if type(settings) ~= "table" then
        return false
    end
    local validated = sanitize(settings)
    if settings.EnableTransform ~= nil then
        if type(settings.EnableTransform) ~= "boolean" then
            return false
        end
        validated.EnableTransform = settings.EnableTransform
    end
    if settings.PerspectiveUpright ~= nil then
        local upright = DevelopModeMapper.decodeUpright(
            settings.PerspectiveUpright
        )
        if not upright.supported then
            return false
        end
        validated.PerspectiveUpright = upright.rawValue
    end
    if settings.HDREditMode ~= nil then
        local hdr = DevelopModeMapper.decodeHdr(settings.HDREditMode)
        if not hdr.supported then
            return false
        end
        validated.HDREditMode = hdr.rawValue
    end
    local suppliedCount = countSettings(settings)
    if suppliedCount == 0
        or countSettings(validated) ~= suppliedCount then
        return false
    end
    for key, value in pairs(settings) do
        if validated[key] ~= value then
            return false
        end
    end
    return true
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
        writeErrorCategory = nil,
        writeErrorCode = nil,
    }

    if isCancelled() then
        result.cancelled = true
        result.notApplied = #operations
        for _, operation in ipairs(operations) do
            operation.applicationStatus = "not_applied"
        end
        return result
    end

    local writeOk = LrTasks.pcall(function()
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

                    local finalSettings = operation.finalSettings
                    local finalSettingCount = countSettings(finalSettings)
                    local finalSettingsValid = finalSettingCount == 0
                        or ApplyService.validateFinalSettings(finalSettings)
                    if not finalSettingsValid
                        or not validDenoiseOperation(operation)
                        or (
                            finalSettingCount == 0
                            and operation.denoiseIncluded ~= true
                        ) then
                        operation.applicationStatus = "not_applied"
                        operation.applyErrorCategory = "apply_failed"
                        operation.applyErrorCode =
                            "invalid_final_settings"
                        result.notApplied = result.notApplied + 1
                    else
                        local applyOk = LrTasks.pcall(function()
                            if operation.denoiseIncluded == true then
                                operation.photo:applyDevelopPreset(
                                    operation.denoisePreset,
                                    "AutoDevelop AI"
                                )
                            end
                            if finalSettingCount > 0 then
                                operation.photo:applyDevelopSettings(
                                    finalSettings,
                                    "AutoDevelop AI"
                                )
                            end
                        end)
                        if applyOk then
                            operation.denoiseApplied =
                                operation.denoiseIncluded == true
                            operation.applicationStatus = "applied"
                            result.applied = result.applied + 1
                        else
                            operation.denoiseApplied = false
                            local restoreSettings =
                                restoreForOperation(operation)
                            local restoreOk = false
                            if countSettings(restoreSettings) > 0 then
                                restoreOk = LrTasks.pcall(function()
                                    operation.photo:applyDevelopSettings(
                                        restoreSettings,
                                        "AutoDevelop AI: Restore"
                                    )
                                end)
                            end
                            operation.applyErrorCategory = "apply_failed"
                            operation.applyErrorCode =
                                "lightroom_apply_failed"
                            operation.applyError =
                                "Lightroom could not apply the prepared settings."
                            if restoreOk then
                                operation.applicationStatus = "restored"
                                result.restoredAfterFailure =
                                    result.restoredAfterFailure + 1
                            else
                                operation.restoreErrorCategory =
                                    "restore_failed"
                                operation.restoreErrorCode =
                                    "lightroom_restore_failed"
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
        result.writeError =
            "Lightroom catalog write access failed."
        result.writeErrorCategory = "write_access_failed"
        result.writeErrorCode = "catalog_write_access_failed"
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

function ApplyService.applyOne(catalog, operation, options)
    if type(operation) ~= "table" then
        return {
            applied = 0,
            restoredAfterFailure = 0,
            failedNotRestored = 0,
            notApplied = 1,
            cancelled = false,
            writeError =
                "No prepared photo operation was supplied.",
            writeErrorCategory = "apply_failed",
            writeErrorCode = "invalid_operation",
        }
    end
    return ApplyService.applyBatch(catalog, { operation }, options)
end

return ApplyService
