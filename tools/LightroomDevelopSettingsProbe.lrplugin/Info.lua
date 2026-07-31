return {
    LrSdkVersion = 13.0,
    LrSdkMinimumVersion = 6.0,
    LrToolkitIdentifier =
        "com.emad.autodevelopai.developsettingsprobe",
    LrPluginName = "AutoDevelop AI Develop Settings Probe",

    VERSION = {
        major = 1,
        minor = 0,
        revision = 0,
        build = 1,
    },

    LrLibraryMenuItems = {
        {
            title = "Dump Develop Settings",
            file = "DumpDevelopSettings.lua",
        },
        {
            title = "Start Upright/HDR Application Test",
            file = "ApplyDevelopModes.lua",
        },
        {
            title = "Record Upright/HDR Result and Restore",
            file = "RestoreDevelopModes.lua",
        },
    },
}
