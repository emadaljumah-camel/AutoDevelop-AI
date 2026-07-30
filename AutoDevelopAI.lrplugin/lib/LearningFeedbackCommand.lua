local LrApplication = import("LrApplication")
local LrDialogs = import("LrDialogs")
local LrFunctionContext = import("LrFunctionContext")
local LrProgressScope = import("LrProgressScope")
local LrTasks = import("LrTasks")

local ExifMapper = ModuleLoader.load("lib/ExifMapper.lua")
local LearningClient = ModuleLoader.load("lib/LearningClient.lua")
local LearningPhotoIdentity =
    ModuleLoader.load("lib/LearningPhotoIdentity.lua")
local LearningSessionStore =
    ModuleLoader.load("lib/LearningSessionStore.lua")
local Logger = ModuleLoader.load("lib/Logger.lua")
local Preferences = ModuleLoader.load("lib/Preferences.lua")
local Utils = ModuleLoader.load("lib/Utils.lua")
local LearningFeedbackDialog =
    ModuleLoader.load("dialogs/LearningFeedbackDialog.lua")

local LearningFeedbackCommand = {}

local function collect(photos, preferences, progress)
    local candidates = {}
    local summary = {
        selected = #photos,
        pending = 0,
        changed = 0,
        unchanged = 0,
        missing = 0,
        previewFailed = 0,
        significantChanges = nil,
        cropChanges = nil,
        levelingChanges = nil,
    }
    for index, photo in ipairs(photos) do
        if progress and progress:isCanceled() then
            return candidates, summary, true
        end
        if progress then
            progress:setCaption(
                "Comparing " .. tostring(index) .. " of " .. tostring(#photos)
            )
            progress:setPortionComplete(index - 1, #photos)
        end
        local photoKey = LearningPhotoIdentity.forPhoto(photo)
        local pending = LearningSessionStore.get(photoKey)
        if pending then
            summary.pending = summary.pending + 1
            local finalSettings = ExifMapper.mapDevelopSettings(photo)
            if not finalSettings then
                summary.previewFailed = summary.previewFailed + 1
            else
                local request = {
                    schema_version = 1,
                    session_id = pending.sessionId,
                    photo_key = photoKey,
                    final_settings = finalSettings,
                }
                local preview = LearningClient.previewFeedback(request, {
                    baseUrl = preferences.backendBaseUrl,
                    timeoutSeconds = preferences.requestTimeoutSeconds,
                })
                if preview.ok then
                    candidates[#candidates + 1] = {
                        photoKey = photoKey,
                        pending = pending,
                        finalSettings = finalSettings,
                        preview = preview,
                    }
                    if preview.hasSignificantChanges then
                        summary.changed = summary.changed + 1
                    else
                        summary.unchanged = summary.unchanged + 1
                    end
                    if #photos == 1 then
                        summary.significantChanges =
                            Utils.deepCopy(preview.significantChanges)
                        summary.cropChanges =
                            Utils.deepCopy(preview.cropChanges)
                        summary.levelingChanges =
                            Utils.deepCopy(preview.levelingChanges)
                    end
                else
                    summary.previewFailed = summary.previewFailed + 1
                end
            end
        else
            summary.missing = summary.missing + 1
        end
        if progress then
            progress:setPortionComplete(index, #photos)
            if progress:isCanceled() then
                return candidates, summary, true
            end
        end
    end
    return candidates, summary, false
end

local function run(context)
    local catalog = LrApplication.activeCatalog()
    local photos = catalog:getTargetPhotos()
    if not photos or #photos == 0 then
        LrDialogs.message(
            "AutoDevelop AI",
            "Select one or more photos to capture editing feedback.",
            "warning"
        )
        return
    end
    local preferences, reason = Preferences.validatedSnapshot()
    if not preferences or not preferences.learningEnabled then
        LrDialogs.message(
            "AutoDevelop AI",
            "Personalized learning is disabled in plug-in preferences.",
            "warning"
        )
        return
    end
    local previewProgress = LrProgressScope({
        title = "Comparing AutoDevelop editing feedback",
        caption = "Preparing comparison",
    })
    local previewFinished = false
    context:addCleanupHandler(function()
        if not previewFinished then
            previewFinished = true
            LrTasks.pcall(function()
                previewProgress:done()
            end)
        end
    end)
    previewProgress:setCancelable(true)
    local candidates, summary, previewCancelled =
        collect(photos, preferences, previewProgress)
    previewProgress:done()
    previewFinished = true
    if previewCancelled then
        return
    end
    if #candidates == 0 then
        LrDialogs.message(
            "AutoDevelop AI",
            summary.pending > 0
                and "The backend could not compare the selected learning session."
                or "No selected photo has a pending AutoDevelop learning baseline.",
            summary.pending > 0 and "warning" or "info"
        )
        return
    end
    local choice = LearningFeedbackDialog.confirm(summary)
    if choice == "cancel" then
        return
    end
    local skipUnchanged = choice == "other"

    local progress = LrProgressScope({
        title = "Saving AutoDevelop editing feedback",
        caption = "Preparing feedback",
    })
    local finished = false
    context:addCleanupHandler(function()
        if not finished then
            finished = true
            LrTasks.pcall(function()
                progress:done()
            end)
        end
    end)
    progress:setCancelable(true)
    local saved, failed, skipped = 0, 0, 0
    for index, candidate in ipairs(candidates) do
        if progress:isCanceled() then
            break
        end
        progress:setCaption(
            "Saving " .. tostring(index) .. " of " .. tostring(#candidates)
        )
        progress:setPortionComplete(index - 1, #candidates)
        if skipUnchanged and candidate.preview.acceptedWithoutChange then
            skipped = skipped + 1
        else
            local response = LearningClient.captureFeedback({
                schema_version = 1,
                session_id = candidate.pending.sessionId,
                photo_key = candidate.photoKey,
                final_settings = candidate.finalSettings,
            }, {
                baseUrl = preferences.backendBaseUrl,
                timeoutSeconds = preferences.requestTimeoutSeconds,
            })
            if response.ok then
                saved = saved + 1
                LearningSessionStore.remove(candidate.photoKey)
            else
                failed = failed + 1
            end
        end
        progress:setPortionComplete(index, #candidates)
    end
    progress:done()
    finished = true
    Logger.info(
        "learning_feedback_batch_complete saved="
            .. tostring(saved)
            .. " failed="
            .. tostring(failed)
            .. " skipped="
            .. tostring(skipped)
    )
    LrDialogs.message(
        "AutoDevelop AI - Capture Editing Feedback",
        "Saved: " .. tostring(saved)
            .. "\nFailed: " .. tostring(failed)
            .. "\nSkipped unchanged: " .. tostring(skipped),
        failed > 0 and "warning" or "info"
    )
end

function LearningFeedbackCommand.start()
    LrTasks.startAsyncTask(function()
        local ok = LrTasks.pcall(function()
            return LrFunctionContext.callWithContext(
                "AutoDevelop AI Capture Editing Feedback",
                run
            )
        end)
        if not ok then
            Logger.error(
                "operation=capture_learning_feedback "
                    .. "category=internal_error code=unexpected_exception"
            )
            LrDialogs.message(
                "AutoDevelop AI",
                "Editing feedback could not be captured safely.",
                "critical"
            )
        end
    end)
end

LearningFeedbackCommand.collect = collect

return LearningFeedbackCommand
