require "ModuleLoader.lua"

local LrTasks = import("LrTasks")
local LrView = import("LrView")

local BackendClient = ModuleLoader.load("lib/BackendClient.lua")
local Preferences = ModuleLoader.load("lib/Preferences.lua")

local bind = LrView.bind

local preferenceKeys = {
    "backendBaseUrl",
    "styleProfileId",
    "requestTimeoutSeconds",
    "applyCrop",
    "confirmationMode",
    "loggingLevel",
}

local function loadValues(propertyTable)
    propertyTable._loadingPreferences = true
    local values = Preferences.valuesForUi()
    for _, key in ipairs(preferenceKeys) do
        propertyTable[key] = values[key]
        local _, reason = Preferences.validate(key, values[key])
        propertyTable[key .. "Validation"] = reason or ""
    end
    if propertyTable.connectionStatus == nil then
        propertyTable.connectionStatus = "Not tested"
    end
    if propertyTable.testingConnection == nil then
        propertyTable.testingConnection = false
    end
    propertyTable._loadingPreferences = false
end

local function observePreference(propertyTable, key)
    propertyTable:addObserver(key, function(_, _, value)
        if propertyTable._loadingPreferences then
            return
        end
        local _, reason = Preferences.set(key, value)
        propertyTable[key .. "Validation"] = reason or ""
    end)
end

local function testConnection(propertyTable)
    if propertyTable.testingConnection then
        return
    end
    local baseUrl, urlError =
        Preferences.validate("backendBaseUrl", propertyTable.backendBaseUrl)
    local timeout, timeoutError = Preferences.validate(
        "requestTimeoutSeconds",
        propertyTable.requestTimeoutSeconds
    )
    if not baseUrl or not timeout then
        propertyTable.connectionStatus =
            urlError or timeoutError or "Preferences are invalid."
        return
    end

    propertyTable.testingConnection = true
    propertyTable.connectionStatus = "Testing connection..."
    LrTasks.startAsyncTask(function()
        local callOk, result = LrTasks.pcall(
            BackendClient.getHealth,
            baseUrl,
            timeout
        )
        if callOk and result and result.ok then
            propertyTable.connectionStatus = "Connected - "
                .. result.service
                .. " "
                .. result.version
        elseif callOk and result
            and result.category == "model_timeout" then
            propertyTable.connectionStatus = "Timed out"
        elseif callOk and result
            and (result.category == "backend_not_running"
                or result.category == "network_error") then
            propertyTable.connectionStatus = "Backend not running"
        else
            propertyTable.connectionStatus = "Invalid response"
        end
        propertyTable.testingConnection = false
    end)
end

local function validationText(factory, key)
    return factory:static_text({
        title = bind(key .. "Validation"),
        fill_horizontal = 1,
    })
end

local function preferenceRow(factory, label, control)
    return factory:row({
        spacing = factory:control_spacing(),
        factory:static_text({
            title = label,
            width = 150,
        }),
        control,
    })
end

return {
    startDialog = function(propertyTable)
        Preferences.initializeDefaults()
        loadValues(propertyTable)
        for _, key in ipairs(preferenceKeys) do
            observePreference(propertyTable, key)
        end
    end,

    sectionsForTopOfDialog = function(factory, propertyTable)
        return {
            {
                title = "AutoDevelop AI",
                synopsis = bind("connectionStatus"),

                factory:column({
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
                    validationText(factory, "backendBaseUrl"),

                    preferenceRow(
                        factory,
                        "Style profile",
                        factory:popup_menu({
                            value = bind("styleProfileId"),
                            items = Preferences.profileChoices,
                        })
                    ),
                    validationText(factory, "styleProfileId"),

                    preferenceRow(
                        factory,
                        "Request timeout (10-600 seconds)",
                        factory:edit_field({
                            value = bind("requestTimeoutSeconds"),
                            immediate = true,
                            width_in_digits = 4,
                            precision = 0,
                        })
                    ),
                    validationText(factory, "requestTimeoutSeconds"),

                    preferenceRow(
                        factory,
                        "Crop",
                        factory:checkbox({
                            title = "Apply recommended crop",
                            value = bind("applyCrop"),
                        })
                    ),
                    validationText(factory, "applyCrop"),

                    preferenceRow(
                        factory,
                        "Confirmation",
                        factory:popup_menu({
                            value = bind("confirmationMode"),
                            items = Preferences.confirmationChoices,
                        })
                    ),
                    validationText(factory, "confirmationMode"),
                    factory:static_text({
                        title = "Never ask applies automatically after "
                            .. "preparation without showing the batch "
                            .. "confirmation.",
                        fill_horizontal = 1,
                    }),

                    preferenceRow(
                        factory,
                        "Logging",
                        factory:popup_menu({
                            value = bind("loggingLevel"),
                            items = Preferences.loggingChoices,
                        })
                    ),
                    validationText(factory, "loggingLevel"),

                    factory:row({
                        spacing = factory:control_spacing(),
                        factory:push_button({
                            title = "Test Connection",
                            action = function()
                                testConnection(propertyTable)
                            end,
                        }),
                        factory:push_button({
                            title = "Reset Defaults",
                            action = function()
                                if propertyTable.testingConnection then
                                    propertyTable.connectionStatus =
                                        "Wait for the connection test to finish."
                                    return
                                end
                                Preferences.resetDefaults()
                                loadValues(propertyTable)
                            end,
                        }),
                        factory:static_text({
                            title = bind("connectionStatus"),
                            fill_horizontal = 1,
                        }),
                    }),
                }),
            },
        }
    end,
}
