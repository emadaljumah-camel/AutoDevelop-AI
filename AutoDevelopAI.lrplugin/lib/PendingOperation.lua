local Utils = ModuleLoader.load("lib/Utils.lua")

local PendingOperation = {}

function PendingOperation.new(values)
    values = values or {}
    return {
        photo = values.photo,
        photoKey = values.photoKey,
        filename = values.filename,
        requestId = values.requestId,
        profileId = values.profileId,
        requestedStyleId = values.requestedStyleId,
        effectiveStyleId = values.effectiveStyleId,
        styleSelectionMode = values.styleSelectionMode,
        styleSelectionReason = values.styleSelectionReason,
        editingIntensity = values.editingIntensity,
        sceneConfidence = values.sceneConfidence,
        originalSettings = Utils.deepCopy(values.originalSettings or {}),
        mappedSettings = Utils.deepCopy(values.mappedSettings or {}),
        cropRecommended = values.cropRecommended == true,
        compositionCropIncluded =
            values.compositionCropIncluded == true,
        levelingRecommended = values.levelingRecommended == true,
        levelingIncluded = values.levelingIncluded == true,
        levelingMode = values.levelingMode,
        levelingAngle = values.levelingAngle,
        denoiseRecommended = values.denoiseRecommended == true,
        enableHdr = values.enableHdr == true,
        warnings = Utils.deepCopy(values.warnings or {}),
        model = values.model,
        resolvedModel = values.resolvedModel,
        processingDurationMs = values.processingDurationMs,
        exifContext = Utils.deepCopy(values.exifContext or {}),
        validationSummary = Utils.deepCopy(values.validationSummary or {}),
        learning = Utils.deepCopy(values.learning),
        applicationStatus = "pending",
    }
end

function PendingOperation.clear(operations)
    if type(operations) ~= "table" then
        return
    end
    for index = #operations, 1, -1 do
        operations[index] = nil
    end
end

return PendingOperation
