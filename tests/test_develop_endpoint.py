import asyncio
from collections.abc import Callable, Iterator
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autodevelop.api.dependencies import (
    get_model_client,
    get_safety_validator,
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
    CropRecommendation,
    DenoiseRecommendation,
    DevelopRequest,
    DevelopResponse,
    DevelopSettings,
    EditPlan,
    HdrRecommendation,
    LevelingRecommendation,
    ProcessingWarning,
    ProcessingOptions,
    TechnicalAnalysis,
    UprightRecommendation,
)
from autodevelop.profiles import (
    ProfileNotFoundError,
    StyleProfile,
    StyleProfileLoader,
)
from autodevelop.validation import SafetyValidator, ValidationResult
from autodevelop.validation import policies

REQUEST_ID = "88888888-8888-4888-8888-888888888888"
OTHER_REQUEST_ID = "99999999-9999-4999-8999-999999999999"


def _request_body(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": "1.0",
        "request_id": REQUEST_ID,
        "filename": "Landscape_Test.NEF",
        "model": "gemma",
        "preview_path": "not-read.jpg",
        "exif": {"iso": 1600},
        "options": {
            "style_profile": "natural_travel",
            "include_crop": True,
            "include_denoise": True,
        },
    }
    body.update(changes)
    return body


def _raw_response(
    request: DevelopRequest,
    *,
    settings: DevelopSettings | None = None,
    crop: CropRecommendation | None = None,
    leveling: LevelingRecommendation | None = None,
    upright: UprightRecommendation | None = None,
    analysis: TechnicalAnalysis | None = None,
    denoise: DenoiseRecommendation | None = None,
    warnings: list[ProcessingWarning] | None = None,
    model: str | None = None,
) -> DevelopResponse:
    return DevelopResponse(
        schema_version="1.0",
        request_id=request.request_id,
        filename=request.filename,
        status="success",
        analysis=analysis,
        edit_plan=EditPlan(
            style_profile=request.options.style_profile,
            goals=["Produce a safe recommendation"],
            cautions=["Preserve source detail"],
        ),
        develop_settings=settings or DevelopSettings(Exposure2012=0.25),
        crop=crop,
        leveling=leveling or LevelingRecommendation(
            recommended=False,
            angle=0,
            mode="none",
        ),
        upright=upright or UprightRecommendation(recommended=False),
        denoise=denoise,
        warnings=warnings or [],
        model=model or request.model,
        resolved_model={
            "gemma": "gemma-4-31b",
            "qwen": "qwen_qwen3-vl-32b-instruct",
            "gpt_oss": "gpt-oss",
            "gemini": "gemini-2.5-flash",
        }[request.model or "gemma"],
        processing_duration_ms=17,
    )


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
    def __init__(
        self,
        response_factory: Callable[[DevelopRequest], object] = _raw_response,
    ) -> None:
        self.response_factory = response_factory
        self.develop_calls = 0
        self.awaited = False
        self.request: DevelopRequest | None = None
        self.request_before: dict[str, Any] | None = None
        self.raw_response: object | None = None
        self.raw_response_before: dict[str, Any] | None = None

    async def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        return await FakeModelClient().analyze(request)

    async def develop(self, request: DevelopRequest) -> DevelopResponse:
        self.develop_calls += 1
        self.request = request
        self.request_before = request.model_dump()
        await asyncio.sleep(0)
        self.awaited = True
        response = self.response_factory(request)
        self.raw_response = response
        if isinstance(response, DevelopResponse):
            self.raw_response_before = response.model_dump()
        return response  # type: ignore[return-value]


class RaisingModelClient(ModelClient):
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.develop_calls = 0

    async def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        raise NotImplementedError

    async def develop(self, request: DevelopRequest) -> DevelopResponse:
        self.develop_calls += 1
        raise self.error


class RecordingProfileLoader:
    def __init__(self, profile: StyleProfile) -> None:
        self.profile = profile
        self.requested_ids: list[str] = []

    def get_cached_profile(self, profile_id: str) -> StyleProfile:
        self.requested_ids.append(profile_id)
        return self.profile


class MissingProfileLoader:
    def __init__(self) -> None:
        self.requested_ids: list[str] = []

    def get_cached_profile(self, profile_id: str) -> StyleProfile:
        self.requested_ids.append(profile_id)
        raise ProfileNotFoundError(profile_id)


class CountingStyleProfileLoader(StyleProfileLoader):
    def __init__(self) -> None:
        super().__init__()
        self.reload_calls = 0
        self.cached_calls = 0

    def reload_profiles(self) -> list[StyleProfile]:
        self.reload_calls += 1
        return super().reload_profiles()

    def get_cached_profile(self, profile_id: str) -> StyleProfile:
        self.cached_calls += 1
        return super().get_cached_profile(profile_id)


class RecordingSafetyValidator(SafetyValidator):
    def __init__(self) -> None:
        self.calls = 0
        self.settings: DevelopSettings | None = None
        self.crop: CropRecommendation | None = None
        self.denoise: DenoiseRecommendation | None = None
        self.profile: StyleProfile | None = None
        self.enable_hdr: HdrRecommendation | None = None
        self.leveling: LevelingRecommendation | None = None
        self.upright: UprightRecommendation | None = None

    def validate(
        self,
        *,
        settings: DevelopSettings | None,
        crop: CropRecommendation | None,
        denoise: DenoiseRecommendation | None,
        profile: StyleProfile,
        enable_hdr: HdrRecommendation | None = None,
        leveling: LevelingRecommendation | None = None,
        upright: UprightRecommendation | None = None,
        analysis: TechnicalAnalysis | None = None,
        options: ProcessingOptions | None = None,
        iso: int | None = None,
    ) -> ValidationResult:
        self.calls += 1
        self.settings = settings
        self.crop = crop
        self.denoise = denoise
        self.profile = profile
        self.enable_hdr = enable_hdr
        self.leveling = leveling
        self.upright = upright
        return super().validate(
            settings=settings,
            crop=crop,
            denoise=denoise,
            profile=profile,
            enable_hdr=enable_hdr,
            leveling=leveling,
            upright=upright,
            analysis=analysis,
            options=options,
            iso=iso,
        )


class RaisingSafetyValidator(SafetyValidator):
    def __init__(self, error: Exception) -> None:
        self.error = error

    def validate(self, **_kwargs) -> ValidationResult:
        raise self.error


def _set_overrides(
    app: FastAPI,
    *,
    model_client: ModelClient | None = None,
    profile_loader: object | None = None,
    safety_validator: SafetyValidator | None = None,
) -> None:
    if model_client is not None:
        async def model_dependency() -> ModelClient:
            return model_client

        app.dependency_overrides[get_model_client] = model_dependency
    if profile_loader is not None:
        async def profile_dependency() -> object:
            return profile_loader

        app.dependency_overrides[get_style_profile_loader] = profile_dependency
    if safety_validator is not None:
        async def validator_dependency() -> SafetyValidator:
            return safety_validator

        app.dependency_overrides[get_safety_validator] = validator_dependency


def test_valid_request_uses_real_fake_client_and_validator(
    client: TestClient,
) -> None:
    response = client.post("/autodevelop/v1/develop", json=_request_body())

    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == REQUEST_ID
    assert payload["filename"] == "Landscape_Test.NEF"
    assert payload["schema_version"] == "1.0"
    assert payload["model"] == "gemma"
    assert payload["resolved_model"] == "gemma-4-31b"
    assert payload["processing_duration_ms"] == 1
    assert payload["edit_plan"]["style_profile"] == "natural_travel"
    assert payload["develop_settings"]["Exposure2012"] == 0.1


def test_develop_logs_base64_transport_without_image_content(
    app: FastAPI,
    capfd: pytest.CaptureFixture[str],
) -> None:
    encoded = "ZmFrZS1wcmV2aWV3"

    with TestClient(app) as client:
        response = client.post(
            "/autodevelop/v1/develop",
            json=_request_body(
                preview_path=None,
                preview_base64=encoded,
            ),
        )

    assert response.status_code == 200
    captured = capfd.readouterr()
    assert "preview_source=preview_base64" in captured.err
    assert encoded not in captured.err


def test_valid_nondefault_profile_is_authoritative(
    client: TestClient,
) -> None:
    body = _request_body()
    body["options"]["style_profile"] = "stock_neutral"

    response = client.post("/autodevelop/v1/develop", json=body)

    assert response.status_code == 200
    payload = response.json()
    assert payload["edit_plan"]["style_profile"] == "stock_neutral"
    assert payload["develop_settings"]["Contrast2012"] == 12.0


def test_documentary_profile_is_authoritative(client: TestClient) -> None:
    body = _request_body()
    body["options"]["style_profile"] = "documentary"

    response = client.post("/autodevelop/v1/develop", json=body)

    assert response.status_code == 200
    assert response.json()["edit_plan"]["style_profile"] == "documentary"


@pytest.mark.parametrize("model_id", ["gemma", "qwen", "gpt_oss"])
def test_develop_accepts_selectable_local_models(
    client: TestClient,
    model_id: str,
) -> None:
    response = client.post(
        "/autodevelop/v1/develop",
        json=_request_body(model=model_id),
    )
    assert response.status_code == 200
    assert response.json()["model"] == model_id


@pytest.mark.parametrize(
    ("model_id", "code"),
    [("claude", "model_unavailable"), ("unknown", "model_not_found")],
)
def test_develop_rejects_invalid_model_selection(
    client: TestClient,
    model_id: str,
    code: str,
) -> None:
    response = client.post(
        "/autodevelop/v1/develop",
        json=_request_body(model=model_id),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == code


def test_unknown_profile_returns_error_without_model_call(
    app: FastAPI,
) -> None:
    model_client = RecordingModelClient()
    profile_loader = MissingProfileLoader()
    _set_overrides(
        app,
        model_client=model_client,
        profile_loader=profile_loader,
    )

    with TestClient(app) as client:
        response = client.post(
            "/autodevelop/v1/develop",
            json=_request_body(
                options={
                    "style_profile": "does_not_exist",
                    "include_crop": True,
                    "include_denoise": True,
                }
            ),
        )

    assert response.status_code == 400
    assert response.json() == {
        "schema_version": "1.0",
        "request_id": REQUEST_ID,
        "filename": "Landscape_Test.NEF",
        "status": "error",
        "error": {
            "code": "profile_not_found",
            "message": "Style profile 'does_not_exist' was not found.",
            "retryable": False,
            "field": None,
        },
        "warnings": [],
    }
    assert profile_loader.requested_ids == ["does_not_exist"]
    assert model_client.develop_calls == 0


@pytest.mark.parametrize(
    "body",
    [
        {},
        _request_body(filename="   "),
        _request_body(request_id="not-a-uuid"),
        {
            key: value
            for key, value in _request_body().items()
            if key != "preview_path"
        },
        _request_body(unexpected=True),
    ],
)
def test_invalid_request_returns_422(
    client: TestClient,
    body: dict[str, Any],
) -> None:
    response = client.post("/autodevelop/v1/develop", json=body)

    assert response.status_code == 422


def test_injected_dependencies_are_used_and_inputs_are_not_mutated(
    app: FastAPI,
) -> None:
    profile = StyleProfileLoader().get_profile("natural_travel")
    profile_before = profile.model_dump()
    profile_loader = RecordingProfileLoader(profile)
    model_client = RecordingModelClient()
    validator = RecordingSafetyValidator()
    _set_overrides(
        app,
        model_client=model_client,
        profile_loader=profile_loader,
        safety_validator=validator,
    )

    with TestClient(app) as client:
        response = client.post("/autodevelop/v1/develop", json=_request_body())

    assert response.status_code == 200
    assert model_client.awaited
    assert model_client.develop_calls == 1
    assert model_client.request is not None
    assert model_client.request.model_dump() == model_client.request_before
    assert isinstance(model_client.raw_response, DevelopResponse)
    assert model_client.raw_response.model_dump() == model_client.raw_response_before
    assert validator.calls == 1
    assert validator.settings is model_client.raw_response.develop_settings
    assert validator.crop is model_client.raw_response.crop
    assert validator.denoise is model_client.raw_response.denoise
    assert validator.profile is profile
    assert profile.model_dump() == profile_before
    assert profile_loader.requested_ids == ["natural_travel"]


def test_develop_adds_lightroom_level_fallback_without_another_model_call(
    app: FastAPI,
) -> None:
    model_client = RecordingModelClient()
    validator = RecordingSafetyValidator()
    _set_overrides(
        app,
        model_client=model_client,
        safety_validator=validator,
    )

    with TestClient(app) as client:
        response = client.post("/autodevelop/v1/develop", json=_request_body())

    assert response.status_code == 200
    assert model_client.develop_calls == 1
    assert validator.upright is not None
    assert validator.upright.recommended is True
    assert validator.upright.mode == "level"
    assert response.json()["upright"]["mode"] == "level"


def test_settings_are_sanitized_without_inventing_values(
    app: FastAPI,
) -> None:
    raw_settings = DevelopSettings(
        Exposure2012=5.0,
        Contrast2012=0.0,
        Temperature=None,
        CropLeft=0.1,
    )
    model_client = RecordingModelClient(
        lambda request: _raw_response(request, settings=raw_settings)
    )
    _set_overrides(app, model_client=model_client)

    with TestClient(app) as client:
        response = client.post("/autodevelop/v1/develop", json=_request_body())

    assert response.status_code == 200
    settings = response.json()["develop_settings"]
    assert settings["Exposure2012"] == 1.0
    assert settings["Contrast2012"] == 0.0
    assert settings["Temperature"] is None
    assert settings["CropLeft"] is None
    assert settings["Texture"] is None
    warning_codes = [warning["code"] for warning in response.json()["warnings"]]
    assert warning_codes == [
        policies.SLIDER_CLAMPED_HIGH,
        policies.SLIDER_NOT_ALLOWED,
    ]


def _valid_crop(**changes: object) -> CropRecommendation:
    values: dict[str, object] = {
        "recommended": True,
        "left": 0.05,
        "right": 0.95,
        "top": 0.05,
        "bottom": 0.95,
        "confidence": 0.9,
        "reason": "Improve alignment.",
    }
    values.update(changes)
    return CropRecommendation.model_validate(values)


@pytest.mark.parametrize(
    ("crop", "expected_crop", "expected_code"),
    [
        (_valid_crop(), "preserved", None),
        (
            _valid_crop(left=0.13),
            None,
            policies.CROP_EDGE_LIMIT_EXCEEDED,
        ),
        (
            _valid_crop(left=0.12, right=0.88, top=0.12, bottom=0.88),
            None,
            policies.CROP_AREA_TOO_SMALL,
        ),
    ],
)
def test_crop_is_sanitized_by_profile_policy(
    app: FastAPI,
    crop: CropRecommendation,
    expected_crop: str | None,
    expected_code: str | None,
) -> None:
    model_client = RecordingModelClient(
        lambda request: _raw_response(request, crop=crop)
    )
    _set_overrides(app, model_client=model_client)

    with TestClient(app) as client:
        response = client.post("/autodevelop/v1/develop", json=_request_body())

    assert response.status_code == 200
    payload = response.json()
    if expected_crop is None:
        assert payload["crop"] is None
    elif expected_crop == "preserved":
        assert payload["crop"] == crop.model_dump(mode="json")
    if expected_code is not None:
        assert expected_code in {
            warning["code"] for warning in payload["warnings"]
        }


@pytest.mark.parametrize(
    ("denoise", "expected"),
    [
        (None, None),
        (
            DenoiseRecommendation(
                recommended=True,
                amount=20.0,
                confidence=0.9,
            ),
                25.0,
        ),
        (
            DenoiseRecommendation(
                recommended=True,
                amount=90.0,
                confidence=0.9,
            ),
                25.0,
        ),
        (
            DenoiseRecommendation(
                recommended=False,
                amount=None,
                confidence=0.9,
            ),
            False,
        ),
    ],
)
def test_denoise_is_sanitized_by_profile_policy(
    app: FastAPI,
    denoise: DenoiseRecommendation | None,
    expected: float | bool | None,
) -> None:
    model_client = RecordingModelClient(
        lambda request: _raw_response(request, denoise=denoise)
    )
    _set_overrides(app, model_client=model_client)

    with TestClient(app) as client:
        response = client.post("/autodevelop/v1/develop", json=_request_body())

    assert response.status_code == 200
    safe_denoise = response.json()["denoise"]
    if expected is None:
        assert safe_denoise is None
    elif expected is False:
        assert safe_denoise["recommended"] is False
        assert safe_denoise["amount"] is None
    else:
        assert safe_denoise["recommended"] is True
        assert safe_denoise["amount"] == expected


def test_iso_3600_raw_forces_denoise_before_profile_limiting(
    app: FastAPI,
) -> None:
    model_client = RecordingModelClient(
        lambda request: _raw_response(
            request,
            denoise=DenoiseRecommendation(
                recommended=False,
                amount=None,
                confidence=0.2,
                reason="The preview appears clean.",
            ),
        )
    )
    validator = RecordingSafetyValidator()
    _set_overrides(
        app,
        model_client=model_client,
        safety_validator=validator,
    )

    with TestClient(app) as client:
        response = client.post(
            "/autodevelop/v1/develop",
            json=_request_body(exif={"iso": 3600, "file_format": "RAW"}),
        )

    assert response.status_code == 200
    assert validator.denoise is not None
    assert validator.denoise.recommended is True
    assert validator.denoise.amount == 50.0
    assert validator.denoise.confidence == 0.9
    assert response.json()["denoise"]["recommended"] is True
    assert response.json()["denoise"]["amount"] == 25.0


def test_model_and_validator_warnings_merge_deterministically_without_duplicates(
    app: FastAPI,
) -> None:
    duplicate = ProcessingWarning(
        code=policies.SLIDER_CLAMPED_HIGH,
        message="Exposure2012 was clamped to the profile maximum.",
        field="Exposure2012",
        severity="warning",
    )
    model_only = ProcessingWarning(
        code="model_observation",
        message="Model supplied an observation.",
        field=None,
        severity="info",
    )
    model_client = RecordingModelClient(
        lambda request: _raw_response(
            request,
            settings=DevelopSettings(Exposure2012=5.0),
            warnings=[model_only, duplicate],
        )
    )
    _set_overrides(app, model_client=model_client)

    with TestClient(app) as client:
        response = client.post("/autodevelop/v1/develop", json=_request_body())

    warnings = response.json()["warnings"]
    assert [warning["code"] for warning in warnings] == [
        "model_observation",
        policies.SLIDER_CLAMPED_HIGH,
    ]


@pytest.mark.parametrize(
    ("change", "expected_code"),
    [
        ({"request_id": UUID(OTHER_REQUEST_ID)}, "provider_schema_mismatch"),
        ({"filename": "Different.NEF"}, "provider_schema_mismatch"),
        ({"schema_version": "2.0"}, "provider_schema_mismatch"),
        ({"status": "partial"}, "provider_schema_mismatch"),
        ({"model": None}, "provider_schema_mismatch"),
    ],
)
def test_invalid_model_metadata_returns_502(
    app: FastAPI,
    change: dict[str, object],
    expected_code: str,
) -> None:
    def response_factory(request: DevelopRequest) -> DevelopResponse:
        return _raw_response(request).model_copy(update=change)

    _set_overrides(
        app,
        model_client=RecordingModelClient(response_factory),
    )

    with TestClient(app) as client:
        response = client.post("/autodevelop/v1/develop", json=_request_body())

    assert response.status_code == 502
    assert response.json()["error"]["code"] == expected_code


def test_unexpected_model_response_type_returns_502(app: FastAPI) -> None:
    _set_overrides(
        app,
        model_client=RecordingModelClient(lambda _request: {"invalid": True}),
    )

    with TestClient(app) as client:
        response = client.post("/autodevelop/v1/develop", json=_request_body())

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_schema_mismatch"


@pytest.mark.parametrize(
    ("error", "status_code", "code", "retryable"),
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
            ModelClientError("client failed", model_name="stub"),
            502,
            "model_client_error",
            True,
        ),
    ],
)
def test_model_client_errors_are_mapped(
    app: FastAPI,
    error: Exception,
    status_code: int,
    code: str,
    retryable: bool,
) -> None:
    _set_overrides(app, model_client=RaisingModelClient(error))

    with TestClient(app) as client:
        response = client.post("/autodevelop/v1/develop", json=_request_body())

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["retryable"] is retryable


def test_validator_internal_error_is_safe(app: FastAPI) -> None:
    secret = "private C:\\model\\prompt.txt"
    _set_overrides(
        app,
        model_client=RecordingModelClient(),
        safety_validator=RaisingSafetyValidator(RuntimeError(secret)),
    )

    with TestClient(app) as client:
        response = client.post("/autodevelop/v1/develop", json=_request_body())

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "validation_internal_error"
    assert response.json()["error"]["retryable"] is True
    assert secret not in response.text


def test_unexpected_model_error_is_safe(app: FastAPI) -> None:
    secret = "private C:\\model\\prompt.txt"
    _set_overrides(
        app,
        model_client=RaisingModelClient(RuntimeError(secret)),
    )

    with TestClient(app) as client:
        response = client.post("/autodevelop/v1/develop", json=_request_body())

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert secret not in response.text


def test_request_uses_only_cached_profiles_after_startup(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(app) as client:
        def fail(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("filesystem accessed during Develop request")

        monkeypatch.setattr(Path, "read_text", fail)
        monkeypatch.setattr(Path, "is_file", fail)

        first = client.post("/autodevelop/v1/develop", json=_request_body())
        second = client.post("/autodevelop/v1/develop", json=_request_body())

    assert first.status_code == 200
    assert second.status_code == 200


def test_application_scoped_loader_and_validator_are_reused(
    tmp_path: Path,
) -> None:
    loader = CountingStyleProfileLoader()
    validator = RecordingSafetyValidator()
    app = create_app(
        Settings(_env_file=None, log_path=tmp_path / "autodevelop.log"),
        profile_loader=loader,
        safety_validator=validator,
    )
    model_client = RecordingModelClient()
    _set_overrides(app, model_client=model_client)

    with TestClient(app) as client:
        assert app.state.style_profile_loader is loader
        assert app.state.safety_validator is validator
        assert client.get("/autodevelop/v1/health").status_code == 200
        assert client.post(
            "/autodevelop/v1/develop",
            json=_request_body(),
        ).status_code == 200
        assert client.post(
            "/autodevelop/v1/develop",
            json=_request_body(),
        ).status_code == 200

    assert loader.reload_calls == 1
    assert loader.cached_calls == 2
    assert validator.calls == 2
    assert model_client.develop_calls == 2


def test_analyze_and_health_endpoints_remain_available(
    client: TestClient,
) -> None:
    analyze_response = client.post(
        "/autodevelop/v1/analyze",
        json=_request_body(),
    )
    health_response = client.get("/autodevelop/v1/health")

    assert analyze_response.status_code == 200
    assert health_response.status_code == 200


def test_openapi_documents_develop_contract(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/autodevelop/v1/develop"]["post"]

    request_schema = operation["requestBody"]["content"][
        "application/json"
    ]["schema"]
    success_schema = operation["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert request_schema["$ref"].endswith("/DevelopRequest")
    assert success_schema["$ref"].endswith("/DevelopResponse")
    for status_code in ("400", "500", "502"):
        error_schema = operation["responses"][status_code]["content"][
            "application/json"
        ]["schema"]
        assert error_schema["$ref"].endswith("/ErrorResponse")


def test_response_objects_are_independent_of_raw_model_output(
    app: FastAPI,
) -> None:
    model_warning = ProcessingWarning(
        code="raw_warning",
        message="Raw warning.",
        severity="info",
    )
    model_client = RecordingModelClient(
        lambda request: _raw_response(request, warnings=[model_warning])
    )
    _set_overrides(app, model_client=model_client)

    with TestClient(app) as client:
        response = client.post("/autodevelop/v1/develop", json=_request_body())

    assert response.status_code == 200
    assert isinstance(model_client.raw_response, DevelopResponse)
    assert model_client.raw_response.model_dump() == model_client.raw_response_before
    returned = deepcopy(response.json())
    returned["warnings"][0]["message"] = "changed"
    assert model_client.raw_response.warnings[0].message == "Raw warning."
