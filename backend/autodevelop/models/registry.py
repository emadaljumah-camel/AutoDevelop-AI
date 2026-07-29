"""Canonical metadata for selectable AutoDevelop AI inference models."""

from typing import Literal

from pydantic import ConfigDict, Field

from autodevelop.models.common import NonBlankString, TransportModel

ProviderType = Literal["local_openai_compatible", "gemini_cloud", "future"]
AvailabilityState = Literal["enabled", "conditional", "future"]


class ModelDefinition(TransportModel):
    """Immutable public definition of one stable model choice."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: NonBlankString = Field(description="Stable API model identifier.")
    display_name: NonBlankString = Field(description="User-facing model name.")
    provider: ProviderType = Field(description="Inference provider family.")
    description: NonBlankString = Field(description="Short user-facing description.")
    sort_order: int = Field(ge=1, description="Deterministic display order.")
    availability: AvailabilityState = Field(
        description="Static availability classification."
    )
    availability_label: NonBlankString = Field(
        description="Canonical user-facing availability label."
    )
    configuration_requirements: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Names of backend configuration values required at runtime.",
    )
    default_backend_model: NonBlankString | None = Field(
        default=None,
        description="Optional default raw provider model identifier.",
    )

    @property
    def selectable(self) -> bool:
        """Return whether this definition can be selected for inference."""

        return self.availability != "future"


_MODELS = (
    ModelDefinition(
        id="gemma",
        display_name="Gemma",
        provider="local_openai_compatible",
        description=(
            "Local Gemma vision model through an OpenAI-compatible inference server."
        ),
        sort_order=1,
        availability="enabled",
        availability_label="Configured by backend",
        configuration_requirements=("local_base_url", "gemma_model"),
        default_backend_model="gemma-4-31b",
    ),
    ModelDefinition(
        id="qwen",
        display_name="Qwen",
        provider="local_openai_compatible",
        description=(
            "Local Qwen vision model through an OpenAI-compatible inference server."
        ),
        sort_order=2,
        availability="enabled",
        availability_label="Configured by backend",
        configuration_requirements=("local_base_url", "qwen_model"),
        default_backend_model="qwen_qwen3-vl-32b-instruct",
    ),
    ModelDefinition(
        id="gpt_oss",
        display_name="GPT OSS",
        provider="local_openai_compatible",
        description=(
            "Local GPT-compatible open model through an OpenAI-compatible "
            "inference server."
        ),
        sort_order=3,
        availability="enabled",
        availability_label="Configured by backend",
        configuration_requirements=("local_base_url", "gpt_oss_model"),
        default_backend_model="gpt-oss",
    ),
    ModelDefinition(
        id="gemini",
        display_name="Gemini",
        provider="gemini_cloud",
        description=(
            "Google Gemini cloud model using a configured API key and model identifier."
        ),
        sort_order=4,
        availability="conditional",
        availability_label="Requires backend API key",
        configuration_requirements=("gemini_api_key", "gemini_model"),
        default_backend_model="gemini-2.5-flash",
    ),
    ModelDefinition(
        id="claude",
        display_name="Claude",
        provider="future",
        description="Claude provider integration is reserved for a future phase.",
        sort_order=5,
        availability="future",
        availability_label="Future",
        configuration_requirements=(),
        default_backend_model=None,
    ),
)
_BY_ID = {definition.id: definition for definition in _MODELS}
DEFAULT_MODEL_ID = "gemma"


def list_model_definitions() -> tuple[ModelDefinition, ...]:
    """Return deterministic, immutable copies of all model definitions."""

    return tuple(item.model_copy(deep=True) for item in _MODELS)


def get_model_definition(model_id: str) -> ModelDefinition | None:
    """Return a defensive copy for a stable model ID, if registered."""

    definition = _BY_ID.get(model_id)
    return definition.model_copy(deep=True) if definition is not None else None


def is_known_model_id(model_id: str) -> bool:
    """Return whether a stable model ID is registered."""

    return model_id in _BY_ID
