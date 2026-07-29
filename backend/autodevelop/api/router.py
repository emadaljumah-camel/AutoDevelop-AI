"""Versioned API router."""

from fastapi import APIRouter

from autodevelop.api.routes.analyze import router as analyze_router
from autodevelop.api.routes.develop import router as develop_router
from autodevelop.api.routes.health import router as health_router
from autodevelop.api.routes.models import router as models_router

api_router = APIRouter()
api_router.include_router(analyze_router)
api_router.include_router(develop_router)
api_router.include_router(health_router)
api_router.include_router(models_router)
