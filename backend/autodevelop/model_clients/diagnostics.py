"""Safe, bounded diagnostics for invalid provider responses."""

from dataclasses import dataclass, field, replace
import re
from typing import Any, Iterable, Mapping

from pydantic import ValidationError

_SECRET_RE = re.compile(
    r"(?i)(authorization|api[_-]?key|token|secret)\s*[:=]\s*([^\s,;]+)"
)
_DATA_IMAGE_RE = re.compile(
    r"(?i)data:image/[a-z0-9.+-]+;base64,[a-z0-9+/=\s]+"
)
_LONG_BASE64_RE = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{160,}={0,2}")
_SAFE_MESSAGE_RE = re.compile(r"[^A-Za-z0-9 _.,:;()\[\]{}'\"/+\-=]")


@dataclass(frozen=True)
class InvalidResponseDiagnostics:
    """Structured diagnostic context that is safe to summarize in logs."""

    stage: str
    diagnostic_code: str
    field_path: str | None = None
    validation_errors: tuple[Mapping[str, str], ...] = field(default_factory=tuple)
    validation_error_count: int = 0
    provider_content_length: int | None = None
    extracted_json_length: int | None = None
    markdown_fences_present: bool = False
    trailing_text_present: bool = False
    legacy_normalization_attempted: bool = False
    phase: str | None = None
    provider_attempt: int | None = None
    provider_call_number: int | None = None
    repair_attempt: bool = False
    raw_content: str | None = field(default=None, repr=False, compare=False)

    def with_context(
        self,
        *,
        phase: str | None = None,
        provider_attempt: int | None = None,
        provider_call_number: int | None = None,
        repair_attempt: bool | None = None,
    ) -> "InvalidResponseDiagnostics":
        """Return a copy with request-local inference context attached."""

        return replace(
            self,
            phase=phase if phase is not None else self.phase,
            provider_attempt=(
                provider_attempt
                if provider_attempt is not None
                else self.provider_attempt
            ),
            provider_call_number=(
                provider_call_number
                if provider_call_number is not None
                else self.provider_call_number
            ),
            repair_attempt=(
                repair_attempt
                if repair_attempt is not None
                else self.repair_attempt
            ),
        )


def sanitize_invalid_content(content: str, *, max_chars: int) -> str:
    """Redact obvious secrets and image data, then apply a hard length bound."""

    bounded_max = max(1, max_chars)
    sanitized = _DATA_IMAGE_RE.sub("[REDACTED_IMAGE_DATA]", content)
    sanitized = _LONG_BASE64_RE.sub("[REDACTED_BASE64]", sanitized)
    sanitized = _SECRET_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", sanitized)
    if len(sanitized) > bounded_max:
        return sanitized[:bounded_max] + "...[TRUNCATED]"
    return sanitized


def validation_error_summary(
    exc: ValidationError,
    *,
    limit: int = 5,
) -> tuple[int, tuple[Mapping[str, str], ...]]:
    """Return bounded Pydantic errors without rejected input or unsafe context."""

    raw_errors = exc.errors(include_input=False, include_context=False)
    summarized: list[Mapping[str, str]] = []
    for error in raw_errors[:limit]:
        path = ".".join(str(part) for part in error.get("loc", ())) or "<root>"
        error_type = str(error.get("type", "validation_error"))
        message = _SAFE_MESSAGE_RE.sub(
            "",
            str(error.get("msg", "Validation failed.")),
        )[:160]
        summarized.append(
            {
                "path": path[:240],
                "type": error_type[:120],
                "message": message,
            }
        )
    return len(raw_errors), tuple(summarized)


def first_error_path(errors: Iterable[Mapping[str, str]]) -> str | None:
    """Return the first bounded validation path, if present."""

    for error in errors:
        return error.get("path")
    return None
