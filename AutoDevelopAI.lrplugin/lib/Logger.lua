local LrLogger = import("LrLogger")

local logger = LrLogger("com.emad.autodevelopai")
logger:enable("logfile")

local Logger = {}

function Logger.info(message)
    logger:info(tostring(message))
end

function Logger.warn(message)
    logger:warn(tostring(message))
end

function Logger.error(message)
    logger:error(tostring(message))
end

function Logger.debug(message)
    logger:debug(tostring(message))
end

return Logger
