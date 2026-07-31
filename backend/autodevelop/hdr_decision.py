"""Deterministic evidence scoring and preference-aware HDR decisions."""

from pathlib import Path

from autodevelop.models import (
    HdrDecisionDiagnostics,
    HdrRecommendation,
    LearningDiagnostics,
    ProcessingOptions,
    TechnicalAnalysis,
)
from autodevelop.models.common import (
    HdrDecisionBasis,
    HdrOffReason,
    HdrPreference,
)
_RAW_EXTENSIONS = frozenset(
    {
        ".3fr",
        ".arw",
        ".cr2",
        ".cr3",
        ".dng",
        ".erf",
        ".iiq",
        ".kdc",
        ".mef",
        ".mos",
        ".mrw",
        ".nef",
        ".nrw",
        ".orf",
        ".pef",
        ".raf",
        ".raw",
        ".rw2",
        ".rwl",
        ".srw",
        ".x3f",
    }
)

_MODEL_MINIMUM_CONFIDENCE = 0.65
_MODEL_MINIMUM_EVIDENCE = 0.40
_OBJECTIVE_MINIMUM_EVIDENCE = 0.65


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _dynamic_range(analysis: TechnicalAnalysis | None) -> str:
    if analysis is None:
        return "unknown"
    semantic = analysis.dynamic_range_analysis.dynamic_range
    if semantic != "unknown":
        return semantic
    return (analysis.dynamic_range or "").strip().lower()


def _has_visual_evidence(analysis: TechnicalAnalysis | None) -> bool:
    return (
        analysis is not None
        and _dynamic_range(analysis) in {"moderate", "high", "very_high"}
    )


def calculate_hdr_evidence(
    analysis: TechnicalAnalysis | None,
    learning: LearningDiagnostics | None,
    preference: HdrPreference,
    *,
    minimum_samples: int,
) -> HdrDecisionDiagnostics:
    """Calculate bounded visual, learning, and preference HDR evidence."""

    semantic = (
        analysis.dynamic_range_analysis
        if analysis is not None
        else None
    )
    dynamic_range = _dynamic_range(analysis)
    score = {
        "very_high": 0.45,
        "high": 0.35,
        "moderate": 0.18,
    }.get(dynamic_range, 0.0)
    if semantic is not None:
        score += {"high": 0.20, "moderate": 0.10}.get(
            semantic.highlight_pressure,
            0.0,
        )
        score += {"high": 0.20, "moderate": 0.10}.get(
            semantic.shadow_pressure,
            0.0,
        )
        if semantic.backlit:
            score += 0.10
        if semantic.bright_sky_dark_foreground:
            score += 0.12
        if semantic.bright_windows_dark_interior:
            score += 0.15
        if semantic.sunrise_or_sunset:
            score += 0.08
    base_scene_score = _clamp(score)

    enable_rate = (
        learning.hdr_learning_enable_rate
        if learning is not None
        else None
    )
    sample_count = (
        learning.hdr_learning_sample_count
        if learning is not None
        else 0
    )
    learning_applied = bool(
        learning is not None
        and learning.hdr_personalization_applied
        and enable_rate is not None
        and enable_rate >= 0.70
        and sample_count >= minimum_samples
    )
    learning_bonus = 0.0
    if (
        base_scene_score > 0
        and learning_applied
        and preference != "conservative"
    ):
        learning_bonus = 0.10
    preference_bonus = (
        0.08
        if base_scene_score > 0 and preference == "prefer_hdr"
        else 0.0
    )
    combined_score = _clamp(
        base_scene_score + learning_bonus + preference_bonus
    )
    scene_candidate = bool(semantic is not None and semantic.hdr_candidate)
    scene_inconsistent = bool(
        scene_candidate
        and dynamic_range not in {"moderate", "high", "very_high"}
    )

    return HdrDecisionDiagnostics(
        scene_hdr_candidate=scene_candidate,
        scene_hdr_confidence=(
            semantic.hdr_confidence if semantic is not None else 0.0
        ),
        base_scene_evidence_score=base_scene_score,
        learning_bonus=learning_bonus,
        user_preference_bonus=preference_bonus,
        combined_evidence_score=combined_score,
        scene_hdr_inconsistent=scene_inconsistent,
        visual_evidence_score=base_scene_score,
        hdr_evidence_score=combined_score,
        hdr_learning_applied=learning_applied,
        hdr_learning_enable_rate=enable_rate,
        hdr_learning_sample_count=sample_count,
    )


def _contraindications(
    *,
    filename: str,
    analysis: TechnicalAnalysis | None,
    options: ProcessingOptions,
) -> tuple[HdrOffReason, ...]:
    reasons: list[HdrOffReason] = []
    if Path(filename).suffix.lower() not in _RAW_EXTENSIONS:
        reasons.append("unsupported_source_format")
    if not options.hdr_edit_supported:
        reasons.append("caller_unsupported")
    if options.hdr_workflow == "sdr_only":
        reasons.append("sdr_only_workflow")
    if analysis is None or not _has_visual_evidence(analysis):
        reasons.append("insufficient_dynamic_range")
    if analysis is not None:
        if analysis.severe_underexposure:
            reasons.append("severe_underexposure")
        noise = (analysis.noise_level or "").strip().lower()
        if noise in {"high", "severe", "extreme"}:
            reasons.append("high_noise_risk")
    return tuple(reasons)


def decide_hdr(
    raw: HdrRecommendation | None,
    *,
    filename: str,
    analysis: TechnicalAnalysis | None,
    options: ProcessingOptions,
    learning: LearningDiagnostics | None,
    minimum_samples: int,
    evidence: HdrDecisionDiagnostics | None = None,
) -> tuple[HdrRecommendation, HdrDecisionDiagnostics]:
    """Blend model, objective evidence, and learning before safety validation."""

    preference = options.hdr_preference
    diagnostics = evidence or calculate_hdr_evidence(
        analysis,
        learning,
        preference,
        minimum_samples=minimum_samples,
    )
    raw_value = raw or HdrRecommendation(recommended=False)
    evidence_threshold = _MODEL_MINIMUM_EVIDENCE
    confidence_threshold = _MODEL_MINIMUM_CONFIDENCE
    contraindications = _contraindications(
        filename=filename,
        analysis=analysis,
        options=options,
    )
    dynamic_range = _dynamic_range(analysis)
    eligible_range = dynamic_range in {"moderate", "high", "very_high"}
    model_path = bool(
        not contraindications
        and diagnostics.scene_hdr_candidate
        and not diagnostics.scene_hdr_inconsistent
        and raw_value.recommended
        and raw_value.confidence >= confidence_threshold
        and diagnostics.combined_evidence_score >= evidence_threshold
    )
    objective_path = bool(
        not contraindications
        and diagnostics.scene_hdr_candidate
        and not diagnostics.scene_hdr_inconsistent
        and diagnostics.base_scene_evidence_score
        >= _OBJECTIVE_MINIMUM_EVIDENCE
    )
    enable_rate = diagnostics.hdr_learning_enable_rate or 0.0
    learned_path = bool(
        not contraindications
        and preference == "prefer_hdr"
        and diagnostics.hdr_learning_applied
        and diagnostics.hdr_learning_sample_count >= minimum_samples
        and enable_rate >= 0.70
        and diagnostics.base_scene_evidence_score >= 0.18
        and diagnostics.combined_evidence_score >= 0.36
        and diagnostics.scene_hdr_candidate
        and eligible_range
        and not diagnostics.scene_hdr_inconsistent
    )
    basis: HdrDecisionBasis = "disabled"
    decision_confidence: float | None = None
    reason = raw_value.reason
    if model_path:
        basis = "model"
        decision_confidence = raw_value.confidence
    elif objective_path:
        basis = "objective_evidence"
        decision_confidence = diagnostics.base_scene_evidence_score
        reason = "Strong objective scene evidence supports HDR edit mode."
    elif learned_path:
        basis = "learned_preference"
        decision_confidence = _clamp(
            0.60 * enable_rate
            + 0.40 * diagnostics.combined_evidence_score
        )
        reason = (
            "Learned HDR preference is supported by eligible scene evidence."
        )
    enabled = basis != "disabled"
    off_reason: HdrOffReason | None = None
    if not enabled:
        if contraindications:
            off_reason = contraindications[0]
        elif (
            not diagnostics.scene_hdr_candidate
            or diagnostics.scene_hdr_inconsistent
        ):
            off_reason = "insufficient_evidence"
        elif diagnostics.combined_evidence_score < evidence_threshold:
            off_reason = "insufficient_evidence"
        elif raw_value.recommended and raw_value.confidence < confidence_threshold:
            off_reason = "confidence_below_threshold"
        else:
            off_reason = "model_not_recommended"
    output_confidence = (
        decision_confidence if decision_confidence is not None
        else raw_value.confidence
    )
    proposed = raw_value.model_copy(
        update={
            "recommended": enabled,
            "enabled": enabled,
            "confidence": output_confidence,
            "reason": reason,
        },
        deep=True,
    )
    return proposed, diagnostics.model_copy(
        update={
            "decision_basis": basis,
            "decision_confidence": decision_confidence,
            "contraindications": list(contraindications),
            "raw_hdr_recommended": raw_value.recommended,
            "raw_hdr_confidence": raw_value.confidence,
            "validated_hdr_enabled": enabled,
            "validated_hdr_confidence": output_confidence,
            "hdr_rejected": bool(raw_value.recommended and not enabled),
            "hdr_rejection_reason": off_reason,
        },
        deep=True,
    )
