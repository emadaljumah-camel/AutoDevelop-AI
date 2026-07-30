local LrDialogs = import("LrDialogs")
local LrView = import("LrView")

local LearningFeedbackDialog = {}

local detailOrder = {
    "Exposure2012",
    "Contrast2012",
    "Highlights2012",
    "Shadows2012",
    "Whites2012",
    "Blacks2012",
    "Texture",
    "Clarity2012",
    "Dehaze",
    "Vibrance",
    "Saturation",
    "Temperature",
    "Tint",
    "CropLeft",
    "CropRight",
    "CropTop",
    "CropBottom",
    "CropAngle",
}

local friendlyLabels = {
    Contrast2012 = "Contrast",
    Clarity2012 = "Clarity",
}

local function signed(value)
    if value == math.floor(value) then
        return string.format("%+d", value)
    end
    return string.format("%+.2f", value)
end

local function appendDetails(lines, heading, details, order)
    if type(details) ~= "table" then
        return
    end
    local addedHeading = false
    for _, key in ipairs(order) do
        local detail = details[key]
        if type(detail) == "table" then
            if not addedHeading then
                lines[#lines + 1] = ""
                lines[#lines + 1] = heading
                addedHeading = true
            end
            lines[#lines + 1] = string.format(
                "%-12s baseline %s   current %s   change %s",
                friendlyLabels[key] or key,
                signed(detail.baseline),
                signed(detail.current),
                signed(detail.delta)
            )
        end
    end
end

function LearningFeedbackDialog.confirm(summary)
    local factory = LrView.osFactory()
    local lines = {
        "Selected photos: " .. tostring(summary.selected),
        "Pending learning sessions: " .. tostring(summary.pending),
        "Photos with significant changes: " .. tostring(summary.changed),
        "Unchanged photos: " .. tostring(summary.unchanged),
        "Missing pending session: " .. tostring(summary.missing),
        "Comparison failures: " .. tostring(summary.previewFailed or 0),
        "",
        "The backend compares current settings with the applied AI baseline.",
        "This command does not modify any photo.",
    }
    appendDetails(lines, "Significant tonal/color changes:",
        summary.significantChanges, detailOrder)
    appendDetails(lines, "Composition crop changes:",
        summary.cropChanges,
        {"CropLeft", "CropRight", "CropTop", "CropBottom"})
    appendDetails(lines, "Leveling changes:",
        summary.levelingChanges, {"CropAngle"})
    return LrDialogs.presentModalDialog({
        title = "AutoDevelop AI - Capture Editing Feedback",
        contents = factory:column({
            spacing = factory:control_spacing(),
            factory:static_text({
                title = table.concat(lines, "\n"),
                fill_horizontal = 1,
            }),
        }),
        actionVerb = "Save feedback",
        otherVerb = "Skip unchanged photos",
        cancelVerb = "Cancel",
    })
end

return LearningFeedbackDialog
