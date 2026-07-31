"""Provider-neutral parsing for JSON model responses."""

import json
import re
from typing import Any

from autodevelop.model_clients.diagnostics import InvalidResponseDiagnostics
from autodevelop.model_clients.exceptions import InvalidModelResponseError

_FENCE_START_RE = re.compile(r"^\s*```(?:json)?\s*", re.IGNORECASE)
_FENCE_END_RE = re.compile(r"\s*```\s*$")


class ParsedProviderPayload(dict[str, Any]):
    """Parsed object retaining only bounded-diagnostic transport metadata."""

    def __init__(
        self,
        value: dict[str, Any],
        *,
        raw_content: str,
        extracted_json_length: int,
        markdown_fences_present: bool,
    ) -> None:
        super().__init__(value)
        self.raw_content = raw_content
        self.provider_content_length = len(raw_content)
        self.extracted_json_length = extracted_json_length
        self.markdown_fences_present = markdown_fences_present


def _failure(
    message: str,
    *,
    model_name: str,
    stage: str,
    diagnostic_code: str,
    content: str,
    candidate: str | None = None,
    fences_present: bool = False,
    trailing_text_present: bool = False,
) -> InvalidModelResponseError:
    return InvalidModelResponseError(
        message,
        model_name=model_name,
        code=(
            "provider_json_parse_failed"
            if stage == "json_parse_failed"
            else (
                "provider_schema_mismatch"
                if stage == "provider_schema_validation_failed"
                else "invalid_model_response"
            )
        ),
        diagnostics=InvalidResponseDiagnostics(
            stage=stage,
            diagnostic_code=diagnostic_code,
            provider_content_length=len(content),
            extracted_json_length=len(candidate) if candidate is not None else None,
            markdown_fences_present=fences_present,
            trailing_text_present=trailing_text_present,
            raw_content=content,
        ),
    )


def parse_json_object(content: str, *, model_name: str) -> dict[str, Any]:
    """Parse one plain or fenced JSON object into a mapping."""

    if not isinstance(content, str):
        raise InvalidModelResponseError(
            "The provider response content was not text.",
            model_name=model_name,
            diagnostics=InvalidResponseDiagnostics(
                stage="empty_provider_content",
                diagnostic_code="provider_content_not_text",
            ),
        )

    stripped = content.strip()
    if not stripped:
        raise _failure(
            "The provider response content was empty.",
            model_name=model_name,
            stage="empty_provider_content",
            diagnostic_code="empty_provider_content",
            content=content,
        )

    fences_present = bool(_FENCE_START_RE.match(stripped))
    if fences_present:
        start = _FENCE_START_RE.match(stripped)
        end = _FENCE_END_RE.search(stripped)
        if start is None or end is None or end.start() < start.end():
            raise _failure(
                "The provider JSON fence was incomplete.",
                model_name=model_name,
                stage="json_extraction_failed",
                diagnostic_code="incomplete_markdown_fence",
                content=content,
                fences_present=True,
            )
        candidate = stripped[start.end() : end.start()].strip()
    else:
        candidate = stripped

    try:
        value, end_index = json.JSONDecoder().raw_decode(candidate)
    except json.JSONDecodeError as exc:
        diagnostic_code = (
            "truncated_json"
            if exc.pos >= max(0, len(candidate) - 1)
            or "unterminated" in exc.msg.lower()
            else "invalid_json"
        )
        raise _failure(
            "The provider response was not a valid JSON object.",
            model_name=model_name,
            stage="json_parse_failed",
            diagnostic_code=diagnostic_code,
            content=content,
            candidate=candidate,
            fences_present=fences_present,
        ) from exc
    trailing_text = candidate[end_index:].strip()
    if trailing_text:
        raise _failure(
            "The provider response contained trailing text.",
            model_name=model_name,
            stage="json_extraction_failed",
            diagnostic_code="trailing_provider_text",
            content=content,
            candidate=candidate[:end_index],
            fences_present=fences_present,
            trailing_text_present=True,
        )
    if not isinstance(value, dict):
        raise _failure(
            "The provider response was not a JSON object.",
            model_name=model_name,
            stage="provider_schema_validation_failed",
            diagnostic_code="top_level_not_object",
            content=content,
            candidate=candidate,
            fences_present=fences_present,
        )
    return ParsedProviderPayload(
        value,
        raw_content=content,
        extracted_json_length=len(candidate),
        markdown_fences_present=fences_present,
    )
