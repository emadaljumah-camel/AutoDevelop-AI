local LrDialogs = import("LrDialogs")

local ErrorClassifier = ModuleLoader.load("lib/ErrorClassifier.lua")

local ErrorDialog = {}

local messages = {
    backend_not_running = {
        title = "AutoDevelop AI Backend Not Available",
        text = "Could not connect to the AutoDevelop AI backend.\n\nCheck "
            .. "that the backend is running, the configured URL is correct, "
            .. "and port 8005 is accessible.",
    },
    invalid_profile = {
        title = "Invalid Style Profile",
        text = "The selected style profile is not available. Open Plug-in "
            .. "Manager and select a valid style profile.",
    },
    model_timeout = {
        title = "AutoDevelop AI Timed Out",
        text = "The model did not respond before the configured timeout. "
            .. "Check LM Studio or increase the request timeout.",
    },
    network_error = {
        title = "Network Error",
        text = "The connection was interrupted. Check the backend address "
            .. "and local network, then try again.",
    },
    invalid_response = {
        title = "Invalid Backend Response",
        text = "The backend returned data the plug-in could not safely use. "
            .. "The affected photo was not changed.",
    },
    backend_error = {
        title = "AutoDevelop AI Backend Error",
        text = "The backend could not complete the request. Review the "
            .. "backend log and try again.",
    },
    validation_error = {
        title = "Invalid request",
        text = "The request or plug-in preferences were invalid. Review "
            .. "the preferences and try again.",
    },
    cancelled = {
        title = "Cancelled",
        text = "Processing was cancelled. Remaining photos were not "
            .. "processed.",
    },
    internal_error = {
        title = "AutoDevelop AI Error",
        text = "The plug-in encountered an unexpected error. No unsafe "
            .. "changes were applied.",
    },
}

function ErrorDialog.details(category)
    return messages[category] or messages[ErrorClassifier.codes.internalError]
end

local function safeBaseUrl(value)
    if type(value) ~= "string" then
        return nil
    end
    return value:gsub("^(https?://)[^/@]+@", "%1")
end

function ErrorDialog.messageFor(category, context)
    local message = ErrorDialog.details(category).text
    context = context or {}
    if category == ErrorClassifier.codes.backendNotRunning then
        local baseUrl = safeBaseUrl(context.backendBaseUrl)
        if baseUrl then
            message = message .. "\n\nConfigured URL: " .. baseUrl
        end
    elseif category == ErrorClassifier.codes.invalidProfile
        and type(context.profileId) == "string" then
        message = message
            .. '\n\nSelected profile: "'
            .. context.profileId
            .. '"'
    elseif category == ErrorClassifier.codes.modelTimeout
        and type(context.requestTimeoutSeconds) == "number" then
        message = message
            .. "\n\nConfigured timeout: "
            .. tostring(context.requestTimeoutSeconds)
            .. " seconds"
    end
    return message
end

function ErrorDialog.show(category, context)
    local details = ErrorDialog.details(category)
    LrDialogs.message(
        details.title,
        ErrorDialog.messageFor(category, context),
        category == ErrorClassifier.codes.cancelled
            and "warning" or "critical"
    )
end

return ErrorDialog
