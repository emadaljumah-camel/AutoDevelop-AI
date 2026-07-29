local LrExportSession = import("LrExportSession")
local LrFileUtils = import("LrFileUtils")
local LrPathUtils = import("LrPathUtils")
local LrTasks = import("LrTasks")

local Utils = require("lib.Utils")

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
        return false, existsOrError
    end
    if not existsOrError then
        return true
    end

    local deleteOk, deleted, reason = LrTasks.pcall(
        LrFileUtils.delete,
        directory
    )
    if not deleteOk then
        return false, deleted
    end
    return deleted == true, reason
end

local function createDirectory(directory)
    local ok, created, reason = LrTasks.pcall(
        LrFileUtils.createAllDirectories,
        directory
    )
    if not ok then
        return false, created
    end
    if created ~= true then
        return false, reason
    end

    local existsOk, existsOrError = LrTasks.pcall(
        LrFileUtils.exists,
        directory
    )
    if not existsOk then
        return false, existsOrError
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
    progressScope
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
            return nil, "Could not finalize the temporary preview: "
                .. tostring(moveError or "move failed")
        end
        if LrFileUtils.exists(uniquePath) ~= "file" then
            return nil, "The temporary preview was not created."
        end
        if not LrPathUtils.isAbsolute(uniquePath) then
            return nil, "The temporary preview path was not absolute."
        end
        return {
            path = uniquePath,
            directory = photoDirectory,
        }
    end

    return nil, "Preview rendering was cancelled."
end

function PreviewExporter.exportPhoto(photo, batchDirectory, progressScope)
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
        progressScope
    )
    if not ok or not preview then
        local cleaned, cleanupError = cleanupDirectory(photoDirectory)
        if not cleaned then
            return nil, "Preview rendering failed and cleanup failed: "
                .. tostring(cleanupError or "unknown cleanup error")
        end
        if not ok then
            return nil, "Lightroom encountered an unexpected preview error."
        end
        return nil, renderError
    end
    return preview
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
