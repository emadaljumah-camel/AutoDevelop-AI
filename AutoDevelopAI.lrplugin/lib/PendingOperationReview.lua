local CropMapper = ModuleLoader.load("lib/CropMapper.lua")
local DevelopModeMapper =
    ModuleLoader.load("lib/DevelopModeMapper.lua")
local DevelopSettingsMapper =
    ModuleLoader.load("lib/DevelopSettingsMapper.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")

local PendingOperationReview = {}

local labels = {
    Exposure2012 = "Exposure",
    Contrast2012 = "Contrast",
    Highlights2012 = "Highlights",
    Shadows2012 = "Shadows",
    Whites2012 = "Whites",
    Blacks2012 = "Blacks",
    Texture = "Texture",
    Clarity2012 = "Clarity",
    Dehaze = "Dehaze",
    Vibrance = "Vibrance",
    Saturation = "Saturation",
    Temperature = "Temperature",
    Tint = "Tint",
    CropLeft = "Left",
    CropRight = "Right",
    CropTop = "Top",
    CropBottom = "Bottom",
    CropAngle = "Crop angle",
}

local degree = "\194\176"
local emDash = "\226\128\148"

local function normalizeZero(value, threshold)
    if math.abs(value) < threshold then
        return 0
    end
    return value
end

local function compact(value, signed)
    value = normalizeZero(value, 0.05)
    local rounded = math.floor(math.abs(value) + 0.5)
    local integral = math.abs(math.abs(value) - rounded) < 0.000001
    local format
    if integral then
        format = signed and "%+.0f" or "%.0f"
    else
        format = signed and "%+.1f" or "%.1f"
    end
    return string.format(format, value)
end

local function formatValue(key, value, role)
    if not Utils.isFiniteNumber(value) then
        return emDash
    end
    local signed = role ~= "current"
    if key == "Exposure2012" then
        value = normalizeZero(value, 0.005)
        return string.format(signed and "%+.2f" or "%.2f", value)
    end
    if key == "Temperature" then
        return string.format(
            role == "change" and "%+.0f K" or "%.0f K",
            value
        )
    end
    if key == "Tint" then
        return string.format("%+.0f", normalizeZero(value, 0.5))
    end
    if key == "CropLeft"
        or key == "CropRight"
        or key == "CropTop"
        or key == "CropBottom" then
        value = normalizeZero(value, 0.0005)
        return string.format(
            role == "change" and "%+.3f" or "%.3f",
            value
        )
    end
    if key == "CropAngle" then
        value = normalizeZero(value, 0.005)
        return string.format(
            signed and "%+.2f%s" or "%.2f%s",
            value,
            degree
        )
    end
    return compact(value, signed)
end

local function row(key, originalSettings, finalSettings)
    local current = originalSettings[key]
    local proposed = finalSettings[key]
    local delta = nil
    if Utils.isFiniteNumber(current)
        and Utils.isFiniteNumber(proposed) then
        delta = proposed - current
    end
    return {
        key = key,
        label = labels[key] or key,
        current = formatValue(key, current, "current"),
        proposed = formatValue(key, proposed, "proposed"),
        change = formatValue(key, delta, "change"),
        currentValue = current,
        proposedValue = proposed,
        deltaValue = delta,
    }
end

local function preparedStatus(
    recommended,
    included,
    suppressed,
    rejected
)
    if rejected then
        return "Rejected by validation"
    end
    if included then
        return "Recommended - prepared for application"
    end
    if suppressed then
        return "Recommended - suppressed by preference"
    end
    if recommended then
        return "Recommended - not prepared"
    end
    return "Not needed"
end

local function geometry(operation, originalSettings, finalSettings)
    local validation = operation.validationSummary or {}
    local lines = {
        "Composition crop: "
            .. preparedStatus(
                operation.cropRecommended,
                operation.compositionCropIncluded,
                operation.cropDisabled,
                validation.crop_rejected == true
            ),
    }
    if operation.levelingIncluded
        and not operation.compositionCropIncluded then
        lines[#lines + 1] =
            "Current crop bounds will be preserved"
    end
    lines[#lines + 1] = "Leveling: "
        .. preparedStatus(
            operation.levelingRecommended,
            operation.levelingIncluded,
            operation.levelingDisabled,
            validation.leveling_rejected == true
        )
    if operation.levelingRecommended and operation.levelingMode then
        local mode = tostring(operation.levelingMode):gsub("_", " ")
        mode = mode:sub(1, 1):upper() .. mode:sub(2)
        lines[#lines + 1] = "Leveling mode: " .. mode
    end

    local rows = {}
    for _, key in ipairs(CropMapper.keys()) do
        if Utils.isFiniteNumber(finalSettings[key]) then
            rows[#rows + 1] =
                row(key, originalSettings, finalSettings)
        end
    end
    if operation.compositionCropIncluded
        and Utils.isFiniteNumber(finalSettings.CropLeft)
        and Utils.isFiniteNumber(finalSettings.CropRight)
        and Utils.isFiniteNumber(finalSettings.CropTop)
        and Utils.isFiniteNumber(finalSettings.CropBottom) then
        local retained = (
            finalSettings.CropRight - finalSettings.CropLeft
        ) * (
            finalSettings.CropBottom - finalSettings.CropTop
        ) * 100
        lines[#lines + 1] = "Approximate retained frame: "
            .. string.format("%.0f%%", retained)
    end
    return rows, lines
end

local function confidenceText(value)
    if not Utils.isFiniteNumber(value) then
        return "Unavailable"
    end
    return string.format("%.0f%%", value * 100)
end

local function upright(operation, originalSettings, finalSettings)
    local decision = operation.upright or {}
    local diagnostics = operation.modeDiagnostics or {}
    local originalRaw = originalSettings.PerspectiveUpright
    if originalRaw == nil then
        originalRaw = diagnostics.perspectiveUpright
    end
    local originalUpright = DevelopModeMapper.decodeUpright(
        originalRaw
    )
    local finalRaw = finalSettings.PerspectiveUpright
    if finalRaw == nil
        and decision.recommended ~= true
        and originalUpright.supported then
        finalRaw = originalUpright.rawValue
    end
    local finalUpright = DevelopModeMapper.decodeUpright(
        finalRaw
    )
    local comparison = "Unavailable (no change proposed)"
    if originalUpright.supported and finalUpright.supported then
        comparison = tostring(originalUpright.mode)
            .. " -> "
            .. tostring(finalUpright.mode)
    end
    local fallbackReason = decision.recommended
        and "No reason supplied"
        or "No Upright correction recommended"
    return {
        "Recommended: "
            .. (decision.recommended and "Yes" or "No"),
        "Mode: "
            .. (
                finalUpright.supported
                and tostring(finalUpright.mode)
                or tostring(decision.mode or "off")
            ),
        "Current -> proposed: " .. comparison,
        "Confidence: " .. confidenceText(decision.confidence),
        "Reason: "
            .. Utils.safeMessage(decision.reason, fallbackReason),
    }
end

local function hdr(operation, originalSettings, finalSettings)
    local decision = operation.hdr or {}
    local diagnostics = operation.hdrDecision or {}
    local modeDiagnostics = operation.modeDiagnostics or {}
    local originalRaw = originalSettings.HDREditMode
    if originalRaw == nil then
        originalRaw = modeDiagnostics.hdrEditMode
    end
    local originalHdr = DevelopModeMapper.decodeHdr(
        originalRaw
    )
    local finalRaw = finalSettings.HDREditMode
    if finalRaw == nil
        and diagnostics.validated_hdr_enabled ~= true
        and originalHdr.supported then
        finalRaw = originalHdr.rawValue
    end
    local finalHdr = DevelopModeMapper.decodeHdr(
        finalRaw
    )
    local learnedPreference = "None"
    if diagnostics.hdr_learning_applied == true then
        local rate = diagnostics.hdr_learning_enable_rate
        learnedPreference = (
            Utils.isFiniteNumber(rate) and rate >= 0.70
        ) and "Strong" or "Moderate"
    end
    local reasonLabels = {
        profile_disallowed = "HDR is disabled by the selected profile",
        insufficient_dynamic_range =
            "Insufficient dynamic-range evidence",
        insufficient_evidence = "Insufficient combined HDR evidence",
        confidence_below_threshold =
            "Confidence is below the profile threshold",
        high_noise_risk = "High noise risk",
        severe_underexposure = "Severe underexposure",
        portrait_without_hdr_need =
            "Portrait lighting has no specific HDR need",
        documentary_authenticity =
            "Documentary authenticity policy",
        model_not_recommended = "Model did not recommend HDR",
        caller_unsupported = "Lightroom HDR mode is unavailable",
        sdr_only_workflow = "SDR-only workflow",
        unsupported_source_format = "Source is not an eligible RAW file",
    }
    local basisLabels = {
        disabled = "Disabled",
        model = "Model recommendation",
        objective_evidence = "Objective scene evidence",
        learned_preference = "Learned preference",
    }
    local comparison = "Unavailable (no change proposed)"
    if originalHdr.supported and finalHdr.supported then
        comparison = (originalHdr.enabled and "Enabled" or "Disabled")
            .. " -> "
            .. (finalHdr.enabled and "Enabled" or "Disabled")
    end
    local baseSceneEvidence =
        diagnostics.base_scene_evidence_score
        or diagnostics.visual_evidence_score
    local combinedEvidence =
        diagnostics.combined_evidence_score
        or diagnostics.hdr_evidence_score
    return {
        "Scene candidate: "
            .. (diagnostics.scene_hdr_candidate and "Yes" or "No"),
        "Base scene evidence: "
            .. confidenceText(baseSceneEvidence),
        "Learning bonus: "
            .. confidenceText(diagnostics.learning_bonus),
        "Preference bonus: "
            .. confidenceText(diagnostics.user_preference_bonus),
        "Combined evidence: "
            .. confidenceText(combinedEvidence),
        "Model confidence: "
            .. confidenceText(diagnostics.raw_hdr_confidence),
        "Learned preference: " .. learnedPreference,
        "Decision basis: "
            .. (
                basisLabels[diagnostics.decision_basis]
                or "Unavailable"
            ),
        "Decision confidence: "
            .. confidenceText(diagnostics.decision_confidence),
        "Final decision: "
            .. (
                finalHdr.supported and finalHdr.enabled
                and "Enabled" or "Disabled"
            ),
        "Current -> proposed: " .. comparison,
        "Reason: "
            .. Utils.safeMessage(
                reasonLabels[diagnostics.hdr_rejection_reason]
                    or decision.reason,
                "No reason supplied"
            ),
    }
end

local function processing(operation)
    local denoise = type(operation.denoise) == "table"
        and operation.denoise or {}
    local lines = {}
    lines[#lines + 1] = "Denoise: "
        .. (
            operation.denoiseRecommended
            and "Recommended"
            or "Not recommended"
        )
    lines[#lines + 1] = "Denoise will be applied: "
        .. (operation.denoiseIncluded and "Yes" or "No")
    if operation.denoiseRecommended then
        lines[#lines + 1] = "Denoise amount: "
            .. (
                Utils.isFiniteNumber(denoise.amount)
                and tostring(denoise.amount)
                or "Unavailable"
            )
        lines[#lines + 1] = "Denoise confidence: "
            .. confidenceText(denoise.confidence)
        lines[#lines + 1] = "Denoise preset: "
            .. Utils.safeMessage(
                denoise.presetName,
                operation.denoiseIncluded
                    and "Resolved" or "Unavailable"
            )
        lines[#lines + 1] = "Denoise reason: "
            .. Utils.safeMessage(
                operation.denoiseIncluded
                    and denoise.reason
                    or denoise.unavailableReason,
                "No reason supplied"
            )
    end
    lines[#lines + 1] =
        "Dust removal: Not part of this prepared operation"
    return lines
end

local function learning(operation)
    local diagnostics = operation.learning
    if type(diagnostics) ~= "table" then
        return {
            "Enabled: No",
            "Similar samples found: 0",
            "Average similarity: unavailable",
            "Personalization: Not applied",
        }
    end
    local similarity = "unavailable"
    if Utils.isFiniteNumber(diagnostics.average_similarity) then
        similarity = string.format("%.2f", diagnostics.average_similarity)
    end
    return {
        "Enabled: " .. (diagnostics.enabled and "Yes" or "No"),
        "Similar samples found: "
            .. tostring(diagnostics.retrieved_sample_count or 0),
        "Average similarity: " .. similarity,
        "Personalization: "
            .. (
                diagnostics.personalization_applied
                and "Applied"
                or "Not applied"
            ),
    }
end

local function warnings(operation, comparisonUnavailable)
    local lines = {}
    local items = operation.warnings or {}
    local visible = math.min(#items, 5)
    for index = 1, visible do
        lines[#lines + 1] = "- "
            .. Utils.safeMessage(
                items[index].message,
                "Processing warning"
            )
    end
    if #items > visible then
        lines[#lines + 1] = "+"
            .. tostring(#items - visible)
            .. " more warnings"
    end
    if #lines == 0 then
        lines[1] = "None"
    end
    if comparisonUnavailable then
        if #lines == 1 and lines[1] == "None" then
            lines = {}
        end
        lines[#lines + 1] =
            "- Current-value comparison is unavailable for one or more settings."
    end
    return lines
end

function PendingOperationReview.build(operation)
    operation = operation or {}
    local originalSettings = operation.originalSettings or {}
    local finalSettings = operation.finalSettings or {}
    local developRows = {}
    local comparisonUnavailable = false
    for _, key in ipairs(DevelopSettingsMapper.keys()) do
        if Utils.isFiniteNumber(finalSettings[key]) then
            developRows[#developRows + 1] =
                row(key, originalSettings, finalSettings)
            if not Utils.isFiniteNumber(originalSettings[key]) then
                comparisonUnavailable = true
            end
        end
    end
    local geometryRows, geometryLines =
        geometry(operation, originalSettings, finalSettings)
    local settingCount = #developRows + #geometryRows
    if finalSettings.PerspectiveUpright ~= nil then
        settingCount = settingCount + 1
    end
    if finalSettings.EnableTransform ~= nil then
        settingCount = settingCount + 1
    end
    if finalSettings.HDREditMode ~= nil then
        settingCount = settingCount + 1
    end
    if operation.denoiseIncluded == true then
        settingCount = settingCount + 1
    end
    return {
        settingCount = settingCount,
        developRows = developRows,
        geometryRows = geometryRows,
        geometryLines = geometryLines,
        uprightLines = upright(
            operation,
            originalSettings,
            finalSettings
        ),
        hdrLines = hdr(operation, originalSettings, finalSettings),
        processingLines =
            processing(operation),
        learningLines = learning(operation),
        warningLines = warnings(operation, comparisonUnavailable),
        comparisonUnavailable = comparisonUnavailable,
    }
end

return PendingOperationReview
