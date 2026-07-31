"""Resolve stable model IDs to configured provider transports."""

from collections.abc import Mapping
from dataclasses import dataclass

from autodevelop.config import Settings
from autodevelop.model_clients.clients import GeminiClient, LocalOpenAIClient
from autodevelop.model_clients.clients.base import ProviderClient
from autodevelop.model_clients.exceptions import (
    ModelNotConfiguredError,
    ModelNotFoundError,
    ModelUnavailableError,
)
from autodevelop.models.registry import ModelDefinition, get_model_definition


@dataclass(frozen=True)
class ResolvedModel:
    """One validated stable model resolution."""

    definition: ModelDefinition
    resolved_model: str
    client: ProviderClient


class ModelResolver:
    """Resolve a stable ID without fallback or mutable request state."""

    def __init__(
        self,
        settings: Settings,
        *,
        provider_clients: Mapping[str, ProviderClient] | None = None,
    ) -> None:
        self._settings = settings
        self._provider_clients = dict(provider_clients or {})

    def resolve(self, model_id: str) -> ResolvedModel:
        definition = get_model_definition(model_id)
        if definition is None:
            raise ModelNotFoundError(
                "The selected model is not registered.", model_name=model_id
            )
        if not definition.selectable:
            raise ModelUnavailableError(
                "The selected model is not available.", model_name=model_id
            )
        if definition.provider == "gemini_cloud":
            api_key = self._settings.gemini_api_key.get_secret_value().strip()
            if not api_key:
                raise ModelNotConfiguredError(
                    "Gemini is not configured.", model_name=model_id
                )
            raw_model = self._settings.gemini_model
        else:
            raw_model = {
                "gemma": self._settings.gemma_model,
                "qwen": self._settings.qwen_model,
                "gpt_oss": self._settings.gpt_oss_model,
            }[model_id]
        client = self._provider_clients.get(model_id)
        if client is None:
            if definition.provider == "gemini_cloud":
                client = GeminiClient(
                    api_key=api_key,
                    model=raw_model,
                    timeout_seconds=self._settings.gemini_timeout_seconds,
                )
            else:
                client = LocalOpenAIClient(
                    base_url=self._settings.local_base_url,
                    api_key=self._settings.local_api_key.get_secret_value().strip(),
                    model=raw_model,
                    timeout_seconds=self._settings.local_timeout_seconds,
                    response_format_mode=self._settings.local_response_format,
                )
        return ResolvedModel(definition, raw_model, client)
