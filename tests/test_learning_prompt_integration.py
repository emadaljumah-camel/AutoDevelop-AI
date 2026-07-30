import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from autodevelop.config import Settings
from autodevelop.learning.models import RetrievalSample
from autodevelop.learning.schemas import FeatureVector
from autodevelop.learning.service import LearningService
from autodevelop.main import create_app
from autodevelop.model_clients import ModelResolver
from autodevelop.model_clients.clients import LocalOpenAIClient
from autodevelop.profiles import StyleProfileLoader

REQUEST_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


class FakeEmbedding:
    available = True
    feature_type = "test"

    def embed(self, _image_bytes: bytes) -> FeatureVector:
        return FeatureVector(
            feature_type="test",
            feature_version=1,
            dimensions=2,
            vector=[1.0, 0.0],
        )


class CandidateRepository:
    def __init__(
        self,
        candidates: list[RetrievalSample] | None = None,
        *,
        fail: bool = False,
    ) -> None:
        self.candidates = candidates or []
        self.fail = fail
        self.calls = 0

    def retrieval_candidates(self, _profile_id: str) -> list[RetrievalSample]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("private database detail")
        return self.candidates


def _sample(index: int, delta: float) -> RetrievalSample:
    return RetrievalSample(
        session_id=f"private-session-{index}",
        profile_id="natural_travel",
        captured_at_utc=datetime.now(UTC),
        significant_delta={"Exposure2012": delta},
        crop_delta={},
        leveling_delta={},
        accepted_without_change=False,
        feature_type="test",
        feature_version=1,
        vector=(1.0, 0.0),
        exif_context={"camera": "Camera", "capture_time_category": "day"},
    )


def _body(endpoint: str) -> dict[str, Any]:
    body = {
        "schema_version": "1.0",
        "request_id": REQUEST_ID,
        "filename": "Current.NEF",
        "model": "gemma",
        "preview_base64": "aW1hZ2U=",
        "exif": {"camera": "Camera"},
        "options": {"style_profile": "natural_travel"},
    }
    if endpoint == "develop":
        body["learning"] = {"enabled": True}
    return body


def _provider_payload(endpoint: str) -> dict[str, Any]:
    if endpoint == "analyze":
        return {
            "status": "success",
            "analysis": {
                "scene_type": "general",
                "confidence": 0.9,
            },
            "edit_plan": {
                "style_profile": "natural_travel",
                "goals": [],
                "cautions": [],
            },
            "crop": None,
            "leveling": {
                "recommended": False,
                "angle": 0,
                "mode": "none",
            },
            "denoise": {
                "recommended": False,
                "amount": None,
                "confidence": 0.9,
                "reason": "Not needed.",
            },
            "warnings": [],
        }
    payload: dict[str, Any] = {
        "status": "success",
        "analysis": {
            "scene_type": "general",
            "confidence": 0.9,
        },
        "edit_plan": {
            "style_profile": "natural_travel",
            "goals": [],
            "cautions": [],
        },
        "crop": None,
        "leveling": {
            "recommended": False,
            "angle": 0,
            "mode": "none",
        },
        "denoise": {
            "recommended": False,
            "amount": None,
            "confidence": 0.9,
            "reason": "Not needed.",
        },
        "warnings": [],
    }
    if endpoint == "develop":
        payload["develop_settings"] = {"Exposure2012": 0.1}
    return payload


def _client(
    tmp_path: Path,
    repository: CandidateRepository,
    captured: dict[str, Any],
) -> TestClient:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        captured["prompt"] = payload["messages"][0]["content"][0]["text"]
        endpoint = captured["endpoint"]
        if "Identify only the observable semantic signals" in captured["prompt"]:
            provider_payload = {
                "primary_subject_type": "other",
                "primary_subject": "general subject",
                "scene_category": "commercial_general",
                "lighting_type": "daylight",
                "dynamic_range": "moderate",
                "color_character": "balanced",
                "confidence": 0.9,
                "editing_priorities": ["Maintain natural tone"],
            }
        else:
            provider_payload = _provider_payload(endpoint)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(provider_payload)}}
                ]
            },
        )

    transport = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://provider.test/v1/",
    )
    provider = LocalOpenAIClient(
        base_url="http://provider.test/v1",
        api_key="",
        model="gemma-4-31b",
        timeout_seconds=10,
        client=transport,
    )
    settings = Settings(
        _env_file=None,
        log_path=tmp_path / "learning-prompt.log",
        learning_db=tmp_path / "unused.sqlite3",
    )
    loader = StyleProfileLoader()
    loader.reload_profiles()
    learning = LearningService(
        settings=settings,
        repository=repository,  # type: ignore[arg-type]
        profile_loader=loader,
        embedding_provider=FakeEmbedding(),
    )
    resolver = ModelResolver(
        settings,
        provider_clients={"gemma": provider},
    )
    app = create_app(
        settings,
        profile_loader=loader,
        model_resolver=resolver,
        learning_service=learning,
    )
    return TestClient(app)


def test_develop_adds_bounded_aggregate_personalization(tmp_path: Path) -> None:
    repository = CandidateRepository(
        [_sample(1, -0.2), _sample(2, -0.1), _sample(3, -0.15)]
    )
    captured: dict[str, Any] = {"endpoint": "develop"}
    with _client(tmp_path, repository, captured) as client:
        response = client.post("/autodevelop/v1/develop", json=_body("develop"))

    assert response.status_code == 200
    prompt = captured["prompt"]
    assert "PERSONAL EDITING PREFERENCES FROM SIMILAR PHOTOS" in prompt
    assert "private-session" not in prompt
    assert "Current.NEF" in prompt  # Current request context remains allowed.
    learning = response.json()["learning"]
    assert learning["personalization_applied"] is True
    assert learning["usable_sample_count"] == 3
    assert learning["retrieved_sample_count"] == 3
    assert learning["minimum_sample_count"] == 3
    assert learning["average_similarity"] == pytest.approx(0.925)


def test_insufficient_samples_omit_personalization_block(tmp_path: Path) -> None:
    repository = CandidateRepository([_sample(1, -0.2), _sample(2, -0.1)])
    captured: dict[str, Any] = {"endpoint": "develop"}
    with _client(tmp_path, repository, captured) as client:
        response = client.post("/autodevelop/v1/develop", json=_body("develop"))

    assert response.status_code == 200
    assert "PERSONAL EDITING PREFERENCES" not in captured["prompt"]
    learning = response.json()["learning"]
    assert learning["reason"] == "insufficient_samples"
    assert learning["usable_sample_count"] == 2
    assert learning["retrieved_sample_count"] == 0
    assert learning["minimum_sample_count"] == 3
    assert learning["average_similarity"] is None


def test_request_disabled_learning_reports_safe_diagnostics(tmp_path: Path) -> None:
    repository = CandidateRepository(
        [_sample(1, -0.2), _sample(2, -0.1), _sample(3, -0.15)]
    )
    captured: dict[str, Any] = {"endpoint": "develop"}
    body = _body("develop")
    body["learning"] = {"enabled": False}
    with _client(tmp_path, repository, captured) as client:
        response = client.post("/autodevelop/v1/develop", json=body)

    assert response.status_code == 200
    assert repository.calls == 0
    learning = response.json()["learning"]
    assert learning == {
        "enabled": True,
        "personalization_applied": False,
        "usable_sample_count": 0,
        "retrieved_sample_count": 0,
        "minimum_sample_count": 3,
        "average_similarity": None,
        "feature_type": "test",
        "reason": "disabled",
    }


def test_retrieval_failure_does_not_fail_develop(tmp_path: Path) -> None:
    repository = CandidateRepository(fail=True)
    captured: dict[str, Any] = {"endpoint": "develop"}
    with _client(tmp_path, repository, captured) as client:
        response = client.post("/autodevelop/v1/develop", json=_body("develop"))

    assert response.status_code == 200
    assert response.json()["learning"]["reason"] == "retrieval_unavailable"
    assert "private database detail" not in (
        tmp_path / "learning-prompt.log"
    ).read_text(encoding="utf-8")


def test_analyze_never_retrieves_or_adds_personalization(tmp_path: Path) -> None:
    repository = CandidateRepository(
        [_sample(1, -0.2), _sample(2, -0.1), _sample(3, -0.15)]
    )
    captured: dict[str, Any] = {"endpoint": "analyze"}
    with _client(tmp_path, repository, captured) as client:
        response = client.post("/autodevelop/v1/analyze", json=_body("analyze"))

    assert response.status_code == 200
    assert repository.calls == 0
    assert "PERSONAL EDITING PREFERENCES" not in captured["prompt"]


def test_provider_cannot_supply_learning_diagnostics(tmp_path: Path) -> None:
    captured: dict[str, Any] = {"endpoint": "develop"}

    class InjectingRepository(CandidateRepository):
        pass

    repository = InjectingRepository()

    def handler(_request: httpx.Request) -> httpx.Response:
        payload = _provider_payload("develop")
        payload["learning"] = {
            "enabled": True,
            "personalization_applied": True,
            "usable_sample_count": 999,
            "retrieved_sample_count": 999,
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(payload)}}]},
        )

    transport = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://provider.test/v1/",
    )
    settings = Settings(
        _env_file=None,
        log_path=tmp_path / "identity.log",
        learning_db=tmp_path / "unused.sqlite3",
    )
    loader = StyleProfileLoader()
    loader.reload_profiles()
    learning = LearningService(
        settings=settings,
        repository=repository,  # type: ignore[arg-type]
        profile_loader=loader,
        embedding_provider=FakeEmbedding(),
    )
    resolver = ModelResolver(
        settings,
        provider_clients={
            "gemma": LocalOpenAIClient(
                base_url="http://provider.test/v1",
                api_key="",
                model="gemma-4-31b",
                timeout_seconds=10,
                client=transport,
            )
        },
    )
    app = create_app(
        settings,
        profile_loader=loader,
        model_resolver=resolver,
        learning_service=learning,
    )
    with TestClient(app) as client:
        response = client.post("/autodevelop/v1/develop", json=_body("develop"))

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_model_response"
