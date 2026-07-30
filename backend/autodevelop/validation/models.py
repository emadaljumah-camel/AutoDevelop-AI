"""Public models returned by the safety-validation layer."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from autodevelop.models import (
    CropRecommendation,
    DenoiseRecommendation,
    DevelopSettings,
    HdrRecommendation,
    LevelingRecommendation,
)


class ValidationAction(StrEnum):
    """Action taken by safety validation."""

    ACCEPTED = "accepted"
    CLAMPED = "clamped"
    REMOVED = "removed"
    REJECTED = "rejected"


class _ValidationModel(BaseModel):
    """Strict base configuration for validation output."""

    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
    )


class ValidationIssue(_ValidationModel):
    """One deterministic adjustment or rejection produced by validation."""

    code: str = Field(
        min_length=1,
        description="Stable machine-readable issue code.",
    )
    message: str = Field(
        min_length=1,
        description="Human-readable explanation of the issue.",
    )
    field: str | None = Field(
        default=None,
        description="Optional field associated with the issue.",
    )
    original_value: JsonValue | None = Field(
        default=None,
        description="Optional JSON-safe value received by the validator.",
    )
    adjusted_value: JsonValue | None = Field(
        default=None,
        description="Optional JSON-safe value emitted by the validator.",
    )
    action: ValidationAction = Field(
        description="Action taken for the issue.",
    )
    severity: Literal["info", "warning", "error"] = Field(
        description="Issue severity.",
    )


class ValidationResult(_ValidationModel):
    """Safe normalized recommendations and their validation audit trail."""

    is_safe: bool = Field(
        description="Whether the result contains no error-severity issues.",
    )
    settings: DevelopSettings = Field(
        description="Safe Lightroom develop settings.",
    )
    crop: CropRecommendation | None = Field(
        default=None,
        description="Safe crop recommendation, if retained.",
    )
    leveling: LevelingRecommendation = Field(
        default_factory=lambda: LevelingRecommendation(
            recommended=False,
            angle=0,
            mode="none",
        ),
        description="Safe rotational-leveling recommendation.",
    )
    denoise: DenoiseRecommendation | None = Field(
        default=None,
        description="Safe denoise recommendation, if supplied.",
    )
    enable_hdr: HdrRecommendation = Field(
        default_factory=lambda: HdrRecommendation(recommended=False),
        description="Backend-validated Lightroom HDR edit-mode recommendation.",
    )
    issues: list[ValidationIssue] = Field(
        default_factory=list,
        description="Ordered validation issues.",
    )
    rejected_fields: list[str] = Field(
        default_factory=list,
        description="Ordered unique fields rejected during validation.",
    )
    clamped_fields: list[str] = Field(
        default_factory=list,
        description="Ordered unique fields clamped during validation.",
    )
    removed_fields: list[str] = Field(
        default_factory=list,
        description="Ordered unique fields removed during validation.",
    )
