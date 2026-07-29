"""Abstract interface for AutoDevelop AI model clients."""

from abc import ABC, abstractmethod

from autodevelop.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    DevelopRequest,
    DevelopResponse,
)


class ModelClient(ABC):
    """Asynchronous interface implemented by vision-model clients."""

    @abstractmethod
    async def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        """Analyze one photo request without producing develop settings."""

    @abstractmethod
    async def develop(
        self,
        request: DevelopRequest,
    ) -> DevelopResponse:
        """Produce raw model recommendations for one photo request."""
