"""Provider-neutral application model service."""

import asyncio
import base64
import binascii
from pathlib import Path
import logging
from typing import TypeVar

from pydantic import ValidationError

from autodevelop.model_clients.base import ModelClient
from autodevelop.model_clients.exceptions import (
    InvalidModelResponseError,
    ModelRequestError,
)
from autodevelop.model_clients.prompt import build_prompt, build_scene_analysis_prompt
from autodevelop.model_clients.resolver import ModelResolver
from autodevelop.model_clients.response_validation import build_model_response
from autodevelop.learning.service import LearningService
from autodevelop.models import LearningDiagnostics
from autodevelop.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    EditPlan,
    DevelopRequest,
    DevelopResponse,
    TechnicalAnalysis,
)
from autodevelop.profiles import (
    AUTO_STYLE_ID,
    SceneSignals,
    StyleProfileLoader,
    select_style,
)

ResponseT = TypeVar("ResponseT", AnalyzeResponse, DevelopResponse)
logger = logging.getLogger(__name__)


class ModelService(ModelClient):
    """Resolve providers, perform inference, and validate transport output."""

    def __init__(
        self,
        resolver: ModelResolver,
        profile_loader: StyleProfileLoader,
        learning_service: LearningService | None = None,
    ) -> None:
        self._resolver = resolver
        self._profiles = profile_loader
        self._learning = learning_service

    async def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        resolved, image_bytes = await self._resolve_and_load(request)
        scene = await self._analyze_scene(request, resolved, image_bytes)
        selection = select_style(request.options.style_profile, scene)
        profile = self._profiles.get_cached_profile(selection.effective_style_id)
        payload = await resolved.client.infer(
            prompt=build_prompt(
                request,
                profile,
                operation="analyze",
                selection=selection,
            ),
            image_base64=base64.b64encode(image_bytes).decode("ascii"),
            request_id=str(request.request_id),
        )
        response = build_model_response(
            payload,
            request,
            response_type=AnalyzeResponse,
            expected_resolved_model=resolved.resolved_model,
            requested_style_id=selection.requested_style_id,
            effective_style_id=selection.effective_style_id,
            style_selection_mode=selection.mode,
            style_selection_reason=selection.reason,
            editing_intensity=selection.editing_intensity,
            scene_confidence=scene.confidence,
        )
        return response.model_copy(
            update={"analysis": self._technical_analysis(scene)}
        )

    async def develop(self, request: DevelopRequest) -> DevelopResponse:
        resolved, image_bytes = await self._resolve_and_load(request)
        if request.options.style_profile == AUTO_STYLE_ID:
            scene = await self._analyze_scene(request, resolved, image_bytes)
        else:
            scene = SceneSignals(
                primary_subject_type="unknown",
                scene_category="unknown",
                confidence=0.0,
            )
        selection = select_style(request.options.style_profile, scene)
        profile = self._profiles.get_cached_profile(selection.effective_style_id)
        personalization = None
        diagnostics = None
        if self._learning is not None:
            try:
                learning_result = await self._learning.prepare_personalization(
                    request,
                    image_bytes,
                    profile_id=selection.effective_style_id,
                )
                personalization = learning_result.context
                diagnostics = learning_result.diagnostics
            except Exception:
                logger.warning(
                    "learning_retrieval_unavailable request_id=%s",
                    request.request_id,
                )
                diagnostics = LearningDiagnostics(
                    enabled=self._learning.settings.learning_enabled,
                    personalization_applied=False,
                    usable_sample_count=0,
                    retrieved_sample_count=0,
                    minimum_sample_count=(
                        self._learning.settings.learning_min_samples
                    ),
                    average_similarity=None,
                    feature_type=None,
                    reason="retrieval_unavailable",
                )
        payload = await resolved.client.infer(
            prompt=build_prompt(
                request,
                profile,
                operation="develop",
                personalization=personalization,
                selection=selection,
            ),
            image_base64=base64.b64encode(image_bytes).decode("ascii"),
            request_id=str(request.request_id),
        )
        response = build_model_response(
            payload,
            request,
            response_type=DevelopResponse,
            expected_resolved_model=resolved.resolved_model,
            requested_style_id=selection.requested_style_id,
            effective_style_id=selection.effective_style_id,
            style_selection_mode=selection.mode,
            style_selection_reason=selection.reason,
            editing_intensity=selection.editing_intensity,
            scene_confidence=scene.confidence if selection.mode == "auto" else None,
        )
        if selection.mode == "auto":
            response = response.model_copy(
                update={"analysis": self._technical_analysis(scene)}
            )
        if isinstance(response, DevelopResponse) and diagnostics is not None:
            response = response.model_copy(
                update={"learning": diagnostics.model_copy(deep=True)}
            )
        return response

    async def _resolve_and_load(
        self,
        request: AnalyzeRequest | DevelopRequest,
    ):
        if request.model is None:
            raise ModelRequestError(
                "The model selection was not normalized.",
                model_name="unresolved",
            )
        return self._resolver.resolve(request.model), await self._load_image_bytes(request)

    async def _analyze_scene(self, request, resolved, image_bytes: bytes) -> SceneSignals:
        payload = await resolved.client.infer(
            prompt=build_scene_analysis_prompt(request),
            image_base64=base64.b64encode(image_bytes).decode("ascii"),
            request_id=str(request.request_id),
        )
        try:
            return SceneSignals.model_validate(payload)
        except ValidationError as exc:
            raise InvalidModelResponseError(
                "The provider scene analysis was invalid.",
                model_name=resolved.resolved_model,
            ) from exc

    @staticmethod
    def _technical_analysis(scene: SceneSignals) -> TechnicalAnalysis:
        return TechnicalAnalysis(
            scene_type=scene.scene_category,
            main_subject=scene.primary_subject or scene.primary_subject_type,
            lighting=scene.lighting_type,
            dynamic_range=scene.dynamic_range,
            noise_level=scene.noise_level,
            highlight_recoverability=scene.highlight_recoverability,
            shadow_recoverability=scene.shadow_recoverability,
            severe_underexposure=scene.severe_underexposure,
            visible_people=1 if scene.people_present else 0,
            has_faces=scene.portrait_dominant,
            has_sky=scene.scene_category in {"scenic_travel", "night"},
            confidence=scene.confidence,
        )

    @staticmethod
    async def _load_image_bytes(
        request: AnalyzeRequest | DevelopRequest,
    ) -> bytes:
        if request.preview_base64 is not None:
            try:
                return base64.b64decode(request.preview_base64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ModelRequestError(
                    "The preview was not valid base64.", model_name=request.model
                ) from exc
        if request.preview_path is None:
            raise ModelRequestError(
                "No preview was supplied.", model_name=request.model
            )
        try:
            return await asyncio.to_thread(Path(request.preview_path).read_bytes)
        except OSError as exc:
            raise ModelRequestError(
                "The preview could not be read.", model_name=request.model
            ) from exc
