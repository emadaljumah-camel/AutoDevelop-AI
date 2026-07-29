"""Package-relative loading and caching for style profiles."""

import json
import re
from pathlib import Path

from pydantic import ValidationError

from autodevelop.profiles.models import StyleProfile

_PROFILE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class ProfileNotFoundError(LookupError):
    """Raised when a requested profile file does not exist."""


class ProfileValidationError(ValueError):
    """Raised when a profile file cannot be parsed or validated."""


class StyleProfileLoader:
    """Load validated JSON profiles with defensive cache semantics."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = (
            data_dir
            if data_dir is not None
            else Path(__file__).resolve().parent / "data"
        )
        self._cache: dict[str, StyleProfile] = {}

    @property
    def data_dir(self) -> Path:
        """Return the configured profile directory."""

        return self._data_dir

    def get_profile(self, profile_id: str) -> StyleProfile:
        """Return a validated profile or raise when it is unavailable."""

        if profile_id in self._cache:
            return self._copy_profile(self._cache[profile_id])
        if not _PROFILE_ID_PATTERN.fullmatch(profile_id):
            raise ProfileNotFoundError(f"Style profile not found: {profile_id}")

        path = self._data_dir / f"{profile_id}.json"
        if not path.is_file():
            raise ProfileNotFoundError(f"Style profile not found: {path}")

        profile = self._load_profile_file(path)
        self._cache[profile_id] = profile
        return self._copy_profile(profile)

    def list_profiles(self) -> list[StyleProfile]:
        """Return all profiles in deterministic alphabetical ID order."""

        return [
            self.get_profile(path.stem)
            for path in sorted(self._data_dir.glob("*.json"), key=lambda item: item.name)
        ]

    def reload_profiles(self) -> list[StyleProfile]:
        """Atomically reload every profile and replace the successful cache."""

        new_cache: dict[str, StyleProfile] = {}
        for path in sorted(self._data_dir.glob("*.json"), key=lambda item: item.name):
            profile = self._load_profile_file(path)
            new_cache[profile.id] = profile

        self._cache = new_cache
        return [
            self._copy_profile(new_cache[profile_id])
            for profile_id in sorted(new_cache)
        ]

    def _load_profile_file(self, path: Path) -> StyleProfile:
        try:
            raw_profile = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProfileValidationError(
                f"{path}: malformed JSON at line {exc.lineno}, column {exc.colno}: "
                f"{exc.msg}"
            ) from exc
        except OSError as exc:
            raise ProfileValidationError(f"{path}: could not read profile: {exc}") from exc

        try:
            profile = StyleProfile.model_validate(raw_profile)
        except ValidationError as exc:
            field_errors = "; ".join(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors()
            )
            raise ProfileValidationError(f"{path}: {field_errors}") from exc

        if profile.id != path.stem:
            raise ProfileValidationError(
                f"{path}: id: expected '{path.stem}', found '{profile.id}'"
            )
        return profile

    @staticmethod
    def _copy_profile(profile: StyleProfile) -> StyleProfile:
        return profile.model_copy(deep=True)
