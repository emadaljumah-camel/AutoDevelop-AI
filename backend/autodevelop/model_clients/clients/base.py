"""Provider-neutral inference transport interface."""

from typing import Any, Protocol


class ProviderClient(Protocol):
    """Transport capable of returning one normalized JSON object."""

    async def infer(
        self,
        *,
        prompt: str,
        image_base64: str,
        request_id: str,
    ) -> dict[str, Any]:
        """Perform one inference call."""
