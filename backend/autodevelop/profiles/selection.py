"""Backend-owned scene interpretation and deterministic style selection."""

from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from autodevelop.models.common import (
    EditingIntensity,
    NonBlankString,
    TransportModel,
    UnitFloat,
)
from autodevelop.profiles.registry import AUTO_STYLE_ID, is_valid_style_id

SubjectType = Literal[
    "landscape",
    "architecture",
    "person",
    "people",
    "street",
    "interior",
    "nightscape",
    "astrophotography",
    "nature",
    "other",
    "unknown",
]
SceneCategory = Literal[
    "scenic_travel",
    "architecture",
    "portrait",
    "documentary",
    "night",
    "commercial_general",
    "unknown",
]
LightingType = Literal[
    "daylight",
    "golden_hour",
    "sunset_sunrise",
    "blue_hour",
    "overcast",
    "artificial",
    "low_light",
    "mixed",
    "unknown",
]
DynamicRange = Literal["low", "moderate", "high", "unknown"]
ColorCharacter = Literal["muted", "balanced", "vivid", "mixed", "unknown"]
class SceneSignals(TransportModel):
    """Strict semantic signals returned by the scene-analysis provider pass."""

    primary_subject_type: SubjectType
    primary_subject: NonBlankString | None = None
    secondary_subject_types: list[SubjectType] = Field(default_factory=list)
    scene_category: SceneCategory
    people_present: bool = False
    portrait_dominant: bool = False
    architecture_dominant: bool = False
    documentary_context: bool = False
    night_scene: bool = False
    lighting_type: LightingType = "unknown"
    dynamic_range: DynamicRange = "unknown"
    noise_level: Literal["low", "moderate", "high", "severe", "unknown"] = "unknown"
    color_character: ColorCharacter = "unknown"
    confidence: UnitFloat
    editing_priorities: list[NonBlankString] = Field(
        default_factory=list,
        max_length=5,
    )
    highlight_recoverability: Literal[
        "poor", "limited", "moderate", "high", "unknown"
    ] = "unknown"
    shadow_recoverability: Literal[
        "poor", "limited", "moderate", "high", "unknown"
    ] = "unknown"
    severe_underexposure: bool = False


@dataclass(frozen=True, slots=True)
class StyleSelection:
    """Trusted result used by prompts, learning retrieval, and API diagnostics."""

    requested_style_id: str
    effective_style_id: str
    mode: Literal["auto", "manual"]
    reason: str
    editing_intensity: EditingIntensity
    scene: SceneSignals


_MANUAL_INTENSITY: dict[str, EditingIntensity] = {
    "natural_travel": "strong",
    "landscape_impact": "strong",
    "architecture": "moderate",
    "stock_neutral": "moderate",
    "portrait": "moderate",
    "night": "moderate",
    "documentary": "moderate",
}


def select_style(requested_style_id: str, scene: SceneSignals) -> StyleSelection:
    """Honor manual styles or choose a registered profile from scene signals."""

    if requested_style_id != AUTO_STYLE_ID:
        if not is_valid_style_id(requested_style_id):
            raise ValueError("Unsupported style profile.")
        return StyleSelection(
            requested_style_id=requested_style_id,
            effective_style_id=requested_style_id,
            mode="manual",
            reason="Manual style override",
            editing_intensity=_MANUAL_INTENSITY[requested_style_id],
            scene=scene.model_copy(deep=True),
        )

    effective = "stock_neutral"
    reason = "Ambiguous scene; broad commercial treatment"
    intensity: EditingIntensity = "moderate"
    if scene.night_scene or scene.scene_category == "night":
        effective = "night"
        reason = "Night or low-light scene"
        intensity = "moderate"
    elif scene.portrait_dominant or scene.scene_category == "portrait":
        effective = "portrait"
        reason = "Portrait-dominant subject"
        intensity = "moderate"
    elif scene.documentary_context or scene.scene_category == "documentary":
        effective = "documentary"
        reason = "Documentary or editorial context"
        intensity = "moderate"
    elif scene.architecture_dominant or scene.scene_category == "architecture":
        effective = "architecture"
        reason = "Architectural study"
        intensity = "moderate"
    elif scene.scene_category == "scenic_travel" or scene.primary_subject_type in {
        "landscape",
        "nature",
    }:
        dramatic = (
            scene.dynamic_range == "high"
            and scene.lighting_type in {"golden_hour", "sunset_sunrise"}
        ) or (
            scene.dynamic_range == "high"
            and scene.color_character == "vivid"
            and scene.confidence >= 0.8
        )
        if dramatic:
            effective = "landscape_impact"
            reason = "Dramatic scenic landscape"
            intensity = "strong"
        else:
            effective = "natural_travel"
            reason = "Scenic travel subject"
            intensity = "strong"

    return StyleSelection(
        requested_style_id=requested_style_id,
        effective_style_id=effective,
        mode="auto",
        reason=reason,
        editing_intensity=intensity,
        scene=scene.model_copy(deep=True),
    )
