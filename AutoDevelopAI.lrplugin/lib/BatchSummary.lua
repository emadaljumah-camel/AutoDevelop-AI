local Utils = ModuleLoader.load("lib/Utils.lua")

local BatchSummary = {}

function BatchSummary.new(selected, kind, startedAt)
    return {
        kind = kind,
        selected = selected or 0,
        attempted = 0,
        processed = 0,
        prepared = 0,
        analyzed = 0,
        ready = 0,
        applied = 0,
        skipped = 0,
        failed = 0,
        notProcessed = 0,
        restoredAfterFailure = 0,
        failedNotRestored = 0,
        cropRecommendedCount = 0,
        cropPreparedCount = 0,
        cropDisabled = 0,
        levelingRecommendedCount = 0,
        levelingPreparedCount = 0,
        levelingDisabled = 0,
        levelingAngleMinimum = nil,
        levelingAngleMaximum = nil,
        cropAppliedCount = 0,
        levelingAppliedCount = 0,
        hdrRecommendedCount = 0,
        hdrAppliedCount = 0,
        denoiseRecommendedCount = 0,
        denoiseAppliedCount = 0,
        denoiseIgnored = 0,
        warningCount = 0,
        cancelled = false,
        terminalCategory = nil,
        failures = {},
        failureCategories = {},
        startedAt = startedAt,
        elapsedSeconds = 0,
        personalizationApplied = 0,
        learningReason = nil,
        learningDiagnosticsCount = 0,
        learningEnabled = nil,
        learningUsableMinimum = nil,
        learningUsableMaximum = nil,
        learningRetrievedMinimum = nil,
        learningRetrievedMaximum = nil,
        learningRequiredMinimum = nil,
        learningRequiredMaximum = nil,
        learningSimilarityTotal = 0,
        learningSimilarityCount = 0,
        learningBaselineSaved = 0,
        learningBaselineFailed = 0,
        showLearningSummary = false,
        effectiveStyles = {},
        editingIntensities = {},
        models = {},
        resolvedModels = {},
    }
end

function BatchSummary.recordStyle(summary, operation)
    if type(summary) ~= "table" or type(operation) ~= "table" then
        return
    end
    local styleId = operation.effectiveStyleId
    if type(styleId) == "string" and styleId ~= "" then
        summary.effectiveStyles[styleId] =
            (summary.effectiveStyles[styleId] or 0) + 1
    end
    local intensity = operation.editingIntensity
    if type(intensity) == "string" and intensity ~= "" then
        summary.editingIntensities[intensity] =
            (summary.editingIntensities[intensity] or 0) + 1
    end
end

function BatchSummary.addFailure(summary, filename, failure)
    summary.failed = summary.failed + 1
    local category = type(failure) == "table"
        and failure.category or "internal_error"
    summary.failureCategories[category] =
        (summary.failureCategories[category] or 0) + 1
    if #summary.failures < 5 then
        local stage = type(failure) == "table"
            and failure.stage or nil
        summary.failures[#summary.failures + 1] = {
            filename = filename,
            category = category,
            code = type(failure) == "table" and failure.code or nil,
            stage = type(stage) == "string"
                and Utils.safeErrorCode(stage, "internal_error") or nil,
        }
    end
end

local function updateRange(summary, minimumKey, maximumKey, value)
    if not Utils.isFiniteNumber(value) then
        return
    end
    local minimum = summary[minimumKey]
    local maximum = summary[maximumKey]
    summary[minimumKey] = minimum == nil and value or math.min(minimum, value)
    summary[maximumKey] = maximum == nil and value or math.max(maximum, value)
end

function BatchSummary.recordGeometry(summary, operation)
    if type(summary) ~= "table" or type(operation) ~= "table" then
        return
    end
    if operation.cropRecommended then
        summary.cropRecommendedCount =
            (summary.cropRecommendedCount or 0) + 1
    end
    if operation.compositionCropIncluded then
        summary.cropPreparedCount = (summary.cropPreparedCount or 0) + 1
    end
    if operation.cropDisabled then
        summary.cropDisabled = (summary.cropDisabled or 0) + 1
    end
    if operation.levelingRecommended then
        summary.levelingRecommendedCount =
            (summary.levelingRecommendedCount or 0) + 1
        updateRange(
            summary,
            "levelingAngleMinimum",
            "levelingAngleMaximum",
            operation.levelingAngle
        )
    end
    if operation.levelingIncluded then
        summary.levelingPreparedCount =
            (summary.levelingPreparedCount or 0) + 1
    end
    if operation.levelingDisabled then
        summary.levelingDisabled = (summary.levelingDisabled or 0) + 1
    end
end

function BatchSummary.recordLearning(summary, learning)
    if type(summary) ~= "table" or type(learning) ~= "table" then
        return
    end
    summary.learningDiagnosticsCount =
        (summary.learningDiagnosticsCount or 0) + 1
    if summary.learningEnabled == nil then
        summary.learningEnabled = learning.enabled == true
    else
        summary.learningEnabled =
            summary.learningEnabled or learning.enabled == true
    end
    if learning.personalization_applied == true then
        summary.personalizationApplied =
            (summary.personalizationApplied or 0) + 1
    end
    summary.learningReason = summary.learningReason or learning.reason
    updateRange(
        summary,
        "learningUsableMinimum",
        "learningUsableMaximum",
        learning.usable_sample_count
    )
    updateRange(
        summary,
        "learningRetrievedMinimum",
        "learningRetrievedMaximum",
        learning.retrieved_sample_count
    )
    updateRange(
        summary,
        "learningRequiredMinimum",
        "learningRequiredMaximum",
        learning.minimum_sample_count
    )
    if Utils.isFiniteNumber(learning.average_similarity) then
        summary.learningSimilarityTotal =
            (summary.learningSimilarityTotal or 0)
            + learning.average_similarity
        summary.learningSimilarityCount =
            (summary.learningSimilarityCount or 0) + 1
    end
end

function BatchSummary.markAttempted(summary)
    summary.attempted = (summary.attempted or 0) + 1
end

function BatchSummary.recordPrepared(summary, operation)
    if type(summary) ~= "table" or type(operation) ~= "table" then
        return
    end
    summary.prepared = (summary.prepared or 0) + 1
    summary.ready = (summary.ready or 0) + 1
    BatchSummary.recordStyle(summary, operation)
    BatchSummary.recordGeometry(summary, operation)
    BatchSummary.recordLearning(summary, operation.learning)
    summary.warningCount =
        (summary.warningCount or 0) + #(operation.warnings or {})
    if type(operation.model) == "string"
        and operation.model ~= "" then
        summary.models[operation.model] = true
    end
    if type(operation.resolvedModel) == "string"
        and operation.resolvedModel ~= "" then
        summary.resolvedModels[operation.resolvedModel] = true
    end
    if operation.hdrRecommended == true then
        summary.hdrRecommendedCount =
            (summary.hdrRecommendedCount or 0) + 1
    end
    if operation.denoiseRecommended == true then
        summary.denoiseRecommendedCount =
            (summary.denoiseRecommendedCount or 0) + 1
        if operation.denoiseIncluded ~= true then
            summary.denoiseIgnored = (summary.denoiseIgnored or 0) + 1
        end
    end
end

function BatchSummary.recordSkipped(summary)
    if type(summary) ~= "table" then
        return
    end
    summary.processed = (summary.processed or 0) + 1
    summary.skipped = (summary.skipped or 0) + 1
end

local function applicationFailure(operation, application)
    if (application.restoredAfterFailure or 0) > 0
        or (application.failedNotRestored or 0) > 0 then
        return {
            category = operation.applyErrorCategory or "apply_failed",
            code = operation.applyErrorCode or "lightroom_apply_failed",
        }
    end
    if application.writeError then
        return {
            category =
                application.writeErrorCategory or "write_access_failed",
            code = application.writeErrorCode
                or "catalog_write_access_failed",
        }
    end
    if (application.notApplied or 0) > 0
        and application.cancelled ~= true then
        return {
            category = "apply_failed",
            code = "operation_not_applied",
        }
    end
    return nil
end

function BatchSummary.recordApplication(summary, operation, application)
    if type(summary) ~= "table"
        or type(operation) ~= "table"
        or type(application) ~= "table" then
        return
    end
    summary.processed = (summary.processed or 0) + 1
    summary.applied =
        (summary.applied or 0) + (application.applied or 0)
    summary.restoredAfterFailure =
        (summary.restoredAfterFailure or 0)
        + (application.restoredAfterFailure or 0)
    summary.failedNotRestored =
        (summary.failedNotRestored or 0)
        + (application.failedNotRestored or 0)

    if operation.applicationStatus == "applied" then
        if operation.compositionCropIncluded then
            summary.cropAppliedCount =
                (summary.cropAppliedCount or 0) + 1
        end
        if operation.levelingIncluded then
            summary.levelingAppliedCount =
                (summary.levelingAppliedCount or 0) + 1
        end
        if operation.enableHdr then
            summary.hdrAppliedCount =
                (summary.hdrAppliedCount or 0) + 1
        end
        if operation.denoiseApplied then
            summary.denoiseAppliedCount =
                (summary.denoiseAppliedCount or 0) + 1
        end
    end

    local failure = applicationFailure(operation, application)
    if failure then
        BatchSummary.addFailure(
            summary,
            operation.displayFilename or operation.filename or "Photo",
            failure
        )
    end
end

function BatchSummary.recordProcessedFailure(summary, filename, failure)
    if type(summary) ~= "table" then
        return
    end
    summary.processed = (summary.processed or 0) + 1
    BatchSummary.addFailure(summary, filename, failure)
end

function BatchSummary.markNotProcessed(summary, count)
    if count and count > 0 then
        summary.notProcessed = summary.notProcessed + count
    end
end

function BatchSummary.sortedCategories(summary)
    local names = {}
    for name in pairs(summary.failureCategories or {}) do
        names[#names + 1] = name
    end
    table.sort(names)
    return names
end

return BatchSummary
