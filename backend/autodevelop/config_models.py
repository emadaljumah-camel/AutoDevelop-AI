"""Strict typed schema for non-secret YAML model configuration."""

from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    field_validator,
    model_validator,
)

from autodevelop.models.registry import get_model_definition

NonBlankConfigString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, strict=True),
]
ProviderTimeout = Annotated[int, Field(strict=True, ge=10, le=600)]


def normalize_safe_http_url(value: str) -> str:
    """Return a normalized credential-free HTTP(S) URL."""

    normalized = value.strip()
    parsed = urlsplit(normalized)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("value must be a safe HTTP(S) URL")
    return normalized.rstrip("/")


class _YamlModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LocalProviderYamlConfig(_YamlModel):
    base_url: NonBlankConfigString | None = None
    timeout_seconds: ProviderTimeout | None = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        return normalize_safe_http_url(value) if value is not None else None


class GeminiProviderYamlConfig(_YamlModel):
    timeout_seconds: ProviderTimeout | None = None


class ProviderYamlConfig(_YamlModel):
    local: LocalProviderYamlConfig | None = None
    gemini: GeminiProviderYamlConfig | None = None


class ModelYamlEntry(_YamlModel):
    provider_model_id: NonBlankConfigString | None = None
    enabled: StrictBool | None = None


class ModelsYamlConfig(_YamlModel):
    version: Literal[1] = 1
    default_model: NonBlankConfigString | None = None
    providers: ProviderYamlConfig | None = None
    models: dict[str, ModelYamlEntry] = Field(default_factory=dict)

    @field_validator("default_model")
    @classmethod
    def validate_default_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        definition = get_model_definition(value)
        if definition is None:
            raise ValueError("default_model is not registered")
        if not definition.selectable:
            raise ValueError("default_model is not selectable")
        return value

    @model_validator(mode="after")
    def validate_model_entries(self) -> "ModelsYamlConfig":
        for model_id, entry in self.models.items():
            definition = get_model_definition(model_id)
            if definition is None:
                raise ValueError(f"models.{model_id} is not registered")
            if model_id == "claude":
                if entry.enabled is True:
                    raise ValueError("Claude cannot be enabled")
                if entry.provider_model_id is not None:
                    raise ValueError("Claude cannot configure a provider model")
            elif entry.enabled is not None:
                raise ValueError(
                    f"models.{model_id}.enabled is not supported"
                )
        return self
