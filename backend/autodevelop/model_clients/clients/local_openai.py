"""Shared OpenAI-compatible transport for local vision models."""

import json
from typing import Any

import httpx

from autodevelop.model_clients.exceptions import (
    InvalidModelResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from autodevelop.model_clients.parsing import parse_json_object


class LocalOpenAIClient:
    """Call one configured local OpenAI-compatible vision model."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._client = client

    async def infer(
        self,
        *,
        prompt: str,
        image_base64: str,
        request_id: str,
    ) -> dict[str, Any]:
        headers = {"X-Request-ID": request_id}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = {
            "model": self.model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            },
                        },
                    ],
                }
            ],
        }
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url=f"{self._base_url}/", timeout=self._timeout
        )
        try:
            response = await client.post(
                "chat/completions", json=payload, headers=headers
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("content is not text")
            return parse_json_object(content, model_name=self.model)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                "The local inference provider timed out.", model_name=self.model
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                "The local inference provider is unavailable.",
                model_name=self.model,
            ) from exc
        except InvalidModelResponseError:
            raise
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise InvalidModelResponseError(
                "The local inference provider returned invalid output.",
                model_name=self.model,
            ) from exc
        finally:
            if owns_client:
                await client.aclose()
