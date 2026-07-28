"""JSON-backed style profile repository."""

import json
from pathlib import Path
from typing import JsonValue

from pydantic import BaseModel


class StyleProfile(BaseModel):
    """A named collection of future editing preferences."""

    name: str
    description: str = ""
    settings: dict[str, JsonValue] = {}


class StyleProfileRepository:
    """Load style profiles from individual JSON files."""

    def __init__(self, profiles_dir: Path) -> None:
        self._profiles_dir = profiles_dir

    def list_profiles(self) -> list[StyleProfile]:
        """Load every valid profile file in filename order."""

        if not self._profiles_dir.exists():
            return []

        return [
            StyleProfile.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self._profiles_dir.glob("*.json"))
        ]

    def get_profile(self, profile_name: str) -> StyleProfile | None:
        """Load a profile by filename stem."""

        path = self._profiles_dir / f"{profile_name}.json"
        if not path.is_file():
            return None

        return StyleProfile.model_validate(json.loads(path.read_text(encoding="utf-8")))
