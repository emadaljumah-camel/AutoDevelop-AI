import math

import pytest

from autodevelop.models import (
    CropRecommendation,
    DenoiseRecommendation,
    DevelopSettings,
    HdrRecommendation,
    LevelingRecommendation,
    ProcessingOptions,
    TechnicalAnalysis,
)
from autodevelop.profiles import StyleProfile, StyleProfileLoader
from autodevelop.validation import (
    SafetyValidator,
    ValidationAction,
    ValidationResult,
)
from autodevelop.validation import policies


@pytest.fixture
def profile() -> StyleProfile:
    return StyleProfileLoader().get_profile("natural_travel")


@pytest.fixture
def validator() -> SafetyValidator:
    return SafetyValidator()


def _validate(
    validator: SafetyValidator,
    profile: StyleProfile,
    *,
    settings: DevelopSettings | None = None,
    crop: CropRecommendation | None = None,
    denoise: DenoiseRecommendation | None = None,
    enable_hdr: HdrRecommendation | None = None,
    leveling: LevelingRecommendation | None = None,
    analysis: TechnicalAnalysis | None = None,
    options: ProcessingOptions | None = None,
    iso: int | None = None,
) -> ValidationResult:
    return validator.validate(
        settings=settings,
        crop=crop,
        denoise=denoise,
        profile=profile,
        enable_hdr=enable_hdr,
        leveling=leveling,
        analysis=analysis,
        options=options,
        iso=iso,
    )


def _valid_crop(**changes: object) -> CropRecommendation:
    values: dict[str, object] = {
        "recommended": True,
        "left": 0.05,
        "right": 0.95,
        "top": 0.05,
        "bottom": 0.95,
        "confidence": 0.8,
        "reason": "Improve alignment.",
    }
    values.update(changes)
    return CropRecommendation.model_validate(values)


def test_none_settings_returns_empty_develop_settings(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    result = _validate(validator, profile)

    assert result.settings.model_dump(exclude_none=True) == {}
    assert result.issues == []


def test_empty_settings_pass_unchanged(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    result = _validate(validator, profile, settings=DevelopSettings())

    assert result.settings == DevelopSettings()
    assert result.issues == []


def test_in_range_slider_passes_unchanged(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    result = _validate(
        validator,
        profile,
        settings=DevelopSettings(Exposure2012=0.5),
    )

    assert result.settings.Exposure2012 == 0.5
    assert result.issues == []


def test_slider_below_minimum_is_clamped(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    result = _validate(
        validator,
        profile,
        settings=DevelopSettings(Exposure2012=-5.0),
    )

    assert result.settings.Exposure2012 == -1.0
    assert result.issues[0].code == policies.SLIDER_CLAMPED_LOW
    assert result.issues[0].action is ValidationAction.CLAMPED
    assert result.clamped_fields == ["Exposure2012"]


def test_slider_above_maximum_is_clamped(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    result = _validate(
        validator,
        profile,
        settings=DevelopSettings(Contrast2012=100.0),
    )

    assert result.settings.Contrast2012 == 32.0
    assert result.issues[0].code == policies.SLIDER_CLAMPED_HIGH
    assert result.clamped_fields == ["Contrast2012"]


def test_several_sliders_are_clamped_independently(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    result = _validate(
        validator,
        profile,
        settings=DevelopSettings(
            Exposure2012=4.0,
            Contrast2012=-50.0,
            Dehaze=40.0,
        ),
    )

    assert result.settings.Exposure2012 == 1.0
    assert result.settings.Contrast2012 == -15.0
    assert result.settings.Dehaze == 18.0
    assert result.clamped_fields == [
        "Exposure2012",
        "Contrast2012",
        "Dehaze",
    ]


def test_null_slider_remains_null_without_issue(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    result = _validate(
        validator,
        profile,
        settings=DevelopSettings(Exposure2012=None),
    )

    assert result.settings.Exposure2012 is None
    assert result.issues == []


def test_slider_not_allowed_by_profile_is_removed(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    result = _validate(
        validator,
        profile,
        settings=DevelopSettings(CropLeft=0.1),
    )

    assert result.settings.CropLeft is None
    assert result.issues[0].code == policies.SLIDER_NOT_ALLOWED
    assert result.removed_fields == ["CropLeft"]


def test_original_develop_settings_remain_unchanged(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    source = DevelopSettings(Exposure2012=5.0, CropLeft=0.1)
    before = source.model_dump()

    _validate(validator, profile, settings=source)

    assert source.model_dump() == before


def test_original_style_profile_remains_unchanged(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    before = profile.model_dump()

    _validate(
        validator,
        profile,
        settings=DevelopSettings(Exposure2012=5.0),
        crop=_valid_crop(),
        leveling=LevelingRecommendation(
            recommended=True,
            angle=20.0,
            mode="horizon",
        ),
        denoise=DenoiseRecommendation(
            recommended=True,
            amount=100.0,
            confidence=0.9,
        ),
    )

    assert profile.model_dump() == before


def test_issue_ordering_is_deterministic(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    settings = DevelopSettings(
        CropLeft=0.1,
        Dehaze=50.0,
        Contrast2012=-50.0,
        Exposure2012=5.0,
    )

    first = _validate(validator, profile, settings=settings)
    second = _validate(validator, profile, settings=settings)

    expected_fields = ["Exposure2012", "Contrast2012", "Dehaze", "CropLeft"]
    assert [issue.field for issue in first.issues] == expected_fields
    assert [issue.model_dump() for issue in first.issues] == [
        issue.model_dump() for issue in second.issues
    ]


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, True])
def test_invalid_slider_numeric_values_are_rejected_defensively(
    validator: SafetyValidator,
    profile: StyleProfile,
    value: object,
) -> None:
    source = DevelopSettings.model_construct(Exposure2012=value)

    result = _validate(validator, profile, settings=source)

    assert result.settings.Exposure2012 is None
    assert result.issues[0].code == policies.INVALID_NUMERIC_VALUE
    assert result.issues[0].action is ValidationAction.REJECTED
    assert result.rejected_fields == ["Exposure2012"]


def test_crop_none_passes_through(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    assert _validate(validator, profile).crop is None


def test_valid_recommended_crop_passes(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    crop = _valid_crop()

    result = _validate(validator, profile, crop=crop)

    assert result.crop == crop
    assert result.issues == []


def test_recommended_crop_with_missing_bound_is_rejected(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    crop = CropRecommendation.model_construct(
        recommended=True,
        left=0.05,
        right=0.95,
        top=0.05,
        bottom=None,
        confidence=0.8,
    )

    result = _validate(validator, profile, crop=crop)

    assert result.crop is None
    assert result.issues[0].code == policies.CROP_MISSING_BOUNDS
    assert result.rejected_fields == ["crop"]


def test_invalid_crop_ordering_is_rejected(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    crop = CropRecommendation.model_construct(
        recommended=True,
        left=0.8,
        right=0.2,
        top=0.05,
        bottom=0.95,
        confidence=0.8,
    )

    result = _validate(validator, profile, crop=crop)

    assert result.crop is None
    assert result.issues[0].code == policies.CROP_INVALID_BOUNDS


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("left", -0.1),
        ("right", 1.1),
        ("top", math.nan),
        ("bottom", math.inf),
    ],
)
def test_crop_outside_unit_interval_is_rejected_defensively(
    validator: SafetyValidator,
    profile: StyleProfile,
    field_name: str,
    value: float,
) -> None:
    values = {
        "recommended": True,
        "left": 0.05,
        "right": 0.95,
        "top": 0.05,
        "bottom": 0.95,
        "confidence": 0.8,
    }
    values[field_name] = value
    crop = CropRecommendation.model_construct(**values)

    result = _validate(validator, profile, crop=crop)

    assert result.crop is None
    assert result.issues[0].code == policies.CROP_INVALID_BOUNDS
    assert result.rejected_fields == ["crop"]


def test_crop_edge_exactly_at_limit_is_accepted(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    limit = profile.crop_policy.max_edge_crop
    crop = _valid_crop(left=limit, right=1.0, top=0.0, bottom=1.0)

    result = _validate(validator, profile, crop=crop)

    assert result.crop == crop
    assert result.issues == []


def test_crop_left_edge_above_limit_is_rejected(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    crop = _valid_crop(left=0.13, right=1.0, top=0.0, bottom=1.0)

    result = _validate(validator, profile, crop=crop)

    assert result.crop is None
    assert result.rejected_fields == ["crop"]
    assert result.issues[0].model_dump(mode="json") == {
        "code": policies.CROP_EDGE_LIMIT_EXCEEDED,
        "message": "Crop removes more from the left edge than the profile permits.",
        "field": "crop.left",
        "original_value": 0.13,
        "adjusted_value": profile.crop_policy.max_edge_crop,
        "action": "rejected",
        "severity": "warning",
    }


def test_crop_right_edge_above_limit_is_rejected(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    crop = _valid_crop(left=0.0, right=0.87, top=0.0, bottom=1.0)

    result = _validate(validator, profile, crop=crop)

    assert result.crop is None
    assert result.issues[0].code == policies.CROP_EDGE_LIMIT_EXCEEDED
    assert result.issues[0].field == "crop.right"
    assert result.issues[0].original_value == pytest.approx(0.13)


def test_crop_top_edge_above_limit_is_rejected(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    crop = _valid_crop(left=0.0, right=1.0, top=0.13, bottom=1.0)

    result = _validate(validator, profile, crop=crop)

    assert result.crop is None
    assert result.issues[0].code == policies.CROP_EDGE_LIMIT_EXCEEDED
    assert result.issues[0].field == "crop.top"
    assert result.issues[0].original_value == 0.13


def test_crop_bottom_edge_above_limit_is_rejected(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    crop = _valid_crop(left=0.0, right=1.0, top=0.0, bottom=0.87)

    result = _validate(validator, profile, crop=crop)

    assert result.crop is None
    assert result.issues[0].code == policies.CROP_EDGE_LIMIT_EXCEEDED
    assert result.issues[0].field == "crop.bottom"
    assert result.issues[0].original_value == pytest.approx(0.13)


def test_multiple_crop_edge_violations_have_deterministic_order(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    crop = _valid_crop(left=0.13, right=0.86, top=0.13, bottom=0.86)

    result = _validate(validator, profile, crop=crop)

    assert result.crop is None
    assert [issue.field for issue in result.issues] == [
        "crop.left",
        "crop.right",
        "crop.top",
        "crop.bottom",
    ]
    assert [issue.original_value for issue in result.issues] == pytest.approx(
        [0.13, 0.14, 0.13, 0.14]
    )
    assert all(
        issue.code == policies.CROP_EDGE_LIMIT_EXCEEDED
        and issue.action is ValidationAction.REJECTED
        and issue.severity == "warning"
        for issue in result.issues
    )


def test_crop_can_pass_retained_area_but_fail_edge_limit(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    crop = _valid_crop(left=0.13, right=1.0, top=0.0, bottom=1.0)
    retained_area = (crop.right - crop.left) * (crop.bottom - crop.top)

    result = _validate(validator, profile, crop=crop)

    assert retained_area >= profile.crop_policy.minimum_retained_area
    assert result.crop is None
    assert result.issues[0].code == policies.CROP_EDGE_LIMIT_EXCEEDED


def test_crop_can_pass_edge_limit_but_fail_retained_area(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    crop = _valid_crop(left=0.11, right=0.89, top=0.11, bottom=0.89)

    result = _validate(validator, profile, crop=crop)

    assert all(
        cropped_amount <= profile.crop_policy.max_edge_crop
        for cropped_amount in (
            crop.left,
            1.0 - crop.right,
            crop.top,
            1.0 - crop.bottom,
        )
    )
    assert result.crop is None
    assert result.issues[0].code == policies.CROP_AREA_TOO_SMALL


def test_multiple_crop_edge_violations_track_crop_once(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    crop = _valid_crop(left=0.13, right=0.86, top=0.13, bottom=0.86)

    result = _validate(validator, profile, crop=crop)

    assert len(result.issues) == 4
    assert result.rejected_fields == ["crop"]


def test_crop_edge_rejection_does_not_mutate_crop_or_profile(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    crop = _valid_crop(left=0.13, right=1.0, top=0.0, bottom=1.0)
    crop_before = crop.model_dump()
    profile_before = profile.model_dump()

    _validate(validator, profile, crop=crop)

    assert crop.model_dump() == crop_before
    assert profile.model_dump() == profile_before


def test_crop_below_retained_area_threshold_is_rejected(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    crop = _valid_crop(left=0.11, right=0.89, top=0.11, bottom=0.89)

    result = _validate(validator, profile, crop=crop)

    assert result.crop is None
    assert result.issues[0].code == policies.CROP_AREA_TOO_SMALL


def test_leveling_angle_inside_limit_passes(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    leveling = LevelingRecommendation(
        recommended=True,
        angle=4.0,
        mode="horizon",
    )
    result = _validate(validator, profile, leveling=leveling)

    assert result.leveling.angle == 4.0
    assert result.leveling.mode == "horizon"
    assert result.issues == []


def test_leveling_angle_outside_limit_is_clamped(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    leveling = LevelingRecommendation(
        recommended=True,
        angle=-12.0,
        mode="horizon",
    )
    result = _validate(validator, profile, leveling=leveling)

    assert result.leveling.angle == -5.0
    assert result.issues[0].code == policies.LEVELING_ANGLE_CLAMPED
    assert result.clamped_fields == ["leveling.angle"]


def test_crop_below_confidence_threshold_is_rejected(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    result = _validate(validator, profile, crop=_valid_crop(confidence=0.4))

    assert result.crop is None
    assert result.issues[0].code == policies.CROP_CONFIDENCE_TOO_LOW
    assert result.rejected_fields == ["crop"]
    assert result.is_safe is True


def test_nonrecommended_crop_removes_inactive_bounds(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    crop = CropRecommendation(
        recommended=False,
        left=0.05,
        right=0.95,
        top=0.05,
        bottom=0.95,
        confidence=0.8,
        reason="Not needed.",
    )

    result = _validate(validator, profile, crop=crop)

    assert result.crop is not None
    assert result.crop.recommended is False
    assert result.crop.left is None
    assert result.crop.confidence == 0.8
    assert [issue.action for issue in result.issues] == [
        ValidationAction.REMOVED
    ] * 4


def test_original_crop_recommendation_remains_unchanged(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    crop = _valid_crop()
    before = crop.model_dump()

    _validate(validator, profile, crop=crop)

    assert crop.model_dump() == before


def test_denoise_none_passes_through(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    assert _validate(validator, profile).denoise is None


def test_exact_preset_denoise_amount_passes(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    denoise = DenoiseRecommendation(
        recommended=True,
        amount=25.0,
        confidence=0.8,
        reason="Visible noise.",
    )

    result = _validate(validator, profile, denoise=denoise)

    assert result.denoise == denoise
    assert result.issues == []


def test_denoise_below_profile_iso_is_rejected(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    denoise = DenoiseRecommendation(
        recommended=True,
        amount=25.0,
        confidence=0.8,
    )

    result = _validate(
        validator,
        profile,
        denoise=denoise,
        iso=profile.denoise_policy.minimum_iso - 1,
    )

    assert result.denoise is not None
    assert result.denoise.recommended is False
    assert result.denoise.amount is None
    assert result.issues[0].code == policies.DENOISE_ISO_TOO_LOW
    assert result.rejected_fields == ["denoise"]


def test_denoise_amount_below_minimum_is_clamped(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    denoise = DenoiseRecommendation(
        recommended=True,
        amount=-5.0,
        confidence=0.8,
    )

    result = _validate(validator, profile, denoise=denoise)

    assert result.denoise is not None
    assert result.denoise.amount == 25.0
    assert [issue.code for issue in result.issues] == [
        policies.DENOISE_AMOUNT_CLAMPED_LOW,
        policies.DENOISE_AMOUNT_QUANTIZED,
    ]


def test_denoise_amount_above_maximum_is_clamped(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    denoise = DenoiseRecommendation(
        recommended=True,
        amount=100.0,
        confidence=0.8,
    )

    result = _validate(validator, profile, denoise=denoise)

    assert result.denoise is not None
    assert result.denoise.amount == 25.0
    assert [issue.code for issue in result.issues] == [
        policies.DENOISE_AMOUNT_CLAMPED_HIGH,
        policies.DENOISE_AMOUNT_QUANTIZED,
    ]


def test_recommended_denoise_without_amount_warns_without_inventing_value(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    denoise = DenoiseRecommendation(
        recommended=True,
        amount=None,
        confidence=0.8,
    )

    result = _validate(validator, profile, denoise=denoise)

    assert result.denoise is not None
    assert result.denoise.recommended is True
    assert result.denoise.amount is None
    assert result.issues[0].code == policies.DENOISE_AMOUNT_MISSING
    assert result.issues[0].severity == "warning"


def test_low_confidence_denoise_becomes_not_recommended(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    denoise = DenoiseRecommendation(
        recommended=True,
        amount=20.0,
        confidence=0.3,
        reason="Uncertain noise.",
    )

    result = _validate(validator, profile, denoise=denoise)

    assert result.denoise is not None
    assert result.denoise.recommended is False
    assert result.denoise.amount is None
    assert result.denoise.confidence == 0.3
    assert result.denoise.reason == "Uncertain noise."
    assert result.issues[0].code == policies.DENOISE_CONFIDENCE_TOO_LOW
    assert result.rejected_fields == ["denoise"]


def test_nonrecommended_denoise_removes_amount(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    denoise = DenoiseRecommendation(
        recommended=False,
        amount=15.0,
        confidence=0.8,
        reason="Not needed.",
    )

    result = _validate(validator, profile, denoise=denoise)

    assert result.denoise is not None
    assert result.denoise.recommended is False
    assert result.denoise.amount is None
    assert result.denoise.confidence == 0.8
    assert result.issues[0].code == (
        policies.DENOISE_AMOUNT_REMOVED_WHEN_NOT_RECOMMENDED
    )


def test_original_denoise_recommendation_remains_unchanged(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    denoise = DenoiseRecommendation(
        recommended=True,
        amount=100.0,
        confidence=0.3,
    )
    before = denoise.model_dump()

    _validate(validator, profile, denoise=denoise)

    assert denoise.model_dump() == before


def test_rejected_fields_contains_no_duplicates(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    crop = CropRecommendation.model_construct(
        recommended=True,
        left=-1.0,
        right=2.0,
        top=math.nan,
        bottom=math.inf,
        confidence=0.8,
    )

    result = _validate(validator, profile, crop=crop)

    assert result.rejected_fields == ["crop"]


def test_clamped_fields_contains_no_duplicates(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    result = _validate(
        validator,
        profile,
        settings=DevelopSettings(
            Exposure2012=5.0,
            Contrast2012=100.0,
        ),
        crop=_valid_crop(),
        leveling=LevelingRecommendation(
            recommended=True,
            angle=20.0,
            mode="horizon",
        ),
        denoise=DenoiseRecommendation(
            recommended=True,
            amount=100.0,
            confidence=0.8,
        ),
    )

    assert len(result.clamped_fields) == len(set(result.clamped_fields))


def test_removed_fields_contains_no_duplicates(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    crop = CropRecommendation(
        recommended=False,
        left=0.05,
        right=0.95,
        top=0.05,
        bottom=0.95,
    )
    denoise = DenoiseRecommendation(
        recommended=False,
        amount=10.0,
    )

    result = _validate(validator, profile, crop=crop, denoise=denoise)

    assert len(result.removed_fields) == len(set(result.removed_fields))


@pytest.mark.parametrize(
    ("scene_type", "lighting", "exposure"),
    [
        ("landscape", "sunset", "Bright sky over dark foreground"),
        ("interior", "mixed", "Bright windows and recoverable interior shadows"),
        ("night city", "artificial", "Luminous signs and deep recoverable shadows"),
    ],
)
def test_genuine_high_dynamic_range_scene_can_recommend_hdr(
    validator: SafetyValidator,
    profile: StyleProfile,
    scene_type: str,
    lighting: str,
    exposure: str,
) -> None:
    result = _validate(
        validator,
        profile,
        enable_hdr=HdrRecommendation(
            recommended=True,
            enabled=True,
            confidence=0.9,
        ),
        analysis=TechnicalAnalysis(
            scene_type=scene_type,
            lighting=lighting,
            exposure_assessment=exposure,
            dynamic_range="high",
            noise_level="low",
            highlight_recoverability="high",
            shadow_recoverability="moderate",
        ),
        options=ProcessingOptions(
            hdr_edit_supported=True,
            hdr_workflow="hdr",
        ),
    )

    assert result.enable_hdr.recommended is True
    assert result.enable_hdr.reason is None


def test_subject_category_does_not_override_hdr_technical_safety(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    result = _validate(
        validator,
        profile,
        enable_hdr=HdrRecommendation(
            recommended=True,
            enabled=True,
            confidence=0.9,
        ),
        analysis=TechnicalAnalysis(
            scene_type="portrait",
            main_subject="ordinary portrait",
            lighting="soft daylight",
            dynamic_range="high",
            noise_level="low",
            highlight_recoverability="moderate",
        ),
        options=ProcessingOptions(
            hdr_edit_supported=True,
            hdr_workflow="hdr",
        ),
    )

    assert result.enable_hdr.recommended is True
    assert result.rejected_fields == []


def test_landscape_style_alone_does_not_force_hdr(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    result = _validate(
        validator,
        profile,
        enable_hdr=HdrRecommendation(
            recommended=True,
            enabled=True,
            confidence=0.9,
        ),
        analysis=TechnicalAnalysis(
            scene_type="landscape",
            lighting="daylight",
            dynamic_range="low",
            highlight_recoverability="moderate",
        ),
        options=ProcessingOptions(
            hdr_edit_supported=True,
            hdr_workflow="hdr",
        ),
    )

    assert result.enable_hdr.recommended is False


def test_noisy_high_range_scene_does_not_recommend_hdr(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    result = _validate(
        validator,
        profile,
        enable_hdr=HdrRecommendation(
            recommended=True,
            enabled=True,
            confidence=0.9,
        ),
        analysis=TechnicalAnalysis(
            scene_type="night city",
            lighting="artificial",
            dynamic_range="high",
            noise_level="high",
            highlight_recoverability="high",
            shadow_recoverability="moderate",
        ),
        options=ProcessingOptions(
            hdr_edit_supported=True,
            hdr_workflow="hdr",
        ),
    )

    assert result.enable_hdr.recommended is False


@pytest.mark.parametrize(
    "options",
    [
        ProcessingOptions(hdr_edit_supported=False, hdr_workflow="hdr"),
        ProcessingOptions(hdr_edit_supported=True, hdr_workflow="sdr_only"),
    ],
)
def test_provider_cannot_bypass_hdr_capability_or_workflow_gate(
    validator: SafetyValidator,
    profile: StyleProfile,
    options: ProcessingOptions,
) -> None:
    result = _validate(
        validator,
        profile,
        enable_hdr=HdrRecommendation(
            recommended=True,
            enabled=True,
            confidence=0.9,
        ),
        analysis=TechnicalAnalysis(
            scene_type="landscape",
            lighting="sunset",
            dynamic_range="high",
            noise_level="low",
            highlight_recoverability="high",
            shadow_recoverability="high",
        ),
        options=options,
    )

    assert result.enable_hdr.recommended is False


def test_validation_result_serialization_round_trip(
    validator: SafetyValidator,
    profile: StyleProfile,
) -> None:
    result = _validate(
        validator,
        profile,
        settings=DevelopSettings(Exposure2012=5.0, CropLeft=0.1),
        crop=_valid_crop(),
        leveling=LevelingRecommendation(
            recommended=True,
            angle=20.0,
            mode="horizon",
        ),
        denoise=DenoiseRecommendation(
            recommended=True,
            amount=100.0,
            confidence=0.8,
        ),
    )

    restored = ValidationResult.model_validate_json(result.model_dump_json())

    assert restored == result
