"""FastAPI application entry point."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from autodevelop import __version__
from autodevelop.api.router import api_router
from autodevelop.config import Settings, get_settings
from autodevelop.logging_config import configure_logging
from autodevelop.learning.database import LearningDatabase, LearningDatabaseError
from autodevelop.learning.embedding import LocalColorLuminanceEmbedding
from autodevelop.learning.repository import LearningRepository
from autodevelop.learning.service import LearningService
from autodevelop.model_clients import ModelClient, ModelResolver, ModelService
from autodevelop.profiles import StyleProfileLoader
from autodevelop.validation import SafetyValidator


logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    profile_loader: StyleProfileLoader | None = None,
    safety_validator: SafetyValidator | None = None,
    model_client: ModelClient | None = None,
    model_resolver: ModelResolver | None = None,
    learning_service: LearningService | None = None,
) -> FastAPI:
    """Create the AutoDevelop AI ASGI application."""

    resolved_settings = settings or get_settings()
    application_profile_loader = (
        profile_loader if profile_loader is not None else StyleProfileLoader()
    )
    application_safety_validator = safety_validator or SafetyValidator()
    application_model_resolver = model_resolver or ModelResolver(resolved_settings)
    application_model_service = model_client
    application_learning_service = learning_service

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configure_logging(
            log_path=resolved_settings.log_path,
            level=resolved_settings.log_level,
        )
        logger.info(
            (
                "configuration_loaded config_source=%s default_model=%s "
                "local_base_url_configured=%s gemma_model_configured=%s "
                "qwen_model_configured=%s gpt_oss_model_configured=%s "
                "gemini_model_configured=%s gemini_api_key_configured=%s "
                "learning_enabled=%s learning_database_configured=%s "
                "learning_minimum_samples=%d learning_maximum_results=%d "
                "learning_minimum_similarity=%.2f"
            ),
            resolved_settings.configuration_source_summary,
            resolved_settings.default_model,
            bool(resolved_settings.local_base_url),
            bool(resolved_settings.gemma_model),
            bool(resolved_settings.qwen_model),
            bool(resolved_settings.gpt_oss_model),
            bool(resolved_settings.gemini_model),
            bool(
                resolved_settings.gemini_api_key.get_secret_value().strip()
            ),
            str(resolved_settings.learning_enabled).lower(),
            str(bool(resolved_settings.learning_db)).lower(),
            resolved_settings.learning_min_samples,
            resolved_settings.learning_max_results,
            resolved_settings.learning_min_similarity,
        )
        try:
            application_profile_loader.reload_profiles()
        except Exception:
            logger.exception("Failed to initialize AutoDevelop AI style profiles.")
            raise
        nonlocal application_learning_service
        if application_learning_service is None:
            repository = None
            if resolved_settings.learning_enabled:
                try:
                    database = LearningDatabase(resolved_settings.learning_db)
                    await asyncio.to_thread(database.initialize)
                    repository = LearningRepository(
                        database,
                        resolved_settings.learning_max_candidate_pool,
                    )
                except LearningDatabaseError:
                    logger.warning("learning_database_unavailable")
            embedding = LocalColorLuminanceEmbedding()
            application_learning_service = LearningService(
                settings=resolved_settings,
                repository=repository,
                profile_loader=application_profile_loader,
                embedding_provider=embedding,
            )
        nonlocal application_model_service
        if application_model_service is None:
            application_model_service = ModelService(
                application_model_resolver,
                application_profile_loader,
                application_learning_service,
            )
        application.state.style_profile_loader = application_profile_loader
        application.state.safety_validator = application_safety_validator
        application.state.model_service = application_model_service
        application.state.model_resolver = application_model_resolver
        application.state.learning_service = application_learning_service
        logger.info(
            (
                "learning_initialized enabled=%s database_available=%s "
                "embedding_available=%s feature_type=%s"
            ),
            resolved_settings.learning_enabled,
            application_learning_service.database_available,
            application_learning_service.embedding_available,
            application_learning_service.feature_type,
        )
        yield

    application = FastAPI(
        title=resolved_settings.app_name,
        version=__version__,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.include_router(
        api_router,
        prefix=resolved_settings.api_prefix,
    )
    return application


app = create_app()
