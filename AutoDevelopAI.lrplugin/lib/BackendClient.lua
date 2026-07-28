local LrHttp = import("LrHttp")

local Config = require("lib.Config")

local BackendClient = {}

function BackendClient.getHealth()
    return LrHttp.get(Config.apiBaseUrl .. "/health")
end

return BackendClient
