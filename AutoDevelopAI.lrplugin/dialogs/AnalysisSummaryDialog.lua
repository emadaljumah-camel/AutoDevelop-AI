local LrDialogs = import("LrDialogs")

local BatchSummary = ModuleLoader.load("lib/BatchSummary.lua")
local ErrorDialog = ModuleLoader.load("dialogs/ErrorDialog.lua")
local ProgressTracker = ModuleLoader.load("lib/ProgressTracker.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")

local AnalysisSummaryDialog = {}

local function summaryText(summary)
    local lines = {
        "Selected: " .. tostring(summary.selected),
        "Analyzed successfully: " .. tostring(summary.analyzed),
        "Failed: " .. tostring(summary.failed),
        "Skipped: " .. tostring(summary.skipped),
        "Not processed: " .. tostring(summary.notProcessed),
        "Style: "
            .. Utils.safeMessage(summary.styleDisplayName, "unavailable"),
        "Profile ID: " .. Utils.safeMessage(summary.profileId, "unavailable"),
        "Cancelled: " .. (summary.cancelled and "yes" or "no"),
        "Elapsed: "
            .. ProgressTracker.formatDuration(summary.elapsedSeconds or 0),
    }

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
    end

    if summary.terminalCategory then
        lines[#lines + 1] = ""
        lines[#lines + 1] =
            ErrorDialog.messageFor(summary.terminalCategory, summary)
    end

    if #summary.failures > 0 then
        lines[#lines + 1] = ""
        lines[#lines + 1] = "Examples:"
        for _, failure in ipairs(summary.failures) do
            lines[#lines + 1] = "- "
                .. Utils.safeMessage(failure.filename, "Photo")
                .. ": "
                .. ErrorDialog.messageFor(failure.category, summary)
        end
    end
    return table.concat(lines, "\n")
end

function AnalysisSummaryDialog.show(summary)
    local messageType = "info"
    if summary.failed > 0 or summary.skipped > 0
        or summary.notProcessed > 0 or summary.cancelled then
        messageType = "warning"
    end
    LrDialogs.message(
        "AutoDevelop AI - Analyze Selected Photos",
        summaryText(summary),
        messageType
    )
end

return AnalysisSummaryDialog
