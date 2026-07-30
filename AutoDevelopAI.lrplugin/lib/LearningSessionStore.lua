local Preferences = ModuleLoader.load("lib/Preferences.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")

local LearningSessionStore = {}
local MAXIMUM_ENTRIES = 500

local function sessions()
    return Preferences.getLearningPendingSessions()
end

function LearningSessionStore.put(photoKey, values)
    if type(photoKey) ~= "string" or #photoKey ~= 64
        or type(values) ~= "table" then
        return false
    end
    local stored = sessions()
    stored[photoKey] = {
        sessionId = values.sessionId,
        photoKey = photoKey,
        baselineTimestamp = values.baselineTimestamp,
        profileId = values.profileId,
        modelId = values.modelId,
        filename = values.filename,
    }
    local count = 0
    for _ in pairs(stored) do
        count = count + 1
    end
    while count > MAXIMUM_ENTRIES do
        local oldestKey
        local oldestTimestamp
        for key, item in pairs(stored) do
            local timestamp = tostring(item.baselineTimestamp or "")
            if not oldestTimestamp or timestamp < oldestTimestamp then
                oldestKey = key
                oldestTimestamp = timestamp
            end
        end
        stored[oldestKey] = nil
        count = count - 1
    end
    Preferences.setLearningPendingSessions(stored)
    return true
end

function LearningSessionStore.get(photoKey)
    local value = sessions()[photoKey]
    return value and Utils.deepCopy(value) or nil
end

function LearningSessionStore.remove(photoKey)
    local stored = sessions()
    local existed = stored[photoKey] ~= nil
    stored[photoKey] = nil
    Preferences.setLearningPendingSessions(stored)
    return existed
end

return LearningSessionStore
