local LrApplication = import("LrApplication")
local LrTasks = import("LrTasks")

local Utils = ModuleLoader.load("lib/Utils.lua")

local DenoisePresetService = {}
local presetNames = {
    [25] = "AutoDevelop AI - Denoise 25",
    [50] = "AutoDevelop AI - Denoise 50",
    [75] = "AutoDevelop AI - Denoise 75",
}
local presetCache = {}

local function normalizedAmount(value)
    if not Utils.isFiniteNumber(value)
        or value ~= math.floor(value)
        or not presetNames[value] then
        return nil
    end
    return value
end

local function containsDenoise(value, seen)
    local valueType = type(value)
    if valueType == "string" then
        return value:lower():find("denoise", 1, true) ~= nil
    end
    if valueType ~= "table" then
        return false
    end
    seen = seen or {}
    if seen[value] then
        return false
    end
    seen[value] = true
    for key, child in pairs(value) do
        if containsDenoise(key, seen) or containsDenoise(child, seen) then
            seen[value] = nil
            return true
        end
    end
    seen[value] = nil
    return false
end

local function findPreset(amount)
    if presetCache[amount] then
        return presetCache[amount], nil
    end
    local name = presetNames[amount]
    local foldersOk, folders = LrTasks.pcall(function()
        return LrApplication.developPresetFolders()
    end)
    if not foldersOk or type(folders) ~= "table" then
        return nil, "denoise_preset_lookup_failed"
    end
    for _, folder in ipairs(folders) do
        local presetsOk, presets = LrTasks.pcall(function()
            return folder:getDevelopPresets()
        end)
        if presetsOk and type(presets) == "table" then
            for _, preset in ipairs(presets) do
                local nameOk, candidateName = LrTasks.pcall(function()
                    return preset:getName()
                end)
                if nameOk and candidateName == name then
                    presetCache[amount] = preset
                    return preset, nil
                end
            end
        end
    end
    return nil, "denoise_preset_missing"
end

local function sourceFormat(photo)
    local value = Utils.trim(Utils.safeRawMetadata(photo, "fileFormat"))
    return value and value:upper() or nil
end

local function captureOriginal(currentSettings)
    local original = {}
    if type(currentSettings) ~= "table"
        or type(currentSettings.FilterList) ~= "table" then
        return original
    end
    original.FilterList = Utils.deepCopy(currentSettings.FilterList)
    if Utils.isFiniteNumber(currentSettings.ColorNoiseReduction) then
        original.ColorNoiseReduction = currentSettings.ColorNoiseReduction
    end
    return original
end

function DenoisePresetService.prepare(
    photo,
    currentSettings,
    requestedAmount
)
    local amount = normalizedAmount(requestedAmount)
    if not amount then
        return {
            ready = false,
            code = "denoise_preset_amount_unsupported",
            reason = "No verified Denoise preset matches the recommended amount.",
        }
    end
    local format = sourceFormat(photo)
    if format ~= "RAW" and format ~= "DNG" then
        return {
            ready = false,
            amount = amount,
            code = "denoise_source_unsupported",
            reason = "Lightroom AI Denoise requires a supported RAW or DNG source.",
        }
    end
    if type(currentSettings) ~= "table"
        or type(currentSettings.FilterList) ~= "table" then
        return {
            ready = false,
            amount = amount,
            code = "denoise_baseline_unavailable",
            reason = "The current Lightroom Denoise state cannot be restored safely.",
        }
    end
    if containsDenoise(currentSettings.FilterList) then
        return {
            ready = false,
            amount = amount,
            code = "denoise_already_enabled",
            reason = "Lightroom AI Denoise is already enabled for this photo.",
        }
    end

    local preset, presetError = findPreset(amount)
    if not preset then
        return {
            ready = false,
            amount = amount,
            code = presetError,
            reason = "Required Lightroom preset not found: "
                .. presetNames[amount],
        }
    end
    return {
        ready = true,
        amount = amount,
        preset = preset,
        presetName = presetNames[amount],
        originalSettings = captureOriginal(currentSettings),
    }
end

function DenoisePresetService.sanitizeRestore(settings)
    return captureOriginal(settings)
end

function DenoisePresetService.isSupportedAmount(value)
    return normalizedAmount(value) ~= nil
end

function DenoisePresetService.containsDenoise(value)
    return containsDenoise(value)
end

function DenoisePresetService.presetName(value)
    local amount = normalizedAmount(value)
    return amount and presetNames[amount] or nil
end

return DenoisePresetService
