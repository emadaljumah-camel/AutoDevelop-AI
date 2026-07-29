require "ModuleLoader.lua"

local LrBinding = import("LrBinding")
local LrTasks = import("LrTasks")
local LrView = import("LrView")

local BackendClient = ModuleLoader.load("lib/BackendClient.lua")
local Logger = ModuleLoader.load("lib/Logger.lua")
local PluginManagerController =
    ModuleLoader.load("lib/PluginManagerController.lua")
local Preferences = ModuleLoader.load("lib/Preferences.lua")

local bind = LrView.bind
local share = LrView.share

local observedKeys = {
    "backendBaseUrl",
    "styleProfileId",
    "modelProfileId",
    "requestTimeoutText",
    "applyCrop",
    "confirmationMode",
    "loggingLevel",
}

local function loadValues(properties)
    properties._loadingPreferences = true
    PluginManagerController.populate(properties)
    properties._loadingPreferences = false
end

local function observePreference(properties, key)
    properties:addObserver(key, function()
        if properties._loadingPreferences then
            return
        end
        PluginManagerController.saveField(properties, key)
    end)
end

local function setPropertySafely(properties, key, value)
    return LrTasks.pcall(function()
        properties[key] = value
    end)
end

local function logConnectionResult(category)
    if category == "internal_error" then
        Logger.debug(
            "plugin_manager_test_connection_failed "
                .. "category=internal_error"
        )
        return
    end
    Logger.debug(
        "plugin_manager_test_connection_completed category="
            .. category
    )
end

local function testConnection(properties)
    if properties.connectionTestRunning then
        return
    end

    local settings, reason =
        PluginManagerController.validateAndSave(properties)
    if not settings then
        properties.connectionState = "invalid_settings"
        properties.connectionStatusText =
            "Invalid settings: " .. reason
        return
    end

    properties.connectionTestRunning = true
    properties.canTestConnection = false
    properties.connectionState = "testing"
    properties.connectionStatusText = "Testing…"
    Logger.debug("plugin_manager_test_connection_started")

    LrTasks.startAsyncTask(function()
        local callOk, result = LrTasks.pcall(
            BackendClient.getHealth,
            settings.backendBaseUrl,
            settings.requestTimeoutSeconds
        )
        local classified, outcome = LrTasks.pcall(
            PluginManagerController.classifyConnectionResult,
            callOk,
            result
        )
        if not classified then
            outcome = {
                state = "internal_error",
                text = "Connection test failed safely. "
                    .. "Check the plug-in log.",
                category = "internal_error",
            }
        end

        -- Reset each guard independently even if another UI update fails.
        setPropertySafely(
            properties,
            "connectionTestRunning",
            false
        )
        setPropertySafely(properties, "canTestConnection", true)
        setPropertySafely(
            properties,
            "connectionState",
            outcome.state
        )
        setPropertySafely(
            properties,
            "connectionStatusText",
            outcome.text
        )
        logConnectionResult(outcome.category)
    end)
end

local function validationText(factory)
    return factory:static_text({
        title = bind("validationMessage"),
        fill_horizontal = 1,
    })
end

local function preferenceRow(factory, label, control)
    return factory:row({
        spacing = factory:control_spacing(),
        factory:static_text({
            title = label,
            width = share("autodevelop_plugin_manager_label_width"),
        }),
        control,
    })
end

return {
    startDialog = function(propertyTable)
        Preferences.initializeDefaults()
        loadValues(propertyTable)
        if not propertyTable._observersInstalled then
            for _, key in ipairs(observedKeys) do
                observePreference(propertyTable, key)
            end
            propertyTable._observersInstalled = true
        end
    end,

    sectionsForTopOfDialog = function(factory, propertyTable)
        return {
            {
                title = "AutoDevelop AI",
                synopsis = bind("connectionStatusText"),

                factory:column({
                    bind_to_object = propertyTable,
                    spacing = factory:control_spacing(),
                    fill_horizontal = 1,

                    preferenceRow(
                        factory,
                        "Backend URL",
                        factory:edit_field({
                            value = bind("backendBaseUrl"),
                            immediate = true,
                            width_in_chars = 36,
                        })
                    ),

                    preferenceRow(
                        factory,
                        "Style profile",
                        factory:popup_menu({
                            value = bind("styleProfileId"),
                            items =
                                Preferences.getStyleProfileChoices(),
                        })
                    ),

                    preferenceRow(
                        factory,
                        "Default Model",
                        factory:popup_menu({
                            value = bind("modelProfileId"),
                            items =
                                Preferences.getModelProfileChoices(),
                        })
                    ),
                    factory:static_text({
                        title = "Claude — Future",
                        fill_horizontal = 1,
                    }),

                    preferenceRow(
                        factory,
                        "Request timeout (10-600 seconds)",
                        factory:edit_field({
                            value = bind("requestTimeoutText"),
                            width_in_chars = 6,
                            immediate = true,
                        })
                    ),

                    preferenceRow(
                        factory,
                        "Crop",
                        factory:checkbox({
                            title = "Apply recommended crop",
                            value = bind("applyCrop"),
                        })
                    ),

                    preferenceRow(
                        factory,
                        "Confirmation",
                        factory:popup_menu({
                            value = bind("confirmationMode"),
                            items =
                                Preferences.getConfirmationChoices(),
                        })
                    ),
                    factory:static_text({
                        title = "Never applies automatically after "
                            .. "preparation without showing the batch "
                            .. "confirmation.",
                        fill_horizontal = 1,
                    }),

                    preferenceRow(
                        factory,
                        "Logging",
                        factory:popup_menu({
                            value = bind("loggingLevel"),
                            items = Preferences.getLoggingChoices(),
                        })
                    ),

                    validationText(factory),

                    factory:row({
                        spacing = factory:control_spacing(),
                        factory:push_button({
                            title = "Test Connection",
                            enabled = bind("canTestConnection"),
                            action = function()
                                testConnection(propertyTable)
                            end,
                        }),
                        factory:push_button({
                            title = "Reset Defaults",
                            action = function()
                                if propertyTable.connectionTestRunning then
                                    propertyTable.connectionStatusText =
                                        "Wait for the connection test "
                                        .. "to finish."
                                    return
                                end
                                propertyTable._loadingPreferences = true
                                Preferences.resetDefaults()
                                PluginManagerController.populate(
                                    propertyTable
                                )
                                propertyTable._loadingPreferences = false
                            end,
                        }),
                    }),

                    factory:row({
                        spacing = factory:control_spacing(),
                        factory:static_text({
                            title = "Status:",
                            width = share(
                                "autodevelop_plugin_manager_label_width"
                            ),
                        }),
                        factory:static_text({
                            title = bind("connectionStatusText"),
                            fill_horizontal = 1,
                        }),
                    }),
                }),
            },
        }
    end,
}
