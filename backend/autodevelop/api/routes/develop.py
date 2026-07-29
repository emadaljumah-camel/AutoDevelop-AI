"""Develop endpoint for future-safe Lightroom recommendations."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
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
    ModelRequestError,
    ModelResponseError,
    ModelResolver,
)
from autodevelop.model_clients.response_validation import validate_model_response
from autodevelop.models import (
    DevelopRequest,
    DevelopResponse,
    ErrorResponse,
    ProcessingWarning,
)
from autodevelop.profiles import ProfileNotFoundError, StyleProfileLoader
from autodevelop.validation import (
    SafetyValidator,
    ValidationIssue,
    ValidationResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["develop"])


def _warning_key(warning: ProcessingWarning) -> tuple[str, str, str | None, str]:
    return (
        warning.code,
        warning.message,
        warning.field,
        warning.severity,
    )


def _issue_warning(issue: ValidationIssue) -> ProcessingWarning:
    return ProcessingWarning(
        code=issue.code,
        message=issue.message,
        field=issue.field,
        severity=issue.severity,
    )


def _merge_warnings(
    model_warnings: list[ProcessingWarning],
    validation_issues: list[ValidationIssue],
) -> list[ProcessingWarning]:
    """Preserve stable source ordering while removing exact duplicates."""

    merged: list[ProcessingWarning] = []
    seen: set[tuple[str, str, str | None, str]] = set()
    candidates = [
        *(warning.model_copy(deep=True) for warning in model_warnings),
        *(_issue_warning(issue) for issue in validation_issues),
    ]
    for warning in candidates:
        key = _warning_key(warning)
        if key not in seen:
            seen.add(key)
            merged.append(warning)
    return merged


def _build_final_response(
    raw_response: DevelopResponse,
    validation_result: ValidationResult,
) -> DevelopResponse:
    """Construct a new response containing only validator-approved output."""

    return DevelopResponse(
        schema_version=raw_response.schema_version,
        request_id=raw_response.request_id,
        filename=raw_response.filename,
        status=raw_response.status,
        analysis=(
            raw_response.analysis.model_copy(deep=True)
            if raw_response.analysis is not None
            else None
        ),
        edit_plan=(
            raw_response.edit_plan.model_copy(deep=True)
            if raw_response.edit_plan is not None
            else None
        ),
        develop_settings=validation_result.settings.model_copy(deep=True),
        crop=(
            validation_result.crop.model_copy(deep=True)
            if validation_result.crop is not None
            else None
        ),
        denoise=(
            validation_result.denoise.model_copy(deep=True)
            if validation_result.denoise is not None
            else None
        ),
        warnings=_merge_warnings(
            raw_response.warnings,
            validation_result.issues,
        ),
        model=raw_response.model,
        resolved_model=raw_response.resolved_model,
        processing_duration_ms=raw_response.processing_duration_ms,
    )


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
) -> DevelopResponse | JSONResponse:
    """Return sanitized recommendations without applying Lightroom edits."""

    profile_id = request.options.style_profile
    logger.info(
        "Develop request started request_id=%s filename=%s profile=%s",
        request.request_id,
        request.filename,
        profile_id,
    )

    try:
        profile = profile_loader.get_cached_profile(profile_id)
    except ProfileNotFoundError:
        logger.warning(
            "Develop profile not found request_id=%s filename=%s profile=%s",
            request.request_id,
            request.filename,
            profile_id,
        )
        return error_response(
            request,
            status_code=status.HTTP_400_BAD_REQUEST,
            code="profile_not_found",
            message=f"Style profile {profile_id!r} was not found.",
            retryable=False,
        )
    except Exception:
        logger.error(
            "Unexpected Develop profile lookup failure request_id=%s filename=%s",
            request.request_id,
            request.filename,
        )
        return error_response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="An internal error occurred while processing the photo.",
            retryable=True,
        )

    try:
        selection = resolve_model_request(
            request,
            settings=settings,
            resolver=model_resolver,
        )
        request = selection.request
        resolution = selection.resolution
        logger.info(
            (
                "Develop model selected request_id=%s filename=%s model=%s "
                "model_source=%s provider=%s"
            ),
            request.request_id,
            request.filename,
            request.model,
            selection.source,
            resolution.definition.provider,
        )
        raw_response = await model_client.develop(request)
        raw_response = validate_model_response(
            request,
            raw_response,
            expected_type=DevelopResponse,
            expected_resolved_model=resolution.resolved_model,
        )
    except ModelRequestError as exc:
        logger.warning(
            "Develop model request rejected request_id=%s filename=%s",
            request.request_id,
            request.filename,
        )
        return model_error_response(request, exc)
    except ModelResponseError as exc:
        logger.warning(
            "Develop model response invalid request_id=%s filename=%s",
            request.request_id,
            request.filename,
        )
        return model_error_response(request, exc)
    except ModelClientError as exc:
        logger.warning(
            "Develop model client failure request_id=%s filename=%s",
            request.request_id,
            request.filename,
        )
        return model_error_response(request, exc)
    except Exception:
        logger.error(
            "Unexpected Develop model failure request_id=%s filename=%s",
            request.request_id,
            request.filename,
        )
        return error_response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="An internal error occurred while processing the photo.",
            retryable=True,
        )

    try:
        validation_result = safety_validator.validate(
            settings=raw_response.develop_settings,
            crop=raw_response.crop,
            denoise=raw_response.denoise,
            profile=profile,
        )
        final_response = _build_final_response(
            raw_response,
            validation_result,
        )
    except Exception:
        logger.error(
            "Develop safety validation failed request_id=%s filename=%s",
            request.request_id,
            request.filename,
        )
        return error_response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="validation_internal_error",
            message="An internal validation error occurred.",
            retryable=True,
        )

    logger.info(
        (
            "Develop request complete request_id=%s filename=%s profile=%s "
            "model=%s provider=%s resolved_model=%s outcome=%s duration_ms=%s "
            "validation_issues=%d "
            "crop_rejected=%s clamped=%d removed=%d"
        ),
        request.request_id,
        request.filename,
        profile_id,
        raw_response.model,
        resolution.definition.provider,
        raw_response.resolved_model,
        raw_response.status,
        raw_response.processing_duration_ms,
        len(validation_result.issues),
        "crop" in validation_result.rejected_fields,
        len(validation_result.clamped_fields),
        len(validation_result.removed_fields),
    )
    return final_response
