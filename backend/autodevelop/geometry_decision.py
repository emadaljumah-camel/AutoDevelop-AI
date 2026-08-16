"""Deterministic local fallback for Lightroom geometry correction."""

from dataclasses import dataclass

from autodevelop.models import (
    LevelingRecommendation,
    TechnicalAnalysis,
    UprightMode,
    UprightRecommendation,
)
from autodevelop.profiles import StyleProfile


@dataclass(frozen=True, slots=True)
class GeometryDecision:
    """Auditable Upright proposal passed to the safety validator."""

    upright: UprightRecommendation | None
    fallback_applied: bool
    basis: str


def _model_recommended_upright(
    recommendation: UprightRecommendation | None,
) -> bool:
    return bool(
        recommendation is not None
        and recommendation.recommended
        and recommendation.mode != UprightMode.OFF
    )


def decide_geometry(
    *,
    leveling: LevelingRecommendation | None,
    upright: UprightRecommendation | None,
    analysis: TechnicalAnalysis | None,
    profile: StyleProfile,
) -> GeometryDecision:
    """Use existing evidence and Lightroom Upright without another model call."""

    if leveling is not None and leveling.recommended:
        return GeometryDecision(upright, False, "model_leveling")

    if _model_recommended_upright(upright):
        return GeometryDecision(
            upright.model_copy(deep=True) if upright is not None else None,
            False,
            "model_upright",
        )

    if profile.id == "portrait" or (
        analysis is not None
        and (analysis.scene_type or "").strip().lower() == "portrait"
    ):
        return GeometryDecision(upright, False, "portrait_exempt")

    policy = profile.upright_policy
    if not policy.allow_upright:
        return GeometryDecision(upright, False, "profile_disallows_upright")

    if UprightMode.LEVEL not in policy.allowed_modes:
        return GeometryDecision(upright, False, "profile_has_no_fallback_mode")

    return GeometryDecision(
        UprightRecommendation(
            recommended=True,
            mode=UprightMode.LEVEL,
            confidence=policy.minimum_confidence,
            reason="Use Lightroom Upright Level for local horizon and roll analysis.",
        ),
        True,
        "lightroom_level_fallback",
    )
