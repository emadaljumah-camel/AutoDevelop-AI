"""Application configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
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


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()
