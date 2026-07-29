"""Read-only model capability endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends

from autodevelop.api.dependencies import get_runtime_settings
from autodevelop.config import Settings
from autodevelop.models.capabilities import ModelCapability, ModelsResponse
from autodevelop.models.registry import list_model_definitions

router = APIRouter(tags=["models"])


@router.get("/models", response_model=ModelsResponse)
async def list_models(
    settings: Annotated[Settings, Depends(get_runtime_settings)],
) -> ModelsResponse:
    """Return safe registry metadata and runtime configuration status."""

    capabilities: list[ModelCapability] = []
    for definition in list_model_definitions():
        configured_model: str | None
        if definition.id == "claude":
            status = "future"
            configured_model = None
        elif definition.id == "gemini":
            configured_model = settings.gemini_model
            status = (
                "configured"
                if settings.gemini_api_key.get_secret_value().strip()
                else "not_configured"
            )
        else:
            configured_model = {
                "gemma": settings.gemma_model,
                "qwen": settings.qwen_model,
                "gpt_oss": settings.gpt_oss_model,
            }[definition.id]
            status = "configured"
        capabilities.append(
            ModelCapability(
                id=definition.id,
                display_name=definition.display_name,
                provider=definition.provider,
                description=definition.description,
                status=status,
                configured_model=configured_model,
            )
        )
    return ModelsResponse(
        models=capabilities,
        default_model=settings.default_model,
        status_semantics=(
            "Configuration state only; provider reachability is checked when "
            "inference is requested."
        ),
    )
