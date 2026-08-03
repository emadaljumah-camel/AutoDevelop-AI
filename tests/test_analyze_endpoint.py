import asyncio
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autodevelop.api.dependencies import (
    get_model_client,
    get_style_profile_loader,
)
from autodevelop.config import Settings
from autodevelop.main import create_app
from autodevelop.model_clients import (
    FakeModelClient,
    ModelClient,
    ModelClientError,
    ModelRequestError,
    ModelResponseError,
)
from autodevelop.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    DevelopRequest,
    DevelopResponse,
)
from autodevelop.profiles import StyleProfile, StyleProfileLoader

REQUEST_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


def _request_body(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": "1.0",
        "request_id": REQUEST_ID,
        "filename": "Landscape_Test.NEF",
        "model": "gemma",
        "preview_path": "not-read.jpg",
        "options": {
            "style_profile": "natural_travel",
            "include_crop": True,
            "include_denoise": True,
        },
    }
    body.update(changes)
    return body


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    return create_app(
        Settings(
            _env_file=None,
            log_path=tmp_path / "autodevelop.log",
        ),
        model_client=FakeModelClient(),
    )


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


class RecordingModelClient(ModelClient):
    def __init__(self, *, model_name: str = "gemma-4-31b") -> None:
        self.model_name = model_name
        self.awaited = False
        self.request_before: dict[str, Any] | None = None
        self.request_after: dict[str, Any] | None = None

    async def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        self.request_before = request.model_dump()
        await asyncio.sleep(0)
        self.awaited = True
        response = await FakeModelClient(
            model_name=self.model_name,
            scenario="neutral",
        ).analyze(request)
        self.request_after = request.model_dump()
        return response

    async def develop(
        self,
        request: DevelopRequest,
        profile: StyleProfile,
    ) -> DevelopResponse:
        raise NotImplementedError


class RaisingModelClient(ModelClient):
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        raise self.error

    async def develop(
        self,
        request: DevelopRequest,
        profile: StyleProfile,
    ) -> DevelopResponse:
        raise NotImplementedError


class MismatchedAnalyzeModelClient(RecordingModelClient):
    def __init__(self, change: dict[str, object]) -> None:
        super().__init__()
        self.change = change

    async def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        response = await super().analyze(request)
        return response.model_copy(update=self.change)


class RecordingProfileLoader:
    def __init__(self, profile: StyleProfile) -> None:
        self.profile = profile
        self.requested_profile_id: str | None = None

    def get_cached_profile(self, profile_id: str) -> StyleProfile:
        self.requested_profile_id = profile_id
        return self.profile.model_copy(deep=True)


class CountingStyleProfileLoader(StyleProfileLoader):
    def __init__(self) -> None:
        super().__init__()
        self.reload_calls = 0
        self.cached_profile_calls = 0

    def reload_profiles(self) -> list[StyleProfile]:
        self.reload_calls += 1
        return super().reload_profiles()

    def get_cached_profile(self, profile_id: str) -> StyleProfile:
        self.cached_profile_calls += 1
        return super().get_cached_profile(profile_id)


class FailingStyleProfileLoader(StyleProfileLoader):
    def reload_profiles(self) -> list[StyleProfile]:
        raise RuntimeError("profile initialization failed")


def test_lifespan_initializes_and_reuses_one_profile_loader(
    tmp_path: Path,
) -> None:
    loader = CountingStyleProfileLoader()
    application = create_app(
        Settings(
            _env_file=None,
            log_path=tmp_path / "autodevelop.log",
        ),
        profile_loader=loader,
        model_client=FakeModelClient(),
    )

    with TestClient(application) as test_client:
        assert application.state.style_profile_loader is loader
        assert loader.reload_calls == 1

        first = test_client.post(
            "/autodevelop/v1/analyze",
            json=_request_body(),
        )
        second = test_client.post(
            "/autodevelop/v1/analyze",
            json=_request_body(filename="Portrait_Second.NEF"),
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert application.state.style_profile_loader is loader
        assert loader.reload_calls == 1
        assert loader.cached_profile_calls == 4


def test_analyze_requests_use_no_filesystem_after_startup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    application = create_app(
        Settings(
            _env_file=None,
            log_path=tmp_path / "autodevelop.log",
        ),
        model_client=FakeModelClient(),
    )

    with TestClient(application) as test_client:
        def fail(*_: object, **__: object) -> None:
            raise AssertionError("unexpected request-time filesystem access")

        monkeypatch.setattr(Path, "is_file", fail)
        monkeypatch.setattr(Path, "read_text", fail)

        first = test_client.post(
            "/autodevelop/v1/analyze",
            json=_request_body(),
        )
        second = test_client.post(
            "/autodevelop/v1/analyze",
            json=_request_body(filename="Architecture_Second.NEF"),
        )
        unknown_body = _request_body()
        unknown_body["options"]["style_profile"] = "does_not_exist"
        unknown = test_client.post(
            "/autodevelop/v1/analyze",
            json=unknown_body,
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert unknown.status_code == 400
    assert unknown.json()["error"]["code"] == "profile_not_found"


def test_profile_initialization_failure_aborts_startup(
    tmp_path: Path,
) -> None:
    application = create_app(
        Settings(
            _env_file=None,
            log_path=tmp_path / "autodevelop.log",
        ),
        profile_loader=FailingStyleProfileLoader(),
    )

    with pytest.raises(RuntimeError, match="profile initialization failed"):
        with TestClient(application):
            pass


@pytest.mark.parametrize(
    "preview_fields",
    [
        {"preview_path": "not-read.jpg"},
        {"preview_path": None, "preview_base64": "ZmFrZS1wcmV2aWV3"},
    ],
)
def test_valid_preview_request_returns_complete_success(
    client: TestClient,
    preview_fields: dict[str, str | None],
) -> None:
    response = client.post(
        "/autodevelop/v1/analyze",
        json=_request_body(**preview_fields),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == REQUEST_ID
    assert payload["filename"] == "Landscape_Test.NEF"
    assert payload["schema_version"] == "1.0"
    assert payload["model"] == "gemma"
    assert payload["resolved_model"] == "gemma-4-31b"
    assert payload["processing_duration_ms"] == 1
    assert payload["edit_plan"]["style_profile"] == "natural_travel"
    assert payload["analysis"]["scene_type"] == "landscape"
    assert payload["crop"]["recommended"] is True
    assert payload["warnings"] == []


def test_valid_nondefault_profile_is_accepted(client: TestClient) -> None:
    body = _request_body()
    body["options"]["style_profile"] = "architecture"

    response = client.post("/autodevelop/v1/analyze", json=body)

    assert response.status_code == 200
    assert response.json()["edit_plan"]["style_profile"] == "architecture"


def test_documentary_profile_is_accepted(client: TestClient) -> None:
    body = _request_body()
    body["options"]["style_profile"] = "documentary"

    response = client.post("/autodevelop/v1/analyze", json=body)

    assert response.status_code == 200
    assert response.json()["edit_plan"]["style_profile"] == "documentary"


@pytest.mark.parametrize("model_id", ["gemma", "qwen", "gpt_oss"])
def test_selectable_local_models_are_explicitly_accepted(
    client: TestClient,
    model_id: str,
) -> None:
    response = client.post(
        "/autodevelop/v1/analyze",
        json=_request_body(model=model_id),
    )
    assert response.status_code == 200
    assert response.json()["model"] == model_id


@pytest.mark.parametrize(
    ("model_id", "code"),
    [("claude", "model_unavailable"), ("unknown", "model_not_found")],
)
def test_invalid_model_selection_is_structured(
    client: TestClient,
    model_id: str,
    code: str,
) -> None:
    response = client.post(
        "/autodevelop/v1/analyze",
        json=_request_body(model=model_id),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == code


def test_gemini_requires_configuration_and_is_accepted_when_configured(
    tmp_path: Path,
) -> None:
    unconfigured = create_app(
        Settings(_env_file=None, log_path=tmp_path / "unconfigured.log"),
        model_client=FakeModelClient(),
    )
    with TestClient(unconfigured) as test_client:
        response = test_client.post(
            "/autodevelop/v1/analyze",
            json=_request_body(model="gemini"),
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "model_not_configured"

    configured = create_app(
        Settings(
            _env_file=None,
            log_path=tmp_path / "configured.log",
            gemini_api_key="secret",
        ),
        model_client=FakeModelClient(model_name="gemini-2.5-flash"),
    )
    with TestClient(configured) as test_client:
        response = test_client.post(
            "/autodevelop/v1/analyze",
            json=_request_body(model="gemini"),
        )
    assert response.status_code == 200
    assert response.json()["model"] == "gemini"
    assert response.json()["resolved_model"] == "gemini-2.5-flash"


def test_unknown_profile_returns_versioned_error_without_fallback(
    client: TestClient,
) -> None:
    body = _request_body()
    body["options"]["style_profile"] = "does_not_exist"

    response = client.post("/autodevelop/v1/analyze", json=body)

    assert response.status_code == 400
    assert response.json() == {
        "schema_version": "1.0",
        "request_id": REQUEST_ID,
        "filename": "Landscape_Test.NEF",
        "status": "error",
        "error": {
            "code": "profile_not_found",
            "message": "Style profile 'does_not_exist' was not found.",
            "field": None,
            "retryable": False,
        },
        "warnings": [],
    }
    assert "edit_plan" not in response.json()


@pytest.mark.parametrize(
    "body",
    [
        {
            "schema_version": "1.0",
            "request_id": REQUEST_ID,
            "filename": "photo.nef",
        },
        _request_body(filename="   "),
        _request_body(request_id="not-a-uuid"),
        _request_body(unexpected="rejected"),
    ],
)
def test_invalid_request_uses_standard_422(
    client: TestClient,
    body: dict[str, Any],
) -> None:
    response = client.post("/autodevelop/v1/analyze", json=body)

    assert response.status_code == 422
    assert response.json()["detail"]


def test_model_client_dependency_override_is_awaited(
    app: FastAPI,
    client: TestClient,
) -> None:
    model_client = RecordingModelClient()
    app.dependency_overrides[get_model_client] = lambda: model_client

    response = client.post(
        "/autodevelop/v1/analyze",
        json=_request_body(),
    )

    assert response.status_code == 200
    assert response.json()["model"] == "gemma"
    assert response.json()["resolved_model"] == "gemma-4-31b"
    assert model_client.awaited is True


def test_route_does_not_mutate_request(
    app: FastAPI,
    client: TestClient,
) -> None:
    model_client = RecordingModelClient()
    app.dependency_overrides[get_model_client] = lambda: model_client
    body = _request_body()
    body_before = deepcopy(body)

    response = client.post("/autodevelop/v1/analyze", json=body)

    assert response.status_code == 200
    assert body == body_before
    assert model_client.request_before == model_client.request_after


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "2.0"},
        {"request_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"},
        {"filename": "Different.NEF"},
        {"model": "qwen"},
        {"resolved_model": "different-provider-model"},
    ],
)
def test_analyze_rejects_mismatched_response_identity(
    app: FastAPI,
    change: dict[str, object],
) -> None:
    app.dependency_overrides[get_model_client] = lambda: MismatchedAnalyzeModelClient(
        change
    )
    with TestClient(app) as test_client:
        response = test_client.post(
            "/autodevelop/v1/analyze",
            json=_request_body(),
        )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_schema_mismatch"


def test_analyze_identity_failure_does_not_expose_or_log_bad_value(
    app: FastAPI,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "secret-provider-value"
    app.dependency_overrides[get_model_client] = lambda: MismatchedAnalyzeModelClient(
        {"resolved_model": secret}
    )
    with TestClient(app) as test_client:
        response = test_client.post(
            "/autodevelop/v1/analyze",
            json=_request_body(),
        )
    assert response.status_code == 502
    assert secret not in response.text
    assert secret not in caplog.text


def test_analyze_logs_base64_transport_without_image_content(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    encoded = "ZmFrZS1wcmV2aWV3"

    response = client.post(
        "/autodevelop/v1/analyze",
        json=_request_body(preview_path=None, preview_base64=encoded),
    )

    assert response.status_code == 200
    assert "preview_source=preview_base64" in caplog.text
    assert encoded not in caplog.text


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code", "retryable"),
    [
        (
            ModelRequestError("bad request", model_name="stub"),
            400,
            "model_request_error",
            False,
        ),
        (
            ModelResponseError("bad response", model_name="stub"),
            502,
            "model_response_error",
            True,
        ),
        (
            ModelClientError("model unavailable", model_name="stub"),
            502,
            "model_client_error",
            True,
        ),
        (
            RuntimeError("secret path C:\\private\\model.bin"),
            500,
            "internal_error",
            True,
        ),
    ],
)
def test_client_errors_map_to_safe_error_response(
    app: FastAPI,
    client: TestClient,
    error: Exception,
    expected_status: int,
    expected_code: str,
    retryable: bool,
) -> None:
    app.dependency_overrides[get_model_client] = lambda: RaisingModelClient(error)

    response = client.post(
        "/autodevelop/v1/analyze",
        json=_request_body(),
    )

    assert response.status_code == expected_status
    payload = response.json()
    assert payload["schema_version"] == "1.0"
    assert payload["request_id"] == REQUEST_ID
    assert payload["filename"] == "Landscape_Test.NEF"
    assert payload["status"] == "error"
    assert payload["error"]["code"] == expected_code
    assert payload["error"]["retryable"] is retryable


def test_internal_error_does_not_expose_raw_exception(
    app: FastAPI,
    client: TestClient,
) -> None:
    secret = "secret path C:\\private\\model.bin"
    app.dependency_overrides[get_model_client] = lambda: RaisingModelClient(
        RuntimeError(secret)
    )

    response = client.post(
        "/autodevelop/v1/analyze",
        json=_request_body(),
    )

    assert response.status_code == 500
    assert secret not in response.text
    assert response.json()["error"]["message"] == (
        "An internal error occurred while analyzing the photo."
    )


def test_style_profile_loader_dependency_can_be_overridden(
    app: FastAPI,
    client: TestClient,
) -> None:
    profile = StyleProfileLoader().get_profile("natural_travel")
    loader = RecordingProfileLoader(profile)
    app.dependency_overrides[get_style_profile_loader] = lambda: loader
    body = _request_body()
    body["options"]["style_profile"] = "natural_travel"

    response = client.post("/autodevelop/v1/analyze", json=body)

    assert response.status_code == 200
    assert loader.requested_profile_id == "natural_travel"
    assert response.json()["edit_plan"]["style_profile"] == "natural_travel"


def test_health_endpoint_still_works(client: TestClient) -> None:
    response = client.get("/autodevelop/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_openapi_documents_analyze_models_and_errors(
    client: TestClient,
) -> None:
    document = client.get("/openapi.json").json()
    operation = document["paths"]["/autodevelop/v1/analyze"]["post"]

    request_schema = operation["requestBody"]["content"]["application/json"][
        "schema"
    ]
    success_schema = operation["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert request_schema["$ref"].endswith("/AnalyzeRequest")
    assert success_schema["$ref"].endswith("/AnalyzeResponse")
    for status_code in ("400", "500", "502"):
        error_schema = operation["responses"][status_code]["content"][
            "application/json"
        ]["schema"]
        assert error_schema["$ref"].endswith("/ErrorResponse")
