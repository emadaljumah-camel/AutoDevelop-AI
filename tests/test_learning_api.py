import json
import logging
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from autodevelop.api.dependencies import get_learning_service
from autodevelop.config import Settings
from autodevelop.learning.comparison import compare_feedback_settings
from autodevelop.learning.schemas import (
    DevelopModeState,
    DevelopSettingDeltas,
    FeedbackRequest,
)
from autodevelop.main import create_app
from autodevelop.model_clients import FakeModelClient
from autodevelop.models import DevelopSettings

PHOTO_KEY = "a" * 64


@pytest.fixture
def learning_client(tmp_path: Path):
    database_path = tmp_path / "learning.sqlite3"
    settings = Settings(
        _env_file=None,
        learning_db=database_path,
        log_path=tmp_path / "autodevelop.log",
    )
    app = create_app(settings, model_client=FakeModelClient())
    with TestClient(app) as client:
        yield client, database_path


def _baseline(
    *,
    session_id: str | None = None,
    profile: str = "natural_travel",
    model: str = "qwen",
    exposure: float = 0.4,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "session_id": session_id or str(uuid4()),
        "request_id": str(uuid4()),
        "photo_key": PHOTO_KEY,
        "filename": "Learning.NEF",
        "catalog_id": "catalog-hash",
        "local_identifier": "42",
        "profile": profile,
        "model": model,
        "resolved_model": "qwen_qwen3-vl-32b-instruct",
        "original_settings": {"Exposure2012": 0.0},
        "recommendation": {"Exposure2012": exposure},
        "applied_baseline": {
            "Exposure2012": exposure,
            "Contrast2012": 12.0,
            "Clarity2012": 18.0,
            "Dehaze": 6.0,
            "Vibrance": 18.0,
            "Highlights2012": -20.0,
            "CropLeft": 0.0,
            "CropRight": 1.0,
            "CropTop": 0.0,
            "CropBottom": 1.0,
        },
        "exif_context": {
            "camera": "Camera",
            "iso": 400,
            "capture_time_category": "day",
        },
        "validation_summary": {"issue_count": 0},
    }


def test_upright_and_hdr_changes_are_compared_and_persisted(
    learning_client,
) -> None:
    client, database_path = learning_client
    baseline = _baseline()
    baseline["applied_modes"] = {
        "upright": "off",
        "upright_raw_value": 0,
        "hdr_enabled": False,
        "hdr_raw_value": 0,
        "hdr_max_value": 2.3,
    }
    baseline["original_modes"] = {
        "upright": "off",
        "hdr_enabled": False,
    }
    baseline["recommendation_modes"] = {
        "upright": "off",
        "hdr_enabled": False,
    }
    stored = client.post(
        "/autodevelop/v1/learning/baselines",
        json=baseline,
    )
    assert stored.status_code == 200

    feedback = client.post(
        "/autodevelop/v1/learning/feedback",
        json={
            "schema_version": 1,
            "session_id": baseline["session_id"],
            "photo_key": PHOTO_KEY,
            "final_settings": baseline["applied_baseline"],
            "final_modes": {
                "upright": "vertical",
                "hdr_enabled": True,
            },
        },
    )

    assert feedback.status_code == 200
    assert feedback.json()["accepted_without_change"] is False
    assert feedback.json()["mode_changes"] == {
        "upright": "vertical",
        "hdr_enabled": True,
    }
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT s.applied_upright_mode, s.applied_hdr_enabled,
                   s.baseline_upright_mode, s.ai_upright_mode,
                   s.baseline_hdr_enabled, s.ai_hdr_enabled,
                   s.baseline_hdr_max_value,
                   f.final_upright_mode, f.final_hdr_enabled,
                   f.upright_changed, f.upright_accepted,
                   f.hdr_changed, f.hdr_accepted
            FROM learning_sessions AS s
            JOIN learning_feedback AS f USING (session_id)
            """
        ).fetchone()
    assert row == (
        "off", 0, "off", "off", 0, 0, 2.3,
        "vertical", 1, 1, 0, 1, 0,
    )

    status = client.get("/autodevelop/v1/learning/status")
    assert status.status_code == 200
    assert status.json()["upright_learning"] == {
        "usable_sample_count": 1,
        "change_count": 1,
        "acceptance_count": 0,
    }
    assert status.json()["hdr_learning"] == {
        "usable_sample_count": 1,
        "change_count": 1,
        "acceptance_count": 0,
    }


def test_hdr_decision_confidence_is_persisted_for_calibration(
    learning_client,
) -> None:
    client, database_path = learning_client
    baseline = _baseline()
    baseline["hdr_decision"] = {
        "scene_hdr_candidate": True,
        "scene_hdr_confidence": 0.78,
        "base_scene_evidence_score": 0.56,
        "learning_bonus": 0.04,
        "user_preference_bonus": 0.06,
        "combined_evidence_score": 0.66,
        "decision_basis": "disabled",
        "decision_confidence": None,
        "scene_hdr_inconsistent": False,
        "contraindications": [],
        "visual_evidence_score": 0.56,
        "hdr_evidence_score": 0.66,
        "hdr_learning_applied": True,
        "hdr_learning_enable_rate": 0.91,
        "hdr_learning_sample_count": 22,
        "raw_hdr_recommended": False,
        "raw_hdr_confidence": 0.64,
        "validated_hdr_enabled": False,
        "validated_hdr_confidence": 0.64,
        "hdr_rejected": False,
        "hdr_rejection_reason": "model_not_recommended",
    }

    response = client.post(
        "/autodevelop/v1/learning/baselines",
        json=baseline,
    )

    assert response.status_code == 200
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT scene_hdr_candidate, scene_hdr_confidence,
                   base_scene_evidence_score, hdr_learning_bonus,
                   hdr_preference_bonus, combined_hdr_evidence_score,
                   hdr_decision_basis, hdr_decision_confidence,
                   scene_hdr_inconsistent, hdr_contraindications_json,
                   hdr_evidence_score, raw_hdr_recommended,
                   raw_hdr_confidence, validated_hdr_enabled,
                   validated_hdr_confidence, hdr_rejection_reason,
                   hdr_personalization_applied, hdr_learning_enable_rate
            FROM learning_sessions
            WHERE session_id = ?
            """,
            (baseline["session_id"],),
        ).fetchone()
    assert row == (
        1,
        0.78,
        0.56,
        0.04,
        0.06,
        0.66,
        "disabled",
        None,
        0,
        "[]",
        0.66,
        0,
        0.64,
        0,
        0.64,
        "model_not_recommended",
        1,
        0.91,
    )


@pytest.mark.parametrize(
    "contraindications",
    [[], ["high_noise_risk"]],
)
def test_hdr_contraindication_lists_round_trip_into_feedback_preview(
    learning_client,
    contraindications: list[str],
) -> None:
    client, database_path = learning_client
    baseline = _baseline()
    baseline["hdr_decision"] = {
        "contraindications": contraindications,
    }

    stored = client.post(
        "/autodevelop/v1/learning/baselines",
        json=baseline,
    )
    preview = client.post(
        "/autodevelop/v1/learning/feedback/preview",
        json={
            "schema_version": 1,
            "session_id": baseline["session_id"],
            "photo_key": baseline["photo_key"],
            "final_settings": baseline["applied_baseline"],
            "final_modes": {},
        },
    )

    assert stored.status_code == 200
    assert preview.status_code == 200
    assert preview.json()["accepted_without_change"] is True
    with sqlite3.connect(database_path) as connection:
        stored_json = connection.execute(
            """
            SELECT hdr_contraindications_json
            FROM learning_sessions
            WHERE session_id = ?
            """,
            (baseline["session_id"],),
        ).fetchone()[0]
    assert json.loads(stored_json) == contraindications


def test_guided_upright_is_not_a_supported_learning_mode() -> None:
    with pytest.raises(ValidationError):
        DevelopModeState(upright="guided")


def test_baseline_is_stored_idempotently_and_conflicts_are_rejected(
    learning_client,
) -> None:
    client, database_path = learning_client
    request = _baseline()

    first = client.post("/autodevelop/v1/learning/baselines", json=request)
    duplicate = client.post("/autodevelop/v1/learning/baselines", json=request)
    conflicting = client.post(
        "/autodevelop/v1/learning/baselines",
        json={**request, "recommendation": {"Exposure2012": 0.7}},
    )

    assert first.status_code == 200
    assert first.json()["stored"] is True
    assert duplicate.status_code == 200
    assert duplicate.json()["stored"] is False
    assert conflicting.status_code == 409
    assert conflicting.json()["error"]["code"] == "baseline_conflict"
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM learning_sessions"
        ).fetchone()[0] == 1


@pytest.mark.parametrize(
    ("changes", "status_code"),
    [
        ({"profile": "unknown"}, 400),
        ({"model": "unknown"}, 400),
        ({"model": "claude"}, 400),
        ({"session_id": "not-a-uuid"}, 422),
        ({"photo_key": "not-a-hash"}, 422),
        ({"unexpected": True}, 422),
        ({"recommendation": {"UnsupportedSetting": 2}}, 422),
        ({"applied_baseline": {}}, 422),
        ({"filename": "x" * 256}, 422),
    ],
)
def test_invalid_baselines_are_rejected(
    learning_client,
    changes: dict[str, object],
    status_code: int,
) -> None:
    client, _ = learning_client

    response = client.post(
        "/autodevelop/v1/learning/baselines",
        json={**_baseline(), **changes},
    )

    assert response.status_code == status_code


def test_nonfinite_feedback_is_rejected_before_storage() -> None:
    with pytest.raises(ValidationError):
        FeedbackRequest.model_validate(
            {
                "schema_version": 1,
                "session_id": str(uuid4()),
                "photo_key": PHOTO_KEY,
                "final_settings": {"Exposure2012": float("nan")},
            }
        )


@pytest.mark.parametrize(
    ("setting", "baseline", "current", "expected_delta"),
    [
        ("Contrast2012", 12.0, 22.0, 10.0),
        ("Clarity2012", 18.0, 28.0, 10.0),
        ("Dehaze", 6.0, 11.0, 5.0),
        ("Vibrance", 18.0, 28.0, 10.0),
    ],
)
def test_reported_lightroom_settings_are_significant(
    setting: str,
    baseline: float,
    current: float,
    expected_delta: float,
) -> None:
    result = compare_feedback_settings(
        {setting: baseline},
        {setting: current},
    )

    assert getattr(result.significant_delta, setting) == expected_delta
    assert result.comparisons[setting].significant is True


def test_changes_below_threshold_are_accepted_without_change() -> None:
    result = compare_feedback_settings(
        {
            "Contrast2012": 12.0,
            "Clarity2012": 18.0,
            "Dehaze": 6.0,
            "Vibrance": 18.0,
        },
        {
            "Contrast2012": 13.9,
            "Clarity2012": 19.9,
            "Dehaze": 6.9,
            "Vibrance": 19.9,
        },
    )

    assert result.accepted_without_change is True
    assert not result.significant_delta.model_dump(exclude_none=True)
    assert set(result.ignored_delta.model_dump(exclude_none=True)) == {
        "Contrast2012",
        "Clarity2012",
        "Dehaze",
        "Vibrance",
    }


def test_preview_and_save_share_authoritative_comparison(
    learning_client,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, database_path = learning_client
    baseline = _baseline()
    assert client.post(
        "/autodevelop/v1/learning/baselines",
        json=baseline,
    ).status_code == 200
    request = {
        "schema_version": 1,
        "session_id": baseline["session_id"],
        "photo_key": PHOTO_KEY,
        "final_settings": {
            "Contrast2012": 25.0,
            "Clarity2012": 32.0,
            "Dehaze": 18.0,
            "Vibrance": 38.0,
        },
    }

    with caplog.at_level(
        logging.DEBUG,
        logger="autodevelop.learning.service",
    ):
        preview = client.post(
            "/autodevelop/v1/learning/feedback/preview",
            json=request,
        )

    assert preview.status_code == 200
    body = preview.json()
    assert body["has_significant_changes"] is True
    assert body["accepted_without_change"] is False
    expected = {
        "Contrast2012": (12.0, 25.0, 13.0, 2.0),
        "Clarity2012": (18.0, 32.0, 14.0, 2.0),
        "Dehaze": (6.0, 18.0, 12.0, 1.0),
        "Vibrance": (18.0, 38.0, 20.0, 2.0),
    }
    for setting, values in expected.items():
        detail = body["significant_changes"][setting]
        assert (
            detail["baseline"],
            detail["current"],
            detail["delta"],
            detail["threshold"],
        ) == values
        assert detail["significant"] is True
        assert any(
            f"setting={setting}" in record.message
            and "significant=true" in record.message
            for record in caplog.records
        )

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM learning_feedback"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT state FROM learning_sessions"
        ).fetchone()[0] == "pending_feedback"

    saved = client.post(
        "/autodevelop/v1/learning/feedback",
        json=request,
    )

    assert saved.status_code == 200
    saved_body = saved.json()
    assert saved_body["accepted_without_change"] is False
    for setting, (_, _, delta, _) in expected.items():
        assert saved_body["significant_changes"][setting] == delta
    with sqlite3.connect(database_path) as connection:
        stored_delta = json.loads(
            connection.execute(
                "SELECT delta_json FROM learning_feedback"
            ).fetchone()[0]
        )
    assert stored_delta == {
        setting: values[2]
        for setting, values in expected.items()
    }


def test_negative_crop_deltas_preview_save_and_persist_identically(
    learning_client,
) -> None:
    client, database_path = learning_client
    baseline = _baseline()
    baseline["applied_baseline"].update(
        {
            "CropRight": 0.95,
            "CropBottom": 0.94,
        }
    )
    assert client.post(
        "/autodevelop/v1/learning/baselines",
        json=baseline,
    ).status_code == 200
    request = {
        "schema_version": 1,
        "session_id": baseline["session_id"],
        "photo_key": PHOTO_KEY,
        "final_settings": {
            "Contrast2012": 22.0,
            "CropRight": 0.943338,
            "CropBottom": 0.933476,
        },
    }

    preview = client.post(
        "/autodevelop/v1/learning/feedback/preview",
        json=request,
    )
    saved = client.post(
        "/autodevelop/v1/learning/feedback",
        json=request,
    )

    assert preview.status_code == 200
    assert saved.status_code == 200
    preview_crop = {
        key: detail["delta"]
        for key, detail in preview.json()["crop_changes"].items()
    }
    saved_crop = {
        key: value
        for key, value in saved.json()["crop_changes"].items()
        if value is not None
    }
    assert saved_crop == pytest.approx(
        {
            "CropRight": -0.006662,
            "CropBottom": -0.006524,
        }
    )
    assert preview_crop == pytest.approx(saved_crop)
    assert saved.json()["significant_changes"]["Contrast2012"] == 10.0

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT crop_delta_json, delta_json, crop_changed
            FROM learning_feedback
            """
        ).fetchone()
    stored_crop = json.loads(row[0])
    stored_delta = json.loads(row[1])
    assert stored_crop == pytest.approx(saved_crop)
    assert stored_delta["CropRight"] == pytest.approx(-0.006662)
    assert stored_delta["CropBottom"] == pytest.approx(-0.006524)
    assert stored_delta["Contrast2012"] == 10.0
    assert row[2] == 1


@pytest.mark.parametrize(
    ("setting", "baseline_value", "final_value", "expected_delta"),
    [
        ("CropLeft", 0.02, 0.03, 0.01),
        ("CropAngle", 2.0, -1.0, -3.0),
    ],
)
def test_signed_crop_deltas_save_successfully(
    learning_client,
    setting: str,
    baseline_value: float,
    final_value: float,
    expected_delta: float,
) -> None:
    client, _ = learning_client
    baseline = _baseline()
    baseline["applied_baseline"][setting] = baseline_value
    assert client.post(
        "/autodevelop/v1/learning/baselines",
        json=baseline,
    ).status_code == 200

    response = client.post(
        "/autodevelop/v1/learning/feedback",
        json={
            "schema_version": 1,
            "session_id": baseline["session_id"],
            "photo_key": PHOTO_KEY,
            "final_settings": {setting: final_value},
        },
    )

    assert response.status_code == 200
    change_group = (
        "leveling_changes" if setting == "CropAngle" else "crop_changes"
    )
    assert response.json()[change_group][setting] == pytest.approx(
        expected_delta
    )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_crop_delta_schema_rejects_nonfinite_values(value: float) -> None:
    with pytest.raises(ValidationError):
        DevelopSettingDeltas.model_validate({"CropRight": value})


@pytest.mark.parametrize("value", [-1.01, 1.01])
def test_crop_delta_schema_rejects_values_beyond_safe_difference(
    value: float,
) -> None:
    with pytest.raises(ValidationError):
        DevelopSettingDeltas.model_validate({"CropRight": value})


@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_absolute_crop_coordinates_keep_unit_range_validation(
    value: float,
) -> None:
    with pytest.raises(ValidationError):
        DevelopSettings.model_validate({"CropRight": value})


def test_feedback_schema_errors_return_sanitized_structured_errors(
    learning_client,
) -> None:
    client, _ = learning_client
    try:
        DevelopSettingDeltas.model_validate({"CropRight": float("inf")})
    except ValidationError as error:
        schema_error = error
    else:
        raise AssertionError("expected a schema validation error")

    class BrokenFeedbackService:
        async def capture_feedback(self, request):
            raise schema_error

        async def preview_feedback(self, request):
            raise schema_error

    async def override_learning_service():
        return BrokenFeedbackService()

    client.app.dependency_overrides[get_learning_service] = (
        override_learning_service
    )
    request = {
        "schema_version": 1,
        "session_id": str(uuid4()),
        "photo_key": PHOTO_KEY,
        "final_settings": {"CropRight": 0.9},
    }
    try:
        saved = client.post(
            "/autodevelop/v1/learning/feedback",
            json=request,
        )
        preview = client.post(
            "/autodevelop/v1/learning/feedback/preview",
            json=request,
        )
    finally:
        client.app.dependency_overrides.pop(get_learning_service, None)

    for response in (saved, preview):
        assert response.status_code == 500
        assert response.json() == {
            "schema_version": 1,
            "error": {
                "code": "feedback_processing_error",
                "message": "Feedback could not be processed safely.",
            },
        }
        assert "CropRight" not in response.text


@pytest.mark.parametrize("alias", ["Contrast", "Clarity", "dehaze", "vibrance"])
def test_feedback_preview_rejects_noncanonical_aliases(
    learning_client,
    alias: str,
) -> None:
    client, _ = learning_client
    baseline = _baseline()
    client.post("/autodevelop/v1/learning/baselines", json=baseline)

    response = client.post(
        "/autodevelop/v1/learning/feedback/preview",
        json={
            "schema_version": 1,
            "session_id": baseline["session_id"],
            "photo_key": PHOTO_KEY,
            "final_settings": {alias: 20},
        },
    )

    assert response.status_code == 422


def test_historical_empty_baseline_is_not_classified_as_unchanged(
    learning_client,
) -> None:
    client, database_path = learning_client
    baseline = _baseline()
    client.post("/autodevelop/v1/learning/baselines", json=baseline)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE learning_sessions SET applied_baseline_json = '{}'"
        )

    request = {
        "schema_version": 1,
        "session_id": baseline["session_id"],
        "photo_key": PHOTO_KEY,
        "final_settings": {"Contrast2012": 25.0},
    }
    preview = client.post(
        "/autodevelop/v1/learning/feedback/preview",
        json=request,
    )
    save = client.post(
        "/autodevelop/v1/learning/feedback",
        json=request,
    )

    assert preview.status_code == 409
    assert preview.json()["error"]["code"] == "baseline_unavailable"
    assert save.status_code == 409
    assert save.json()["error"]["code"] == "baseline_unavailable"
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM learning_feedback"
        ).fetchone()[0] == 0


def test_feedback_uses_trusted_baseline_and_separates_crop(
    learning_client,
) -> None:
    client, database_path = learning_client
    baseline = _baseline()
    assert client.post(
        "/autodevelop/v1/learning/baselines", json=baseline
    ).status_code == 200

    feedback = client.post(
        "/autodevelop/v1/learning/feedback",
        json={
            "schema_version": 1,
            "session_id": baseline["session_id"],
            "photo_key": PHOTO_KEY,
            "final_settings": {
                "Exposure2012": 0.2,
                "Highlights2012": -19.0,
                "CropLeft": 0.01,
                "CropRight": 1.0,
                "CropTop": 0.0,
                "CropBottom": 1.0,
            },
        },
    )

    assert feedback.status_code == 200
    body = feedback.json()
    assert body["significant_changes"]["Exposure2012"] == pytest.approx(-0.2)
    assert body["ignored_changes"]["Highlights2012"] == pytest.approx(1.0)
    assert body["crop_changes"]["CropLeft"] == pytest.approx(0.01)
    assert body["accepted_without_change"] is False
    with sqlite3.connect(database_path) as connection:
        delta = connection.execute(
            "SELECT delta_json FROM learning_feedback"
        ).fetchone()[0]
        assert '"Exposure2012":-0.2' in delta


def test_unchanged_feedback_is_stored_as_acceptance_and_recaptured(
    learning_client,
) -> None:
    client, database_path = learning_client
    baseline = _baseline()
    client.post("/autodevelop/v1/learning/baselines", json=baseline)
    request = {
        "schema_version": 1,
        "session_id": baseline["session_id"],
        "photo_key": PHOTO_KEY,
        "final_settings": baseline["applied_baseline"],
    }

    first = client.post("/autodevelop/v1/learning/feedback", json=request)
    second = client.post("/autodevelop/v1/learning/feedback", json=request)

    assert first.json()["accepted_without_change"] is True
    assert second.status_code == 200
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM learning_feedback"
        ).fetchone()[0] == 1


def test_missing_session_photo_mismatch_and_client_baseline_are_rejected(
    learning_client,
) -> None:
    client, _ = learning_client
    missing = client.post(
        "/autodevelop/v1/learning/feedback",
        json={
            "schema_version": 1,
            "session_id": str(uuid4()),
            "photo_key": PHOTO_KEY,
            "final_settings": {"Exposure2012": 0.0},
        },
    )
    baseline = _baseline()
    client.post("/autodevelop/v1/learning/baselines", json=baseline)
    mismatch = client.post(
        "/autodevelop/v1/learning/feedback",
        json={
            "schema_version": 1,
            "session_id": baseline["session_id"],
            "photo_key": "b" * 64,
            "final_settings": {"Exposure2012": 0.0},
        },
    )
    untrusted = client.post(
        "/autodevelop/v1/learning/feedback",
        json={
            "schema_version": 1,
            "session_id": baseline["session_id"],
            "photo_key": PHOTO_KEY,
            "baseline": {"Exposure2012": 99},
            "final_settings": {"Exposure2012": 0.0},
        },
    )

    assert missing.status_code == 404
    assert mismatch.status_code == 409
    assert untrusted.status_code == 422


def test_status_and_deletion_return_only_safe_aggregates(learning_client) -> None:
    client, _ = learning_client
    first = _baseline()
    second = _baseline()
    client.post("/autodevelop/v1/learning/baselines", json=first)
    client.post("/autodevelop/v1/learning/baselines", json=second)

    status_response = client.get("/autodevelop/v1/learning/status")
    invalid_delete = client.request(
        "DELETE",
        "/autodevelop/v1/learning/all",
        json={"confirm": "wrong"},
    )
    delete_one = client.delete(
        f"/autodevelop/v1/learning/sessions/{first['session_id']}"
    )
    delete_all = client.request(
        "DELETE",
        "/autodevelop/v1/learning/all",
        json={"confirm": "DELETE_ALL_LEARNING_DATA"},
    )

    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["pending_sessions"] == 2
    serialized = status_response.text.lower()
    for forbidden in ("sqlite", "database_path", "filename", "vector"):
        assert forbidden not in serialized
    assert invalid_delete.status_code == 422
    assert delete_one.json()["affected_sessions"] == 1
    assert delete_all.json()["affected_sessions"] == 2
