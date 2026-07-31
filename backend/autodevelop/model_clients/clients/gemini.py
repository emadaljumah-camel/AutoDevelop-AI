"""Google Gemini REST transport."""

import json
from typing import Any

import httpx

from autodevelop.model_clients.exceptions import (
    InvalidModelResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from autodevelop.model_clients.parsing import parse_json_object


class GeminiClient:
    """Call Gemini generateContent using environment-supplied credentials."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._client = client

    async def infer(
        self,
        *,
        prompt: str,
        image_base64: str | None,
        request_id: str,
        response_schema: dict[str, Any] | None = None,
        schema_name: str | None = None,
    ) -> dict[str, Any]:
        parts: list[dict[str, Any]] = [{"text": prompt}]
        if image_base64 is not None:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_base64,
                    }
                }
            )
        payload = {
            "contents": [
                {
                    "parts": parts,
                }
            ],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url="https://generativelanguage.googleapis.com/v1beta/",
            timeout=self._timeout,
        )
        try:
            response = await client.post(
                f"models/{self.model}:generateContent",
                json=payload,
                headers={
                    "x-goog-api-key": self._api_key,
                    "X-Request-ID": request_id,
                },
            )
            response.raise_for_status()
            data = response.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            if not isinstance(text, str):
                raise TypeError("content is not text")
            return parse_json_object(text, model_name=self.model)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                "The Gemini provider timed out.", model_name=self.model
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                "The Gemini provider is unavailable.", model_name=self.model
            ) from exc
        except InvalidModelResponseError:
            raise
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise InvalidModelResponseError(
                "The Gemini provider returned invalid output.", model_name=self.model
            ) from exc
        finally:
            if owns_client:
                await client.aclose()
