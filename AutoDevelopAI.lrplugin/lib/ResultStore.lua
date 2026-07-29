local Utils = require("lib.Utils")

local ResultStore = {}
local results = {}
local resultCount = 0

function ResultStore.put(photoKey, result)
    if results[photoKey] == nil then
        resultCount = resultCount + 1
    end
    results[photoKey] = Utils.deepCopy(result)
end

function ResultStore.get(photoKey)
    local result = results[photoKey]
    if result == nil then
        return nil
    end
    return Utils.deepCopy(result)
end

function ResultStore.remove(photoKey)
    if results[photoKey] ~= nil then
        results[photoKey] = nil
        resultCount = resultCount - 1
    end
end

function ResultStore.clear()
    results = {}
    resultCount = 0
end

function ResultStore.count()
    return resultCount
end

return ResultStore
