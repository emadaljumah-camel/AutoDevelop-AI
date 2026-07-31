return {
    LrSdkVersion = 13.0,
    LrSdkMinimumVersion = 6.0,
    LrToolkitIdentifier = "com.emad.autodevelopai",
    LrPluginName = "AutoDevelop AI",
    LrPluginInfoProvider = "PluginManager.lua",

    VERSION = {
        major = 0,
        minor = 1,
        revision = 0,
        build = 1,
    },

    LrLibraryMenuItems = {
        {
            title = "Auto Develop Selected Photos",
            file = "AutoDevelopSelectedPhotos.lua",
        },
        {
            title = "Capture Editing Feedback",
            file = "CaptureEditingFeedback.lua",
        },
        {
            title = "Analyze Selected Photos",
            file = "AnalyzeSelectedPhotos.lua",
        },
        {
            title = "Settings",
            file = "Settings.lua",
        },
    },
}
