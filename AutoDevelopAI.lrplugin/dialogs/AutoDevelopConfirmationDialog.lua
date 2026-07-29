local LrDialogs = import("LrDialogs")

local BatchSummary = ModuleLoader.load("lib/BatchSummary.lua")
local ErrorDialog = ModuleLoader.load("dialogs/ErrorDialog.lua")
local ProgressTracker = ModuleLoader.load("lib/ProgressTracker.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")
local Validation = ModuleLoader.load("lib/Validation.lua")

local AutoDevelopConfirmationDialog = {}

local function modelSummary(summary)
    local names = {}
    for name in pairs(summary.models or {}) do
        local identifier = Validation.validateModelIdentifier(name)
        if identifier then
            names[#names + 1] = identifier
        end
    end
    table.sort(names)
    if #names == 0 then
        return "unavailable"
    end
    if #names == 1 then
        return names[1]
    end
    return "mixed: " .. table.concat(names, ", ")
end

local function preparationLines(summary)
    return {
        "Selected: " .. tostring(summary.selected),
        "Ready to apply: " .. tostring(summary.ready),
        "Failed: " .. tostring(summary.failed),
        "Skipped: " .. tostring(summary.skipped),
        "Not processed: " .. tostring(summary.notProcessed),
        "Style: "
            .. Utils.safeMessage(summary.styleDisplayName, "unavailable"),
        "Profile ID: " .. Utils.safeMessage(summary.profileId, "unavailable"),
        "Confirmation: "
            .. Utils.safeMessage(summary.confirmationMode, "not applicable"),
        "Model: " .. modelSummary(summary),
        "Crop changes: " .. tostring(summary.cropCount),
        "Crop recommended but disabled: "
            .. tostring(summary.cropDisabled or 0),
        "Denoise recommended but not applied: "
            .. tostring(summary.denoiseIgnored),
        "Warnings: " .. tostring(summary.warningCount),
        "Elapsed: "
            .. ProgressTracker.formatDuration(summary.elapsedSeconds or 0),
    }
end

local function examples(summary)
    local lines = {}
    if #(summary.examples or {}) == 0 then
        return lines
    end
    lines[#lines + 1] = ""
    lines[#lines + 1] = "Examples:"
    for _, example in ipairs(summary.examples) do
        lines[#lines + 1] = "- "
            .. Utils.safeMessage(example.filename, "Photo")
            .. ": "
            .. tostring(example.settingCount)
            .. " settings, crop "
            .. (example.cropIncluded and "yes" or "no")
            .. ", warnings "
            .. tostring(example.warningCount)
    end
    return lines
end

function AutoDevelopConfirmationDialog.confirm(summary)
    local lines = preparationLines(summary)
    for _, line in ipairs(examples(summary)) do
        lines[#lines + 1] = line
    end
    lines[#lines + 1] = ""
    lines[#lines + 1] =
        "No photo has been modified yet. Apply these prepared changes?"
    local choice = LrDialogs.confirm(
        "AutoDevelop AI - Confirm Develop Settings",
        table.concat(lines, "\n"),
        "Apply",
        "Cancel"
    )
    return choice == "ok"
end

function AutoDevelopConfirmationDialog.showFinal(summary, application)
    application = application or {}
    local lines = preparationLines(summary)
    lines[#lines + 1] = "Cancelled: "
        .. (summary.cancelled and "yes" or "no")
    lines[#lines + 1] = ""
    lines[#lines + 1] = "Applied: " .. tostring(application.applied or 0)
    lines[#lines + 1] = "Crop applied: "
        .. tostring(application.cropApplied or 0)
    lines[#lines + 1] = "Restored after failure: "
        .. tostring(application.restoredAfterFailure or 0)
    lines[#lines + 1] = "Failed and not restored: "
        .. tostring(application.failedNotRestored or 0)
    lines[#lines + 1] = "Not applied: "
        .. tostring(application.notApplied or 0)

    local categories = BatchSummary.sortedCategories(summary)
    if #categories > 0 then
        lines[#lines + 1] = ""
        lines[#lines + 1] = "Failure categories:"
        for _, category in ipairs(categories) do
            lines[#lines + 1] = "- "
                .. ErrorDialog.details(category).title
                .. ": "
                .. tostring(summary.failureCategories[category])
        end
        local firstFailure = summary.failures
            and summary.failures[1] or nil
        if firstFailure then
            lines[#lines + 1] = "Diagnostic code: "
                .. Utils.safeErrorCode(
                    firstFailure.code,
                    "internal_error"
                )
            if firstFailure.stage then
                lines[#lines + 1] = "Diagnostic stage: "
                    .. Utils.safeErrorCode(
                        firstFailure.stage,
                        "internal_error"
                    )
            end
        end
    end

    if summary.terminalCategory and not summary.cancelled then
        lines[#lines + 1] = ""
        lines[#lines + 1] =
            ErrorDialog.messageFor(summary.terminalCategory, summary)
    end

    if application.writeError then
        lines[#lines + 1] = ""
        lines[#lines + 1] = Utils.safeMessage(
            application.writeError,
            "Catalog write access failed."
        )
    elseif application.userCancelled then
        lines[#lines + 1] = ""
        lines[#lines + 1] = "The batch was cancelled before application."
    end

    local messageType = "info"
    if summary.failed > 0
        or summary.skipped > 0
        or summary.notProcessed > 0
        or summary.cancelled
        or (application.failedNotRestored or 0) > 0
        or application.writeError then
        messageType = "warning"
    end
    LrDialogs.message(
        "AutoDevelop AI - Auto Develop Selected Photos",
        table.concat(lines, "\n"),
        messageType
    )
end

return AutoDevelopConfirmationDialog
