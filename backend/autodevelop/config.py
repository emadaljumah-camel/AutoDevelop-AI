"""Application configuration."""

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    default_model: str = "gemma"
    local_base_url: str = "http://127.0.0.1:1234/v1"
    local_api_key: SecretStr = SecretStr("")
    local_timeout_seconds: float = Field(default=120.0, gt=0)
    gemma_model: str = "gemma-4-31b"
    qwen_model: str = "qwen_qwen3-vl-32b-instruct"
    gpt_oss_model: str = "gpt-oss"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: float = Field(default=120.0, gt=0)

    @field_validator(
        "default_model",
        "local_base_url",
        "gemma_model",
        "qwen_model",
        "gpt_oss_model",
        "gemini_model",
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
    )
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("local_base_url")
    @classmethod
    def validate_local_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("local_base_url must be a safe HTTP(S) URL")
        return value.rstrip("/")

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


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()
