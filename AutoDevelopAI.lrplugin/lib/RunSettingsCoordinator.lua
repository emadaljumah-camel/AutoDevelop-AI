local RunSettingsCoordinator = {}

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

function RunSettingsCoordinator.begin(options)
    options = options or {}
    local dialogResult = options.dialogResult
    if type(dialogResult) ~= "table"
        or dialogResult.confirmed ~= true then
        return outcome("cancelled")
    end

    local profileId = dialogResult.profileId
    local modelId = dialogResult.modelId
    if type(options.validateProfile) ~= "function"
        or not options.validateProfile(profileId) then
        return outcome("invalid_profile")
    end
    if type(options.validateModel) ~= "function"
        or not options.validateModel(modelId) then
        return outcome("invalid_model", { modelId = modelId })
    end

    if dialogResult.rememberProfileAsDefault == true then
        if type(options.persistProfileDefault) ~= "function"
            or not options.persistProfileDefault(profileId) then
            return outcome("preference_save_failed", {
                profileId = profileId,
            })
        end
    end
    if dialogResult.rememberModelAsDefault == true then
        if type(options.persistModelDefault) ~= "function"
            or not options.persistModelDefault(modelId) then
            return outcome("preference_save_failed", {
                profileId = profileId,
                modelId = modelId,
            })
        end
    end

    if type(options.snapshotFactory) ~= "function" then
        return outcome("invalid_preferences", {
            profileId = profileId,
        })
    end
    local snapshot, _, invalidKey =
        options.snapshotFactory(profileId, modelId)
    if type(snapshot) ~= "table" then
        return outcome("invalid_preferences", {
            profileId = profileId,
            invalidKey = invalidKey,
        })
    end

    snapshot = copySnapshot(snapshot)
    snapshot.styleProfileId = profileId
    snapshot.modelProfileId = modelId
    return outcome("ready", {
        profileId = profileId,
        modelId = modelId,
        _snapshot = snapshot,
    })
end

function RunSettingsCoordinator.getSnapshot(run)
    if type(run) ~= "table" or run.status ~= "ready" then
        return nil
    end
    local snapshot = copySnapshot(run._snapshot)
    snapshot.styleProfileId = run.profileId
    snapshot.modelProfileId = run.modelId
    return snapshot
end

function RunSettingsCoordinator.prepare(run, photos, prepareBatch)
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

    local snapshot = RunSettingsCoordinator.getSnapshot(run)
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

return RunSettingsCoordinator
