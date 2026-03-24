# =============================================================================
# 模块: common/email_templates.py
# 功能: 邮件 HTML 模板渲染
# 架构角色: 加载 templates/email/ 下的 Jinja2 模板并渲染为 HTML 字符串，
#           供 notification_job.py 等模块生成邮件正文使用。
#
# 设计决策:
#   - 与 apps/ui/templates/ 分离：邮件模板有独立约束（内联 CSS、table 布局）
#   - 延迟初始化 Jinja2 Environment，避免 import-time 副作用
#   - autoescape=True 防止文章标题/摘要中的 HTML 注入
#   - 复用 common/markdown.py 的文本清洗和格式化函数作为 Jinja2 filter
# =============================================================================

"""Email HTML template rendering for ResearchPulse v2."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from common.markdown import clean_text, format_datetime
from common.theme_filters import register_theme_filters

logger = logging.getLogger(__name__)

# 模板目录：项目根目录下的 templates/email/
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"

# 模块级 Jinja2 环境（延迟初始化）
_env: Optional[Environment] = None


def _get_env(theme_config: dict | None = None) -> Environment:
    """Get or create the Jinja2 environment with theme filters.

    获取或创建 Jinja2 渲染环境，并注册主题过滤器。

    如果提供了 theme_config，则每次调用都会使用新的环境（带主题颜色）；
    如果没有提供，则返回带默认颜色的共享单例环境。

    Args:
        theme_config: 来自 ContentTheme.config 的配置字典，为 None 时使用默认颜色。

    Returns:
        Environment: Configured Jinja2 environment with theme filters.
    """
    global _env

    if theme_config is not None:
        # 有主题配置时，创建一个新的临时环境以注入主题颜色
        env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=select_autoescape(["html"]),
        )
        env.filters["clean"] = clean_text
        env.filters["format_dt"] = format_datetime
        register_theme_filters(env, theme_config)
        return env

    # 无主题配置时，复用带默认颜色的单例环境
    if _env is None:
        _env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=select_autoescape(["html"]),
        )
        # 注册自定义 filter，复用 common/markdown.py 的工具函数
        _env.filters["clean"] = clean_text
        _env.filters["format_dt"] = format_datetime
        # 注册默认主题过滤器（使用 DEFAULT_COLORS）
        register_theme_filters(_env, None)
    return _env


def render_user_digest(
    articles: List[Dict[str, Any]],
    date: str,
    url_prefix: str,
    theme_config: dict | None = None,
) -> str:
    """Render user subscription digest email as HTML.

    渲染用户订阅摘要邮件 HTML。按来源分组展示文章卡片。

    Args:
        articles: Article data dictionaries.
        date: Date string for the digest (e.g. "2025-02-19").
        url_prefix: Site URL prefix for links.
        theme_config: 来自 ContentTheme.config 的配置字典（可选）。
                      如果提供，模板中的 color/color_style 等过滤器将使用主题颜色。

    Returns:
        str: Rendered HTML string.
    """
    # 按来源类型分组
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for article in articles:
        source = article.get("source_type", "unknown")
        groups.setdefault(source, []).append(article)

    # 来源中文显示名
    source_names = {
        "arxiv": "arXiv 论文",
        "rss": "RSS 文章",
        "wechat": "微信公众号",
        "weibo": "微博热搜",
        "hackernews": "HackerNews",
        "reddit": "Reddit",
        "twitter": "Twitter",
    }

    env = _get_env(theme_config)
    template = env.get_template("user_digest.html")
    return template.render(
        articles=articles,
        groups=groups,
        source_names=source_names,
        date=date,
        url_prefix=url_prefix,
        total_count=len(articles),
    )


def render_admin_report(
    crawl_stats: Dict[str, Any],
    url_prefix: str,
    theme_config: dict | None = None,
) -> str:
    """Render admin crawl completion report email as HTML.

    渲染管理员爬取完成报告邮件 HTML。

    Args:
        crawl_stats: Crawl summary statistics dictionary.
        url_prefix: Site URL prefix for links.
        theme_config: 来自 ContentTheme.config 的配置字典（可选）。

    Returns:
        str: Rendered HTML string.
    """
    env = _get_env(theme_config)
    template = env.get_template("admin_report.html")
    return template.render(
        stats=crawl_stats.get("stats", {}),
        total=crawl_stats.get("total_articles", 0),
        errors=crawl_stats.get("errors", []),
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        url_prefix=url_prefix,
    )
