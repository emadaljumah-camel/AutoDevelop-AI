local Config = require("lib.Config")
local ExifMapper = require("lib.ExifMapper")
local Utils = require("lib.Utils")

local RequestBuilder = {}

local function buildBase(photo, previewPath, options)
    options = options or {}
    local styleProfile = Utils.trim(options.styleProfileId)
        or Config.DEFAULT_STYLE_PROFILE
    local uuidFactory = options.uuidFactory or Utils.newUuid
    local requestId = uuidFactory()

    if not Utils.isUuid(requestId) then
        return nil, "Request ID generator returned an invalid UUID."
    end
    local filename = Utils.photoFilename(photo)

    local request = {
        schema_version = "1.0",
        request_id = requestId,
        filename = filename,
        preview_path = previewPath,
        exif = ExifMapper.mapExif(photo),
        current_settings = ExifMapper.mapDevelopSettings(photo),
        options = {},
    }
    request.options.style_profile = styleProfile
    return request
end

function RequestBuilder.build(photo, previewPath, options)
    return buildBase(photo, previewPath, options)
end

function RequestBuilder.buildAnalyze(photo, previewPath, options)
    return buildBase(photo, previewPath, options)
end

function RequestBuilder.buildDevelop(photo, previewPath, options)
    options = options or {}
    local request, reason = buildBase(photo, previewPath, options)
    if not request then
        return nil, reason
    end
    request.options.include_crop = options.includeCrop ~= false
    request.options.include_denoise = options.includeDenoise ~= false
    request.options.dry_run = options.dryRun == true
    request.options.preserve_current_adjustments =
        options.preserveCurrentAdjustments ~= false
    return request
end

return RequestBuilder
