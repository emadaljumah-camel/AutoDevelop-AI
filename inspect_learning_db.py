import sqlite3
from pathlib import Path

path = Path(r"D:\Projects\AutoDevelop-AI\data\phase4-test.sqlite3")

if not path.exists():
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
