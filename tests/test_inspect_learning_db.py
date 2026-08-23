import sqlite3
from pathlib import Path

import pytest

import inspect_learning_db


def _create_diagnostic_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE learning_sessions (
                state TEXT NOT NULL
            );
            CREATE TABLE learning_feedback (
                usable INTEGER NOT NULL
            );
            INSERT INTO learning_sessions(state)
            VALUES ('pending'), ('pending'), ('complete');
            INSERT INTO learning_feedback(usable)
            VALUES (1), (1), (0);
            """
        )


def test_default_database_path_is_repository_relative_and_cwd_independent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    expected = (
        Path(inspect_learning_db.__file__).resolve().parent
        / "data"
        / "phase4-test.sqlite3"
    )

    monkeypatch.chdir(tmp_path)

    assert inspect_learning_db._parse_args([]).database_path == expected


def test_missing_database_fails_with_clear_error(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.sqlite3"

    with pytest.raises(SystemExit) as exc_info:
        inspect_learning_db.main([str(missing_path)])

    assert str(exc_info.value) == f"Database not found: {missing_path}"


def test_explicit_database_preserves_diagnostic_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "learning.sqlite3"
    _create_diagnostic_database(path)

    inspect_learning_db.main([str(path)])

    output = capsys.readouterr().out
    assert "Tables:\n  learning_feedback\n  learning_sessions\n" in output
    assert "\nSession counts:\n" in output
    assert "('complete', 1)" in output
    assert "('pending', 2)" in output
    assert "\nFeedback counts:\n" in output
    assert "(0, 1)" in output
    assert "(1, 2)" in output
