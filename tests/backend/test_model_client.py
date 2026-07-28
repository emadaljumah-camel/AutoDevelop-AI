import asyncio
import json

import httpx
import pytest

from autodevelop.model.client import (
    LMStudioClient,
    LMStudioError,
    extract_json_object,
)


def test_extract_json_object_repairs_common_model_output() -> None:
    content = 'Result:\n```json\n{"exposure": +0.5, "enabled": true}\n```'

    assert extract_json_object(content) == {
        "exposure": 0.5,
        "enabled": True,
    }


def test_extract_json_object_rejects_invalid_content() -> None:
    with pytest.raises(LMStudioError, match="valid JSON object"):
        extract_json_object("no object was returned")


def test_list_models_uses_versioned_lm_studio_route() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(
            200,
            json={"data": [{"id": "local-vision-model", "object": "model"}]},
        )

    client = LMStudioClient(
        "http://lm-studio.test/v1",
        transport=httpx.MockTransport(handler),
    )

    models = asyncio.run(client.list_models())

    assert [model.id for model in models] == ["local-vision-model"]


def test_complete_json_sends_only_caller_provided_messages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload["model"] == "configured-model"
        assert payload["messages"] == [
            {"role": "user", "content": "Return a JSON object."}
        ]
        assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"status": "ready"}',
                        }
                    }
                ]
            },
        )

    client = LMStudioClient(
        "http://lm-studio.test/v1",
        model="configured-model",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(
        client.complete_json(
            [{"role": "user", "content": "Return a JSON object."}]
        )
    )

    assert result == {"status": "ready"}


def test_complete_json_requires_configured_model() -> None:
    client = LMStudioClient("http://lm-studio.test/v1")

    with pytest.raises(LMStudioError, match="model must be configured"):
        asyncio.run(client.complete_json([]))


def test_http_error_is_wrapped_with_response_detail() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="model is unavailable")

    client = LMStudioClient(
        "http://lm-studio.test/v1",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LMStudioError, match="model is unavailable"):
        asyncio.run(client.list_models())
