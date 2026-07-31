"""Strict public and internal learning transport schemas."""

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from autodevelop.learning.constants import LIGHTROOM_LIMITS
from autodevelop.models import (
    DevelopSettings,
    HdrDecisionDiagnostics,
    LearningDiagnostics,
    UprightMode,
)
from autodevelop.models.common import FiniteFloat, NonNegativeInteger, UnitFloat

PhotoKey = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
BoundedText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ExposureDelta = Annotated[FiniteFloat, Field(ge=-10, le=10)]
StandardSliderDelta = Annotated[FiniteFloat, Field(ge=-200, le=200)]
TemperatureDelta = Annotated[FiniteFloat, Field(ge=-48_000, le=48_000)]
TintDelta = Annotated[FiniteFloat, Field(ge=-300, le=300)]
CropCoordinateDelta = Annotated[FiniteFloat, Field(ge=-1, le=1)]
CropAngleDelta = Annotated[FiniteFloat, Field(ge=-90, le=90)]


class LearningSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class LearningExifContext(LearningSchema):
    file_format: str | None = Field(default=None, max_length=20)
    camera: str | None = Field(default=None, max_length=200)
    lens: str | None = Field(default=None, max_length=200)
    iso: int | None = Field(default=None, ge=1, le=6_553_600)
    aperture: FiniteFloat | None = Field(default=None, gt=0, le=128)
    shutter_speed: str | None = Field(default=None, max_length=50)
    focal_length: FiniteFloat | None = Field(default=None, gt=0, le=10_000)
    capture_time_category: Literal[
        "night", "morning", "day", "evening", "unknown"
    ] = "unknown"
    orientation: int | None = Field(default=None, ge=1, le=8)
    width: int | None = Field(default=None, gt=0, le=1_000_000)
    height: int | None = Field(default=None, gt=0, le=1_000_000)
    scene_type: str | None = Field(default=None, max_length=100)
    lighting: str | None = Field(default=None, max_length=200)


class ValidationSummary(LearningSchema):
    issue_count: NonNegativeInteger = 0
    crop_rejected: bool = False
    leveling_rejected: bool = False
    clamped_count: NonNegativeInteger = 0
    removed_count: NonNegativeInteger = 0


class DevelopModeState(LearningSchema):
    """Categorical Lightroom modes kept separate from numeric sliders."""

    upright: UprightMode | None = None
    upright_raw_value: Literal[0, 1, 2, 3, 4] | None = None
    hdr_enabled: bool | None = None
    hdr_raw_value: Literal[0, 1] | None = None
    hdr_max_value: FiniteFloat | None = None


class LearningModeChanges(LearningSchema):
    upright: UprightMode | None = None
    hdr_enabled: bool | None = None


def _validate_setting_ranges(settings: DevelopSettings) -> DevelopSettings:
    for name, value in settings.model_dump(exclude_none=True).items():
        minimum, maximum = LIGHTROOM_LIMITS[name]
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} is outside the supported Lightroom range")
    return settings


class BaselineRequest(LearningSchema):
    schema_version: Literal[1]
    session_id: UUID
    request_id: UUID
    photo_key: PhotoKey
    filename: BoundedText = Field(max_length=255)
    catalog_id: str | None = Field(default=None, max_length=128)
    local_identifier: str | None = Field(default=None, max_length=128)
    profile: BoundedText = Field(max_length=64)
    model: BoundedText = Field(max_length=64)
    resolved_model: BoundedText = Field(max_length=200)
    original_settings: DevelopSettings
    recommendation: DevelopSettings
    applied_baseline: DevelopSettings
    original_modes: DevelopModeState = Field(default_factory=DevelopModeState)
    recommendation_modes: DevelopModeState = Field(
        default_factory=DevelopModeState
    )
    applied_modes: DevelopModeState = Field(default_factory=DevelopModeState)
    exif_context: LearningExifContext = Field(default_factory=LearningExifContext)
    validation_summary: ValidationSummary = Field(default_factory=ValidationSummary)
    hdr_decision: HdrDecisionDiagnostics | None = None

    _original_ranges = field_validator("original_settings")(
        _validate_setting_ranges
    )
    _recommendation_ranges = field_validator("recommendation")(
        _validate_setting_ranges
    )
    _baseline_ranges = field_validator("applied_baseline")(
        _validate_setting_ranges
    )

    @model_validator(mode="after")
    def require_applied_baseline(self) -> "BaselineRequest":
        if not self.applied_baseline.model_dump(exclude_none=True):
            raise ValueError("applied_baseline must contain a develop setting")
        return self


class BaselineResponse(LearningSchema):
    schema_version: Literal[1] = 1
    session_id: UUID
    state: Literal["pending_feedback"] = "pending_feedback"
    stored: bool


class FeedbackRequest(LearningSchema):
    schema_version: Literal[1]
    session_id: UUID
    photo_key: PhotoKey
    final_settings: DevelopSettings
    final_modes: DevelopModeState = Field(default_factory=DevelopModeState)

    _final_ranges = field_validator("final_settings")(
        _validate_setting_ranges
    )


class DevelopSettingDeltas(LearningSchema):
    """Finite signed differences between canonical Lightroom settings."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    Exposure2012: ExposureDelta | None = None
    Contrast2012: StandardSliderDelta | None = None
    Highlights2012: StandardSliderDelta | None = None
    Shadows2012: StandardSliderDelta | None = None
    Whites2012: StandardSliderDelta | None = None
    Blacks2012: StandardSliderDelta | None = None
    Texture: StandardSliderDelta | None = None
    Clarity2012: StandardSliderDelta | None = None
    Dehaze: StandardSliderDelta | None = None
    Vibrance: StandardSliderDelta | None = None
    Saturation: StandardSliderDelta | None = None
    Temperature: TemperatureDelta | None = None
    Tint: TintDelta | None = None
    CropLeft: CropCoordinateDelta | None = None
    CropRight: CropCoordinateDelta | None = None
    CropTop: CropCoordinateDelta | None = None
    CropBottom: CropCoordinateDelta | None = None
    CropAngle: CropAngleDelta | None = None


class FeedbackResponse(LearningSchema):
    schema_version: Literal[1] = 1
    feedback_id: UUID
    session_id: UUID
    usable: bool
    accepted_without_change: bool
    significant_changes: DevelopSettingDeltas
    ignored_changes: DevelopSettingDeltas
    crop_changes: DevelopSettingDeltas
    leveling_changes: DevelopSettingDeltas
    mode_changes: LearningModeChanges
    state: Literal["feedback_captured"] = "feedback_captured"


class FeedbackSettingComparison(LearningSchema):
    baseline: FiniteFloat
    current: FiniteFloat
    delta: FiniteFloat
    threshold: FiniteFloat = Field(ge=0)
    significant: bool


class FeedbackPreviewResponse(LearningSchema):
    schema_version: Literal[1] = 1
    session_id: UUID
    has_significant_changes: bool
    accepted_without_change: bool
    significant_changes: dict[str, FeedbackSettingComparison]
    ignored_changes: dict[str, FeedbackSettingComparison]
    crop_changes: dict[str, FeedbackSettingComparison]
    leveling_changes: dict[str, FeedbackSettingComparison]
    mode_changes: LearningModeChanges


class ModeLearningStatus(LearningSchema):
    usable_sample_count: NonNegativeInteger
    change_count: NonNegativeInteger
    acceptance_count: NonNegativeInteger


class LearningStatusResponse(LearningSchema):
    schema_version: Literal[1] = 1
    enabled: bool
    database_available: bool
    embedding_available: bool
    feature_type: str | None
    pending_sessions: NonNegativeInteger
    feedback_samples: NonNegativeInteger
    usable_samples: NonNegativeInteger
    accepted_without_change: NonNegativeInteger
    upright_learning: ModeLearningStatus
    hdr_learning: ModeLearningStatus
    minimum_samples: int = Field(ge=1)


class DeleteAllLearningRequest(LearningSchema):
    confirm: Literal["DELETE_ALL_LEARNING_DATA"]


class DeleteLearningResponse(LearningSchema):
    schema_version: Literal[1] = 1
    deleted: bool
    affected_sessions: NonNegativeInteger


class FeatureVector(LearningSchema):
    feature_type: BoundedText = Field(max_length=100)
    feature_version: int = Field(ge=1, le=1000)
    dimensions: int = Field(ge=1, le=512)
    vector: list[FiniteFloat] = Field(min_length=1, max_length=512)

    @field_validator("vector")
    @classmethod
    def validate_dimensions(cls, value: list[float], info) -> list[float]:
        dimensions = info.data.get("dimensions")
        if dimensions is not None and len(value) != dimensions:
            raise ValueError("feature dimensions do not match vector length")
        return value


class PersonalizationContext(LearningSchema):
    profile_id: str
    sample_count: NonNegativeInteger
    usable_sample_count: NonNegativeInteger
    average_similarity: FiniteFloat
    preferred_adjustments: dict[str, FiniteFloat]
    crop_adjustments: dict[str, FiniteFloat]
    leveling_adjustments: dict[str, FiniteFloat]
    preferred_upright_mode: UprightMode | None = None
    upright_support_count: NonNegativeInteger = 0
    preferred_hdr_enabled: bool | None = None
    hdr_support_count: NonNegativeInteger = 0
    hdr_enable_rate: UnitFloat | None = None
    accepted_without_change_ratio: FiniteFloat
    feature_type: str | None


def safe_model_dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json", exclude_none=True)
