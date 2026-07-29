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
    assert raised.value.code == "invalid_model_response"


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

    assert raised.value.code == "invalid_model_response"


def test_trusted_envelope_does_not_mutate_provider_payload() -> None:
    response_payload = _response().model_dump(mode="json")
    for field in (
        "schema_version",
        "request_id",
        "filename",
        "model",
        "resolved_model",
    ):
        response_payload.pop(field)
    original = response_payload.copy()

    response = build_model_response(
        response_payload,
        _request(),
        response_type=AnalyzeResponse,
        expected_resolved_model="gemma-4-31b",
    )

    assert response_payload == original
    assert response.schema_version == "1.0"
    assert response.request_id == REQUEST_ID
    assert response.filename == "Identity.NEF"
    assert response.model == "gemma"
    assert response.resolved_model == "gemma-4-31b"
