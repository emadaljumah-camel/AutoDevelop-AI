"""Safe HTTP mapping for stable model-service failures."""

from fastapi import status
from fastapi.responses import JSONResponse

from autodevelop.api.exception_handlers import error_response
from autodevelop.model_clients import ModelClientError
from autodevelop.models import AnalyzeRequest, DevelopRequest

_ERRORS: dict[str, tuple[int, str, bool]] = {
    "model_request_error": (
        status.HTTP_400_BAD_REQUEST,
        "The model client rejected the request.",
        False,
    ),
    "model_response_error": (
        status.HTTP_502_BAD_GATEWAY,
        "The model client returned an invalid response.",
        True,
    ),
    "model_client_error": (
        status.HTTP_502_BAD_GATEWAY,
        "The model service could not complete the request.",
        True,
    ),
    "model_not_found": (
        status.HTTP_400_BAD_REQUEST,
        "The selected model was not found.",
        False,
    ),
    "model_unavailable": (
        status.HTTP_400_BAD_REQUEST,
        "The selected model is not available in this version.",
        False,
    ),
    "model_not_configured": (
        status.HTTP_400_BAD_REQUEST,
        "The selected model is not configured on the backend.",
        False,
    ),
    "provider_unavailable": (
        status.HTTP_502_BAD_GATEWAY,
        "The selected inference provider is unavailable.",
        True,
    ),
    "provider_timeout": (
        status.HTTP_504_GATEWAY_TIMEOUT,
        "The selected inference provider timed out.",
        True,
    ),
    "invalid_model_response": (
        status.HTTP_502_BAD_GATEWAY,
        "The selected model returned an invalid response.",
        False,
    ),
    "invalid_model_response_repeated": (
        status.HTTP_502_BAD_GATEWAY,
        "The selected model repeatedly returned an invalid response.",
        False,
    ),
    "provider_json_parse_failed": (
        status.HTTP_502_BAD_GATEWAY,
        "The selected model returned malformed JSON.",
        False,
    ),
    "provider_schema_mismatch": (
        status.HTTP_502_BAD_GATEWAY,
        "The selected model response did not match the required schema.",
        False,
    ),
    "invalid_response_metadata": (
        status.HTTP_502_BAD_GATEWAY,
        "The model client returned invalid response metadata.",
        True,
    ),
    "inference_failed": (
        status.HTTP_502_BAD_GATEWAY,
        "The selected model could not complete inference.",
        True,
    ),
}


def model_error_response(
    request: AnalyzeRequest | DevelopRequest,
    exc: ModelClientError,
) -> JSONResponse:
    """Return a sanitized structured response without raw provider details."""

    status_code, message, retryable = _ERRORS.get(
        exc.code,
        (
            status.HTTP_502_BAD_GATEWAY,
            "The model service could not complete the request.",
            True,
        ),
    )
    diagnostics = getattr(exc, "diagnostics", None)
    if (
        exc.code == "provider_json_parse_failed"
        and diagnostics is not None
        and diagnostics.diagnostic_code == "truncated_json"
    ):
        retryable = True
    if (
        diagnostics is not None
        and diagnostics.stage == "empty_provider_content"
    ):
        retryable = True
    return error_response(
        request,
        status_code=status_code,
        code=exc.code,
        message=message,
        retryable=retryable,
    )
