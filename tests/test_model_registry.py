from pathlib import Path

import pytest
from pydantic import ValidationError

from autodevelop.config import Settings
from autodevelop.models.registry import (
    DEFAULT_MODEL_ID,
    get_model_definition,
    list_model_definitions,
)


def test_registry_is_ordered_unique_and_copy_safe() -> None:
    definitions = list_model_definitions()
    assert [item.id for item in definitions] == [
        "gemma",
        "qwen",
        "gpt_oss",
        "gemini",
        "claude",
    ]
    assert len({item.id for item in definitions}) == 5
    assert len({item.display_name for item in definitions}) == 5
    assert len({item.sort_order for item in definitions}) == 5
    assert all(item.description for item in definitions)
    assert DEFAULT_MODEL_ID == "gemma"
    assert definitions[-1].availability == "future"
    assert definitions[-1].selectable is False
    with pytest.raises(ValidationError):
        definitions[0].id = "changed"  # type: ignore[misc]
    assert get_model_definition("gemma").id == "gemma"  # type: ignore[union-attr]
    assert get_model_definition("unknown") is None


def test_default_model_configuration_validation() -> None:
    assert Settings(_env_file=None).default_model == "gemma"
    with pytest.raises(ValidationError, match="not registered"):
        Settings(_env_file=None, default_model="unknown")
    with pytest.raises(ValidationError, match="not selectable"):
        Settings(_env_file=None, default_model="claude")
    assert Settings(_env_file=None, local_api_key="").local_api_key.get_secret_value() == ""
    assert Settings(_env_file=None, gemini_api_key="").gemini_api_key.get_secret_value() == ""


def test_lightroom_registry_mirrors_canonical_display_metadata() -> None:
    source = Path(
        "AutoDevelopAI.lrplugin/lib/ModelProfiles.lua"
    ).read_text(encoding="utf-8")
    for definition in list_model_definitions():
        assert f'id = "{definition.id}"' in source
        assert f'displayName = "{definition.display_name}"' in source
        assert f'provider = "{definition.provider}"' in source
        assert f'description = "{definition.description}"' in source
        assert f'availability = "{definition.availability_label}"' in source
