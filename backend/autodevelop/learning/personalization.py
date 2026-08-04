"""Robust aggregation and bounded prompt rendering."""

from collections.abc import Iterable
from datetime import UTC, datetime
from math import exp, log

from autodevelop.learning.constants import (
    MAX_CONTEXT_CHARACTERS,
    MODE_MINIMUM_AGREEMENT,
    MODE_MINIMUM_SUPPORT,
    PERSONALIZATION_CAPS,
    SUPPORTED_SETTINGS,
)
from autodevelop.learning.models import RetrievalSample
from autodevelop.learning.schemas import PersonalizationContext
from autodevelop.models import RECOMMENDABLE_UPRIGHT_MODES, UprightMode


def _weighted_median(values: list[tuple[float, float]]) -> float:
    ordered = sorted(values, key=lambda item: item[0])
    total = sum(weight for _, weight in ordered)
    midpoint = total / 2
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= midpoint:
            return value
    return ordered[-1][0]


def _categorical_preference(
    values: list[tuple[object, float]],
) -> tuple[object | None, int]:
    if len(values) < MODE_MINIMUM_SUPPORT:
        return None, len(values)
    weights: dict[object, float] = {}
    for value, weight in values:
        weights[value] = weights.get(value, 0.0) + weight
    winner, winner_weight = sorted(
        weights.items(),
        key=lambda item: (-item[1], str(item[0])),
    )[0]
    if winner_weight / sum(weights.values()) < MODE_MINIMUM_AGREEMENT:
        return None, len(values)
    return winner, len(values)


def _sample_weight(sample: RetrievalSample) -> float:
    similarity = max(sample.similarity, 0.001)
    captured = sample.captured_at_utc
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=UTC)
    age_days = max(
        0.0,
        (datetime.now(UTC) - captured).total_seconds() / 86_400,
    )
    recency = exp(-log(2) * age_days / 180)
    return similarity * max(recency, 0.1)


def aggregate_hdr_preference(
    samples: list[RetrievalSample],
) -> tuple[bool | None, int, float | None]:
    """Aggregate HDR mode independently of the editing style profile."""

    values = [
        (sample.hdr_enabled, _sample_weight(sample))
        for sample in samples
        if sample.hdr_enabled is not None
    ]
    preferred, support = _categorical_preference(values)
    total_weight = sum(weight for _, weight in values)
    enable_rate = (
        sum(weight for enabled, weight in values if enabled) / total_weight
        if total_weight > 0
        else None
    )
    return (
        bool(preferred) if preferred is not None else None,
        support,
        enable_rate,
    )


def aggregate_preferences(
    samples: list[RetrievalSample],
    *,
    profile_id: str,
    usable_sample_count: int,
    feature_type: str | None,
) -> PersonalizationContext | None:
    if not samples:
        return None
    adjustment_names = sorted(
        {
            name
            for sample in samples
            for name in sample.significant_delta
            if name in PERSONALIZATION_CAPS
        },
        key=SUPPORTED_SETTINGS.index,
    )
    crop_names = sorted(
        {
            name
            for sample in samples
            for name in sample.crop_delta
            if name in PERSONALIZATION_CAPS
        },
        key=SUPPORTED_SETTINGS.index,
    )
    leveling_names = sorted(
        {
            name
            for sample in samples
            for name in sample.leveling_delta
            if name in PERSONALIZATION_CAPS
        },
        key=SUPPORTED_SETTINGS.index,
    )

    def aggregate(
        names: Iterable[str],
        *,
        source_name: str,
    ) -> dict[str, float]:
        result = {}
        for name in names:
            values = []
            for sample in samples:
                source = getattr(sample, source_name)
                if name in source:
                    values.append((source[name], _sample_weight(sample)))
                elif sample.accepted_without_change:
                    values.append((0.0, _sample_weight(sample)))
            if values:
                raw = _weighted_median(values)
                cap = PERSONALIZATION_CAPS[name]
                result[name] = max(-cap, min(cap, raw))
        return result

    upright, upright_support = _categorical_preference([
        (sample.upright_mode, _sample_weight(sample))
        for sample in samples
        if sample.upright_mode in RECOMMENDABLE_UPRIGHT_MODES
    ])
    hdr, hdr_support, hdr_enable_rate = aggregate_hdr_preference(samples)

    return PersonalizationContext(
        profile_id=profile_id,
        sample_count=len(samples),
        usable_sample_count=usable_sample_count,
        average_similarity=(
            sum(sample.similarity for sample in samples) / len(samples)
        ),
        preferred_adjustments=aggregate(
            adjustment_names,
            source_name="significant_delta",
        ),
        crop_adjustments=aggregate(crop_names, source_name="crop_delta"),
        leveling_adjustments=aggregate(
            leveling_names,
            source_name="leveling_delta",
        ),
        preferred_upright_mode=(
            UprightMode(upright) if upright is not None else None
        ),
        upright_support_count=upright_support,
        preferred_hdr_enabled=(
            hdr
        ),
        hdr_support_count=hdr_support,
        hdr_enable_rate=hdr_enable_rate,
        accepted_without_change_ratio=(
            sum(sample.accepted_without_change for sample in samples)
            / len(samples)
        ),
        feature_type=feature_type,
    )


def render_personalization(context: PersonalizationContext) -> str:
    preferred_upright_mode = (
        context.preferred_upright_mode
        if context.preferred_upright_mode in RECOMMENDABLE_UPRIGHT_MODES
        else None
    )
    lines = [
        "PERSONAL EDITING PREFERENCES FROM SIMILAR PHOTOS",
        "",
        "These are aggregate observations from the user's prior manual "
        "corrections. Treat them as soft preferences, not mandatory edits.",
        f"Style profile: {context.profile_id}",
        f"Similar usable examples: {context.sample_count}",
        f"Average similarity: {context.average_similarity:.2f}",
        "",
        "Observed tonal/color preferences:",
    ]
    if context.preferred_adjustments:
        for name in SUPPORTED_SETTINGS:
            if name in context.preferred_adjustments:
                value = context.preferred_adjustments[name]
                lines.append(f"- {name}: typical correction {value:+.4g}")
    else:
        lines.append("- No consistent tonal/color correction.")
    if context.crop_adjustments:
        lines.append("")
        lines.append("Observed crop preferences (separate, soft context):")
        for name in SUPPORTED_SETTINGS:
            if name in context.crop_adjustments:
                value = context.crop_adjustments[name]
                lines.append(f"- {name}: typical correction {value:+.4g}")
    if context.leveling_adjustments:
        lines.append("")
        lines.append("Observed leveling preferences (separate, soft context):")
        for name in SUPPORTED_SETTINGS:
            if name in context.leveling_adjustments:
                value = context.leveling_adjustments[name]
                lines.append(f"- {name}: typical correction {value:+.4g}")
    if (
        preferred_upright_mode is not None
        or context.preferred_hdr_enabled is not None
    ):
        lines.append("")
        lines.append("Observed categorical mode preferences (soft context):")
        if preferred_upright_mode is not None:
            lines.append(
                "- Upright: "
                f"{preferred_upright_mode.value} "
                f"({context.upright_support_count} similar examples)"
            )
        if context.preferred_hdr_enabled is not None:
            lines.append(
                "- HDR edit mode: "
                f"{'on' if context.preferred_hdr_enabled else 'off'} "
                f"({context.hdr_support_count} similar examples)"
            )
        if (
            context.preferred_hdr_enabled is True
            and context.hdr_enable_rate is not None
            and context.hdr_enable_rate >= 0.70
        ):
            lines.extend(
                [
                    "",
                    "PERSONAL HDR PREFERENCE",
                    "For visually similar photographs, the user "
                    "frequently enables HDR after the AI leaves it disabled.",
                    "Treat this as a strong preference signal. When the current "
                    "image has moderate or high dynamic range and HDR is "
                    "permitted, prefer enabling HDR unless a specific visual "
                    "or safety reason argues against it.",
                    "Do not ignore this preference merely because an acceptable "
                    "SDR edit is technically possible.",
                ]
            )
    lines.extend(
        [
            "",
            "The final result must fit the current image and all current style "
            "and safety constraints. Do not copy historical values blindly.",
            "Mode preferences never override confidence thresholds, scene "
            "evidence, technical safety, or caller capability checks.",
            "END PERSONAL EDITING PREFERENCES",
        ]
    )
    rendered = "\n".join(lines)
    return rendered[:MAX_CONTEXT_CHARACTERS]
