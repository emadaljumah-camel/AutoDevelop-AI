local ApiClient = ModuleLoader.load("lib/ApiClient.lua")
local Config = ModuleLoader.load("lib/Config.lua")
local JobClient = {}

local function validIdentifier(value)
    return type(value) == "string"
        and value ~= ""
        and value:match("^[A-Za-z0-9_-]+$") ~= nil
end

local function connection(settings)
    return {
        baseUrl = settings.backendBaseUrl,
        timeoutSeconds = settings.requestTimeoutSeconds,
    }
end

local function decoded(response)
    if not response or not response.ok then
        return nil, response
    end
    local value, decodeError = ApiClient.decodeBody(response)
    if type(value) ~= "table" then
        return nil, {
            ok = false,
            category = "invalid_response",
            code = "job_response_invalid",
            message = decodeError,
            retryable = false,
        }
    end
    return value
end

function JobClient.create(settings, manifest)
    local photos = {}
    for index, photo in ipairs(manifest.photos or {}) do
        photos[index] = {
            photo_id = photo.photo_id,
            request = photo.request,
        }
    end
    return decoded(ApiClient.postPath(
        Config.apiPaths.jobs,
        {
            schema_version = Config.SCHEMA_VERSION,
            client_job_id = manifest.client_job_id,
            client = "lightroom",
            plugin_version = manifest.plugin_version,
            photos = photos,
        },
        connection(settings)
    ))
end

function JobClient.uploaded(settings, jobId)
    if not validIdentifier(jobId) then
        return nil, { code = "invalid_job_id", retryable = false }
    end
    return decoded(ApiClient.getPath(
        Config.apiPaths.jobs .. "/" .. jobId .. "/uploads",
        connection(settings)
    ))
end

function JobClient.upload(settings, jobId, photoId, previewPath)
    if not validIdentifier(jobId) or not validIdentifier(photoId) then
        return nil, { code = "invalid_job_photo_id", retryable = false }
    end
    local file = io.open(previewPath, "rb")
    if not file then
        return nil, { code = "preview_read_failed", retryable = false }
    end
    local jpeg = file:read("*all")
    file:close()
    if type(jpeg) ~= "string" or jpeg == "" then
        return nil, { code = "preview_read_failed", retryable = false }
    end
    return decoded(ApiClient.postBytesPath(
        Config.apiPaths.jobs
            .. "/" .. jobId
            .. "/photos/" .. photoId
            .. "/preview/binary",
        jpeg,
        "image/jpeg",
        connection(settings)
    ))
end

function JobClient.run(settings, jobId)
    if not validIdentifier(jobId) then
        return nil, { code = "invalid_job_id", retryable = false }
    end
    return decoded(ApiClient.postPath(
        Config.apiPaths.jobs .. "/" .. jobId .. "/run",
        {},
        connection(settings)
    ))
end

function JobClient.status(settings, jobId)
    if not validIdentifier(jobId) then
        return nil, { code = "invalid_job_id", retryable = false }
    end
    return decoded(ApiClient.getPath(
        Config.apiPaths.jobs .. "/" .. jobId .. "/status",
        connection(settings)
    ))
end

function JobClient.result(settings, jobId)
    if not validIdentifier(jobId) then
        return nil, { code = "invalid_job_id", retryable = false }
    end
    return decoded(ApiClient.getPath(
        Config.apiPaths.jobs .. "/" .. jobId .. "/result",
        connection(settings)
    ))
end

function JobClient.submit(settings, manifest, progressScope)
    local created, createError = JobClient.create(settings, manifest)
    if not created then
        return nil, createError
    end
    local jobId = created.job_id
    if not validIdentifier(jobId) then
        return nil, { code = "invalid_job_id_response", retryable = false }
    end
    local uploadState, uploadError = JobClient.uploaded(settings, jobId)
    if not uploadState then
        return nil, uploadError
    end
    local uploaded = {}
    for _, photoId in ipairs(uploadState.uploaded_photo_ids or {}) do
        uploaded[photoId] = true
    end
    for index, photo in ipairs(manifest.photos or {}) do
        if progressScope and progressScope:isCanceled() then
            return nil, { code = "upload_cancelled", retryable = true }
        end
        if not uploaded[photo.photo_id] then
            if progressScope then
                progressScope:setCaption(
                    "Uploading " .. tostring(index)
                        .. " of " .. tostring(#manifest.photos)
                        .. ": " .. tostring(photo.filename)
                )
            end
            local response, uploadOneError = JobClient.upload(
                settings,
                jobId,
                photo.photo_id,
                photo.preview_path
            )
            if not response then
                return nil, uploadOneError
            end
        end
    end
    return JobClient.run(settings, jobId)
end

return JobClient
