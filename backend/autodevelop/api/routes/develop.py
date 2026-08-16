"""HTTP adapter for validated Develop recommendations."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from autodevelop.api.dependencies import (
    get_model_client,
    get_model_resolver,
    get_runtime_settings,
    get_safety_validator,
    get_style_profile_loader,
)
from autodevelop.config import Settings
from autodevelop.develop_service import process_develop
from autodevelop.model_clients import ModelClient, ModelResolver
from autodevelop.models import DevelopRequest, DevelopResponse, ErrorResponse
from autodevelop.profiles import StyleProfileLoader
from autodevelop.validation import SafetyValidator

router = APIRouter(tags=["develop"])


@router.post(
    "/develop",
    response_model=DevelopResponse,
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Unknown profile or rejected model request.",
        },
        500: {
            "model": ErrorResponse,
            "description": "Unexpected validation or internal failure.",
        },
        502: {
            "model": ErrorResponse,
            "description": "Model client or model response failure.",
        },
        504: {
            "model": ErrorResponse,
            "description": "Inference provider timeout.",
        },
    },
)
async def develop_photo(
    request: DevelopRequest,
    model_client: Annotated[ModelClient, Depends(get_model_client)],
    model_resolver: Annotated[ModelResolver, Depends(get_model_resolver)],
    settings: Annotated[Settings, Depends(get_runtime_settings)],
    profile_loader: Annotated[
        StyleProfileLoader,
        Depends(get_style_profile_loader),
    ],
    safety_validator: Annotated[
        SafetyValidator,
        Depends(get_safety_validator),
    ],
    endpoint_attempt: Annotated[
        int | None,
        Header(alias="X-Autodevelop-Attempt", ge=1, le=10),
    ] = None,
) -> DevelopResponse | JSONResponse:
    """Return sanitized recommendations without applying Lightroom edits."""

    return await process_develop(
        request,
        model_client=model_client,
        model_resolver=model_resolver,
        settings=settings,
        profile_loader=profile_loader,
        safety_validator=safety_validator,
        endpoint_attempt=endpoint_attempt,
    )
