"""Robust aggregation and bounded prompt rendering."""

from collections.abc import Iterable

from autodevelop.learning.constants import (
    MAX_CONTEXT_CHARACTERS,
    PERSONALIZATION_CAPS,
    SUPPORTED_SETTINGS,
)
from autodevelop.learning.models import RetrievalSample
from autodevelop.learning.schemas import PersonalizationContext


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
                    values.append((source[name], max(sample.similarity, 0.001)))
                elif sample.accepted_without_change:
                    values.append((0.0, max(sample.similarity, 0.001)))
            if values:
                raw = _weighted_median(values)
                cap = PERSONALIZATION_CAPS[name]
                result[name] = max(-cap, min(cap, raw))
        return result

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
        accepted_without_change_ratio=(
            sum(sample.accepted_without_change for sample in samples)
            / len(samples)
        ),
        feature_type=feature_type,
    )


def render_personalization(context: PersonalizationContext) -> str:
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
    lines.extend(
        [
            "",
            "The final result must fit the current image and all current style "
            "and safety constraints. Do not copy historical values blindly.",
            "These averaged slider preferences must never force Lightroom HDR "
            "edit mode on or off; HDR remains a separate scene-driven decision.",
            "END PERSONAL EDITING PREFERENCES",
        ]
    )
    rendered = "\n".join(lines)
    return rendered[:MAX_CONTEXT_CHARACTERS]
