require "ModuleLoader.lua"

local LearningFeedbackCommand =
    ModuleLoader.load("lib/LearningFeedbackCommand.lua")

LearningFeedbackCommand.start()
