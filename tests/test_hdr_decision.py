import pytest

from autodevelop.hdr_decision import decide_hdr
from autodevelop.models import (
    DynamicRangeAnalysis,
    HdrRecommendation,
    LearningDiagnostics,
    ProcessingOptions,
    TechnicalAnalysis,
)


def _learning(rate: float, count: int) -> LearningDiagnostics:
    return LearningDiagnostics(
        enabled=True,
        personalization_applied=True,
        usable_sample_count=count,
        retrieved_sample_count=count,
        minimum_sample_count=3,
        hdr_personalization_applied=True,
        hdr_learning_enable_rate=rate,
        hdr_learning_sample_count=count,
    )


def _analysis(
    *,
    dynamic_range: str = "high",
    highlight_pressure: str = "high",
    shadow_pressure: str = "high",
    scene_type: str = "landscape",
    **cues: bool,
) -> TechnicalAnalysis:
    return TechnicalAnalysis(
        scene_type=scene_type,
        lighting="mixed sunlight and shade",
        dynamic_range=dynamic_range,
        noise_level="low",
        highlight_recoverability="high",
        shadow_recoverability="high",
        dynamic_range_analysis=DynamicRangeAnalysis(
            dynamic_range=dynamic_range,
            highlight_pressure=highlight_pressure,
            shadow_pressure=shadow_pressure,
            hdr_candidate=dynamic_range in {"moderate", "high", "very_high"},
            hdr_confidence=0.82,
            **cues,
        ),
    )


def _decide(
    analysis: TechnicalAnalysis,
    *,
    raw: HdrRecommendation | None = None,
    learning: LearningDiagnostics | None = None,
    preference: str = "prefer_hdr",
):
    return decide_hdr(
        raw or HdrRecommendation(recommended=False, confidence=0.9),
        filename="DSC_7516.NEF",
        analysis=analysis,
        options=ProcessingOptions(
            hdr_edit_supported=True,
            hdr_workflow="hdr",
            hdr_preference=preference,
        ),
        learning=learning,
        minimum_samples=3,
    )


def test_bright_sky_dark_foreground_and_learning_enable_hdr() -> None:
    recommendation, diagnostics = _decide(
        _analysis(bright_sky_dark_foreground=True, backlit=True),
        learning=_learning(0.91, 22),
    )

    assert recommendation.enabled is True
    assert diagnostics.hdr_learning_applied is True
    assert diagnostics.hdr_evidence_score >= 0.42


def test_moderate_range_with_twenty_two_hdr_samples_can_enable_hdr() -> None:
    recommendation, diagnostics = _decide(
        _analysis(
            dynamic_range="moderate",
            highlight_pressure="moderate",
            shadow_pressure="moderate",
        ),
        learning=_learning(0.95, 22),
    )

    assert recommendation.enabled is True
    assert diagnostics.hdr_learning_sample_count == 22


def test_balanced_daylight_without_pressure_remains_off() -> None:
    raw = HdrRecommendation(recommended=False, confidence=0.64)
    recommendation, diagnostics = _decide(
        _analysis(
            dynamic_range="moderate",
            highlight_pressure="none",
            shadow_pressure="none",
        ),
        raw=raw,
        learning=None,
        preference="balanced",
    )

    assert recommendation.enabled is False
    assert recommendation.confidence == 0.64
    assert diagnostics.raw_hdr_confidence == 0.64
    assert diagnostics.hdr_rejection_reason == "insufficient_evidence"


def test_subject_profile_cannot_veto_strong_documentary_scene_evidence() -> None:
    recommendation, diagnostics = _decide(
        _analysis(bright_sky_dark_foreground=True),
        learning=_learning(1.0, 22),
    )

    assert recommendation.enabled is True
    assert diagnostics.hdr_rejection_reason is None


def test_subject_category_cannot_veto_strong_portrait_scene_evidence() -> None:
    analysis = _analysis(scene_type="portrait")
    analysis = analysis.model_copy(
        update={"lighting": "ordinary soft studio light"}
    )
    recommendation, diagnostics = _decide(
        analysis,
        learning=_learning(1.0, 22),
    )

    assert recommendation.enabled is True
    assert diagnostics.hdr_rejection_reason is None


def test_learning_never_enables_hdr_without_visual_evidence() -> None:
    recommendation, diagnostics = _decide(
        _analysis(
            dynamic_range="low",
            highlight_pressure="none",
            shadow_pressure="none",
        ),
        learning=_learning(1.0, 22),
    )

    assert recommendation.enabled is False
    assert diagnostics.visual_evidence_score == 0
    assert diagnostics.hdr_evidence_score == 0
    assert diagnostics.hdr_rejection_reason == "insufficient_dynamic_range"


def test_learned_preference_enables_repeated_moderate_scene_case() -> None:
    recommendation, diagnostics = _decide(
        _analysis(
            dynamic_range="moderate",
            highlight_pressure="none",
            shadow_pressure="none",
        ),
        raw=HdrRecommendation(recommended=False, confidence=0.20),
        learning=_learning(1.0, 4),
        preference="prefer_hdr",
    )

    assert recommendation.enabled is True
    assert recommendation.confidence == 0.744
    assert diagnostics.base_scene_evidence_score == 0.18
    assert diagnostics.learning_bonus == 0.10
    assert diagnostics.user_preference_bonus == 0.08
    assert diagnostics.combined_evidence_score == pytest.approx(0.36)
    assert diagnostics.decision_basis == "learned_preference"
    assert diagnostics.decision_confidence == 0.744
    assert diagnostics.raw_hdr_confidence == 0.20
    assert diagnostics.contraindications == []


def test_learned_preference_path_requires_prefer_hdr() -> None:
    recommendation, diagnostics = _decide(
        _analysis(
            dynamic_range="moderate",
            highlight_pressure="none",
            shadow_pressure="none",
        ),
        raw=HdrRecommendation(recommended=False, confidence=0.20),
        learning=_learning(1.0, 4),
        preference="balanced",
    )

    assert recommendation.enabled is False
    assert diagnostics.decision_basis == "disabled"
    assert diagnostics.hdr_rejection_reason == "insufficient_evidence"


def test_learned_preference_path_requires_minimum_samples() -> None:
    recommendation, diagnostics = _decide(
        _analysis(
            dynamic_range="moderate",
            highlight_pressure="none",
            shadow_pressure="none",
        ),
        raw=HdrRecommendation(recommended=False, confidence=0.20),
        learning=_learning(1.0, 2),
        preference="prefer_hdr",
    )

    assert recommendation.enabled is False
    assert diagnostics.hdr_learning_applied is False
    assert diagnostics.decision_basis == "disabled"


def test_model_path_uses_global_confidence_threshold() -> None:
    recommendation, diagnostics = _decide(
        _analysis(
            dynamic_range="moderate",
            highlight_pressure="moderate",
            shadow_pressure="moderate",
        ),
        raw=HdrRecommendation(recommended=True, confidence=0.78),
        preference="prefer_hdr",
    )

    assert recommendation.enabled is True
    assert diagnostics.decision_basis == "model"
    assert diagnostics.decision_confidence == 0.78


def test_prefer_hdr_does_not_lower_model_confidence_threshold() -> None:
    recommendation, diagnostics = _decide(
        _analysis(
            dynamic_range="moderate",
            highlight_pressure="moderate",
            shadow_pressure="moderate",
        ),
        raw=HdrRecommendation(recommended=True, confidence=0.64),
        preference="prefer_hdr",
    )

    assert recommendation.enabled is False
    assert diagnostics.hdr_rejection_reason == "confidence_below_threshold"


def test_objective_path_does_not_require_model_recommendation() -> None:
    recommendation, diagnostics = _decide(
        _analysis(
            dynamic_range="high",
            highlight_pressure="high",
            shadow_pressure="high",
        ),
        raw=HdrRecommendation(recommended=False, confidence=0.20),
        preference="balanced",
    )

    assert recommendation.enabled is True
    assert diagnostics.base_scene_evidence_score == 0.75
    assert diagnostics.decision_basis == "objective_evidence"
    assert diagnostics.decision_confidence == 0.75


def test_inconsistent_low_range_candidate_is_flagged_and_rejected() -> None:
    analysis = _analysis(
        dynamic_range="low",
        highlight_pressure="none",
        shadow_pressure="none",
    )
    analysis = analysis.model_copy(
        update={
            "dynamic_range_analysis": (
                analysis.dynamic_range_analysis.model_copy(
                    update={
                        "hdr_candidate": True,
                        "hdr_confidence": 0.20,
                    }
                )
            )
        }
    )

    recommendation, diagnostics = _decide(
        analysis,
        raw=HdrRecommendation(recommended=True, confidence=0.90),
        learning=_learning(1.0, 20),
    )

    assert recommendation.enabled is False
    assert diagnostics.scene_hdr_inconsistent is True
    assert "insufficient_dynamic_range" in diagnostics.contraindications
    assert diagnostics.hdr_rejection_reason == "insufficient_dynamic_range"


def test_scene_candidate_is_required_even_with_model_confidence() -> None:
    analysis = _analysis(
        dynamic_range="high",
        highlight_pressure="high",
        shadow_pressure="high",
    )
    analysis = analysis.model_copy(
        update={
            "dynamic_range_analysis": (
                analysis.dynamic_range_analysis.model_copy(
                    update={"hdr_candidate": False}
                )
            )
        }
    )

    recommendation, diagnostics = _decide(
        analysis,
        raw=HdrRecommendation(recommended=True, confidence=0.95),
        preference="balanced",
    )

    assert recommendation.enabled is False
    assert diagnostics.decision_basis == "disabled"
