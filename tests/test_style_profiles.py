import json
import math
from pathlib import Path

import pytest

from autodevelop.profiles import (
    ProfileNotFoundError,
    ProfileValidationError,
    StyleProfileLoader,
)

PROFILE_IDS = [
    "architecture",
    "documentary",
    "landscape_impact",
    "natural_travel",
    "night",
    "portrait",
    "stock_neutral",
]


def _profile_data(profile_id: str = "test_profile") -> dict[str, object]:
    return {
        "id": profile_id,
        "display_name": "Test Profile",
        "description": "Profile data used by loader tests.",
        "version": "1.0",
        "editing_goals": ["Produce a balanced edit"],
        "cautions": ["Avoid excessive processing"],
        "slider_ranges": {
            "Exposure2012": {
                "min": -1.0,
                "max": 1.0,
                "preferred": 0.0,
            }
        },
        "crop_policy": {
            "allow_crop": True,
            "allow_leveling": True,
            "max_edge_crop": 0.1,
            "minimum_retained_area": 0.75,
            "maximum_absolute_angle": 4.0,
            "minimum_confidence": 0.6,
            "require_confidence": False,
            "preserve_aspect_ratio": True,
        },
        "denoise_policy": {
            "allow_denoise": True,
            "minimum_iso": 800,
            "minimum_amount": 0.0,
            "maximum_amount": 35.0,
            "minimum_confidence": 0.6,
            "preserve_detail": True,
        },
    }


def _write_profile(
    data_dir: Path,
    profile_id: str,
    data: dict[str, object],
) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f"{profile_id}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_all_seven_packaged_profiles_load_successfully() -> None:
    profiles = StyleProfileLoader().list_profiles()

    assert [profile.id for profile in profiles] == PROFILE_IDS
    assert all(profile.version == "1.0" for profile in profiles)
    assert all(profile.slider_ranges for profile in profiles)


def test_documentary_profile_has_conservative_supported_constraints() -> None:
    profile = StyleProfileLoader().get_profile("documentary")

    assert profile.id == "documentary"
    assert profile.display_name == "Documentary"
    assert profile.slider_ranges["Dehaze"].max <= 10.0
    assert profile.slider_ranges["Saturation"].max <= 8.0
    assert profile.slider_ranges["Texture"].max <= 16.0
    assert profile.crop_policy.max_edge_crop <= 0.08
    assert profile.crop_policy.minimum_retained_area >= 0.88
    assert profile.denoise_policy.maximum_amount <= 30.0


def test_documentary_limits_stay_within_existing_bundled_safety_envelope() -> None:
    loader = StyleProfileLoader()
    documentary = loader.get_profile("documentary")
    established = [
        loader.get_profile(profile_id)
        for profile_id in PROFILE_IDS
        if profile_id != "documentary"
    ]

    for name, documentary_range in documentary.slider_ranges.items():
        established_ranges = [
            profile.slider_ranges[name]
            for profile in established
            if name in profile.slider_ranges
        ]
        assert established_ranges
        assert documentary_range.min >= min(
            slider_range.min for slider_range in established_ranges
        )
        assert documentary_range.max <= max(
            slider_range.max for slider_range in established_ranges
        )

    assert documentary.crop_policy.max_edge_crop <= max(
        profile.crop_policy.max_edge_crop for profile in established
    )
    assert documentary.crop_policy.minimum_retained_area >= min(
        profile.crop_policy.minimum_retained_area for profile in established
    )
    assert documentary.crop_policy.maximum_absolute_angle <= max(
        profile.crop_policy.maximum_absolute_angle for profile in established
    )
    assert documentary.denoise_policy.maximum_amount <= max(
        profile.denoise_policy.maximum_amount for profile in established
    )


def test_list_profiles_has_deterministic_alphabetical_order() -> None:
    loader = StyleProfileLoader()

    first = [profile.id for profile in loader.list_profiles()]
    second = [profile.id for profile in loader.list_profiles()]

    assert first == sorted(first)
    assert second == first


def test_missing_profile_raises_profile_not_found() -> None:
    with pytest.raises(ProfileNotFoundError, match="does_not_exist"):
        StyleProfileLoader().get_profile("does_not_exist")


def test_malformed_json_reports_file_context(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text('{"id": "broken",', encoding="utf-8")

    with pytest.raises(ProfileValidationError) as exc_info:
        StyleProfileLoader(tmp_path).get_profile("broken")

    message = str(exc_info.value)
    assert str(path) in message
    assert "malformed JSON" in message
    assert "line" in message


def test_filename_and_profile_id_must_match(tmp_path: Path) -> None:
    path = _write_profile(
        tmp_path,
        "filename_id",
        _profile_data("different_id"),
    )

    with pytest.raises(ProfileValidationError) as exc_info:
        StyleProfileLoader(tmp_path).get_profile("filename_id")

    message = str(exc_info.value)
    assert str(path) in message
    assert "expected 'filename_id', found 'different_id'" in message


def test_unknown_profile_fields_are_rejected(tmp_path: Path) -> None:
    data = _profile_data()
    data["unexpected"] = True
    path = _write_profile(tmp_path, "test_profile", data)

    with pytest.raises(ProfileValidationError) as exc_info:
        StyleProfileLoader(tmp_path).get_profile("test_profile")

    message = str(exc_info.value)
    assert str(path) in message
    assert "unexpected" in message
    assert "Extra inputs are not permitted" in message


def test_invalid_slider_range_is_rejected(tmp_path: Path) -> None:
    data = _profile_data()
    slider_ranges = data["slider_ranges"]
    assert isinstance(slider_ranges, dict)
    slider_ranges["Exposure2012"] = {
        "min": 1.0,
        "max": -1.0,
        "preferred": 0.0,
    }
    path = _write_profile(tmp_path, "test_profile", data)

    with pytest.raises(ProfileValidationError) as exc_info:
        StyleProfileLoader(tmp_path).get_profile("test_profile")

    message = str(exc_info.value)
    assert str(path) in message
    assert "slider_ranges.Exposure2012" in message
    assert "min <= max" in message


def test_preferred_value_outside_slider_range_is_rejected(
    tmp_path: Path,
) -> None:
    data = _profile_data()
    slider_ranges = data["slider_ranges"]
    assert isinstance(slider_ranges, dict)
    slider_ranges["Exposure2012"] = {
        "min": -1.0,
        "max": 1.0,
        "preferred": 2.0,
    }
    path = _write_profile(tmp_path, "test_profile", data)

    with pytest.raises(ProfileValidationError) as exc_info:
        StyleProfileLoader(tmp_path).get_profile("test_profile")

    message = str(exc_info.value)
    assert str(path) in message
    assert "slider_ranges.Exposure2012" in message
    assert "preferred value" in message


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_profile_numbers_are_rejected(
    tmp_path: Path,
    value: float,
) -> None:
    data = _profile_data()
    slider_ranges = data["slider_ranges"]
    assert isinstance(slider_ranges, dict)
    slider_ranges["Exposure2012"] = {
        "min": value,
        "max": 1.0,
        "preferred": 0.0,
    }
    path = _write_profile(tmp_path, "test_profile", data)

    with pytest.raises(ProfileValidationError) as exc_info:
        StyleProfileLoader(tmp_path).get_profile("test_profile")

    message = str(exc_info.value)
    assert str(path) in message
    assert "slider_ranges.Exposure2012.min" in message


def test_successfully_loaded_profile_is_cached(tmp_path: Path) -> None:
    original = _profile_data()
    _write_profile(tmp_path, "test_profile", original)
    loader = StyleProfileLoader(tmp_path)

    first = loader.get_profile("test_profile")
    changed = _profile_data()
    changed["description"] = "Changed on disk after caching."
    _write_profile(tmp_path, "test_profile", changed)
    second = loader.get_profile("test_profile")

    assert first.description == "Profile data used by loader tests."
    assert second.description == first.description


def test_reload_profiles_replaces_cached_values(tmp_path: Path) -> None:
    original = _profile_data()
    _write_profile(tmp_path, "test_profile", original)
    loader = StyleProfileLoader(tmp_path)
    loader.get_profile("test_profile")

    changed = _profile_data()
    changed["description"] = "Reloaded description."
    _write_profile(tmp_path, "test_profile", changed)
    reloaded = loader.reload_profiles()

    assert [profile.description for profile in reloaded] == [
        "Reloaded description."
    ]
    assert loader.get_profile("test_profile").description == "Reloaded description."


def test_mutating_returned_profile_does_not_corrupt_cache(
    tmp_path: Path,
) -> None:
    _write_profile(tmp_path, "test_profile", _profile_data())
    loader = StyleProfileLoader(tmp_path)
    first = loader.get_profile("test_profile")

    first.editing_goals.append("Caller mutation")
    first.slider_ranges["Exposure2012"].min = -999.0
    first.slider_ranges.clear()
    second = loader.get_profile("test_profile")

    assert second.editing_goals == ["Produce a balanced edit"]
    assert second.slider_ranges["Exposure2012"].min == -1.0


def test_loading_is_independent_of_current_working_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    profile = StyleProfileLoader().get_profile("natural_travel")

    assert profile.id == "natural_travel"
    assert profile.display_name == "Natural Travel"
