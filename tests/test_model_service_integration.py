import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from autodevelop.config import Settings
from autodevelop.main import create_app
from autodevelop.model_clients import FakeModelClient, ModelResolver
from autodevelop.model_clients.clients import LocalOpenAIClient
from autodevelop.models import AnalyzeRequest, DevelopRequest
from autodevelop.validation import SafetyValidator

REQUEST_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
IDENTITY_FIELDS = (
    "schema_version",
    "request_id",
    "filename",
    "model",
    "resolved_model",
)


class RecordingSafetyValidator(SafetyValidator):
    def __init__(self) -> None:
        self.called = False

    def validate(self, **kwargs):
        self.called = True
        return super().validate(**kwargs)


def _request_body(endpoint: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": "1.0",
        "request_id": REQUEST_ID,
        "filename": "Integration.NEF",
        "model": "gemma",
        "preview_base64": "aW1hZ2U=",
        "options": {"style_profile": "natural_travel"},
    }
    if endpoint == "develop":
        body["options"].update(
            {
                "include_crop": True,
                "include_denoise": True,
                "dry_run": False,
                "preserve_current_adjustments": True,
            }
        )
    return body


def _valid_provider_payload(
    endpoint: str,
    *,
    include_identity: bool = False,
) -> dict[str, Any]:
    body = _request_body(endpoint)
    if endpoint == "analyze":
        request = AnalyzeRequest.model_validate(body)
        response = asyncio.run(
            FakeModelClient(model_name="gemma-4-31b").analyze(request)
        )
    else:
        request = DevelopRequest.model_validate(body)
        response = asyncio.run(
            FakeModelClient(model_name="gemma-4-31b").develop(request)
        )
    payload = response.model_dump(mode="json")
    if not include_identity:
        for field in IDENTITY_FIELDS:
            payload.pop(field)
    return payload


def _invoke_route(
    tmp_path: Path,
    endpoint: str,
    content: str,
    *,
    safety_validator: SafetyValidator | None = None,
) -> tuple[httpx.Response, str, int]:
    provider_calls = 0
    provider_secret = "provider-secret-must-not-leak"

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal provider_calls
        provider_calls += 1
        assert request.url.host == "provider.test"
        assert request.headers["authorization"] == f"Bearer {provider_secret}"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
        )

    transport_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://provider.test/v1/",
    )
    provider_client = LocalOpenAIClient(
        base_url="http://provider.test/v1",
        api_key=provider_secret,
        model="gemma-4-31b",
        timeout_seconds=10,
        client=transport_client,
    )
    log_path = tmp_path / f"{endpoint}.log"
    settings = Settings(
        _env_file=None,
        log_path=log_path,
        local_api_key=provider_secret,
        gemma_model="gemma-4-31b",
    )
    resolver = ModelResolver(
        settings,
        provider_clients={"gemma": provider_client},
    )
    app = create_app(
        settings,
        safety_validator=safety_validator,
        model_resolver=resolver,
    )
    with TestClient(app) as client:
        response = client.post(
            f"/autodevelop/v1/{endpoint}",
            json=_request_body(endpoint),
        )
    asyncio.run(transport_client.aclose())
    return response, log_path.read_text(encoding="utf-8"), provider_calls


@pytest.mark.parametrize("endpoint", ["analyze", "develop"])
@pytest.mark.parametrize(
    "render",
    [
        pytest.param(
            lambda payload: json.dumps(payload),
            id="plain-json",
        ),
        pytest.param(
            lambda payload: f"```json\n{json.dumps(payload)}\n```",
            id="fenced-json",
        ),
    ],
)
def test_real_model_service_accepts_valid_provider_content(
    tmp_path: Path,
    endpoint: str,
    render: Callable[[dict[str, Any]], str],
) -> None:
    validator = RecordingSafetyValidator()
    response, log_text, calls = _invoke_route(
        tmp_path,
        endpoint,
        render(_valid_provider_payload(endpoint)),
        safety_validator=validator,
    )

    assert response.status_code == 200
    assert response.json()["request_id"] == REQUEST_ID
    assert response.json()["filename"] == "Integration.NEF"
    assert response.json()["model"] == "gemma"
    assert response.json()["resolved_model"] == "gemma-4-31b"
    assert calls == 1
    assert "provider-secret-must-not-leak" not in response.text
    assert "provider-secret-must-not-leak" not in log_text
    assert validator.called is (endpoint == "develop")


@pytest.mark.parametrize("endpoint", ["analyze", "develop"])
def test_matching_optional_provider_identity_echoes_are_accepted(
    tmp_path: Path,
    endpoint: str,
) -> None:
    response, _, calls = _invoke_route(
        tmp_path,
        endpoint,
        json.dumps(_valid_provider_payload(endpoint, include_identity=True)),
    )

    assert response.status_code == 200
    assert calls == 1


@pytest.mark.parametrize("endpoint", ["analyze", "develop"])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "2.0"),
        ("request_id", "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"),
        ("filename", "Different.NEF"),
        ("model", "qwen"),
        ("resolved_model", "different-provider-model"),
    ],
)
def test_real_model_service_rejects_provider_identity_mismatch(
    tmp_path: Path,
    endpoint: str,
    field: str,
    value: str,
) -> None:
    marker = "raw-provider-marker"
    payload = _valid_provider_payload(endpoint, include_identity=True)
    payload[field] = value
    payload["warnings"] = [
        {
            "code": "provider_marker",
            "message": marker,
            "severity": "warning",
        }
    ]

    response, log_text, calls = _invoke_route(
        tmp_path,
        endpoint,
        json.dumps(payload),
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_model_response"
    assert marker not in response.text
    assert marker not in log_text
    assert value not in response.text
    if field == "model":
        assert f"model={value}" not in log_text
    else:
        assert value not in log_text
    assert calls == 1


@pytest.mark.parametrize("endpoint", ["analyze", "develop"])
@pytest.mark.parametrize(
    "content",
    [
        "raw-provider-marker non-json",
        '{"status": "raw-provider-marker"',
        '["raw-provider-marker"]',
        "{}",
    ],
    ids=["non-json", "truncated-json", "top-level-array", "invalid-object"],
)
def test_real_model_service_maps_malformed_output_safely(
    tmp_path: Path,
    endpoint: str,
    content: str,
) -> None:
    response, log_text, calls = _invoke_route(tmp_path, endpoint, content)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_model_response"
    assert content not in response.text
    assert content not in log_text
    assert "provider-secret-must-not-leak" not in response.text
    assert "provider-secret-must-not-leak" not in log_text
    assert calls == 1
