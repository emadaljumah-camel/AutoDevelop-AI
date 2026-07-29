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
        originalSettings = Utils.deepCopy(values.originalSettings or {}),
        mappedSettings = Utils.deepCopy(values.mappedSettings or {}),
        cropIncluded = values.cropIncluded == true,
        denoiseRecommended = values.denoiseRecommended == true,
        warnings = Utils.deepCopy(values.warnings or {}),
        model = values.model,
        resolvedModel = values.resolvedModel,
        processingDurationMs = values.processingDurationMs,
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
