"""Overrideable FastAPI dependencies for API routes."""

from fastapi import Request

from autodevelop.model_clients import ModelClient
from autodevelop.model_clients import ModelResolver
from autodevelop.config import Settings
from autodevelop.profiles import StyleProfileLoader
from autodevelop.validation import SafetyValidator


async def get_model_client(request: Request) -> ModelClient:
    """Return the application-scoped provider-neutral model service."""

    return request.app.state.model_service


async def get_model_resolver(request: Request) -> ModelResolver:
    """Return the application-scoped stateless model resolver."""

    return request.app.state.model_resolver


async def get_runtime_settings(request: Request) -> Settings:
    """Return the validated application-scoped runtime settings."""

    return request.app.state.settings


async def get_style_profile_loader(request: Request) -> StyleProfileLoader:
    """Return the initialized application-scoped style-profile loader."""

    return request.app.state.style_profile_loader


async def get_safety_validator(request: Request) -> SafetyValidator:
    """Return the application-scoped stateless safety validator."""

    return request.app.state.safety_validator
