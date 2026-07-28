"""Minimal client for LM Studio's OpenAI-compatible API."""

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

import httpx
from pydantic import BaseModel


class LMStudioError(RuntimeError):
    """Raised when LM Studio cannot complete a requested operation."""


class LMStudioModel(BaseModel):
    """Model metadata returned by LM Studio."""

    id: str
    object: str = "model"


class _ModelListResponse(BaseModel):
    data: list[LMStudioModel]


_LEADING_PLUS_NUMBER_RE = re.compile(
    r"(?P<prefix>[:\[,]\s*)\+(?P<number>\d+(?:\.\d+)?)"
)


def _remove_leading_plus_from_json_numbers(content: str) -> str:
    return _LEADING_PLUS_NUMBER_RE.sub(r"\g<prefix>\g<number>", content)


def extract_json_object(content: str) -> dict[str, Any]:
    """Extract one JSON object from plain or surrounding model text."""

    candidates = [content]
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end > start:
        candidates.append(content[start : end + 1])

    for candidate in candidates:
        for possible_json in (
            candidate,
            _remove_leading_plus_from_json_numbers(candidate),
        ):
            try:
                value = json.loads(possible_json)
            except json.JSONDecodeError:
                continue

            if isinstance(value, dict):
                return value

    preview = content[:500].replace("\n", "\\n")
    raise LMStudioError(
        f"LM Studio did not return a valid JSON object. Response preview: {preview}"
    )


class LMStudioClient:
    """Client for LM Studio's OpenAI-compatible HTTP API."""

    def __init__(
        self,
        base_url: str,
        *,
        model: str = "",
        timeout_seconds: float = 30.0,
        max_tokens: int = 2048,
        use_response_format: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_tokens = max_tokens
        self._use_response_format = use_response_format
        self._transport = transport

    async def list_models(self) -> list[LMStudioModel]:
        """Return models exposed by the configured LM Studio server."""

        response = await self._request("GET", "models")
        try:
            payload = _ModelListResponse.model_validate(response.json())
        except (json.JSONDecodeError, ValueError) as exc:
            raise LMStudioError(
                "LM Studio returned an unexpected model-list response"
            ) from exc
        return payload.data

    async def complete_json(
        self,
        messages: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Send caller-provided messages and return one JSON object."""

        if not self._model:
            raise LMStudioError("An LM Studio model must be configured")

        payload: dict[str, Any] = {
            "model": self._model,
            "temperature": 0.1,
            "max_tokens": self._max_tokens,
            "messages": [dict(message) for message in messages],
        }
        if self._use_response_format:
            payload["response_format"] = {"type": "json_object"}

        response = await self._request(
            "POST",
            "chat/completions",
            json_payload=payload,
        )
        try:
            response_payload = response.json()
            content = response_payload["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise LMStudioError(
                "LM Studio returned an unexpected chat-completion response"
            ) from exc

        if isinstance(content, list):
            content = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict)
            )
        if not isinstance(content, str):
            raise LMStudioError(
                "LM Studio returned an unexpected chat-completion response"
            )

        return extract_json_object(content)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any] | None = None,
    ) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                base_url=f"{self._base_url}/",
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.request(
                    method,
                    path,
                    json=json_payload,
                )
                response.raise_for_status()
                return response
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip()
            if len(detail) > 1000:
                detail = f"{detail[:1000]}..."
            raise LMStudioError(
                f"LM Studio request failed: {exc}. Response: {detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise LMStudioError(f"LM Studio request failed: {exc}") from exc
