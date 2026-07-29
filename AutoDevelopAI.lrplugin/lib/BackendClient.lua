local LrHttp = import("LrHttp")

local Config = ModuleLoader.load("lib/Config.lua")

local BackendClient = {}

function BackendClient.getHealth()
    return LrHttp.get(Config.apiBaseUrl .. "/health")
end

return BackendClient
