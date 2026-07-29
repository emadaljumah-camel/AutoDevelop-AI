local Utils = ModuleLoader.load("lib/Utils.lua")

local BatchSummary = {}

function BatchSummary.new(selected, kind, startedAt)
    return {
        kind = kind,
        selected = selected or 0,
        analyzed = 0,
        ready = 0,
        applied = 0,
        skipped = 0,
        failed = 0,
        notProcessed = 0,
        restoredAfterFailure = 0,
        failedNotRestored = 0,
        cropCount = 0,
        cropDisabled = 0,
        denoiseIgnored = 0,
        warningCount = 0,
        cancelled = false,
        terminalCategory = nil,
        failures = {},
        failureCategories = {},
        startedAt = startedAt,
        elapsedSeconds = 0,
    }
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
