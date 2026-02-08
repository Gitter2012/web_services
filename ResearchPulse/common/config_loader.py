"""YAML configuration loader for ResearchPulse.

This module provides utilities to load configuration from YAML files
with support for project-level and app-specific settings.

Configuration precedence (highest to lowest):
1. Environment variables (runtime override)
2. .env file (secrets)
3. /config/defaults.yaml apps.<app> (project-level overrides)
4. /apps/<app>/config/defaults.yaml (app-level defaults)
5. Hardcoded Python defaults (fallback)
"""

from __future__ import annotations

import logging
import logging.config
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = BASE_DIR / "config"

_config_cache: Optional[Dict[str, Any]] = None


def load_yaml(file_path: Path) -> Dict[str, Any]:
    """Load a YAML file and return its contents as a dict.

    Args:
        file_path: Path to the YAML file.

    Returns:
        Dictionary containing the YAML contents, or empty dict if file doesn't exist.
    """
    if not file_path.exists():
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_config() -> Dict[str, Any]:
    """Load and cache the main config from /config/defaults.yaml.

    Returns:
        Cached configuration dictionary.
    """
    global _config_cache
    if _config_cache is None:
        _config_cache = load_yaml(CONFIG_DIR / "defaults.yaml")
    return _config_cache


def get_project_config() -> Dict[str, Any]:
    """Get project-level config (app, logging, email sections).

    Returns:
        Dictionary with project-level configuration sections.
    """
    config = get_config()
    return {
        "app": config.get("app", {}),
        "logging": config.get("logging", {}),
        "email": config.get("email", {}),
    }


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries. Override values take precedence.

    Args:
        base: Base dictionary (app-level defaults).
        override: Override dictionary (project-level config).

    Returns:
        Merged dictionary with override values taking precedence.
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_app_config(app_name: str) -> Dict[str, Any]:
    """Get merged config for a specific app.

    Loads app-level defaults from /apps/<app>/config/defaults.yaml,
    then deep-merges with project-level overrides from
    /config/defaults.yaml apps.<app> section.

    Args:
        app_name: Name of the app (e.g., 'arxiv_crawler', 'arxiv_ui').

    Returns:
        Dictionary with merged app-specific configuration.
    """
    # 1. Load app-level defaults
    app_defaults_path = BASE_DIR / "apps" / app_name / "config" / "defaults.yaml"
    app_defaults = load_yaml(app_defaults_path)

    # 2. Load project-level overrides
    project_config = get_config()
    project_app_config = project_config.get("apps", {}).get(app_name, {})

    # 3. Deep merge: project overrides app defaults
    return deep_merge(app_defaults, project_app_config)


def setup_logging_from_yaml(
    config_path: Optional[Path] = None,
    log_level_override: Optional[str] = None,
    log_file_override: Optional[Path] = None,
) -> None:
    """Configure logging from YAML with optional overrides.

    Args:
        config_path: Path to logging YAML config. Defaults to /config/logging.yaml.
        log_level_override: Override the root logger level.
        log_file_override: Override the file handler's filename.
    """
    config_path = config_path or CONFIG_DIR / "logging.yaml"
    config = load_yaml(config_path)

    if not config:
        # Fallback to basic config if YAML not found
        logging.basicConfig(
            level=log_level_override or "INFO",
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )
        return

    # Apply overrides from environment/settings
    if log_level_override:
        config.setdefault("root", {})["level"] = log_level_override.upper()

    if log_file_override:
        if "handlers" in config and "file" in config["handlers"]:
            config["handlers"]["file"]["filename"] = str(log_file_override)

    # Ensure log directory exists for file handlers
    for handler in config.get("handlers", {}).values():
        if "filename" in handler:
            log_dir = Path(handler["filename"]).parent
            if not log_dir.is_absolute():
                log_dir = BASE_DIR / log_dir
            log_dir.mkdir(parents=True, exist_ok=True)
            # Update to absolute path
            if not Path(handler["filename"]).is_absolute():
                handler["filename"] = str(BASE_DIR / handler["filename"])

    logging.config.dictConfig(config)


def clear_config_cache() -> None:
    """Clear the configuration cache. Useful for testing."""
    global _config_cache
    _config_cache = None
