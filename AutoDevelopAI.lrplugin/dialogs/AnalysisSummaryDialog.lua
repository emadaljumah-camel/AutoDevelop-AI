local LrDialogs = import("LrDialogs")

local Utils = require("lib.Utils")

local AnalysisSummaryDialog = {}

local function summaryText(summary)
    local lines = {
        "Selected: " .. tostring(summary.selected),
        "Analyzed successfully: " .. tostring(summary.analyzed),
        "Failed: " .. tostring(summary.failed),
        "Skipped: " .. tostring(summary.skipped),
        "Not processed: " .. tostring(summary.notProcessed),
        "Cancelled: " .. (summary.cancelled and "yes" or "no"),
    }

    if summary.backendUnavailable then
        lines[#lines + 1] = ""
        lines[#lines + 1] =
            "The backend could not be reached. Check that AutoDevelop AI "
            .. "is running on port 8005."
    end

    if #summary.failures > 0 then
        lines[#lines + 1] = ""
        lines[#lines + 1] = "Examples:"
        for _, failure in ipairs(summary.failures) do
            lines[#lines + 1] = "- "
                .. Utils.safeMessage(failure.filename, "Photo")
                .. ": "
                .. Utils.safeMessage(failure.reason, "Analysis failed.")
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
