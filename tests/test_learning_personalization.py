from datetime import UTC, datetime

from autodevelop.learning.constants import MAX_CONTEXT_CHARACTERS
from autodevelop.learning.models import RetrievalSample
from autodevelop.learning.personalization import (
    aggregate_preferences,
    render_personalization,
)


def _sample(
    session_id: str,
    *,
    exposure: float | None,
    similarity: float,
    accepted: bool = False,
) -> RetrievalSample:
    return RetrievalSample(
        session_id=session_id,
        profile_id="natural_travel",
        captured_at_utc=datetime.now(UTC),
        significant_delta=(
            {"Exposure2012": exposure} if exposure is not None else {}
        ),
        crop_delta={},
        leveling_delta={},
        accepted_without_change=accepted,
        feature_type="test",
        feature_version=1,
        vector=(1.0, 0.0),
        exif_context={},
        similarity=similarity,
    )


def test_weighted_median_favors_similar_samples_and_bounds_outlier() -> None:
    context = aggregate_preferences(
        [
            _sample("close", exposure=-0.2, similarity=0.95),
            _sample("also-close", exposure=-0.15, similarity=0.90),
            _sample("outlier", exposure=50.0, similarity=0.71),
        ],
        profile_id="natural_travel",
        usable_sample_count=3,
        feature_type="test",
    )

    assert context is not None
    assert context.preferred_adjustments["Exposure2012"] == -0.15


def test_accepted_without_change_contributes_zero_and_ratio() -> None:
    context = aggregate_preferences(
        [
            _sample("changed", exposure=-0.2, similarity=0.8),
            _sample("accepted-1", exposure=None, similarity=0.9, accepted=True),
            _sample("accepted-2", exposure=None, similarity=0.9, accepted=True),
        ],
        profile_id="natural_travel",
        usable_sample_count=3,
        feature_type="test",
    )

    assert context is not None
    assert context.preferred_adjustments["Exposure2012"] == 0.0
    assert context.accepted_without_change_ratio == 2 / 3


def test_context_is_bounded_aggregate_only_and_deterministic() -> None:
    context = aggregate_preferences(
        [
            _sample("private-session", exposure=-0.2, similarity=0.8),
            _sample("second", exposure=-0.1, similarity=0.8),
            _sample("third", exposure=-0.15, similarity=0.8),
        ],
        profile_id="natural_travel",
        usable_sample_count=3,
        feature_type="test",
    )
    assert context is not None

    rendered = render_personalization(context)

    assert len(rendered) <= MAX_CONTEXT_CHARACTERS
    assert "soft preferences" in rendered
    assert "private-session" not in rendered
    assert ".NEF" not in rendered
    assert "embedding" not in rendered.lower()
    assert rendered.endswith("END PERSONAL EDITING PREFERENCES")
