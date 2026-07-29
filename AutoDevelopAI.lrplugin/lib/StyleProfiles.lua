local StyleProfiles = {}

local defaultId = "natural_travel"

local styles = {
    {
        id = "natural_travel",
        displayName = "Natural Travel",
        description =
            "Balanced, natural edits for travel and general photography.",
        sortOrder = 1,
    },
    {
        id = "landscape_impact",
        displayName = "Landscape Impact",
        description =
            "Stronger depth, contrast, atmosphere, and color separation "
            .. "for landscapes.",
        sortOrder = 2,
    },
    {
        id = "architecture",
        displayName = "Architecture",
        description =
            "Clean tonal control, structure, highlight protection, and "
            .. "restrained color.",
        sortOrder = 3,
    },
    {
        id = "stock_neutral",
        displayName = "Stock Neutral",
        description =
            "Neutral, commercially usable edits with controlled contrast "
            .. "and saturation.",
        sortOrder = 4,
    },
    {
        id = "portrait",
        displayName = "Portrait",
        description =
            "Gentle skin-friendly contrast, protected highlights, and "
            .. "restrained texture.",
        sortOrder = 5,
    },
    {
        id = "night",
        displayName = "Night",
        description =
            "Controlled shadows, protected highlights, noise-aware "
            .. "contrast, and balanced color.",
        sortOrder = 6,
    },
    {
        id = "documentary",
        displayName = "Documentary",
        description =
            "Realistic, restrained edits that preserve atmosphere, "
            .. "context, and authentic color.",
        sortOrder = 7,
    },
}

local stylesById = {}
for _, style in ipairs(styles) do
    stylesById[style.id] = style
end

local function copyStyle(style)
    if not style then
        return nil
    end
    return {
        id = style.id,
        displayName = style.displayName,
        description = style.description,
        sortOrder = style.sortOrder,
    }
end

function StyleProfiles.getChoices()
    local choices = {}
    for index, style in ipairs(styles) do
        choices[index] = {
            title = style.displayName,
            value = style.id,
        }
    end
    return choices
end

function StyleProfiles.getById(id)
    if type(id) ~= "string" then
        return nil
    end
    return copyStyle(stylesById[id])
end

function StyleProfiles.isValidId(id)
    return type(id) == "string" and stylesById[id] ~= nil
end

function StyleProfiles.getDisplayName(id)
    local style = StyleProfiles.getById(id)
    return style and style.displayName or nil
end

function StyleProfiles.getDescription(id)
    local style = StyleProfiles.getById(id)
    return style and style.description or nil
end

function StyleProfiles.getDefaultId()
    return defaultId
end

function StyleProfiles.resolveInitialSelection(storedId)
    if StyleProfiles.isValidId(storedId) then
        return storedId, false
    end
    return defaultId, true
end

return StyleProfiles
