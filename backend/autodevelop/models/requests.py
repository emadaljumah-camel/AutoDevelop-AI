"""Version 1 Analyze and Develop request models."""

from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from autodevelop.models.common import (
    CurrentDevelopSettings,
    NonBlankString,
    PhotoExif,
    ProcessingOptions,
    TransportModel,
)


class _PhotoRequest(TransportModel):
    """Fields shared by Analyze and Develop requests."""

    schema_version: Literal["1.0"] = Field(
        description="API contract version; Version 1 requires 1.0.",
    )
    request_id: UUID = Field(
        description="Caller-generated UUID used to correlate the request.",
    )
    filename: NonBlankString = Field(
        description="Non-blank original photo filename.",
    )
    preview_path: NonBlankString | None = Field(
        default=None,
        description="Optional preview path; existence is not checked here.",
    )
    preview_base64: NonBlankString | None = Field(
        default=None,
        description="Optional base64 preview text; content is not decoded here.",
    )
    exif: PhotoExif = Field(
        default_factory=PhotoExif,
        description="Normalized EXIF metadata.",
    )
    current_settings: CurrentDevelopSettings = Field(
        default_factory=CurrentDevelopSettings,
        description="Current Lightroom settings supplied as context.",
    )
    options: ProcessingOptions = Field(
        default_factory=ProcessingOptions,
        description="Processing options for the request.",
    )

    @model_validator(mode="after")
    def validate_preview_source(self) -> "_PhotoRequest":
        """Require at least one preview source without accessing it."""

        if self.preview_path is None and self.preview_base64 is None:
            raise ValueError("preview_path or preview_base64 is required")
        return self


class AnalyzeRequest(_PhotoRequest):
    """Request for technical analysis and non-applied recommendations."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "schema_version": "1.0",
                    "request_id": "11111111-1111-4111-8111-111111111111",
                    "filename": "DSC_0001.NEF",
                    "preview_path": "temp/DSC_0001.jpg",
                    "exif": {"iso": 400, "aperture": 8.0},
                }
            ]
        }
    )


class DevelopRequest(_PhotoRequest):
    """Request for a complete AutoDevelop recommendation."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "schema_version": "1.0",
                    "request_id": "22222222-2222-4222-8222-222222222222",
                    "filename": "DSC_0002.NEF",
                    "preview_base64": "/9j/4AAQSkZJRgABAQ...",
                    "options": {
                        "style_profile": "natural_travel",
                        "include_crop": True,
                        "include_denoise": True,
                        "dry_run": False,
                        "preserve_current_adjustments": True,
                    },
                }
            ]
        }
    )
