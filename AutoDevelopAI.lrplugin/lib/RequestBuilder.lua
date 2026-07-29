local ExifMapper = ModuleLoader.load("lib/ExifMapper.lua")
local Preferences = ModuleLoader.load("lib/Preferences.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")

local RequestBuilder = {}

local function buildBase(photo, previewPath, options)
    options = options or {}
    local styleProfile = options.styleProfileId
    if styleProfile == nil then
        styleProfile = Preferences.getStyleProfileId()
    else
        styleProfile = Preferences.validate("styleProfileId", styleProfile)
    end
    if not styleProfile then
        return nil, "The selected style profile is invalid."
    end
    local uuidFactory = options.uuidFactory or Utils.newUuid
    local requestId = uuidFactory()

    if not Utils.isUuid(requestId) then
        return nil, "Request ID generator returned an invalid UUID."
    end
    local filename = Utils.photoFilename(photo)

    local request = {
        schema_version = Config.SCHEMA_VERSION,
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
