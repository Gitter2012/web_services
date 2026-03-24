# =============================================================================
# 模块: common/theme_filters.py
# 功能: 通用主题 Jinja2 过滤器
# 架构角色: 为邮件模板提供基于 ContentTheme 配置的动态颜色过滤器
# 设计决策:
#   1. 过滤器通过 register_theme_filters() 注册到 Jinja2 Environment
#   2. 支持 fallback 默认值，确保主题缺失颜色时不会报错
#   3. 过滤器函数通过闭包绑定到当前主题的 colors 配置
#   4. 提供 color / color_style / bg_color_style 三种常用过滤器
# =============================================================================

"""Jinja2 theme filters for dynamic color rendering in email templates."""

from __future__ import annotations

import logging
from typing import Any

from jinja2 import Environment

logger = logging.getLogger(__name__)

# 当主题中没有对应颜色时的全局 fallback 配置
# 与 WeChatHTMLFormatter.DEFAULT_COLORS 保持对齐
DEFAULT_COLORS: dict[str, str] = {
    "title_color": "#1a1a1a",
    "title_color_dark": "#1a1a2e",
    "subtitle_color": "#3e3e3e",
    "section_title_color": "#1e6bb8",
    "text_color": "#3e3e3e",
    "meta_color": "#888888",
    "link_color": "#576b95",
    "link_color_cyan": "#4ecdc4",
    "accent_color": "#1e6bb8",
    "border_color": "#e5e5e5",
    "bg_light": "#f7f7f7",
    "bg_email": "#f5f5f7",
    "bg_email_light": "#f0f2f5",
    "success_color": "#2ecc71",
    "error_color": "#e74c3c",
    "warning_color": "#f59e0b",
    "source_arxiv": "#b31b1b",
    "source_rss": "#f5a623",
    "source_wechat": "#07c160",
}


def build_theme_filters(theme_config: dict | None = None) -> dict[str, Any]:
    """Build Jinja2 filter functions bound to the given theme config.

    创建绑定到指定主题配置的 Jinja2 过滤器函数集。

    Args:
        theme_config: 来自 ContentTheme.config 的配置字典，格式为
                      ``{"colors": {...}, "typography": {...}}``。
                      如果为 None，使用 DEFAULT_COLORS。

    Returns:
        dict: 过滤器名称 -> 过滤器函数的映射，可注册到 Jinja2 Environment。

    Example::

        env = Environment(...)
        filters = build_theme_filters(theme.config)
        env.filters.update(filters)

        # 在模板中使用：
        # {{ "title_color_dark" | color }}         -> "#1a1a2e"
        # {{ "title_color_dark" | color_style }}   -> "color: #1a1a2e;"
        # {{ "bg_email" | bg_color_style }}        -> "background-color: #f5f5f7;"
    """
    # 合并主题颜色和默认颜色（主题优先）
    if theme_config:
        theme_colors = theme_config.get("colors", {})
        colors = {**DEFAULT_COLORS, **theme_colors}
    else:
        colors = dict(DEFAULT_COLORS)

    def color(name: str, fallback: str = "#000000") -> str:
        """Return the color value for the given color name.

        返回指定颜色名称对应的颜色值。

        Usage in template: ``{{ "title_color" | color }}``

        Args:
            name: 颜色名称（如 title_color、bg_email）。
            fallback: 颜色不存在时的默认值。

        Returns:
            颜色十六进制字符串，如 #1a1a2e。
        """
        return colors.get(name, fallback)

    def color_style(name: str, fallback: str = "#000000") -> str:
        """Return a CSS color style string.

        返回 CSS color 样式字符串。

        Usage in template: ``{{ "title_color" | color_style }}``

        Returns:
            CSS 样式字符串，如 ``color: #1a1a2e;``。
        """
        return f"color: {colors.get(name, fallback)};"

    def bg_color_style(name: str, fallback: str = "#ffffff") -> str:
        """Return a CSS background-color style string.

        返回 CSS background-color 样式字符串。

        Usage in template: ``{{ "bg_email" | bg_color_style }}``

        Returns:
            CSS 样式字符串，如 ``background-color: #f5f5f7;``。
        """
        return f"background-color: {colors.get(name, fallback)};"

    def border_color_style(name: str, side: str = "", fallback: str = "#e5e5e5") -> str:
        """Return a CSS border-color style string.

        返回 CSS border 颜色样式字符串，支持单侧边框。

        Usage in template: ``{{ "border_color" | border_color_style }}``
        or: ``{{ "accent_color" | border_color_style("left") }}``

        Args:
            name: 颜色名称。
            side: 边框方向（left/right/top/bottom），为空表示全边框。
            fallback: 颜色不存在时的默认值。

        Returns:
            CSS 样式字符串，如 ``border-left-color: #1e6bb8;``。
        """
        c = colors.get(name, fallback)
        if side:
            return f"border-{side}-color: {c};"
        return f"border-color: {c};"

    return {
        "color": color,
        "color_style": color_style,
        "bg_color_style": bg_color_style,
        "border_color_style": border_color_style,
    }


def register_theme_filters(
    env: Environment,
    theme_config: dict | None = None,
) -> None:
    """Register theme filters into a Jinja2 Environment.

    将主题过滤器注册到 Jinja2 Environment 中。

    Args:
        env: Jinja2 Environment 实例。
        theme_config: 主题配置字典。为 None 时使用默认颜色。

    Example::

        env = Environment(loader=FileSystemLoader(...))
        register_theme_filters(env, theme.config)
    """
    filters = build_theme_filters(theme_config)
    env.filters.update(filters)
    logger.debug(
        "Registered theme filters: %s (theme_config provided: %s)",
        list(filters.keys()),
        theme_config is not None,
    )
