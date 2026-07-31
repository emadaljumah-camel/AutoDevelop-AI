"""Canonical feedback comparison shared by preview and persistence."""

from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Mapping

from autodevelop.learning.constants import (
    COMPOSITION_CROP_SETTINGS,
    LEVELING_SETTINGS,
    SIGNIFICANCE_THRESHOLDS,
    SUPPORTED_SETTINGS,
)
from autodevelop.learning.schemas import DevelopModeState, DevelopSettingDeltas
from autodevelop.models import DevelopSettings, UprightMode


@dataclass(frozen=True)
class SettingComparison:
    """One canonical Lightroom setting comparison."""

    baseline: float
    current: float
    delta: float
    threshold: float
    significant: bool


@dataclass(frozen=True)
class FeedbackComparison:
    """Immutable classification result for one feedback request."""

    final_settings: DevelopSettings
    comparisons: Mapping[str, SettingComparison]
    delta: DevelopSettingDeltas
    significant_delta: DevelopSettingDeltas
    ignored_delta: DevelopSettingDeltas
    crop_delta: DevelopSettingDeltas
    leveling_delta: DevelopSettingDeltas
    final_modes: DevelopModeState
    ai_upright_mode: UprightMode | None
    ai_hdr_enabled: bool | None
    upright_changed: bool
    hdr_changed: bool
    accepted_without_change: bool


def compare_feedback_settings(
    applied_baseline: Mapping[str, float],
    final_settings: Mapping[str, float],
    *,
    applied_modes: DevelopModeState | None = None,
    final_modes: DevelopModeState | None = None,
) -> FeedbackComparison:
    """Compare canonical current values with the trusted applied baseline."""

    canonical_final = {
        key: float(final_settings[key])
        for key in SUPPORTED_SETTINGS
        if key in final_settings and isfinite(float(final_settings[key]))
    }
    comparisons: dict[str, SettingComparison] = {}
    delta: dict[str, float] = {}
    significant: dict[str, float] = {}
    ignored: dict[str, float] = {}
    crop: dict[str, float] = {}
    leveling: dict[str, float] = {}

    for key in SUPPORTED_SETTINGS:
        if key not in applied_baseline or key not in canonical_final:
            continue
        baseline = float(applied_baseline[key])
        current = canonical_final[key]
        if not isfinite(baseline):
            continue
        change = current - baseline
        threshold = SIGNIFICANCE_THRESHOLDS[key]
        is_significant = abs(change) >= threshold
        comparisons[key] = SettingComparison(
            baseline=baseline,
            current=current,
            delta=change,
            threshold=threshold,
            significant=is_significant,
        )
        delta[key] = change
        if is_significant and key in COMPOSITION_CROP_SETTINGS:
            crop[key] = change
        elif is_significant and key in LEVELING_SETTINGS:
            leveling[key] = change
        elif is_significant:
            significant[key] = change
        else:
            ignored[key] = change

    applied_modes = applied_modes or DevelopModeState()
    final_modes = final_modes or DevelopModeState()
    upright_changed = (
        applied_modes.upright is not None
        and final_modes.upright is not None
        and applied_modes.upright != final_modes.upright
    )
    hdr_changed = (
        applied_modes.hdr_enabled is not None
        and final_modes.hdr_enabled is not None
        and applied_modes.hdr_enabled != final_modes.hdr_enabled
    )

    return FeedbackComparison(
        final_settings=DevelopSettings(**canonical_final),
        comparisons=MappingProxyType(comparisons),
        delta=DevelopSettingDeltas(**delta),
        significant_delta=DevelopSettingDeltas(**significant),
        ignored_delta=DevelopSettingDeltas(**ignored),
        crop_delta=DevelopSettingDeltas(**crop),
        leveling_delta=DevelopSettingDeltas(**leveling),
        final_modes=final_modes.model_copy(deep=True),
        ai_upright_mode=applied_modes.upright,
        ai_hdr_enabled=applied_modes.hdr_enabled,
        upright_changed=upright_changed,
        hdr_changed=hdr_changed,
        accepted_without_change=(
            not significant
            and not crop
            and not leveling
            and not upright_changed
            and not hdr_changed
        ),
    )
