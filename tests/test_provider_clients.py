import asyncio
import json

import httpx
import pytest

from autodevelop.model_clients import InvalidModelResponseError, ProviderTimeoutError
from autodevelop.model_clients.clients import GeminiClient, LocalOpenAIClient


def test_local_transport_uses_configured_model_and_blank_key() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["json"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"status":"success"}'}}]},
        )

    async def invoke() -> dict[str, object]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://local.test/v1/",
        ) as client:
            return await LocalOpenAIClient(
                base_url="http://local.test/v1",
                api_key="",
                model="configured-qwen",
                timeout_seconds=10,
                client=client,
            ).infer(prompt="json", image_base64="aW1hZ2U=", request_id="request")

    result = asyncio.run(invoke())
    assert result == {"status": "success"}
    assert captured["json"]["model"] == "configured-qwen"  # type: ignore[index]
    assert "response_format" not in captured["json"]  # type: ignore[operator]
    assert "authorization" not in captured["headers"]  # type: ignore[operator]


def test_gemini_transport_uses_inline_image_and_api_key_header() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["json"] = json.loads(request.content)
        captured["path"] = request.url.path
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": '{"status":"success"}'}]}}
                ]
            },
        )

    async def invoke() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://generativelanguage.googleapis.com/v1beta/",
        ) as client:
            await GeminiClient(
                api_key="secret",
                model="gemini-test",
                timeout_seconds=10,
                client=client,
            ).infer(prompt="json", image_base64="aW1hZ2U=", request_id="request")

    asyncio.run(invoke())
    assert captured["path"].endswith("/models/gemini-test:generateContent")  # type: ignore[union-attr]
    parts = captured["json"]["contents"][0]["parts"]  # type: ignore[index]
    assert parts[1]["inline_data"]["data"] == "aW1hZ2U="
    assert captured["headers"]["x-goog-api-key"] == "secret"  # type: ignore[index]


def test_timeout_is_structured() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    async def invoke() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://local.test/v1/",
        ) as client:
            await LocalOpenAIClient(
                base_url="http://local.test/v1",
                api_key="",
                model="gemma",
                timeout_seconds=10,
                client=client,
            ).infer(prompt="json", image_base64="aW1hZ2U=", request_id="request")

    with pytest.raises(ProviderTimeoutError):
        asyncio.run(invoke())


@pytest.mark.parametrize(
    "content",
    [
        "plain non-json text",
        "Markdown without a JSON object",
        '{"status": "truncated"',
        '["not", "an", "object"]',
    ],
)
def test_local_malformed_output_is_invalid_model_response(content: str) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
        )

    async def invoke() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://local.test/v1/",
        ) as client:
            await LocalOpenAIClient(
                base_url="http://local.test/v1",
                api_key="",
                model="gemma",
                timeout_seconds=10,
                client=client,
            ).infer(prompt="json", image_base64="aW1hZ2U=", request_id="request")

    with pytest.raises(InvalidModelResponseError) as raised:
        asyncio.run(invoke())
    assert raised.value.code == (
        "provider_schema_mismatch"
        if content.startswith("[")
        else "provider_json_parse_failed"
    )
    assert content not in str(raised.value)


@pytest.mark.parametrize(
    "content",
    ['{"status":"success"}', '```json\n{"status":"success"}\n```'],
)
def test_local_plain_and_fenced_json_objects_are_accepted(content: str) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
        )

    async def invoke() -> dict[str, object]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://local.test/v1/",
        ) as client:
            return await LocalOpenAIClient(
                base_url="http://local.test/v1",
                api_key="",
                model="gemma",
                timeout_seconds=10,
                client=client,
            ).infer(prompt="json", image_base64="aW1hZ2U=", request_id="request")

    assert asyncio.run(invoke()) == {"status": "success"}


def test_gemini_malformed_output_is_invalid_model_response() -> None:
    secret = "gemini-test-secret"
    malformed = "not-json-secret-body"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": malformed}]}}]},
        )

    async def invoke() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://generativelanguage.googleapis.com/v1beta/",
        ) as client:
            await GeminiClient(
                api_key=secret,
                model="gemini-test",
                timeout_seconds=10,
                client=client,
            ).infer(prompt="json", image_base64="aW1hZ2U=", request_id="request")

    with pytest.raises(InvalidModelResponseError) as raised:
        asyncio.run(invoke())
    assert raised.value.code == "provider_json_parse_failed"
    assert secret not in str(raised.value)
    assert malformed not in str(raised.value)
