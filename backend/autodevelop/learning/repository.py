"""Transactional persistence for learning baselines and feedback."""

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from autodevelop.learning.constants import SCHEMA_VERSION
from autodevelop.learning.database import LearningDatabase
from autodevelop.learning.models import RetrievalSample, StoredSession
from autodevelop.learning.schemas import (
    BaselineRequest,
    DevelopModeState,
    DevelopSettingDeltas,
    FeatureVector,
    safe_model_dump,
)
from autodevelop.models import DevelopSettings, UprightMode


class BaselineConflictError(RuntimeError):
    pass


class LearningSessionNotFoundError(LookupError):
    pass


class PhotoKeyMismatchError(ValueError):
    pass


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _load_json(value: str) -> dict[str, Any]:
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise ValueError("stored learning JSON is not an object")
    return decoded


def _load_json_list(value: str) -> list[Any]:
    decoded = json.loads(value)
    if not isinstance(decoded, list):
        raise ValueError("stored learning JSON is not an array")
    return decoded


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class LearningRepository:
    def __init__(
        self,
        database: LearningDatabase,
        maximum_candidate_pool: int,
    ) -> None:
        self._database = database
        self._maximum_candidate_pool = maximum_candidate_pool

    @staticmethod
    def baseline_fingerprint(request: BaselineRequest) -> str:
        canonical = _json(safe_model_dump(request))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def store_baseline(
        self,
        request: BaselineRequest,
        feature: FeatureVector | None,
    ) -> bool:
        fingerprint = self.baseline_fingerprint(request)
        session_id = str(request.session_id)
        now = _utc_now()
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT request_hash FROM learning_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if existing is not None:
                if existing["request_hash"] == fingerprint:
                    return False
                raise BaselineConflictError(
                    "The learning session identifier is already in use."
                )
            connection.execute(
                """
                INSERT INTO learning_sessions (
                    session_id, request_id, request_hash, photo_key, filename,
                    catalog_id, local_identifier, profile_id, stable_model_id,
                    resolved_model_id, created_at_utc,
                    baseline_captured_at_utc, original_settings_json,
                    recommendation_json, applied_baseline_json,
                    applied_upright_mode, applied_hdr_enabled,
                    baseline_upright_mode, ai_upright_mode,
                    baseline_hdr_enabled, ai_hdr_enabled,
                    baseline_hdr_max_value,
                    scene_hdr_candidate, scene_hdr_confidence,
                    base_scene_evidence_score, hdr_learning_bonus,
                    hdr_preference_bonus, combined_hdr_evidence_score,
                    hdr_decision_basis, hdr_decision_confidence,
                    scene_hdr_inconsistent, hdr_contraindications_json,
                    hdr_evidence_score, raw_hdr_recommended,
                    raw_hdr_confidence, validated_hdr_enabled,
                    validated_hdr_confidence, hdr_rejection_reason,
                    hdr_personalization_applied, hdr_learning_enable_rate,
                    exif_context_json, validation_summary_json, state,
                    schema_version
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    session_id,
                    str(request.request_id),
                    fingerprint,
                    request.photo_key,
                    request.filename,
                    request.catalog_id,
                    request.local_identifier,
                    request.profile,
                    request.model,
                    request.resolved_model,
                    now,
                    now,
                    _json(request.original_settings.model_dump(exclude_none=True)),
                    _json(request.recommendation.model_dump(exclude_none=True)),
                    _json(request.applied_baseline.model_dump(exclude_none=True)),
                    (
                        request.applied_modes.upright.value
                        if request.applied_modes.upright is not None
                        else None
                    ),
                    request.applied_modes.hdr_enabled,
                    (
                        request.original_modes.upright.value
                        if request.original_modes.upright is not None
                        else None
                    ),
                    (
                        request.recommendation_modes.upright.value
                        if request.recommendation_modes.upright is not None
                        else None
                    ),
                    request.original_modes.hdr_enabled,
                    request.recommendation_modes.hdr_enabled,
                    request.applied_modes.hdr_max_value,
                    (
                        request.hdr_decision.scene_hdr_candidate
                        if request.hdr_decision is not None
                        else None
                    ),
                    (
                        request.hdr_decision.scene_hdr_confidence
                        if request.hdr_decision is not None
                        else None
                    ),
                    (
                        request.hdr_decision.base_scene_evidence_score
                        if request.hdr_decision is not None
                        else None
                    ),
                    (
                        request.hdr_decision.learning_bonus
                        if request.hdr_decision is not None
                        else None
                    ),
                    (
                        request.hdr_decision.user_preference_bonus
                        if request.hdr_decision is not None
                        else None
                    ),
                    (
                        request.hdr_decision.combined_evidence_score
                        if request.hdr_decision is not None
                        else None
                    ),
                    (
                        request.hdr_decision.decision_basis
                        if request.hdr_decision is not None
                        else None
                    ),
                    (
                        request.hdr_decision.decision_confidence
                        if request.hdr_decision is not None
                        else None
                    ),
                    (
                        request.hdr_decision.scene_hdr_inconsistent
                        if request.hdr_decision is not None
                        else None
                    ),
                    (
                        _json(request.hdr_decision.contraindications)
                        if request.hdr_decision is not None
                        else None
                    ),
                    (
                        request.hdr_decision.hdr_evidence_score
                        if request.hdr_decision is not None
                        else None
                    ),
                    (
                        request.hdr_decision.raw_hdr_recommended
                        if request.hdr_decision is not None
                        else None
                    ),
                    (
                        request.hdr_decision.raw_hdr_confidence
                        if request.hdr_decision is not None
                        else None
                    ),
                    (
                        request.hdr_decision.validated_hdr_enabled
                        if request.hdr_decision is not None
                        else None
                    ),
                    (
                        request.hdr_decision.validated_hdr_confidence
                        if request.hdr_decision is not None
                        else None
                    ),
                    (
                        request.hdr_decision.hdr_rejection_reason
                        if request.hdr_decision is not None
                        else None
                    ),
                    (
                        request.hdr_decision.hdr_learning_applied
                        if request.hdr_decision is not None
                        else None
                    ),
                    (
                        request.hdr_decision.hdr_learning_enable_rate
                        if request.hdr_decision is not None
                        else None
                    ),
                    _json(safe_model_dump(request.exif_context)),
                    _json(safe_model_dump(request.validation_summary)),
                    "pending_feedback",
                    SCHEMA_VERSION,
                ),
            )
            if feature is not None:
                connection.execute(
                    """
                    INSERT INTO learning_features (
                        session_id, feature_type, feature_version, dimensions,
                        vector_json, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        feature.feature_type,
                        feature.feature_version,
                        feature.dimensions,
                        _json(feature.vector),
                        now,
                    ),
                )
        return True

    def get_session(self, session_id: UUID | str) -> StoredSession:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT session_id, request_id, photo_key, filename, profile_id,
                       stable_model_id, resolved_model_id, created_at_utc,
                       applied_baseline_json, applied_upright_mode,
                       applied_hdr_enabled, exif_context_json, state,
                       scene_hdr_candidate, scene_hdr_confidence,
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
                (str(session_id),),
            ).fetchone()
        if row is None:
            raise LearningSessionNotFoundError(
                "The learning session was not found."
            )
        return StoredSession(
            session_id=row["session_id"],
            request_id=row["request_id"],
            photo_key=row["photo_key"],
            filename=row["filename"],
            profile_id=row["profile_id"],
            stable_model_id=row["stable_model_id"],
            resolved_model_id=row["resolved_model_id"],
            created_at_utc=datetime.fromisoformat(row["created_at_utc"]),
            applied_baseline={
                key: float(value)
                for key, value in _load_json(
                    row["applied_baseline_json"]
                ).items()
            },
            applied_upright_mode=(
                UprightMode(request_mode)
                if (
                    request_mode := row["applied_upright_mode"]
                ) is not None
                else None
            ),
            applied_hdr_enabled=(
                bool(row["applied_hdr_enabled"])
                if row["applied_hdr_enabled"] is not None
                else None
            ),
            exif_context=_load_json(row["exif_context_json"]),
            state=row["state"],
            hdr_decision={
                "scene_hdr_candidate": (
                    bool(row["scene_hdr_candidate"])
                    if row["scene_hdr_candidate"] is not None
                    else None
                ),
                "scene_hdr_confidence": row["scene_hdr_confidence"],
                "base_scene_evidence_score": row[
                    "base_scene_evidence_score"
                ],
                "learning_bonus": row["hdr_learning_bonus"],
                "user_preference_bonus": row["hdr_preference_bonus"],
                "combined_evidence_score": row[
                    "combined_hdr_evidence_score"
                ],
                "decision_basis": row["hdr_decision_basis"],
                "decision_confidence": row["hdr_decision_confidence"],
                "scene_hdr_inconsistent": (
                    bool(row["scene_hdr_inconsistent"])
                    if row["scene_hdr_inconsistent"] is not None
                    else None
                ),
                "contraindications": (
                    _load_json_list(row["hdr_contraindications_json"])
                    if row["hdr_contraindications_json"] is not None
                    else None
                ),
                "hdr_evidence_score": row["hdr_evidence_score"],
                "raw_hdr_recommended": (
                    bool(row["raw_hdr_recommended"])
                    if row["raw_hdr_recommended"] is not None
                    else None
                ),
                "raw_hdr_confidence": row["raw_hdr_confidence"],
                "validated_hdr_enabled": (
                    bool(row["validated_hdr_enabled"])
                    if row["validated_hdr_enabled"] is not None
                    else None
                ),
                "validated_hdr_confidence": row[
                    "validated_hdr_confidence"
                ],
                "hdr_rejection_reason": row["hdr_rejection_reason"],
                "hdr_personalization_applied": (
                    bool(row["hdr_personalization_applied"])
                    if row["hdr_personalization_applied"] is not None
                    else None
                ),
                "hdr_learning_enable_rate": row[
                    "hdr_learning_enable_rate"
                ],
            },
        )

    def upsert_feedback(
        self,
        *,
        feedback_id: UUID,
        session_id: UUID,
        final_settings: DevelopSettings,
        delta: DevelopSettingDeltas,
        significant_delta: DevelopSettingDeltas,
        crop_delta: DevelopSettingDeltas,
        leveling_delta: DevelopSettingDeltas,
        final_modes: DevelopModeState,
        upright_changed: bool,
        hdr_changed: bool,
        accepted_without_change: bool,
        usable: bool,
        exclusion_reason: str | None,
    ) -> None:
        now = _utc_now()
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO learning_feedback (
                    feedback_id, session_id, captured_at_utc,
                    final_settings_json, delta_json, significant_delta_json,
                    crop_delta_json, crop_changed, leveling_delta_json,
                    leveling_changed, final_upright_mode,
                    final_hdr_enabled, upright_changed, upright_accepted,
                    hdr_changed, hdr_accepted,
                    accepted_without_change, usable,
                    exclusion_reason, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    feedback_id = excluded.feedback_id,
                    captured_at_utc = excluded.captured_at_utc,
                    final_settings_json = excluded.final_settings_json,
                    delta_json = excluded.delta_json,
                    significant_delta_json = excluded.significant_delta_json,
                    crop_delta_json = excluded.crop_delta_json,
                    crop_changed = excluded.crop_changed,
                    leveling_delta_json = excluded.leveling_delta_json,
                    leveling_changed = excluded.leveling_changed,
                    final_upright_mode = excluded.final_upright_mode,
                    final_hdr_enabled = excluded.final_hdr_enabled,
                    upright_changed = excluded.upright_changed,
                    upright_accepted = excluded.upright_accepted,
                    hdr_changed = excluded.hdr_changed,
                    hdr_accepted = excluded.hdr_accepted,
                    accepted_without_change = excluded.accepted_without_change,
                    usable = excluded.usable,
                    exclusion_reason = excluded.exclusion_reason,
                    schema_version = excluded.schema_version
                """,
                (
                    str(feedback_id),
                    str(session_id),
                    now,
                    _json(final_settings.model_dump(exclude_none=True)),
                    _json(delta.model_dump(exclude_none=True)),
                    _json(significant_delta.model_dump(exclude_none=True)),
                    _json(crop_delta.model_dump(exclude_none=True)),
                    bool(crop_delta.model_dump(exclude_none=True)),
                    _json(leveling_delta.model_dump(exclude_none=True)),
                    bool(leveling_delta.model_dump(exclude_none=True)),
                    (
                        final_modes.upright.value
                        if final_modes.upright is not None
                        else None
                    ),
                    final_modes.hdr_enabled,
                    upright_changed,
                    (
                        not upright_changed
                        if final_modes.upright is not None
                        else None
                    ),
                    hdr_changed,
                    (
                        not hdr_changed
                        if final_modes.hdr_enabled is not None
                        else None
                    ),
                    accepted_without_change,
                    usable,
                    exclusion_reason,
                    SCHEMA_VERSION,
                ),
            )
            connection.execute(
                """
                UPDATE learning_sessions
                SET state = 'feedback_captured'
                WHERE session_id = ?
                """,
                (str(session_id),),
            )

    def retrieval_candidates(self, profile_id: str) -> list[RetrievalSample]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT s.session_id, s.profile_id, s.exif_context_json,
                       f.captured_at_utc, f.significant_delta_json,
                       f.crop_delta_json, f.leveling_delta_json,
                       f.final_upright_mode, f.final_hdr_enabled,
                       f.accepted_without_change,
                       x.feature_type, x.feature_version, x.vector_json
                FROM learning_sessions AS s
                JOIN learning_feedback AS f ON f.session_id = s.session_id
                LEFT JOIN learning_features AS x ON x.session_id = s.session_id
                WHERE s.profile_id = ?
                  AND s.state = 'feedback_captured'
                  AND f.usable = 1
                ORDER BY f.captured_at_utc DESC, s.session_id ASC
                LIMIT ?
                """,
                (profile_id, self._maximum_candidate_pool),
            ).fetchall()
        return self._retrieval_samples(rows)

    def hdr_retrieval_candidates(self) -> list[RetrievalSample]:
        """Return usable HDR mode samples without a style-profile filter."""

        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT s.session_id, s.profile_id, s.exif_context_json,
                       f.captured_at_utc, f.significant_delta_json,
                       f.crop_delta_json, f.leveling_delta_json,
                       f.final_upright_mode, f.final_hdr_enabled,
                       f.accepted_without_change,
                       x.feature_type, x.feature_version, x.vector_json
                FROM learning_sessions AS s
                JOIN learning_feedback AS f ON f.session_id = s.session_id
                LEFT JOIN learning_features AS x ON x.session_id = s.session_id
                WHERE s.state = 'feedback_captured'
                  AND f.usable = 1
                  AND f.final_hdr_enabled IS NOT NULL
                ORDER BY f.captured_at_utc DESC, s.session_id ASC
                LIMIT ?
                """,
                (self._maximum_candidate_pool,),
            ).fetchall()
        return self._retrieval_samples(rows)

    @staticmethod
    def _retrieval_samples(rows) -> list[RetrievalSample]:
        samples = []
        for row in rows:
            vector_raw = (
                json.loads(row["vector_json"])
                if row["vector_json"] is not None
                else None
            )
            samples.append(
                RetrievalSample(
                    session_id=row["session_id"],
                    profile_id=row["profile_id"],
                    captured_at_utc=datetime.fromisoformat(
                        row["captured_at_utc"]
                    ),
                    significant_delta=DevelopSettingDeltas.model_validate(
                        _load_json(row["significant_delta_json"])
                    ).model_dump(exclude_none=True),
                    crop_delta=DevelopSettingDeltas.model_validate(
                        _load_json(row["crop_delta_json"])
                    ).model_dump(exclude_none=True),
                    leveling_delta=DevelopSettingDeltas.model_validate(
                        _load_json(row["leveling_delta_json"])
                    ).model_dump(exclude_none=True),
                    upright_mode=(
                        UprightMode(row["final_upright_mode"])
                        if row["final_upright_mode"] is not None
                        else None
                    ),
                    hdr_enabled=(
                        bool(row["final_hdr_enabled"])
                        if row["final_hdr_enabled"] is not None
                        else None
                    ),
                    accepted_without_change=bool(
                        row["accepted_without_change"]
                    ),
                    feature_type=row["feature_type"],
                    feature_version=row["feature_version"],
                    vector=(
                        tuple(float(value) for value in vector_raw)
                        if isinstance(vector_raw, list)
                        else None
                    ),
                    exif_context=_load_json(row["exif_context_json"]),
                )
            )
        return samples

    def status_counts(self) -> dict[str, int]:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE s.state = 'pending_feedback'
                    ) AS pending_sessions,
                    COUNT(f.id) AS feedback_samples,
                    COUNT(*) FILTER (WHERE f.usable = 1) AS usable_samples,
                    COUNT(*) FILTER (
                        WHERE f.accepted_without_change = 1
                    ) AS accepted_without_change,
                    COUNT(*) FILTER (
                        WHERE f.usable = 1 AND f.final_upright_mode IS NOT NULL
                    ) AS upright_usable_sample_count,
                    COUNT(*) FILTER (
                        WHERE f.upright_changed = 1
                    ) AS upright_change_count,
                    COUNT(*) FILTER (
                        WHERE f.upright_accepted = 1
                    ) AS upright_acceptance_count,
                    COUNT(*) FILTER (
                        WHERE f.usable = 1 AND f.final_hdr_enabled IS NOT NULL
                    ) AS hdr_usable_sample_count,
                    COUNT(*) FILTER (
                        WHERE f.hdr_changed = 1
                    ) AS hdr_change_count,
                    COUNT(*) FILTER (
                        WHERE f.hdr_accepted = 1
                    ) AS hdr_acceptance_count
                FROM learning_sessions AS s
                LEFT JOIN learning_feedback AS f ON f.session_id = s.session_id
                """
            ).fetchone()
        return {key: int(row[key] or 0) for key in row.keys()}

    def dismiss_session(self, session_id: UUID) -> bool:
        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE learning_sessions
                SET state = 'dismissed'
                WHERE session_id = ? AND state != 'dismissed'
                """,
                (str(session_id),),
            )
        return cursor.rowcount == 1

    def delete_all(self) -> int:
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM learning_sessions"
            ).fetchone()
            count = int(row["count"])
            connection.execute("DELETE FROM learning_sessions")
        return count
