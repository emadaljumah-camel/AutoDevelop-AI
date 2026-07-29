from pathlib import Path

PLUGIN = Path("AutoDevelopAI.lrplugin")


def _read(relative_path: str) -> str:
    return (PLUGIN / relative_path).read_text(encoding="utf-8")


def test_analyze_menu_is_registered_and_delegated() -> None:
    info = _read("Info.lua")
    menu_actions = _read("lib/MenuActions.lua")

    assert 'title = "Analyze Selected Photos"' in info
    assert 'file = "AnalyzeSelectedPhotos.lua"' in info
    assert 'require("lib.AnalyzeCommand").start()' in menu_actions


def test_backend_configuration_uses_autodevelop_port_and_route() -> None:
    config = _read("lib/Config.lua")
    client = _read("lib/ApiClient.lua")

    assert "http://127.0.0.1:8005" in config
    assert 'Config.DEFAULT_STYLE_PROFILE = "natural_travel"' in config
    assert "styleProfileId = Config.DEFAULT_STYLE_PROFILE" in config
    assert '"/autodevelop/v1/analyze"' in client
    assert "LrHttp.post(" in client
    assert '"POST"' in client


def test_requests_use_backend_contract_field_names() -> None:
    builder = _read("lib/RequestBuilder.lua")

    assert "schema_version" in builder
    assert "request_id" in builder
    assert "preview_path" in builder
    assert "current_settings" in builder
    assert "style_profile" in builder
    assert "current_develop_settings" not in builder


def test_json_is_encoded_through_lrjson() -> None:
    json_module = _read("lib/Json.lua")
    client = _read("lib/ApiClient.lua")

    assert "LrJson.encode(value)" in json_module
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


def test_no_lightroom_mutation_apis_are_used() -> None:
    plugin_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in PLUGIN.rglob("*.lua")
    )
    forbidden = (
        "withWriteAccessDo",
        "applyDevelopSettings",
        "setRawMetadata",
        "setSelectedPhotos",
        "setActivePhoto",
        "createDevelopSnapshot",
        "LrDevelopController",
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
