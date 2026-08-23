import argparse
import sqlite3
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent
DEFAULT_DATABASE_PATH = REPOSITORY_ROOT / "data" / "phase4-test.sqlite3"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect an AutoDevelop AI learning database.",
    )
    parser.add_argument(
        "database_path",
        nargs="?",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help=(
            "Database to inspect. Defaults to "
            "data/phase4-test.sqlite3 under the repository root."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    path: Path = _parse_args(argv).database_path
    if not path.is_file():
        raise SystemExit(f"Database not found: {path}")

    with sqlite3.connect(path) as connection:
        print("Tables:")
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' ORDER BY name"
        ):
            print(" ", row[0])

        print("\nSession counts:")
        for row in connection.execute(
            "SELECT state, COUNT(*) "
            "FROM learning_sessions GROUP BY state"
        ):
            print(row)

        print("\nFeedback counts:")
        for row in connection.execute(
            "SELECT usable, COUNT(*) "
            "FROM learning_feedback GROUP BY usable"
        ):
            print(row)


if __name__ == "__main__":
    main()
