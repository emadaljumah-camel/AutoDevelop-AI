"""Validated contracts for durable AutoDevelop jobs."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from autodevelop.models import DevelopRequest, DevelopResponse, ErrorResponse

JobStatus = Literal["created", "running", "completed", "failed", "interrupted"]
JobIdentifier = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
]


class DevelopJobPhoto(BaseModel):
    """One photo and its preview-free validated Develop request."""

    model_config = ConfigDict(extra="forbid")

    photo_id: JobIdentifier
    request: dict[str, Any]

    @field_validator("request", mode="before")
    @classmethod
    def validate_request(cls, value: object) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("request must be an object")
        payload = dict(value)
        if payload.get("preview_base64") is not None or payload.get("preview_path") is not None:
            raise ValueError("job requests must not contain preview data or paths")
        validated = DevelopRequest.model_validate(
            {**payload, "preview_base64": "pending-job-preview"}
        )
        normalized = validated.model_dump(mode="json")
        normalized.pop("preview_base64", None)
        normalized.pop("preview_path", None)
        return normalized

    def build_request(self, preview_base64: str) -> DevelopRequest:
        """Build the normal API request after loading the acknowledged preview."""

        return DevelopRequest.model_validate(
            {**self.request, "preview_base64": preview_base64}
        )


class CreateDevelopJobRequest(BaseModel):
    """Idempotent batch manifest supplied by the Lightroom client."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    client_job_id: JobIdentifier | None = None
    client: Literal["lightroom"] = "lightroom"
    plugin_version: str = Field(min_length=1, max_length=64)
    photos: list[DevelopJobPhoto] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_photo_ids(self) -> "CreateDevelopJobRequest":
        photo_ids = [photo.photo_id for photo in self.photos]
        if len(photo_ids) != len(set(photo_ids)):
            raise ValueError("photos must have unique photo_id values")
        request_ids = [photo.request["request_id"] for photo in self.photos]
        if len(request_ids) != len(set(request_ids)):
            raise ValueError("photos must have unique request_id values")
        return self


class PreviewUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_base64: str = Field(min_length=1)


class JobProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str = Field(default="created", min_length=1, max_length=64)
    processed_photos: int = Field(default=0, ge=0)
    total_photos: int = Field(default=0, ge=0)
    current_photo_id: JobIdentifier | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> "JobProgress":
        if self.processed_photos > self.total_photos:
            raise ValueError("processed_photos cannot exceed total_photos")
        return self


class JobPhotoResult(BaseModel):
    """Immutable checkpoint for one processed photo."""

    model_config = ConfigDict(extra="forbid")

    photo_id: JobIdentifier
    http_status: int = Field(ge=200, le=599)
    response: DevelopResponse | ErrorResponse

    @model_validator(mode="after")
    def validate_http_status(self) -> "JobPhotoResult":
        if isinstance(self.response, ErrorResponse) and self.http_status < 400:
            raise ValueError("error responses require an error HTTP status")
        if isinstance(self.response, DevelopResponse) and self.http_status >= 300:
            raise ValueError("Develop responses require a successful HTTP status")
        return self


class JobResult(BaseModel):
    """Complete ordered result downloaded by Lightroom."""

    model_config = ConfigDict(extra="forbid")

    job_id: JobIdentifier
    status: Literal["completed"] = "completed"
    results: list[JobPhotoResult]
    succeeded_photos: int = Field(ge=0)
    failed_photos: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> "JobResult":
        succeeded = sum(
            isinstance(item.response, DevelopResponse) for item in self.results
        )
        failed = len(self.results) - succeeded
        if self.succeeded_photos != succeeded or self.failed_photos != failed:
            raise ValueError("result counts do not match photo outcomes")
        return self
