"""FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from autodevelop import __version__
from autodevelop.api.router import api_router
from autodevelop.config import Settings, get_settings
from autodevelop.logging_config import configure_logging
from autodevelop.profiles import StyleProfileLoader


logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    profile_loader: StyleProfileLoader | None = None,
) -> FastAPI:
    """Create the AutoDevelop AI ASGI application."""

    resolved_settings = settings or get_settings()
    application_profile_loader = (
        profile_loader if profile_loader is not None else StyleProfileLoader()
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
