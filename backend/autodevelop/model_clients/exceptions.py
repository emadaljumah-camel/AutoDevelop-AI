"""Exceptions raised by AutoDevelop AI model clients."""

from autodevelop.model_clients.diagnostics import InvalidResponseDiagnostics


class ModelClientError(RuntimeError):
    """Base failure with stable code and model-name context."""

    default_code = "model_client_error"

    def __init__(
        self,
        message: str,
        *,
        model_name: str,
        code: str | None = None,
    ) -> None:
        self.code = code or self.default_code
        self.model_name = model_name
        super().__init__(
            f"{message} [code={self.code}, model_name={self.model_name}]"
        )


class ModelRequestError(ModelClientError):
    """The model client could not accept a request."""

    default_code = "model_request_error"


class ModelResponseError(ModelClientError):
    """The model client produced or was asked to produce an invalid response."""

    default_code = "model_response_error"


class ModelNotFoundError(ModelRequestError):
    default_code = "model_not_found"


class ModelUnavailableError(ModelRequestError):
    default_code = "model_unavailable"


class ModelNotConfiguredError(ModelRequestError):
    default_code = "model_not_configured"


class ProviderUnavailableError(ModelClientError):
    default_code = "provider_unavailable"


class ProviderTimeoutError(ModelClientError):
    default_code = "provider_timeout"


class InferenceFailedError(ModelClientError):
    default_code = "inference_failed"


class InvalidModelResponseError(ModelResponseError):
    default_code = "invalid_model_response"

    def __init__(
        self,
        message: str,
        *,
        model_name: str,
        code: str | None = None,
        diagnostics: InvalidResponseDiagnostics | None = None,
    ) -> None:
        self.diagnostics = diagnostics or InvalidResponseDiagnostics(
            stage="provider_schema_validation_failed",
            diagnostic_code="invalid_model_response",
        )
        super().__init__(
            message,
            model_name=model_name,
            code=code,
        )

    def with_diagnostic_context(
        self,
        *,
        phase: str,
        provider_attempt: int,
        provider_call_number: int,
        repair_attempt: bool,
    ) -> "InvalidModelResponseError":
        """Attach request-local context without exposing provider content."""

        self.diagnostics = self.diagnostics.with_context(
            phase=phase,
            provider_attempt=provider_attempt,
            provider_call_number=provider_call_number,
            repair_attempt=repair_attempt,
        )
        return self
