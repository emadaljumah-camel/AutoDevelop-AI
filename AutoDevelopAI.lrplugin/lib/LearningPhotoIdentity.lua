local Sha256 = ModuleLoader.load("lib/Sha256.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")

local LearningPhotoIdentity = {}

local function canonicalIdentity(photo)
    local localIdentifier =
        Utils.safePhotoProperty(photo, "localIdentifier")
    if localIdentifier ~= nil then
        return "local|" .. tostring(localIdentifier)
    end
    local uuid = Utils.trim(Utils.safeRawMetadata(photo, "uuid"))
    if uuid then
        return "uuid|" .. uuid
    end
    local path = Utils.trim(Utils.safeRawMetadata(photo, "path"))
        or "no-path"
    local captured = Utils.trim(
        Utils.safeRawMetadata(photo, "dateTimeOriginalISO8601")
    ) or "no-date"
    local cameraSerial = Utils.trim(
        Utils.safeRawMetadata(photo, "cameraSerialNumber")
    ) or "no-serial"
    local copyName = Utils.trim(
        Utils.safeFormattedMetadata(photo, "copyName")
    ) or "master"
    return table.concat({
        "fallback",
        path:lower():gsub("\\", "/"),
        captured,
        cameraSerial,
        copyName,
    }, "|")
end

function LearningPhotoIdentity.forPhoto(photo)
    return Sha256.digest(canonicalIdentity(photo))
end

function LearningPhotoIdentity.localIdentifier(photo)
    local value = Utils.safePhotoProperty(photo, "localIdentifier")
    return value ~= nil and tostring(value) or nil
end

return LearningPhotoIdentity
