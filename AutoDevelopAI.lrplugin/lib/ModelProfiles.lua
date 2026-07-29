local ModelProfiles = {}

local defaultId = "gemma"
local models = {
    {
        id = "gemma",
        displayName = "Gemma",
        provider = "local_openai_compatible",
        description = "Local Gemma vision model through an OpenAI-compatible inference server.",
        availability = "Configured by backend",
        selectable = true,
        sortOrder = 1,
    },
    {
        id = "qwen",
        displayName = "Qwen",
        provider = "local_openai_compatible",
        description = "Local Qwen vision model through an OpenAI-compatible inference server.",
        availability = "Configured by backend",
        selectable = true,
        sortOrder = 2,
    },
    {
        id = "gpt_oss",
        displayName = "GPT OSS",
        provider = "local_openai_compatible",
        description = "Local GPT-compatible open model through an OpenAI-compatible inference server.",
        availability = "Configured by backend",
        selectable = true,
        sortOrder = 3,
    },
    {
        id = "gemini",
        displayName = "Gemini",
        provider = "gemini_cloud",
        description = "Google Gemini cloud model using a configured API key and model identifier.",
        availability = "Requires backend API key",
        selectable = true,
        sortOrder = 4,
    },
    {
        id = "claude",
        displayName = "Claude",
        provider = "future",
        description = "Claude provider integration is reserved for a future phase.",
        availability = "Future",
        selectable = false,
        sortOrder = 5,
    },
}

local byId = {}
for _, model in ipairs(models) do
    byId[model.id] = model
end

local function copy(model)
    if not model then
        return nil
    end
    return {
        id = model.id,
        displayName = model.displayName,
        provider = model.provider,
        description = model.description,
        availability = model.availability,
        selectable = model.selectable,
        sortOrder = model.sortOrder,
    }
end

function ModelProfiles.getChoices()
    local choices = {}
    for index, model in ipairs(models) do
        choices[index] = {
            title = model.displayName,
            value = model.id,
        }
    end
    return choices
end

function ModelProfiles.getSelectableChoices()
    local choices = {}
    for _, model in ipairs(models) do
        if model.selectable then
            choices[#choices + 1] = {
                title = model.displayName,
                value = model.id,
            }
        end
    end
    return choices
end

function ModelProfiles.getById(id)
    return type(id) == "string" and copy(byId[id]) or nil
end

function ModelProfiles.isKnownId(id)
    return type(id) == "string" and byId[id] ~= nil
end

function ModelProfiles.isSelectableId(id)
    return ModelProfiles.isKnownId(id) and byId[id].selectable == true
end

function ModelProfiles.getDisplayName(id)
    local model = ModelProfiles.getById(id)
    return model and model.displayName or nil
end

function ModelProfiles.getDescription(id)
    local model = ModelProfiles.getById(id)
    return model and model.description or nil
end

function ModelProfiles.getAvailabilityLabel(id)
    local model = ModelProfiles.getById(id)
    return model and model.availability or nil
end

function ModelProfiles.getDefaultId()
    return defaultId
end

function ModelProfiles.resolveInitialSelection(storedId)
    if ModelProfiles.isSelectableId(storedId) then
        return storedId, false
    end
    return defaultId, true
end

return ModelProfiles
