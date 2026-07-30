"""Immutable domain records used by the learning repository."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class StoredSession:
    session_id: str
    request_id: str
    photo_key: str
    filename: str
    profile_id: str
    stable_model_id: str
    resolved_model_id: str
    created_at_utc: datetime
    applied_baseline: dict[str, float]
    exif_context: dict[str, Any]
    state: str


@dataclass(frozen=True)
class RetrievalSample:
    session_id: str
    profile_id: str
    captured_at_utc: datetime
    significant_delta: dict[str, float]
    crop_delta: dict[str, float]
    leveling_delta: dict[str, float]
    accepted_without_change: bool
    feature_type: str | None
    feature_version: int | None
    vector: tuple[float, ...] | None
    exif_context: dict[str, Any]
    similarity: float = 0.0
