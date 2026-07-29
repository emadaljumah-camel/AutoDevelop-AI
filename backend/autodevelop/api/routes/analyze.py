"""Analyze endpoint for validated photo requests."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from autodevelop.api.dependencies import (
    get_model_client,
    get_style_profile_loader,
)
from autodevelop.api.exception_handlers import error_response
from autodevelop.model_clients import (
    ModelClient,
    ModelClientError,
    ModelRequestError,
    ModelResponseError,
)
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
    },
)
async def analyze_photo(
    request: AnalyzeRequest,
    model_client: Annotated[ModelClient, Depends(get_model_client)],
    profile_loader: Annotated[
        StyleProfileLoader,
        Depends(get_style_profile_loader),
    ],
) -> AnalyzeResponse | JSONResponse:
    """Validate the selected profile and return model-generated analysis."""

    try:
        profile_loader.get_cached_profile(request.options.style_profile)
        return await model_client.analyze(request)
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
    except ModelRequestError:
        return error_response(
            request,
            status_code=status.HTTP_400_BAD_REQUEST,
            code="model_request_error",
            message="The model client rejected the analysis request.",
            retryable=False,
        )
    except ModelResponseError:
        return error_response(
            request,
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="model_response_error",
            message="The model client returned an invalid analysis response.",
            retryable=True,
        )
    except ModelClientError:
        return error_response(
            request,
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="model_client_error",
            message="The model client could not complete the analysis request.",
            retryable=True,
        )
    except Exception:
        logger.exception(
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
