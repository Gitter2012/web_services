# =============================================================================
# 模块: common/logger.py
# 功能: 日志系统初始化的便捷封装
# 架构角色: 作为日志配置的入口，封装了 config_loader 模块中复杂的 YAML 日志配置逻辑，
#   为应用启动时提供简洁的日志初始化接口。
#   实际的日志配置加载逻辑委托给 config_loader.setup_logging_from_yaml。
#
# 设计决策:
#   - 采用薄封装（thin wrapper）模式，保持接口简洁
#   - 日志配置来自 /config/logging.yaml，支持：
#     - 每个应用模块独立的日志级别和处理器
#     - 文件轮转（Rotating File Handler）
#     - 自定义格式化器
# =============================================================================
"""Logging setup for ResearchPulse.

Uses YAML-based configuration from /config/logging.yaml with optional
runtime overrides for log level and log file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

# 从 config_loader 导入底层的 YAML 日志配置函数
from common.config_loader import setup_logging_from_yaml


def setup_logging(log_level: str = "INFO", log_file: Optional[Path] = None) -> None:
    """Setup logging using YAML config with optional overrides.

    Loads logging configuration from /config/logging.yaml which supports:
    - Per-app logging levels and handlers
    - Rotating file handlers
    - Custom formatters

    使用 YAML 配置文件初始化日志系统，可选覆盖日志级别和日志文件路径。
    该函数在 main.py 的模块级代码中被调用，是整个应用日志系统初始化的入口。

    Args:
        log_level: Override the root logger level (default: INFO).
            覆盖根日志记录器的级别，默认为 "INFO"。
            在 main.py 中传入的是 settings.debug 值（bool 类型，会被转为字符串）。
        log_file: Override the file handler's filename (optional).
            覆盖文件处理器的输出路径，None 表示使用 YAML 中的默认路径。

    副作用:
        - 配置全局 Python 日志系统
        - 可能创建日志文件目录
    """
    setup_logging_from_yaml(
        log_level_override=log_level,
        log_file_override=log_file,
    )
