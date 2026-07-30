"""Application configuration."""

from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Mapping

from pydantic import Field, PrivateAttr, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from autodevelop.config_models import normalize_safe_http_url

ConfigurationSource = Literal["environment", "yaml", "built-in"]
_LEARNING_ENVIRONMENT_FIELDS = frozenset(
    {
        "learning_enabled",
        "learning_db",
        "learning_min_samples",
        "learning_max_results",
        "learning_min_similarity",
        "learning_max_candidate_pool",
    }
)


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and an optional .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AUTODEVELOP_",
        extra="ignore",
    )

    app_name: str = "AutoDevelop AI"
    host: str = "127.0.0.1"
    port: int = 8005
    api_prefix: str = "/autodevelop/v1"
    database_path: Path = Path("data/autodevelop.db")
    log_path: Path = Path("logs/autodevelop.log")
    temp_dir: Path = Path("temp")
    profiles_dir: Path = Path("profiles")
    log_level: str = "INFO"
    exiftool_path: str = "exiftool"
    exiftool_timeout_seconds: float = Field(default=30.0, gt=0)
    lm_studio_base_url: str = "http://127.0.0.1:1234/v1"
    lm_studio_model: str = ""
    lm_studio_timeout_seconds: float = Field(default=30.0, gt=0)
    lm_studio_max_tokens: int = Field(default=2048, gt=0)
    lm_studio_use_response_format: bool = True
    config_file: str | None = Field(default=None, exclude=True, repr=False)
    default_model: str = "gemma"
    local_base_url: str = "http://127.0.0.1:1234/v1"
    local_api_key: SecretStr = SecretStr("")
    local_timeout_seconds: float = Field(default=120.0, ge=10, le=600)
    gemma_model: str = "gemma-4-31b"
    qwen_model: str = "qwen_qwen3-vl-32b-instruct"
    gpt_oss_model: str = "gpt-oss"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: float = Field(default=120.0, ge=10, le=600)
    learning_enabled: bool = True
    learning_db: Path = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "autodevelop_learning.sqlite3"
    )
    learning_min_samples: int = Field(default=3, ge=1, le=100)
    learning_max_results: int = Field(default=5, ge=1, le=20)
    learning_min_similarity: float = Field(default=0.70, ge=0, le=1)
    learning_max_candidate_pool: int = Field(default=100, ge=1)

    _yaml_loaded: bool = PrivateAttr(default=False)
    _configuration_sources: dict[str, ConfigurationSource] = PrivateAttr(
        default_factory=dict
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Callable[[], dict[str, Any]],
        env_settings: Callable[[], dict[str, Any]],
        dotenv_settings: Callable[[], dict[str, Any]],
        file_secret_settings: Callable[[], dict[str, Any]],
    ) -> tuple[Callable[[], dict[str, Any]], ...]:
        """Exclude non-secret learning settings from environment sources."""

        def without_learning(
            source: Callable[[], dict[str, Any]],
        ) -> dict[str, Any]:
            values = source()
            return {
                key: value
                for key, value in values.items()
                if key not in _LEARNING_ENVIRONMENT_FIELDS
            }

        return (
            init_settings,
            lambda: without_learning(env_settings),
            lambda: without_learning(dotenv_settings),
            file_secret_settings,
        )

    @field_validator(
        "default_model",
        "local_base_url",
        "gemma_model",
        "qwen_model",
        "gpt_oss_model",
        "gemini_model",
        "config_file",
        mode="before",
    )
    @classmethod
    def normalize_required_text(cls, value: object) -> object:
        """Normalize configuration text while preserving strict non-blank checks."""

        return value.strip() if isinstance(value, str) else value

    @field_validator(
        "local_base_url",
        "gemma_model",
        "qwen_model",
        "gpt_oss_model",
        "gemini_model",
        "config_file",
    )
    @classmethod
    def reject_blank_text(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("local_base_url")
    @classmethod
    def validate_local_base_url(cls, value: str) -> str:
        return normalize_safe_http_url(value)

    @field_validator("default_model")
    @classmethod
    def validate_default_model(cls, value: str) -> str:
        from autodevelop.models.registry import get_model_definition

        definition = get_model_definition(value)
        if definition is None:
            raise ValueError("default_model is not registered")
        if not definition.selectable:
            raise ValueError("default_model is not selectable")
        return value

    @field_validator("learning_db")
    @classmethod
    def resolve_learning_database_path(cls, value: Path) -> Path:
        """Resolve relative overrides from the stable application root."""

        path = value.expanduser()
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        return path.resolve(strict=False)

    def set_configuration_metadata(
        self,
        *,
        yaml_loaded: bool,
        sources: Mapping[str, ConfigurationSource],
    ) -> None:
        """Attach safe startup-source metadata outside serialized settings."""

        self._yaml_loaded = yaml_loaded
        self._configuration_sources = dict(sources)

    @property
    def yaml_configuration_loaded(self) -> bool:
        return self._yaml_loaded

    @property
    def configuration_sources(
        self,
    ) -> Mapping[str, ConfigurationSource]:
        return MappingProxyType(self._configuration_sources)

    @property
    def environment_overrides_active(self) -> bool:
        return "environment" in self._configuration_sources.values()

    @property
    def configuration_source_summary(self) -> str:
        if self._yaml_loaded and self.environment_overrides_active:
            return "yaml+environment"
        if self._yaml_loaded:
            return "yaml"
        if self.environment_overrides_active:
            return "environment"
        return "built-in"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    from autodevelop.config_loader import load_settings

    return load_settings()
