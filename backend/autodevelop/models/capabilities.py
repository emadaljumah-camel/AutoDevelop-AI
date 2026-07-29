"""Public model-capability response models."""

from typing import Literal

from pydantic import Field

from autodevelop.models.common import NonBlankString, TransportModel

CapabilityStatus = Literal["configured", "not_configured", "future"]


class ModelCapability(TransportModel):
    """Safe public runtime capability for one stable model."""

    id: NonBlankString = Field(description="Stable model registry ID.")
    display_name: NonBlankString = Field(description="User-facing model name.")
    provider: NonBlankString = Field(description="Provider family.")
    description: NonBlankString = Field(description="User-facing model description.")
    status: CapabilityStatus = Field(description="Fixed runtime availability status.")
    configured_model: NonBlankString | None = Field(
        default=None,
        description="Configured provider model identifier; never a credential.",
    )


class ModelsResponse(TransportModel):
    """Ordered model capabilities and configured default."""

    models: list[ModelCapability] = Field(
        default_factory=list, description="Models in canonical display order."
    )
    default_model: NonBlankString = Field(
        description="Validated stable default model ID."
    )
    status_semantics: Literal[
        "Configuration state only; provider reachability is checked when inference is requested."
    ] = Field(
        description="Clarifies that this endpoint performs no provider health check."
    )
