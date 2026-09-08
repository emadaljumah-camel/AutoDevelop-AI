local LrExportSession = import("LrExportSession")
local LrFileUtils = import("LrFileUtils")
local LrPathUtils = import("LrPathUtils")
local LrTasks = import("LrTasks")

local Utils = ModuleLoader.load("lib/Utils.lua")
local PreviewTransport =
    ModuleLoader.load("lib/PreviewTransport.lua")

local PreviewExporter = {}

local function cleanupDirectory(directory)
    if not directory then
        return true
    end

    local existsOk, existsOrError = LrTasks.pcall(
        LrFileUtils.exists,
        directory
    )
    if not existsOk then
        return false, "temporary_path_check_failed"
    end
    if not existsOrError then
        return true
    end

    local deleteOk, deleted, reason = LrTasks.pcall(
        LrFileUtils.delete,
        directory
    )
    if not deleteOk then
        return false, "temporary_path_delete_failed"
    end
    if deleted == true then
        return true
    end
    return false, "temporary_path_delete_failed"
end

local function createDirectory(directory)
    local ok, created, reason = LrTasks.pcall(
        LrFileUtils.createAllDirectories,
        directory
    )
    if not ok then
        return false, "temporary_directory_create_failed"
    end
    if created ~= true then
        return false, "temporary_directory_create_failed"
    end

    local existsOk, existsOrError = LrTasks.pcall(
        LrFileUtils.exists,
        directory
    )
    if not existsOk then
        return false, "temporary_path_check_failed"
    end
    return existsOrError == "directory",
        "Could not verify the temporary directory."
end

local function exportSettings(destination)
    return {
        LR_export_destinationType = "specificFolder",
        LR_export_destinationPathPrefix = destination,
        LR_export_useSubfolder = false,
        LR_collisionHandling = "overwrite",
        LR_format = "JPEG",
        LR_jpeg_quality = 0.8,
        LR_colorSpace = "sRGB",
        LR_size_doConstrain = true,
        LR_size_resizeType = "longEdge",
        LR_size_maxWidth = 1600,
        LR_size_maxHeight = 1600,
        LR_size_units = "pixels",
        LR_outputSharpeningOn = false,
        LR_watermarking_enabled = false,
        LR_reimportExportedPhoto = false,
    }
end

function PreviewExporter.photoKey(photo, fallback)
    local localIdentifier = Utils.safePhotoProperty(photo, "localIdentifier")
    if localIdentifier ~= nil then
        return "local-" .. tostring(localIdentifier)
    end
    local uuid = Utils.safeRawMetadata(photo, "uuid")
    if uuid and uuid ~= "" then
        return "uuid-" .. tostring(uuid)
    end
    return "position-" .. tostring(fallback or "unknown")
end

function PreviewExporter.createBatchDirectory()
    local temporaryRoot = LrPathUtils.getStandardFilePath("temp")
    local batchDirectory = LrPathUtils.child(
        temporaryRoot,
        "AutoDevelopAI-" .. Utils.newUuid()
    )
    local created, reason = createDirectory(batchDirectory)
    if not created then
        cleanupDirectory(batchDirectory)
        return nil, reason
            or "Could not create the temporary preview directory."
    end
    return batchDirectory
end

local function renderPhoto(
    photo,
    photoDirectory,
    progressScope,
    options
)
    local session = LrExportSession({
        photosToExport = { photo },
        exportSettings = exportSettings(photoDirectory),
    })

    for _, rendition in session:renditions({
        progressScope = progressScope,
        stopIfCanceled = true,
    }) do
        local success, renderedPath = rendition:waitForRender()
        if not success then
            return nil, "Lightroom could not render the preview."
        end

        local uniquePath = LrPathUtils.child(
            photoDirectory,
            Utils.newUuid() .. ".jpg"
        )
        local moved, moveError = LrFileUtils.move(renderedPath, uniquePath)
        if not moved then
            return nil, "Lightroom could not finalize the temporary preview."
        end
        if LrFileUtils.exists(uniquePath) ~= "file" then
            return nil, "The temporary preview was not created."
        end
        if not LrPathUtils.isAbsolute(uniquePath) then
            return nil, "The temporary preview path was not absolute."
        end
        if options.encode == false then
            return {
                path = uniquePath,
                directory = photoDirectory,
            }
        end
        local encoded, encodeError, transport =
            PreviewTransport.encodeFile(uniquePath)
        if not encoded then
            return nil, encodeError or "preview_encoding_failed"
        end
        return {
            path = uniquePath,
            directory = photoDirectory,
            base64 = encoded,
            rawBytes = transport.rawBytes,
            encodedBytes = transport.encodedBytes,
        }
    end

    return nil, "Preview rendering was cancelled."
end

function PreviewExporter.exportPhoto(
    photo,
    batchDirectory,
    progressScope,
    options
)
    options = options or {}
    local photoDirectory = LrPathUtils.child(
        batchDirectory,
        Utils.newUuid()
    )
    local created, createError = createDirectory(photoDirectory)
    if not created then
        cleanupDirectory(photoDirectory)
        return nil, createError
            or "Could not create a temporary photo directory."
    end

    local ok, preview, renderError = LrTasks.pcall(
        renderPhoto,
        photo,
        photoDirectory,
        progressScope,
        options
    )
    if not ok or not preview then
        local cleaned, cleanupError = cleanupDirectory(photoDirectory)
        if not cleaned then
            return nil,
                "Preview rendering failed and temporary cleanup failed."
        end
        if not ok then
            return nil, "Lightroom encountered an unexpected preview error."
        end
        return nil, renderError
    end
    return preview
end

function PreviewExporter.exportBatch(photos, destination, progressScope)
    local settings = exportSettings(destination)
    settings.LR_collisionHandling = "rename"
    settings.LR_renamingTokensOn = true
    settings.LR_initialSequenceNumber = 1
    settings.LR_tokens = "autodevelop-ai-{{naming_sequenceNumber_5Digits}}"
    local session = LrExportSession({
        photosToExport = photos,
        exportSettings = settings,
    })
    local previews = {}
    local rendered = 0
    for _, rendition in session:renditions({
        progressScope = progressScope,
        stopIfCanceled = true,
    }) do
        if progressScope and progressScope:isCanceled() then
            return nil, "cancelled"
        end
        local success, renderedPath = rendition:waitForRender()
        if not success then
            return nil, "Lightroom could not render the preview."
        end
        rendered = rendered + 1
        local key = PreviewExporter.photoKey(rendition.photo, rendered)
        if previews[key] then
            return nil, "duplicate_preview_photo"
        end
        if LrFileUtils.exists(renderedPath) ~= "file"
            or not LrPathUtils.isAbsolute(renderedPath) then
            return nil, "preview_path_invalid"
        end
        previews[key] = { path = renderedPath, directory = destination }
    end
    if rendered ~= #photos then
        return nil, "preview_count_mismatch"
    end
    return previews
end

function PreviewExporter.cleanupPreview(handle)
    if not handle or not handle.directory then
        return true
    end
    return cleanupDirectory(handle.directory)
end

function PreviewExporter.cleanupBatch(batchDirectory)
    return cleanupDirectory(batchDirectory)
end

return PreviewExporter
