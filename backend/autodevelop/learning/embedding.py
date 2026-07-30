"""Deterministic local visual features with no cloud dependency."""

import io
import math
from typing import Protocol

from autodevelop.learning.schemas import FeatureVector


class ImageEmbeddingProvider(Protocol):
    available: bool
    feature_type: str | None

    def embed(self, image_bytes: bytes) -> FeatureVector:
        """Return one finite, normalized image representation."""


class LocalColorLuminanceEmbedding:
    """A lightweight 64-dimensional color/luminance descriptor."""

    feature_type = "local_color_luminance"
    feature_version = 1
    dimensions = 64

    def __init__(self) -> None:
        try:
            from PIL import Image as _Image  # noqa: F401
        except ImportError:
            self.available = False
        else:
            self.available = True

    def embed(self, image_bytes: bytes) -> FeatureVector:
        if not self.available:
            raise RuntimeError("The local embedding provider is unavailable.")
        from PIL import Image

        with Image.open(io.BytesIO(image_bytes)) as source:
            image = source.convert("RGB")
            histogram = image.histogram()
            pixel_count = max(image.width * image.height, 1)
            color = []
            for channel in range(3):
                values = histogram[channel * 256:(channel + 1) * 256]
                for bucket in range(16):
                    total = sum(values[bucket * 16:(bucket + 1) * 16])
                    color.append(total / pixel_count)
            luminance = image.convert("L").resize((4, 4))
            grid = [value / 255.0 for value in luminance.getdata()]
        vector = color + grid
        norm = math.sqrt(sum(value * value for value in vector))
        if norm <= 0 or not math.isfinite(norm):
            raise ValueError("The image representation could not be normalized.")
        normalized = [value / norm for value in vector]
        return FeatureVector(
            feature_type=self.feature_type,
            feature_version=self.feature_version,
            dimensions=self.dimensions,
            vector=normalized,
        )
