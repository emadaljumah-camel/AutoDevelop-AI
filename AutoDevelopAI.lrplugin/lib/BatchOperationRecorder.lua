local Utils = ModuleLoader.load("lib/Utils.lua")

local BatchOperationRecorder = {}

local function isExactNonBlankString(value)
    return type(value) == "string" and Utils.trim(value) == value
end

local function isValidOperation(operation)
    return type(operation) == "table"
        and operation.photo ~= nil
        and isExactNonBlankString(operation.filename)
        and isExactNonBlankString(operation.requestId)
        and type(operation.originalSettings) == "table"
        and type(operation.mappedSettings) == "table"
        and operation.applicationStatus == "pending"
end

function BatchOperationRecorder.tryRecord(state)
    state = state or {}
    if state.cancelled == true
        or state.preparationResult == "cancelled" then
        return "cancelled"
    end
    if state.terminalFailure == true then
        return "terminal_failure"
    end
    if state.preparationResult ~= "ready"
        or type(state.operations) ~= "table"
        or not isValidOperation(state.operation) then
        return "invalid_operation"
    end

    state.operations[#state.operations + 1] = state.operation
    return "recorded"
end

return BatchOperationRecorder
