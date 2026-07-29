local LrDialogs = import("LrDialogs")

local MenuActions = {}

local function showPlaceholder(commandName)
    LrDialogs.message(
        "AutoDevelop AI",
        commandName .. " is included in the initial skeleton and is not implemented yet.",
        "info"
    )
end

function MenuActions.autoDevelopSelectedPhotos()
    require("lib.AutoDevelopCommand").start()
end

function MenuActions.analyzeSelectedPhotos()
    require("lib.AnalyzeCommand").start()
end

function MenuActions.applyRecommendedCrop()
    showPlaceholder("Apply Recommended Crop")
end

function MenuActions.showStyleProfiles()
    showPlaceholder("Style Profiles")
end

function MenuActions.showSettings()
    showPlaceholder("Settings")
end

function MenuActions.showLogs()
    showPlaceholder("Logs")
end

return MenuActions
