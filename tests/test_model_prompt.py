import json

import pytest

from autodevelop.model_clients.prompt import build_prompt, build_scene_analysis_prompt
from autodevelop.models import AnalyzeRequest, DevelopRequest
from autodevelop.learning.schemas import PersonalizationContext
from autodevelop.profiles import SceneSignals, StyleProfileLoader, select_style


@pytest.fixture
def profile():
    loader = StyleProfileLoader()
    loader.reload_profiles()
    return loader.get_cached_profile("natural_travel")


def _request(request_type):
    return request_type.model_validate(
        {
            "schema_version": "1.0",
            "request_id": "11111111-1111-4111-8111-111111111111",
            "filename": "Prompt.NEF",
            "model": "qwen",
            "preview_base64": "secret-image-content",
            "exif": {"iso": 400},
            "current_settings": {"Exposure2012": 0.0},
            "options": {"style_profile": "natural_travel"},
        }
    )


def _selection():
    return select_style(
        "natural_travel",
        SceneSignals(
            primary_subject_type="landscape",
            scene_category="scenic_travel",
            confidence=0.9,
        ),
    )


def _prompt_sections(prompt: str) -> tuple[dict, dict]:
    context_text, schema_text = prompt.split("\n\nJSON SCHEMA\n", maxsplit=1)
    context = json.loads(context_text.split("\n\nCONTEXT JSON\n", maxsplit=1)[1])
    return context, json.loads(schema_text)


@pytest.mark.parametrize(
    ("request_type", "operation", "has_develop_settings"),
    [
        (AnalyzeRequest, "analyze", False),
        (DevelopRequest, "develop", True),
    ],
)
def test_prompt_uses_canonical_provider_contract(
    profile,
    request_type,
    operation: str,
    has_develop_settings: bool,
) -> None:
    prompt = build_prompt(
        _request(request_type),
        profile,
        operation=operation,
        selection=_selection(),
    )
    context, schema = _prompt_sections(prompt)

    assert context["effective_style_id"] == "natural_travel"
    assert context["current_settings"]["Exposure2012"] == 0.0
    assert context["slider_ranges"] == {
        name: value.model_dump(mode="json", exclude_none=True)
        for name, value in profile.slider_ranges.items()
    }
    assert context["crop_policy"] == profile.crop_policy.model_dump(mode="json")
    assert context["denoise_policy"] == profile.denoise_policy.model_dump(mode="json")

    properties = schema["properties"]
    for trusted_field in (
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
    ):
        assert trusted_field not in properties
        assert trusted_field not in schema.get("required", [])
    assert "analysis" in properties
    assert "edit_plan" in properties
    assert "crop" in properties
    assert "denoise" in properties
    assert "warnings" in properties
    assert ("enable_hdr" in properties) is has_develop_settings
    assert ("develop_settings" in properties) is has_develop_settings


def test_prompt_states_safety_and_null_rules_without_sensitive_image(profile) -> None:
    prompt = build_prompt(
        _request(DevelopRequest),
        profile,
        operation="develop",
        selection=_selection(),
    )

    assert "Unknown fields are forbidden" in prompt
    assert "never replace an unknown value with zero" in prompt
    assert "0 <= left < right <= 1" in prompt
    assert "0 <= top < bottom <= 1" in prompt
    assert "When denoise is not recommended, amount must be null" in prompt
    assert "secret-image-content" not in prompt
    assert "Authorization" not in prompt


def test_prompt_layers_are_ordered_and_master_philosophy_appears_once(profile) -> None:
    prompt = build_prompt(
        _request(DevelopRequest),
        profile,
        operation="develop",
        selection=_selection(),
    )
    normalized = " ".join(prompt.split())

    headings = (
        "ROLE AND GOAL",
        "MASTER EDITING PHILOSOPHY",
        "SCENE ANALYSIS",
        "SELECTED STYLE",
        "EDITING INTENSITY",
        "USER LEARNING PREFERENCES",
        "LIGHTROOM HDR EDIT MODE",
        "LIGHTROOM RULES",
        "FINAL SELF-REVIEW",
        "OUTPUT CONTRACT",
    )
    positions = [prompt.index(heading) for heading in headings]
    assert positions == sorted(positions)
    assert prompt.count("MASTER EDITING PHILOSOPHY") == 1
    assert "strong but believable" in prompt
    assert "visually weak" in normalized
    assert "Do not return this reasoning" in prompt


def test_learning_layer_follows_style_and_precedes_lightroom_rules(profile) -> None:
    context = PersonalizationContext(
        profile_id="natural_travel",
        sample_count=3,
        usable_sample_count=5,
        average_similarity=0.86,
        preferred_adjustments={"Contrast2012": 4.0},
        crop_adjustments={},
        leveling_adjustments={},
        accepted_without_change_ratio=0.0,
        feature_type="test",
    )
    prompt = build_prompt(
        _request(DevelopRequest),
        profile,
        operation="develop",
        selection=_selection(),
        personalization=context,
    )

    assert prompt.index("SELECTED STYLE") < prompt.index(
        "PERSONAL EDITING PREFERENCES FROM SIMILAR PHOTOS"
    )
    assert prompt.index(
        "PERSONAL EDITING PREFERENCES FROM SIMILAR PHOTOS"
    ) < prompt.index("LIGHTROOM HDR EDIT MODE")
    assert "must never force Lightroom HDR edit mode on or off" in prompt


@pytest.mark.parametrize(
    ("profile_id", "required_phrases"),
    [
        ("stock_neutral", ("rather than a flat", "meaningful whites and blacks")),
        ("portrait", ("clearly finished portrait", "conservative skin-local")),
        ("documentary", ("professionally finished", "authenticity")),
        ("architecture", ("strong structural definition", "defined shadows")),
        ("night", ("luminous but controlled", "defined blacks")),
        ("natural_travel", ("strong premium", "atmospheric separation")),
        ("landscape_impact", ("strongest believable", "foreground, midground")),
    ],
)
def test_every_profile_prompt_has_stronger_subject_aware_impact(
    profile_id: str,
    required_phrases: tuple[str, ...],
) -> None:
    loader = StyleProfileLoader()
    loader.reload_profiles()
    selected = loader.get_cached_profile(profile_id)
    selection = select_style(
        profile_id,
        SceneSignals(
            primary_subject_type="unknown",
            scene_category="unknown",
            confidence=0.5,
        ),
    )
    prompt = " ".join(build_prompt(
        _request(DevelopRequest),
        selected,
        operation="develop",
        selection=selection,
    ).lower().split())

    assert "professionally finished" in prompt
    assert "stock-thumbnail" in prompt
    assert "visually weak" in prompt
    assert all(phrase.lower() in prompt for phrase in required_phrases)


def test_hdr_prompt_is_scene_driven_and_never_promotes_artificial_hdr(profile) -> None:
    prompt = " ".join(build_prompt(
        _request(DevelopRequest),
        profile,
        operation="develop",
        selection=_selection(),
    ).split())

    assert "likely RAW highlight and shadow recoverability" in prompt
    assert "Style selection and HDR selection are independent" in prompt
    assert "not an artificial HDR look" in prompt
    assert "create HDR halos" not in prompt
    assert "add an artificial HDR look" not in prompt


def test_scene_analysis_estimates_raw_recoverability_beyond_jpeg_preview() -> None:
    prompt = " ".join(
        build_scene_analysis_prompt(_request(DevelopRequest)).split()
    )

    assert "RAW highlight and shadow recoverability" in prompt
    assert "JPEG preview alone" in prompt


@pytest.mark.parametrize(
    ("profile_id", "phrases"),
    [
        (
            "architecture",
            ("perspective convergence", "intentional architectural viewpoint"),
        ),
        (
            "documentary",
            ("authentic dynamic framing", "documentary context"),
        ),
        (
            "portrait",
            ("shoulder lines", "facial asymmetry"),
        ),
    ],
)
def test_profile_leveling_guidance_remains_subject_specific(
    profile_id: str,
    phrases: tuple[str, ...],
) -> None:
    loader = StyleProfileLoader()
    loader.reload_profiles()
    selected = loader.get_cached_profile(profile_id)
    prompt = build_prompt(
        _request(DevelopRequest),
        selected,
        operation="develop",
        selection=select_style(
            profile_id,
            SceneSignals(
                primary_subject_type="unknown",
                scene_category="unknown",
                confidence=0.5,
            ),
        ),
    ).lower()

    assert all(phrase in prompt for phrase in phrases)
    assert "a crop decision must never imply leveling" in prompt
    assert "leveling decision must never imply a composition crop" in prompt
