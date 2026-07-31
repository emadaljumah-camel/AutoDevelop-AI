import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from autodevelop.learning.database import LearningDatabase, LearningDatabaseError
from autodevelop.learning.migrations import (
    MIGRATIONS,
    SCHEMA_VERSION,
    UnsupportedLearningSchemaError,
)


def test_database_initializes_reopens_and_configures_sqlite(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "learning.sqlite3"
    database = LearningDatabase(path)

    database.initialize()
    database.initialize()

    assert path.parent.is_dir()
    assert path.is_file()
    with database.connect() as connection:
        version = connection.execute(
            "SELECT MAX(version) FROM learning_schema"
        ).fetchone()[0]
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    assert version == SCHEMA_VERSION
    assert journal_mode.lower() == "wal"
    assert foreign_keys == 1


def test_future_schema_fails_clearly(tmp_path: Path) -> None:
    database = LearningDatabase(tmp_path / "future.sqlite3")
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO learning_schema(version) VALUES (?)",
            (SCHEMA_VERSION + 1,),
        )

    with pytest.raises(UnsupportedLearningSchemaError):
        database.initialize()


def test_invalid_database_parent_fails_safely(tmp_path: Path) -> None:
    blocking_file = tmp_path / "file"
    blocking_file.write_text("not a directory", encoding="utf-8")

    with pytest.raises(LearningDatabaseError):
        LearningDatabase(blocking_file / "learning.sqlite3").initialize()


def test_concurrent_short_transactions_do_not_corrupt_database(
    tmp_path: Path,
) -> None:
    database = LearningDatabase(tmp_path / "concurrent.sqlite3")
    database.initialize()

    def read_schema(_: int) -> int:
        with database.connect() as connection:
            return connection.execute(
                "SELECT MAX(version) FROM learning_schema"
            ).fetchone()[0]

    with ThreadPoolExecutor(max_workers=8) as executor:
        versions = list(executor.map(read_schema, range(40)))

    assert versions == [SCHEMA_VERSION] * 40
    with database.connect() as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_foreign_key_prevents_orphan_feedback(tmp_path: Path) -> None:
    database = LearningDatabase(tmp_path / "foreign.sqlite3")
    database.initialize()
    with pytest.raises(sqlite3.IntegrityError), database.connect() as connection:
        connection.execute(
            """
            INSERT INTO learning_feedback (
                feedback_id, session_id, captured_at_utc, final_settings_json,
                delta_json, significant_delta_json, crop_delta_json,
                crop_changed, accepted_without_change, usable,
                exclusion_reason, schema_version
            ) VALUES ('f', 'missing', 'now', '{}', '{}', '{}', '{}',
                      0, 1, 1, NULL, 1)
            """
        )


def test_schema_one_crop_angle_migrates_without_deleting_feedback(
    tmp_path: Path,
) -> None:
    path = tmp_path / "schema-one.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE learning_schema (
                version INTEGER PRIMARY KEY,
                applied_at_utc TEXT NOT NULL DEFAULT 'now'
            );
            """
        )
        connection.executescript(MIGRATIONS[1])
        connection.execute("INSERT INTO learning_schema(version) VALUES (1)")
        connection.execute(
            """
            INSERT INTO learning_feedback (
                feedback_id, session_id, captured_at_utc, final_settings_json,
                delta_json, significant_delta_json, crop_delta_json,
                crop_changed, accepted_without_change, usable,
                exclusion_reason, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "feedback",
                "session",
                "now",
                "{}",
                "{}",
                "{}",
                '{"CropAngle":-0.7,"CropLeft":0.01}',
                1,
                0,
                1,
                None,
                1,
            ),
        )

    LearningDatabase(path).initialize()

    with sqlite3.connect(path) as connection:
        row = connection.execute(
            """
            SELECT crop_delta_json, leveling_delta_json, leveling_changed
            FROM learning_feedback
            """
        ).fetchone()
        count = connection.execute(
            "SELECT COUNT(*) FROM learning_feedback"
        ).fetchone()[0]
    assert row == ('{"CropLeft":0.01}', '{"CropAngle":-0.7}', 1)
    assert count == 1


def test_schema_two_rows_migrate_with_nullable_mode_fields(
    tmp_path: Path,
) -> None:
    path = tmp_path / "schema-two.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE learning_schema (
                version INTEGER PRIMARY KEY,
                applied_at_utc TEXT NOT NULL DEFAULT 'now'
            )
            """
        )
        connection.executescript(MIGRATIONS[1])
        connection.executescript(MIGRATIONS[2])
        connection.execute(
            "INSERT INTO learning_schema(version) VALUES (1), (2)"
        )
        connection.execute(
            """
            INSERT INTO learning_sessions (
                session_id, request_id, request_hash, photo_key, filename,
                profile_id, stable_model_id, resolved_model_id,
                created_at_utc, baseline_captured_at_utc,
                original_settings_json, recommendation_json,
                applied_baseline_json, exif_context_json,
                validation_summary_json, state, schema_version
            ) VALUES (
                'session', 'request', 'hash', 'photo', 'Legacy.NEF',
                'natural_travel', 'qwen', 'qwen-model', 'now', 'now',
                '{}', '{}', '{"Exposure2012":0}', '{}', '{}',
                'feedback_captured', 2
            )
            """
        )
        connection.execute(
            """
            INSERT INTO learning_feedback (
                feedback_id, session_id, captured_at_utc,
                final_settings_json, delta_json, significant_delta_json,
                crop_delta_json, crop_changed, leveling_delta_json,
                leveling_changed, accepted_without_change, usable,
                exclusion_reason, schema_version
            ) VALUES (
                'feedback', 'session', 'now', '{"Exposure2012":0}',
                '{}', '{}', '{}', 0, '{}', 0, 1, 1, NULL, 2
            )
            """
        )

    LearningDatabase(path).initialize()

    with sqlite3.connect(path) as connection:
        session = connection.execute(
            """
            SELECT applied_upright_mode, applied_hdr_enabled,
                   baseline_upright_mode, ai_upright_mode,
                   baseline_hdr_enabled, ai_hdr_enabled,
                   baseline_hdr_max_value
            FROM learning_sessions
            """
        ).fetchone()
        feedback = connection.execute(
            """
            SELECT final_upright_mode, final_hdr_enabled,
                   upright_changed, upright_accepted,
                   hdr_changed, hdr_accepted
            FROM learning_feedback
            """
        ).fetchone()
        version = connection.execute(
            "SELECT MAX(version) FROM learning_schema"
        ).fetchone()[0]
    assert session == (None, None, None, None, None, None, None)
    assert feedback == (None, None, None, None, None, None)
    assert version == SCHEMA_VERSION


def test_original_schema_three_database_receives_status_columns(
    tmp_path: Path,
) -> None:
    path = tmp_path / "original-schema-three.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE learning_schema (
                version INTEGER PRIMARY KEY,
                applied_at_utc TEXT NOT NULL DEFAULT 'now'
            )
            """
        )
        for version in (1, 2, 3):
            connection.executescript(MIGRATIONS[version])
            connection.execute(
                "INSERT INTO learning_schema(version) VALUES (?)",
                (version,),
            )

    LearningDatabase(path).initialize()

    with sqlite3.connect(path) as connection:
        version = connection.execute(
            "SELECT MAX(version) FROM learning_schema"
        ).fetchone()[0]
        session_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(learning_sessions)"
            )
        }
        feedback_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(learning_feedback)"
            )
        }

    assert version == SCHEMA_VERSION
    for column in (
        "base_scene_evidence_score",
        "hdr_learning_bonus",
        "hdr_preference_bonus",
        "combined_hdr_evidence_score",
        "hdr_decision_basis",
        "hdr_decision_confidence",
        "scene_hdr_inconsistent",
        "hdr_contraindications_json",
    ):
        assert column in session_columns
    assert {
        "baseline_upright_mode",
        "ai_upright_mode",
        "baseline_hdr_enabled",
        "ai_hdr_enabled",
        "baseline_hdr_max_value",
    } <= session_columns
    assert {
        "upright_changed",
        "upright_accepted",
        "hdr_changed",
        "hdr_accepted",
    } <= feedback_columns
