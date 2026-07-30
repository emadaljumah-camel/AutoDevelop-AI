from pathlib import Path

import pytest
from pydantic import ValidationError

from autodevelop.config import Settings


def test_learning_defaults_are_typed_and_stable() -> None:
    settings = Settings(_env_file=None)

    assert settings.learning_enabled is True
    assert settings.learning_db.is_absolute()
    assert settings.learning_db.name == "autodevelop_learning.sqlite3"
    assert settings.learning_min_samples == 3
    assert settings.learning_max_results == 5
    assert settings.learning_min_similarity == 0.70
    assert settings.learning_max_candidate_pool == 100


def test_relative_learning_database_resolves_from_application_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(Path.home())

    settings = Settings(_env_file=None, learning_db=Path("data/custom.sqlite3"))

    assert settings.learning_db.is_absolute()
    assert settings.learning_db.parts[-2:] == ("data", "custom.sqlite3")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("learning_min_samples", 0),
        ("learning_max_results", 21),
        ("learning_min_similarity", -0.01),
        ("learning_min_similarity", 1.01),
        ("learning_max_candidate_pool", 0),
    ],
)
def test_invalid_learning_settings_are_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})
