local LrLogger = import("LrLogger")

local Preferences = ModuleLoader.load("lib/Preferences.lua")

local logger = LrLogger("com.emad.autodevelopai")
logger:enable("logfile")

local Logger = {}

local priorities = {
    error = 1,
    warning = 2,
    info = 3,
    debug = 4,
}

local function enabled(level)
    local configured = Preferences.getRuntimeLoggingLevel()
    return priorities[level] <= priorities[configured]
end

function Logger.info(message)
    if enabled("info") then
        logger:info(tostring(message))
    end
end

function Logger.warn(message)
    if enabled("warning") then
        logger:warn(tostring(message))
    end
end

function Logger.error(message)
    if enabled("error") then
        logger:error(tostring(message))
    end
end

function Logger.debug(message)
    if enabled("debug") then
        logger:debug(tostring(message))
    end
end

return Logger
