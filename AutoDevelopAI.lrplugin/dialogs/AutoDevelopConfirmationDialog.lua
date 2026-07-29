local LrDialogs = import("LrDialogs")

local Utils = require("lib.Utils")

local AutoDevelopConfirmationDialog = {}

local function modelSummary(summary)
    local names = {}
    for name in pairs(summary.models or {}) do
        names[#names + 1] = name
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
        "Profile: " .. Utils.safeMessage(summary.profileId, "unavailable"),
        "Model: " .. modelSummary(summary),
        "Crop changes: " .. tostring(summary.cropCount),
        "Denoise recommended but not applied: "
            .. tostring(summary.denoiseIgnored),
        "Warnings: " .. tostring(summary.warningCount),
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
    lines[#lines + 1] = "Restored after failure: "
        .. tostring(application.restoredAfterFailure or 0)
    lines[#lines + 1] = "Failed and not restored: "
        .. tostring(application.failedNotRestored or 0)
    lines[#lines + 1] = "Not applied: "
        .. tostring(application.notApplied or 0)

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
