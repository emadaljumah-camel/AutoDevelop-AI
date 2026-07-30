"""SQLite connection and migration boundary for personalized learning."""

import sqlite3
from pathlib import Path

from autodevelop.learning.migrations import migrate


class LearningDatabaseError(RuntimeError):
    """Sanitized learning database initialization failure."""


class LearningDatabase:
    """Create hardened short-lived SQLite connections."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def connect(self) -> sqlite3.Connection:
        connection: sqlite3.Connection | None = None
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                self._path,
                timeout=5.0,
                check_same_thread=False,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA journal_mode = WAL")
            return connection
        except (OSError, sqlite3.Error) as exc:
            if connection is not None:
                connection.close()
            raise LearningDatabaseError(
                "The learning database could not be opened."
            ) from exc

    def initialize(self) -> None:
        try:
            with self.connect() as connection:
                migrate(connection)
        except LearningDatabaseError:
            raise
        except sqlite3.Error as exc:
            raise LearningDatabaseError(
                "The learning database could not be initialized."
            ) from exc
