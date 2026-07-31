"""Deterministic visual and photographic-context similarity."""

import math
from dataclasses import replace
from datetime import datetime

from autodevelop.learning.models import RetrievalSample
from autodevelop.learning.schemas import FeatureVector, LearningExifContext


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not left or len(left) != len(right):
        raise ValueError("feature vectors must have equal non-zero dimensions")
    if any(not math.isfinite(value) for value in (*left, *right)):
        raise ValueError("feature vectors must contain only finite values")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm <= 0 or right_norm <= 0:
        raise ValueError("feature vectors must have non-zero magnitude")
    return sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )


def metadata_similarity(
    current: LearningExifContext,
    historical: dict[str, object],
) -> float:
    scores: list[float] = []
    for name in ("camera", "lens", "orientation", "capture_time_category"):
        current_value = getattr(current, name)
        previous_value = historical.get(name)
        if current_value is not None and previous_value is not None:
            scores.append(float(current_value == previous_value))
    if current.iso and isinstance(historical.get("iso"), int):
        ratio = abs(math.log2(current.iso / int(historical["iso"])))
        scores.append(max(0.0, 1.0 - ratio / 4.0))
    if current.focal_length and isinstance(
        historical.get("focal_length"), (int, float)
    ):
        ratio = abs(
            math.log2(current.focal_length / float(historical["focal_length"]))
        )
        scores.append(max(0.0, 1.0 - ratio / 3.0))
    return sum(scores) / len(scores) if scores else 0.0


class LearningRetriever:
    """Rank usable samples supplied by the caller without external services."""

    def retrieve(
        self,
        candidates: list[RetrievalSample],
        *,
        feature: FeatureVector | None,
        exif_context: LearningExifContext,
        minimum_similarity: float,
        maximum_results: int,
    ) -> list[RetrievalSample]:
        ranked: list[RetrievalSample] = []
        for sample in candidates:
            metadata_score = metadata_similarity(exif_context, sample.exif_context)
            if (
                feature is not None
                and sample.vector is not None
                and sample.feature_type == feature.feature_type
                and sample.feature_version == feature.feature_version
                and len(sample.vector) == feature.dimensions
            ):
                visual = cosine_similarity(
                    tuple(feature.vector),
                    sample.vector,
                )
                if visual < minimum_similarity:
                    continue
                score = 0.85 * visual + 0.15 * metadata_score
            else:
                if metadata_score <= 0:
                    continue
                score = metadata_score
            ranked.append(replace(sample, similarity=score))
        ranked.sort(
            key=lambda sample: (
                -sample.similarity,
                -_timestamp(sample.captured_at_utc),
                sample.session_id,
            )
        )
        return ranked[:maximum_results]


def _timestamp(value: datetime) -> float:
    return value.timestamp()
