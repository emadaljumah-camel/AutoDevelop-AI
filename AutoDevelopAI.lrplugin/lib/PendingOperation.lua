local Utils = ModuleLoader.load("lib/Utils.lua")

local PendingOperation = {}

local function countSettings(settings)
    local count = 0
    if type(settings) ~= "table" then
        return count
    end
    for _ in pairs(settings) do
        count = count + 1
    end
    return count
end

function PendingOperation.new(values)
    values = values or {}
    local upright = Utils.deepCopy(values.upright or {
        recommended = values.uprightRecommended == true,
        mode = values.uprightMode or "off",
        confidence = values.uprightConfidence or 0,
        reason = values.uprightReason,
    })
    local hdr = Utils.deepCopy(values.hdr or {
        recommended = values.hdrRecommended == true,
        enabled = values.enableHdr == true,
        confidence = values.hdrConfidence or 0,
        reason = values.hdrReason,
    })
    local denoiseValues = values.denoise or {}
    local denoise = {
        recommended = denoiseValues.recommended == true
            or values.denoiseRecommended == true,
        included = denoiseValues.included == true,
        amount = denoiseValues.amount,
        confidence = denoiseValues.confidence,
        reason = denoiseValues.reason,
        unavailableReason = denoiseValues.unavailableReason,
        unavailableCode = denoiseValues.unavailableCode,
        presetName = denoiseValues.presetName,
    }
    return {
        photo = values.photo,
        photoKey = values.photoKey,
        photoId = values.photoId or values.photoKey or values.filename,
        displayFilename =
            values.displayFilename or values.filename or values.photoId,
        filename =
            values.filename or values.displayFilename or values.photoId,
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
        finalSettings = Utils.deepCopy(
            values.finalSettings or values.mappedSettings or {}
        ),
        cropRecommended = values.cropRecommended == true,
        compositionCropIncluded =
            values.compositionCropIncluded == true,
        levelingRecommended = values.levelingRecommended == true,
        levelingIncluded = values.levelingIncluded == true,
        levelingMode = values.levelingMode,
        levelingAngle = values.levelingAngle,
        denoise = denoise,
        denoiseRecommended = denoise.recommended,
        denoiseIncluded = denoise.included,
        denoisePreset = values.denoisePreset,
        denoiseOriginalSettings = Utils.deepCopy(
            values.denoiseOriginalSettings or {}
        ),
        denoiseApplied = false,
        upright = upright,
        uprightRecommended = upright.recommended == true,
        uprightMode = upright.mode or "off",
        uprightConfidence = upright.confidence,
        hdr = hdr,
        hdrRecommended = hdr.recommended == true,
        enableHdr = hdr.enabled == true,
        hdrConfidence = hdr.confidence,
        hdrDecision = Utils.deepCopy(values.hdrDecision),
        modeDiagnostics = Utils.deepCopy(values.modeDiagnostics or {}),
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

function PendingOperation.inspectDisplayContract(operation)
    operation = type(operation) == "table" and operation or {}
    local originalSettings = operation.originalSettings
    local finalSettings = operation.finalSettings
    local originalCount = countSettings(originalSettings)
    local finalCount = countSettings(finalSettings)
    local denoisePrepared = operation.denoiseIncluded == true
        and operation.denoisePreset ~= nil
        and type(operation.denoiseOriginalSettings) == "table"
        and type(operation.denoiseOriginalSettings.FilterList) == "table"
    if denoisePrepared then
        originalCount = originalCount + 1
        finalCount = finalCount + 1
    end
    local missingOriginalCount = 0
    if type(finalSettings) == "table" then
        for key in pairs(finalSettings) do
            if type(originalSettings) ~= "table"
                or (
                    not Utils.isFiniteNumber(originalSettings[key])
                    and type(originalSettings[key]) ~= "boolean"
                ) then
                missingOriginalCount = missingOriginalCount + 1
            end
        end
    end

    local filename = operation.displayFilename or operation.filename
    local hasFilename = type(filename) == "string"
        and Utils.trim(filename) ~= ""
    local hasPhotoIdentity = hasFilename
        or operation.photo ~= nil
        or operation.photoKey ~= nil
    local diagnosticCode = nil
    if not hasPhotoIdentity then
        diagnosticCode = "missing_photo_identity"
    elseif finalCount == 0 then
        diagnosticCode = "missing_final_settings"
    elseif originalCount == 0 then
        diagnosticCode = "missing_original_settings"
    elseif missingOriginalCount > 0 then
        diagnosticCode = "incomplete_original_settings"
    end

    return {
        canApply = diagnosticCode == nil,
        diagnosticCode = diagnosticCode,
        hasPhotoIdentity = hasPhotoIdentity,
        originalSettings = originalSettings,
        finalSettings = finalSettings,
        originalCount = originalCount,
        finalCount = finalCount,
        missingOriginalCount = missingOriginalCount,
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
