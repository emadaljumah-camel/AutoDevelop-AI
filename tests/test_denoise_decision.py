from autodevelop.denoise_decision import decide_denoise
from autodevelop.models import (
    DenoiseRecommendation,
    ProcessingOptions,
    TechnicalAnalysis,
)


def _options(*, enabled: bool = True) -> ProcessingOptions:
    return ProcessingOptions(include_denoise=enabled)


def test_iso_3600_proactively_recommends_amount_50() -> None:
    result = decide_denoise(
        DenoiseRecommendation(
            recommended=False,
            confidence=0.2,
            reason="Model did not recommend Denoise.",
        ),
        iso=3600,
        file_format="RAW",
        analysis=TechnicalAnalysis(noise_level="moderate"),
        options=_options(),
    )

    assert result is not None
    assert result.recommended is True
    assert result.amount == 50.0
    assert result.confidence == 0.90
    assert "ISO 3600" in (result.reason or "")


def test_iso_6400_recommends_amount_75() -> None:
    result = decide_denoise(
        None,
        iso=6400,
        file_format="DNG",
        analysis=None,
        options=_options(),
    )

    assert result is not None
    assert result.amount == 75.0
    assert result.confidence == 0.95


def test_iso_1600_requires_high_noise_evidence() -> None:
    low = decide_denoise(
        None,
        iso=1600,
        file_format="RAW",
        analysis=TechnicalAnalysis(noise_level="low"),
        options=_options(),
    )
    high = decide_denoise(
        None,
        iso=1600,
        file_format="RAW",
        analysis=TechnicalAnalysis(noise_level="high"),
        options=_options(),
    )

    assert low is None
    assert high is not None
    assert high.recommended is True
    assert high.amount == 25.0


def test_explicit_unsupported_format_disables_denoise() -> None:
    result = decide_denoise(
        DenoiseRecommendation(
            recommended=True,
            amount=50,
            confidence=0.9,
        ),
        iso=6400,
        file_format="JPEG",
        analysis=TechnicalAnalysis(noise_level="high"),
        options=_options(),
    )

    assert result is not None
    assert result.recommended is False
    assert result.amount is None
    assert "JPEG" in (result.reason or "")


def test_caller_can_disable_denoise() -> None:
    result = decide_denoise(
        DenoiseRecommendation(
            recommended=True,
            amount=50,
            confidence=0.9,
        ),
        iso=6400,
        file_format="RAW",
        analysis=TechnicalAnalysis(noise_level="high"),
        options=_options(enabled=False),
    )

    assert result is not None
    assert result.recommended is False
    assert result.amount is None
