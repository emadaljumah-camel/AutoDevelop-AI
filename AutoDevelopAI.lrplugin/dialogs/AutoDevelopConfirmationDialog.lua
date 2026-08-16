local LrDialogs = import("LrDialogs")
local LrFunctionContext = import("LrFunctionContext")
local LrTasks = import("LrTasks")
local LrView = import("LrView")

local BatchSummary = ModuleLoader.load("lib/BatchSummary.lua")
local ErrorDialog = ModuleLoader.load("dialogs/ErrorDialog.lua")
local Logger = ModuleLoader.load("lib/Logger.lua")
local PendingOperation = ModuleLoader.load("lib/PendingOperation.lua")
local ProgressTracker = ModuleLoader.load("lib/ProgressTracker.lua")
local PendingOperationReview =
    ModuleLoader.load("lib/PendingOperationReview.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")
local Validation = ModuleLoader.load("lib/Validation.lua")
local StyleProfiles = ModuleLoader.load("lib/StyleProfiles.lua")

local AutoDevelopConfirmationDialog = {}

local function displayFilename(operation)
    operation = type(operation) == "table" and operation or {}
    return Utils.safeMessage(
        operation.displayFilename,
        operation.filename or operation.photoId or "Photo"
    )
end

local displayDiagnosticMessages = {
    missing_photo_identity =
        "Pending operation contains no photo identity.",
    missing_final_settings =
        "Pending operation contains no final develop settings.",
    missing_original_settings =
        "Pending operation contains no original develop settings.",
    incomplete_original_settings =
        "Pending operation has incomplete original develop settings.",
    unrenderable_final_settings =
        "Pending operation contains final settings that cannot be displayed.",
}

local learningReasonLabels = {
    disabled = "Disabled for this request",
    database_unavailable = "Learning database unavailable",
    embedding_unavailable = "Image comparison unavailable",
    insufficient_samples = "Insufficient feedback",
    no_similar_samples = "Insufficient similar feedback",
    retrieval_unavailable = "Learning retrieval unavailable",
}

local denoiseExclusionLabels = {
    denoise_preset_missing = "Required preset missing",
    denoise_preset_lookup_failed = "Preset lookup failed",
    denoise_preset_amount_unsupported = "Unsupported preset amount",
    denoise_source_unsupported = "Unsupported source format",
    denoise_baseline_unavailable = "Restorable baseline unavailable",
    denoise_already_enabled = "Denoise already enabled",
    denoise_unavailable = "Denoise unavailable",
}

local function titleCase(value)
    local text = Utils.safeMessage(value, "Unavailable"):gsub("_", " ")
    return text:sub(1, 1):upper() .. text:sub(2)
end

local function appendSection(lines, title, sectionLines)
    lines[#lines + 1] = ""
    lines[#lines + 1] = title
    lines[#lines + 1] = string.rep("-", #title)
    for _, line in ipairs(sectionLines or {}) do
        lines[#lines + 1] = line
    end
end

local function appendRows(lines, rows)
    if #(rows or {}) == 0 then
        lines[#lines + 1] = "No settings will be written."
        return
    end
    lines[#lines + 1] = string.format(
        "%-18s  %-12s  %-12s  %-12s",
        "Setting",
        "Current",
        "Proposed",
        "Change"
    )
    lines[#lines + 1] = string.rep("-", 64)
    for _, item in ipairs(rows) do
        lines[#lines + 1] = string.format(
            "%-18s  %-12s  %-12s  %-12s",
            item.label,
            item.current,
            item.proposed,
            item.change
        )
    end
end

function AutoDevelopConfirmationDialog.photoLines(
    operation,
    index,
    total
)
    operation = operation or {}
    local display = PendingOperation.inspectDisplayContract(operation)
    local review = PendingOperationReview.build(operation)
    local lines = {
        "Photo "
            .. tostring(index or 0)
            .. " of "
            .. tostring(total or 0),
        "Filename: " .. displayFilename(operation),
        "",
        "Style",
        "-----",
        "Selection: "
            .. (
                operation.requestedStyleId == "auto"
                and "Auto"
                or "Manual"
            ),
        "Applied style: "
            .. Utils.safeMessage(
                StyleProfiles.getDisplayName(
                    operation.effectiveStyleId
                ),
                operation.effectiveStyleId or "Unavailable"
            ),
        "Editing intensity: "
            .. titleCase(operation.editingIntensity),
        "Settings: "
            .. tostring(review.settingCount),
        "Warnings: " .. tostring(#(operation.warnings or {})),
    }

    appendSection(lines, "Develop Settings", {})
    appendRows(lines, review.developRows)
    appendSection(lines, "Geometry", review.geometryLines)
    appendRows(lines, review.geometryRows)
    appendSection(lines, "Transform Upright", review.uprightLines)
    appendSection(lines, "HDR", review.hdrLines)
    appendSection(lines, "Processing", review.processingLines)
    appendSection(lines, "Learning", review.learningLines)
    appendSection(lines, "Warnings", review.warningLines)
    if not display.canApply then
        appendSection(lines, "Diagnostic", {
            "Unable to display prepared settings.",
            "",
            displayDiagnosticMessages[display.diagnosticCode]
                or "Pending operation display data is invalid.",
            "Diagnostic code: "
                .. tostring(
                    display.diagnosticCode or "invalid_display_contract"
                ),
        })
    end
    return lines, review
end

local function yesNo(value)
    return value and "yes" or "no"
end

local function warningCount(operation)
    if type(operation) ~= "table"
        or type(operation.warnings) ~= "table" then
        return 0
    end
    return #operation.warnings
end

local function logConfirmationDetails(
    operation,
    display,
    renderedCharacterCount
)
    operation = type(operation) == "table" and operation or {}
    local finalSettings = type(operation.finalSettings) == "table"
        and operation.finalSettings or {}
    Logger.debug(
        "confirmation_details filename="
            .. displayFilename(operation)
            .. " original_settings="
            .. tostring(display.originalCount or 0)
            .. " final_settings="
            .. tostring(display.finalCount or 0)
            .. " crop_prepared="
            .. yesNo(operation.compositionCropIncluded == true)
            .. " leveling_prepared="
            .. yesNo(operation.levelingIncluded == true)
            .. " hdr_prepared="
            .. yesNo(finalSettings.HDREditMode == 1)
            .. " learning_present="
            .. yesNo(type(operation.learning) == "table")
            .. " warnings="
            .. tostring(warningCount(operation))
            .. " rendered_characters="
            .. tostring(renderedCharacterCount)
    )
    if renderedCharacterCount < 100 then
        Logger.warn(
            "operation=confirmation_details "
                .. "code=short_confirmation_details missing="
                .. tostring(display.diagnosticCode or "unknown")
        )
    end
end

function AutoDevelopConfirmationDialog.confirmPhoto(
    operation,
    index,
    total
)
    return LrFunctionContext.callWithContext(
        "AutoDevelopAIPhotoConfirmation",
        function()
            local factory = LrView.osFactory()
            local display =
                PendingOperation.inspectDisplayContract(operation)
            local renderOk, lines, review = LrTasks.pcall(function()
                return AutoDevelopConfirmationDialog.photoLines(
                    operation,
                    index,
                    total
                )
            end)
            if renderOk
                and type(lines) == "table"
                and display.canApply
                and (
                    type(review) ~= "table"
                    or review.settingCount ~= display.finalCount
                ) then
                display.canApply = false
                display.diagnosticCode = "unrenderable_final_settings"
                appendSection(lines, "Diagnostic", {
                    "Unable to display prepared settings.",
                    "",
                    displayDiagnosticMessages[display.diagnosticCode],
                    "Diagnostic code: " .. display.diagnosticCode,
                })
            end
            if not renderOk or type(lines) ~= "table" then
                display.canApply = false
                display.diagnosticCode = "confirmation_render_failed"
                lines = {
                    "Photo "
                        .. tostring(index or 0)
                        .. " of "
                        .. tostring(total or 0),
                    "Filename: "
                        .. displayFilename(operation),
                    "",
                    "Unable to render prepared settings.",
                    "Diagnostic code: confirmation_render_failed",
                }
                Logger.error(
                    "operation=confirmation_render "
                        .. "code=confirmation_render_failed"
                )
            end
            local detailsText = table.concat(lines, "\n")
            logConfirmationDetails(
                operation,
                display,
                #detailsText
            )

            local contents = {
                spacing = factory:control_spacing(),
                fill_horizontal = 1,
                factory:scrolled_view({
                    width = 650,
                    height = 500,
                    horizontal_scroller = false,
                    vertical_scroller = true,
                    factory:static_text({
                        title = detailsText,
                        width_in_chars = 82,
                        height_in_lines = -1,
                        fill_horizontal = 1,
                    }),
                }),
            }
            if display.canApply then
                local applyRemainingButton = factory:push_button({
                    title = "Apply Remaining Without Confirmation",
                    action = function(button)
                        LrDialogs.stopModalWithResult(
                            button,
                            "apply_remaining"
                        )
                    end,
                })
                contents[#contents + 1] = factory:row({
                    fill_horizontal = 1,
                    applyRemainingButton,
                })
            end

            local dialogOptions = {
                title = "AutoDevelop AI - Photo "
                    .. tostring(index)
                    .. " of "
                    .. tostring(total),
                cancelVerb = "Cancel Batch",
                resizable = false,
                contents = factory:column(contents),
            }
            if display.canApply then
                dialogOptions.actionVerb = "Apply"
                dialogOptions.otherVerb = "Skip"
            else
                dialogOptions.actionVerb = "Skip"
            end
            local result = LrDialogs.presentModalDialog(dialogOptions)
            if not display.canApply then
                if result == "ok" then
                    return "skip"
                end
                return "cancel_batch"
            end
            if result == "ok" then
                return "apply"
            end
            if result == "other" then
                return "skip"
            end
            if result == "apply_remaining" then
                return "apply_remaining"
            end
            return "cancel_batch"
        end
    )
end

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

local function denoiseExclusionSummary(summary)
    local entries = sortedCounts(
        summary.denoiseExclusionReasons,
        function(identifier)
            return denoiseExclusionLabels[identifier]
                or titleCase(identifier)
        end
    )
    if #entries == 0 then
        return "none"
    end
    local parts = {}
    for _, item in ipairs(entries) do
        parts[#parts + 1] = item.label .. " (" .. item.count .. ")"
    end
    return table.concat(parts, ", ")
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
    if #styles > 0 then
        local parts = {}
        for _, item in ipairs(styles) do
            parts[#parts + 1] = item.label .. " (" .. item.count .. ")"
        end
        lines[#lines + 1] = "Style distribution: "
            .. table.concat(parts, ", ")
    else
        lines[#lines + 1] = "Style distribution: unavailable"
    end
    local intensities = sortedCounts(summary.editingIntensities)
    if #intensities > 0 then
        local parts = {}
        for _, item in ipairs(intensities) do
            local label = item.label:gsub("_", " ")
            label = label:sub(1, 1):upper() .. label:sub(2)
            parts[#parts + 1] = label .. " (" .. item.count .. ")"
        end
        lines[#lines + 1] = "Editing intensity distribution: "
            .. table.concat(parts, ", ")
    else
        lines[#lines + 1] =
            "Editing intensity distribution: unavailable"
    end
end

local function finalLines(summary)
    local lines = {
        "Selected: " .. tostring(summary.selected),
        "Processed: " .. tostring(summary.processed or 0),
        "Applied: " .. tostring(summary.applied or 0),
        "Skipped: " .. tostring(summary.skipped),
        "Failed: " .. tostring(summary.failed),
        "Restored after apply failure: "
            .. tostring(summary.restoredAfterFailure or 0),
        "Restore failed: "
            .. tostring(summary.failedNotRestored or 0),
        "Not processed: " .. tostring(summary.notProcessed),
        "Cancelled: " .. (summary.cancelled and "Yes" or "No"),
        "Elapsed: "
            .. ProgressTracker.formatDuration(summary.elapsedSeconds or 0),
        "",
        "Model",
        "-----",
        "Model: "
            .. Utils.safeMessage(summary.modelDisplayName, "unavailable"),
        "Model ID: " .. Utils.safeMessage(summary.modelId, modelSummary(summary)),
        "Resolved model: " .. resolvedModelSummary(summary),
        "",
        "Geometry and processing",
        "-----------------------",
        "Photos updated with Develop recommendations: "
            .. tostring(summary.applied or 0),
        "The counters below cover optional operations only.",
        "Composition crop recommended: "
            .. tostring(summary.cropRecommendedCount or 0),
        "Composition crops applied: "
            .. tostring(summary.cropAppliedCount or 0),
        "Leveling recommended: "
            .. tostring(summary.levelingRecommendedCount or 0),
        "Level corrections applied: "
            .. tostring(summary.levelingAppliedCount or 0),
        "HDR recommended: "
            .. tostring(summary.hdrRecommendedCount or 0),
        "HDR applied: "
            .. tostring(summary.hdrAppliedCount or 0),
        "Denoise recommended: "
            .. tostring(summary.denoiseRecommendedCount or 0),
        "Denoise applied: "
            .. tostring(summary.denoiseAppliedCount or 0),
        "Denoise excluded: "
            .. tostring(summary.denoiseIgnored or 0),
        "Denoise exclusion reasons: "
            .. denoiseExclusionSummary(summary),
        "Personalization applied: "
            .. tostring(summary.personalizationApplied or 0)
            .. " photos",
        "Warnings: " .. tostring(summary.warningCount),
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
    appendLearningLines(lines, summary, true)
    return lines
end

function AutoDevelopConfirmationDialog.showFinal(summary, application)
    application = application or {}
    local lines = finalLines(summary)

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
        "AutoDevelop AI - Batch Complete",
        table.concat(lines, "\n"),
        messageType
    )
end

return AutoDevelopConfirmationDialog
