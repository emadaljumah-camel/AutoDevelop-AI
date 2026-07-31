"""Provider-neutral application model service."""

import asyncio
import base64
import binascii
from dataclasses import replace
import json
from pathlib import Path
import logging
from typing import TypeVar

from pydantic import ValidationError

from autodevelop.model_clients.base import ModelClient
from autodevelop.model_clients.exceptions import (
    InvalidModelResponseError,
    ModelRequestError,
)
from autodevelop.model_clients.diagnostics import (
    InvalidResponseDiagnostics,
    first_error_path,
    sanitize_invalid_content,
    validation_error_summary,
)
from autodevelop.model_clients.prompt import (
    build_prompt,
    build_repair_prompt,
    build_scene_analysis_prompt,
    provider_response_schema,
    scene_analysis_schema,
)
from autodevelop.model_clients.resolver import ModelResolver
from autodevelop.model_clients.response_validation import build_model_response
from autodevelop.learning.service import LearningService
from autodevelop.hdr_decision import calculate_hdr_evidence
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
        *,
        log_invalid_model_response: bool = False,
        invalid_response_max_chars: int = 4000,
    ) -> None:
        self._resolver = resolver
        self._profiles = profile_loader
        self._learning = learning_service
        self._log_invalid_model_response = log_invalid_model_response
        self._invalid_response_max_chars = invalid_response_max_chars

    async def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        resolved, image_bytes = await self._resolve_and_load(request)
        scene = await self._analyze_scene(
            request,
            resolved,
            image_bytes,
            provider_call_number=1,
        )
        selection = select_style(request.options.style_profile, scene)
        profile = self._profiles.get_cached_profile(selection.effective_style_id)
        payload = await self._infer(
            request=request,
            resolved=resolved,
            prompt=build_prompt(
                request,
                profile,
                operation="analyze",
                selection=selection,
            ),
            image_base64=base64.b64encode(image_bytes).decode("ascii"),
            phase="final_develop",
            provider_attempt=1,
            provider_call_number=2,
            response_schema=provider_response_schema("analyze"),
            schema_name="autodevelop_analyze_response",
        )
        try:
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
        except InvalidModelResponseError as exc:
            self._attach_and_log(
                exc,
                request=request,
                payload=payload,
                phase="final_develop",
                provider_attempt=1,
                provider_call_number=2,
                repair_attempt=False,
            )
            raise
        return response.model_copy(
            update={"analysis": self._technical_analysis(scene)}
        )

    async def develop(self, request: DevelopRequest) -> DevelopResponse:
        resolved, image_bytes = await self._resolve_and_load(request)
        scene = await self._analyze_scene(
            request,
            resolved,
            image_bytes,
            provider_call_number=1,
        )
        final_call_number = 2
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
        hdr_evidence = calculate_hdr_evidence(
            self._technical_analysis(scene),
            diagnostics,
            request.options.hdr_preference,
            minimum_samples=(
                self._learning.settings.learning_min_samples
                if self._learning is not None
                else 3
            ),
        )
        response_schema = provider_response_schema("develop")
        payload = await self._infer(
            request=request,
            resolved=resolved,
            prompt=build_prompt(
                request,
                profile,
                operation="develop",
                personalization=personalization,
                hdr_evidence=hdr_evidence,
                selection=selection,
            ),
            image_base64=base64.b64encode(image_bytes).decode("ascii"),
            phase="final_develop",
            provider_attempt=1,
            provider_call_number=final_call_number,
            response_schema=response_schema,
            schema_name="autodevelop_response",
        )
        try:
            response = self._build_develop_response(
                payload,
                request=request,
                resolved=resolved,
                selection=selection,
                scene=scene,
            )
        except InvalidModelResponseError as exc:
            self._attach_and_log(
                exc,
                request=request,
                payload=payload,
                phase="final_develop",
                provider_attempt=1,
                provider_call_number=final_call_number,
                repair_attempt=False,
            )
            if not self._repairable(exc, resolved.client):
                raise
            try:
                repair_payload = await self._infer(
                    request=request,
                    resolved=resolved,
                    prompt=build_repair_prompt(
                        dict(payload),
                        exc.diagnostics.validation_errors,
                        response_schema,
                    ),
                    image_base64=None,
                    phase="final_develop",
                    provider_attempt=2,
                    provider_call_number=final_call_number + 1,
                    response_schema=response_schema,
                    schema_name="autodevelop_response_repair",
                    repair_attempt=True,
                )
            except InvalidModelResponseError as repair_exc:
                repair_exc.code = "invalid_model_response_repeated"
                raise
            try:
                response = self._build_develop_response(
                    repair_payload,
                    request=request,
                    resolved=resolved,
                    selection=selection,
                    scene=scene,
                )
            except InvalidModelResponseError as repair_exc:
                repair_exc.code = "invalid_model_response_repeated"
                self._attach_and_log(
                    repair_exc,
                    request=request,
                    payload=repair_payload,
                    phase="final_develop",
                    provider_attempt=2,
                    provider_call_number=final_call_number + 1,
                    repair_attempt=True,
                )
                raise
        response = response.model_copy(
            update={
                "analysis": self._technical_analysis(scene),
                "hdr_decision": hdr_evidence.model_copy(
                    update={
                        "raw_hdr_recommended": response.enable_hdr.recommended,
                        "raw_hdr_confidence": response.enable_hdr.confidence,
                    },
                    deep=True,
                ),
            }
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

    async def _analyze_scene(
        self,
        request,
        resolved,
        image_bytes: bytes,
        *,
        provider_call_number: int,
    ) -> SceneSignals:
        payload = await self._infer(
            request=request,
            resolved=resolved,
            prompt=build_scene_analysis_prompt(request),
            image_base64=base64.b64encode(image_bytes).decode("ascii"),
            phase="auto_scene_analysis",
            provider_attempt=1,
            provider_call_number=provider_call_number,
            response_schema=scene_analysis_schema(),
            schema_name="autodevelop_scene_analysis",
        )
        try:
            return SceneSignals.model_validate(payload)
        except ValidationError as exc:
            error_count, errors = validation_error_summary(exc)
            invalid = InvalidModelResponseError(
                "The provider scene analysis was invalid.",
                model_name=resolved.resolved_model,
                code="provider_schema_mismatch",
                diagnostics=InvalidResponseDiagnostics(
                    stage="provider_schema_validation_failed",
                    diagnostic_code="scene_schema_validation_failed",
                    field_path=first_error_path(errors),
                    validation_errors=errors,
                    validation_error_count=error_count,
                ),
            )
            self._attach_and_log(
                invalid,
                request=request,
                payload=payload,
                phase="auto_scene_analysis",
                provider_attempt=1,
                provider_call_number=provider_call_number,
                repair_attempt=False,
            )
            raise invalid from exc

    async def _infer(
        self,
        *,
        request,
        resolved,
        prompt: str,
        image_base64: str | None,
        phase: str,
        provider_attempt: int,
        provider_call_number: int,
        response_schema: dict,
        schema_name: str,
        repair_attempt: bool = False,
    ):
        logger.info(
            (
                "provider_request request_id=%s filename=%s phase=%s "
                "provider_call_number=%d provider_attempt=%d repair=%s "
                "provider=%s resolved_model=%s"
            ),
            request.request_id,
            request.filename,
            phase,
            provider_call_number,
            provider_attempt,
            str(repair_attempt).lower(),
            resolved.definition.provider,
            resolved.resolved_model,
        )
        try:
            return await resolved.client.infer(
                prompt=prompt,
                image_base64=image_base64,
                request_id=str(request.request_id),
                response_schema=response_schema,
                schema_name=schema_name,
            )
        except InvalidModelResponseError as exc:
            self._attach_and_log(
                exc,
                request=request,
                payload=None,
                phase=phase,
                provider_attempt=provider_attempt,
                provider_call_number=provider_call_number,
                repair_attempt=repair_attempt,
            )
            raise

    @staticmethod
    def _build_develop_response(payload, *, request, resolved, selection, scene):
        return build_model_response(
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

    @staticmethod
    def _repairable(exc: InvalidModelResponseError, client) -> bool:
        return bool(
            getattr(client, "supports_structured_repair", False)
        ) and exc.diagnostics.stage in {
            "provider_schema_validation_failed",
            "legacy_schema_normalization_failed",
            "effective_style_mismatch",
        }

    def _attach_and_log(
        self,
        exc: InvalidModelResponseError,
        *,
        request,
        payload,
        phase: str,
        provider_attempt: int,
        provider_call_number: int,
        repair_attempt: bool,
    ) -> None:
        exc.with_diagnostic_context(
            phase=phase,
            provider_attempt=provider_attempt,
            provider_call_number=provider_call_number,
            repair_attempt=repair_attempt,
        )
        diagnostics = exc.diagnostics
        if payload is not None:
            diagnostics = replace(
                diagnostics,
                provider_content_length=(
                    diagnostics.provider_content_length
                    if diagnostics.provider_content_length is not None
                    else getattr(payload, "provider_content_length", None)
                ),
                extracted_json_length=(
                    diagnostics.extracted_json_length
                    if diagnostics.extracted_json_length is not None
                    else getattr(payload, "extracted_json_length", None)
                ),
                markdown_fences_present=(
                    diagnostics.markdown_fences_present
                    or bool(getattr(payload, "markdown_fences_present", False))
                ),
                raw_content=(
                    diagnostics.raw_content
                    or getattr(payload, "raw_content", None)
                ),
            )
            exc.diagnostics = diagnostics
        logger.warning(
            (
                "model_response_invalid request_id=%s filename=%s phase=%s "
                "stage=%s diagnostic_code=%s field=%s "
                "validation_error_count=%d validation_errors=%s "
                "provider_content_length=%s extracted_json_length=%s "
                "markdown_fences_present=%s trailing_text_present=%s "
                "legacy_normalization_attempted=%s provider_call_number=%d "
                "provider_attempt=%d repair=%s"
            ),
            request.request_id,
            request.filename,
            phase,
            diagnostics.stage,
            diagnostics.diagnostic_code,
            diagnostics.field_path or "<none>",
            diagnostics.validation_error_count,
            json.dumps(list(diagnostics.validation_errors), separators=(",", ":")),
            diagnostics.provider_content_length,
            diagnostics.extracted_json_length,
            str(diagnostics.markdown_fences_present).lower(),
            str(diagnostics.trailing_text_present).lower(),
            str(diagnostics.legacy_normalization_attempted).lower(),
            provider_call_number,
            provider_attempt,
            str(repair_attempt).lower(),
        )
        if self._log_invalid_model_response and diagnostics.raw_content is not None:
            logger.warning(
                (
                    "invalid_model_response_content request_id=%s filename=%s "
                    "phase=%s provider_call_number=%d repair=%s content=%s"
                ),
                request.request_id,
                request.filename,
                phase,
                provider_call_number,
                str(repair_attempt).lower(),
                sanitize_invalid_content(
                    diagnostics.raw_content,
                    max_chars=self._invalid_response_max_chars,
                ),
            )

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
            geometry_analysis=scene.geometry_analysis.model_copy(deep=True),
            dynamic_range_analysis=
                scene.dynamic_range_analysis.model_copy(deep=True),
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
