"""Service health endpoint."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from autodevelop import __version__

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health endpoint response."""

    status: Literal["ok"]
    service: str
    version: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report that the backend process is available."""

    return HealthResponse(
        status="ok",
        service="AutoDevelop AI",
        version=__version__,
    )
