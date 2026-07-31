import hashlib
import json
import math
from uuid import UUID

import pytest
from pydantic import ValidationError

from autodevelop.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    CropRecommendation,
    DenoiseRecommendation,
    DevelopRequest,
    DevelopResponse,
    DevelopSettings,
    ErrorResponse,
    HdrRecommendation,
    LearningDiagnostics,
    LevelingRecommendation,
    PhotoExif,
    ProcessingWarning,
    TechnicalAnalysis,
    UprightRecommendation,
)

REQUEST_ID = UUID("11111111-1111-4111-8111-111111111111")

ANALYZE_RESPONSE_DATA = {
    "schema_version": "1.0",
    "request_id": str(REQUEST_ID),
    "filename": "DSC_0001.NEF",
    "status": "success",
    "requested_style_id": "natural_travel",
    "effective_style_id": "natural_travel",
    "style_selection_mode": "manual",
    "style_selection_reason": "Manual style override",
    "editing_intensity": "moderate",
    "scene_confidence": 0.93,
    "analysis": {
        "scene_type": "landscape",
        "main_subject": "mountain lake",
        "lighting": "soft morning light",
        "exposure_assessment": "Highlights are recoverable.",
        "white_balance_assessment": "Slightly cool.",
        "dynamic_range": "high",
        "noise_level": "low",
        "highlight_recoverability": "unknown",
        "shadow_recoverability": "unknown",
        "severe_underexposure": False,
        "horizon_status": "slightly tilted",
        "visible_people": 0,
        "has_faces": False,
        "has_sky": True,
        "confidence": 0.93,
        "geometry_analysis": {
            "reliable_horizontal_lines": False,
            "reliable_vertical_lines": False,
            "camera_roll_detected": False,
            "perspective_convergence": "unknown",
            "upright_candidate_mode": "off",
            "upright_confidence": 0.0,
        },
        "dynamic_range_analysis": {
            "dynamic_range": "unknown",
            "highlight_pressure": "unknown",
            "shadow_pressure": "unknown",
            "backlit": False,
            "bright_sky_dark_foreground": False,
            "bright_windows_dark_interior": False,
            "sunrise_or_sunset": False,
            "hdr_candidate": False,
            "hdr_confidence": 0.0,
        },
    },
    "edit_plan": {
        "style_profile": "natural_travel",
        "goals": ["Recover sky detail", "Add tonal separation"],
        "cautions": ["Preserve natural foliage color"],
    },
    "crop": {
        "recommended": True,
        "left": 0.02,
        "right": 0.98,
        "top": 0.03,
        "bottom": 0.97,
        "confidence": 0.86,
        "reason": "Improve composition.",
    },
    "leveling": {
        "recommended": True,
        "angle": -0.4,
        "mode": "horizon",
    },
    "denoise": {
        "recommended": False,
        "amount": None,
        "confidence": 0.9,
        "reason": "Noise is minimal.",
    },
    "warnings": [
        {
            "code": "preview_limited",
            "message": "Analysis used a rendered preview.",
            "field": "preview_path",
            "severity": "info",
        }
    ],
    "model": "gemma",
    "resolved_model": "local-vision-model",
    "processing_duration_ms": 842,
}

DEVELOP_RESPONSE_DATA = {
    **ANALYZE_RESPONSE_DATA,
    "request_id": "22222222-2222-4222-8222-222222222222",
    "develop_settings": {
        "Exposure2012": 0.3,
        "Contrast2012": 18.0,
        "Highlights2012": -42.0,
        "Shadows2012": 26.0,
        "Whites2012": 14.0,
        "Blacks2012": -12.0,
        "Texture": 10.0,
        "Clarity2012": 8.0,
        "Dehaze": 6.0,
        "Vibrance": 24.0,
        "Saturation": 2.0,
        "Temperature": 5750.0,
        "Tint": 6.0,
        "CropLeft": None,
        "CropRight": None,
        "CropTop": None,
        "CropBottom": None,
        "CropAngle": None,
    },
    "upright": {
        "recommended": False,
        "mode": "off",
        "confidence": 0.0,
        "reason": None,
    },
    "enable_hdr": {
        "recommended": False,
        "enabled": False,
        "confidence": 0.0,
        "reason": None,
    },
    "hdr_decision": None,
}

ERROR_RESPONSE_DATA = {
    "schema_version": "1.0",
    "request_id": "33333333-3333-4333-8333-333333333333",
    "filename": "DSC_0003.NEF",
    "status": "error",
    "error": {
        "code": "invalid_preview",
        "message": "The preview could not be read.",
        "field": "preview_path",
        "retryable": False,
    },
    "warnings": [],
}

PUBLIC_SCHEMA_HASHES = {
    AnalyzeRequest: "4517ffdbdb7f9530adb538036133ad1a54a31569c55dab74b806d066f528cdb0",
    DevelopRequest: "d26a8cc68d0b9675e82422852762698e96168280f4cea0ce70f96e3a3fa9cc48",
    AnalyzeResponse: "35129c750611b35c79e87ff53997d2818fc9784006a00b90895fa939073adc87",
    DevelopResponse: "f65703721fed6a8e9b96f477980dbf803b9dff6801fa2dc569a7706abb7ff44d",
    ErrorResponse: "527d0bbd9b728522f146a539d44bc433c39e7988db3926cda467ce9cdec9994e",
}


def _minimal_request_data() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "request_id": str(REQUEST_ID),
        "filename": "DSC_0001.NEF",
    }


def test_minimal_analyze_request_with_preview_path() -> None:
    request = AnalyzeRequest(
        **_minimal_request_data(),
        preview_path="temp/DSC_0001.jpg",
    )

    assert request.preview_path == "temp/DSC_0001.jpg"
    assert request.exif.model_dump(exclude_none=True) == {}
    assert request.current_settings.model_dump(exclude_none=True) == {}
    assert request.options.style_profile == "auto"


def test_minimal_analyze_request_with_preview_base64() -> None:
    request = AnalyzeRequest(
        **_minimal_request_data(),
        preview_base64="/9j/4AAQSkZJRgABAQ...",
    )

    assert request.preview_base64.startswith("/9j/")


def test_analyze_request_requires_preview_source() -> None:
    with pytest.raises(ValidationError, match="preview_path or preview_base64"):
        AnalyzeRequest.model_validate(_minimal_request_data())


def test_analyze_request_accepts_both_preview_sources() -> None:
    request = AnalyzeRequest(
        **_minimal_request_data(),
        preview_path="temp/DSC_0001.jpg",
        preview_base64="/9j/4AAQSkZJRgABAQ...",
    )

    assert request.preview_path is not None
    assert request.preview_base64 is not None


@pytest.mark.parametrize("filename", ["", " ", "\t"])
def test_blank_filename_is_rejected(filename: str) -> None:
    with pytest.raises(ValidationError):
        AnalyzeRequest(
            schema_version="1.0",
            request_id=REQUEST_ID,
            filename=filename,
            preview_path="temp/preview.jpg",
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("latitude", -90.01),
        ("latitude", 90.01),
        ("longitude", -180.01),
        ("longitude", 180.01),
    ],
)
def test_invalid_latitude_and_longitude_are_rejected(
    field_name: str,
    value: float,
) -> None:
    with pytest.raises(ValidationError):
        PhotoExif.model_validate({field_name: value})


@pytest.mark.parametrize("iso", [0, -1])
def test_zero_or_negative_iso_is_rejected(iso: int) -> None:
    with pytest.raises(ValidationError):
        PhotoExif(iso=iso)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize(
    ("model_type", "payload"),
    [
        (PhotoExif, {"aperture": None}),
        (DevelopSettings, {"Exposure2012": None}),
        (
            LevelingRecommendation,
            {"recommended": True, "angle": None, "mode": "horizon"},
        ),
        (
            DenoiseRecommendation,
            {"recommended": True, "amount": None},
        ),
        (TechnicalAnalysis, {"confidence": None}),
    ],
)
def test_nonfinite_values_are_rejected_for_numeric_model_categories(
    model_type: type[
        PhotoExif
        | DevelopSettings
        | CropRecommendation
        | LevelingRecommendation
        | DenoiseRecommendation
        | TechnicalAnalysis
    ],
    payload: dict[str, object],
    value: float,
) -> None:
    payload = payload.copy()
    field_name = next(key for key, item in payload.items() if item is None)
    payload[field_name] = value

    with pytest.raises(ValidationError):
        model_type.model_validate(payload)


@pytest.mark.parametrize(
    "field_name",
    [
        "Exposure2012",
        "Contrast2012",
        "Highlights2012",
        "Shadows2012",
        "Whites2012",
        "Blacks2012",
        "Texture",
        "Clarity2012",
        "Dehaze",
        "Vibrance",
        "Saturation",
        "Temperature",
        "Tint",
        "CropLeft",
        "CropRight",
        "CropTop",
        "CropBottom",
        "CropAngle",
    ],
)
def test_boolean_is_rejected_for_numeric_develop_settings(
    field_name: str,
) -> None:
    with pytest.raises(ValidationError, match="boolean"):
        DevelopSettings.model_validate({field_name: True})


def test_missing_develop_settings_remain_none() -> None:
    settings = DevelopSettings()

    assert all(value is None for value in settings.model_dump().values())
    assert settings.model_dump(exclude_none=True) == {}


def test_explicit_null_develop_settings_remain_none() -> None:
    settings = DevelopSettings(
        Exposure2012=None,
        CropLeft=None,
        CropAngle=None,
    )

    assert settings.Exposure2012 is None
    assert settings.CropLeft is None
    assert settings.CropAngle is None


def test_partial_develop_settings_are_accepted_without_clamping() -> None:
    settings = DevelopSettings(
        Exposure2012=5000.0,
        Highlights2012=-5000.0,
        CropLeft=0.1,
    )

    assert settings.model_dump(exclude_none=True) == {
        "Exposure2012": 5000.0,
        "Highlights2012": -5000.0,
        "CropLeft": 0.1,
    }


def test_valid_complete_crop_recommendation() -> None:
    crop = CropRecommendation(
        recommended=True,
        left=0.1,
        right=0.9,
        top=0.2,
        bottom=0.8,
        confidence=0.9,
        reason="Improve composition.",
    )

    assert crop.left == 0.1
    assert crop.bottom == 0.8


def test_leveling_state_is_independent_and_strict() -> None:
    leveling = LevelingRecommendation(
        recommended=True,
        angle=-0.5,
        mode="horizon",
    )
    assert leveling.angle == -0.5
    with pytest.raises(ValidationError):
        LevelingRecommendation(
            recommended=False,
            angle=-0.5,
            mode="horizon",
        )


def test_recommended_crop_with_missing_bound_is_rejected() -> None:
    with pytest.raises(ValidationError, match="all crop bounds"):
        CropRecommendation(
            recommended=True,
            left=0.1,
            right=0.9,
            top=0.2,
        )


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (0.5, 0.5),
        (0.7, 0.3),
    ],
)
def test_crop_left_must_be_less_than_right(
    left: float,
    right: float,
) -> None:
    with pytest.raises(ValidationError, match="left < right"):
        CropRecommendation(
            recommended=True,
            left=left,
            right=right,
            top=0.1,
            bottom=0.9,
        )


@pytest.mark.parametrize(
    ("top", "bottom"),
    [
        (0.5, 0.5),
        (0.8, 0.2),
    ],
)
def test_crop_top_must_be_less_than_bottom(
    top: float,
    bottom: float,
) -> None:
    with pytest.raises(ValidationError, match="top < bottom"):
        CropRecommendation(
            recommended=True,
            left=0.1,
            right=0.9,
            top=top,
            bottom=bottom,
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("left", -0.01),
        ("right", 1.01),
        ("top", -1.0),
        ("bottom", 2.0),
    ],
)
def test_crop_coordinate_outside_unit_interval_is_rejected(
    field_name: str,
    value: float,
) -> None:
    payload = {
        "recommended": True,
        "left": 0.1,
        "right": 0.9,
        "top": 0.1,
        "bottom": 0.9,
    }
    payload[field_name] = value

    with pytest.raises(ValidationError):
        CropRecommendation.model_validate(payload)


def test_crop_fields_may_be_null_when_not_recommended() -> None:
    crop = CropRecommendation(
        recommended=False,
        left=None,
        right=None,
        top=None,
        bottom=None,
    )

    assert crop.model_dump(exclude_none=True) == {"recommended": False}


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_confidence_outside_unit_interval_is_rejected(
    confidence: float,
) -> None:
    with pytest.raises(ValidationError):
        TechnicalAnalysis(confidence=confidence)


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        DevelopSettings.model_validate({"UnknownSetting": 1.0})


@pytest.mark.parametrize(
    ("model_type", "payload"),
    [
        (
            AnalyzeRequest,
            {
                **_minimal_request_data(),
                "preview_path": "temp/preview.jpg",
            },
        ),
        (AnalyzeResponse, ANALYZE_RESPONSE_DATA),
        (DevelopResponse, DEVELOP_RESPONSE_DATA),
    ],
)
def test_unknown_fields_remain_rejected_on_public_messages(
    model_type: type[AnalyzeRequest | AnalyzeResponse | DevelopResponse],
    payload: dict[str, object],
) -> None:
    payload = {**payload, "unexpected_field": "unexpected"}

    with pytest.raises(ValidationError, match="Extra inputs"):
        model_type.model_validate(payload)


@pytest.mark.parametrize(
    ("model_type", "payload"),
    [
        (AnalyzeResponse, ANALYZE_RESPONSE_DATA),
        (DevelopResponse, DEVELOP_RESPONSE_DATA),
        (ErrorResponse, ERROR_RESPONSE_DATA),
    ],
)
def test_response_json_serialization_round_trip(
    model_type: type[AnalyzeResponse | DevelopResponse | ErrorResponse],
    payload: dict[str, object],
) -> None:
    response = model_type.model_validate(payload)
    restored = model_type.model_validate_json(response.model_dump_json())

    assert restored == response


@pytest.mark.parametrize(
    ("model_type", "payload"),
    [
        (AnalyzeResponse, ANALYZE_RESPONSE_DATA),
        (DevelopResponse, DEVELOP_RESPONSE_DATA),
    ],
)
def test_processing_response_json_output_is_unchanged(
    model_type: type[AnalyzeResponse | DevelopResponse],
    payload: dict[str, object],
) -> None:
    response = model_type.model_validate(payload)

    serialized = json.loads(response.model_dump_json())
    if model_type is DevelopResponse:
        assert serialized.pop("learning") is None
    assert serialized == payload


@pytest.mark.parametrize("model_type", [AnalyzeResponse, DevelopResponse])
def test_processing_response_warning_lists_are_not_shared(
    model_type: type[AnalyzeResponse | DevelopResponse],
) -> None:
    first = model_type(
        schema_version="1.0",
        request_id=REQUEST_ID,
        filename="first.NEF",
        status="success",
        model="gemma",
        resolved_model="gemma-4-31b",
    )
    second = model_type(
        schema_version="1.0",
        request_id=REQUEST_ID,
        filename="second.NEF",
        status="success",
        model="gemma",
        resolved_model="gemma-4-31b",
    )

    first.warnings.append(
        ProcessingWarning(
            code="first_only",
            message="This warning belongs to the first response.",
            severity="info",
        )
    )
    assert len(first.warnings) == 1
    assert second.warnings == []


def test_mode_recommendations_accept_bounded_explanations() -> None:
    hdr = HdrRecommendation.model_validate(
        {
            "recommended": True,
            "enabled": True,
            "confidence": 0.91,
            "reason": "Strong highlight and shadow pressure.",
        }
    )
    upright = UprightRecommendation.model_validate(
        {
            "recommended": True,
            "mode": "vertical",
            "confidence": 0.88,
            "reason": "Reliable vertical lines converge.",
        }
    )

    assert hdr.reason == "Strong highlight and shadow pressure."
    assert upright.reason == "Reliable vertical lines converge."


@pytest.mark.parametrize("model_type", [AnalyzeResponse, DevelopResponse])
@pytest.mark.parametrize("filename", ["", " ", "\t"])
def test_nonblank_string_is_shared_by_response_filenames(
    model_type: type[AnalyzeResponse | DevelopResponse],
    filename: str,
) -> None:
    with pytest.raises(ValidationError):
        model_type(
            schema_version="1.0",
            request_id=REQUEST_ID,
            filename=filename,
            status="success",
        )


@pytest.mark.parametrize(
    ("model_type", "expected_hash"),
    list(PUBLIC_SCHEMA_HASHES.items()),
)
def test_public_json_schemas_are_unchanged(
    model_type: type[
        AnalyzeRequest
        | DevelopRequest
        | AnalyzeResponse
        | DevelopResponse
        | ErrorResponse
    ],
    expected_hash: str,
) -> None:
    canonical_schema = json.dumps(
        model_type.model_json_schema(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    assert hashlib.sha256(canonical_schema).hexdigest() == expected_hash


def test_learning_diagnostics_validate_visible_summary_values() -> None:
    diagnostics = LearningDiagnostics(
        enabled=True,
        personalization_applied=True,
        usable_sample_count=18,
        retrieved_sample_count=5,
        minimum_sample_count=3,
        average_similarity=0.86,
        feature_type="local_color_luminance",
        reason=None,
    )

    assert diagnostics.minimum_sample_count == 3
    assert diagnostics.average_similarity == 0.86
    with pytest.raises(ValidationError):
        LearningDiagnostics(
            enabled=True,
            personalization_applied=False,
            usable_sample_count=2,
            retrieved_sample_count=0,
            minimum_sample_count=0,
            average_similarity=None,
            reason="insufficient_samples",
        )
    with pytest.raises(ValidationError):
        diagnostics.model_copy(
            update={"average_similarity": 1.01}
        ).model_validate(
            {
                **diagnostics.model_dump(),
                "average_similarity": 1.01,
            }
        )


@pytest.mark.parametrize("model_type", [AnalyzeRequest, DevelopRequest])
@pytest.mark.parametrize("schema_version", ["0.9", "1.1", 1.0])
def test_schema_version_other_than_literal_string_is_rejected(
    model_type: type[AnalyzeRequest | DevelopRequest],
    schema_version: object,
) -> None:
    payload = {
        **_minimal_request_data(),
        "schema_version": schema_version,
        "preview_path": "temp/preview.jpg",
    }

    with pytest.raises(ValidationError):
        model_type.model_validate(payload)


def test_request_id_serializes_consistently_as_json_string() -> None:
    request = DevelopRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        filename="DSC_0001.NEF",
        preview_path="temp/preview.jpg",
    )

    assert request.model_dump(mode="json")["request_id"] == str(REQUEST_ID)
    restored = DevelopRequest.model_validate_json(request.model_dump_json())
    assert restored.request_id == REQUEST_ID
