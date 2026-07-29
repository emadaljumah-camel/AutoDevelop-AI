local LrBinding = import("LrBinding")
local LrDialogs = import("LrDialogs")
local LrFunctionContext = import("LrFunctionContext")
local LrView = import("LrView")

local StyleProfiles = ModuleLoader.load("lib/StyleProfiles.lua")
local ModelProfiles = ModuleLoader.load("lib/ModelProfiles.lua")

local bind = LrView.bind

local RunSettingsDialog = {}

local function updateStyleDescription(properties)
    properties.selectedDescription =
        StyleProfiles.getDescription(properties.selectedProfileId) or ""
end

local function updateModelDescription(properties)
    properties.selectedModelDescription =
        ModelProfiles.getDescription(properties.selectedModelId) or ""
    properties.selectedModelAvailability =
        ModelProfiles.getAvailabilityLabel(properties.selectedModelId) or ""
end

function RunSettingsDialog.resultForSelection(
    profileId,
    modelId,
    rememberProfileAsDefault,
    rememberModelAsDefault
)
    return {
        confirmed = true,
        profileId = profileId,
        modelId = modelId,
        rememberProfileAsDefault = rememberProfileAsDefault == true,
        rememberModelAsDefault = rememberModelAsDefault == true,
    }
end

function RunSettingsDialog.show(storedProfileId, storedModelId)
    return LrFunctionContext.callWithContext(
        "AutoDevelopAIStyleSelection",
        function(context)
            local initialId, invalidStored =
                StyleProfiles.resolveInitialSelection(storedProfileId)
            local initialModelId, invalidStoredModel =
                ModelProfiles.resolveInitialSelection(storedModelId)
            local properties = LrBinding.makePropertyTable(context)
            properties.selectedProfileId = initialId
            properties.selectedDescription =
                StyleProfiles.getDescription(initialId)
            properties.selectedModelId = initialModelId
            properties.selectedModelDescription =
                ModelProfiles.getDescription(initialModelId)
            properties.selectedModelAvailability =
                ModelProfiles.getAvailabilityLabel(initialModelId)
            properties.rememberProfileAsDefault = false
            properties.rememberModelAsDefault = false
            properties.invalidStoredProfileMessage = invalidStored
                and "The previously saved style is unavailable. "
                    .. "Choose a style for this run."
                or ""
            properties.invalidStoredModelMessage = invalidStoredModel
                and "The previously saved model is unavailable. "
                    .. "Choose a model for this run."
                or ""

            properties:addObserver("selectedProfileId", function()
                updateStyleDescription(properties)
            end)
            properties:addObserver("selectedModelId", function()
                updateModelDescription(properties)
            end)

            local factory = LrView.osFactory()
            local result = LrDialogs.presentModalDialog({
                title = "AutoDevelop AI Settings",
                actionVerb = "Continue",
                cancelVerb = "Cancel",
                resizable = false,
                contents = factory:column({
                    bind_to_object = properties,
                    spacing = factory:control_spacing(),
                    fill_horizontal = 1,
                    factory:row({
                        spacing = factory:control_spacing(),
                        factory:static_text({
                            title = "Style",
                            width_in_chars = 12,
                        }),
                        factory:popup_menu({
                            value = bind("selectedProfileId"),
                            items = StyleProfiles.getChoices(),
                            width_in_chars = 28,
                        }),
                    }),
                    factory:static_text({
                        title = bind("selectedDescription"),
                        fill_horizontal = 1,
                        width_in_chars = 52,
                    }),
                    factory:static_text({
                        title = bind("invalidStoredProfileMessage"),
                        fill_horizontal = 1,
                        width_in_chars = 52,
                    }),
                    factory:row({
                        spacing = factory:control_spacing(),
                        factory:static_text({
                            title = "Model",
                            width_in_chars = 12,
                        }),
                        factory:popup_menu({
                            value = bind("selectedModelId"),
                            items = ModelProfiles.getSelectableChoices(),
                            width_in_chars = 28,
                        }),
                    }),
                    factory:static_text({
                        title = bind("selectedModelDescription"),
                        fill_horizontal = 1,
                        width_in_chars = 52,
                    }),
                    factory:static_text({
                        title = bind("selectedModelAvailability"),
                        fill_horizontal = 1,
                    }),
                    factory:static_text({
                        title = "Claude — Future",
                        fill_horizontal = 1,
                    }),
                    factory:static_text({
                        title = bind("invalidStoredModelMessage"),
                        fill_horizontal = 1,
                        width_in_chars = 52,
                    }),
                    factory:checkbox({
                        title = "Remember this style as default",
                        value = bind("rememberProfileAsDefault"),
                    }),
                    factory:checkbox({
                        title = "Remember this model as default",
                        value = bind("rememberModelAsDefault"),
                    }),
                }),
            })

            if result ~= "ok" then
                return {
                    confirmed = false,
                }
            end
            if not ModelProfiles.isSelectableId(
                properties.selectedModelId
            ) then
                return { confirmed = false }
            end
            return RunSettingsDialog.resultForSelection(
                properties.selectedProfileId,
                properties.selectedModelId,
                properties.rememberProfileAsDefault,
                properties.rememberModelAsDefault
            )
        end
    )
end

return RunSettingsDialog
