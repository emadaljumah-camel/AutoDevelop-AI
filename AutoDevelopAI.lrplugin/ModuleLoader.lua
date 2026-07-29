local LrPathUtils = import("LrPathUtils")

ModuleLoader = ModuleLoader or {}

local cache = ModuleLoader._cache or {}
local loading = ModuleLoader._loading or {}

ModuleLoader._cache = cache
ModuleLoader._loading = loading

local function validateRelativePath(relativePath)
    if type(relativePath) ~= "string"
        or relativePath == ""
        or relativePath:sub(1, 1) == "/"
        or relativePath:find("\\", 1, true)
        or relativePath:find("..", 1, true)
        or not relativePath:match("^[%w_/%-]+%.lua$") then
        error("Invalid plug-in module path: " .. tostring(relativePath), 3)
    end
end

local function absolutePath(relativePath)
    local path = _PLUGIN.path
    for segment in relativePath:gmatch("[^/]+") do
        path = LrPathUtils.child(path, segment)
    end
    return path
end

function ModuleLoader.load(relativePath)
    validateRelativePath(relativePath)

    if cache[relativePath] ~= nil then
        return cache[relativePath]
    end
    if loading[relativePath] then
        error("Circular plug-in module load: " .. relativePath, 2)
    end

    loading[relativePath] = true
    local ok, loaded = pcall(dofile, absolutePath(relativePath))
    loading[relativePath] = nil
    if not ok then
        error(
            "Could not load plug-in module "
                .. relativePath
                .. ": "
                .. tostring(loaded),
            2
        )
    end

    if loaded == nil then
        loaded = true
    end
    cache[relativePath] = loaded
    return loaded
end

return ModuleLoader
