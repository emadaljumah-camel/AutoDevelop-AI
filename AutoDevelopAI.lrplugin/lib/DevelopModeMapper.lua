local DevelopModeMapper = {}

local uprightModeToLightroom = {
    off = 0,
    auto = 1,
    full = 2,
    level = 3,
    vertical = 4,
}

local lightroomToUprightMode = {}
for mode, rawValue in pairs(uprightModeToLightroom) do
    lightroomToUprightMode[rawValue] = mode
end

function DevelopModeMapper.encodeUpright(mode)
    if type(mode) ~= "string" then
        return nil, "invalid_upright_mode"
    end
    local rawValue = uprightModeToLightroom[mode]
    if rawValue == nil then
        return nil, "unknown_upright_mode"
    end
    return rawValue, nil
end

function DevelopModeMapper.decodeUpright(rawValue)
    local mode = lightroomToUprightMode[rawValue]
    if mode == nil then
        return {
            mode = "unknown",
            rawValue = rawValue,
            supported = false,
        }
    end
    return {
        mode = mode,
        rawValue = rawValue,
        supported = true,
    }
end

function DevelopModeMapper.encodeHdr(enabled)
    if type(enabled) ~= "boolean" then
        return nil, "invalid_hdr_enabled"
    end
    return enabled and 1 or 0, nil
end

function DevelopModeMapper.decodeHdr(rawValue)
    if rawValue == 0 or rawValue == 1 then
        return {
            enabled = rawValue == 1,
            rawValue = rawValue,
            supported = true,
        }
    end
    return {
        enabled = nil,
        rawValue = rawValue,
        supported = false,
    }
end

return DevelopModeMapper
