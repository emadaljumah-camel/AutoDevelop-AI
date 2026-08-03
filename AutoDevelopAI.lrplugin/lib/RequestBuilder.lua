local Config = ModuleLoader.load("lib/Config.lua")
local ExifMapper = ModuleLoader.load("lib/ExifMapper.lua")
local StyleProfiles = ModuleLoader.load("lib/StyleProfiles.lua")
local ModelProfiles = ModuleLoader.load("lib/ModelProfiles.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")

local RequestBuilder = {}

local function buildBase(photo, previewBase64, options)
    options = options or {}
    local styleProfile = options.styleProfileId
    if not StyleProfiles.isValidId(styleProfile) then
        return nil, "The selected style profile is invalid."
    end
    local modelProfile = options.modelProfileId
    if not ModelProfiles.isSelectableId(modelProfile) then
        return nil, "The selected model is invalid or unavailable."
    end
    local uuidFactory = options.uuidFactory or Utils.newUuid
    local requestId = uuidFactory()

    if not Utils.isUuid(requestId) then
        return nil, "Request ID generator returned an invalid UUID."
    end
    local photoIdentity = options.photoIdentity
        or Utils.capturePhotoIdentity(photo)
    local filename = photoIdentity.displayFilename
    if type(previewBase64) ~= "string" or previewBase64 == "" then
        return nil, "Preview content is unavailable."
    end

    local request = {
        schema_version = Config.SCHEMA_VERSION,
        request_id = requestId,
        filename = filename,
        model = modelProfile,
        preview_base64 = previewBase64,
        exif = ExifMapper.mapExif(photo),
        current_settings = ExifMapper.mapDevelopSettings(photo),
        options = {},
    }
    request.options.style_profile = styleProfile
    return request
end

function RequestBuilder.build(photo, previewBase64, options)
    return buildBase(photo, previewBase64, options)
end

function RequestBuilder.buildAnalyze(photo, previewBase64, options)
    return buildBase(photo, previewBase64, options)
end

function RequestBuilder.buildDevelop(photo, previewBase64, options)
    options = options or {}
    local request, reason = buildBase(photo, previewBase64, options)
    if not request then
        return nil, reason
    end
    request.options.include_crop = options.includeCrop ~= false
    request.options.include_denoise = options.includeDenoise ~= false
    request.options.dry_run = options.dryRun == true
    request.options.preserve_current_adjustments =
        options.preserveCurrentAdjustments ~= false
    request.options.hdr_edit_supported =
        ExifMapper.hdrEditSupported(photo)
    request.options.hdr_workflow = "unknown"
    request.options.hdr_preference =
        options.hdrPreference or "balanced"
    request.learning = {
        enabled = options.learningEnabled ~= false,
    }
    return request
end

return RequestBuilder
