import re
from pathlib import Path, PurePosixPath

PLUGIN = Path("AutoDevelopAI.lrplugin")
MENU_ITEM_PATTERN = re.compile(
    r"""
    \{
        \s*title\s*=\s*"(?P<title>[^"]+)"\s*,
        \s*file\s*=\s*"(?P<file>[^"]+)"\s*,
    \s*\}
    """,
    re.VERBOSE,
)
DOTTED_MODULE_PATTERN = re.compile(
    r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+$"
)
REQUIRE_PATTERN = re.compile(
    r"""\brequire\s*(?:\(\s*)?["'](?P<module>[^"']+)["']"""
)
LOADER_PATTERN = re.compile(
    r"""\bModuleLoader\.load\(\s*["'](?P<path>[^"']+)["']"""
)


def _read(relative_path: str) -> str:
    return (PLUGIN / relative_path).read_text(encoding="utf-8")


def _library_menu_items() -> dict[str, str]:
    info = _read("Info.lua")
    items = {
        match.group("title"): match.group("file")
        for match in MENU_ITEM_PATTERN.finditer(info)
    }
    assert items, "Info.lua did not contain any parseable menu items"
    return items


def test_library_menu_files_are_real_relative_lua_scripts() -> None:
    items = _library_menu_items()
    actual_lua_files = {
        path.relative_to(PLUGIN).as_posix()
        for path in PLUGIN.rglob("*.lua")
    }

    assert items["Analyze Selected Photos"] == "AnalyzeSelectedPhotos.lua"
    assert (
        items["Auto Develop Selected Photos"]
        == "AutoDevelopSelectedPhotos.lua"
    )

    for title, file_value in items.items():
        assert not (
            DOTTED_MODULE_PATTERN.fullmatch(file_value)
            and not file_value.endswith(".lua")
        ), f"{title!r} uses dotted Lua module notation: {file_value!r}"
        assert file_value.endswith(
            ".lua"
        ), f"{title!r} must reference a Lua script path"
        assert "\\" not in file_value
        path = PurePosixPath(file_value)
        assert not path.is_absolute()
        assert all(part not in {"", ".", ".."} for part in path.parts)
        assert (
            file_value in actual_lua_files
        ), f"{title!r} references a missing or case-mismatched script"


def test_primary_menu_scripts_delegate_directly_to_commands() -> None:
    analyze_entry = _read("AnalyzeSelectedPhotos.lua")
    auto_develop_entry = _read("AutoDevelopSelectedPhotos.lua")

    assert analyze_entry.strip() == (
        'require "ModuleLoader.lua"\n\n'
        'local AnalyzeCommand = ModuleLoader.load("lib/AnalyzeCommand.lua")\n'
        "AnalyzeCommand.start()"
    )
    assert auto_develop_entry.strip() == (
        'require "ModuleLoader.lua"\n\n'
        "local AutoDevelopCommand = "
        'ModuleLoader.load("lib/AutoDevelopCommand.lua")\n'
        "AutoDevelopCommand.start()"
    )


def test_plugin_imports_resolve_with_lightroom_compatible_loader() -> None:
    actual_lua_files = {
        path.relative_to(PLUGIN).as_posix()
        for path in PLUGIN.rglob("*.lua")
    }

    for source_path in PLUGIN.rglob("*.lua"):
        source_relative = source_path.relative_to(PLUGIN).as_posix()
        source = source_path.read_text(encoding="utf-8")
        modules = [
            match.group("module")
            for match in REQUIRE_PATTERN.finditer(source)
        ]
        for module in modules:
            assert "/" not in module and "\\" not in module, (
                f"{source_relative!r} requires a non-root toolkit script: "
                f"{module!r}"
            )
            assert module.endswith(".lua"), (
                f"{source_relative!r} requires a script without .lua: "
                f"{module!r}"
            )
            assert module in actual_lua_files, (
                f"{source_relative!r} imports missing or case-mismatched "
                f"module {module!r}"
            )

        loaded_paths = [
            match.group("path")
            for match in LOADER_PATTERN.finditer(source)
        ]
        for loaded_path in loaded_paths:
            assert loaded_path.endswith(".lua")
            assert "\\" not in loaded_path
            path = PurePosixPath(loaded_path)
            assert not path.is_absolute()
            assert all(part not in {"", ".", ".."} for part in path.parts)
            assert loaded_path in actual_lua_files, (
                f"{source_relative!r} loads missing or case-mismatched "
                f"module {loaded_path!r}"
            )

    for title, wrapper_path in _library_menu_items().items():
        wrapper = _read(wrapper_path)
        required = [
            match.group("module")
            for match in REQUIRE_PATTERN.finditer(wrapper)
        ]
        assert required == ["ModuleLoader.lua"], (
            f"{title!r} wrapper must require only ModuleLoader.lua"
        )
        assert LOADER_PATTERN.search(
            wrapper
        ), f"{title!r} wrapper does not load a command module"


def test_module_loader_is_cached_and_plugin_relative() -> None:
    loader = _read("ModuleLoader.lua")

    assert "_PLUGIN.path" in loader
    assert "LrPathUtils.child" in loader
    assert "cache[relativePath]" in loader
    assert "pcall(dofile, absolutePath(relativePath))" in loader
    assert 'relativePath:find("..", 1, true)' in loader


def test_backend_configuration_uses_autodevelop_port_and_route() -> None:
    config = _read("lib/Config.lua")
    client = _read("lib/ApiClient.lua")

    assert "http://127.0.0.1:8005" in config
    assert 'Config.DEFAULT_STYLE_PROFILE = "natural_travel"' in config
    assert "styleProfileId = Config.DEFAULT_STYLE_PROFILE" in config
    assert 'analyze = "/autodevelop/v1/analyze"' in config
    assert 'develop = "/autodevelop/v1/develop"' in config
    assert "Config.apiPaths.analyze" in client
    assert "Config.apiPaths.develop" in client
    assert "LrHttp.post(" in client
    assert '"POST"' in client
    assert "8004" not in config
    assert "8004" not in client


def test_requests_use_backend_contract_field_names() -> None:
    builder = _read("lib/RequestBuilder.lua")

    assert "schema_version" in builder
    assert "request_id" in builder
    assert "preview_path" in builder
    assert "current_settings" in builder
    assert "style_profile" in builder
    assert "current_develop_settings" not in builder


def test_json_codec_is_bundled_and_used_by_api_client() -> None:
    json_module = _read("lib/Json.lua")
    client = _read("lib/ApiClient.lua")

    assert 'import("LrJson")' not in json_module
    assert "function Json.encode(value)" in json_module
    assert "function Json.decode(value)" in json_module
    assert "pcall(encodeValue, value, {})" in json_module
    assert "pcall(parseValue, state)" in json_module
    assert "Json.encode(request)" in client
    assert "preview_path" not in client


def test_preview_cleanup_covers_protected_and_batch_paths() -> None:
    command = _read("lib/AnalyzeCommand.lua")
    exporter = _read("lib/PreviewExporter.lua")

    assert "context:addCleanupHandler" in command
    assert "cleanupPreview(preview)" in command
    assert "cleanupBatch(batchDirectory)" in command
    assert "progressScope:done()" in command
    assert "cleanupDirectory(handle.directory)" in exporter
    assert "cleanupDirectory(batchDirectory)" in exporter
    assert "LrPathUtils.isAbsolute(uniquePath)" in exporter

    constructed = command.index("local progressScope = LrProgressScope")
    registered = command.index(
        "context:addCleanupHandler(releaseProgress)",
        constructed,
    )
    configured = command.index(
        "progressScope:setCancelable(true)",
        constructed,
    )
    cleanup_call = command.index(
        "finishProgress(progressScope)",
        constructed,
    )

    assert constructed < cleanup_call < registered < configured
    assert "if progressFinished then" in command[constructed:registered]
    assert "progressScope:" not in command[constructed:registered]


def test_response_validation_requires_request_match_and_analysis() -> None:
    validation = _read("lib/Validation.lua")

    assert "response.request_id ~= request.request_id" in validation
    assert 'response.schema_version ~= "1.0"' in validation
    assert 'type(response.analysis) ~= "table"' in validation
    assert 'type(response.edit_plan) ~= "table"' in validation


def test_develop_response_validation_requires_safe_contract() -> None:
    validation = _read("lib/Validation.lua")

    assert "Validation.validateDevelopResponse" in validation
    assert "response.request_id ~= request.request_id" in validation
    assert 'response.schema_version ~= "1.0"' in validation
    assert 'type(response.develop_settings) ~= "table"' in validation
    assert "validateCrop(response.crop)" in validation
    assert "validateDenoise(response.denoise)" in validation
    assert "validateWarnings(response.warnings)" in validation
    assert "hasOnlyFields(response, developResponseFields)" in validation


def test_command_is_async_sequential_and_cancellable() -> None:
    command = _read("lib/AnalyzeCommand.lua")

    assert "LrTasks.startAsyncTask(function()" in command
    assert "LrFunctionContext.callWithContext" in command
    assert "LrTasks.pcall" in command
    assert "for index, photo in ipairs(photos) do" in command
    assert "progressScope:isCanceled()" in command
    assert "LrTasks.sleep(0.5)" in command
    assert "startAsyncTask" not in _read("lib/ApiClient.lua")


def test_yielding_work_is_not_wrapped_in_standard_xpcall() -> None:
    command = _read("lib/AnalyzeCommand.lua")
    exporter = _read("lib/PreviewExporter.lua")

    assert "xpcall" not in command
    assert "xpcall" not in exporter
    assert "LrTasks.pcall" in exporter
    assert "rendition:waitForRender()" in exporter


def test_documented_filename_and_photo_identity_access() -> None:
    utils = _read("lib/Utils.lua")

    assert 'safeFormattedMetadata(photo, "fileName")' in utils
    assert 'safePhotoProperty(photo, "localIdentifier")' in utils
    assert 'safeRawMetadata(photo, "fileName")' not in utils
    assert 'safeRawMetadata(photo, "localIdentifier")' not in utils
    assert '"photo_unidentified"' not in utils


def test_capture_time_and_gps_mapping_are_defensive() -> None:
    mapper = _read("lib/ExifMapper.lua")

    assert '"dateTimeOriginalISO8601"' in mapper
    assert '"captureTime"' not in mapper
    assert "value >= -90" in mapper
    assert "value <= 90" in mapper
    assert "value >= -180" in mapper
    assert "value <= 180" in mapper


def test_default_style_profile_has_one_plugin_source_of_truth() -> None:
    config = _read("lib/Config.lua")
    builder = _read("lib/RequestBuilder.lua")

    assert 'Config.DEFAULT_STYLE_PROFILE = "natural_travel"' in config
    assert "Config.DEFAULT_STYLE_PROFILE" in builder
    assert '"natural_travel"' not in builder


def test_only_apply_service_uses_catalog_develop_writes() -> None:
    apply_service = _read("lib/ApplyService.lua")
    other_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in PLUGIN.rglob("*.lua")
        if path.name != "ApplyService.lua"
    )

    assert "catalog:withWriteAccessDo(" in apply_service
    assert "operation.photo:applyDevelopSettings(" in apply_service
    assert "withWriteAccessDo" not in other_source
    assert "applyDevelopSettings" not in other_source
    assert "ApiClient" not in apply_service
    assert "PreviewExporter" not in apply_service
    assert "LrDialogs" not in apply_service


def test_auto_develop_confirmation_precedes_catalog_application() -> None:
    command = _read("lib/AutoDevelopCommand.lua")

    backend = command.index("ApiClient.develop(request)")
    confirmed = command.index(
        "AutoDevelopConfirmationDialog.confirm(summary)"
    )
    applied = command.index("ApplyService.applyBatch(catalog, operations")

    assert backend < confirmed < applied
    assert "withWriteAccessDo" not in command


def test_auto_develop_progress_cleanup_precedes_scope_methods() -> None:
    command = _read("lib/AutoDevelopCommand.lua")

    preparation_constructed = command.index(
        "local preparationProgress = LrProgressScope"
    )
    preparation_registered = command.index(
        "context:addCleanupHandler(releasePreparationProgress)",
        preparation_constructed,
    )
    preparation_configured = command.index(
        "preparationProgress:setCancelable(true)",
        preparation_constructed,
    )
    assert (
        preparation_constructed
        < preparation_registered
        < preparation_configured
    )
    assert (
        "preparationProgress:"
        not in command[preparation_constructed:preparation_registered]
    )

    apply_constructed = command.index(
        "local applyProgress = LrProgressScope"
    )
    apply_registered = command.index(
        "context:addCleanupHandler(releaseApplyProgress)",
        apply_constructed,
    )
    apply_configured = command.index(
        "applyProgress:setCancelable(true)",
        apply_constructed,
    )
    assert apply_constructed < apply_registered < apply_configured
    assert "applyProgress:" not in command[apply_constructed:apply_registered]


def test_auto_develop_uses_two_phase_cleanup_and_no_standard_xpcall() -> None:
    command = _read("lib/AutoDevelopCommand.lua")
    apply_service = _read("lib/ApplyService.lua")

    assert "context:addCleanupHandler" in command
    assert "cleanupPreview(preview)" in command
    assert "cleanupBatch(batchDirectory)" in command
    assert "PendingOperation.clear(operations)" in command
    assert "LrTasks.startAsyncTask(function()" in command
    assert "LrTasks.pcall" in command
    assert "xpcall" not in command
    assert "xpcall" not in apply_service
    assert "LrTasks.pcall" in apply_service


def test_develop_mapping_is_allow_listed_and_preserves_process_version() -> None:
    mapper = _read("lib/DevelopSettingsMapper.lua")
    crop_mapper = _read("lib/CropMapper.lua")

    for key in (
        "Exposure2012",
        "Contrast2012",
        "Highlights2012",
        "Shadows2012",
        "Whites2012",
        "Blacks2012",
        "Texture",
        "Clarity2012",
        "Dehaze",
        "Vibrance",
        "Saturation",
        "Temperature",
        "Tint",
    ):
        assert f'"{key}"' in mapper
    assert "ProcessVersion" not in mapper
    assert "CameraProfile" not in mapper
    assert "WhiteBalance" not in mapper
    assert "CropLeft = crop.left" in crop_mapper
    assert "CropRight = crop.right" in crop_mapper
    assert "CropTop = crop.top" in crop_mapper
    assert "CropBottom = crop.bottom" in crop_mapper
    assert "CropAngle = crop.angle" in crop_mapper


def test_no_unrelated_lightroom_mutation_apis_are_used() -> None:
    plugin_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in PLUGIN.rglob("*.lua")
    )
    forbidden = (
        "setRawMetadata",
        "setFormattedMetadata",
        "setSelectedPhotos",
        "setActivePhoto",
        "setActiveSources",
        "createDevelopSnapshot",
        "LrDevelopController",
        "createVirtualCopy",
        "updateAISettings",
        "applyDenoise",
        "requestEnhance",
        "createEnhancedDNG",
        "LrAI",
    )

    for operation in forbidden:
        assert operation not in plugin_source


def test_plugin_does_not_depend_on_reference_directory() -> None:
    plugin_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in PLUGIN.rglob("*.lua")
    )

    assert "reference/" not in plugin_source
    assert "reference\\" not in plugin_source
