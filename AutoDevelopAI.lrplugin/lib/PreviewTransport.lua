local LrFileUtils = import("LrFileUtils")
local LrStringUtils = import("LrStringUtils")
local LrTasks = import("LrTasks")

local PreviewTransport = {}

local MAX_RAW_PREVIEW_BYTES = 8 * 1024 * 1024
local MAX_ENCODED_PREVIEW_BYTES = 11 * 1024 * 1024

local function estimatedBase64Bytes(rawBytes)
    return 4 * math.ceil(rawBytes / 3)
end

function PreviewTransport.encodeFile(path)
    if type(path) ~= "string" or path == "" then
        return nil, "preview_path_unavailable"
    end

    local readOk, contents = LrTasks.pcall(LrFileUtils.readFile, path)
    if not readOk or type(contents) ~= "string" then
        return nil, "preview_read_failed"
    end

    local rawBytes = #contents
    if rawBytes == 0 then
        return nil, "preview_empty"
    end
    if rawBytes > MAX_RAW_PREVIEW_BYTES then
        return nil, "preview_raw_size_exceeded"
    end

    local estimatedBytes = estimatedBase64Bytes(rawBytes)
    if estimatedBytes > MAX_ENCODED_PREVIEW_BYTES then
        return nil, "preview_encoded_size_exceeded"
    end

    local encodeOk, encoded = LrTasks.pcall(
        LrStringUtils.encodeBase64,
        contents
    )
    contents = nil
    if not encodeOk or type(encoded) ~= "string" or encoded == "" then
        return nil, "preview_encoding_failed"
    end
    if #encoded > MAX_ENCODED_PREVIEW_BYTES then
        return nil, "preview_encoded_size_exceeded"
    end

    return encoded, nil, {
        rawBytes = rawBytes,
        encodedBytes = #encoded,
    }
end

PreviewTransport.MAX_RAW_PREVIEW_BYTES = MAX_RAW_PREVIEW_BYTES
PreviewTransport.MAX_ENCODED_PREVIEW_BYTES =
    MAX_ENCODED_PREVIEW_BYTES
PreviewTransport.estimatedBase64Bytes = estimatedBase64Bytes

return PreviewTransport
