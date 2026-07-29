local Config = {}

Config.API_PREFIX = "/autodevelop/v1"
Config.SCHEMA_VERSION = "1.0"

Config.defaults = {
    backendBaseUrl = "http://127.0.0.1:8005",
    requestTimeoutSeconds = 120,
    applyCrop = true,
    confirmationMode = "always",
    loggingLevel = "info",
}

Config.apiPaths = {
    analyze = Config.API_PREFIX .. "/analyze",
    develop = Config.API_PREFIX .. "/develop",
    health = Config.API_PREFIX .. "/health",
}
Config.logPath = "logs/autodevelop.log"
Config.tempDirectory = "temp"

function Config.apiUrl(baseUrl, path)
    return tostring(baseUrl):gsub("/+$", "") .. path
end

return Config
