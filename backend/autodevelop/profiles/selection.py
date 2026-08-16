"""Backend-owned scene interpretation and deterministic style selection."""

from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from autodevelop.models.common import (
    DynamicRangeAnalysis,
    EditingIntensity,
    GeometryAnalysis,
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
    "dramatic_overcast",
    "artificial",
    "low_light",
    "mixed",
    "unknown",
]
DynamicRange = Literal["low", "moderate", "high", "very_high", "unknown"]
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
    geometry_analysis: GeometryAnalysis = Field(
        default_factory=GeometryAnalysis,
    )
    dynamic_range_analysis: DynamicRangeAnalysis = Field(
        default_factory=DynamicRangeAnalysis,
    )


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
    "architecture": "strong",
    "stock_neutral": "strong",
    "portrait": "moderate",
    "night": "strong",
    "documentary": "strong",
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
    intensity: EditingIntensity = "strong"
    if scene.night_scene or scene.scene_category == "night":
        effective = "night"
        reason = "Night or low-light scene"
        intensity = "strong"
    elif scene.portrait_dominant or scene.scene_category == "portrait":
        effective = "portrait"
        reason = "Portrait-dominant subject"
        intensity = "moderate"
    elif scene.documentary_context or scene.scene_category == "documentary":
        effective = "documentary"
        reason = "Documentary or editorial context"
        intensity = "strong"
    elif scene.architecture_dominant or scene.scene_category == "architecture":
        effective = "architecture"
        reason = "Architectural study"
        intensity = "strong"
    elif scene.scene_category == "scenic_travel" or scene.primary_subject_type in {
        "landscape",
        "nature",
    }:
        landscape_dominant = (
            scene.primary_subject_type == "landscape"
            and scene.confidence >= 0.65
        ) or (
            scene.primary_subject_type == "nature"
            and scene.scene_category == "scenic_travel"
            and scene.confidence >= 0.75
        )
        dramatic = (
            scene.dynamic_range in {"high", "very_high"}
            and scene.lighting_type
            in {"golden_hour", "sunset_sunrise", "dramatic_overcast"}
        ) or (
            scene.dynamic_range in {"high", "very_high"}
            and scene.color_character == "vivid"
            and scene.confidence >= 0.8
        )
        if landscape_dominant:
            effective = "landscape_impact"
            if dramatic:
                reason = "Dramatic scenic landscape"
                intensity = "strong"
            else:
                reason = "Landscape-dominant scene"
                intensity = "strong"
        else:
            effective = "natural_travel"
            reason = "Mixed scenic travel scene"
            intensity = "strong"

    return StyleSelection(
        requested_style_id=requested_style_id,
        effective_style_id=effective,
        mode="auto",
        reason=reason,
        editing_intensity=intensity,
        scene=scene.model_copy(deep=True),
    )
