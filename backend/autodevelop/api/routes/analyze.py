"""Analyze endpoint for validated photo requests."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from autodevelop.api.dependencies import (
    get_model_client,
    get_model_resolver,
    get_runtime_settings,
    get_style_profile_loader,
)
from autodevelop.api.exception_handlers import error_response
from autodevelop.api.model_errors import model_error_response
from autodevelop.api.model_selection import resolve_model_request
from autodevelop.config import Settings
from autodevelop.model_clients import (
    ModelClient,
    ModelClientError,
    InvalidModelResponseError,
    ModelRequestError,
    ModelResponseError,
    ModelResolver,
)
from autodevelop.model_clients.response_validation import validate_model_response
from autodevelop.models import AnalyzeRequest, AnalyzeResponse, ErrorResponse
from autodevelop.profiles import ProfileNotFoundError, StyleProfileLoader

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analyze"])


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Unknown profile or rejected model request.",
        },
        500: {
            "model": ErrorResponse,
            "description": "Unexpected internal processing failure.",
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
async def analyze_photo(
    request: AnalyzeRequest,
    model_client: Annotated[ModelClient, Depends(get_model_client)],
    model_resolver: Annotated[ModelResolver, Depends(get_model_resolver)],
    settings: Annotated[Settings, Depends(get_runtime_settings)],
    profile_loader: Annotated[
        StyleProfileLoader,
        Depends(get_style_profile_loader),
    ],
) -> AnalyzeResponse | JSONResponse:
    """Validate the selected profile and return model-generated analysis."""

    try:
        profile_loader.get_cached_profile(request.options.style_profile)
        selection = resolve_model_request(
            request,
            settings=settings,
            resolver=model_resolver,
        )
        request = selection.request
        resolution = selection.resolution
        logger.info(
            (
                "Analyze request started request_id=%s filename=%s profile=%s "
                "model=%s model_source=%s provider=%s"
            ),
            request.request_id,
            request.filename,
            request.options.style_profile,
            request.model,
            selection.source,
            resolution.definition.provider,
        )
        response = await model_client.analyze(request)
        response = validate_model_response(
            request,
            response,
            expected_type=AnalyzeResponse,
            expected_resolved_model=resolution.resolved_model,
        )
        logger.info(
            (
                "Analyze request complete request_id=%s filename=%s profile=%s "
                "model=%s provider=%s resolved_model=%s outcome=%s duration_ms=%s"
            ),
            request.request_id,
            request.filename,
            request.options.style_profile,
            request.model,
            resolution.definition.provider,
            response.resolved_model,
            response.status,
            response.processing_duration_ms,
        )
        return response
    except ProfileNotFoundError:
        return error_response(
            request,
            status_code=status.HTTP_400_BAD_REQUEST,
            code="profile_not_found",
            message=(
                f"Style profile {request.options.style_profile!r} was not found."
            ),
            retryable=False,
        )
    except InvalidModelResponseError as exc:
        logger.warning(
            (
                "Analyze model response rejected request_id=%s filename=%s "
                "model=%s validation_category=invalid_model_response"
            ),
            request.request_id,
            request.filename,
            request.model,
        )
        return model_error_response(request, exc)
    except (ModelRequestError, ModelResponseError, ModelClientError) as exc:
        return model_error_response(request, exc)
    except Exception:
        logger.error(
            "Unexpected Analyze endpoint failure for request_id=%s filename=%s",
            request.request_id,
            request.filename,
        )
        return error_response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="An internal error occurred while analyzing the photo.",
            retryable=True,
        )
