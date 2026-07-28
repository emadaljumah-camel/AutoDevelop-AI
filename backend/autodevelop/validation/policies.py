"""Stable issue-code constants used by safety validation."""

from typing import Final

SLIDER_CLAMPED_LOW: Final = "slider_clamped_low"
SLIDER_CLAMPED_HIGH: Final = "slider_clamped_high"
SLIDER_NOT_ALLOWED: Final = "slider_not_allowed"
INVALID_NUMERIC_VALUE: Final = "invalid_numeric_value"

CROP_NOT_ALLOWED: Final = "crop_not_allowed"
CROP_MISSING_BOUNDS: Final = "crop_missing_bounds"
CROP_INVALID_BOUNDS: Final = "crop_invalid_bounds"
CROP_EDGE_LIMIT_EXCEEDED: Final = "crop_edge_limit_exceeded"
CROP_AREA_TOO_SMALL: Final = "crop_area_too_small"
CROP_ANGLE_CLAMPED: Final = "crop_angle_clamped"
CROP_ANGLE_NOT_ALLOWED: Final = "crop_angle_not_allowed"
CROP_CONFIDENCE_REQUIRED: Final = "crop_confidence_required"
CROP_CONFIDENCE_TOO_LOW: Final = "crop_confidence_too_low"
CROP_VALUES_REMOVED_WHEN_NOT_RECOMMENDED: Final = (
    "crop_values_removed_when_not_recommended"
)

DENOISE_NOT_ALLOWED: Final = "denoise_not_allowed"
DENOISE_AMOUNT_CLAMPED_LOW: Final = "denoise_amount_clamped_low"
DENOISE_AMOUNT_CLAMPED_HIGH: Final = "denoise_amount_clamped_high"
DENOISE_AMOUNT_MISSING: Final = "denoise_amount_missing"
DENOISE_CONFIDENCE_TOO_LOW: Final = "denoise_confidence_too_low"
DENOISE_AMOUNT_REMOVED_WHEN_NOT_RECOMMENDED: Final = (
    "denoise_amount_removed_when_not_recommended"
)
