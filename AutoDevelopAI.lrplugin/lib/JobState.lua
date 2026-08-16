local LrFileUtils = import("LrFileUtils")
local LrPathUtils = import("LrPathUtils")

local Json = ModuleLoader.load("lib/Json.lua")

local JobState = {}

local function ensureDirectory(path)
    if LrFileUtils.exists(path) ~= "directory" then
        return LrFileUtils.createAllDirectories(path) == true
    end
    return true
end

function JobState.defaultRoot()
    return LrPathUtils.child(
        LrPathUtils.getStandardFilePath("documents"),
        "AutoDevelop AI Jobs"
    )
end

function JobState.activePath(jobRoot)
    if not ensureDirectory(jobRoot) then
        return nil, "job_root_unavailable"
    end
    return LrPathUtils.child(jobRoot, "active_job.json")
end

function JobState.createFolder(jobRoot, clientJobId)
    if type(clientJobId) ~= "string"
        or not clientJobId:match("^[A-Za-z0-9_-]+$") then
        return nil, "invalid_client_job_id"
    end
    if not ensureDirectory(jobRoot) then
        return nil, "job_root_unavailable"
    end
    local folder = LrPathUtils.child(jobRoot, "job_" .. clientJobId)
    if not ensureDirectory(folder) then
        return nil, "job_directory_unavailable"
    end
    local previews = LrPathUtils.child(folder, "previews")
    if not ensureDirectory(previews) then
        return nil, "job_preview_directory_unavailable"
    end
    return folder
end

function JobState.writeJson(path, value)
    local encoded, encodeError = Json.encode(value)
    if not encoded then
        return false, encodeError or "job_state_encoding_failed"
    end
    local temporary = path .. ".tmp"
    local backup = path .. ".bak"
    local file, openError = io.open(temporary, "w")
    if not file then
        return false, openError or "job_state_open_failed"
    end
    file:write(encoded)
    file:write("\n")
    file:flush()
    file:close()

    if LrFileUtils.exists(backup) then
        LrFileUtils.delete(backup)
    end
    if LrFileUtils.exists(path)
        and not LrFileUtils.move(path, backup) then
        LrFileUtils.delete(temporary)
        return false, "job_state_backup_failed"
    end
    if not LrFileUtils.move(temporary, path) then
        if LrFileUtils.exists(backup) then
            LrFileUtils.move(backup, path)
        end
        return false, "job_state_replace_failed"
    end
    if LrFileUtils.exists(backup) then
        LrFileUtils.delete(backup)
    end
    return true
end

function JobState.readJson(path)
    if not LrFileUtils.exists(path)
        and LrFileUtils.exists(path .. ".bak") then
        LrFileUtils.move(path .. ".bak", path)
    end
    local contents = LrFileUtils.readFile(path)
    if type(contents) ~= "string" then
        return nil, "job_state_read_failed"
    end
    return Json.decode(contents)
end

function JobState.loadActive(jobRoot)
    local path, pathError = JobState.activePath(jobRoot)
    if not path then
        return nil, pathError
    end
    if not LrFileUtils.exists(path) then
        return nil
    end
    return JobState.readJson(path)
end

function JobState.saveActive(jobRoot, state)
    local path, pathError = JobState.activePath(jobRoot)
    if not path then
        return false, pathError
    end
    return JobState.writeJson(path, state)
end

return JobState
