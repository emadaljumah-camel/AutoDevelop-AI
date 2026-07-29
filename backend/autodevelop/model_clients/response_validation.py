"""Shared response identity validation for Analyze and Develop."""

from collections.abc import Mapping
from typing import Any, TypeVar

from pydantic import ValidationError

from autodevelop.model_clients.exceptions import InvalidModelResponseError
from autodevelop.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    DevelopRequest,
    DevelopResponse,
)

ResponseT = TypeVar("ResponseT", AnalyzeResponse, DevelopResponse)

_PROVIDER_IDENTITY_FIELDS = (
    "schema_version",
    "request_id",
    "filename",
    "model",
    "resolved_model",
)


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
        )


def build_model_response(
    payload: Mapping[str, Any] | object,
    request: AnalyzeRequest | DevelopRequest,
    *,
    response_type: type[ResponseT],
    expected_resolved_model: str,
) -> ResponseT:
    """Build a response from provider content and a trusted backend envelope."""

    if not isinstance(payload, Mapping):
        raise InvalidModelResponseError(
            "The provider response was not a JSON object.",
            model_name=expected_resolved_model,
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
    trusted_payload = {
        **provider_content,
        "schema_version": "1.0",
        "request_id": str(request.request_id),
        "filename": request.filename,
        "model": request.model,
        "resolved_model": expected_resolved_model,
    }
    try:
        return response_type.model_validate(trusted_payload)
    except ValidationError as exc:
        raise InvalidModelResponseError(
            "The provider response does not match the API contract.",
            model_name=expected_resolved_model,
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
    if isinstance(response, AnalyzeResponse):
        if response.analysis is None:
            mismatches.append("analysis")
        if response.edit_plan is None:
            mismatches.append("edit_plan")

    if mismatches:
        raise InvalidModelResponseError(
            "The model response identity was invalid.",
            model_name=safe_model_name,
        )
    return response
