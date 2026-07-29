local BatchPolicy = {}

function BatchPolicy.newSummary(selected)
    return {
        selected = selected or 0,
        analyzed = 0,
        failed = 0,
        skipped = 0,
        notProcessed = 0,
        cancelled = false,
        backendUnavailable = false,
        failures = {},
    }
end

function BatchPolicy.addFailure(summary, filename, reason)
    summary.failed = summary.failed + 1
    if #summary.failures < 5 then
        summary.failures[#summary.failures + 1] = {
            filename = filename,
            reason = reason,
        }
    end
end

function BatchPolicy.shouldRetry(status, retriesUsed, cancelled)
    return not cancelled
        and retriesUsed < 1
        and (status == 500 or status == 502)
end

function BatchPolicy.markNotProcessed(summary, count)
    if count and count > 0 then
        summary.notProcessed = summary.notProcessed + count
    end
end

return BatchPolicy
