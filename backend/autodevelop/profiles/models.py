"""Validated style-profile models."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from autodevelop.models.common import (
    DevelopSettings,
    FiniteFloat,
    NonBlankString,
    NonNegativeInteger,
    UnitFloat,
)

PROFILE_SLIDER_NAMES = frozenset(DevelopSettings.model_fields) - {
    "CropLeft",
    "CropRight",
    "CropTop",
    "CropBottom",
}
NonNegativeFiniteFloat = Annotated[FiniteFloat, Field(ge=0)]


class _ProfileModel(BaseModel):
    """Strict validation shared by style-profile models."""

    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
    )


class SliderRange(_ProfileModel):
    """Safe intent range for one Lightroom slider."""

    min: FiniteFloat = Field(
        description="Minimum intended slider value.",
    )
    max: FiniteFloat = Field(
        description="Maximum intended slider value.",
    )
    preferred: FiniteFloat | None = Field(
        default=None,
        description="Optional preferred value within the intended range.",
    )

    @model_validator(mode="after")
    def validate_range(self) -> "SliderRange":
        """Validate range ordering and the optional preferred value."""

        if self.min > self.max:
            raise ValueError("slider range must satisfy min <= max")
        if self.preferred is not None and not self.min <= self.preferred <= self.max:
            raise ValueError("preferred value must be between min and max")
        return self


class CropPolicy(_ProfileModel):
    """Style intent governing future crop and leveling recommendations."""

    allow_crop: bool = Field(
        description="Whether crop recommendations are allowed.",
    )
    allow_leveling: bool = Field(
        description="Whether leveling recommendations are allowed.",
    )
    max_edge_crop: UnitFloat = Field(
        description="Maximum intended crop fraction from any single edge.",
    )
    minimum_retained_area: UnitFloat = Field(
        description="Minimum fraction of image area a crop must retain.",
    )
    maximum_absolute_angle: NonNegativeFiniteFloat = Field(
        description="Maximum intended absolute leveling angle in degrees.",
    )
    minimum_confidence: UnitFloat = Field(
        description="Minimum confidence required for a crop recommendation.",
    )
    require_confidence: bool = Field(
        default=False,
        description="Whether crop recommendations must include confidence.",
    )
    preserve_aspect_ratio: bool = Field(
        description="Whether future crop recommendations should preserve aspect ratio.",
    )


class DenoisePolicy(_ProfileModel):
    """Style intent governing future denoise recommendations."""

    allow_denoise: bool = Field(
        description="Whether denoise recommendations are allowed.",
    )
    minimum_iso: NonNegativeInteger = Field(
        description="ISO threshold at which denoise may be considered.",
    )
    minimum_amount: NonNegativeFiniteFloat = Field(
        description="Minimum intended Lightroom denoise amount.",
    )
    maximum_amount: NonNegativeFiniteFloat = Field(
        description="Maximum intended Lightroom denoise amount.",
    )
    minimum_confidence: UnitFloat = Field(
        description="Minimum confidence required for denoise recommendation.",
    )
    preserve_detail: bool = Field(
        description="Whether detail preservation should be prioritized.",
    )

    @model_validator(mode="after")
    def validate_amount_range(self) -> "DenoisePolicy":
        """Validate denoise amount policy ordering."""

        if self.minimum_amount > self.maximum_amount:
            raise ValueError(
                "denoise amount range must satisfy minimum_amount <= maximum_amount"
            )
        return self


class StyleProfile(_ProfileModel):
    """Complete file-backed editing-intent profile."""

    id: str = Field(
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Stable lowercase profile identifier.",
    )
    display_name: NonBlankString = Field(
        description="Human-readable profile name.",
    )
    description: NonBlankString = Field(
        description="Concise description of the profile intent.",
    )
    version: NonBlankString = Field(
        description="Profile format or content version.",
    )
    editing_goals: list[NonBlankString] = Field(
        description="Editing outcomes encouraged by the profile.",
    )
    cautions: list[NonBlankString] = Field(
        description="Editing outcomes the profile should avoid.",
    )
    slider_ranges: dict[str, SliderRange] = Field(
        description="Safe intent ranges keyed by canonical Lightroom slider name.",
    )
    crop_policy: CropPolicy = Field(
        description="Crop and leveling intent for this style.",
    )
    denoise_policy: DenoisePolicy = Field(
        description="Denoise intent for this style.",
    )

    @field_validator("slider_ranges")
    @classmethod
    def validate_slider_names(
        cls,
        ranges: dict[str, SliderRange],
    ) -> dict[str, SliderRange]:
        """Allow only canonical non-coordinate Lightroom slider names."""

        unknown_names = sorted(set(ranges) - PROFILE_SLIDER_NAMES)
        if unknown_names:
            joined_names = ", ".join(unknown_names)
            raise ValueError(f"unknown Lightroom slider name(s): {joined_names}")
        return ranges
