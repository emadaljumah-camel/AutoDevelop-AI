local LrJson = import("LrJson")

local Json = {}

function Json.encode(value)
    local ok, encoded = pcall(function()
        return LrJson.encode(value)
    end)
    if not ok then
        return nil, tostring(encoded)
    end
    return encoded
end

function Json.decode(value)
    if type(value) ~= "string" or value == "" then
        return nil, "Response body was empty."
    end
    local ok, decoded = pcall(function()
        return LrJson.decode(value)
    end)
    if not ok then
        return nil, tostring(decoded)
    end
    if type(decoded) ~= "table" then
        return nil, "Decoded JSON was not an object."
    end
    return decoded
end

return Json
