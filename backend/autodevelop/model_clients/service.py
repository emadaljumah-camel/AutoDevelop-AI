"""Provider-neutral application model service."""

import asyncio
import base64
from pathlib import Path
from typing import TypeVar

from autodevelop.model_clients.base import ModelClient
from autodevelop.model_clients.exceptions import (
    ModelRequestError,
)
from autodevelop.model_clients.prompt import build_prompt
from autodevelop.model_clients.resolver import ModelResolver
from autodevelop.model_clients.response_validation import build_model_response
from autodevelop.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    DevelopRequest,
    DevelopResponse,
)
from autodevelop.profiles import StyleProfileLoader

ResponseT = TypeVar("ResponseT", AnalyzeResponse, DevelopResponse)


class ModelService(ModelClient):
    """Resolve providers, perform inference, and validate transport output."""

    def __init__(
        self,
        resolver: ModelResolver,
        profile_loader: StyleProfileLoader,
    ) -> None:
        self._resolver = resolver
        self._profiles = profile_loader

    async def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        return await self._invoke(request, AnalyzeResponse, operation="analyze")

    async def develop(self, request: DevelopRequest) -> DevelopResponse:
        return await self._invoke(request, DevelopResponse, operation="develop")

    async def _invoke(
        self,
        request: AnalyzeRequest | DevelopRequest,
        response_type: type[ResponseT],
        *,
        operation: str,
    ) -> ResponseT:
        if request.model is None:
            raise ModelRequestError(
                "The model selection was not normalized.",
                model_name="unresolved",
            )
        resolved = self._resolver.resolve(request.model)
        profile = self._profiles.get_cached_profile(request.options.style_profile)
        image_base64 = await self._load_image(request)
        payload = await resolved.client.infer(
            prompt=build_prompt(request, profile, operation=operation),
            image_base64=image_base64,
            request_id=str(request.request_id),
        )
        return build_model_response(
            payload,
            request,
            response_type=response_type,
            expected_resolved_model=resolved.resolved_model,
        )

    @staticmethod
    async def _load_image(
        request: AnalyzeRequest | DevelopRequest,
    ) -> str:
        if request.preview_base64 is not None:
            return request.preview_base64
        if request.preview_path is None:
            raise ModelRequestError(
                "No preview was supplied.", model_name=request.model
            )
        try:
            data = await asyncio.to_thread(Path(request.preview_path).read_bytes)
        except OSError as exc:
            raise ModelRequestError(
                "The preview could not be read.", model_name=request.model
            ) from exc
        return base64.b64encode(data).decode("ascii")
