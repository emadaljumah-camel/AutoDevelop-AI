"""Provider-neutral parsing for JSON model responses."""

import json
import re
from typing import Any

from autodevelop.model_clients.exceptions import InvalidModelResponseError

_FENCED_JSON_RE = re.compile(
    r"^\s*```(?:json)?\s*(?P<payload>\{.*\})\s*```\s*$",
    re.IGNORECASE | re.DOTALL,
)


def parse_json_object(content: str, *, model_name: str) -> dict[str, Any]:
    """Parse one plain or fenced JSON object into a mapping."""

    if not isinstance(content, str):
        raise InvalidModelResponseError(
            "The provider response content was not text.",
            model_name=model_name,
        )

    fenced = _FENCED_JSON_RE.match(content)
    candidate = fenced.group("payload") if fenced else content.strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise InvalidModelResponseError(
            "The provider response was not a valid JSON object.",
            model_name=model_name,
        ) from exc
    if not isinstance(value, dict):
        raise InvalidModelResponseError(
            "The provider response was not a JSON object.",
            model_name=model_name,
        )
    return value
