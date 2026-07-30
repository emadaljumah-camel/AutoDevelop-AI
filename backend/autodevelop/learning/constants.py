"""Stable learning thresholds, limits, and setting categories."""

from typing import Final

SCHEMA_VERSION: Final = 2
MAX_PAYLOAD_BYTES: Final = 64 * 1024
MAX_FEATURE_DIMENSIONS: Final = 512
MAX_CONTEXT_CHARACTERS: Final = 2_000

SUPPORTED_SETTINGS: Final = (
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
)
COMPOSITION_CROP_SETTINGS: Final = frozenset(
    {"CropLeft", "CropRight", "CropTop", "CropBottom"}
)
LEVELING_SETTINGS: Final = frozenset({"CropAngle"})

SIGNIFICANCE_THRESHOLDS: Final = {
    "Exposure2012": 0.05,
    "Contrast2012": 2.0,
    "Highlights2012": 2.0,
    "Shadows2012": 2.0,
    "Whites2012": 2.0,
    "Blacks2012": 2.0,
    "Texture": 2.0,
    "Clarity2012": 2.0,
    "Dehaze": 1.0,
    "Vibrance": 2.0,
    "Saturation": 2.0,
    "Temperature": 50.0,
    "Tint": 1.0,
    "CropLeft": 0.005,
    "CropRight": 0.005,
    "CropTop": 0.005,
    "CropBottom": 0.005,
    "CropAngle": 0.1,
}

PERSONALIZATION_CAPS: Final = {
    "Exposure2012": 0.75,
    "Contrast2012": 20.0,
    "Highlights2012": 25.0,
    "Shadows2012": 25.0,
    "Whites2012": 20.0,
    "Blacks2012": 20.0,
    "Texture": 15.0,
    "Clarity2012": 15.0,
    "Dehaze": 10.0,
    "Vibrance": 20.0,
    "Saturation": 10.0,
    "Temperature": 750.0,
    "Tint": 10.0,
    "CropLeft": 0.03,
    "CropRight": 0.03,
    "CropTop": 0.03,
    "CropBottom": 0.03,
    "CropAngle": 1.5,
}

LIGHTROOM_LIMITS: Final = {
    "Exposure2012": (-5.0, 5.0),
    "Contrast2012": (-100.0, 100.0),
    "Highlights2012": (-100.0, 100.0),
    "Shadows2012": (-100.0, 100.0),
    "Whites2012": (-100.0, 100.0),
    "Blacks2012": (-100.0, 100.0),
    "Texture": (-100.0, 100.0),
    "Clarity2012": (-100.0, 100.0),
    "Dehaze": (-100.0, 100.0),
    "Vibrance": (-100.0, 100.0),
    "Saturation": (-100.0, 100.0),
    "Temperature": (2_000.0, 50_000.0),
    "Tint": (-150.0, 150.0),
    "CropLeft": (0.0, 1.0),
    "CropRight": (0.0, 1.0),
    "CropTop": (0.0, 1.0),
    "CropBottom": (0.0, 1.0),
    "CropAngle": (-45.0, 45.0),
}
