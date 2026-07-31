from uuid import UUID

import pytest

from autodevelop.model_clients import FakeModelClient, InvalidModelResponseError
from autodevelop.model_clients.response_validation import (
    build_model_response,
    validate_model_response,
    validate_provider_payload_identity,
)
from autodevelop.models import AnalyzeRequest, AnalyzeResponse

REQUEST_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


def _request() -> AnalyzeRequest:
    return AnalyzeRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        filename="Identity.NEF",
        model="gemma",
        preview_path="not-read.jpg",
    )


def _response() -> AnalyzeResponse:
    request = _request()
    import asyncio

    return asyncio.run(
        FakeModelClient(model_name="gemma-4-31b").analyze(request)
    )


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "2.0"},
        {"request_id": UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")},
        {"filename": "Different.NEF"},
        {"model": "qwen"},
        {"resolved_model": "different-provider-model"},
        {"status": "partial"},
        {"analysis": None},
        {"edit_plan": None},
    ],
)
def test_shared_validator_rejects_mismatched_analyze_identity(
    change: dict[str, object],
) -> None:
    with pytest.raises(InvalidModelResponseError) as raised:
        validate_model_response(
            _request(),
            _response().model_copy(update=change),
            expected_type=AnalyzeResponse,
            expected_resolved_model="gemma-4-31b",
        )
    assert raised.value.code == "provider_schema_mismatch"


def test_shared_validator_accepts_valid_analyze_response() -> None:
    response = _response()
    assert (
        validate_model_response(
            _request(),
            response,
            expected_type=AnalyzeResponse,
            expected_resolved_model="gemma-4-31b",
        )
        is response
    )


def test_provider_identity_echoes_are_optional() -> None:
    validate_provider_payload_identity(
        {"status": "success"},
        _request(),
        expected_resolved_model="gemma-4-31b",
    )


def test_matching_provider_identity_echoes_are_accepted() -> None:
    validate_provider_payload_identity(
        {
            "schema_version": "1.0",
            "request_id": str(REQUEST_ID),
            "filename": "Identity.NEF",
            "model": "gemma",
            "resolved_model": "gemma-4-31b",
        },
        _request(),
        expected_resolved_model="gemma-4-31b",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "2.0"),
        ("request_id", "cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
        ("filename", "Different.NEF"),
        ("model", "qwen"),
        ("resolved_model", "different-provider-model"),
    ],
)
def test_mismatched_provider_identity_echo_is_rejected(
    field: str,
    value: str,
) -> None:
    with pytest.raises(InvalidModelResponseError) as raised:
        validate_provider_payload_identity(
            {field: value},
            _request(),
            expected_resolved_model="gemma-4-31b",
        )

    assert raised.value.code == "provider_schema_mismatch"


def test_trusted_envelope_does_not_mutate_provider_payload() -> None:
    response_payload = _response().model_dump(mode="json")
    for field in (
        "schema_version",
        "request_id",
        "filename",
        "model",
        "resolved_model",
        "requested_style_id",
        "effective_style_id",
        "style_selection_mode",
        "style_selection_reason",
        "editing_intensity",
        "scene_confidence",
    ):
        response_payload.pop(field)
    original = response_payload.copy()

    response = build_model_response(
        response_payload,
        _request(),
        response_type=AnalyzeResponse,
        expected_resolved_model="gemma-4-31b",
        requested_style_id="auto",
        effective_style_id="stock_neutral",
        style_selection_mode="auto",
        style_selection_reason="Ambiguous scene; broad commercial treatment",
        editing_intensity="moderate",
        scene_confidence=0.0,
    )

    assert response_payload == original
    assert response.schema_version == "1.0"
    assert response.request_id == REQUEST_ID
    assert response.filename == "Identity.NEF"
    assert response.model == "gemma"
    assert response.resolved_model == "gemma-4-31b"


def _legacy_geometry_payload(*, angle_marker=...) -> dict[str, object]:
    payload = _response().model_dump(mode="json")
    for field in (
        "schema_version",
        "request_id",
        "filename",
        "model",
        "resolved_model",
        "requested_style_id",
        "effective_style_id",
        "style_selection_mode",
        "style_selection_reason",
        "editing_intensity",
        "scene_confidence",
        "leveling",
    ):
        payload.pop(field, None)
    crop = {
        "recommended": True,
        "left": 0.03,
        "right": 0.97,
        "top": 0.02,
        "bottom": 0.96,
        "confidence": 0.9,
        "reason": "Improve composition.",
    }
    if angle_marker is not ...:
        crop["angle"] = angle_marker
    payload["crop"] = crop
    return payload


def _build_legacy(payload: dict[str, object]) -> AnalyzeResponse:
    return build_model_response(
        payload,
        _request(),
        response_type=AnalyzeResponse,
        expected_resolved_model="gemma-4-31b",
        requested_style_id="auto",
        effective_style_id="stock_neutral",
        style_selection_mode="auto",
        style_selection_reason="Ambiguous scene; broad commercial treatment",
        editing_intensity="moderate",
        scene_confidence=0.0,
    )


@pytest.mark.parametrize("legacy_angle", [..., None, 0, 0.0])
def test_legacy_missing_null_or_zero_angle_normalizes_to_crop_only(
    legacy_angle: object,
) -> None:
    response = _build_legacy(
        _legacy_geometry_payload(angle_marker=legacy_angle)
    )

    assert response.crop is not None
    assert response.crop.recommended is True
    assert response.leveling.recommended is False
    assert response.leveling.angle == 0
    assert response.leveling.mode == "none"


def test_legacy_nonzero_angle_normalizes_to_leveling_once() -> None:
    response = _build_legacy(_legacy_geometry_payload(angle_marker=-0.72))

    assert response.crop is not None
    assert response.leveling.recommended is True
    assert response.leveling.angle == -0.72
    assert response.leveling.mode == "horizon"
    assert "angle" not in response.crop.model_dump()


def test_legacy_and_new_leveling_sources_are_rejected() -> None:
    payload = _legacy_geometry_payload(angle_marker=-0.72)
    payload["leveling"] = {
        "recommended": True,
        "angle": -0.72,
        "mode": "horizon",
    }

    with pytest.raises(InvalidModelResponseError):
        _build_legacy(payload)
