"""Static integration checks for the Lightroom Plug-in Manager provider."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "AutoDevelopAI.lrplugin"


def _read(relative_path: str) -> str:
    return (PLUGIN / relative_path).read_text(encoding="utf-8")


def test_plugin_manager_uses_one_bound_observable_state_table() -> None:
    source = _read("PluginManager.lua")

    assert 'local LrBinding = import("LrBinding")' in source
    assert "local bind = LrView.bind" in source
    assert "local share = LrView.share" in source
    assert "bind_to_object = propertyTable" in source
    assert re.search(
        r"PluginManagerController\.populate\(\s*propertyTable\s*\)",
        source,
    )
    assert "LrBinding.makePropertyTable" not in source


def test_plugin_manager_populates_all_required_properties() -> None:
    controller = _read("lib/PluginManagerController.lua")

    for property_name in (
        "backendBaseUrl",
        "styleProfileId",
        "requestTimeoutText",
        "applyCrop",
        "confirmationMode",
        "loggingLevel",
        "connectionState",
        "connectionStatusText",
        "connectionTestRunning",
        "validationMessage",
    ):
        assert property_name in controller

    assert 'properties.connectionState = "idle"' in controller
    assert 'properties.connectionStatusText = "Not tested"' in controller
    assert "properties.connectionTestRunning = false" in controller


def test_popup_choices_use_ordered_getters_and_exact_labels() -> None:
    preferences = _read("lib/Preferences.lua")
    styles = _read("lib/StyleProfiles.lua")

    expected_styles = (
        ("Natural Travel", "natural_travel"),
        ("Landscape Impact", "landscape_impact"),
        ("Architecture", "architecture"),
        ("Stock Neutral", "stock_neutral"),
        ("Portrait", "portrait"),
        ("Night", "night"),
        ("Documentary", "documentary"),
    )
    for title, value in expected_styles:
        assert f'id = "{value}"' in styles
        assert f'displayName = "{title}"' in styles

    expected_preference_items = (
        ("Always", "always"),
        ("Never", "never"),
        ("Error", "error"),
        ("Warning", "warning"),
        ("Info", "info"),
        ("Debug", "debug"),
    )
    for title, value in expected_preference_items:
        item = f'{{ title = "{title}", value = "{value}" }}'
        assert item in preferences

    assert "StyleProfiles.getChoices()" in preferences

    for getter in (
        "getStyleProfileChoices",
        "getConfirmationChoices",
        "getLoggingChoices",
    ):
        assert f"function Preferences.{getter}()" in preferences


def test_timeout_is_a_plain_text_control_without_numeric_options() -> None:
    source = _read("PluginManager.lua")
    timeout_control = re.search(
        r'factory:edit_field\(\{\s*'
        r'value = bind\("requestTimeoutText"\),(.*?)\}\)',
        source,
        re.DOTALL,
    )

    assert timeout_control is not None
    control = timeout_control.group(1)
    assert "width_in_chars = 6" in control
    assert "immediate = true" in control
    for numeric_option in (
        "width_in_digits",
        "precision",
        "increment",
        "min",
        "max",
        "formatter",
    ):
        assert numeric_option not in control


def test_connection_handler_is_async_guarded_and_visibly_bound() -> None:
    source = _read("PluginManager.lua")

    assert "if properties.connectionTestRunning then" in source
    assert "PluginManagerController.validateAndSave(properties)" in source
    assert 'properties.connectionState = "testing"' in source
    assert 'properties.connectionStatusText = "Testing…"' in source
    assert source.index('properties.connectionStatusText = "Testing…"') < (
        source.index("LrTasks.startAsyncTask(function()")
    )
    assert "LrTasks.pcall(" in source
    assert "setPropertySafely(" in source
    assert 'enabled = bind("canTestConnection")' in source
    assert 'title = bind("connectionStatusText")' in source


def test_connection_diagnostics_are_safe_lifecycle_markers() -> None:
    source = _read("PluginManager.lua")

    for marker in (
        "plugin_manager_test_connection_started",
        "plugin_manager_test_connection_completed category=",
        "plugin_manager_test_connection_failed ",
    ):
        assert marker in source
    assert "Logger.debug(result" not in source
    assert "Logger.debug(outcome.text" not in source


def test_connection_ui_has_no_photo_or_catalog_side_effects() -> None:
    source = _read("PluginManager.lua")

    for forbidden in (
        "LrApplication",
        "getTargetPhotos",
        "getTargetPhoto",
        "PreviewExporter",
        "requestJpegThumbnail",
        "withWriteAccessDo",
        "applyDevelopSettings",
        "LrExportSession",
    ):
        assert forbidden not in source


def test_reset_defaults_repopulates_state_and_clears_status() -> None:
    source = _read("PluginManager.lua")
    controller = _read("lib/PluginManagerController.lua")

    assert "Preferences.resetDefaults()" in source
    assert "PluginManagerController.populate(" in source
    assert 'properties.validationMessage = errors[1] or ""' in controller
    assert 'properties.connectionStatusText = "Not tested"' in controller
