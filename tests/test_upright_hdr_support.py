from pydantic import ValidationError
import pytest

from autodevelop.models import (
    DynamicRangeAnalysis,
    GeometryAnalysis,
    HdrRecommendation,
    ProcessingOptions,
    TechnicalAnalysis,
    UprightMode,
    UprightRecommendation,
)
from autodevelop.learning.comparison import compare_feedback_settings
from autodevelop.learning.schemas import DevelopModeState
from autodevelop.profiles import StyleProfileLoader
from autodevelop.validation import SafetyValidator
from autodevelop.validation import policies


def _hdr_analysis() -> TechnicalAnalysis:
    return TechnicalAnalysis(
        scene_type="landscape",
        lighting="sunset",
        dynamic_range="high",
        noise_level="low",
        highlight_recoverability="high",
        shadow_recoverability="moderate",
        dynamic_range_analysis=DynamicRangeAnalysis(
            dynamic_range="high",
            highlight_pressure="high",
            shadow_pressure="moderate",
            hdr_candidate=True,
            hdr_confidence=0.9,
        ),
    )


def test_verified_upright_modes_serialize_to_wire_values() -> None:
    assert [mode.value for mode in UprightMode] == [
        "off",
        "auto",
        "full",
        "level",
        "vertical",
    ]


def test_unknown_upright_mode_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UprightRecommendation(
            recommended=True,
            mode="guided",
            confidence=1,
        )


def test_semantic_evidence_defaults_are_safe_and_inactive() -> None:
    analysis = TechnicalAnalysis()

    assert analysis.geometry_analysis == GeometryAnalysis()
    assert analysis.dynamic_range_analysis == DynamicRangeAnalysis()
    assert analysis.geometry_analysis.upright_candidate_mode is UprightMode.OFF
    assert analysis.dynamic_range_analysis.hdr_candidate is False


@pytest.mark.parametrize(
    ("profile_id", "mode", "confidence", "expected_code"),
    [
        ("documentary", UprightMode.VERTICAL, 0.99, policies.UPRIGHT_MODE_NOT_ALLOWED),
        ("natural_travel", UprightMode.AUTO, 0.70, policies.UPRIGHT_CONFIDENCE_TOO_LOW),
    ],
)
def test_upright_profile_policy_rejects_unsafe_recommendations(
    profile_id: str,
    mode: UprightMode,
    confidence: float,
    expected_code: str,
) -> None:
    profile = StyleProfileLoader().get_profile(profile_id)
    result = SafetyValidator().validate(
        settings=None,
        crop=None,
        denoise=None,
        profile=profile,
        upright=UprightRecommendation(
            recommended=True,
            mode=mode,
            confidence=confidence,
        ),
    )

    assert result.upright == UprightRecommendation(recommended=False)
    assert result.issues[0].code == expected_code


def test_upright_allowed_mode_above_threshold_is_preserved() -> None:
    recommendation = UprightRecommendation(
        recommended=True,
        mode=UprightMode.VERTICAL,
        confidence=0.9,
        reason="Reliable converging verticals.",
    )
    result = SafetyValidator().validate(
        settings=None,
        crop=None,
        denoise=None,
        profile=StyleProfileLoader().get_profile("architecture"),
        upright=recommendation,
    )

    assert result.upright == recommendation
    assert result.rejected_fields == []


def test_hdr_allowed_above_threshold_with_scene_evidence_is_preserved() -> None:
    recommendation = HdrRecommendation(
        recommended=True,
        enabled=True,
        confidence=0.9,
        reason="High scene range with recoverable extremes.",
    )
    result = SafetyValidator().validate(
        settings=None,
        crop=None,
        denoise=None,
        profile=StyleProfileLoader().get_profile("landscape_impact"),
        enable_hdr=recommendation,
        analysis=_hdr_analysis(),
        options=ProcessingOptions(
            hdr_edit_supported=True,
            hdr_workflow="hdr",
        ),
    )

    assert result.enable_hdr == recommendation
    assert result.rejected_fields == []


def test_hdr_validation_is_identical_across_profiles() -> None:
    validator = SafetyValidator()
    recommendation = HdrRecommendation(
        recommended=True,
        enabled=True,
        confidence=0.8,
    )
    disallowed = validator.validate(
        settings=None,
        crop=None,
        denoise=None,
        profile=StyleProfileLoader().get_profile("documentary"),
        enable_hdr=recommendation,
        analysis=_hdr_analysis(),
        options=ProcessingOptions(
            hdr_edit_supported=True,
            hdr_workflow="hdr",
        ),
    )
    low_confidence = validator.validate(
        settings=None,
        crop=None,
        denoise=None,
        profile=StyleProfileLoader().get_profile("stock_neutral"),
        enable_hdr=recommendation,
        analysis=_hdr_analysis(),
        options=ProcessingOptions(
            hdr_edit_supported=True,
            hdr_workflow="hdr",
        ),
    )

    assert disallowed.enable_hdr == recommendation
    assert disallowed.issues == []
    assert low_confidence.enable_hdr == recommendation
    assert low_confidence.issues == []


def test_inactive_hdr_enabled_state_is_normalized_off() -> None:
    result = SafetyValidator().validate(
        settings=None,
        crop=None,
        denoise=None,
        profile=StyleProfileLoader().get_profile("landscape_impact"),
        enable_hdr=HdrRecommendation(
            recommended=False,
            enabled=True,
            confidence=0.9,
        ),
    )

    assert result.enable_hdr == HdrRecommendation(
        recommended=False,
        confidence=0.9,
    )
    assert result.issues[0].code == policies.HDR_INACTIVE_NORMALIZED


@pytest.mark.parametrize(
    ("final_modes", "upright_changed", "hdr_changed"),
    [
        (
            DevelopModeState(upright="vertical", hdr_enabled=False),
            True,
            False,
        ),
        (
            DevelopModeState(upright="off", hdr_enabled=True),
            False,
            True,
        ),
    ],
)
def test_mode_only_feedback_is_significant(
    final_modes: DevelopModeState,
    upright_changed: bool,
    hdr_changed: bool,
) -> None:
    comparison = compare_feedback_settings(
        {"Exposure2012": 0.0},
        {"Exposure2012": 0.0},
        applied_modes=DevelopModeState(
            upright="off",
            hdr_enabled=False,
        ),
        final_modes=final_modes,
    )

    assert comparison.significant_delta.model_dump(exclude_none=True) == {}
    assert comparison.upright_changed is upright_changed
    assert comparison.hdr_changed is hdr_changed
    assert comparison.accepted_without_change is False
