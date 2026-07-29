local Json = {}

Json.null = {}

local escapeValues = {
    ['"'] = '\\"',
    ["\\"] = "\\\\",
    ["\b"] = "\\b",
    ["\f"] = "\\f",
    ["\n"] = "\\n",
    ["\r"] = "\\r",
    ["\t"] = "\\t",
}

local function isFiniteNumber(value)
    return type(value) == "number"
        and value == value
        and value ~= math.huge
        and value ~= -math.huge
end

local function encodeString(value)
    local escaped = value:gsub('[%z\1-\31\\"]', function(character)
        return escapeValues[character]
            or string.format("\\u%04x", string.byte(character))
    end)
    return '"' .. escaped .. '"'
end

local function arrayLength(value)
    local count = 0
    local maximum = 0
    for key in pairs(value) do
        if type(key) ~= "number"
            or key < 1
            or key ~= math.floor(key) then
            return nil
        end
        count = count + 1
        maximum = math.max(maximum, key)
    end
    if count == 0 then
        return nil
    end
    if count ~= maximum then
        error("JSON arrays must not contain gaps.", 0)
    end
    return maximum
end

local function encodeValue(value, seen)
    local valueType = type(value)
    if value == Json.null then
        return "null"
    end
    if valueType == "nil" then
        return "null"
    end
    if valueType == "boolean" then
        return value and "true" or "false"
    end
    if valueType == "number" then
        if not isFiniteNumber(value) then
            error("JSON numbers must be finite.", 0)
        end
        return tostring(value):gsub(",", ".")
    end
    if valueType == "string" then
        return encodeString(value)
    end
    if valueType ~= "table" then
        error("Unsupported JSON value type: " .. valueType, 0)
    end
    if seen[value] then
        error("Circular table cannot be encoded as JSON.", 0)
    end

    seen[value] = true
    local parts = {}
    local length = arrayLength(value)
    if length then
        for index = 1, length do
            parts[index] = encodeValue(value[index], seen)
        end
        seen[value] = nil
        return "[" .. table.concat(parts, ",") .. "]"
    end

    local keys = {}
    for key in pairs(value) do
        if type(key) ~= "string" then
            seen[value] = nil
            error("JSON object keys must be strings.", 0)
        end
        keys[#keys + 1] = key
    end
    table.sort(keys)
    for index, key in ipairs(keys) do
        parts[index] = encodeString(key)
            .. ":"
            .. encodeValue(value[key], seen)
    end
    seen[value] = nil
    return "{" .. table.concat(parts, ",") .. "}"
end

local function parseError(state, message)
    error(
        "Invalid JSON at character "
            .. tostring(state.index)
            .. ": "
            .. message,
        0
    )
end

local function skipWhitespace(state)
    while state.index <= state.length do
        local character = state.text:sub(state.index, state.index)
        if character ~= " "
            and character ~= "\t"
            and character ~= "\r"
            and character ~= "\n" then
            return
        end
        state.index = state.index + 1
    end
end

local function utf8Character(codepoint)
    if codepoint <= 0x7F then
        return string.char(codepoint)
    end
    if codepoint <= 0x7FF then
        return string.char(
            0xC0 + math.floor(codepoint / 0x40),
            0x80 + (codepoint % 0x40)
        )
    end
    if codepoint <= 0xFFFF then
        return string.char(
            0xE0 + math.floor(codepoint / 0x1000),
            0x80 + (math.floor(codepoint / 0x40) % 0x40),
            0x80 + (codepoint % 0x40)
        )
    end
    if codepoint <= 0x10FFFF then
        return string.char(
            0xF0 + math.floor(codepoint / 0x40000),
            0x80 + (math.floor(codepoint / 0x1000) % 0x40),
            0x80 + (math.floor(codepoint / 0x40) % 0x40),
            0x80 + (codepoint % 0x40)
        )
    end
    error("Invalid Unicode code point.", 0)
end

local function unicodeEscape(state)
    local digits = state.text:sub(state.index, state.index + 3)
    if #digits ~= 4 or not digits:match("^%x%x%x%x$") then
        parseError(state, "invalid Unicode escape")
    end
    state.index = state.index + 4
    local codepoint = tonumber(digits, 16)

    if codepoint >= 0xD800 and codepoint <= 0xDBFF then
        if state.text:sub(state.index, state.index + 1) ~= "\\u" then
            parseError(state, "high surrogate was not followed by a low surrogate")
        end
        state.index = state.index + 2
        local lowDigits = state.text:sub(state.index, state.index + 3)
        if #lowDigits ~= 4 or not lowDigits:match("^%x%x%x%x$") then
            parseError(state, "invalid low-surrogate escape")
        end
        state.index = state.index + 4
        local low = tonumber(lowDigits, 16)
        if low < 0xDC00 or low > 0xDFFF then
            parseError(state, "invalid low surrogate")
        end
        codepoint = 0x10000
            + ((codepoint - 0xD800) * 0x400)
            + (low - 0xDC00)
    elseif codepoint >= 0xDC00 and codepoint <= 0xDFFF then
        parseError(state, "unexpected low surrogate")
    end

    return utf8Character(codepoint)
end

local function parseString(state)
    state.index = state.index + 1
    local parts = {}
    while state.index <= state.length do
        local character = state.text:sub(state.index, state.index)
        state.index = state.index + 1
        if character == '"' then
            return table.concat(parts)
        end
        if character == "\\" then
            if state.index > state.length then
                parseError(state, "unfinished escape sequence")
            end
            local escaped = state.text:sub(state.index, state.index)
            state.index = state.index + 1
            local simple = {
                ['"'] = '"',
                ["\\"] = "\\",
                ["/"] = "/",
                b = "\b",
                f = "\f",
                n = "\n",
                r = "\r",
                t = "\t",
            }
            if simple[escaped] then
                parts[#parts + 1] = simple[escaped]
            elseif escaped == "u" then
                parts[#parts + 1] = unicodeEscape(state)
            else
                parseError(state, "invalid escape sequence")
            end
        else
            if string.byte(character) < 32 then
                parseError(state, "unescaped control character")
            end
            parts[#parts + 1] = character
        end
    end
    parseError(state, "unterminated string")
end

local parseValue

local function parseNumber(state)
    local startIndex = state.index
    if state.text:sub(state.index, state.index) == "-" then
        state.index = state.index + 1
    end

    local first = state.text:sub(state.index, state.index)
    if first == "0" then
        state.index = state.index + 1
    elseif first:match("[1-9]") then
        repeat
            state.index = state.index + 1
        until not state.text:sub(state.index, state.index):match("%d")
    else
        parseError(state, "invalid number")
    end

    if state.text:sub(state.index, state.index) == "." then
        state.index = state.index + 1
        if not state.text:sub(state.index, state.index):match("%d") then
            parseError(state, "fraction requires a digit")
        end
        repeat
            state.index = state.index + 1
        until not state.text:sub(state.index, state.index):match("%d")
    end

    local exponent = state.text:sub(state.index, state.index)
    if exponent == "e" or exponent == "E" then
        state.index = state.index + 1
        local sign = state.text:sub(state.index, state.index)
        if sign == "+" or sign == "-" then
            state.index = state.index + 1
        end
        if not state.text:sub(state.index, state.index):match("%d") then
            parseError(state, "exponent requires a digit")
        end
        repeat
            state.index = state.index + 1
        until not state.text:sub(state.index, state.index):match("%d")
    end

    local numberText = state.text:sub(startIndex, state.index - 1)
    local value = tonumber(numberText)
    if not isFiniteNumber(value) then
        parseError(state, "number is not finite")
    end
    return value
end

local function parseArray(state)
    state.index = state.index + 1
    skipWhitespace(state)
    local result = {}
    if state.text:sub(state.index, state.index) == "]" then
        state.index = state.index + 1
        return result
    end

    while true do
        result[#result + 1] = parseValue(state)
        skipWhitespace(state)
        local character = state.text:sub(state.index, state.index)
        if character == "]" then
            state.index = state.index + 1
            return result
        end
        if character ~= "," then
            parseError(state, "array requires ',' or ']'")
        end
        state.index = state.index + 1
        skipWhitespace(state)
    end
end

local function parseObject(state)
    state.index = state.index + 1
    skipWhitespace(state)
    local result = {}
    if state.text:sub(state.index, state.index) == "}" then
        state.index = state.index + 1
        return result
    end

    while true do
        if state.text:sub(state.index, state.index) ~= '"' then
            parseError(state, "object key must be a string")
        end
        local key = parseString(state)
        skipWhitespace(state)
        if state.text:sub(state.index, state.index) ~= ":" then
            parseError(state, "object key requires ':'")
        end
        state.index = state.index + 1
        skipWhitespace(state)
        local value = parseValue(state)
        if value ~= Json.null then
            result[key] = value
        end
        skipWhitespace(state)
        local character = state.text:sub(state.index, state.index)
        if character == "}" then
            state.index = state.index + 1
            return result
        end
        if character ~= "," then
            parseError(state, "object requires ',' or '}'")
        end
        state.index = state.index + 1
        skipWhitespace(state)
    end
end

parseValue = function(state)
    skipWhitespace(state)
    local character = state.text:sub(state.index, state.index)
    if character == '"' then
        return parseString(state)
    end
    if character == "{" then
        return parseObject(state)
    end
    if character == "[" then
        return parseArray(state)
    end
    if character == "-" or character:match("%d") then
        return parseNumber(state)
    end

    local literals = {
        ["true"] = true,
        ["false"] = false,
        ["null"] = Json.null,
    }
    for literal, value in pairs(literals) do
        if state.text:sub(
            state.index,
            state.index + #literal - 1
        ) == literal then
            state.index = state.index + #literal
            return value
        end
    end
    parseError(state, "unexpected value")
end

function Json.encode(value)
    local ok, encoded = pcall(encodeValue, value, {})
    if not ok then
        return nil, tostring(encoded)
    end
    return encoded
end

function Json.decode(value)
    if type(value) ~= "string" or value == "" then
        return nil, "Response body was empty."
    end

    local state = {
        text = value,
        index = 1,
        length = #value,
    }
    local ok, decoded = pcall(parseValue, state)
    if not ok then
        return nil, tostring(decoded)
    end
    skipWhitespace(state)
    if state.index <= state.length then
        return nil,
            "Invalid JSON at character "
                .. tostring(state.index)
                .. ": trailing data"
    end
    if type(decoded) ~= "table" or decoded == Json.null then
        return nil, "Decoded JSON was not an object."
    end
    return decoded
end

return Json
