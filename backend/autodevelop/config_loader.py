"""Load startup-only YAML model configuration and resolve source precedence."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError
from yaml.nodes import MappingNode, Node, SequenceNode

from autodevelop.config import Settings
from autodevelop.config_models import ModelsYamlConfig

APPLICATION_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODELS_CONFIG = Path("config") / "models.yaml"

_MODEL_SETTING_FIELDS = (
    "default_model",
    "local_base_url",
    "local_timeout_seconds",
    "local_response_format",
    "gemma_model",
    "qwen_model",
    "gpt_oss_model",
    "gemini_model",
    "gemini_timeout_seconds",
)
_DIAGNOSTIC_SETTING_FIELDS = (
    "log_invalid_model_response",
    "invalid_response_max_chars",
)
_LEARNING_SETTING_FIELDS = (
    "learning_enabled",
    "learning_db",
    "learning_min_samples",
    "learning_max_results",
    "learning_min_similarity",
    "learning_max_candidate_pool",
)


class ModelConfigurationError(ValueError):
    """Sanitized startup failure for model configuration."""


@dataclass(frozen=True)
class LoadedYamlConfiguration:
    config: ModelsYamlConfig
    path: Path
    loaded: bool
    explicitly_configured: bool


def resolve_models_config_path(
    config_file: str | Path | None,
    *,
    application_root: Path = APPLICATION_ROOT,
) -> tuple[Path, bool]:
    """Resolve default and explicit paths independently of the current directory."""

    explicitly_configured = config_file is not None
    candidate = (
        Path(config_file).expanduser()
        if explicitly_configured
        else DEFAULT_MODELS_CONFIG
    )
    if not candidate.is_absolute():
        candidate = application_root / candidate
    return candidate.resolve(strict=False), explicitly_configured


def _reject_duplicate_keys(node: Node) -> None:
    if isinstance(node, MappingNode):
        seen: set[tuple[str, str]] = set()
        for key_node, value_node in node.value:
            marker = (key_node.tag, key_node.value)
            if marker in seen:
                raise ModelConfigurationError(
                    "Duplicate YAML keys are not allowed."
                )
            seen.add(marker)
            _reject_duplicate_keys(key_node)
            _reject_duplicate_keys(value_node)
    elif isinstance(node, SequenceNode):
        for item in node.value:
            _reject_duplicate_keys(item)


def parse_models_yaml(content: str) -> ModelsYamlConfig:
    """Safely parse one YAML document into the typed configuration schema."""

    try:
        composed = yaml.compose(content, Loader=yaml.SafeLoader)
        if composed is not None:
            _reject_duplicate_keys(composed)
        raw = yaml.safe_load(content)
    except ModelConfigurationError:
        raise
    except yaml.YAMLError:
        raise ModelConfigurationError(
            "Model configuration YAML is malformed."
        ) from None
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise ModelConfigurationError(
            "Model configuration YAML root must be a mapping."
        )
    try:
        return ModelsYamlConfig.model_validate(dict(raw))
    except ValidationError as exc:
        locations = set()
        for error in exc.errors(include_input=False):
            location = [str(part) for part in error["loc"]]
            if error["type"] == "extra_forbidden" and location:
                location[-1] = "<unknown-key>"
            locations.add(".".join(location) or "<root>")
        context = ", ".join(sorted(locations))
        raise ModelConfigurationError(
            f"Model configuration validation failed at: {context}"
        ) from None


def load_models_yaml(
    config_file: str | Path | None,
    *,
    application_root: Path = APPLICATION_ROOT,
) -> LoadedYamlConfiguration:
    """Read and validate one optional startup configuration file."""

    path, explicitly_configured = resolve_models_config_path(
        config_file,
        application_root=application_root,
    )
    if not path.is_file():
        if explicitly_configured:
            raise ModelConfigurationError(
                "The explicitly configured model configuration file was not found."
            )
        return LoadedYamlConfiguration(
            config=ModelsYamlConfig(),
            path=path,
            loaded=False,
            explicitly_configured=False,
        )
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise ModelConfigurationError(
            "The model configuration file could not be read."
        ) from None
    return LoadedYamlConfiguration(
        config=parse_models_yaml(content),
        path=path,
        loaded=True,
        explicitly_configured=explicitly_configured,
    )


def _flatten_yaml_config(
    config: ModelsYamlConfig,
    *,
    application_root: Path,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if config.default_model is not None:
        values["default_model"] = config.default_model
    if config.providers is not None:
        if config.providers.local is not None:
            local = config.providers.local
            if local.base_url is not None:
                values["local_base_url"] = local.base_url
            if local.timeout_seconds is not None:
                values["local_timeout_seconds"] = local.timeout_seconds
            values["local_response_format"] = local.response_format
        if config.providers.gemini is not None:
            gemini = config.providers.gemini
            if gemini.timeout_seconds is not None:
                values["gemini_timeout_seconds"] = gemini.timeout_seconds
    field_names = {
        "gemma": "gemma_model",
        "qwen": "qwen_model",
        "gpt_oss": "gpt_oss_model",
        "gemini": "gemini_model",
    }
    for model_id, field_name in field_names.items():
        entry = config.models.get(model_id)
        if entry is not None and entry.provider_model_id is not None:
            values[field_name] = entry.provider_model_id
    learning = config.learning
    if learning is not None:
        database_path = Path(learning.database_path).expanduser()
        if not database_path.is_absolute():
            database_path = application_root / database_path
        values.update(
            {
                "learning_enabled": learning.enabled,
                "learning_db": database_path.resolve(strict=False),
                "learning_min_samples": learning.minimum_samples,
                "learning_max_results": learning.maximum_results,
                "learning_min_similarity": learning.minimum_similarity,
                "learning_max_candidate_pool": learning.maximum_candidate_pool,
            }
        )
    diagnostics = config.diagnostics
    if diagnostics is not None:
        values.update(
            {
                "log_invalid_model_response": (
                    diagnostics.log_invalid_model_response
                ),
                "invalid_response_max_chars": diagnostics.invalid_response_max_chars,
            }
        )
    return values


def load_settings(
    *,
    config_file: str | Path | None = None,
    application_root: Path = APPLICATION_ROOT,
    env_file: str | Path | None = ".env",
) -> Settings:
    """Resolve environment over YAML over built-in defaults."""

    environment_settings = Settings(_env_file=env_file)
    requested_file = (
        config_file if config_file is not None else environment_settings.config_file
    )
    loaded = load_models_yaml(
        requested_file,
        application_root=application_root,
    )
    yaml_values = _flatten_yaml_config(
        loaded.config,
        application_root=application_root,
    )
    environment_fields = environment_settings.model_fields_set
    resolved_values = {
        field_name: getattr(environment_settings, field_name)
        for field_name in type(environment_settings).model_fields
    }
    for field_name, value in yaml_values.items():
        if (
            field_name in _LEARNING_SETTING_FIELDS
            or field_name not in environment_fields
        ):
            resolved_values[field_name] = value
    settings = Settings(_env_file=None, **resolved_values)

    sources = {}
    for field_name in (
        _MODEL_SETTING_FIELDS
        + _LEARNING_SETTING_FIELDS
        + _DIAGNOSTIC_SETTING_FIELDS
    ):
        if field_name in environment_fields:
            sources[field_name] = "environment"
        elif field_name in yaml_values:
            sources[field_name] = "yaml"
        else:
            sources[field_name] = "built-in"
    settings.set_configuration_metadata(
        yaml_loaded=loaded.loaded,
        sources=sources,
    )
    return settings
