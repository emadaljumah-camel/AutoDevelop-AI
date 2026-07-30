"""Layered provider-neutral prompt construction helpers."""

from copy import deepcopy
import json
from typing import Any

from autodevelop.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    DevelopRequest,
    DevelopResponse,
)
from autodevelop.profiles import StyleProfile
from autodevelop.profiles.selection import SceneSignals, StyleSelection
from autodevelop.learning.personalization import render_personalization
from autodevelop.learning.schemas import PersonalizationContext
from autodevelop.model_clients.prompt_layers import (
    FINAL_SELF_REVIEW,
    HDR_RULES,
    LIGHTROOM_RULES,
    MASTER_EDITING_PHILOSOPHY,
    ROLE_AND_GOAL,
    render_prompt_layers,
)

_BACKEND_IDENTITY_FIELDS = (
    "schema_version",
    "request_id",
    "filename",
    "model",
    "resolved_model",
    "learning",
    "requested_style_id",
    "effective_style_id",
    "style_selection_mode",
    "style_selection_reason",
    "editing_intensity",
    "scene_confidence",
)


def _provider_response_schema(operation: str) -> dict[str, Any]:
    """Return the canonical response schema without backend-owned identity."""

    response_type = AnalyzeResponse if operation == "analyze" else DevelopResponse
    schema = deepcopy(response_type.model_json_schema(mode="validation"))
    properties = schema.get("properties", {})
    for field in _BACKEND_IDENTITY_FIELDS:
        properties.pop(field, None)
    required = schema.get("required")
    if isinstance(required, list):
        schema["required"] = [
            field for field in required if field not in _BACKEND_IDENTITY_FIELDS
        ]
    schema.pop("examples", None)
    return schema


def build_prompt(
    request: AnalyzeRequest | DevelopRequest,
    profile: StyleProfile,
    *,
    operation: str,
    personalization: PersonalizationContext | None = None,
    selection: StyleSelection,
) -> str:
    """Build ordered premium editing layers without embedding image content."""

    context = {
        "operation": operation,
        "schema_version": request.schema_version,
        "filename": request.filename,
        "requested_style_id": selection.requested_style_id,
        "effective_style_id": selection.effective_style_id,
        "scene_analysis": selection.scene.model_dump(mode="json"),
        "editing_goals": profile.editing_goals,
        "cautions": profile.cautions,
        "slider_ranges": {
            name: slider_range.model_dump(mode="json", exclude_none=True)
            for name, slider_range in profile.slider_ranges.items()
        },
        "crop_policy": profile.crop_policy.model_dump(mode="json"),
        "leveling_policy": profile.leveling_policy.model_dump(mode="json"),
        "denoise_policy": profile.denoise_policy.model_dump(mode="json"),
        "exif": request.exif.model_dump(mode="json", exclude_none=True),
        "current_settings": request.current_settings.model_dump(
            mode="json", exclude_none=True
        ),
        "options": request.options.model_dump(mode="json"),
    }
    contract = _provider_response_schema(operation)
    style_layer = render_prompt_layers(
        (
            "SELECTED STYLE\n"
            f"Backend-selected style ID: {profile.id}\n"
            f"Style name: {profile.display_name}\n"
            f"Style intent: {profile.description}\n"
            "Goals:\n- "
            + "\n- ".join(profile.editing_goals)
            + "\nCautions:\n- "
            + "\n- ".join(profile.cautions),
            "EDITING INTENSITY\n"
            f"Use {selection.editing_intensity} intensity as qualitative guidance, "
            "not a slider multiplier. Determine each value from this image.",
        )
    )
    learning_layer = (
        render_personalization(personalization)
        if operation == "develop" and personalization is not None
        else "USER LEARNING PREFERENCES\nNo usable personalized preference context."
    )
    required_items = (
        "Always include analysis, edit_plan, warnings, crop, leveling, and denoise."
    )
    if operation == "develop":
        required_items += (
            " Always include enable_hdr with recommended=true or false "
            "and reason=null."
        )
    contract_layer = (
        f"OUTPUT CONTRACT\nProduce an AutoDevelop AI {operation} result. Return "
        "exactly one JSON object with no Markdown, code fences, hidden reasoning, "
        "commentary, NaN, or Infinity. The status must be \"success\". "
        + required_items
        + f" Use the exact backend-selected style_profile {profile.id!r} "
        "in edit_plan. Do not include "
        "schema_version, request_id, filename, model, resolved_model, learning, "
        "or style-selection diagnostics; the trusted backend supplies them. "
        "Unknown fields are forbidden. Confidence values must be "
        "between 0 and 1. Missing or null Lightroom develop values mean leave "
        "unchanged; never replace an unknown value with zero. Recommend only "
        "canonical develop_settings keys present in the JSON Schema and keep "
        "values within the supplied style slider_ranges. Put composition bounds "
        "only in crop and rotational correction only in leveling; never put "
        "CropAngle in develop_settings. When crop is recommended, provide "
        "all four bounds satisfying 0 <= left < right <= 1 and "
        "0 <= top < bottom <= 1; otherwise use crop=null or recommended=false "
        "with null bounds. When leveling is recommended, provide a finite angle "
        "and mode horizon, vertical, or both. Otherwise use recommended=false, "
        "angle=0, and mode=none. A crop decision must never imply leveling, and "
        "a leveling decision must never imply a composition crop. When denoise "
        "is not recommended, amount must be null. Follow crop_policy, "
        "leveling_policy, and denoise_policy.\n\nCONTEXT JSON\n"
        + json.dumps(context, separators=(",", ":"))
        + "\n\nJSON SCHEMA\n"
        + json.dumps(contract, separators=(",", ":"))
    )
    return render_prompt_layers(
        (
            ROLE_AND_GOAL,
            MASTER_EDITING_PHILOSOPHY,
            "SCENE ANALYSIS\n"
            + json.dumps(selection.scene.model_dump(mode="json"), separators=(",", ":")),
            style_layer,
            learning_layer,
            HDR_RULES,
            LIGHTROOM_RULES,
            FINAL_SELF_REVIEW,
            contract_layer,
        )
    )


def build_scene_analysis_prompt(request: AnalyzeRequest | DevelopRequest) -> str:
    """Build the strict first-pass scene interpretation contract."""

    context = {
        "filename": request.filename,
        "exif": request.exif.model_dump(mode="json", exclude_none=True),
    }
    schema = SceneSignals.model_json_schema(mode="validation")
    return render_prompt_layers(
        (
            "SCENE ANALYSIS\nIdentify only the observable semantic signals needed "
            "for backend-owned style selection. Assess likely RAW highlight and "
            "shadow recoverability from the scene and source/EXIF context; do not "
            "treat clipping or darkness in the rendered JPEG preview alone as "
            "proof that RAW detail is unrecoverable. Do not select or recommend "
            "a style.",
            "Return exactly one JSON object matching the schema. Do not return "
            "Markdown, commentary, hidden reasoning, NaN, Infinity, or extra fields.",
            "IMAGE CONTEXT\n" + json.dumps(context, separators=(",", ":")),
            "JSON SCHEMA\n" + json.dumps(schema, separators=(",", ":")),
        )
    )
