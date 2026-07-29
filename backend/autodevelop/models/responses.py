"""Version 1 Analyze, Develop, and error response models."""

from typing import Any, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, GetJsonSchemaHandler
from pydantic_core import CoreSchema

from autodevelop.models.common import (
    CropRecommendation,
    DenoiseRecommendation,
    DevelopSettings,
    EditPlan,
    NonBlankString,
    NonNegativeInteger,
    ProcessingWarning,
    TechnicalAnalysis,
    TransportModel,
)

ResponseStatus = Literal["success", "partial", "error"]


class _ResponseBase(TransportModel):
    """Fields required on every top-level Version 1 response."""

    schema_version: Literal["1.0"] = Field(
        description="API contract version; Version 1 requires 1.0.",
    )
    request_id: UUID = Field(
        description="UUID copied from the corresponding request.",
    )
    filename: NonBlankString = Field(
        description="Non-blank original photo filename.",
    )


class _ProcessingResponseBase(_ResponseBase):
    """Fields shared by Analyze and Develop responses."""

    status: ResponseStatus = Field(
        description="Overall processing outcome.",
    )
    analysis: TechnicalAnalysis | None = Field(
        default=None,
        description="Optional technical analysis.",
    )
    edit_plan: EditPlan | None = Field(
        default=None,
        description="Optional high-level edit plan.",
    )
    crop: CropRecommendation | None = Field(
        default=None,
        description="Optional crop recommendation.",
    )
    denoise: DenoiseRecommendation | None = Field(
        default=None,
        description="Optional denoise recommendation.",
    )
    warnings: list[ProcessingWarning] = Field(
        default_factory=list,
        description="Nonfatal processing warnings.",
    )
    model: NonBlankString = Field(
        description="Stable model registry ID used for processing.",
    )
    resolved_model: NonBlankString = Field(
        description="Configured provider model identifier used for inference.",
    )
    processing_duration_ms: NonNegativeInteger | None = Field(
        default=None,
        description="Optional non-negative processing duration in milliseconds.",
    )


class AnalyzeResponse(_ProcessingResponseBase):
    """Technical analysis response without Lightroom application."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "schema_version": "1.0",
                    "request_id": "11111111-1111-4111-8111-111111111111",
                    "filename": "DSC_0001.NEF",
                    "status": "success",
                    "analysis": {
                        "scene_type": "landscape",
                        "main_subject": "mountain lake",
                        "lighting": "soft morning light",
                        "exposure_assessment": "Highlights are recoverable.",
                        "white_balance_assessment": "Slightly cool.",
                        "dynamic_range": "high",
                        "noise_level": "low",
                        "horizon_status": "slightly tilted",
                        "visible_people": 0,
                        "has_faces": False,
                        "has_sky": True,
                        "confidence": 0.93,
                    },
                    "edit_plan": {
                        "style_profile": "natural_travel",
                        "goals": ["Recover sky detail", "Add tonal separation"],
                        "cautions": ["Preserve natural foliage color"],
                    },
                    "crop": {
                        "recommended": True,
                        "left": 0.02,
                        "right": 0.98,
                        "top": 0.03,
                        "bottom": 0.97,
                        "angle": -0.4,
                        "confidence": 0.86,
                        "reason": "Level the horizon.",
                    },
                    "denoise": {
                        "recommended": False,
                        "amount": None,
                        "confidence": 0.9,
                        "reason": "Noise is minimal.",
                    },
                    "warnings": [],
                    "model": "gemma",
                    "resolved_model": "gemma-4-31b",
                    "processing_duration_ms": 842,
                }
            ]
        }
    )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> dict[str, Any]:
        """Preserve the public Analyze status-field description."""

        schema = super().__get_pydantic_json_schema__(core_schema, handler)
        schema["properties"]["status"]["description"] = "Overall analysis outcome."
        return schema


class DevelopResponse(_ProcessingResponseBase):
    """Complete AutoDevelop recommendation response."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "schema_version": "1.0",
                    "request_id": "22222222-2222-4222-8222-222222222222",
                    "filename": "DSC_0002.NEF",
                    "status": "success",
                    "analysis": {
                        "scene_type": "landscape",
                        "main_subject": "coastline",
                        "lighting": "golden hour",
                        "exposure_assessment": "Bright sky with open shadows.",
                        "white_balance_assessment": "Warm and natural.",
                        "dynamic_range": "high",
                        "noise_level": "low",
                        "horizon_status": "level",
                        "visible_people": 0,
                        "has_faces": False,
                        "has_sky": True,
                        "confidence": 0.95,
                    },
                    "edit_plan": {
                        "style_profile": "natural_travel",
                        "goals": ["Recover highlights", "Enhance depth"],
                        "cautions": ["Avoid oversaturating the sky"],
                    },
                    "develop_settings": {
                        "Exposure2012": 0.3,
                        "Contrast2012": 18.0,
                        "Highlights2012": -42.0,
                        "Shadows2012": 26.0,
                        "Whites2012": 14.0,
                        "Blacks2012": -12.0,
                        "Texture": 10.0,
                        "Clarity2012": 8.0,
                        "Dehaze": 6.0,
                        "Vibrance": 24.0,
                        "Saturation": 2.0,
                        "Temperature": 5750.0,
                        "Tint": 6.0,
                        "CropLeft": 0.02,
                        "CropRight": 0.98,
                        "CropTop": 0.03,
                        "CropBottom": 0.97,
                        "CropAngle": -0.4,
                    },
                    "crop": {
                        "recommended": True,
                        "left": 0.02,
                        "right": 0.98,
                        "top": 0.03,
                        "bottom": 0.97,
                        "angle": -0.4,
                        "confidence": 0.88,
                        "reason": "Remove narrow edge distractions.",
                    },
                    "denoise": {
                        "recommended": False,
                        "amount": None,
                        "confidence": 0.91,
                        "reason": "Noise is not significant.",
                    },
                    "warnings": [],
                    "model": "qwen",
                    "resolved_model": "qwen_qwen3-vl-32b-instruct",
                    "processing_duration_ms": 1094,
                }
            ]
        }
    )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> dict[str, Any]:
        """Preserve the public Develop status-field description."""

        schema = super().__get_pydantic_json_schema__(core_schema, handler)
        schema["properties"]["status"][
            "description"
        ] = "Overall recommendation outcome."
        return schema

    develop_settings: DevelopSettings | None = Field(
        default=None,
        description="Optional Lightroom develop recommendations.",
    )


class ErrorDetail(TransportModel):
    """Structured error information."""

    code: str = Field(
        min_length=1,
        description="Non-empty machine-readable error code.",
    )
    message: str = Field(
        min_length=1,
        description="Non-empty human-readable error message.",
    )
    field: str | None = Field(
        default=None,
        description="Optional request field associated with the error.",
    )
    retryable: bool = Field(
        default=False,
        description="Whether retrying the same operation may succeed.",
    )


class ErrorResponse(_ResponseBase):
    """Versioned error response for a photo request."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "schema_version": "1.0",
                    "request_id": "33333333-3333-4333-8333-333333333333",
                    "filename": "DSC_0003.NEF",
                    "status": "error",
                    "error": {
                        "code": "invalid_preview",
                        "message": "The preview could not be read.",
                        "field": "preview_path",
                        "retryable": False,
                    },
                    "warnings": [],
                }
            ]
        }
    )

    status: Literal["error"] = Field(
        description="Error responses always use the error status.",
    )
    error: ErrorDetail = Field(
        description="Structured error details.",
    )
    warnings: list[ProcessingWarning] = Field(
        default_factory=list,
        description="Additional nonfatal warnings.",
    )
