import pytest

from autodevelop.profiles import SceneSignals, select_style


@pytest.mark.parametrize(
    ("signals", "expected"),
    [
        (
            {"scene_category": "scenic_travel", "primary_subject_type": "landscape"},
            "natural_travel",
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
