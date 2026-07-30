"""Bounded, expiring handoff of Develop features to baseline storage."""

from dataclasses import dataclass
from threading import Lock
from time import monotonic

from autodevelop.learning.schemas import FeatureVector


@dataclass(frozen=True)
class _CacheEntry:
    feature: FeatureVector | None
    expires_at: float


class FeatureHandoffCache:
    """Thread-safe cache keyed only by trusted request identifiers."""

    def __init__(self, *, maximum_entries: int = 500, ttl_seconds: int = 900) -> None:
        self._maximum_entries = maximum_entries
        self._ttl_seconds = ttl_seconds
        self._entries: dict[str, _CacheEntry] = {}
        self._lock = Lock()

    def put(self, request_id: str, feature: FeatureVector | None) -> None:
        now = monotonic()
        with self._lock:
            self._purge(now)
            if len(self._entries) >= self._maximum_entries:
                oldest = min(
                    self._entries,
                    key=lambda key: self._entries[key].expires_at,
                )
                self._entries.pop(oldest, None)
            self._entries[request_id] = _CacheEntry(
                feature=feature.model_copy(deep=True) if feature else None,
                expires_at=now + self._ttl_seconds,
            )

    def pop(self, request_id: str) -> FeatureVector | None:
        now = monotonic()
        with self._lock:
            self._purge(now)
            entry = self._entries.pop(request_id, None)
        if entry is None or entry.feature is None:
            return None
        return entry.feature.model_copy(deep=True)

    def _purge(self, now: float) -> None:
        expired = [
            key for key, entry in self._entries.items()
            if entry.expires_at <= now
        ]
        for key in expired:
            self._entries.pop(key, None)
