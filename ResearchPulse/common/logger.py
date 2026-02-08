"""Logging setup for ResearchPulse.

Uses YAML-based configuration from /config/logging.yaml with optional
runtime overrides for log level and log file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from common.config_loader import setup_logging_from_yaml


def setup_logging(log_level: str = "INFO", log_file: Optional[Path] = None) -> None:
    """Setup logging using YAML config with optional overrides.

    Loads logging configuration from /config/logging.yaml which supports:
    - Per-app logging levels and handlers
    - Rotating file handlers
    - Custom formatters

    Args:
        log_level: Override the root logger level (default: INFO).
        log_file: Override the file handler's filename (optional).
    """
    setup_logging_from_yaml(
        log_level_override=log_level,
        log_file_override=log_file,
    )
