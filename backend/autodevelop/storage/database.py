"""SQLite edit-session storage boundary."""

import sqlite3
from pathlib import Path


class EditSessionDatabase:
    """Own the SQLite connection and initial edit-session schema."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    @property
    def path(self) -> Path:
        """Return the configured database path."""

        return self._database_path

    def connect(self) -> sqlite3.Connection:
        """Open a SQLite connection with named-row access."""

        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        """Create the initial edit-session table when absent."""

        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS edit_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    status TEXT NOT NULL,
                    photo_count INTEGER NOT NULL DEFAULT 0,
                    style_profile TEXT
                )
                """
            )
