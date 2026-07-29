from pathlib import Path

from fastapi.testclient import TestClient

from autodevelop.config import Settings
from autodevelop.main import create_app
from autodevelop.model_clients import FakeModelClient
from autodevelop.model_clients.clients import GeminiClient, LocalOpenAIClient


def test_models_endpoint_is_ordered_and_secret_free(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            log_path=tmp_path / "models.log",
            gemini_api_key="super-secret",
        ),
        model_client=FakeModelClient(),
    )
    with TestClient(app) as client:
        response = client.get("/autodevelop/v1/models")
    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["models"]] == [
        "gemma",
        "qwen",
        "gpt_oss",
        "gemini",
        "claude",
    ]
    assert payload["default_model"] == "gemma"
    assert payload["models"][3]["status"] == "configured"
    assert payload["models"][4]["status"] == "future"
    assert payload["models"][0]["status"] == "configured"
    assert payload["status_semantics"].startswith("Configuration state only")
    assert "super-secret" not in response.text


def test_gemini_is_not_configured_without_key(tmp_path: Path) -> None:
    app = create_app(
        Settings(_env_file=None, log_path=tmp_path / "models.log"),
        model_client=FakeModelClient(),
    )
    with TestClient(app) as client:
        payload = client.get("/autodevelop/v1/models").json()
    gemini = next(item for item in payload["models"] if item["id"] == "gemini")
    assert gemini["status"] == "not_configured"


def test_models_endpoint_performs_no_provider_request(
    tmp_path: Path,
    monkeypatch,
) -> None:
    async def fail(*_args, **_kwargs):
        raise AssertionError("capabilities endpoint called a provider")

    monkeypatch.setattr(LocalOpenAIClient, "infer", fail)
    monkeypatch.setattr(GeminiClient, "infer", fail)
    app = create_app(
        Settings(
            _env_file=None,
            log_path=tmp_path / "models.log",
            gemini_api_key="configured-secret",
        ),
        model_client=FakeModelClient(),
    )
    with TestClient(app) as client:
        response = client.get("/autodevelop/v1/models")
    assert response.status_code == 200
    assert "configured-secret" not in response.text
