local LrTasks = import("LrTasks")

local Utils = {}

local randomSeeded = false
local uuidCounter = 0

function Utils.trim(value)
    if type(value) ~= "string" then
        return nil
    end
    local trimmed = value:match("^%s*(.-)%s*$")
    if trimmed == "" then
        return nil
    end
    return trimmed
end

function Utils.isFiniteNumber(value)
    return type(value) == "number"
        and value == value
        and value ~= math.huge
        and value ~= -math.huge
end

function Utils.safeRawMetadata(photo, key)
    if not photo or type(photo.getRawMetadata) ~= "function" then
        return nil
    end
    local ok, value = LrTasks.pcall(function()
        return photo:getRawMetadata(key)
    end)
    if ok then
        return value
    end
    return nil
end

function Utils.safeFormattedMetadata(photo, key)
    if not photo or type(photo.getFormattedMetadata) ~= "function" then
        return nil
    end
    local ok, value = LrTasks.pcall(function()
        return photo:getFormattedMetadata(key)
    end)
    if ok then
        return value
    end
    return nil
end

function Utils.safePhotoProperty(photo, key)
    if not photo or type(key) ~= "string" then
        return nil
    end
    local ok, value = pcall(function()
        return photo[key]
    end)
    if ok then
        return value
    end
    return nil
end

local function seedRandom()
    if randomSeeded then
        return
    end
    uuidCounter = uuidCounter + 1
    local seed = os.time() + math.floor(os.clock() * 1000000) + uuidCounter
    math.randomseed(seed)
    math.random()
    math.random()
    math.random()
    randomSeeded = true
end

local function randomInteger(randomFn, minimum, maximum)
    if randomFn then
        return randomFn(minimum, maximum)
    end
    seedRandom()
    return math.random(minimum, maximum)
end

function Utils.newUuid(randomFn)
    local template = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx"
    return (template:gsub("[xy]", function(character)
        local value
        if character == "x" then
            value = randomInteger(randomFn, 0, 15)
        else
            value = randomInteger(randomFn, 8, 11)
        end
        return string.format("%x", value)
    end))
end

function Utils.isUuid(value)
    if type(value) ~= "string" then
        return false
    end
    local first, second, third, fourth, fifth = value:match(
        "^([0-9a-fA-F]+)%-([0-9a-fA-F]+)%-([0-9a-fA-F]+)%-"
            .. "([0-9a-fA-F]+)%-([0-9a-fA-F]+)$"
    )
    return first ~= nil
        and #first == 8
        and #second == 4
        and #third == 4
        and third:sub(1, 1):lower() == "4"
        and #fourth == 4
        and fourth:sub(1, 1):lower():match("[89ab]") ~= nil
        and #fifth == 12
end

local function photoId(photo)
    local identifier = Utils.safePhotoProperty(photo, "localIdentifier")
    if identifier ~= nil then
        return "photo_" .. tostring(identifier)
    end
    local uuid = Utils.trim(Utils.safeRawMetadata(photo, "uuid"))
    if uuid then
        return "photo_" .. uuid
    end
    return "photo_catalog_item"
end

local function pathBasename(path)
    path = Utils.trim(path)
    if path then
        local leaf = Utils.trim(path:match("([^/\\]+)$"))
        if leaf then
            return leaf
        end
    end
    return nil
end

function Utils.photoId(photo)
    return photoId(photo)
end

function Utils.capturePhotoIdentity(photo)
    local internalId = photoId(photo)
    local displayFilename = Utils.trim(
        Utils.safeFormattedMetadata(photo, "fileName")
    )
    if not displayFilename then
        displayFilename = Utils.trim(
            Utils.safeRawMetadata(photo, "fileName")
        )
    end
    if not displayFilename then
        displayFilename = pathBasename(
            Utils.safeRawMetadata(photo, "path")
        )
    end
    return {
        photoId = internalId,
        displayFilename = displayFilename or internalId,
    }
end

function Utils.photoFilename(photo)
    return Utils.capturePhotoIdentity(photo).displayFilename
end

function Utils.photoKey(photo)
    local identifier = Utils.safePhotoProperty(photo, "localIdentifier")
    if identifier ~= nil then
        return "local:" .. tostring(identifier)
    end

    local uuid = Utils.trim(Utils.safeRawMetadata(photo, "uuid"))
    if uuid then
        return "uuid:" .. uuid
    end

    local path = Utils.trim(Utils.safeRawMetadata(photo, "path"))
        or "no-path"
    local filename = Utils.photoFilename(photo)
    local captureDate = Utils.trim(
        Utils.safeRawMetadata(photo, "dateTimeOriginalISO8601")
    ) or "no-date"
    local copyKind = "master"
    local copyName = "no-copy-name"
    if Utils.safeRawMetadata(photo, "isVirtualCopy") == true then
        copyKind = "virtual"
        copyName = Utils.trim(
            Utils.safeFormattedMetadata(photo, "copyName")
        ) or "unnamed"
    end
    return table.concat({
        "fallback",
        path,
        filename,
        captureDate,
        copyKind,
        copyName,
    }, "|")
end

function Utils.nowIso(clockFn)
    local timestamp = clockFn and clockFn() or os.time()
    return os.date("!%Y-%m-%dT%H:%M:%SZ", timestamp)
end

function Utils.deepCopy(value, seen)
    if type(value) ~= "table" then
        return value
    end
    seen = seen or {}
    if seen[value] then
        return seen[value]
    end
    local copy = {}
    seen[value] = copy
    for key, item in pairs(value) do
        copy[Utils.deepCopy(key, seen)] = Utils.deepCopy(item, seen)
    end
    return copy
end

-- This function does not redact arbitrary input. Callers must use it only for
-- content already known to be safe for display or logging.
function Utils.safeMessage(value, fallback)
    local text = Utils.trim(tostring(value or ""))
    if not text then
        return fallback or "Unknown error."
    end
    text = text:gsub("[\r\n]+", " ")
    if #text > 240 then
        text = text:sub(1, 237) .. "..."
    end
    return text
end

-- This helper is intentionally limited to stable identifiers. It must not be
-- used to transform arbitrary exception text into a log message.
function Utils.safeErrorCode(value, fallbackCode)
    if type(value) == "string"
        and value:match("^[a-z][a-z0-9_%.%-]*$") then
        return value
    end
    if type(fallbackCode) == "string"
        and fallbackCode:match("^[a-z][a-z0-9_%.%-]*$") then
        return fallbackCode
    end
    return "internal_error"
end

return Utils
