import pytest

from autodevelop.profiles import SceneSignals, select_style


@pytest.mark.parametrize(
    ("signals", "expected"),
    [
        (
            {"scene_category": "scenic_travel", "primary_subject_type": "landscape"},
            "landscape_impact",
        ),
        (
            {"scene_category": "architecture", "architecture_dominant": True},
            "architecture",
        ),
        (
            {"scene_category": "portrait", "portrait_dominant": True},
            "portrait",
        ),
        (
            {"scene_category": "documentary", "documentary_context": True},
            "documentary",
        ),
        ({"scene_category": "night", "night_scene": True}, "night"),
        ({"scene_category": "unknown"}, "stock_neutral"),
    ],
)
def test_auto_style_selection(signals: dict[str, object], expected: str) -> None:
    result = select_style(
        "auto",
        SceneSignals.model_validate(
            {
                "primary_subject_type": "unknown",
                "confidence": 0.8,
                **signals,
            }
        ),
    )

    assert result.mode == "auto"
    assert result.effective_style_id == expected


def test_dramatic_scenic_scene_selects_landscape_impact() -> None:
    result = select_style(
        "auto",
        SceneSignals(
            primary_subject_type="landscape",
            scene_category="scenic_travel",
            lighting_type="golden_hour",
            dynamic_range="high",
            confidence=0.9,
        ),
    )

    assert result.effective_style_id == "landscape_impact"
    assert result.editing_intensity == "strong"


@pytest.mark.parametrize(
    ("signals", "expected_profile", "expected_intensity"),
    [
        pytest.param(
            {
                "primary_subject_type": "landscape",
                "scene_category": "scenic_travel",
                "lighting_type": "overcast",
                "dynamic_range": "high",
                "color_character": "muted",
                "confidence": 0.9,
            },
            "landscape_impact",
            "strong",
            id="overcast-wetland-and-mountains",
        ),
        pytest.param(
            {
                "primary_subject_type": "landscape",
                "scene_category": "scenic_travel",
                "lighting_type": "golden_hour",
                "dynamic_range": "high",
                "confidence": 0.9,
            },
            "landscape_impact",
            "strong",
            id="golden-hour-mountain-vista",
        ),
        pytest.param(
            {
                "primary_subject_type": "landscape",
                "scene_category": "scenic_travel",
                "lighting_type": "daylight",
                "dynamic_range": "very_high",
                "color_character": "vivid",
                "confidence": 0.9,
            },
            "landscape_impact",
            "strong",
            id="vivid-waterfall-landscape",
        ),
        pytest.param(
            {
                "primary_subject_type": "nature",
                "scene_category": "scenic_travel",
                "lighting_type": "overcast",
                "dynamic_range": "moderate",
                "color_character": "muted",
                "confidence": 0.85,
            },
            "landscape_impact",
            "strong",
            id="foggy-muted-forest",
        ),
        pytest.param(
            {
                "primary_subject_type": "person",
                "scene_category": "scenic_travel",
                "people_present": True,
                "confidence": 0.92,
            },
            "natural_travel",
            "strong",
            id="tourist-in-front-of-mountains",
        ),
        pytest.param(
            {
                "primary_subject_type": "street",
                "scene_category": "scenic_travel",
                "confidence": 0.9,
            },
            "natural_travel",
            "strong",
            id="scenic-village-street",
        ),
        pytest.param(
            {
                "primary_subject_type": "architecture",
                "scene_category": "scenic_travel",
                "architecture_dominant": True,
                "confidence": 0.9,
            },
            "architecture",
            "strong",
            id="temple-with-landscape-background",
        ),
        pytest.param(
            {
                "primary_subject_type": "landscape",
                "scene_category": "scenic_travel",
                "confidence": 0.64,
            },
            "natural_travel",
            "strong",
            id="low-confidence-landscape",
        ),
        pytest.param(
            {
                "primary_subject_type": "landscape",
                "scene_category": "scenic_travel",
                "night_scene": True,
                "confidence": 0.9,
            },
            "night",
            "strong",
            id="night-mountain-scene",
        ),
        pytest.param(
            {
                "primary_subject_type": "person",
                "scene_category": "scenic_travel",
                "portrait_dominant": True,
                "confidence": 0.9,
            },
            "portrait",
            "moderate",
            id="environmental-portrait-outdoors",
        ),
    ],
)
def test_auto_landscape_profile_and_intensity_are_selected_independently(
    signals: dict[str, object],
    expected_profile: str,
    expected_intensity: str,
) -> None:
    result = select_style("auto", SceneSignals.model_validate(signals))

    assert result.effective_style_id == expected_profile
    assert result.editing_intensity == expected_intensity


def test_dramatic_overcast_landscape_is_strong() -> None:
    result = select_style(
        "auto",
        SceneSignals(
            primary_subject_type="landscape",
            scene_category="scenic_travel",
            lighting_type="dramatic_overcast",
            dynamic_range="high",
            color_character="muted",
            confidence=0.9,
        ),
    )

    assert result.effective_style_id == "landscape_impact"
    assert result.reason == "Dramatic scenic landscape"
    assert result.editing_intensity == "strong"


@pytest.mark.parametrize(
    "style_id",
    [
        "natural_travel",
        "landscape_impact",
        "architecture",
        "stock_neutral",
        "portrait",
        "night",
        "documentary",
    ],
)
def test_manual_style_override_is_exact(style_id: str) -> None:
    scene = SceneSignals(
        primary_subject_type="nightscape",
        scene_category="night",
        night_scene=True,
        confidence=0.9,
    )

    result = select_style(style_id, scene)

    assert result.mode == "manual"
    assert result.effective_style_id == style_id


@pytest.mark.parametrize(
    ("style_id", "expected_intensity"),
    [
        ("natural_travel", "strong"),
        ("landscape_impact", "strong"),
        ("architecture", "strong"),
        ("stock_neutral", "strong"),
        ("portrait", "moderate"),
        ("night", "strong"),
        ("documentary", "strong"),
    ],
)
def test_manual_intensity_is_moderate_only_for_portrait(
    style_id: str,
    expected_intensity: str,
) -> None:
    result = select_style(
        style_id,
        SceneSignals(
            primary_subject_type="unknown",
            scene_category="unknown",
            confidence=0.8,
        ),
    )

    assert result.editing_intensity == expected_intensity


def test_unsupported_manual_style_is_rejected() -> None:
    with pytest.raises(ValueError):
        select_style(
            "unsupported",
            SceneSignals(
                primary_subject_type="unknown",
                scene_category="unknown",
                confidence=0.0,
            ),
        )
