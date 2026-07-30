local LrDialogs = import("LrDialogs")

local BatchSummary = ModuleLoader.load("lib/BatchSummary.lua")
local ErrorDialog = ModuleLoader.load("dialogs/ErrorDialog.lua")
local ProgressTracker = ModuleLoader.load("lib/ProgressTracker.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")
local Validation = ModuleLoader.load("lib/Validation.lua")
local StyleProfiles = ModuleLoader.load("lib/StyleProfiles.lua")

local AutoDevelopConfirmationDialog = {}

local learningReasonLabels = {
    disabled = "Disabled for this request",
    database_unavailable = "Learning database unavailable",
    embedding_unavailable = "Image comparison unavailable",
    insufficient_samples = "Insufficient feedback",
    no_similar_samples = "Insufficient similar feedback",
    retrieval_unavailable = "Learning retrieval unavailable",
}

local function rangeText(minimum, maximum)
    if minimum == nil or maximum == nil then
        return "unavailable"
    end
    if minimum == maximum then
        return tostring(minimum)
    end
    return tostring(minimum) .. "-" .. tostring(maximum)
end

local function appendLearningLines(lines, summary, includeBaselineResults)
    if not summary.showLearningSummary
        and (summary.learningBaselineFailed or 0) == 0 then
        return
    end
    lines[#lines + 1] = ""
    lines[#lines + 1] = "Learning"
    lines[#lines + 1] = "---------"
    local diagnosticCount = summary.learningDiagnosticsCount or 0
    if diagnosticCount > 0 then
        lines[#lines + 1] = "Enabled: "
            .. (summary.learningEnabled and "Yes" or "No")
        lines[#lines + 1] = "Usable feedback samples: "
            .. rangeText(
                summary.learningUsableMinimum,
                summary.learningUsableMaximum
            )
        local applied = summary.personalizationApplied or 0
        if applied > 0 or (summary.learningRetrievedMaximum or 0) > 0 then
            lines[#lines + 1] = "Similar samples found: "
                .. rangeText(
                    summary.learningRetrievedMinimum,
                    summary.learningRetrievedMaximum
                )
        end
        if (summary.learningSimilarityCount or 0) > 0 then
            lines[#lines + 1] = "Average similarity: "
                .. string.format(
                    "%.2f",
                    summary.learningSimilarityTotal
                        / summary.learningSimilarityCount
                )
        end
        if applied > 0 then
            lines[#lines + 1] = "Personalization: "
                .. (
                    applied == diagnosticCount
                    and "Applied"
                    or (
                        "Applied for "
                        .. tostring(applied)
                        .. " of "
                        .. tostring(diagnosticCount)
                        .. " photos"
                    )
                )
        else
            lines[#lines + 1] = "Required: "
                .. rangeText(
                    summary.learningRequiredMinimum,
                    summary.learningRequiredMaximum
                )
            lines[#lines + 1] = "Personalization: Not applied"
            if summary.learningReason then
                lines[#lines + 1] = "Reason: "
                    .. (
                        learningReasonLabels[summary.learningReason]
                        or "Unavailable"
                    )
            end
        end
    else
        lines[#lines + 1] = "Enabled: unavailable"
        lines[#lines + 1] = "Personalization: Not applied"
        lines[#lines + 1] = "Reason: Diagnostics unavailable"
    end
    if includeBaselineResults then
        lines[#lines + 1] = "Learning baseline saved: "
            .. tostring(summary.learningBaselineSaved or 0)
        lines[#lines + 1] = "Learning baseline save failed: "
            .. tostring(summary.learningBaselineFailed or 0)
    end
end

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

local function resolvedModelSummary(summary)
    local names = {}
    for name in pairs(summary.resolvedModels or {}) do
        local identifier = Validation.validateModelIdentifier(name)
        if identifier then
            names[#names + 1] = identifier
        end
    end
    table.sort(names)
    return #names > 0 and table.concat(names, ", ") or "unavailable"
end

local function sortedCounts(values, display)
    local entries = {}
    for identifier, count in pairs(values or {}) do
        entries[#entries + 1] = {
            id = identifier,
            count = count,
            label = display and display(identifier) or identifier,
        }
    end
    table.sort(entries, function(left, right)
        return left.id < right.id
    end)
    return entries
end

local function appendStyleLines(lines, summary)
    lines[#lines + 1] = ""
    lines[#lines + 1] = "Style"
    lines[#lines + 1] = "-----"
    lines[#lines + 1] = "Selection: "
        .. (summary.profileId == "auto" and "Auto" or "Manual")
    local styles = sortedCounts(
        summary.effectiveStyles,
        StyleProfiles.getDisplayName
    )
    if #styles == 1 then
        lines[#lines + 1] = "Applied style: " .. styles[1].label
    elseif #styles > 1 then
        local parts = {}
        for index, item in ipairs(styles) do
            if index > 4 then
                break
            end
            parts[#parts + 1] = item.label .. " (" .. item.count .. ")"
        end
        if #styles > 4 then
            parts[#parts + 1] = "+" .. tostring(#styles - 4) .. " more"
        end
        lines[#lines + 1] = "Applied style: Multiple - "
            .. table.concat(parts, ", ")
    else
        lines[#lines + 1] = "Applied style: unavailable"
    end
    local intensities = sortedCounts(summary.editingIntensities)
    if #intensities == 1 then
        local label = intensities[1].label:gsub("_", " ")
        label = label:sub(1, 1):upper() .. label:sub(2)
        lines[#lines + 1] = "Editing intensity: " .. label
    elseif #intensities > 1 then
        lines[#lines + 1] = "Editing intensity: Multiple"
    else
        lines[#lines + 1] = "Editing intensity: unavailable"
    end
end

local function preparationLines(summary, includeBaselineResults)
    local lines = {
        "Selected: " .. tostring(summary.selected),
        "Ready to apply: " .. tostring(summary.ready),
        "Failed: " .. tostring(summary.failed),
        "Skipped: " .. tostring(summary.skipped),
        "Not processed: " .. tostring(summary.notProcessed),
        "Confirmation: "
            .. Utils.safeMessage(summary.confirmationMode, "not applicable"),
        "Model: "
            .. Utils.safeMessage(summary.modelDisplayName, "unavailable"),
        "Model ID: " .. Utils.safeMessage(summary.modelId, modelSummary(summary)),
        "Resolved model: " .. resolvedModelSummary(summary),
        "Composition crop recommended: "
            .. tostring(summary.cropRecommendedCount or 0),
        "Composition crop prepared: "
            .. tostring(summary.cropPreparedCount or 0),
        "Composition crop disabled: "
            .. tostring(summary.cropDisabled or 0),
        "Leveling recommended: "
            .. tostring(summary.levelingRecommendedCount or 0),
        "Leveling prepared: "
            .. tostring(summary.levelingPreparedCount or 0),
        "Leveling disabled: "
            .. tostring(summary.levelingDisabled or 0),
        "Denoise recommended but not applied: "
            .. tostring(summary.denoiseIgnored),
        "Warnings: " .. tostring(summary.warningCount),
        "Elapsed: "
            .. ProgressTracker.formatDuration(summary.elapsedSeconds or 0),
    }
    if Utils.isFiniteNumber(summary.levelingAngleMinimum)
        and Utils.isFiniteNumber(summary.levelingAngleMaximum) then
        local angleText
        if summary.levelingAngleMinimum == summary.levelingAngleMaximum then
            angleText = string.format(
                "%+.2f degrees",
                summary.levelingAngleMinimum
            )
        else
            angleText = string.format(
                "%+.2f to %+.2f degrees",
                summary.levelingAngleMinimum,
                summary.levelingAngleMaximum
            )
        end
        lines[#lines + 1] = "Leveling angle range: " .. angleText
    end
    appendStyleLines(lines, summary)
    appendLearningLines(lines, summary, includeBaselineResults)
    return lines
end

local function examples(summary)
    local lines = {}
    if #(summary.examples or {}) == 0 then
        return lines
    end
    lines[#lines + 1] = ""
    lines[#lines + 1] = "Examples:"
    for _, example in ipairs(summary.examples) do
        local geometry = "composition "
            .. (example.cropRecommended and "recommended" or "not needed")
            .. "/"
            .. (example.cropIncluded and "prepared" or "not prepared")
        if example.levelingRecommended then
            geometry = geometry
                .. ", leveling "
                .. Utils.safeMessage(example.levelingMode, "rotation")
                .. " "
                .. string.format("%+.2f degrees", example.levelingAngle or 0)
                .. "/"
                .. (example.levelingIncluded and "prepared" or "not prepared")
        else
            geometry = geometry .. ", leveling not needed"
        end
        lines[#lines + 1] = "- "
            .. Utils.safeMessage(example.filename, "Photo")
            .. ": "
            .. tostring(example.settingCount)
            .. " settings, "
            .. geometry
            .. ", warnings "
            .. tostring(example.warningCount)
    end
    return lines
end

function AutoDevelopConfirmationDialog.confirm(summary)
    local lines = preparationLines(summary, false)
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
    local lines = preparationLines(summary, true)
    lines[#lines + 1] = "Cancelled: "
        .. (summary.cancelled and "yes" or "no")
    lines[#lines + 1] = ""
    lines[#lines + 1] = "Applied: " .. tostring(application.applied or 0)
    lines[#lines + 1] = "Crop applied: "
        .. tostring(application.cropApplied or 0)
    lines[#lines + 1] = "Leveling applied: "
        .. tostring(application.levelingApplied or 0)
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
