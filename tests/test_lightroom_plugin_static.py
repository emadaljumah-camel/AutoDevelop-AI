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
    assert 'Config.API_PREFIX = "/autodevelop/v1"' in config
    assert 'analyze = Config.API_PREFIX .. "/analyze"' in config
    assert 'develop = Config.API_PREFIX .. "/develop"' in config
    assert 'health = Config.API_PREFIX .. "/health"' in config
    assert "Config.apiPaths.analyze" in client
    assert "Config.apiPaths.develop" in client
    assert "LrHttp.post(" in client
    assert '"POST"' in client
    assert "8004" not in config
    assert "8004" not in client


def test_requests_use_backend_contract_field_names() -> None:
    builder = _read("lib/RequestBuilder.lua")

    assert "schema_version" in builder
    assert "Config.SCHEMA_VERSION" in builder
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
    preparation = _read("lib/PreparationService.lua")

    assert "LrTasks.startAsyncTask(function()" in command
    assert "LrFunctionContext.callWithContext" in command
    assert "LrTasks.pcall" in command
    assert "for index, photo in ipairs(photos) do" in command
    assert "progressScope:isCanceled()" in command
    assert "LrTasks.sleep(0.5)" in preparation
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
    preferences = _read("lib/Preferences.lua")
    styles = _read("lib/StyleProfiles.lua")

    assert '"natural_travel"' not in config
    assert '"natural_travel"' not in preferences
    assert '"natural_travel"' not in builder
    assert "Preferences.getStyleProfileId()" not in builder
    assert "StyleProfiles.isValidId(styleProfile)" in builder
    assert "StyleProfiles.getChoices()" in preferences
    assert "StyleProfiles.getDefaultId()" in preferences
    assert 'local defaultId = "natural_travel"' in styles


def test_style_dialog_precedes_all_processing_in_both_commands() -> None:
    for command_name in ("AnalyzeCommand.lua", "AutoDevelopCommand.lua"):
        source = _read(f"lib/{command_name}")
        command = source[source.index("local function runCommand") :]
        dialog = command.index("RunSettingsDialog.show(")

        assert dialog < command.index("PreviewExporter.createBatchDirectory()")
        assert dialog < command.index("LrProgressScope({")


def test_style_dialog_has_no_processing_or_catalog_side_effects() -> None:
    dialog = _read("dialogs/RunSettingsDialog.lua")

    assert 'import("LrBinding")' in dialog
    assert "LrBinding.makePropertyTable(context)" in dialog
    assert "LrDialogs.presentModalDialog({" in dialog
    assert "LrView.bind" in dialog
    assert "ApiClient" not in dialog
    assert "BackendClient" not in dialog
    assert "PreviewExporter" not in dialog
    assert "withWriteAccessDo" not in dialog
    assert "applyDevelopSettings" not in dialog
    assert "getRawMetadata" not in dialog
    assert "getFormattedMetadata" not in dialog
    assert "LrTasks.sleep" not in dialog
    assert "Preferences" not in dialog


def test_commands_use_pure_style_run_coordinator() -> None:
    coordinator = _read("lib/RunSettingsCoordinator.lua")

    for command_name in ("AnalyzeCommand.lua", "AutoDevelopCommand.lua"):
        command = _read(f"lib/{command_name}")
        assert 'ModuleLoader.load("lib/RunSettingsCoordinator.lua")' in command
        assert "RunSettingsCoordinator.begin({" in command
        assert "RunSettingsCoordinator.prepare(" in command


def test_phase3_model_selection_is_explicit_and_side_effect_free() -> None:
    registry = _read("lib/ModelProfiles.lua")
    dialog = _read("dialogs/RunSettingsDialog.lua")
    builder = _read("lib/RequestBuilder.lua")
    coordinator = _read("lib/RunSettingsCoordinator.lua")

    for model_id in ("gemma", "qwen", "gpt_oss", "gemini", "claude"):
        assert f'id = "{model_id}"' in registry
    assert 'defaultId = "gemma"' in registry
    assert "ModelProfiles.getSelectableChoices()" in dialog
    assert "Claude — Future" in dialog
    assert "request.model = modelProfile" not in builder
    assert "model = modelProfile" in builder
    assert "snapshot.modelProfileId = modelId" in coordinator
    for forbidden in (
        "LrHttp",
        "PreviewExporter",
        "withWriteAccessDo",
        "catalog:with",
    ):
        assert forbidden not in dialog

    for forbidden in (
        "LrDialogs",
        "LrProgressScope",
        "PreviewExporter",
        "ApiClient",
        "BackendClient",
        "withWriteAccessDo",
        "applyDevelopSettings",
        "LrTasks.sleep",
        "pcall(",
        "xpcall(",
    ):
        assert forbidden not in coordinator


def test_commands_pass_one_explicit_run_profile_to_request_builders() -> None:
    analyze = _read("lib/AnalyzeCommand.lua")
    develop = _read("lib/PreparationService.lua")
    builder = _read("lib/RequestBuilder.lua")

    assert "styleProfileId = preferences.styleProfileId" in analyze
    assert "styleProfileId = preferences.styleProfileId" in develop
    assert "Preferences" not in builder
    assert "options.styleProfileId" in builder


def test_style_summaries_include_display_name_and_stable_id() -> None:
    analyze_dialog = _read("dialogs/AnalysisSummaryDialog.lua")
    develop_dialog = _read("dialogs/AutoDevelopConfirmationDialog.lua")

    for dialog in (analyze_dialog, develop_dialog):
        assert '"Style: "' in dialog
        assert '"Profile ID: "' in dialog


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

    backend = command.index("PreparationService.prepareDevelopPhoto(")
    confirmed = command.index(
        "AutoDevelopConfirmationDialog.confirm(summary)"
    )
    applied = command.index("ApplyService.applyBatch(catalog, operations")

    assert backend < confirmed < applied
    assert "withWriteAccessDo" not in command


def test_auto_develop_uses_ordered_cancellation_application_gates() -> None:
    command = _read("lib/AutoDevelopCommand.lua")

    preparation_call = command.index(
        "prepareBatch(",
        command.index("local function runCommand("),
    )
    preparation_gate = command.index(
        "local preparationDecision = ApplicationGate.evaluate({",
        preparation_call,
    )
    confirmation = command.index(
        "AutoDevelopConfirmationDialog.confirm(summary)",
        preparation_gate,
    )
    confirmed_gate = command.index(
        "local confirmedDecision = ApplicationGate.evaluate({",
        confirmation,
    )
    final_gate = command.index(
        "local finalDecision = ApplicationGate.evaluate({",
        confirmed_gate,
    )
    application = command.index(
        "ApplyService.applyBatch(catalog, operations",
        final_gate,
    )

    assert preparation_call < preparation_gate < confirmation
    assert confirmation < confirmed_gate < final_gate < application
    assert "progressCancelled = preparationProgress:isCanceled()" in command
    assert "progressCancelled = applyProgress:isCanceled()" in command
    assert "if not finalDecision.shouldApply then" in command


def test_auto_develop_uses_pure_operation_recorder() -> None:
    command = _read("lib/AutoDevelopCommand.lua")
    recorder = _read("lib/BatchOperationRecorder.lua")

    prepared = command.index("PreparationService.prepareDevelopPhoto(")
    recording = command.index(
        "BatchOperationRecorder.tryRecord({",
        prepared,
    )

    assert prepared < recording
    assert "operations[#operations + 1] = value" not in command
    assert "state.operations[#state.operations + 1] = state.operation" in recorder
    assert 'return "cancelled"' in recorder
    assert 'return "terminal_failure"' in recorder
    assert 'return "invalid_operation"' in recorder


def test_cancelled_outcome_precedes_terminal_dialog() -> None:
    command = _read("lib/AutoDevelopCommand.lua")

    cancelled = command.index("if preparationDecision.cancelled then")
    terminal = command.index(
        "elseif preparationDecision.terminalFailure then",
        cancelled,
    )
    terminal_dialog = command.index(
        "ErrorDialog.show(summary.terminalCategory, summary)",
        terminal,
    )

    assert cancelled < terminal < terminal_dialog
    assert "AutoDevelopConfirmationDialog.showFinal(summary, application)" in (
        command[cancelled:terminal]
    )
    assert "ErrorDialog.show(" not in command[cancelled:terminal]


def test_plugin_manager_provider_and_preferences_are_registered() -> None:
    info = _read("Info.lua")
    provider = _read("PluginManager.lua")

    assert 'LrPluginInfoProvider = "PluginManager.lua"' in info
    assert (PLUGIN / "PluginManager.lua").is_file()
    assert "sectionsForTopOfDialog" in provider
    assert "Preferences.getStyleProfileChoices()" in provider
    assert "Preferences.getConfirmationChoices()" in provider
    assert "Preferences.getLoggingChoices()" in provider
    assert "BackendClient.getHealth," in provider
    assert "settings.backendBaseUrl," in provider
    assert "settings.requestTimeoutSeconds" in provider
    assert "LrTasks.startAsyncTask(function()" in provider
    assert "if properties.connectionTestRunning then" in provider
    assert "PreviewExporter" not in provider
    assert "withWriteAccessDo" not in provider
    assert "getTargetPhotos" not in provider
    assert "Reset Defaults" in provider
    assert "10-600 seconds" in provider
    assert "applies automatically after" in provider


def test_preferences_are_the_only_lr_prefs_boundary() -> None:
    users = []
    for path in PLUGIN.rglob("*.lua"):
        source = path.read_text(encoding="utf-8")
        if "prefsForPlugin" in source or 'import("LrPrefs")' in source:
            users.append(path.relative_to(PLUGIN).as_posix())

    assert users == ["lib/Preferences.lua"]
    preferences = _read("lib/Preferences.lua")
    assert "requestTimeoutSeconds = 120" in _read("lib/Config.lua")
    assert "normalized < 10" in preferences
    assert "normalized > 600" in preferences
    assert "normalized % 1 ~= 0" in preferences
    assert "Config.API_PREFIX" in preferences
    assert "store()[key] = normalized" in preferences
    assert "preferences[key] = value" in preferences


def test_request_builder_imports_every_referenced_project_module() -> None:
    builder = _read("lib/RequestBuilder.lua")

    assert 'local Config = ModuleLoader.load("lib/Config.lua")' in builder
    assert "schema_version = Config.SCHEMA_VERSION" in builder


def test_phase_one_error_categories_are_centralized() -> None:
    classifier = _read("lib/ErrorClassifier.lua")
    client = _read("lib/ApiClient.lua")
    service = _read("lib/PreparationService.lua")

    for category in (
        "backend_not_running",
        "invalid_profile",
        "model_timeout",
        "network_error",
        "invalid_response",
        "backend_error",
        "validation_error",
        "cancelled",
        "internal_error",
    ):
        assert f'"{category}"' in classifier

    assert "headers.error.errorCode" in client
    assert "Validation.parseErrorResponse" in client
    assert "retriesUsed < 1" in _read("lib/BatchPolicy.lua")
    assert "requestFunction(request, connectionOptions)" in service
    assert "result.requestId = request.request_id" in service
    assert "result.filename = request.filename" in service


def test_develop_post_response_lifecycle_markers_are_safe_and_ordered() -> None:
    service = _read("lib/PreparationService.lua")
    markers = (
        "develop_preparation_started",
        "preview_export_started",
        "preview_export_completed",
        "request_build_started",
        "request_build_completed",
        "api_request_started",
        "api_response_received",
        "json_decode_started",
        "json_decode_completed",
        "response_validation_started",
        "response_validation_completed",
        "develop_mapping_started",
        "develop_mapping_completed",
        "crop_mapping_started",
        "crop_mapping_completed",
        "pending_operation_build_started",
        "pending_operation_build_completed",
    )

    positions = [service.index(f'"{marker}"') for marker in markers]
    assert positions == sorted(positions)
    assert '"stage="' in service
    assert '" category="' in service
    assert "Logger.warn(decodeError" not in service
    assert "Logger.warn(validationError" not in service
    assert "Logger.error(failure" not in service
    assert "response.body" not in service
    assert "local ok, result = LrTasks.pcall(function()" in service
    assert "return LrFunctionContext.callWithContext(" in service
    assert "local outcome, value = prepareDevelopPhotoBody(" in service
    assert "outcome = outcome," in service
    assert "value = value," in service
    assert "return result.outcome, result.value" in service
    assert '"invalid_preparation_result"' in service


def test_final_dialog_displays_only_a_sanitized_failure_code() -> None:
    dialog = _read("dialogs/AutoDevelopConfirmationDialog.lua")
    summary = _read("lib/BatchSummary.lua")
    service = _read("lib/PreparationService.lua")

    assert '"Diagnostic code: "' in dialog
    assert '"Diagnostic stage: "' in dialog
    assert "Utils.safeErrorCode(" in dialog
    assert "firstFailure.code" in dialog
    assert "firstFailure.stage" in dialog
    assert "firstFailure.message" not in dialog
    assert "failure.stage = Utils.safeErrorCode(" in service
    assert "develop_preparation_entry" in service
    assert "Utils.safeErrorCode(stage, " in summary


def test_operation_record_lifecycle_uses_actual_batch_recorder() -> None:
    command = _read("lib/AutoDevelopCommand.lua")
    started = command.index('Logger.info("operation_record_started")')
    recorded = command.index(
        "BatchOperationRecorder.tryRecord(",
        started,
    )
    completed = command.index(
        'Logger.info("operation_record_completed")',
        recorded,
    )

    assert started < recorded < completed
    assert '"stage=operation_record category="' in command


def test_progress_and_confirmation_preferences_are_integrated() -> None:
    progress = _read("lib/ProgressTracker.lua")
    analyze = _read("lib/AnalyzeCommand.lua")
    develop = _read("lib/AutoDevelopCommand.lua")
    preparation = _read("lib/PreparationService.lua")

    assert "Photos completed:" in progress
    assert "Elapsed:" in progress
    assert "Estimated remaining:" in progress
    assert "self.completed < 1" in progress
    assert "ProgressTracker.new(#photos" in analyze
    assert "ProgressTracker.new(#photos" in develop
    assert 'confirmationMode = preferences.confirmationMode' in develop
    assert "if preparationDecision.cancelled then" in develop
    assert "elseif preparationDecision.terminalFailure then" in develop
    assert "operation.cropDisabled" in preparation
    assert "application.cropApplied" in develop
    assert "confirmation_mode=" in develop


def test_model_identifier_is_validated_before_logs_and_summaries() -> None:
    validation = _read("lib/Validation.lua")
    analyze = _read("lib/AnalyzeCommand.lua")
    preparation = _read("lib/PreparationService.lua")
    dialog = _read("dialogs/AutoDevelopConfirmationDialog.lua")

    assert "Validation.validateModelIdentifier" in validation
    assert 'value:match("^[A-Za-z]:")' in validation
    assert 'value:match("^[A-Za-z]:[/\\\\]")' not in validation
    assert "validatedModel" in analyze
    assert ".. validatedModel" in analyze
    assert "tostring(decoded.model)" not in analyze
    assert "model = validatedModel" in preparation
    assert "model = decoded.model" not in preparation
    assert "Validation.validateModelIdentifier(name)" in dialog


def test_workflow_exception_handlers_do_not_log_caught_values() -> None:
    workflow_files = (
        "lib/AnalyzeCommand.lua",
        "lib/AutoDevelopCommand.lua",
        "lib/PreparationService.lua",
        "lib/ApplyService.lua",
        "lib/ApiClient.lua",
        "lib/PreviewExporter.lua",
    )
    forbidden = (
        "tostring(failure)",
        "tostring(outcome)",
        "tostring(encodeError)",
        "tostring(responseBody)",
        "tostring(applyError)",
        "tostring(writeError)",
        "tostring(moveError)",
        "tostring(cleanupError)",
        "Utils.safeMessage(reason",
        "Utils.safeMessage(previewError",
        "Utils.safeMessage(requestError",
        "Utils.safeMessage(decodeError",
        "Utils.safeMessage(validationError",
    )

    for relative_path in workflow_files:
        source = _read(relative_path)
        for expression in forbidden:
            assert expression not in source, (
                f"{relative_path} exposes caught value via {expression}"
            )


def test_apply_service_returns_only_stable_failure_details() -> None:
    source = _read("lib/ApplyService.lua")

    assert 'operation.applyErrorCategory = "apply_failed"' in source
    assert '"lightroom_apply_failed"' in source
    assert 'result.writeErrorCategory = "write_access_failed"' in source
    assert '"catalog_write_access_failed"' in source
    assert "applyError," not in source
    assert "writeError," not in source


def test_ordinary_logging_does_not_emit_payloads_or_preview_paths() -> None:
    logger = _read("lib/Logger.lua")
    analyze = _read("lib/AnalyzeCommand.lua")
    develop = _read("lib/AutoDevelopCommand.lua")

    assert "preview_path" not in logger
    assert "base64" not in logger
    assert "prompt" not in logger.lower()
    assert "encoded" not in logger
    assert "Logger.info(encoded" not in analyze
    assert "Logger.info(encoded" not in develop


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
    preparation = _read("lib/PreparationService.lua")

    assert "context:addCleanupHandler" in command
    assert "context:addCleanupHandler" in preparation
    assert "cleanupPreview(preview)" in preparation
    assert "cleanupBatch(batchDirectory)" in command
    assert "PendingOperation.clear(operations)" in command
    assert "LrTasks.startAsyncTask(function()" in command
    assert "LrTasks.pcall" in command
    assert "xpcall" not in command
    assert "xpcall" not in preparation
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
