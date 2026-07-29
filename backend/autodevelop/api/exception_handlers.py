"""Helpers for safe API error responses."""

from fastapi.responses import JSONResponse

from autodevelop.models import (
    AnalyzeRequest,
    DevelopRequest,
    ErrorDetail,
    ErrorResponse,
)


def error_response(
    request: AnalyzeRequest | DevelopRequest,
    *,
    status_code: int,
    code: str,
    message: str,
    retryable: bool,
) -> JSONResponse:
    """Build a versioned JSON error while preserving request metadata."""

    payload = ErrorResponse(
        schema_version="1.0",
        request_id=request.request_id,
        filename=request.filename,
        status="error",
        error=ErrorDetail(
            code=code,
            message=message,
            retryable=retryable,
        ),
        warnings=[],
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
    )
