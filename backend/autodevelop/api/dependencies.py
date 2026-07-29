"""Overrideable FastAPI dependencies for API routes."""

from fastapi import Request

from autodevelop.model_clients import FakeModelClient, ModelClient
from autodevelop.profiles import StyleProfileLoader


def get_model_client() -> ModelClient:
    """Return the configured model client for one API request."""

    return FakeModelClient()


async def get_style_profile_loader(request: Request) -> StyleProfileLoader:
    """Return the initialized application-scoped style-profile loader."""

    return request.app.state.style_profile_loader
