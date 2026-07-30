import asyncio
import builtins
import socket
from uuid import UUID

import pytest

from autodevelop.model_clients import (
    FakeModelClient,
    ModelClient,
    ModelResponseError,
)
from autodevelop.models import (
    AnalyzeRequest,
    DevelopRequest,
    ProcessingWarning,
)
from autodevelop.profiles import StyleProfile, StyleProfileLoader
from autodevelop.validation import SafetyValidator

REQUEST_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


@pytest.fixture
def profile() -> StyleProfile:
    return StyleProfileLoader().get_profile("natural_travel")


def _analyze_request(
    *,
    filename: str = "photo.nef",
    iso: int | None = None,
    style_profile: str = "natural_travel",
    include_crop: bool = True,
    include_denoise: bool = True,
) -> AnalyzeRequest:
    return AnalyzeRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        filename=filename,
        preview_path="does-not-need-to-exist.jpg",
        exif={"iso": iso} if iso is not None else {},
        options={
            "style_profile": style_profile,
            "include_crop": include_crop,
            "include_denoise": include_denoise,
        },
    )


def _develop_request(
    *,
    filename: str = "photo.nef",
    iso: int | None = None,
    include_crop: bool = True,
    include_denoise: bool = True,
) -> DevelopRequest:
    return DevelopRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        filename=filename,
        preview_path="does-not-need-to-exist.jpg",
        exif={"iso": iso} if iso is not None else {},
        options={
            "include_crop": include_crop,
            "include_denoise": include_denoise,
        },
    )


def test_fake_client_implements_model_client_interface() -> None:
    assert isinstance(FakeModelClient(), ModelClient)


def test_default_constructor_values() -> None:
    client = FakeModelClient()

    assert client.model_name is None
    assert client.scenario == "auto"


def test_unknown_scenario_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown fake model scenario 'unknown'"):
        FakeModelClient(scenario="unknown")


def test_analyze_preserves_metadata_and_fixed_response_values() -> None:
    request = _analyze_request(filename="Original File.NEF")

    response = asyncio.run(
        FakeModelClient(model_name="custom-fake").analyze(request)
    )

    assert response.request_id == request.request_id
    assert response.filename == request.filename
    assert response.schema_version == "1.0"
    assert response.model == "gemma"
    assert response.resolved_model == "custom-fake"
    assert response.processing_duration_ms == 1


def test_fake_client_records_stable_model_style_filename_and_count() -> None:
    request = _analyze_request(filename="Recorded.NEF").model_copy(
        update={"model": "qwen"}
    )
    client = FakeModelClient(model_name="configured-qwen")

    asyncio.run(client.analyze(request))

    assert client.invocation_count == 1
    assert client.invocations == [
        {
            "model": "qwen",
            "resolved_model": "configured-qwen",
            "style_profile": "natural_travel",
            "filename": "Recorded.NEF",
        }
    ]


def test_develop_preserves_metadata_and_fixed_response_values(
    profile: StyleProfile,
) -> None:
    request = _develop_request(filename="Original File.NEF")

    response = asyncio.run(
        FakeModelClient(model_name="custom-fake").develop(request, profile)
    )

    assert response.request_id == request.request_id
    assert response.filename == request.filename
    assert response.schema_version == "1.0"
    assert response.model == "gemma"
    assert response.resolved_model == "custom-fake"
    assert response.processing_duration_ms == 1


def test_identical_calls_return_equal_model_dumps(
    profile: StyleProfile,
) -> None:
    client = FakeModelClient(scenario="landscape")
    request = _develop_request()

    first = asyncio.run(client.develop(request, profile))
    second = asyncio.run(client.develop(request, profile))

    assert first.model_dump() == second.model_dump()


def test_input_request_is_not_mutated(profile: StyleProfile) -> None:
    request = _develop_request(iso=6400)
    before = request.model_dump()

    asyncio.run(FakeModelClient().develop(request, profile))

    assert request.model_dump() == before


def test_profile_is_not_mutated(profile: StyleProfile) -> None:
    before = profile.model_dump()

    asyncio.run(FakeModelClient(scenario="landscape").develop(
        _develop_request(),
        profile,
    ))

    assert profile.model_dump() == before


@pytest.mark.parametrize(
    ("keyword", "expected_scene", "expected_exposure"),
    [
        ("NiGhT", "night", "highlights require protection"),
        ("PoRtRaIt", "portrait", "balanced"),
        ("LaNdScApE", "landscape", "balanced"),
        ("ArChItEcTuRe", "architecture", "bright highlights require control"),
        ("UnDeReXpOsEd", "general", "underexposed"),
        ("OvErExPoSeD", "general", "overexposed"),
    ],
)
def test_auto_filename_selection_is_case_insensitive(
    keyword: str,
    expected_scene: str,
    expected_exposure: str,
) -> None:
    response = asyncio.run(
        FakeModelClient().analyze(
            _analyze_request(filename=f"Trip_{keyword}_001.NEF")
        )
    )

    assert response.analysis is not None
    assert response.analysis.scene_type == expected_scene
    assert response.analysis.exposure_assessment == expected_exposure


def test_auto_high_iso_selection() -> None:
    response = asyncio.run(
        FakeModelClient().analyze(_analyze_request(iso=3200))
    )

    assert response.analysis is not None
    assert response.analysis.noise_level == "high"


def test_auto_falls_back_to_neutral() -> None:
    response = asyncio.run(FakeModelClient().analyze(_analyze_request(iso=400)))

    assert response.analysis is not None
    assert response.analysis.scene_type == "general"
    assert response.analysis.exposure_assessment == "balanced"
    assert response.analysis.confidence == 0.95


@pytest.mark.parametrize(
    ("scenario", "field_name", "expected"),
    [
        ("neutral", "exposure_assessment", "balanced"),
        ("underexposed", "exposure_assessment", "underexposed"),
        ("overexposed", "exposure_assessment", "overexposed"),
        ("high_iso", "noise_level", "high"),
        ("night", "scene_type", "night"),
        ("landscape", "main_subject", "landscape"),
        ("portrait", "visible_people", 1),
        (
            "architecture",
            "horizon_status",
            "minor correction may be useful",
        ),
    ],
)
def test_scenario_analyze_output(
    scenario: str,
    field_name: str,
    expected: object,
) -> None:
    response = asyncio.run(
        FakeModelClient(scenario=scenario).analyze(_analyze_request())
    )

    assert response.status == "success"
    assert response.analysis is not None
    assert getattr(response.analysis, field_name) == expected
    assert response.edit_plan is not None
    assert response.edit_plan.goals
    assert response.edit_plan.cautions
    assert response.warnings == []


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        (
            "neutral",
            (0.0, 0.0, -5.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 3.0, 0.0),
        ),
        (
            "underexposed",
            (0.65, 5.0, -15.0, 35.0, 8.0, -8.0, 5.0, 3.0, 2.0, 8.0, 0.0),
        ),
        (
            "overexposed",
            (-0.45, 3.0, -45.0, 10.0, -15.0, -3.0, 3.0, 2.0, 2.0, 5.0, 0.0),
        ),
        (
            "high_iso",
            (0.15, 0.0, -20.0, 20.0, 0.0, -5.0, -5.0, -3.0, 0.0, 3.0, 0.0),
        ),
        (
            "night",
            (0.25, 8.0, -35.0, 22.0, -8.0, -12.0, 0.0, 2.0, 4.0, 7.0, 0.0),
        ),
        (
            "landscape",
            (0.10, 12.0, -30.0, 20.0, 8.0, -10.0, 12.0, 8.0, 7.0, 14.0, 2.0),
        ),
        (
            "portrait",
            (0.15, -2.0, -18.0, 18.0, 2.0, -3.0, -8.0, -6.0, 0.0, 5.0, -2.0),
        ),
        (
            "architecture",
            (0.05, 10.0, -35.0, 18.0, 5.0, -8.0, 15.0, 10.0, 5.0, 5.0, -1.0),
        ),
    ],
)
def test_scenario_develop_settings(
    scenario: str,
    expected: tuple[float, ...],
    profile: StyleProfile,
) -> None:
    response = asyncio.run(
        FakeModelClient(scenario=scenario).develop(
            _develop_request(),
            profile,
        )
    )

    assert response.develop_settings is not None
    settings = response.develop_settings
    assert (
        settings.Exposure2012,
        settings.Contrast2012,
        settings.Highlights2012,
        settings.Shadows2012,
        settings.Whites2012,
        settings.Blacks2012,
        settings.Texture,
        settings.Clarity2012,
        settings.Dehaze,
        settings.Vibrance,
        settings.Saturation,
    ) == expected
    assert settings.Temperature is None
    assert settings.Tint is None


def test_current_settings_are_not_merged_into_recommendations(
    profile: StyleProfile,
) -> None:
    request = _develop_request()
    request.current_settings.Exposure2012 = 2.5
    request.current_settings.Temperature = 6000.0

    response = asyncio.run(
        FakeModelClient(scenario="neutral").develop(request, profile)
    )

    assert response.develop_settings is not None
    assert response.develop_settings.Exposure2012 == 0.0
    assert response.develop_settings.Temperature is None


def test_include_crop_false_returns_none() -> None:
    response = asyncio.run(
        FakeModelClient(scenario="landscape").analyze(
            _analyze_request(include_crop=False)
        )
    )

    assert response.crop is None


def test_landscape_returns_valid_conservative_crop() -> None:
    response = asyncio.run(
        FakeModelClient(scenario="landscape").analyze(_analyze_request())
    )

    assert response.crop is not None
    assert response.crop.model_dump() == {
        "recommended": True,
        "left": 0.02,
        "right": 0.98,
        "top": 0.03,
        "bottom": 0.97,
        "confidence": 0.88,
        "reason": "Remove narrow edge distractions.",
    }


def test_architecture_returns_independent_crop_and_leveling() -> None:
    response = asyncio.run(
        FakeModelClient(scenario="architecture").analyze(_analyze_request())
    )

    assert response.crop is not None
    assert response.crop.recommended is True
    assert response.crop.left == 0.02
    assert response.crop.right == 0.98
    assert response.leveling.recommended is True
    assert response.leveling.angle == 0.4
    assert response.leveling.mode == "vertical"


@pytest.mark.parametrize(
    "scenario",
    ["neutral", "underexposed", "overexposed", "high_iso", "night", "portrait"],
)
def test_non_crop_scenarios_return_not_recommended(scenario: str) -> None:
    response = asyncio.run(
        FakeModelClient(scenario=scenario).analyze(_analyze_request())
    )

    assert response.crop is not None
    assert response.crop.recommended is False


def test_include_denoise_false_returns_none() -> None:
    response = asyncio.run(
        FakeModelClient(scenario="high_iso").analyze(
            _analyze_request(include_denoise=False)
        )
    )

    assert response.denoise is None


@pytest.mark.parametrize(
    ("scenario", "amount", "confidence"),
    [
        ("high_iso", 45.0, 0.95),
        ("night", 35.0, 0.90),
    ],
)
def test_noise_scenarios_recommend_denoise(
    scenario: str,
    amount: float,
    confidence: float,
) -> None:
    response = asyncio.run(
        FakeModelClient(scenario=scenario).analyze(_analyze_request())
    )

    assert response.denoise is not None
    assert response.denoise.recommended is True
    assert response.denoise.amount == amount
    assert response.denoise.confidence == confidence


@pytest.mark.parametrize(
    ("iso", "recommended", "amount"),
    [
        (1599, False, None),
        (1600, True, 20.0),
    ],
)
def test_portrait_denoise_uses_iso_threshold(
    iso: int,
    recommended: bool,
    amount: float | None,
) -> None:
    response = asyncio.run(
        FakeModelClient(scenario="portrait").analyze(
            _analyze_request(iso=iso)
        )
    )

    assert response.denoise is not None
    assert response.denoise.recommended is recommended
    assert response.denoise.amount == amount


@pytest.mark.parametrize(
    "scenario",
    ["neutral", "underexposed", "overexposed", "landscape", "architecture"],
)
def test_non_denoise_scenarios_have_no_amount(scenario: str) -> None:
    response = asyncio.run(
        FakeModelClient(scenario=scenario).analyze(_analyze_request())
    )

    assert response.denoise is not None
    assert response.denoise.recommended is False
    assert response.denoise.amount is None


def test_analyze_edit_plan_uses_registered_manual_profile_id() -> None:
    response = asyncio.run(
        FakeModelClient().analyze(
            _analyze_request(style_profile="architecture")
        )
    )

    assert response.edit_plan is not None
    assert response.edit_plan.style_profile == "architecture"


def test_analyze_rejects_unsupported_profile_id() -> None:
    with pytest.raises(ValueError, match="Unsupported style profile"):
        asyncio.run(
            FakeModelClient().analyze(
                _analyze_request(style_profile="request_profile")
            )
        )


def test_develop_edit_plan_uses_supplied_profile_id(
    profile: StyleProfile,
) -> None:
    response = asyncio.run(
        FakeModelClient().develop(_develop_request(), profile)
    )

    assert response.edit_plan is not None
    assert response.edit_plan.style_profile == profile.id


def test_response_lists_are_not_shared() -> None:
    client = FakeModelClient(scenario="landscape")
    request = _analyze_request()
    first = asyncio.run(client.analyze(request))
    second = asyncio.run(client.analyze(request))

    assert first.edit_plan is not None
    assert second.edit_plan is not None
    first.warnings.append(
        ProcessingWarning(
            code="test",
            message="Test warning.",
            severity="info",
        )
    )
    first.edit_plan.goals.append("Changed goal")
    first.edit_plan.cautions.append("Changed caution")

    assert second.warnings == []
    assert "Changed goal" not in second.edit_plan.goals
    assert "Changed caution" not in second.edit_plan.cautions


def test_invalid_output_raises_model_response_error() -> None:
    client = FakeModelClient(
        model_name="broken-fake",
        scenario="invalid_output",
    )

    with pytest.raises(ModelResponseError) as captured:
        asyncio.run(client.analyze(_analyze_request()))

    assert captured.value.code == "invalid_fake_output"
    assert captured.value.model_name == "broken-fake"
    assert "broken-fake" in str(captured.value)


def test_fake_client_performs_no_filesystem_or_network_calls(
    monkeypatch: pytest.MonkeyPatch,
    profile: StyleProfile,
) -> None:
    request = _develop_request(filename="landscape.nef", iso=6400)

    def fail(*_: object, **__: object) -> None:
        raise AssertionError("unexpected external access")

    monkeypatch.setattr(builtins, "open", fail)
    monkeypatch.setattr(socket, "create_connection", fail)

    response = asyncio.run(FakeModelClient().develop(request, profile))

    assert response.status == "success"


def test_develop_response_passes_through_safety_validator(
    profile: StyleProfile,
) -> None:
    response = asyncio.run(
        FakeModelClient(scenario="landscape").develop(
            _develop_request(),
            profile,
        )
    )

    result = SafetyValidator().validate(
        settings=response.develop_settings,
        crop=response.crop,
        denoise=response.denoise,
        profile=profile,
    )

    assert result.is_safe is True
    assert result.crop is not None
    assert result.crop.recommended is True
