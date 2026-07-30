"""Reusable Version 1 API transport models."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    model_validator,
)


def _reject_boolean_number(value: object) -> object:
    """Prevent Python booleans from being coerced into numeric values."""

    if isinstance(value, bool):
        raise ValueError("boolean values are not valid numeric values")
    return value


FiniteFloat = Annotated[
    float,
    BeforeValidator(_reject_boolean_number),
    Field(allow_inf_nan=False),
]
PositiveFiniteFloat = Annotated[FiniteFloat, Field(gt=0)]
UnitFloat = Annotated[FiniteFloat, Field(ge=0, le=1)]
EditingIntensity = Literal["conservative", "moderate", "strong", "very_strong"]
StyleSelectionMode = Literal["auto", "manual"]
LevelingMode = Literal["none", "horizon", "vertical", "both"]
Recoverability = Literal["poor", "limited", "moderate", "high", "unknown"]
Latitude = Annotated[FiniteFloat, Field(ge=-90, le=90)]
Longitude = Annotated[FiniteFloat, Field(ge=-180, le=180)]
PositiveInteger = Annotated[StrictInt, Field(gt=0)]
NonNegativeInteger = Annotated[StrictInt, Field(ge=0)]
NonBlankString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class TransportModel(BaseModel):
    """Strict base configuration for public API transport models."""

    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
    )


class PhotoExif(TransportModel):
    """Normalized EXIF metadata supplied by the Lightroom plug-in."""

    camera: str | None = Field(
        default=None,
        description="Camera manufacturer and model, when available.",
    )
    lens: str | None = Field(
        default=None,
        description="Lens description reported by the image metadata.",
    )
    iso: PositiveInteger | None = Field(
        default=None,
        description="Positive ISO sensitivity value.",
    )
    aperture: PositiveFiniteFloat | None = Field(
        default=None,
        description="Positive aperture f-number.",
    )
    shutter_speed: str | None = Field(
        default=None,
        description="Exposure duration represented as metadata text.",
    )
    focal_length: PositiveFiniteFloat | None = Field(
        default=None,
        description="Positive focal length in millimeters.",
    )
    capture_date: datetime | None = Field(
        default=None,
        description="Date and time captured, including an offset when available.",
    )
    latitude: Latitude | None = Field(
        default=None,
        description="GPS latitude from -90 through 90 degrees.",
    )
    longitude: Longitude | None = Field(
        default=None,
        description="GPS longitude from -180 through 180 degrees.",
    )
    width: PositiveInteger | None = Field(
        default=None,
        description="Positive original image width in pixels.",
    )
    height: PositiveInteger | None = Field(
        default=None,
        description="Positive original image height in pixels.",
    )
    orientation: StrictInt | None = Field(
        default=None,
        description="Integer EXIF orientation value.",
    )
    exposure_compensation: FiniteFloat | None = Field(
        default=None,
        description="Finite exposure-compensation value in EV.",
    )


class _LightroomDevelopValues(TransportModel):
    """Optional Lightroom values; missing or null means leave unchanged."""

    Exposure2012: FiniteFloat | None = Field(
        default=None,
        description="Lightroom Exposure2012 value; null means unchanged.",
    )
    Contrast2012: FiniteFloat | None = Field(
        default=None,
        description="Lightroom Contrast2012 value; null means unchanged.",
    )
    Highlights2012: FiniteFloat | None = Field(
        default=None,
        description="Lightroom Highlights2012 value; null means unchanged.",
    )
    Shadows2012: FiniteFloat | None = Field(
        default=None,
        description="Lightroom Shadows2012 value; null means unchanged.",
    )
    Whites2012: FiniteFloat | None = Field(
        default=None,
        description="Lightroom Whites2012 value; null means unchanged.",
    )
    Blacks2012: FiniteFloat | None = Field(
        default=None,
        description="Lightroom Blacks2012 value; null means unchanged.",
    )
    Texture: FiniteFloat | None = Field(
        default=None,
        description="Lightroom Texture value; null means unchanged.",
    )
    Clarity2012: FiniteFloat | None = Field(
        default=None,
        description="Lightroom Clarity2012 value; null means unchanged.",
    )
    Dehaze: FiniteFloat | None = Field(
        default=None,
        description="Lightroom Dehaze value; null means unchanged.",
    )
    Vibrance: FiniteFloat | None = Field(
        default=None,
        description="Lightroom Vibrance value; null means unchanged.",
    )
    Saturation: FiniteFloat | None = Field(
        default=None,
        description="Lightroom Saturation value; null means unchanged.",
    )
    Temperature: FiniteFloat | None = Field(
        default=None,
        description="Lightroom Temperature value; null means unchanged.",
    )
    Tint: FiniteFloat | None = Field(
        default=None,
        description="Lightroom Tint value; null means unchanged.",
    )
    CropLeft: UnitFloat | None = Field(
        default=None,
        description="Normalized Lightroom left crop bound; null means unchanged.",
    )
    CropRight: UnitFloat | None = Field(
        default=None,
        description="Normalized Lightroom right crop bound; null means unchanged.",
    )
    CropTop: UnitFloat | None = Field(
        default=None,
        description="Normalized Lightroom top crop bound; null means unchanged.",
    )
    CropBottom: UnitFloat | None = Field(
        default=None,
        description="Normalized Lightroom bottom crop bound; null means unchanged.",
    )
    CropAngle: FiniteFloat | None = Field(
        default=None,
        description="Lightroom crop angle; null means unchanged.",
    )


class CurrentDevelopSettings(_LightroomDevelopValues):
    """Current Lightroom settings supplied as request context."""


class DevelopSettings(_LightroomDevelopValues):
    """Recommended Lightroom settings without safety-layer clamping."""


class ProcessingOptions(TransportModel):
    """Caller-selected options controlling recommendation generation."""

    style_profile: str = Field(
        default="auto",
        description="Auto selection mode or a registered style profile name.",
    )
    include_crop: bool = Field(
        default=True,
        description="Whether crop recommendations should be included.",
    )
    include_denoise: bool = Field(
        default=True,
        description="Whether denoise recommendations should be included.",
    )
    dry_run: bool = Field(
        default=False,
        description="Whether processing should avoid future side effects.",
    )
    preserve_current_adjustments: bool = Field(
        default=True,
        description="Whether existing Lightroom adjustments should be preserved.",
    )
    hdr_edit_supported: bool = Field(
        default=False,
        description="Whether the caller can safely apply Lightroom HDR edit mode.",
    )
    hdr_workflow: Literal["hdr", "sdr_only", "unknown"] = Field(
        default="unknown",
        description="Caller-declared output workflow used for HDR safety gating.",
    )


class LearningRequestOptions(TransportModel):
    """Per-request control for optional personalized Develop context."""

    enabled: bool = Field(
        default=True,
        description="Whether this Develop request may use personalized context.",
    )


class LearningDiagnostics(TransportModel):
    """Safe aggregate diagnostics for optional Develop personalization."""

    enabled: bool = Field(description="Whether backend learning is enabled.")
    personalization_applied: bool = Field(
        description="Whether aggregate personalized context was used."
    )
    usable_sample_count: NonNegativeInteger = Field(
        description="Number of same-profile usable samples available."
    )
    retrieved_sample_count: NonNegativeInteger = Field(
        description="Number of similar samples used for aggregation."
    )
    minimum_sample_count: PositiveInteger = Field(
        description="Minimum usable and similar samples required."
    )
    average_similarity: UnitFloat | None = Field(
        default=None,
        description="Mean similarity of retrieved samples, when available.",
    )
    feature_type: str | None = Field(
        default=None,
        max_length=100,
        description="Safe local feature-provider identifier.",
    )
    reason: Literal[
        "disabled",
        "database_unavailable",
        "embedding_unavailable",
        "insufficient_samples",
        "no_similar_samples",
        "retrieval_unavailable",
    ] | None = Field(
        default=None,
        description="Stable reason personalization was not used.",
    )


class TechnicalAnalysis(TransportModel):
    """Technical and semantic observations about a photo."""

    scene_type: str | None = Field(
        default=None,
        description="Identified scene category.",
    )
    main_subject: str | None = Field(
        default=None,
        description="Identified primary subject.",
    )
    lighting: str | None = Field(
        default=None,
        description="Description of the scene lighting.",
    )
    exposure_assessment: str | None = Field(
        default=None,
        description="Assessment of exposure and tonal distribution.",
    )
    white_balance_assessment: str | None = Field(
        default=None,
        description="Assessment of white balance and color cast.",
    )
    dynamic_range: str | None = Field(
        default=None,
        description="Assessment of scene dynamic range.",
    )
    noise_level: str | None = Field(
        default=None,
        description="Assessment of visible or expected noise.",
    )
    highlight_recoverability: Recoverability = Field(
        default="unknown",
        description="Likely RAW highlight recoverability, not JPEG-preview clipping.",
    )
    shadow_recoverability: Recoverability = Field(
        default="unknown",
        description="Likely RAW shadow recoverability, not JPEG-preview visibility.",
    )
    severe_underexposure: bool = Field(
        default=False,
        description="Whether underexposure or noise makes HDR edit mode unsafe.",
    )
    horizon_status: str | None = Field(
        default=None,
        description="Assessment of horizon visibility and alignment.",
    )
    visible_people: NonNegativeInteger | None = Field(
        default=None,
        description="Non-negative number of visible people.",
    )
    has_faces: bool | None = Field(
        default=None,
        description="Whether faces are visible.",
    )
    has_sky: bool | None = Field(
        default=None,
        description="Whether the scene contains visible sky.",
    )
    confidence: UnitFloat | None = Field(
        default=None,
        description="Optional analysis confidence from 0.0 through 1.0.",
    )


class EditPlan(TransportModel):
    """High-level goals and cautions for a recommended edit."""

    style_profile: str = Field(
        description="Style profile selected for the edit.",
    )
    goals: list[str] = Field(
        default_factory=list,
        description="Editing goals to pursue.",
    )
    cautions: list[str] = Field(
        default_factory=list,
        description="Editing risks or constraints to observe.",
    )


class CropRecommendation(TransportModel):
    """Composition-crop recommendation independent of rotational leveling."""

    recommended: bool = Field(
        description="Whether the crop is recommended.",
    )
    left: UnitFloat | None = Field(
        default=None,
        description="Optional normalized left crop bound.",
    )
    right: UnitFloat | None = Field(
        default=None,
        description="Optional normalized right crop bound.",
    )
    top: UnitFloat | None = Field(
        default=None,
        description="Optional normalized top crop bound.",
    )
    bottom: UnitFloat | None = Field(
        default=None,
        description="Optional normalized bottom crop bound.",
    )
    confidence: UnitFloat | None = Field(
        default=None,
        description="Optional crop confidence from 0.0 through 1.0.",
    )
    reason: str | None = Field(
        default=None,
        description="Optional explanation for the recommendation.",
    )

    @model_validator(mode="after")
    def validate_crop_bounds(self) -> "CropRecommendation":
        """Validate completeness and ordering without applying crop policy."""

        bounds = (self.left, self.right, self.top, self.bottom)
        provided_count = sum(value is not None for value in bounds)
        if self.recommended and 0 < provided_count < 4:
            raise ValueError(
                "all crop bounds are required when a crop is recommended"
            )
        if provided_count == 4:
            assert self.left is not None
            assert self.right is not None
            assert self.top is not None
            assert self.bottom is not None
            if self.left >= self.right:
                raise ValueError("crop bounds must satisfy left < right")
            if self.top >= self.bottom:
                raise ValueError("crop bounds must satisfy top < bottom")
        return self


class LevelingRecommendation(TransportModel):
    """Rotational-leveling recommendation independent of composition crop."""

    recommended: bool = Field(
        description="Whether rotational leveling is recommended.",
    )
    angle: FiniteFloat = Field(
        default=0.0,
        description="Finite Lightroom rotation angle in degrees.",
    )
    mode: LevelingMode = Field(
        default="none",
        description="Stable geometric reference used for rotational leveling.",
    )

    @model_validator(mode="after")
    def validate_state(self) -> "LevelingRecommendation":
        """Require active and inactive leveling states to be unambiguous."""

        if self.recommended:
            if self.mode == "none":
                raise ValueError(
                    "recommended leveling requires a non-none mode"
                )
        elif self.angle != 0 or self.mode != "none":
            raise ValueError(
                "inactive leveling requires angle=0 and mode='none'"
            )
        return self


class DenoiseRecommendation(TransportModel):
    """Recommendation for a future Lightroom denoise operation."""

    recommended: bool = Field(
        description="Whether denoise is recommended.",
    )
    amount: FiniteFloat | None = Field(
        default=None,
        description="Optional denoise amount without transport-layer clamping.",
    )
    confidence: UnitFloat | None = Field(
        default=None,
        description="Optional denoise confidence from 0.0 through 1.0.",
    )
    reason: str | None = Field(
        default=None,
        description="Optional explanation for the recommendation.",
    )


class HdrRecommendation(TransportModel):
    """Backend-validated Lightroom HDR edit-mode recommendation."""

    recommended: bool = Field(
        description="Whether Lightroom HDR edit mode is recommended.",
    )
    reason: Literal[None] = Field(
        default=None,
        description="Reserved field; provider reasoning is never exposed.",
    )


class ProcessingWarning(TransportModel):
    """Nonfatal issue reported during analysis or recommendation generation."""

    code: str = Field(
        min_length=1,
        description="Non-empty machine-readable warning code.",
    )
    message: str = Field(
        min_length=1,
        description="Non-empty human-readable warning message.",
    )
    field: str | None = Field(
        default=None,
        description="Optional request or response field associated with the warning.",
    )
    severity: Literal["info", "warning", "error"] = Field(
        description="Warning severity.",
    )
