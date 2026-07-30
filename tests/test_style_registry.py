import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from autodevelop.profiles import (
    DEFAULT_STYLE_ID,
    StyleProfileLoader,
    get_style,
    is_valid_style_id,
    list_styles,
)


EXPECTED_STYLES = [
    ("natural_travel", "Natural Travel"),
    ("landscape_impact", "Landscape Impact"),
    ("architecture", "Architecture"),
    ("stock_neutral", "Stock Neutral"),
    ("portrait", "Portrait"),
    ("night", "Night"),
    ("documentary", "Documentary"),
]


def test_registry_has_exactly_seven_styles_in_display_order() -> None:
    styles = list_styles()

    assert [(style.id, style.display_name) for style in styles] == EXPECTED_STYLES
    assert [style.sort_order for style in styles] == list(range(1, 8))


def test_registry_fields_are_unique_and_descriptions_are_nonblank() -> None:
    styles = list_styles()

    assert len({style.id for style in styles}) == len(styles)
    assert len({style.display_name for style in styles}) == len(styles)
    assert len({style.sort_order for style in styles}) == len(styles)
    assert all(style.description.strip() for style in styles)


def test_registry_default_and_lookup_behavior() -> None:
    assert DEFAULT_STYLE_ID == "auto"
    assert get_style("documentary") is not None
    assert get_style("missing") is None
    assert is_valid_style_id("natural_travel")
    assert not is_valid_style_id("missing")


def test_registry_results_cannot_mutate_underlying_metadata() -> None:
    styles = list_styles()

    with pytest.raises(FrozenInstanceError):
        styles[0].display_name = "Changed"  # type: ignore[misc]

    assert list_styles()[0].display_name == "Natural Travel"


@pytest.mark.parametrize("style_id,display_name", EXPECTED_STYLES)
def test_loaded_profiles_use_registry_display_metadata(
    style_id: str,
    display_name: str,
) -> None:
    registry_style = get_style(style_id)
    loaded_profile = StyleProfileLoader().get_profile(style_id)

    assert registry_style is not None
    assert loaded_profile.display_name == display_name
    assert loaded_profile.display_name == registry_style.display_name
    assert loaded_profile.description == registry_style.description


def test_json_metadata_cannot_override_registered_metadata(
    tmp_path: Path,
) -> None:
    packaged_loader = StyleProfileLoader()
    source_path = packaged_loader.data_dir / "natural_travel.json"
    raw_profile = json.loads(source_path.read_text(encoding="utf-8"))
    raw_profile["display_name"] = "Overridden name"
    raw_profile["description"] = "Overridden description"
    profile_path = tmp_path / "natural_travel.json"
    profile_path.write_text(json.dumps(raw_profile), encoding="utf-8")

    loader = StyleProfileLoader(tmp_path)
    loaded = loader.get_profile("natural_travel")

    assert loaded.display_name == "Natural Travel"
    assert loaded.description == get_style("natural_travel").description

    raw_profile["display_name"] = "Changed after cache"
    raw_profile["description"] = "Changed after cache"
    profile_path.write_text(json.dumps(raw_profile), encoding="utf-8")
    cached = loader.get_profile("natural_travel")

    assert cached.display_name == "Natural Travel"
    assert cached.description == get_style("natural_travel").description
