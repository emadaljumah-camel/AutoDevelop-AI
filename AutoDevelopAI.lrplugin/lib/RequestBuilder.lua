local Config = require("lib.Config")
local ExifMapper = require("lib.ExifMapper")
local Utils = require("lib.Utils")

local RequestBuilder = {}

function RequestBuilder.build(photo, previewPath, options)
    options = options or {}
    local styleProfile = Utils.trim(options.styleProfileId)
        or Config.DEFAULT_STYLE_PROFILE
    local uuidFactory = options.uuidFactory or Utils.newUuid
    local requestId = uuidFactory()

    if not Utils.isUuid(requestId) then
        return nil, "Request ID generator returned an invalid UUID."
    end
    local filename = Utils.photoFilename(photo)

    return {
        schema_version = "1.0",
        request_id = requestId,
        filename = filename,
        preview_path = previewPath,
        exif = ExifMapper.mapExif(photo),
        current_settings = ExifMapper.mapDevelopSettings(photo),
        options = {
            style_profile = styleProfile,
        },
    }
end

return RequestBuilder
