"""FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from autodevelop import __version__
from autodevelop.api.router import api_router
from autodevelop.config import Settings, get_settings
from autodevelop.logging_config import configure_logging
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
) -> FastAPI:
    """Create the AutoDevelop AI ASGI application."""

    resolved_settings = settings or get_settings()
    application_profile_loader = (
        profile_loader if profile_loader is not None else StyleProfileLoader()
    )
    application_safety_validator = safety_validator or SafetyValidator()
    application_model_resolver = model_resolver or ModelResolver(resolved_settings)
    application_model_service = model_client or ModelService(
        application_model_resolver, application_profile_loader
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configure_logging(
            log_path=resolved_settings.log_path,
            level=resolved_settings.log_level,
        )
        try:
            application_profile_loader.reload_profiles()
        except Exception:
            logger.exception("Failed to initialize AutoDevelop AI style profiles.")
            raise
        application.state.style_profile_loader = application_profile_loader
        application.state.safety_validator = application_safety_validator
        application.state.model_service = application_model_service
        application.state.model_resolver = application_model_resolver
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
