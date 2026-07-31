"""Application service for baseline, feedback, and personalization workflows."""

import asyncio
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from autodevelop.config import Settings
from autodevelop.learning.constants import (
    MAX_PAYLOAD_BYTES,
    SUPPORTED_SETTINGS,
)
from autodevelop.learning.comparison import (
    FeedbackComparison,
    compare_feedback_settings,
)
from autodevelop.learning.embedding import ImageEmbeddingProvider
from autodevelop.learning.feature_cache import FeatureHandoffCache
from autodevelop.learning.personalization import (
    aggregate_hdr_preference,
    aggregate_preferences,
)
from autodevelop.learning.models import RetrievalSample
from autodevelop.learning.repository import LearningRepository, PhotoKeyMismatchError
from autodevelop.learning.schemas import (
    BaselineRequest,
    BaselineResponse,
    DevelopModeState,
    FeedbackRequest,
    FeedbackPreviewResponse,
    FeedbackSettingComparison,
    FeedbackResponse,
    FeatureVector,
    LearningDiagnostics,
    LearningExifContext,
    LearningModeChanges,
    LearningStatusResponse,
    PersonalizationContext,
    safe_model_dump,
)
from autodevelop.learning.similarity import LearningRetriever
from autodevelop.models import DevelopRequest
from autodevelop.models.registry import get_model_definition
from autodevelop.profiles import ProfileNotFoundError, StyleProfileLoader

logger = logging.getLogger(__name__)


class LearningPayloadTooLargeError(ValueError):
    pass


class LearningProfileError(ValueError):
    pass


class LearningModelError(ValueError):
    pass


class LearningUnavailableError(RuntimeError):
    """Raised when an enabled learning operation has no storage repository."""


class LearningBaselineUnavailableError(RuntimeError):
    """Raised when a stored baseline has no comparable canonical settings."""


@dataclass(frozen=True)
class PersonalizationResult:
    context: PersonalizationContext | None
    diagnostics: LearningDiagnostics
    feature: FeatureVector | None


class LearningService:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: LearningRepository | None,
        profile_loader: StyleProfileLoader,
        embedding_provider: ImageEmbeddingProvider,
        feature_cache: FeatureHandoffCache | None = None,
        retriever: LearningRetriever | None = None,
    ) -> None:
        self.settings = settings
        self._repository = repository
        self._profiles = profile_loader
        self._embedding = embedding_provider
        self._cache = feature_cache or FeatureHandoffCache()
        self._retriever = retriever or LearningRetriever()
        self._embedding_failure_reported = False

    @property
    def database_available(self) -> bool:
        return self._repository is not None

    @property
    def embedding_available(self) -> bool:
        return self._embedding.available

    @property
    def feature_type(self) -> str | None:
        return self._embedding.feature_type

    async def prepare_personalization(
        self,
        request: DevelopRequest,
        image_bytes: bytes,
        *,
        profile_id: str | None = None,
    ) -> PersonalizationResult:
        effective_profile_id = profile_id or request.options.style_profile
        enabled = (
            self.settings.learning_enabled
            and request.learning.enabled
            and self._repository is not None
        )
        feature = await self._embed_safely(image_bytes)
        if self.settings.learning_enabled:
            self._cache.put(str(request.request_id), feature)
        if not enabled:
            reason = (
                "database_unavailable"
                if self.settings.learning_enabled and self._repository is None
                else "disabled"
            )
            return self._result(None, feature, reason, 0, 0)
        exif_context = learning_exif_context(request)
        try:
            candidates, hdr_candidates = await asyncio.gather(
                asyncio.to_thread(
                    self._repository.retrieval_candidates,
                    effective_profile_id,
                ),
                asyncio.to_thread(
                    self._repository.hdr_retrieval_candidates,
                ),
            )
            usable_count = len(candidates)
            retrieved = (
                self._retriever.retrieve(
                    candidates,
                    feature=feature,
                    exif_context=exif_context,
                    minimum_similarity=self.settings.learning_min_similarity,
                    maximum_results=self.settings.learning_max_results,
                )
                if usable_count >= self.settings.learning_min_samples
                else []
            )
            hdr_retrieved = self._retriever.retrieve(
                hdr_candidates,
                feature=feature,
                exif_context=exif_context,
                minimum_similarity=self.settings.learning_min_similarity,
                maximum_results=self.settings.learning_max_results,
            )
            context = (
                aggregate_preferences(
                    retrieved,
                    profile_id=effective_profile_id,
                    usable_sample_count=usable_count,
                    feature_type=feature.feature_type if feature else None,
                )
                if len(retrieved) >= self.settings.learning_min_samples
                else None
            )
            hdr_preferred, hdr_support, hdr_enable_rate = (
                aggregate_hdr_preference(hdr_retrieved)
                if len(hdr_retrieved) >= self.settings.learning_min_samples
                else (None, len(hdr_retrieved), None)
            )
            hdr_applied = hdr_preferred is not None
            if context is not None:
                context = context.model_copy(
                    update={
                        "preferred_hdr_enabled": hdr_preferred,
                        "hdr_support_count": hdr_support,
                        "hdr_enable_rate": hdr_enable_rate,
                    },
                    deep=True,
                )
            reason = None
            if context is None and not hdr_applied:
                reason = (
                    "insufficient_samples"
                    if usable_count < self.settings.learning_min_samples
                    else "no_similar_samples"
                )
            return PersonalizationResult(
                context=context,
                diagnostics=LearningDiagnostics(
                    enabled=True,
                    personalization_applied=context is not None or hdr_applied,
                    usable_sample_count=usable_count,
                    retrieved_sample_count=len(retrieved),
                    minimum_sample_count=self.settings.learning_min_samples,
                    average_similarity=(
                        context.average_similarity
                        if context is not None
                        else self._average_similarity(retrieved)
                    ),
                    feature_type=feature.feature_type if feature else None,
                    hdr_personalization_applied=hdr_applied,
                    hdr_learning_enable_rate=hdr_enable_rate,
                    hdr_learning_sample_count=hdr_support,
                    reason=reason,
                ),
                feature=feature,
            )
        except Exception:
            logger.warning(
                "learning_retrieval_unavailable request_id=%s",
                request.request_id,
            )
            return self._result(
                None, feature, "retrieval_unavailable", 0, 0
            )

    async def store_baseline(self, request: BaselineRequest) -> BaselineResponse:
        repository = self._require_repository()
        self._validate_payload_size(request)
        try:
            self._profiles.get_cached_profile(request.profile)
        except ProfileNotFoundError as exc:
            raise LearningProfileError("The style profile is not registered.") from exc
        definition = get_model_definition(request.model)
        if definition is None or not definition.selectable:
            raise LearningModelError("The selected model is not available.")
        feature = self._cache.pop(str(request.request_id))
        stored = await asyncio.to_thread(
            repository.store_baseline,
            request,
            feature,
        )
        logger.info(
            "learning_baseline_saved session_id=%s stored=%s",
            request.session_id,
            stored,
        )
        return BaselineResponse(session_id=request.session_id, stored=stored)

    async def capture_feedback(
        self, request: FeedbackRequest
    ) -> FeedbackResponse:
        repository = self._require_repository()
        comparison = await self._compare_feedback(request)
        feedback_id = uuid4()
        await asyncio.to_thread(
            repository.upsert_feedback,
            feedback_id=feedback_id,
            session_id=request.session_id,
            final_settings=comparison.final_settings,
            delta=comparison.delta,
            significant_delta=comparison.significant_delta,
            crop_delta=comparison.crop_delta,
            leveling_delta=comparison.leveling_delta,
            final_modes=comparison.final_modes,
            upright_changed=comparison.upright_changed,
            hdr_changed=comparison.hdr_changed,
            accepted_without_change=comparison.accepted_without_change,
            usable=True,
            exclusion_reason=None,
        )
        logger.info(
            (
                "learning_feedback_saved session_id=%s "
                "significant_setting_count=%d accepted_without_change=%s usable=true"
            ),
            request.session_id,
            len(
                comparison.significant_delta.model_dump(exclude_none=True)
            )
            + len(comparison.crop_delta.model_dump(exclude_none=True))
            + len(comparison.leveling_delta.model_dump(exclude_none=True))
            + int(comparison.upright_changed)
            + int(comparison.hdr_changed),
            comparison.accepted_without_change,
        )
        logger.info(
            (
                "learning_mode_feedback session_id=%s "
                "upright_changed=%s upright_ai_mode=%s "
                "upright_final_mode=%s hdr_changed=%s "
                "hdr_ai_enabled=%s hdr_final_enabled=%s"
            ),
            request.session_id,
            str(comparison.upright_changed).lower(),
            comparison.ai_upright_mode,
            comparison.final_modes.upright,
            str(comparison.hdr_changed).lower(),
            comparison.ai_hdr_enabled,
            comparison.final_modes.hdr_enabled,
        )
        return FeedbackResponse(
            feedback_id=feedback_id,
            session_id=request.session_id,
            usable=True,
            accepted_without_change=comparison.accepted_without_change,
            significant_changes=comparison.significant_delta,
            ignored_changes=comparison.ignored_delta,
            crop_changes=comparison.crop_delta,
            leveling_changes=comparison.leveling_delta,
            mode_changes=LearningModeChanges(
                upright=(
                    comparison.final_modes.upright
                    if comparison.upright_changed
                    else None
                ),
                hdr_enabled=(
                    comparison.final_modes.hdr_enabled
                    if comparison.hdr_changed
                    else None
                ),
            ),
        )

    async def preview_feedback(
        self,
        request: FeedbackRequest,
    ) -> FeedbackPreviewResponse:
        comparison = await self._compare_feedback(request)

        def details(keys: Mapping[str, float]) -> dict[
            str, FeedbackSettingComparison
        ]:
            return {
                key: FeedbackSettingComparison(
                    **comparison.comparisons[key].__dict__
                )
                for key in keys
            }

        return FeedbackPreviewResponse(
            session_id=request.session_id,
            has_significant_changes=not comparison.accepted_without_change,
            accepted_without_change=comparison.accepted_without_change,
            significant_changes=details(
                comparison.significant_delta.model_dump(exclude_none=True)
            ),
            ignored_changes=details(
                comparison.ignored_delta.model_dump(exclude_none=True)
            ),
            crop_changes=details(
                comparison.crop_delta.model_dump(exclude_none=True)
            ),
            leveling_changes=details(
                comparison.leveling_delta.model_dump(exclude_none=True)
            ),
            mode_changes=LearningModeChanges(
                upright=(
                    comparison.final_modes.upright
                    if comparison.upright_changed
                    else None
                ),
                hdr_enabled=(
                    comparison.final_modes.hdr_enabled
                    if comparison.hdr_changed
                    else None
                ),
            ),
        )

    async def _compare_feedback(
        self,
        request: FeedbackRequest,
    ) -> FeedbackComparison:
        repository = self._require_repository()
        self._validate_payload_size(request)
        session = await asyncio.to_thread(
            repository.get_session,
            request.session_id,
        )
        if session.photo_key != request.photo_key:
            raise PhotoKeyMismatchError(
                "The photo does not match the learning session."
            )
        final = {
            key: float(value)
            for key, value in request.final_settings.model_dump(
                exclude_none=True
            ).items()
        }
        comparison = compare_feedback_settings(
            session.applied_baseline,
            final,
            applied_modes=DevelopModeState(
                upright=session.applied_upright_mode,
                hdr_enabled=session.applied_hdr_enabled,
            ),
            final_modes=request.final_modes,
        )
        if (
            not comparison.comparisons
            and session.applied_upright_mode is None
            and session.applied_hdr_enabled is None
        ):
            raise LearningBaselineUnavailableError(
                "The stored applied baseline is unavailable."
            )
        if logger.isEnabledFor(logging.DEBUG):
            for key in SUPPORTED_SETTINGS:
                detail = comparison.comparisons.get(key)
                if detail is None:
                    logger.debug(
                        "learning_feedback_comparison setting=%s comparable=false",
                        key,
                    )
                else:
                    logger.debug(
                        (
                            "learning_feedback_comparison setting=%s "
                            "baseline=%s current=%s delta=%s threshold=%s "
                            "significant=%s"
                        ),
                        key,
                        detail.baseline,
                        detail.current,
                        detail.delta,
                        detail.threshold,
                        str(detail.significant).lower(),
                    )
        return comparison

    async def status(self) -> LearningStatusResponse:
        if self._repository is None:
            counts = {
                "pending_sessions": 0,
                "feedback_samples": 0,
                "usable_samples": 0,
                "accepted_without_change": 0,
                "upright_usable_sample_count": 0,
                "upright_change_count": 0,
                "upright_acceptance_count": 0,
                "hdr_usable_sample_count": 0,
                "hdr_change_count": 0,
                "hdr_acceptance_count": 0,
            }
        else:
            counts = await asyncio.to_thread(self._repository.status_counts)
        return LearningStatusResponse(
            enabled=self.settings.learning_enabled,
            database_available=self._repository is not None,
            embedding_available=self._embedding.available,
            feature_type=self._embedding.feature_type,
            minimum_samples=self.settings.learning_min_samples,
            pending_sessions=counts["pending_sessions"],
            feedback_samples=counts["feedback_samples"],
            usable_samples=counts["usable_samples"],
            accepted_without_change=counts["accepted_without_change"],
            upright_learning={
                "usable_sample_count": counts[
                    "upright_usable_sample_count"
                ],
                "change_count": counts["upright_change_count"],
                "acceptance_count": counts["upright_acceptance_count"],
            },
            hdr_learning={
                "usable_sample_count": counts["hdr_usable_sample_count"],
                "change_count": counts["hdr_change_count"],
                "acceptance_count": counts["hdr_acceptance_count"],
            },
        )

    async def dismiss(self, session_id: UUID) -> bool:
        return await asyncio.to_thread(
            self._require_repository().dismiss_session,
            session_id,
        )

    async def delete_all(self) -> int:
        return await asyncio.to_thread(
            self._require_repository().delete_all
        )

    async def _embed_safely(self, image_bytes: bytes) -> FeatureVector | None:
        if not self.settings.learning_enabled or not self._embedding.available:
            return None
        try:
            return await asyncio.to_thread(self._embedding.embed, image_bytes)
        except Exception:
            if not self._embedding_failure_reported:
                logger.warning("learning_embedding_unavailable")
                self._embedding_failure_reported = True
            return None

    def _require_repository(self) -> LearningRepository:
        if self._repository is None:
            raise LearningUnavailableError("Learning storage is unavailable.")
        return self._repository

    @staticmethod
    def _validate_payload_size(request) -> None:
        encoded = json.dumps(
            safe_model_dump(request),
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_PAYLOAD_BYTES:
            raise LearningPayloadTooLargeError(
                "The learning payload exceeds the supported size."
            )

    def _result(
        self,
        context: PersonalizationContext | None,
        feature: FeatureVector | None,
        reason: str,
        usable: int,
        retrieved: int,
        average_similarity: float | None = None,
    ) -> PersonalizationResult:
        return PersonalizationResult(
            context=context,
            diagnostics=LearningDiagnostics(
                enabled=self.settings.learning_enabled,
                personalization_applied=False,
                usable_sample_count=usable,
                retrieved_sample_count=retrieved,
                minimum_sample_count=self.settings.learning_min_samples,
                average_similarity=average_similarity,
                feature_type=feature.feature_type if feature else None,
                reason=reason,
            ),
            feature=feature,
        )

    @staticmethod
    def _average_similarity(samples: list[RetrievalSample]) -> float | None:
        if not samples:
            return None
        return sum(sample.similarity for sample in samples) / len(samples)


def learning_exif_context(request: DevelopRequest) -> LearningExifContext:
    capture_category = "unknown"
    captured = request.exif.capture_date
    if isinstance(captured, datetime):
        hour = captured.hour
        if hour < 5 or hour >= 21:
            capture_category = "night"
        elif hour < 10:
            capture_category = "morning"
        elif hour < 17:
            capture_category = "day"
        else:
            capture_category = "evening"
    return LearningExifContext(
        camera=request.exif.camera,
        lens=request.exif.lens,
        iso=request.exif.iso,
        aperture=request.exif.aperture,
        shutter_speed=request.exif.shutter_speed,
        focal_length=request.exif.focal_length,
        capture_time_category=capture_category,
        orientation=request.exif.orientation,
        width=request.exif.width,
        height=request.exif.height,
    )
