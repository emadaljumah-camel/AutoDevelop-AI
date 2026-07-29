local LrBinding = import("LrBinding")
local LrDialogs = import("LrDialogs")
local LrFunctionContext = import("LrFunctionContext")
local LrView = import("LrView")

local StyleProfiles = ModuleLoader.load("lib/StyleProfiles.lua")

local bind = LrView.bind

local StyleSelectionDialog = {}

local function updateDescription(properties)
    properties.selectedDescription =
        StyleProfiles.getDescription(properties.selectedProfileId) or ""
end

function StyleSelectionDialog.resultForSelection(
    profileId,
    rememberAsDefault
)
    return {
        confirmed = true,
        profileId = profileId,
        rememberAsDefault = rememberAsDefault == true,
    }
end

function StyleSelectionDialog.show(storedProfileId)
    return LrFunctionContext.callWithContext(
        "AutoDevelopAIStyleSelection",
        function(context)
            local initialId, invalidStored =
                StyleProfiles.resolveInitialSelection(storedProfileId)
            local properties = LrBinding.makePropertyTable(context)
            properties.selectedProfileId = initialId
            properties.selectedDescription =
                StyleProfiles.getDescription(initialId)
            properties.rememberAsDefault = false
            properties.invalidStoredProfileMessage = invalidStored
                and "The previously saved style is unavailable. "
                    .. "Choose a style for this run."
                or ""

            properties:addObserver("selectedProfileId", function()
                updateDescription(properties)
            end)

            local factory = LrView.osFactory()
            local result = LrDialogs.presentModalDialog({
                title = "AutoDevelop AI Style",
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
                    factory:checkbox({
                        title = "Remember this style as default",
                        value = bind("rememberAsDefault"),
                    }),
                }),
            })

            if result ~= "ok" then
                return {
                    confirmed = false,
                }
            end
            return StyleSelectionDialog.resultForSelection(
                properties.selectedProfileId,
                properties.rememberAsDefault
            )
        end
    )
end

return StyleSelectionDialog
