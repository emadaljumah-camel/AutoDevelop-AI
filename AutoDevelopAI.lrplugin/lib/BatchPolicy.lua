local BatchPolicy = {}

function BatchPolicy.shouldRetry(result, retriesUsed, cancelled)
    local ErrorClassifier = ModuleLoader.load("lib/ErrorClassifier.lua")
    return not cancelled
        and retriesUsed < 1
        and ErrorClassifier.isRetryable(result)
end

return BatchPolicy
