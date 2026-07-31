"""Provider-neutral inference transport interface."""

from typing import Any, Protocol


class ProviderClient(Protocol):
    """Transport capable of returning one normalized JSON object."""

    async def infer(
        self,
        *,
        prompt: str,
        image_base64: str | None,
        request_id: str,
        response_schema: dict[str, Any] | None = None,
        schema_name: str | None = None,
    ) -> dict[str, Any]:
        """Perform one inference call."""
