"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from autodevelop import __version__
from autodevelop.api.router import api_router
from autodevelop.config import Settings, get_settings
from autodevelop.logging_config import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the AutoDevelop AI ASGI application."""

    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging(
            log_path=resolved_settings.log_path,
            level=resolved_settings.log_level,
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
