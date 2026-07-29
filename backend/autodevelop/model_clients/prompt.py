"""Small provider-neutral prompt construction helpers."""

import json

from autodevelop.models import AnalyzeRequest, DevelopRequest
from autodevelop.profiles import StyleProfile


def build_prompt(
    request: AnalyzeRequest | DevelopRequest,
    profile: StyleProfile,
    *,
    operation: str,
) -> str:
    """Build a concise JSON-only instruction without embedding image content."""

    context = {
        "operation": operation,
        "schema_version": request.schema_version,
        "filename": request.filename,
        "style_profile": profile.id,
        "editing_goals": profile.editing_goals,
        "cautions": profile.cautions,
        "exif": request.exif.model_dump(mode="json", exclude_none=True),
        "current_settings": request.current_settings.model_dump(
            mode="json", exclude_none=True
        ),
        "options": request.options.model_dump(mode="json"),
    }
    return (
        "Return only one JSON object matching the AutoDevelop AI "
        f"{operation} response fields. Context: "
        + json.dumps(context, separators=(",", ":"))
    )
