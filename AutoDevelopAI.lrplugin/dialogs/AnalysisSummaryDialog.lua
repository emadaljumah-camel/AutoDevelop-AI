local LrDialogs = import("LrDialogs")

local BatchSummary = ModuleLoader.load("lib/BatchSummary.lua")
local ErrorDialog = ModuleLoader.load("dialogs/ErrorDialog.lua")
local ProgressTracker = ModuleLoader.load("lib/ProgressTracker.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")
local StyleProfiles = ModuleLoader.load("lib/StyleProfiles.lua")

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
        "Model: "
            .. Utils.safeMessage(summary.modelDisplayName, "unavailable"),
        "Model ID: " .. Utils.safeMessage(summary.modelId, "unavailable"),
        "Cancelled: " .. (summary.cancelled and "yes" or "no"),
        "Composition crop recommended: "
            .. tostring(summary.cropRecommendedCount or 0),
        "Leveling recommended: "
            .. tostring(summary.levelingRecommendedCount or 0),
        "Elapsed: "
            .. ProgressTracker.formatDuration(summary.elapsedSeconds or 0),
    }
    local resolved = {}
    for identifier in pairs(summary.resolvedModels or {}) do
        resolved[#resolved + 1] = identifier
    end
    table.sort(resolved)
    lines[#lines + 1] = "Resolved model: "
        .. (#resolved > 0 and table.concat(resolved, ", ") or "unavailable")
    if Utils.isFiniteNumber(summary.levelingAngleMinimum)
        and Utils.isFiniteNumber(summary.levelingAngleMaximum) then
        lines[#lines + 1] = string.format(
            "Leveling angle range: %+.2f to %+.2f degrees",
            summary.levelingAngleMinimum,
            summary.levelingAngleMaximum
        )
    end

    for _, example in ipairs(summary.analysisExamples or {}) do
        lines[#lines + 1] = ""
        lines[#lines + 1] = "Photo Analysis"
        lines[#lines + 1] = "--------------"
        lines[#lines + 1] = "Photo: "
            .. Utils.safeMessage(
                example.displayFilename,
                example.filename or example.photoId or "Photo"
            )
        lines[#lines + 1] = "Primary subject: "
            .. Utils.safeMessage(example.primarySubject, "unavailable")
        lines[#lines + 1] = "Lighting: "
            .. Utils.safeMessage(example.lighting, "unavailable")
        lines[#lines + 1] = "Scene: "
            .. Utils.safeMessage(example.sceneCategory, "unavailable")
        lines[#lines + 1] = "Recommended style: "
            .. Utils.safeMessage(
                StyleProfiles.getDisplayName(example.effectiveStyleId),
                "unavailable"
            )
        local intensity = Utils.safeMessage(
            example.editingIntensity,
            "unavailable"
        ):gsub("_", " ")
        lines[#lines + 1] = "Editing intensity: " .. intensity
        lines[#lines + 1] = "Composition crop: "
            .. (example.cropRecommended and "Recommended" or "Not needed")
        if example.levelingRecommended then
            local mode = Utils.safeMessage(
                example.levelingMode,
                "rotation"
            ):gsub("_", " ")
            lines[#lines + 1] = string.format(
                "Level correction: %s, %+.2f degrees",
                mode,
                example.levelingAngle or 0
            )
        else
            lines[#lines + 1] = "Level correction: Not needed"
        end
        lines[#lines + 1] = "Editing priorities"
        lines[#lines + 1] = "------------------"
        local count = 0
        for _, priority in ipairs(example.priorities or {}) do
            if count >= 4 then
                break
            end
            lines[#lines + 1] = "- "
                .. Utils.safeMessage(priority, "Improve the current image")
            count = count + 1
        end
        if count == 0 then
            lines[#lines + 1] = "- No priorities supplied"
        end
    end

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
