from autodevelop.geometry_decision import decide_geometry
from autodevelop.models import (
    GeometryAnalysis,
    LevelingRecommendation,
    TechnicalAnalysis,
    UprightMode,
    UprightRecommendation,
)
from autodevelop.profiles import StyleProfileLoader


def _inactive_leveling() -> LevelingRecommendation:
    return LevelingRecommendation(recommended=False, angle=0, mode="none")


def test_non_portrait_uses_local_lightroom_level_fallback() -> None:
    profile = StyleProfileLoader().get_profile("documentary")

    decision = decide_geometry(
        leveling=_inactive_leveling(),
        upright=UprightRecommendation(recommended=False),
        analysis=TechnicalAnalysis(scene_type="documentary"),
        profile=profile,
    )

    assert decision.fallback_applied is True
    assert decision.basis == "lightroom_level_fallback"
    assert decision.upright is not None
    assert decision.upright.recommended is True
    assert decision.upright.mode == UprightMode.LEVEL
    assert decision.upright.confidence == profile.upright_policy.minimum_confidence


def test_architecture_uses_local_lightroom_level_fallback() -> None:
    profile = StyleProfileLoader().get_profile("architecture")

    decision = decide_geometry(
        leveling=_inactive_leveling(),
        upright=UprightRecommendation(recommended=False),
        analysis=TechnicalAnalysis(scene_type="architecture"),
        profile=profile,
    )

    assert decision.fallback_applied is True
    assert decision.upright is not None
    assert decision.upright.mode == UprightMode.LEVEL


def test_perspective_evidence_still_uses_level_only_fallback() -> None:
    profile = StyleProfileLoader().get_profile("natural_travel")
    analysis = TechnicalAnalysis(
        scene_type="travel",
        geometry_analysis=GeometryAnalysis(
            reliable_vertical_lines=True,
            perspective_convergence="moderate",
        ),
    )

    decision = decide_geometry(
        leveling=_inactive_leveling(),
        upright=None,
        analysis=analysis,
        profile=profile,
    )

    assert decision.upright is not None
    assert decision.upright.mode == UprightMode.LEVEL


def test_portrait_is_exempt_from_forced_geometry_fallback() -> None:
    profile = StyleProfileLoader().get_profile("portrait")
    original = UprightRecommendation(recommended=False)

    decision = decide_geometry(
        leveling=_inactive_leveling(),
        upright=original,
        analysis=TechnicalAnalysis(scene_type="portrait"),
        profile=profile,
    )

    assert decision.fallback_applied is False
    assert decision.basis == "portrait_exempt"
    assert decision.upright is original


def test_valid_model_geometry_is_preserved() -> None:
    profile = StyleProfileLoader().get_profile("natural_travel")
    original = UprightRecommendation(
        recommended=True,
        mode=UprightMode.LEVEL,
        confidence=0.9,
    )

    decision = decide_geometry(
        leveling=_inactive_leveling(),
        upright=original,
        analysis=TechnicalAnalysis(),
        profile=profile,
    )

    assert decision.fallback_applied is False
    assert decision.basis == "model_upright"
    assert decision.upright == original


def test_model_auto_is_preserved_for_existing_validator_policy() -> None:
    profile = StyleProfileLoader().get_profile("documentary")

    decision = decide_geometry(
        leveling=_inactive_leveling(),
        upright=UprightRecommendation(
            recommended=True,
            mode=UprightMode.AUTO,
            confidence=0.95,
        ),
        analysis=TechnicalAnalysis(scene_type="documentary"),
        profile=profile,
    )

    assert decision.fallback_applied is False
    assert decision.basis == "model_upright"
    assert decision.upright is not None
    assert decision.upright.mode == UprightMode.AUTO
