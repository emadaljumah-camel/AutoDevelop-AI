import logging
from pathlib import Path

import pytest

from autodevelop.logging_config import configure_logging


def test_configure_logging_writes_to_configured_file(tmp_path: Path) -> None:
    log_path = tmp_path / "nested" / "autodevelop.log"
    configure_logging(log_path, "INFO")

    logging.getLogger("autodevelop.test").info("logging is configured")
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert "logging is configured" in log_path.read_text(encoding="utf-8")


def test_configure_logging_rejects_unknown_level(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported log level"):
        configure_logging(tmp_path / "autodevelop.log", "verbose")
