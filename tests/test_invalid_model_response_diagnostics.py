import asyncio
import json
import logging
from typing import Any

import httpx
import pytest

from autodevelop.api.model_errors import model_error_response
from autodevelop.config import Settings
from autodevelop.config_loader import parse_models_yaml
from autodevelop.model_clients.clients.local_openai import LocalOpenAIClient
from autodevelop.model_clients.diagnostics import sanitize_invalid_content
from autodevelop.model_clients.exceptions import InvalidModelResponseError
from autodevelop.model_clients.parsing import (
    ParsedProviderPayload,
    parse_json_object,
)
from autodevelop.model_clients.prompt import (
    build_repair_prompt,
    provider_response_schema,
)
from autodevelop.model_clients.resolver import ModelResolver
from autodevelop.model_clients.response_validation import build_model_response
from autodevelop.model_clients.service import ModelService
from autodevelop.models import DevelopRequest, DevelopResponse
from autodevelop.profiles import StyleProfileLoader


def _request(style: str = "natural_travel") -> DevelopRequest:
    return DevelopRequest.model_validate(
        {
            "schema_version": "1.0",
            "request_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "filename": "DSC_7543.NEF",
            "model": "qwen",
            "preview_base64": "aW1hZ2U=",
            "options": {"style_profile": style},
        }
    )


def _payload(style: str = "natural_travel") -> dict[str, Any]:
    return {
        "status": "success",
        "analysis": {
            "scene_type": "travel",
            "main_subject": "building",
            "confidence": 0.9,
        },
        "edit_plan": {
            "style_profile": style,
            "goals": ["Correct tone"],
            "cautions": ["Keep color believable"],
        },
        "develop_settings": {"Exposure2012": 0.2},
        "crop": None,
        "leveling": {
            "recommended": False,
            "angle": 0.0,
            "mode": "none",
        },
        "denoise": None,
        "enable_hdr": {"recommended": False, "reason": None},
        "warnings": [],
    }


def _scene_payload() -> dict[str, Any]:
    return {
        "primary_subject_type": "architecture",
        "primary_subject": "building",
        "scene_category": "architecture",
        "lighting_type": "daylight",
        "dynamic_range": "moderate",
        "noise_level": "low",
        "color_character": "balanced",
        "confidence": 0.94,
        "editing_priorities": ["Correct structure"],
        "highlight_recoverability": "moderate",
        "shadow_recoverability": "moderate",
    }


def _build(payload: dict[str, Any], *, style: str = "natural_travel"):
    request = _request(style)
    return build_model_response(
        payload,
        request,
        response_type=DevelopResponse,
        expected_resolved_model="qwen_qwen3-vl-32b-instruct",
        requested_style_id=style,
        effective_style_id=style,
        style_selection_mode="manual",
        style_selection_reason="Manual style override",
        editing_intensity="moderate",
        scene_confidence=None,
    )


class SequenceRepairProvider:
    supports_structured_repair = True

    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = payloads
        self.calls: list[dict[str, Any]] = []

    async def infer(self, **kwargs):
        self.calls.append(kwargs)
        return self.payloads[len(self.calls) - 1]


def _service(provider, **kwargs) -> ModelService:
    settings = Settings(_env_file=None)
    loader = StyleProfileLoader()
    loader.reload_profiles()
    resolver = ModelResolver(settings, provider_clients={"qwen": provider})
    return ModelService(resolver, loader, **kwargs)


def test_valid_qwen_json_and_fenced_json_pass_current_contract() -> None:
    plain = json.dumps(_payload())
    parsed = parse_json_object(plain, model_name="qwen")
    fenced = parse_json_object(f"```json\n{plain}\n```", model_name="qwen")

    assert _build(parsed).edit_plan.style_profile == "natural_travel"
    assert _build(fenced).leveling.mode == "none"
    assert fenced.markdown_fences_present is True


def test_trailing_commentary_is_rejected_with_explicit_diagnostic() -> None:
    with pytest.raises(InvalidModelResponseError) as raised:
        parse_json_object(
            json.dumps(_payload()) + "\nHere is why.",
            model_name="qwen",
        )

    assert raised.value.diagnostics.stage == "json_extraction_failed"
    assert raised.value.diagnostics.diagnostic_code == "trailing_provider_text"
    assert raised.value.diagnostics.trailing_text_present is True


def test_schema_errors_report_missing_field_and_bounded_path() -> None:
    payload = _payload()
    payload.pop("status")

    with pytest.raises(InvalidModelResponseError) as raised:
        _build(payload)

    diagnostics = raised.value.diagnostics
    assert diagnostics.stage == "provider_schema_validation_failed"
    assert diagnostics.diagnostic_code == "missing_required_field"
    assert diagnostics.field_path == "status"
    assert diagnostics.validation_error_count == 1
    assert len(diagnostics.validation_errors) == 1


def test_crop_angle_conflict_is_identified_without_weakening_geometry() -> None:
    payload = _payload()
    payload["crop"] = {
        "recommended": True,
        "left": 0.0,
        "right": 1.0,
        "top": 0.0,
        "bottom": 1.0,
        "confidence": 0.9,
        "reason": "test",
        "angle": 1.0,
    }

    with pytest.raises(InvalidModelResponseError) as raised:
        _build(payload)

    diagnostics = raised.value.diagnostics
    assert diagnostics.stage == "legacy_schema_normalization_failed"
    assert diagnostics.field_path == "crop.angle"
    assert diagnostics.legacy_normalization_attempted is True


@pytest.mark.parametrize(
    ("leveling", "code", "path"),
    [
        (
            {"recommended": True, "angle": None, "mode": "horizon"},
            "schema_validation_failed",
            "leveling.angle",
        ),
        (
            {"recommended": True, "angle": 0.4, "mode": "diagonal"},
            "unsupported_enum",
            "leveling.mode",
        ),
    ],
)
def test_leveling_contract_failures_report_exact_path(
    leveling: dict[str, Any],
    code: str,
    path: str,
) -> None:
    payload = _payload()
    payload["leveling"] = leveling

    with pytest.raises(InvalidModelResponseError) as raised:
        _build(payload)

    assert raised.value.diagnostics.diagnostic_code == code
    assert raised.value.diagnostics.field_path == path


def test_auto_style_and_backend_owned_diagnostics_are_rejected() -> None:
    auto_payload = _payload()
    auto_payload["edit_plan"]["style_profile"] = "auto"
    with pytest.raises(InvalidModelResponseError) as auto_error:
        _build(auto_payload)
    assert auto_error.value.diagnostics.stage == "effective_style_mismatch"

    for field in ("learning", "requested_style_id", "effective_style_id"):
        payload = _payload()
        payload[field] = {}
        with pytest.raises(InvalidModelResponseError) as raised:
            _build(payload)
        assert raised.value.diagnostics.diagnostic_code == "backend_owned_field"
        assert raised.value.diagnostics.field_path == field


def test_non_finite_develop_value_is_rejected() -> None:
    payload = _payload()
    payload["develop_settings"]["Exposure2012"] = float("inf")

    with pytest.raises(InvalidModelResponseError) as raised:
        _build(payload)

    assert raised.value.diagnostics.diagnostic_code == "non_finite_value"
    assert raised.value.diagnostics.field_path == "develop_settings.Exposure2012"


def test_final_repair_succeeds_without_resending_image() -> None:
    invalid = _payload()
    invalid.pop("status")
    provider = SequenceRepairProvider([
        _scene_payload(),
        invalid,
        _payload(),
    ])

    response = asyncio.run(_service(provider).develop(_request()))

    assert response.status == "success"
    assert len(provider.calls) == 3
    assert provider.calls[0]["image_base64"] == "aW1hZ2U="
    assert provider.calls[1]["image_base64"] == "aW1hZ2U="
    assert provider.calls[2]["image_base64"] is None
    assert "VALIDATION ERRORS" in provider.calls[2]["prompt"]
    assert "REQUIRED JSON SCHEMA" in provider.calls[2]["prompt"]


def test_auto_final_repair_reuses_scene_and_effective_style() -> None:
    invalid = _payload("architecture")
    invalid.pop("status")
    provider = SequenceRepairProvider(
        [_scene_payload(), invalid, _payload("architecture")]
    )

    response = asyncio.run(_service(provider).develop(_request("auto")))

    assert response.effective_style_id == "architecture"
    assert len(provider.calls) == 3
    assert "SCENE ANALYSIS" in provider.calls[0]["prompt"]
    assert "INVALID JSON" in provider.calls[2]["prompt"]
    assert provider.calls[2]["image_base64"] is None


def test_repeated_invalid_repair_cannot_override_backend_fields() -> None:
    initial = _payload()
    initial["learning"] = {"enabled": True}
    repaired = _payload()
    repaired["effective_style_id"] = "night"
    provider = SequenceRepairProvider([
        _scene_payload(),
        initial,
        repaired,
    ])

    with pytest.raises(InvalidModelResponseError) as raised:
        asyncio.run(_service(provider).develop(_request()))

    assert raised.value.code == "invalid_model_response_repeated"
    assert raised.value.diagnostics.field_path == "effective_style_id"
    assert len(provider.calls) == 3


def test_scene_failure_logs_phase_and_never_runs_final_inference(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = SequenceRepairProvider([{}])
    caplog.set_level(logging.WARNING, logger="autodevelop.model_clients.service")

    with pytest.raises(InvalidModelResponseError):
        asyncio.run(_service(provider).develop(_request("auto")))

    assert len(provider.calls) == 1
    assert "phase=auto_scene_analysis" in caplog.text
    assert "stage=provider_schema_validation_failed" in caplog.text


def test_invalid_content_sanitization_is_bounded_and_removes_images_and_secrets() -> None:
    raw = (
        "Authorization: Bearer-secret "
        "api_key=top-secret "
        "data:image/jpeg;base64,"
        + ("A" * 500)
    )
    sanitized = sanitize_invalid_content(raw, max_chars=256)

    assert len(sanitized) <= 270
    assert "Bearer-secret" not in sanitized
    assert "top-secret" not in sanitized
    assert "A" * 100 not in sanitized
    assert "data:image" not in sanitized


def test_enabled_invalid_content_logging_is_bounded_and_sanitized(
    caplog: pytest.LogCaptureFixture,
) -> None:
    invalid = _payload()
    invalid.pop("status")
    raw = (
        json.dumps(invalid)
        + " Authorization=provider-secret data:image/jpeg;base64,"
        + ("A" * 1000)
    )

    class RawPayloadProvider:
        async def infer(self, **_kwargs):
            return ParsedProviderPayload(
                invalid,
                raw_content=raw,
                extracted_json_length=len(json.dumps(invalid)),
                markdown_fences_present=False,
            )

    caplog.set_level(logging.WARNING, logger="autodevelop.model_clients.service")
    with pytest.raises(InvalidModelResponseError):
        asyncio.run(
            _service(
                RawPayloadProvider(),
                log_invalid_model_response=True,
                invalid_response_max_chars=256,
            ).develop(_request())
        )

    content_line = next(
        line
        for line in caplog.text.splitlines()
        if "invalid_model_response_content" in line
    )
    assert "provider-secret" not in content_line
    assert "data:image" not in content_line
    assert "A" * 100 not in content_line
    assert "[TRUNCATED]" in content_line


def test_yaml_provider_capability_and_diagnostics_are_strictly_configured() -> None:
    config = parse_models_yaml(
        """
version: 1
providers:
  local:
    response_format: json_object
diagnostics:
  log_invalid_model_response: true
  invalid_response_max_chars: 1200
"""
    )

    assert config.providers is not None
    assert config.providers.local is not None
    assert config.providers.local.response_format == "json_object"
    assert config.diagnostics is not None
    assert config.diagnostics.log_invalid_model_response is True
    assert config.diagnostics.invalid_response_max_chars == 1200


@pytest.mark.parametrize(
    ("mode", "expected_type"),
    [
        ("json_schema", "json_schema"),
        ("json_object", "json_object"),
        ("none", None),
    ],
)
def test_local_provider_capability_controls_response_format(
    mode: str,
    expected_type: str | None,
) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"status":"success"}'}}]},
        )

    async def invoke() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://local.test/v1/",
        ) as client:
            await LocalOpenAIClient(
                base_url="http://local.test/v1",
                api_key="",
                model="qwen",
                timeout_seconds=10,
                response_format_mode=mode,
                client=client,
            ).infer(
                prompt="json",
                image_base64="aW1hZ2U=",
                request_id="request",
                response_schema={"type": "object"},
                schema_name="autodevelop_response",
            )

    asyncio.run(invoke())
    if expected_type is None:
        assert "response_format" not in captured
    else:
        assert captured["response_format"]["type"] == expected_type
    if mode == "json_schema":
        assert captured["response_format"]["json_schema"]["strict"] is True
        assert captured["response_format"]["json_schema"]["schema"] == {
            "type": "object"
        }


def test_retry_classification_distinguishes_truncated_and_schema_failures() -> None:
    request = _request()
    with pytest.raises(InvalidModelResponseError) as truncated:
        parse_json_object('{"status":', model_name="qwen")
    truncated_response = model_error_response(request, truncated.value)
    assert json.loads(truncated_response.body)["error"]["retryable"] is True

    invalid = _payload()
    invalid.pop("status")
    with pytest.raises(InvalidModelResponseError) as schema:
        _build(invalid)
    schema_response = model_error_response(request, schema.value)
    assert json.loads(schema_response.body)["error"]["retryable"] is False


def test_repair_prompt_is_bounded_and_forbids_backend_diagnostic_changes() -> None:
    prompt = build_repair_prompt(
        {"status": "bad"},
        (
            {
                "path": "leveling.angle",
                "type": "finite_number",
                "message": "Input should be finite",
            },
        ),
        provider_response_schema("develop"),
    )

    assert "leveling.angle" in prompt
    assert "REQUIRED JSON SCHEMA" in prompt
    assert "Do not return or modify backend-owned style, learning" in prompt
    assert len(prompt) < 50_000
