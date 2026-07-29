from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from autodevelop.api.model_selection import resolve_model_request
from autodevelop.config import Settings
from autodevelop.main import create_app
from autodevelop.model_clients import FakeModelClient, ModelResolver
from autodevelop.models import AnalyzeRequest

_OMITTED = object()


def _body(
    *,
    endpoint: str,
    model: str | None | object = _OMITTED,
) -> dict[str, object]:
    body: dict[str, object] = {
        "schema_version": "1.0",
        "request_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "filename": "Default_Model.NEF",
        "preview_path": "not-read.jpg",
        "options": {"style_profile": "natural_travel"},
    }
    if model is not _OMITTED:
        body["model"] = model
    if endpoint == "develop":
        body["options"] = {
            "style_profile": "natural_travel",
            "include_crop": True,
            "include_denoise": True,
        }
    return body


@pytest.mark.parametrize("endpoint", ["analyze", "develop"])
@pytest.mark.parametrize("default_model", ["gemma", "qwen", "gpt_oss"])
def test_omitted_model_uses_configured_default(
    tmp_path: Path,
    endpoint: str,
    default_model: str,
) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            default_model=default_model,
            log_path=tmp_path / f"{endpoint}-{default_model}.log",
        ),
        model_client=FakeModelClient(),
    )
    with TestClient(app) as client:
        response = client.post(
            f"/autodevelop/v1/{endpoint}",
            json=_body(endpoint=endpoint),
        )
    assert response.status_code == 200
    assert response.json()["model"] == default_model


@pytest.mark.parametrize("endpoint", ["analyze", "develop"])
def test_explicit_model_overrides_default(
    tmp_path: Path,
    endpoint: str,
) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            default_model="qwen",
            log_path=tmp_path / f"{endpoint}.log",
        ),
        model_client=FakeModelClient(),
    )
    with TestClient(app) as client:
        response = client.post(
            f"/autodevelop/v1/{endpoint}",
            json=_body(model="gemma", endpoint=endpoint),
        )
    assert response.status_code == 200
    assert response.json()["model"] == "gemma"


def test_normalization_does_not_mutate_wire_request() -> None:
    request = AnalyzeRequest.model_validate(_body(endpoint="analyze"))
    settings = Settings(_env_file=None, default_model="qwen")

    selection = resolve_model_request(
        request,
        settings=settings,
        resolver=ModelResolver(settings),
    )

    assert request.model is None
    assert selection.request.model == "qwen"
    assert selection.source == "default"


@pytest.mark.parametrize("endpoint", ["analyze", "develop"])
def test_explicit_null_model_is_rejected_without_default_fallback(
    tmp_path: Path,
    endpoint: str,
) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            default_model="qwen",
            log_path=tmp_path / f"{endpoint}-null.log",
        ),
        model_client=FakeModelClient(),
    )
    with TestClient(app) as client:
        response = client.post(
            f"/autodevelop/v1/{endpoint}",
            json=_body(endpoint=endpoint, model=None),
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "model_request_error"


@pytest.mark.parametrize("endpoint", ["analyze", "develop"])
@pytest.mark.parametrize("model", ["", "   "])
def test_blank_explicit_model_is_rejected(
    tmp_path: Path,
    endpoint: str,
    model: str,
) -> None:
    app = create_app(
        Settings(_env_file=None, log_path=tmp_path / f"{endpoint}-blank.log"),
        model_client=FakeModelClient(),
    )
    with TestClient(app) as client:
        response = client.post(
            f"/autodevelop/v1/{endpoint}",
            json=_body(endpoint=endpoint, model=model),
        )

    assert response.status_code == 422


@pytest.mark.parametrize("endpoint", ["analyze", "develop"])
@pytest.mark.parametrize(
    ("model", "code"),
    [("unknown", "model_not_found"), ("claude", "model_unavailable")],
)
def test_invalid_explicit_model_never_falls_back(
    tmp_path: Path,
    endpoint: str,
    model: str,
    code: str,
) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            default_model="qwen",
            log_path=tmp_path / f"{endpoint}-{model}.log",
        ),
        model_client=FakeModelClient(),
    )
    with TestClient(app) as client:
        response = client.post(
            f"/autodevelop/v1/{endpoint}",
            json=_body(endpoint=endpoint, model=model),
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == code


@pytest.mark.parametrize("endpoint", ["analyze", "develop"])
def test_model_source_logging_distinguishes_omitted_and_explicit(
    tmp_path: Path,
    endpoint: str,
) -> None:
    log_path = tmp_path / f"{endpoint}-source.log"
    app = create_app(
        Settings(
            _env_file=None,
            default_model="qwen",
            log_path=log_path,
        ),
        model_client=FakeModelClient(),
    )
    with TestClient(app) as client:
        omitted = client.post(
            f"/autodevelop/v1/{endpoint}",
            json=_body(endpoint=endpoint),
        )
        explicit = client.post(
            f"/autodevelop/v1/{endpoint}",
            json=_body(endpoint=endpoint, model="gemma"),
        )

    assert omitted.status_code == 200
    assert omitted.json()["model"] == "qwen"
    assert explicit.status_code == 200
    assert explicit.json()["model"] == "gemma"
    log_text = log_path.read_text(encoding="utf-8")
    assert "model_source=default" in log_text
    assert "model_source=explicit" in log_text
