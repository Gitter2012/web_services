# =============================================================================
# 模块: common/config_loader.py
# 功能: YAML 配置文件加载工具模块
# 架构角色: 作为配置基础设施层，为整个应用提供 YAML 配置读取能力。
#   支持两级配置合并机制：
#   - 项目级配置：/config/defaults.yaml（全局默认值）
#   - 应用级配置：/apps/<app>/config/defaults.yaml（应用专属配置）
#   项目级配置覆盖应用级配置（深度合并）。
#
# 配置优先级（从高到低）:
#   1. 环境变量（运行时覆盖）
#   2. .env 文件（敏感信息）
#   3. /config/defaults.yaml apps.<app> 段（项目级覆盖）
#   4. /apps/<app>/config/defaults.yaml（应用级默认值）
#   5. Python 代码硬编码默认值（兜底）
#
# 设计决策:
#   - 使用模块级变量 _config_cache 缓存主配置，避免重复读取文件
#   - deep_merge 实现字典深度合并，支持嵌套配置结构
#   - 日志配置使用 Python 标准库 logging.config.dictConfig
# =============================================================================
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

# 项目根目录：从 common/ 目录向上一级
BASE_DIR = Path(__file__).resolve().parents[1]
# 全局配置文件目录
CONFIG_DIR = BASE_DIR / "config"

# 模块级配置缓存，首次加载后不再重复读取文件
# 使用 None 作为未加载标志，空字典 {} 表示文件为空或不存在
_config_cache: Optional[Dict[str, Any]] = None


def load_yaml(file_path: Path) -> Dict[str, Any]:
    """Load a YAML file and return its contents as a dict.

    加载指定的 YAML 文件并返回解析后的字典。
    文件不存在时返回空字典，不抛出异常（容错设计）。

    Args:
        file_path: Path to the YAML file.
            YAML 文件的路径

    Returns:
        Dictionary containing the YAML contents, or empty dict if file doesn't exist.
            YAML 内容字典，文件不存在或为空时返回 {}
    """
    if not file_path.exists():
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        # yaml.safe_load 返回 None 时（空文件），用 or {} 兜底
        return yaml.safe_load(f) or {}


def get_config() -> Dict[str, Any]:
    """Load and cache the main config from /config/defaults.yaml.

    加载并缓存主配置文件。
    使用模块级变量 _config_cache 实现单次加载、全局共享。
    后续调用直接返回缓存，无需重复读取文件。

    Returns:
        Cached configuration dictionary.
            缓存的配置字典
    """
    global _config_cache
    if _config_cache is None:
        _config_cache = load_yaml(CONFIG_DIR / "defaults.yaml")
    return _config_cache


def get_project_config() -> Dict[str, Any]:
    """Get project-level config (app, logging, email sections).

    获取项目级配置，仅包含 app、logging、email 三个顶层段落。
    用于提取与具体应用模块无关的全局配置。

    Returns:
        Dictionary with project-level configuration sections.
            包含项目级配置段的字典
    """
    config = get_config()
    return {
        "app": config.get("app", {}),
        "logging": config.get("logging", {}),
        "email": config.get("email", {}),
    }


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries. Override values take precedence.

    深度合并两个字典，override 字典中的值优先。
    对于嵌套字典，递归合并而非简单替换，保留 base 中未被覆盖的键。
    对于非字典类型的值，override 直接替换 base 中的同名键。

    Args:
        base: Base dictionary (app-level defaults).
            基础字典（应用级默认值）
        override: Override dictionary (project-level config).
            覆盖字典（项目级配置）

    Returns:
        Merged dictionary with override values taking precedence.
            合并后的字典

    示例:
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        override = {"a": {"x": 10, "z": 30}}
        结果 = {"a": {"x": 10, "y": 2, "z": 30}, "b": 3}
    """
    result = base.copy()
    for key, value in override.items():
        # 只有当 base 和 override 中同一键的值都是字典时，才递归合并
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

    获取指定应用模块的合并配置。
    合并逻辑：应用级默认配置 + 项目级覆盖配置（项目级优先）。

    Args:
        app_name: Name of the app (e.g., 'arxiv_crawler', 'arxiv_ui').
            应用名称

    Returns:
        Dictionary with merged app-specific configuration.
            合并后的应用配置字典
    """
    # 第一步：加载应用自身的默认配置
    app_defaults_path = BASE_DIR / "apps" / app_name / "config" / "defaults.yaml"
    app_defaults = load_yaml(app_defaults_path)

    # 第二步：加载项目级配置中该应用的覆盖段
    project_config = get_config()
    project_app_config = project_config.get("apps", {}).get(app_name, {})

    # 第三步：深度合并，项目级配置覆盖应用级默认值
    return deep_merge(app_defaults, project_app_config)


def setup_logging_from_yaml(
    config_path: Optional[Path] = None,
    log_level_override: Optional[str] = None,
    log_file_override: Optional[Path] = None,
) -> None:
    """Configure logging from YAML with optional overrides.

    从 YAML 配置文件初始化 Python 日志系统。
    支持运行时覆盖日志级别和日志文件路径。
    如果 YAML 配置文件不存在，回退到 basicConfig 基础配置。

    Args:
        config_path: Path to logging YAML config. Defaults to /config/logging.yaml.
            日志配置文件路径，默认为 /config/logging.yaml
        log_level_override: Override the root logger level.
            覆盖根日志级别（如 "DEBUG", "INFO"）
        log_file_override: Override the file handler's filename.
            覆盖日志文件路径

    副作用:
        - 调用 logging.config.dictConfig 配置全局日志系统
        - 自动创建日志文件所在目录
    """
    config_path = config_path or CONFIG_DIR / "logging.yaml"
    config = load_yaml(config_path)

    if not config:
        # YAML 配置文件不存在或为空时，使用 basicConfig 作为回退
        logging.basicConfig(
            level=log_level_override or "INFO",
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )
        return

    # 应用运行时覆盖：日志级别
    if log_level_override:
        config.setdefault("root", {})["level"] = log_level_override.upper()

    # 应用运行时覆盖：日志文件路径
    if log_file_override:
        if "handlers" in config and "file" in config["handlers"]:
            config["handlers"]["file"]["filename"] = str(log_file_override)

    # 确保日志文件所在目录存在
    # 遍历所有 handler，检查是否有文件输出的 handler
    for handler in config.get("handlers", {}).values():
        if "filename" in handler:
            log_dir = Path(handler["filename"]).parent
            # 相对路径基于项目根目录解析
            if not log_dir.is_absolute():
                log_dir = BASE_DIR / log_dir
            # 递归创建目录（如果不存在）
            log_dir.mkdir(parents=True, exist_ok=True)
            # 将相对路径统一转换为绝对路径
            if not Path(handler["filename"]).is_absolute():
                handler["filename"] = str(BASE_DIR / handler["filename"])

    # 使用 Python 标准库的 dictConfig 初始化日志配置
    logging.config.dictConfig(config)


def clear_config_cache() -> None:
    """Clear the configuration cache. Useful for testing.

    清除配置缓存。主要用于测试场景，确保每次测试可以重新加载配置。

    副作用:
        - 将 _config_cache 重置为 None
    """
    global _config_cache
    _config_cache = None
