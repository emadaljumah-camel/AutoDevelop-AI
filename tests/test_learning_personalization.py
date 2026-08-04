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
    upright: str | None = None,
    hdr_enabled: bool | None = None,
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
        upright_mode=upright,
        hdr_enabled=hdr_enabled,
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


def test_categorical_preferences_require_consistent_support() -> None:
    context = aggregate_preferences(
        [
            _sample(
                "one",
                exposure=None,
                similarity=0.9,
                upright="level",
                hdr_enabled=True,
            ),
            _sample(
                "two",
                exposure=None,
                similarity=0.85,
                upright="level",
                hdr_enabled=True,
            ),
            _sample(
                "three",
                exposure=None,
                similarity=0.8,
                upright="level",
                hdr_enabled=True,
            ),
        ],
        profile_id="architecture",
        usable_sample_count=3,
        feature_type="test",
    )

    assert context is not None
    assert context.preferred_upright_mode == "level"
    assert context.preferred_hdr_enabled is True
    assert context.hdr_enable_rate == 1.0
    rendered = render_personalization(context)
    assert "Upright: level (3 similar examples)" in rendered
    assert "HDR edit mode: on (3 similar examples)" in rendered
    assert "never override confidence thresholds" in rendered


def test_unsupported_historical_upright_preferences_are_ignored() -> None:
    for mode in ("vertical", "full"):
        context = aggregate_preferences(
            [
                _sample(
                    str(index),
                    exposure=None,
                    similarity=0.9,
                    upright=mode,
                )
                for index in range(3)
            ],
            profile_id="architecture",
            usable_sample_count=3,
            feature_type="test",
        )

        assert context is not None
        assert context.preferred_upright_mode is None
        assert f"Upright: {mode}" not in render_personalization(context)


def test_hdr_preference_is_rendered_as_global_strong_context() -> None:
    context = aggregate_preferences(
        [
            _sample(
                str(index),
                exposure=None,
                similarity=0.9,
                hdr_enabled=True,
            )
            for index in range(1, 4)
        ],
        profile_id="natural_travel",
        usable_sample_count=22,
        feature_type="test",
    )

    assert context is not None
    rendered = render_personalization(context)
    assert "PERSONAL HDR PREFERENCE" in rendered
    assert "visually similar photographs" in rendered
    assert "strong preference signal" in rendered
    assert "acceptable SDR edit is technically possible" in rendered


def test_two_mode_samples_do_not_create_a_preference() -> None:
    context = aggregate_preferences(
        [
            _sample(
                "one",
                exposure=None,
                similarity=0.9,
                upright="level",
                hdr_enabled=False,
            ),
            _sample(
                "two",
                exposure=None,
                similarity=0.8,
                upright="level",
                hdr_enabled=False,
            ),
        ],
        profile_id="natural_travel",
        usable_sample_count=2,
        feature_type="test",
    )

    assert context is not None
    assert context.preferred_upright_mode is None
    assert context.preferred_hdr_enabled is None
