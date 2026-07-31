"""Ordered SQLite migrations for personalized learning."""

import sqlite3

from autodevelop.learning.constants import SCHEMA_VERSION


class UnsupportedLearningSchemaError(RuntimeError):
    """Raised when a database was created by a newer application version."""


_MIGRATION_1 = """
CREATE TABLE learning_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    request_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    photo_key TEXT NOT NULL,
    filename TEXT NOT NULL,
    catalog_id TEXT,
    local_identifier TEXT,
    profile_id TEXT NOT NULL,
    stable_model_id TEXT NOT NULL,
    resolved_model_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    baseline_captured_at_utc TEXT NOT NULL,
    original_settings_json TEXT NOT NULL,
    recommendation_json TEXT NOT NULL,
    applied_baseline_json TEXT NOT NULL,
    exif_context_json TEXT NOT NULL,
    validation_summary_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN ('pending_feedback', 'feedback_captured', 'dismissed', 'stale')
    ),
    schema_version INTEGER NOT NULL
);

CREATE TABLE learning_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feedback_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL UNIQUE,
    captured_at_utc TEXT NOT NULL,
    final_settings_json TEXT NOT NULL,
    delta_json TEXT NOT NULL,
    significant_delta_json TEXT NOT NULL,
    crop_delta_json TEXT NOT NULL,
    crop_changed INTEGER NOT NULL CHECK (crop_changed IN (0, 1)),
    accepted_without_change INTEGER NOT NULL
        CHECK (accepted_without_change IN (0, 1)),
    usable INTEGER NOT NULL CHECK (usable IN (0, 1)),
    exclusion_reason TEXT,
    schema_version INTEGER NOT NULL,
    FOREIGN KEY (session_id) REFERENCES learning_sessions(session_id)
        ON DELETE CASCADE
);

CREATE TABLE learning_features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    feature_type TEXT NOT NULL,
    feature_version INTEGER NOT NULL,
    dimensions INTEGER NOT NULL CHECK (dimensions > 0 AND dimensions <= 512),
    vector_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES learning_sessions(session_id)
        ON DELETE CASCADE
);

CREATE INDEX learning_sessions_profile_state_idx
    ON learning_sessions(profile_id, state);
CREATE INDEX learning_feedback_usable_idx
    ON learning_feedback(usable, captured_at_utc);
"""

_MIGRATION_2 = """
ALTER TABLE learning_feedback
ADD COLUMN leveling_delta_json TEXT NOT NULL DEFAULT '{}';

ALTER TABLE learning_feedback
ADD COLUMN leveling_changed INTEGER NOT NULL DEFAULT 0
    CHECK (leveling_changed IN (0, 1));

UPDATE learning_feedback
SET leveling_delta_json = CASE
        WHEN json_type(crop_delta_json, '$.CropAngle') IS NOT NULL
        THEN json_object(
            'CropAngle',
            json_extract(crop_delta_json, '$.CropAngle')
        )
        ELSE '{}'
    END,
    leveling_changed = CASE
        WHEN json_type(crop_delta_json, '$.CropAngle') IS NOT NULL THEN 1
        ELSE 0
    END,
    crop_delta_json = json_remove(crop_delta_json, '$.CropAngle');
"""

_MIGRATION_3 = """
ALTER TABLE learning_sessions
ADD COLUMN applied_upright_mode TEXT
    CHECK (
        applied_upright_mode IS NULL
        OR applied_upright_mode IN ('off', 'auto', 'full', 'level', 'vertical')
    );

ALTER TABLE learning_sessions
ADD COLUMN applied_hdr_enabled INTEGER
    CHECK (applied_hdr_enabled IS NULL OR applied_hdr_enabled IN (0, 1));

ALTER TABLE learning_feedback
ADD COLUMN final_upright_mode TEXT
    CHECK (
        final_upright_mode IS NULL
        OR final_upright_mode IN ('off', 'auto', 'full', 'level', 'vertical')
    );

ALTER TABLE learning_feedback
ADD COLUMN final_hdr_enabled INTEGER
    CHECK (final_hdr_enabled IS NULL OR final_hdr_enabled IN (0, 1));
"""

_MIGRATION_4 = """
ALTER TABLE learning_sessions
ADD COLUMN baseline_upright_mode TEXT
    CHECK (
        baseline_upright_mode IS NULL
        OR baseline_upright_mode IN ('off', 'auto', 'full', 'level', 'vertical')
    );

ALTER TABLE learning_sessions
ADD COLUMN ai_upright_mode TEXT
    CHECK (
        ai_upright_mode IS NULL
        OR ai_upright_mode IN ('off', 'auto', 'full', 'level', 'vertical')
    );

ALTER TABLE learning_sessions
ADD COLUMN baseline_hdr_enabled INTEGER
    CHECK (baseline_hdr_enabled IS NULL OR baseline_hdr_enabled IN (0, 1));

ALTER TABLE learning_sessions
ADD COLUMN ai_hdr_enabled INTEGER
    CHECK (ai_hdr_enabled IS NULL OR ai_hdr_enabled IN (0, 1));

ALTER TABLE learning_sessions
ADD COLUMN baseline_hdr_max_value REAL;

ALTER TABLE learning_feedback
ADD COLUMN upright_changed INTEGER
    CHECK (upright_changed IS NULL OR upright_changed IN (0, 1));

ALTER TABLE learning_feedback
ADD COLUMN upright_accepted INTEGER
    CHECK (upright_accepted IS NULL OR upright_accepted IN (0, 1));

ALTER TABLE learning_feedback
ADD COLUMN hdr_changed INTEGER
    CHECK (hdr_changed IS NULL OR hdr_changed IN (0, 1));

ALTER TABLE learning_feedback
ADD COLUMN hdr_accepted INTEGER
    CHECK (hdr_accepted IS NULL OR hdr_accepted IN (0, 1));
"""

_MIGRATION_5 = """
ALTER TABLE learning_sessions
ADD COLUMN scene_hdr_candidate INTEGER
    CHECK (scene_hdr_candidate IS NULL OR scene_hdr_candidate IN (0, 1));

ALTER TABLE learning_sessions ADD COLUMN scene_hdr_confidence REAL;
ALTER TABLE learning_sessions ADD COLUMN hdr_evidence_score REAL;

ALTER TABLE learning_sessions
ADD COLUMN raw_hdr_recommended INTEGER
    CHECK (raw_hdr_recommended IS NULL OR raw_hdr_recommended IN (0, 1));

ALTER TABLE learning_sessions ADD COLUMN raw_hdr_confidence REAL;

ALTER TABLE learning_sessions
ADD COLUMN validated_hdr_enabled INTEGER
    CHECK (validated_hdr_enabled IS NULL OR validated_hdr_enabled IN (0, 1));

ALTER TABLE learning_sessions ADD COLUMN validated_hdr_confidence REAL;
ALTER TABLE learning_sessions ADD COLUMN hdr_rejection_reason TEXT;

ALTER TABLE learning_sessions
ADD COLUMN hdr_personalization_applied INTEGER
    CHECK (
        hdr_personalization_applied IS NULL
        OR hdr_personalization_applied IN (0, 1)
    );

ALTER TABLE learning_sessions ADD COLUMN hdr_learning_enable_rate REAL;
"""

_MIGRATION_6 = """
ALTER TABLE learning_sessions ADD COLUMN base_scene_evidence_score REAL;
ALTER TABLE learning_sessions ADD COLUMN hdr_learning_bonus REAL;
ALTER TABLE learning_sessions ADD COLUMN hdr_preference_bonus REAL;
ALTER TABLE learning_sessions ADD COLUMN combined_hdr_evidence_score REAL;
ALTER TABLE learning_sessions ADD COLUMN hdr_decision_basis TEXT;
ALTER TABLE learning_sessions ADD COLUMN hdr_decision_confidence REAL;

ALTER TABLE learning_sessions
ADD COLUMN scene_hdr_inconsistent INTEGER
    CHECK (
        scene_hdr_inconsistent IS NULL
        OR scene_hdr_inconsistent IN (0, 1)
    );

ALTER TABLE learning_sessions ADD COLUMN hdr_contraindications_json TEXT;
"""

MIGRATIONS = {
    1: _MIGRATION_1,
    2: _MIGRATION_2,
    3: _MIGRATION_3,
    4: _MIGRATION_4,
    5: _MIGRATION_5,
    6: _MIGRATION_6,
}


def migrate(connection: sqlite3.Connection) -> None:
    """Apply every pending migration in one exclusive transaction."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_schema (
            version INTEGER PRIMARY KEY,
            applied_at_utc TEXT NOT NULL
                DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
        """
    )
    row = connection.execute(
        "SELECT MAX(version) AS version FROM learning_schema"
    ).fetchone()
    current = int(row["version"] or 0)
    if current > SCHEMA_VERSION:
        raise UnsupportedLearningSchemaError(
            "The learning database schema is newer than this application."
        )
    for version in range(current + 1, SCHEMA_VERSION + 1):
        script = MIGRATIONS[version]
        try:
            connection.executescript(
                "BEGIN IMMEDIATE;\n"
                f"{script}\n"
                "INSERT INTO learning_schema(version) "
                f"VALUES ({version});\n"
                "COMMIT;"
            )
        except sqlite3.Error:
            connection.rollback()
            raise
