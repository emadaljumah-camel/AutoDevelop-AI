"""Analyze endpoint for validated photo requests."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from fastapi.responses import JSONResponse

from autodevelop.api.dependencies import (
    get_model_client,
    get_model_resolver,
    get_runtime_settings,
    get_safety_validator,
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
from autodevelop.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    ErrorResponse,
    ProcessingWarning,
)
from autodevelop.profiles import (
    AUTO_STYLE_ID,
    ProfileNotFoundError,
    StyleProfileLoader,
    is_valid_style_request_id,
)
from autodevelop.validation import SafetyValidator

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
    safety_validator: Annotated[
        SafetyValidator,
        Depends(get_safety_validator),
    ],
    endpoint_attempt: Annotated[
        int | None,
        Header(alias="X-Autodevelop-Attempt", ge=1, le=10),
    ] = None,
) -> AnalyzeResponse | JSONResponse:
    """Validate the selected profile and return model-generated analysis."""

    try:
        if request.options.style_profile != AUTO_STYLE_ID:
            profile_loader.get_cached_profile(request.options.style_profile)
        if not is_valid_style_request_id(request.options.style_profile):
            raise ProfileNotFoundError(request.options.style_profile)
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
                "model=%s model_source=%s provider=%s preview_source=%s "
                "endpoint_attempt=%d"
            ),
            request.request_id,
            request.filename,
            request.options.style_profile,
            request.model,
            selection.source,
            resolution.definition.provider,
            (
                "preview_base64"
                if request.preview_base64 is not None
                else "preview_path"
            ),
            endpoint_attempt or 1,
        )
        response = await model_client.analyze(request)
        response = validate_model_response(
            request,
            response,
            expected_type=AnalyzeResponse,
            expected_resolved_model=resolution.resolved_model,
        )
        profile = profile_loader.get_cached_profile(response.effective_style_id)
        try:
            validation_result = safety_validator.validate(
                settings=None,
                crop=response.crop,
                leveling=response.leveling,
                denoise=response.denoise,
                profile=profile,
                analysis=response.analysis,
                options=request.options,
            )
        except Exception:
            logger.error(
                (
                    "Analyze safety validation failed request_id=%s filename=%s "
                    "endpoint_attempt=%d phase=final_develop "
                    "stage=safety_validation_failed "
                    "diagnostic_code=safety_validation_failed"
                ),
                request.request_id,
                request.filename,
                endpoint_attempt or 1,
            )
            return error_response(
                request,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="validation_internal_error",
                message="An internal validation error occurred.",
                retryable=True,
            )
        validation_warnings = [
            ProcessingWarning(
                code=issue.code,
                message=issue.message,
                field=issue.field,
                severity=issue.severity,
            )
            for issue in validation_result.issues
        ]
        response = response.model_copy(
            update={
                "crop": (
                    validation_result.crop.model_copy(deep=True)
                    if validation_result.crop is not None
                    else None
                ),
                "leveling": validation_result.leveling.model_copy(deep=True),
                "denoise": (
                    validation_result.denoise.model_copy(deep=True)
                    if validation_result.denoise is not None
                    else None
                ),
                "warnings": [
                    *(warning.model_copy(deep=True) for warning in response.warnings),
                    *validation_warnings,
                ],
            }
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
        diagnostics = exc.diagnostics
        logger.warning(
            (
                "Analyze model response rejected request_id=%s filename=%s "
                "model=%s endpoint_attempt=%d phase=%s stage=%s "
                "diagnostic_code=%s field=%s"
            ),
            request.request_id,
            request.filename,
            request.model,
            endpoint_attempt or 1,
            diagnostics.phase or "<unknown>",
            diagnostics.stage,
            diagnostics.diagnostic_code,
            diagnostics.field_path or "<none>",
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
