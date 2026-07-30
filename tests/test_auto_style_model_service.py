import asyncio
from types import SimpleNamespace

import pytest

from autodevelop.config import Settings
from autodevelop.learning.schemas import LearningDiagnostics
from autodevelop.learning.service import PersonalizationResult
from autodevelop.model_clients import InvalidModelResponseError, ModelResolver
from autodevelop.model_clients.service import ModelService
from autodevelop.models import DevelopRequest
from autodevelop.profiles import StyleProfileLoader


class SequenceProvider:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.payloads = payloads
        self.prompts: list[str] = []

    async def infer(self, *, prompt: str, **_kwargs):
        self.prompts.append(prompt)
        return self.payloads[len(self.prompts) - 1]


class RecordingLearning:
    def __init__(self) -> None:
        self.profile_ids: list[str] = []
        self.settings = SimpleNamespace(
            learning_enabled=True,
            learning_min_samples=3,
        )

    async def prepare_personalization(
        self, _request, _image_bytes, *, profile_id: str
    ) -> PersonalizationResult:
        self.profile_ids.append(profile_id)
        return PersonalizationResult(
            context=None,
            diagnostics=LearningDiagnostics(
                enabled=True,
                personalization_applied=False,
                usable_sample_count=0,
                retrieved_sample_count=0,
                minimum_sample_count=3,
                reason="insufficient_samples",
            ),
            feature=None,
        )


def _scene_payload() -> dict[str, object]:
    return {
        "primary_subject_type": "landscape",
        "primary_subject": "mountain lake",
        "scene_category": "scenic_travel",
        "lighting_type": "daylight",
        "dynamic_range": "high",
        "noise_level": "low",
        "color_character": "balanced",
        "confidence": 0.91,
        "editing_priorities": ["Recover sky detail", "Improve depth"],
        "highlight_recoverability": "high",
        "shadow_recoverability": "moderate",
    }


def _develop_payload(style_id: str) -> dict[str, object]:
    return {
        "status": "success",
        "analysis": {
            "scene_type": "landscape",
            "main_subject": "mountain lake",
            "confidence": 0.91,
        },
        "edit_plan": {
            "style_profile": style_id,
            "goals": ["Improve depth"],
            "cautions": ["Keep color believable"],
        },
        "develop_settings": {"Contrast2012": 18.0, "Vibrance": 20.0},
        "crop": None,
        "denoise": None,
        "enable_hdr": {"recommended": False, "reason": None},
        "warnings": [],
    }


def _request(style_id: str) -> DevelopRequest:
    return DevelopRequest.model_validate(
        {
            "schema_version": "1.0",
            "request_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "filename": "Scenic.NEF",
            "model": "gemma",
            "preview_base64": "aW1hZ2U=",
            "options": {"style_profile": style_id},
        }
    )


def _service(provider: SequenceProvider, learning=None) -> ModelService:
    settings = Settings(_env_file=None)
    loader = StyleProfileLoader()
    loader.reload_profiles()
    resolver = ModelResolver(settings, provider_clients={"gemma": provider})
    return ModelService(resolver, loader, learning)


def test_auto_develop_uses_scene_then_effective_style_for_learning() -> None:
    provider = SequenceProvider([_scene_payload(), _develop_payload("natural_travel")])
    learning = RecordingLearning()

    response = asyncio.run(
        _service(provider, learning).develop(_request("auto"))
    )

    assert len(provider.prompts) == 2
    assert "SCENE ANALYSIS" in provider.prompts[0]
    assert "SELECTED STYLE" in provider.prompts[1]
    assert response.requested_style_id == "auto"
    assert response.effective_style_id == "natural_travel"
    assert response.style_selection_mode == "auto"
    assert learning.profile_ids == ["natural_travel"]


def test_manual_develop_uses_one_call_and_honors_style() -> None:
    provider = SequenceProvider([_develop_payload("architecture")])

    response = asyncio.run(
        _service(provider).develop(_request("architecture"))
    )

    assert len(provider.prompts) == 1
    assert response.effective_style_id == "architecture"
    assert response.style_selection_mode == "manual"


def test_provider_cannot_supply_style_diagnostics() -> None:
    payload = _develop_payload("architecture")
    payload["effective_style_id"] = "night"
    provider = SequenceProvider([payload])

    with pytest.raises(InvalidModelResponseError):
        asyncio.run(_service(provider).develop(_request("architecture")))
