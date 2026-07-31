"""Shared response identity validation for Analyze and Develop."""

from collections.abc import Mapping
import math
from typing import Any, TypeVar

from pydantic import ValidationError

from autodevelop.model_clients.diagnostics import (
    InvalidResponseDiagnostics,
    first_error_path,
    validation_error_summary,
)
from autodevelop.model_clients.exceptions import InvalidModelResponseError
from autodevelop.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    DevelopRequest,
    DevelopResponse,
)
from autodevelop.profiles.registry import (
    AUTO_STYLE_ID,
    is_valid_style_id,
    is_valid_style_request_id,
)

ResponseT = TypeVar("ResponseT", AnalyzeResponse, DevelopResponse)

_PROVIDER_IDENTITY_FIELDS = (
    "schema_version",
    "request_id",
    "filename",
    "model",
    "resolved_model",
)
_BACKEND_OWNED_FIELDS = (
    "learning",
    "hdr_decision",
    "requested_style_id",
    "effective_style_id",
    "style_selection_mode",
    "style_selection_reason",
    "editing_intensity",
    "scene_confidence",
)


def _normalize_legacy_geometry(
    payload: Mapping[str, Any],
    *,
    model_name: str,
) -> tuple[dict[str, Any], bool]:
    """Convert the legacy crop angle into the sole leveling structure."""

    normalized = dict(payload)
    crop = normalized.get("crop")
    if not isinstance(crop, Mapping) or "angle" not in crop:
        normalized.setdefault(
            "leveling",
            {"recommended": False, "angle": 0.0, "mode": "none"},
        )
        return normalized, False
    if "leveling" in normalized:
        raise InvalidModelResponseError(
            "The provider response included conflicting geometry fields.",
            model_name=model_name,
            code="provider_schema_mismatch",
            diagnostics=InvalidResponseDiagnostics(
                stage="legacy_schema_normalization_failed",
                diagnostic_code="conflicting_geometry_fields",
                field_path="crop.angle",
                legacy_normalization_attempted=True,
            ),
        )

    normalized_crop = dict(crop)
    legacy_angle = normalized_crop.pop("angle")
    normalized["crop"] = normalized_crop
    if legacy_angle is None or legacy_angle == 0:
        normalized["leveling"] = {
            "recommended": False,
            "angle": 0.0,
            "mode": "none",
        }
        return normalized, True
    if (
        isinstance(legacy_angle, bool)
        or not isinstance(legacy_angle, (int, float))
        or not math.isfinite(legacy_angle)
    ):
        raise InvalidModelResponseError(
            "The provider legacy crop angle was invalid.",
            model_name=model_name,
            code="provider_schema_mismatch",
            diagnostics=InvalidResponseDiagnostics(
                stage="legacy_schema_normalization_failed",
                diagnostic_code="non_finite_value",
                field_path="crop.angle",
                legacy_normalization_attempted=True,
            ),
        )
    normalized["leveling"] = {
        "recommended": True,
        "angle": float(legacy_angle),
        "mode": "horizon",
    }
    return normalized, True


def validate_provider_payload_identity(
    payload: Mapping[str, Any],
    request: AnalyzeRequest | DevelopRequest,
    *,
    expected_resolved_model: str,
) -> None:
    """Validate optional provider identity echoes without trusting their values."""

    expected = {
        "schema_version": "1.0",
        "request_id": str(request.request_id),
        "filename": request.filename,
        "model": request.model,
        "resolved_model": expected_resolved_model,
    }
    if any(
        field in payload and payload[field] != expected[field]
        for field in _PROVIDER_IDENTITY_FIELDS
    ):
        raise InvalidModelResponseError(
            "The provider response identity was invalid.",
            model_name=expected_resolved_model,
            code="provider_schema_mismatch",
            diagnostics=InvalidResponseDiagnostics(
                stage="provider_schema_validation_failed",
                diagnostic_code="provider_identity_mismatch",
                field_path=next(
                    field
                    for field in _PROVIDER_IDENTITY_FIELDS
                    if field in payload and payload[field] != expected[field]
                ),
            ),
        )


def _schema_diagnostic_code(errors: tuple[Mapping[str, str], ...]) -> str:
    if not errors:
        return "schema_validation_failed"
    error_type = errors[0].get("type", "")
    if error_type == "missing":
        return "missing_required_field"
    if error_type == "extra_forbidden":
        return "extra_forbidden_field"
    if "finite" in error_type:
        return "non_finite_value"
    if error_type in {"literal_error", "enum"}:
        return "unsupported_enum"
    return "schema_validation_failed"


def build_model_response(
    payload: Mapping[str, Any] | object,
    request: AnalyzeRequest | DevelopRequest,
    *,
    response_type: type[ResponseT],
    expected_resolved_model: str,
    requested_style_id: str,
    effective_style_id: str,
    style_selection_mode: str,
    style_selection_reason: str,
    editing_intensity: str,
    scene_confidence: float | None,
) -> ResponseT:
    """Build a response from provider content and a trusted backend envelope."""

    if not isinstance(payload, Mapping):
        raise InvalidModelResponseError(
            "The provider response was not a JSON object.",
            model_name=expected_resolved_model,
            code="provider_schema_mismatch",
            diagnostics=InvalidResponseDiagnostics(
                stage="provider_schema_validation_failed",
                diagnostic_code="top_level_not_object",
            ),
        )
    backend_owned_field = next(
        (field for field in _BACKEND_OWNED_FIELDS if field in payload),
        None,
    )
    if backend_owned_field is not None:
        raise InvalidModelResponseError(
            "The provider response included a backend-owned field.",
            model_name=expected_resolved_model,
            code="provider_schema_mismatch",
            diagnostics=InvalidResponseDiagnostics(
                stage="provider_schema_validation_failed",
                diagnostic_code="backend_owned_field",
                field_path=backend_owned_field,
            ),
        )
    validate_provider_payload_identity(
        payload,
        request,
        expected_resolved_model=expected_resolved_model,
    )
    provider_content = {
        field: value
        for field, value in payload.items()
        if field not in _PROVIDER_IDENTITY_FIELDS
    }
    provider_content, legacy_normalization_attempted = _normalize_legacy_geometry(
        provider_content,
        model_name=expected_resolved_model,
    )
    edit_plan = provider_content.get("edit_plan")
    if (
        not isinstance(edit_plan, Mapping)
        or edit_plan.get("style_profile") != effective_style_id
    ):
        raise InvalidModelResponseError(
            "The provider response style identity was invalid.",
            model_name=expected_resolved_model,
            code="provider_schema_mismatch",
            diagnostics=InvalidResponseDiagnostics(
                stage="effective_style_mismatch",
                diagnostic_code="effective_style_mismatch",
                field_path="edit_plan.style_profile",
                legacy_normalization_attempted=legacy_normalization_attempted,
            ),
        )
    trusted_payload = {
        **provider_content,
        "schema_version": "1.0",
        "request_id": str(request.request_id),
        "filename": request.filename,
        "model": request.model,
        "resolved_model": expected_resolved_model,
        "requested_style_id": requested_style_id,
        "effective_style_id": effective_style_id,
        "style_selection_mode": style_selection_mode,
        "style_selection_reason": style_selection_reason,
        "editing_intensity": editing_intensity,
        "scene_confidence": scene_confidence,
    }
    try:
        return response_type.model_validate(trusted_payload)
    except ValidationError as exc:
        error_count, errors = validation_error_summary(exc)
        diagnostic_code = _schema_diagnostic_code(errors)
        raise InvalidModelResponseError(
            "The provider response does not match the API contract.",
            model_name=expected_resolved_model,
            code="provider_schema_mismatch",
            diagnostics=InvalidResponseDiagnostics(
                stage="provider_schema_validation_failed",
                diagnostic_code=diagnostic_code,
                field_path=first_error_path(errors),
                validation_errors=errors,
                validation_error_count=error_count,
                legacy_normalization_attempted=legacy_normalization_attempted,
            ),
        ) from exc


def validate_model_response(
    request: AnalyzeRequest | DevelopRequest,
    response: AnalyzeResponse | DevelopResponse | object,
    *,
    expected_type: type[AnalyzeResponse] | type[DevelopResponse],
    expected_resolved_model: str,
) -> AnalyzeResponse | DevelopResponse:
    """Reject structurally invalid or mismatched provider responses."""

    model_name = getattr(response, "resolved_model", None)
    safe_model_name = (
        model_name
        if isinstance(model_name, str) and model_name.strip()
        else expected_resolved_model
    )
    if not isinstance(response, expected_type):
        raise InvalidModelResponseError(
            "The model client returned an unexpected response type.",
            model_name=safe_model_name,
            code="provider_schema_mismatch",
            diagnostics=InvalidResponseDiagnostics(
                stage="provider_schema_validation_failed",
                diagnostic_code="unexpected_response_type",
            ),
        )

    mismatches: list[str] = []
    if response.schema_version != "1.0":
        mismatches.append("schema_version")
    if response.request_id != request.request_id:
        mismatches.append("request_id")
    if response.filename != request.filename:
        mismatches.append("filename")
    if response.status != "success":
        mismatches.append("status")
    if response.model != request.model:
        mismatches.append("model")
    if response.resolved_model != expected_resolved_model:
        mismatches.append("resolved_model")
    if response.requested_style_id != request.options.style_profile:
        mismatches.append("requested_style_id")
    if not is_valid_style_request_id(response.requested_style_id):
        mismatches.append("requested_style_id")
    if not is_valid_style_id(response.effective_style_id):
        mismatches.append("effective_style_id")
    if response.edit_plan is not None and (
        response.edit_plan.style_profile != response.effective_style_id
    ):
        mismatches.append("effective_style_id")
    if response.style_selection_mode == "manual" and (
        response.effective_style_id != response.requested_style_id
    ):
        mismatches.append("style_selection_mode")
    if response.style_selection_mode == "auto" and (
        response.requested_style_id != AUTO_STYLE_ID
    ):
        mismatches.append("style_selection_mode")
    if isinstance(response, AnalyzeResponse):
        if response.analysis is None:
            mismatches.append("analysis")
        if response.edit_plan is None:
            mismatches.append("edit_plan")

    if mismatches:
        raise InvalidModelResponseError(
            "The model response identity was invalid.",
            model_name=safe_model_name,
            code="provider_schema_mismatch",
            diagnostics=InvalidResponseDiagnostics(
                stage="effective_style_mismatch",
                diagnostic_code="response_identity_mismatch",
                field_path=mismatches[0],
            ),
        )
    return response
