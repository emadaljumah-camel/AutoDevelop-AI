"""Exceptions raised by AutoDevelop AI model clients."""


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
