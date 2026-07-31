"""Deterministic evidence-based Lightroom AI Denoise decisions."""

from autodevelop.models import (
    DenoiseRecommendation,
    ProcessingOptions,
    TechnicalAnalysis,
)

PRESET_AMOUNTS: tuple[float, ...] = (25.0, 50.0, 75.0)
_SUPPORTED_FORMATS = frozenset({"RAW", "DNG"})
_HIGH_NOISE = frozenset({"high", "severe", "extreme"})


def _disabled(reason: str) -> DenoiseRecommendation:
    return DenoiseRecommendation(
        recommended=False,
        amount=None,
        confidence=1.0,
        reason=reason,
    )


def decide_denoise(
    recommendation: DenoiseRecommendation | None,
    *,
    iso: int | None,
    file_format: str | None,
    analysis: TechnicalAnalysis | None,
    options: ProcessingOptions | None,
) -> DenoiseRecommendation | None:
    """Combine reliable ISO evidence with the model recommendation."""

    if options is not None and not options.include_denoise:
        return _disabled("Denoise was disabled by the caller.")

    normalized_format = (file_format or "").strip().upper()
    if normalized_format and normalized_format not in _SUPPORTED_FORMATS:
        return _disabled(
            f"Lightroom AI Denoise is not enabled for {normalized_format} files."
        )

    noise_level = (
        (analysis.noise_level or "").strip().lower()
        if analysis is not None
        else ""
    )
    target: float | None = None
    confidence: float | None = None
    reason: str | None = None
    if iso is not None and iso >= 6400:
        target = 75.0
        confidence = 0.95
        reason = f"ISO {iso} indicates very strong high-ISO noise risk."
    elif iso is not None and iso >= 3200:
        target = 50.0
        confidence = 0.90
        reason = f"ISO {iso} indicates strong high-ISO noise risk."
    elif iso is not None and iso >= 1600 and noise_level in _HIGH_NOISE:
        target = 25.0
        confidence = 0.80
        reason = (
            f"ISO {iso} and {noise_level} scene-noise evidence support Denoise."
        )

    if target is None:
        return recommendation.model_copy(deep=True) if recommendation else None

    model_confidence = (
        recommendation.confidence
        if recommendation is not None and recommendation.confidence is not None
        else 0.0
    )
    return DenoiseRecommendation(
        recommended=True,
        amount=target,
        confidence=max(confidence or 0.0, model_confidence),
        reason=reason,
    )
