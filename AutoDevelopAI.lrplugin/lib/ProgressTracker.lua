local LrDate = import("LrDate")

local Utils = ModuleLoader.load("lib/Utils.lua")

local ProgressTracker = {}
ProgressTracker.__index = ProgressTracker

local function defaultClock()
    return LrDate.currentTime()
end

function ProgressTracker.formatDuration(seconds)
    if not Utils.isFiniteNumber(seconds) or seconds < 0 then
        seconds = 0
    end
    seconds = math.floor(seconds + 0.5)
    local hours = math.floor(seconds / 3600)
    local minutes = math.floor((seconds % 3600) / 60)
    local remainingSeconds = seconds % 60
    if hours > 0 then
        return string.format(
            "%d:%02d:%02d",
            hours,
            minutes,
            remainingSeconds
        )
    end
    return string.format("%02d:%02d", minutes, remainingSeconds)
end

function ProgressTracker.new(total, phase, clock)
    local self = setmetatable({}, ProgressTracker)
    self.total = math.max(0, tonumber(total) or 0)
    self.phase = phase or "Working"
    self.filename = ""
    self.currentIndex = nil
    self.completed = 0
    self.clock = clock or defaultClock
    self.startedAt = self.clock()
    self.phaseStartedAt = self.startedAt
    return self
end

function ProgressTracker:setPhase(phase)
    if phase and phase ~= self.phase then
        self.phase = phase
        self.phaseStartedAt = self.clock()
    end
end

function ProgressTracker:setCurrent(filename, index)
    self.filename = Utils.safeMessage(filename, "Photo")
    if Utils.isFiniteNumber(index)
        and index >= 1
        and index <= self.total then
        self.currentIndex = math.floor(index)
    end
end

function ProgressTracker:markCompleted(count)
    self.completed = math.min(
        self.total,
        math.max(0, tonumber(count) or self.completed)
    )
end

function ProgressTracker:setBatchCounts(counts)
    counts = type(counts) == "table" and counts or {}
    self.batchCounts = {
        applied = math.max(0, tonumber(counts.applied) or 0),
        skipped = math.max(0, tonumber(counts.skipped) or 0),
        failed = math.max(0, tonumber(counts.failed) or 0),
        processed = math.max(0, tonumber(counts.processed) or 0),
    }
end

function ProgressTracker:elapsedSeconds()
    local elapsed = self.clock() - self.startedAt
    if not Utils.isFiniteNumber(elapsed) or elapsed < 0 then
        return 0
    end
    return elapsed
end

function ProgressTracker:estimatedRemainingSeconds()
    if self.completed < 1 or self.completed >= self.total then
        return nil
    end
    return (self:elapsedSeconds() / self.completed)
        * (self.total - self.completed)
end

function ProgressTracker:caption()
    if self.batchCounts then
        local current = self.currentIndex or math.min(
            self.total,
            self.batchCounts.processed + 1
        )
        local remaining = math.max(
            0,
            self.total - self.batchCounts.processed
        )
        return table.concat({
            "Processing photo "
                .. tostring(current)
                .. " of "
                .. tostring(self.total),
            "Current: " .. Utils.safeMessage(self.filename, "Preparing"),
            "Applied: " .. tostring(self.batchCounts.applied),
            "Skipped: " .. tostring(self.batchCounts.skipped),
            "Failed: " .. tostring(self.batchCounts.failed),
            "Remaining: " .. tostring(remaining),
            "Elapsed: "
                .. ProgressTracker.formatDuration(self:elapsedSeconds()),
        }, "\n")
    end
    local remaining = self:estimatedRemainingSeconds()
    local remainingText = remaining
        and ProgressTracker.formatDuration(remaining)
        or "calculating"
    local phaseLine = self.phase
    if self.currentIndex then
        phaseLine = phaseLine
            .. " photo "
            .. tostring(self.currentIndex)
            .. " of "
            .. tostring(self.total)
    end
    return table.concat({
        phaseLine,
        Utils.safeMessage(self.filename, "Preparing"),
        "Photos completed: "
            .. tostring(self.completed)
            .. " / "
            .. tostring(self.total),
        "Elapsed: " .. ProgressTracker.formatDuration(self:elapsedSeconds()),
        "Estimated remaining: " .. remainingText,
    }, "\n")
end

return ProgressTracker
