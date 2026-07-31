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


def test_menu_order_excludes_unimplemented_placeholder_commands() -> None:
    info = _read("Info.lua")
    items = _library_menu_items()

    assert list(items) == [
        "Auto Develop Selected Photos",
        "Capture Editing Feedback",
        "Analyze Selected Photos",
        "Settings",
    ]
    for title, script in (
        ("Apply Recommended Crop", "ApplyRecommendedCrop.lua"),
        ("Style Profiles", "StyleProfiles.lua"),
        ("Logs", "Logs.lua"),
    ):
        assert title not in info
        assert script not in info


def test_learning_feedback_menu_and_read_only_workflow_are_registered() -> None:
    menu_items = _library_menu_items()
    assert menu_items["Capture Editing Feedback"] == "CaptureEditingFeedback.lua"
    wrapper = _read("CaptureEditingFeedback.lua")
    command = _read("lib/LearningFeedbackCommand.lua")
    assert 'ModuleLoader.load("lib/LearningFeedbackCommand.lua")' in wrapper
    assert "LearningFeedbackDialog.confirm(summary)" in command
    assert command.index("LearningFeedbackDialog.confirm(summary)") < command.index(
        "LearningClient.captureFeedback"
    )
    for forbidden in (
        "applyDevelopSettings",
        "withWriteAccessDo",
        "setRawMetadata",
        "setFormattedMetadata",
        "setSelectedPhotos",
        "setTargetPhoto",
    ):
        assert forbidden not in command


def test_learning_baseline_occurs_after_apply_and_outside_apply_service() -> None:
    command = _read("lib/AutoDevelopCommand.lua")
    apply_service = _read("lib/ApplyService.lua")
    applied = command.index("local application = applyOne(")
    baseline = command.index("recordBaseline(operation, preferences)")
    assert applied < baseline
    assert "applyOne = ApplyService.applyOne" in command
    assert "recordBaseline = LearningBaselineService.recordOne" in command
    assert "LearningBaselineService" not in apply_service
    assert "LearningClient" not in apply_service


def test_learning_identity_is_sha256_and_tracking_is_plugin_owned() -> None:
    identity = _read("lib/LearningPhotoIdentity.lua")
    sha = _read("lib/Sha256.lua")
    store = _read("lib/LearningSessionStore.lua")
    preferences = _read("lib/Preferences.lua")
    assert "Sha256.digest(canonicalIdentity(photo))" in identity
    assert "function Sha256.digest" in sha
    assert "Preferences.getLearningPendingSessions" in store
    assert "learningPendingSessions" in preferences
    for forbidden in (
        "setRawMetadata",
        "setFormattedMetadata",
        "addKeyword",
        "setRating",
    ):
        assert forbidden not in identity + store


def test_learning_response_is_optional_and_strictly_validated() -> None:
    validation = _read("lib/Validation.lua")
    assert "learning = true" in validation
    assert "validateLearning(response.learning)" in validation


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
    assert 'safeRawMetadata(photo, "fileName")' in utils
    assert 'safeRawMetadata(photo, "path")' in utils
    assert 'safeRawMetadata(photo, "localIdentifier")' not in utils
    assert '"photo_unidentified"' not in utils
    assert 'local LrTasks = import("LrTasks")' in utils
    assert "local ok, value = LrTasks.pcall(function()" in utils
    formatted = utils.index('safeFormattedMetadata(photo, "fileName")')
    raw = utils.index('safeRawMetadata(photo, "fileName")')
    path = utils.index('safeRawMetadata(photo, "path")', raw)
    internal = utils.index("displayFilename or internalId", path)
    assert formatted < raw < path < internal
    assert "function Utils.capturePhotoIdentity(photo)" in utils


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
    assert 'local defaultId = "auto"' in styles


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
    assert "RunSettingsCoordinator.prepare(" in _read("lib/AnalyzeCommand.lua")
    assert "RunSettingsCoordinator.prepare(" not in _read(
        "lib/AutoDevelopCommand.lua"
    )
    assert "function RunSettingsCoordinator.getSnapshot" in coordinator


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

    assert '"Photo Analysis"' in analyze_dialog
    assert '"Recommended style: "' in analyze_dialog
    assert "example.effectiveStyleId" in analyze_dialog
    assert '"Style"' in develop_dialog
    assert '"Selection: "' in develop_dialog
    assert '"Applied style: "' in develop_dialog
    assert '"Editing intensity: "' in develop_dialog


def test_only_authorized_services_use_catalog_develop_writes() -> None:
    apply_service = _read("lib/ApplyService.lua")
    write_sources = {
        path.relative_to(PLUGIN).as_posix()
        for path in PLUGIN.rglob("*.lua")
        if "withWriteAccessDo" in path.read_text(encoding="utf-8")
        or "applyDevelopSettings" in path.read_text(encoding="utf-8")
    }

    assert "catalog:withWriteAccessDo(" in apply_service
    assert "operation.photo:applyDevelopSettings(" in apply_service
    assert "local finalSettings = operation.finalSettings" in apply_service
    assert "sanitize(operation.mappedSettings)" not in apply_service
    assert write_sources == {
        "lib/ApplyService.lua",
    }
    assert "ApiClient" not in apply_service
    assert "PreviewExporter" not in apply_service
    assert "LrDialogs" not in apply_service


def test_hdr_mode_is_categorical_capability_gated_and_apply_service_owned() -> None:
    mapper = _read("lib/DevelopSettingsMapper.lua")
    exif = _read("lib/ExifMapper.lua")
    builder = _read("lib/RequestBuilder.lua")
    validation = _read("lib/Validation.lua")
    preparation = _read("lib/PreparationService.lua")
    apply_service = _read("lib/ApplyService.lua")

    assert "HDREditMode" not in mapper
    assert "function ExifMapper.hdrEditSupported" in exif
    assert "hdr_edit_supported" in builder
    assert 'hdr_workflow = "unknown"' in builder
    assert "validateHdr(response.enable_hdr)" in validation
    assert "validateUpright(response.upright)" in validation
    assert "decoded.enable_hdr.recommended == true" in preparation
    assert "decoded.upright.recommended == true" in preparation
    assert "DevelopModeMapper.encodeUpright" in apply_service
    assert "PerspectiveUpright" in apply_service
    assert "finalSettings.HDREditMode = 1" in apply_service
    assert "finalSettings = finalSettings" in preparation
    apply_path = apply_service[apply_service.index("function ApplyService.applyBatch") :]
    assert "HDREditMode = 1" not in apply_path
    assert "sanitizeRestore(operation.originalSettings)" in apply_service
    assert "applyDevelopSettings" not in preparation


def test_denoise_uses_verified_native_preset_pipeline() -> None:
    exif = _read("lib/ExifMapper.lua")
    service = _read("lib/DenoisePresetService.lua")
    preparation = _read("lib/PreparationService.lua")
    pending = _read("lib/PendingOperation.lua")
    apply_service = _read("lib/ApplyService.lua")
    review = _read("lib/PendingOperationReview.lua")
    summary = _read("lib/BatchSummary.lua")

    assert 'Utils.safeRawMetadata(photo, "fileFormat")' in exif
    assert "exif.file_format" in exif
    for amount in (25, 50, 75):
        assert f'[{amount}] = "AutoDevelop AI - Denoise {amount}"' in service
    assert "LrApplication.developPresetFolders()" in service
    assert "folder:getDevelopPresets()" in service
    assert "preset:getName()" in service
    assert 'format ~= "RAW" and format ~= "DNG"' in service
    assert "containsDenoise(currentSettings.FilterList)" in service
    assert "original.FilterList = Utils.deepCopy" in service
    assert "DenoisePresetService.prepare(" in preparation
    assert "denoisePreset = denoiseCapability.preset" in preparation
    assert "denoiseOriginalSettings = denoiseCapability.originalSettings" in preparation
    assert "settingCount == 0 and not denoiseIncluded" in preparation
    assert "denoisePreset = values.denoisePreset" in pending
    assert "denoiseOriginalSettings = Utils.deepCopy" in pending
    assert "operation.denoiseIncluded == true" in apply_service
    assert 'operation.photo:applyDevelopPreset(' in apply_service
    assert "restoreForOperation(operation)" in apply_service
    apply_path = apply_service.index("operation.photo:applyDevelopPreset(")
    settings_path = apply_service.index("operation.photo:applyDevelopSettings(")
    assert apply_path < settings_path
    assert "getDevelopSettings" not in apply_service
    assert '"Denoise amount: "' in review
    assert '"Denoise preset: "' in review
    assert "operation.denoiseIncluded and \"Yes\" or \"No\"" in review
    assert "if operation.denoiseIncluded ~= true then" in summary
    assert "FilterList" not in _read("lib/DevelopSettingsMapper.lua")


def test_hdr_preference_and_decision_diagnostics_are_carried_to_ui_and_learning() -> None:
    config = _read("lib/Config.lua")
    preferences = _read("lib/Preferences.lua")
    manager = _read("PluginManager.lua")
    builder = _read("lib/RequestBuilder.lua")
    validation = _read("lib/Validation.lua")
    preparation = _read("lib/PreparationService.lua")
    pending = _read("lib/PendingOperation.lua")
    review = _read("lib/PendingOperationReview.lua")
    baseline = _read("lib/LearningBaselineService.lua")

    assert 'hdrPreference = "prefer_hdr"' in config
    assert '{ title = "Conservative", value = "conservative" }' in preferences
    assert '{ title = "Balanced", value = "balanced" }' in preferences
    assert '{ title = "Prefer HDR", value = "prefer_hdr" }' in preferences
    assert '"HDR preference"' in manager
    assert "request.options.hdr_preference" in builder
    assert "hdrPreference = preferences.hdrPreference" in preparation
    assert "validateHdrDecision(response.hdr_decision)" in validation
    assert "hdrDecision = decoded.hdr_decision" in preparation
    assert "hdrDecision = Utils.deepCopy(values.hdrDecision)" in pending
    assert '"Scene candidate: "' in review
    assert '"Base scene evidence: "' in review
    assert '"Learning bonus: "' in review
    assert '"Preference bonus: "' in review
    assert '"Combined evidence: "' in review
    assert '"Model confidence: "' in review
    assert '"Learned preference: "' in review
    assert '"Decision basis: "' in review
    assert '"Decision confidence: "' in review
    assert '"Final decision: "' in review
    assert "originalRaw = modeDiagnostics.hdrEditMode" in review
    assert '"Enabled" or "Disabled"' in review
    for field in (
        "base_scene_evidence_score",
        "learning_bonus",
        "user_preference_bonus",
        "combined_evidence_score",
        "decision_basis",
        "decision_confidence",
        "scene_hdr_inconsistent",
        "contraindications",
    ):
        assert f"{field} = true" in validation
    assert "hdr_decision = baselineHdrDecision(operation.hdrDecision)" in baseline


def test_auto_develop_confirmation_precedes_catalog_application() -> None:
    command = _read("lib/AutoDevelopCommand.lua")

    identity = command.index("local photoIdentity = Utils.capturePhotoIdentity(photo)")
    backend = command.index("local outcome, value = preparePhoto(")
    confirmed = command.index("decision = confirmPhoto(")
    applied = command.index("local application = applyOne(")

    assert identity < backend < confirmed < applied
    assert "withWriteAccessDo" not in command


def test_per_photo_dialog_exposes_all_four_actions() -> None:
    dialog = _read("dialogs/AutoDevelopConfirmationDialog.lua")

    assert 'actionVerb = "Apply"' in dialog
    assert 'otherVerb = "Skip"' in dialog
    assert 'cancelVerb = "Cancel Batch"' in dialog
    assert 'title = "Apply Remaining Without Confirmation"' in dialog
    assert '"apply_remaining"' in dialog
    assert "LrDialogs.stopModalWithResult(" in dialog
    assert "Preferences" not in dialog
    assert "factory:scrolled_view({" in dialog
    assert "vertical_scroller = true" in dialog
    assert "horizontal_scroller = false" in dialog
    assert 'actionVerb = "Apply"' in dialog
    assert 'ModuleLoader.load("lib/PendingOperationReview.lua")' in dialog
    assert 'ModuleLoader.load("lib/PendingOperation.lua")' in dialog
    assert "height_in_lines = -1" in dialog
    assert "title = detailsText" in dialog
    assert "local renderOk, lines, review = LrTasks.pcall(function()" in dialog
    assert 'display.diagnosticCode = "confirmation_render_failed"' in dialog
    assert 'display.diagnosticCode = "unrenderable_final_settings"' in dialog
    assert "review.settingCount ~= display.finalCount" in dialog
    assert 'dialogOptions.actionVerb = "Skip"' in dialog
    assert "if display.canApply then" in dialog
    assert 'Logger.debug(' in dialog
    assert '" rendered_characters="' in dialog


def test_pending_operation_review_uses_only_prepared_snapshots() -> None:
    review = _read("lib/PendingOperationReview.lua")

    assert "operation.originalSettings" in review
    assert "operation.finalSettings" in review
    assert "operation.mappedSettings" not in review
    for forbidden in (
        "ApiClient",
        "BackendClient",
        "Preferences",
        "LrHttp",
        "PreviewExporter",
        "withWriteAccessDo",
        "applyDevelopSettings",
    ):
        assert forbidden not in review
    assert "math.min(#items, 5)" in review
    assert "DevelopSettingsMapper.keys()" in review
    assert "CropMapper.keys()" in review
    assert "Utils.isFiniteNumber(finalSettings[key])" in review
    assert "Current-value comparison is unavailable" in review
    for label in (
        "Exposure",
        "Contrast",
        "Highlights",
        "Shadows",
        "Whites",
        "Blacks",
        "Texture",
        "Clarity",
        "Dehaze",
        "Vibrance",
        "Saturation",
        "Temperature",
        "Tint",
    ):
        assert f'= "{label}"' in review


def test_confirmation_rendering_has_no_backend_or_write_side_effects() -> None:
    dialog = _read("dialogs/AutoDevelopConfirmationDialog.lua")
    review = _read("lib/PendingOperationReview.lua")

    for forbidden in (
        "ApiClient",
        "BackendClient",
        "Preferences",
        "LrHttp",
        "PreviewExporter",
        "getDevelopSettings",
        "getRawMetadata",
        "getFormattedMetadata",
        "withWriteAccessDo",
        "applyDevelopSettings",
    ):
        assert forbidden not in dialog + review
    assert "operation.displayFilename" in dialog


def test_display_filename_is_captured_and_propagated_without_write_time_reads() -> None:
    preparation = _read("lib/PreparationService.lua")
    request_builder = _read("lib/RequestBuilder.lua")
    pending = _read("lib/PendingOperation.lua")
    summary = _read("lib/BatchSummary.lua")
    analyze = _read("lib/AnalyzeCommand.lua")
    analysis_dialog = _read("dialogs/AnalysisSummaryDialog.lua")
    learning_command = _read("lib/LearningFeedbackCommand.lua")
    learning_dialog = _read("dialogs/LearningFeedbackDialog.lua")
    apply_service = _read("lib/ApplyService.lua")

    assert "photoIdentity = photoIdentity" in preparation
    assert "photoId = photoIdentity.photoId" in preparation
    assert "displayFilename = photoIdentity.displayFilename" in preparation
    assert "options.photoIdentity" in request_builder
    assert "photoId = values.photoId" in pending
    assert "values.displayFilename" in pending
    assert "operation.displayFilename or operation.filename" in summary
    assert "displayFilename = photoIdentity.displayFilename" in analyze
    assert "example.displayFilename" in analysis_dialog
    assert "summary.displayFilename = photoIdentity.displayFilename" in learning_command
    assert "summary.displayFilename" in learning_dialog

    write_path = apply_service[apply_service.index("function ApplyService.applyBatch") :]
    assert "getFormattedMetadata" not in write_path
    assert "getRawMetadata" not in write_path


def test_sequential_flow_passes_same_operation_after_confirmation() -> None:
    command = _read("lib/AutoDevelopCommand.lua")

    operation = command.index("local operation = value")
    confirmation = command.index(
        "decision = confirmPhoto(operation, index, #photos)",
        operation,
    )
    application = command.index(
        "local application = applyOne(",
        confirmation,
    )
    release = command.index("onRelease(operation)", application)
    assert operation < confirmation < application < release
    between = command[confirmation:application]
    assert "PendingOperation.new" not in between
    assert "mappedSettings" not in between
    assert "finalSettings" not in between


def test_catalog_write_block_contains_only_apply_and_restore() -> None:
    apply_service = _read("lib/ApplyService.lua")

    assert "catalog:withWriteAccessDo(" in apply_service
    assert "operation.photo:applyDevelopSettings(" in apply_service
    for forbidden in (
        "LrDialogs",
        "LrHttp",
        "ApiClient",
        "PreviewExporter",
        "LearningClient",
        "LearningBaselineService",
        "LrExportSession",
        "LrTasks.sleep",
        "infer(",
    ):
        assert forbidden not in apply_service


def test_auto_develop_uses_sequential_cancellation_safe_points() -> None:
    command = _read("lib/AutoDevelopCommand.lua")

    loop = command.index("for index, photo in ipairs(photos) do")
    first_cancel = command.index("if progressScope:isCanceled() then", loop)
    preparation = command.index("local outcome, value = preparePhoto(", first_cancel)
    response_cancel = command.index(
        'if outcome == "cancelled" or progressScope:isCanceled() then',
        preparation,
    )
    decision = command.index("decision = confirmPhoto(", response_cancel)
    apply_call = command.index("local application = applyOne(", decision)

    assert loop < first_cancel < preparation < response_cancel
    assert response_cancel < decision < apply_call
    assert "ApplicationGate" not in command
    assert "ErrorClassifier.isTerminalForBatch(value.category)" in command


def test_auto_develop_holds_only_the_current_operation() -> None:
    command = _read("lib/AutoDevelopCommand.lua")
    assert "local operation = value" in command
    assert "onRelease(operation)" in command
    assert "operation = nil" in command
    assert "local operations = {}" not in command
    assert "BatchOperationRecorder" not in command
    assert "PendingOperation.clear" not in command


def test_cancel_and_terminal_failures_count_unprocessed_photos() -> None:
    command = _read("lib/AutoDevelopCommand.lua")

    assert "BatchSummary.markNotProcessed(summary, #photos - index + 1)" in command
    assert "summary.terminalCategory = value.category" in command
    assert "#photos - index" in command
    assert command.count("AutoDevelopConfirmationDialog.showFinal(") == 1


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
    assert "requestFunction(request, requestOptions)" in service
    assert "requestOptions.endpointAttempt = retriesUsed + 1" in service
    assert "return result.retryable == true" in classifier
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
        "geometry_mapping_started",
        "geometry_mapping_completed",
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


def test_sequential_operation_lifecycle_is_incremental() -> None:
    command = _read("lib/AutoDevelopCommand.lua")
    summary = _read("lib/BatchSummary.lua")

    prepared = command.index("BatchSummary.recordPrepared(summary, operation)")
    applied = command.index("BatchSummary.recordApplication(")
    released = command.index("onRelease(operation)", applied)
    assert prepared < applied < released
    assert "function BatchSummary.recordPrepared" in summary
    assert "function BatchSummary.recordApplication" in summary
    assert "#(operation.warnings or {})" in summary


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
    assert 'preferences.confirmationMode == "never"' in develop
    assert "confirmPhoto(operation, index, #photos)" in develop
    assert 'decision == "apply_remaining"' in develop
    assert "operation.cropDisabled" in preparation
    assert "operation.levelingDisabled" in preparation
    assert "summary.cropAppliedCount" in develop
    assert "summary.levelingAppliedCount" in develop
    assert "setBatchCounts" in progress


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

    constructed = command.index("local progressScope = LrProgressScope")
    registered = command.index(
        "context:addCleanupHandler(releaseProgress)",
        constructed,
    )
    configured = command.index(
        "progressScope:setCancelable(true)",
        registered,
    )
    assert constructed < registered < configured
    assert "progressScope:" not in command[constructed:registered]
    assert command.count("LrProgressScope({") == 1


def test_auto_develop_uses_per_photo_cleanup_and_no_standard_xpcall() -> None:
    command = _read("lib/AutoDevelopCommand.lua")
    apply_service = _read("lib/ApplyService.lua")
    preparation = _read("lib/PreparationService.lua")

    assert "context:addCleanupHandler" in command
    assert "context:addCleanupHandler" in preparation
    assert "cleanupPreview(preview)" in preparation
    assert "cleanupBatch(batchDirectory)" in command
    assert "local operation = value" in command
    assert "operation = nil" in command
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
    assert "CropLeft = applyCrop and crop.left" in crop_mapper
    assert "CropRight = applyCrop and crop.right" in crop_mapper
    assert "CropTop = applyCrop and crop.top" in crop_mapper
    assert "CropBottom = applyCrop and crop.bottom" in crop_mapper
    assert "and leveling.angle or currentSettings.CropAngle" in crop_mapper


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


def test_feedback_preview_is_backend_authoritative_and_precedes_save() -> None:
    command = _read("lib/LearningFeedbackCommand.lua")
    mapper = _read("lib/ExifMapper.lua")
    session_store = _read("lib/LearningSessionStore.lua")
    api_client = _read("lib/ApiClient.lua")
    config = _read("lib/Config.lua")

    preview = command.index("LearningClient.previewFeedback")
    dialog = command.index("LearningFeedbackDialog.confirm")
    save = command.index("LearningClient.captureFeedback")
    assert preview < dialog < save
    assert "local thresholds" not in command
    assert "significantCount" not in command
    assert "baselineSettings" not in session_store
    assert "LrTasks.pcall(function()" in mapper
    assert "return photo:getDevelopSettings()" in mapper
    assert "local ok, source = pcall" not in mapper
    assert "learningFeedbackPreview" in api_client
    assert "/learning/feedback/preview" in config


def test_learning_modes_are_captured_once_and_kept_categorical() -> None:
    exif = _read("lib/ExifMapper.lua")
    baseline = _read("lib/LearningBaselineService.lua")
    feedback = _read("lib/LearningFeedbackCommand.lua")
    client = _read("lib/LearningClient.lua")

    assert "function ExifMapper.mapLearningDevelopState" in exif
    assert "DevelopModeMapper.decodeUpright" in exif
    assert "DevelopModeMapper.decodeHdr" in exif
    assert "HDRMaxValue = source.HDRMaxValue" in exif
    assert "function ExifMapper.filterLearningSettings" in exif
    assert "original_settings = ExifMapper.filterLearningSettings(" in baseline
    assert "recommendation = ExifMapper.filterLearningSettings(" in baseline
    assert "applied_modes = captured.modes" in baseline
    assert "hdr_decision = baselineHdrDecision(operation.hdrDecision)" in baseline
    assert "next(normalized.contraindications) == nil" in baseline
    assert "learning_baseline_save_failed filename=" in baseline
    assert "final_modes = captured.modes" in feedback
    assert "modeChanges(decoded.mode_changes)" in client
    assert "withWriteAccessDo" not in baseline
    assert "withWriteAccessDo" not in feedback


def test_learning_status_uses_unclipped_multiline_mode_counts() -> None:
    manager = _read("PluginManager.lua")

    assert '"\\nUpright: "' in manager
    assert '"\\nHDR: "' in manager
    assert "result.upright_learning.change_count" in manager
    assert "result.upright_learning.acceptance_count" in manager
    assert "result.hdr_learning.change_count" in manager
    assert "result.hdr_learning.acceptance_count" in manager
    assert "width_in_chars = 54" in manager
    assert "height_in_lines = 3" in manager


def test_upright_application_and_confirmation_use_exact_structured_decision() -> None:
    apply_service = _read("lib/ApplyService.lua")
    preparation = _read("lib/PreparationService.lua")
    pending = _read("lib/PendingOperation.lua")
    review = _read("lib/PendingOperationReview.lua")
    dialog = _read("dialogs/AutoDevelopConfirmationDialog.lua")

    assert "finalSettings.EnableTransform = true" in apply_service
    assert "finalSettings.PerspectiveUpright = mappedUpright" in apply_service
    assert "upright = {" in preparation
    assert "hdr = {" in preparation
    assert "local upright = Utils.deepCopy(values.upright" in pending
    assert '"Confidence: " .. confidenceText(decision.confidence)' in review
    assert "originalRaw = diagnostics.perspectiveUpright" in review
    assert '"Unavailable (no change proposed)"' in review
    assert '"No Upright correction recommended"' in review
    assert "Utils.safeMessage(decision.reason, fallbackReason)" in review
    assert 'appendSection(lines, "Transform Upright"' in dialog
    assert 'appendSection(lines, "HDR"' in dialog


def test_auto_develop_completion_exposes_learning_diagnostics() -> None:
    command = _read("lib/AutoDevelopCommand.lua")
    summary = _read("lib/BatchSummary.lua")
    dialog = _read("dialogs/AutoDevelopConfirmationDialog.lua")
    validation = _read("lib/Validation.lua")
    config = _read("lib/Config.lua")

    assert "BatchSummary.recordPrepared(summary, operation)" in command
    assert "BatchSummary.recordLearning(summary, operation.learning)" in summary
    assert "function BatchSummary.recordLearning" in summary
    for field in (
        "minimum_sample_count",
        "average_similarity",
    ):
        assert field in validation
    for label in (
        "Learning",
        "Usable feedback samples:",
        "Similar samples found:",
        "Average similarity:",
        "Personalization:",
        "Reason:",
    ):
        assert label in dialog
    assert "learningShowSummary = true" in config


def test_final_develop_dialog_is_incremental_and_informational() -> None:
    dialog = _read("dialogs/AutoDevelopConfirmationDialog.lua")

    for label in (
        "Selected:",
        "Processed:",
        "Applied:",
        "Skipped:",
        "Failed:",
        "Restored after apply failure:",
        "Restore failed:",
        "Not processed:",
        "Cancelled:",
        "Elapsed:",
        "Composition crops applied:",
        "Level corrections applied:",
        "HDR recommended:",
        "HDR applied:",
        "Denoise recommended:",
        "Denoise applied:",
        "Personalization applied:",
        "Style distribution:",
        "Editing intensity distribution:",
    ):
        assert label in dialog
    assert "AutoDevelop AI - Batch Complete" in dialog
    assert "No photo has been modified yet" not in dialog
    assert "Ready to apply:" not in dialog
    assert "Examples:" not in dialog
    assert "function AutoDevelopConfirmationDialog.confirm(" not in dialog


def test_plugin_does_not_depend_on_reference_directory() -> None:
    plugin_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in PLUGIN.rglob("*.lua")
    )

    assert "reference/" not in plugin_source
    assert "reference\\" not in plugin_source
