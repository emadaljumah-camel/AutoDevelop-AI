"""Stable issue-code constants used by safety validation."""

from typing import Final

SLIDER_CLAMPED_LOW: Final = "slider_clamped_low"
SLIDER_CLAMPED_HIGH: Final = "slider_clamped_high"
SLIDER_NOT_ALLOWED: Final = "slider_not_allowed"
INVALID_NUMERIC_VALUE: Final = "invalid_numeric_value"
HDR_RECOMMENDATION_REJECTED: Final = "hdr_recommendation_rejected"
HDR_NOT_ALLOWED: Final = "hdr_not_allowed"
HDR_CONFIDENCE_TOO_LOW: Final = "hdr_confidence_too_low"
HDR_INACTIVE_NORMALIZED: Final = "hdr_inactive_normalized"

UPRIGHT_NOT_ALLOWED: Final = "upright_not_allowed"
UPRIGHT_MODE_NOT_ALLOWED: Final = "upright_mode_not_allowed"
UPRIGHT_CONFIDENCE_TOO_LOW: Final = "upright_confidence_too_low"
UPRIGHT_INVALID_STATE: Final = "upright_invalid_state"

CROP_NOT_ALLOWED: Final = "crop_not_allowed"
CROP_MISSING_BOUNDS: Final = "crop_missing_bounds"
CROP_INVALID_BOUNDS: Final = "crop_invalid_bounds"
CROP_EDGE_LIMIT_EXCEEDED: Final = "crop_edge_limit_exceeded"
CROP_AREA_TOO_SMALL: Final = "crop_area_too_small"
CROP_CONFIDENCE_REQUIRED: Final = "crop_confidence_required"
CROP_CONFIDENCE_TOO_LOW: Final = "crop_confidence_too_low"
CROP_VALUES_REMOVED_WHEN_NOT_RECOMMENDED: Final = (
    "crop_values_removed_when_not_recommended"
)

LEVELING_NOT_ALLOWED: Final = "leveling_not_allowed"
LEVELING_ANGLE_CLAMPED: Final = "leveling_angle_clamped"
LEVELING_INVALID_STATE: Final = "leveling_invalid_state"

DENOISE_NOT_ALLOWED: Final = "denoise_not_allowed"
DENOISE_AMOUNT_CLAMPED_LOW: Final = "denoise_amount_clamped_low"
DENOISE_AMOUNT_CLAMPED_HIGH: Final = "denoise_amount_clamped_high"
DENOISE_AMOUNT_MISSING: Final = "denoise_amount_missing"
DENOISE_CONFIDENCE_TOO_LOW: Final = "denoise_confidence_too_low"
DENOISE_ISO_TOO_LOW: Final = "denoise_iso_too_low"
DENOISE_AMOUNT_QUANTIZED: Final = "denoise_amount_quantized"
DENOISE_AMOUNT_REMOVED_WHEN_NOT_RECOMMENDED: Final = (
    "denoise_amount_removed_when_not_recommended"
)
