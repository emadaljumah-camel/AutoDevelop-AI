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
    ModuleLoader.load("lib/AutoDevelopCommand.lua").start()
end

function MenuActions.analyzeSelectedPhotos()
    ModuleLoader.load("lib/AnalyzeCommand.lua").start()
end

function MenuActions.applyRecommendedCrop()
    showPlaceholder("Apply Recommended Crop")
end

function MenuActions.showStyleProfiles()
    showPlaceholder("Style Profiles")
end

function MenuActions.showSettings()
    LrDialogs.message(
        "AutoDevelop AI Preferences",
        "Open File > Plug-in Manager, select AutoDevelop AI, and use "
            .. "the AutoDevelop AI preferences section.",
        "info"
    )
end

function MenuActions.showLogs()
    showPlaceholder("Logs")
end

return MenuActions
