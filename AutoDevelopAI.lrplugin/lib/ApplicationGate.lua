local ApplicationGate = {}

local function decision(
    shouldApply,
    reason,
    cancelled,
    terminalFailure
)
    return {
        shouldApply = shouldApply,
        reason = reason,
        cancelled = cancelled,
        terminalFailure = terminalFailure,
    }
end

function ApplicationGate.evaluate(state)
    state = state or {}
    if state.preparationCancelled == true
        or state.progressCancelled == true then
        return decision(false, "cancelled", true, false)
    end
    if state.terminalFailure == true then
        return decision(false, "terminal_failure", false, true)
    end

    local readyCount = tonumber(state.readyCount) or 0
    if readyCount <= 0 then
        return decision(false, "no_operations", false, false)
    end

    local confirmationMode = state.confirmationMode
    if confirmationMode == "always" then
        if state.confirmationAccepted == nil then
            return decision(false, "confirmation_required", false, false)
        end
        if state.confirmationAccepted ~= true then
            return decision(false, "confirmation_declined", false, false)
        end
    elseif confirmationMode ~= "never" then
        return decision(false, "invalid_confirmation_mode", false, false)
    end

    return decision(true, "ready", false, false)
end

return ApplicationGate
