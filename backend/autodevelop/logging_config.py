"""Logging configuration for the backend process."""

import logging
from logging.config import dictConfig
from pathlib import Path


def configure_logging(log_path: Path, level: str = "INFO") -> None:
    """Configure consistent console and UTF-8 file logging."""

    normalized_level = level.upper()
    if normalized_level not in logging.getLevelNamesMapping():
        raise ValueError(f"Unsupported log level: {level}")

    log_path.parent.mkdir(parents=True, exist_ok=True)
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "level": normalized_level,
                },
                "file": {
                    "class": "logging.FileHandler",
                    "encoding": "utf-8",
                    "filename": str(log_path),
                    "formatter": "standard",
                    "level": normalized_level,
                },
            },
            "root": {
                "handlers": ["console", "file"],
                "level": normalized_level,
            },
        }
    )
