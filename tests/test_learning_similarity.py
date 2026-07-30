from datetime import UTC, datetime, timedelta

import pytest

from autodevelop.learning.models import RetrievalSample
from autodevelop.learning.schemas import FeatureVector, LearningExifContext
from autodevelop.learning.similarity import LearningRetriever, cosine_similarity


def _sample(
    session_id: str,
    vector: tuple[float, ...] | None,
    *,
    captured: datetime,
    camera: str = "Camera",
) -> RetrievalSample:
    return RetrievalSample(
        session_id=session_id,
        profile_id="natural_travel",
        captured_at_utc=captured,
        significant_delta={"Exposure2012": -0.1},
        crop_delta={},
        leveling_delta={},
        accepted_without_change=False,
        feature_type="test" if vector else None,
        feature_version=1 if vector else None,
        vector=vector,
        exif_context={"camera": camera, "capture_time_category": "day"},
    )


def test_cosine_similarity_known_vectors() -> None:
    assert cosine_similarity((1.0, 0.0), (1.0, 0.0)) == pytest.approx(1.0)
    assert cosine_similarity((1.0, 0.0), (0.0, 1.0)) == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ((1.0,), (1.0, 0.0)),
        ((0.0, 0.0), (1.0, 0.0)),
        ((float("nan"), 0.0), (1.0, 0.0)),
        ((float("inf"), 0.0), (1.0, 0.0)),
    ],
)
def test_invalid_cosine_vectors_are_rejected(left, right) -> None:
    with pytest.raises(ValueError):
        cosine_similarity(left, right)


def test_retrieval_honors_similarity_limit_count_and_tie_breaking() -> None:
    now = datetime.now(UTC)
    feature = FeatureVector(
        feature_type="test",
        feature_version=1,
        dimensions=2,
        vector=[1.0, 0.0],
    )
    candidates = [
        _sample("older", (1.0, 0.0), captured=now - timedelta(days=2)),
        _sample("newer", (1.0, 0.0), captured=now),
        _sample("orthogonal", (0.0, 1.0), captured=now),
    ]

    result = LearningRetriever().retrieve(
        candidates,
        feature=feature,
        exif_context=LearningExifContext(
            camera="Camera", capture_time_category="day"
        ),
        minimum_similarity=0.70,
        maximum_results=1,
    )

    assert [sample.session_id for sample in result] == ["newer"]


def test_metadata_fallback_works_without_embeddings() -> None:
    now = datetime.now(UTC)
    result = LearningRetriever().retrieve(
        [_sample("metadata", None, captured=now)],
        feature=None,
        exif_context=LearningExifContext(
            camera="Camera", capture_time_category="day"
        ),
        minimum_similarity=0.70,
        maximum_results=5,
    )

    assert [sample.session_id for sample in result] == ["metadata"]
