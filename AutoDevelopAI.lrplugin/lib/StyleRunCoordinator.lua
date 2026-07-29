local StyleRunCoordinator = {}

local function copySnapshot(snapshot)
    local copied = {}
    for key, value in pairs(snapshot or {}) do
        copied[key] = value
    end
    return copied
end

local function outcome(status, fields)
    local result = fields or {}
    result.status = status
    result.cancelled = status == "cancelled"
    return result
end

function StyleRunCoordinator.begin(options)
    options = options or {}
    local dialogResult = options.dialogResult
    if type(dialogResult) ~= "table"
        or dialogResult.confirmed ~= true then
        return outcome("cancelled")
    end

    local profileId = dialogResult.profileId
    if type(options.validateProfile) ~= "function"
        or not options.validateProfile(profileId) then
        return outcome("invalid_profile")
    end

    if dialogResult.rememberAsDefault == true then
        if type(options.persistDefault) ~= "function"
            or not options.persistDefault(profileId) then
            return outcome("preference_save_failed", {
                profileId = profileId,
            })
        end
    end

    if type(options.snapshotFactory) ~= "function" then
        return outcome("invalid_preferences", {
            profileId = profileId,
        })
    end
    local snapshot, _, invalidKey =
        options.snapshotFactory(profileId)
    if type(snapshot) ~= "table" then
        return outcome("invalid_preferences", {
            profileId = profileId,
            invalidKey = invalidKey,
        })
    end

    snapshot = copySnapshot(snapshot)
    snapshot.styleProfileId = profileId
    return outcome("ready", {
        profileId = profileId,
        _snapshot = snapshot,
    })
end

function StyleRunCoordinator.getSnapshot(run)
    if type(run) ~= "table" or run.status ~= "ready" then
        return nil
    end
    local snapshot = copySnapshot(run._snapshot)
    snapshot.styleProfileId = run.profileId
    return snapshot
end

function StyleRunCoordinator.prepare(run, photos, prepareBatch)
    if type(run) ~= "table" or run.status ~= "ready" then
        return outcome(
            type(run) == "table" and run.status or "invalid_run",
            {
                profileId = type(run) == "table" and run.profileId or nil,
            }
        )
    end
    if type(photos) ~= "table" or #photos == 0 then
        return outcome("empty", {
            profileId = run.profileId,
            photoCount = 0,
        })
    end
    if type(prepareBatch) ~= "function" then
        return outcome("preparation_failed", {
            profileId = run.profileId,
            photoCount = #photos,
        })
    end

    local snapshot = StyleRunCoordinator.getSnapshot(run)
    local prepared = prepareBatch(photos, snapshot)
    if prepared == nil then
        return outcome("preparation_failed", {
            profileId = run.profileId,
            photoCount = #photos,
        })
    end
    return outcome("completed", {
        profileId = run.profileId,
        photoCount = #photos,
        prepared = prepared,
    })
end

return StyleRunCoordinator
