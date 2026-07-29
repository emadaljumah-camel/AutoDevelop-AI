import pytest

from autodevelop.config import Settings
from autodevelop.model_clients import (
    ModelNotConfiguredError,
    ModelNotFoundError,
    ModelResolver,
    ModelUnavailableError,
)
from autodevelop.model_clients.clients import GeminiClient, LocalOpenAIClient


def test_local_models_resolve_without_fallback() -> None:
    settings = Settings(
        _env_file=None,
        gemma_model="configured-gemma",
        qwen_model="configured-qwen",
        gpt_oss_model="configured-gpt",
    )
    resolver = ModelResolver(settings)
    for stable, raw in (
        ("gemma", "configured-gemma"),
        ("qwen", "configured-qwen"),
        ("gpt_oss", "configured-gpt"),
    ):
        resolved = resolver.resolve(stable)
        assert resolved.definition.id == stable
        assert resolved.resolved_model == raw
        assert isinstance(resolved.client, LocalOpenAIClient)


def test_gemini_and_invalid_resolution_are_structured() -> None:
    resolver = ModelResolver(Settings(_env_file=None, gemini_api_key=""))
    with pytest.raises(ModelNotConfiguredError):
        resolver.resolve("gemini")
    with pytest.raises(ModelUnavailableError):
        resolver.resolve("claude")
    with pytest.raises(ModelNotFoundError):
        resolver.resolve("does_not_exist")

    configured = ModelResolver(
        Settings(
            _env_file=None,
            gemini_api_key="secret",
            gemini_model="configured-gemini",
        )
    ).resolve("gemini")
    assert configured.resolved_model == "configured-gemini"
    assert isinstance(configured.client, GeminiClient)
