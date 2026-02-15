# =============================================================================
# 模块: common/markdown.py
# 功能: Markdown 格式导出工具模块
# 架构角色: 作为数据展示层的工具模块，负责将文章数据渲染为结构化的 Markdown 文档。
#   被以下场景调用：
#   1. 用户订阅文章的 Markdown 导出
#   2. 每日摘要（Daily Digest）生成
#   3. 邮件通知中的内容格式化
#
# 设计决策:
#   - 所有渲染函数接收字典格式的文章数据，与 ORM 模型解耦
#   - 支持按来源分组展示（arXiv、RSS、微信公众号等）
#   - 中文标签和分类名称（面向中文用户群体）
#   - 文本清洗：移除 HTML 标签、反转义 HTML 实体、规范化空白符
#   - 可配置的摘要截断长度，适应不同输出场景
# =============================================================================
"""Markdown export utilities for ResearchPulse v2."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def clean_text(text: str) -> str:
    """Clean text for markdown output.

    清洗文本以适合 Markdown 输出。
    处理流程：移除 HTML 标签 -> 反转义 HTML 实体 -> 规范化空白符。

    Args:
        text: Raw text which may contain HTML tags/entities.

    Returns:
        str: Cleaned plain text.
    """
    if not text:
        return ""
    # 移除所有 HTML 标签，替换为空格
    text = re.sub(r"<[^>]+>", " ", text)
    # 反转义常见 HTML 实体
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    # 将连续空白符合并为单个空格
    text = " ".join(text.split())
    return text.strip()


def truncate_text(text: str, max_len: int = 0) -> str:
    """Truncate text if ``max_len`` is positive.

    截断文本到指定长度。max_len <= 0 时不截断。
    截断时在末尾添加省略号 "..."。

    Args:
        text: Text to truncate.
        max_len: Maximum length; non-positive disables truncation.

    Returns:
        str: Truncated text (possibly with ellipsis).
    """
    if max_len <= 0 or len(text) <= max_len:
        return text
    # 预留 3 个字符给省略号 "..."
    return text[:max_len - 3].rstrip() + "..."


def format_datetime(dt: Optional[datetime]) -> str:
    """Format datetime for display.

    将 datetime 对象格式化为可读的字符串。
    支持传入字符串（直接返回）或 None（返回空字符串）。

    Args:
        dt: Datetime, string, or None.

    Returns:
        str: Formatted datetime string.
    """
    if not dt:
        return ""
    # 兼容已经是字符串的情况
    if isinstance(dt, str):
        return dt
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def render_article_markdown(
    article: Dict[str, Any],
    include_abstract: bool = True,
    abstract_max_len: int = 0,
) -> str:
    """Render a single article to markdown.

    将单篇文章数据渲染为 Markdown 格式。
    包含标题（带链接）、元信息、标签、摘要、AI 总结等部分。
    arXiv 论文还额外显示 PDF 下载链接和翻译链接。

    Args:
        article: Article data dictionary.
        include_abstract: Whether to include abstract.
        abstract_max_len: Max abstract length (0 = no truncation).

    Returns:
        str: Markdown-formatted article content.
    """
    lines = []

    # 标题作为二级标题，带超链接
    title = clean_text(article.get("title", ""))
    if title:
        lines.append(f"## [{title}]({article.get('url', '')})")
        lines.append("")

    # 元信息区域
    meta = []

    # 作者
    author = clean_text(article.get("author", ""))
    if author:
        meta.append(f"**作者**: {author}")

    # 来源类型
    source_type = article.get("source_type", "")
    if source_type:
        meta.append(f"**来源**: {source_type.upper()}")

    # 分类
    category = article.get("category", "")
    if category:
        meta.append(f"**分类**: {category}")

    # 发布时间
    publish_time = article.get("publish_time")
    if publish_time:
        meta.append(f"**发布时间**: {format_datetime(publish_time)}")

    # arXiv 论文特有的元信息
    if source_type == "arxiv":
        arxiv_id = article.get("arxiv_id", "")
        if arxiv_id:
            meta.append(f"**arXiv ID**: [{arxiv_id}](https://arxiv.org/abs/{arxiv_id})")

        primary_cat = article.get("arxiv_primary_category", "")
        if primary_cat:
            meta.append(f"**主类目**: {primary_cat}")

        updated_time = article.get("arxiv_updated_time")
        if updated_time:
            meta.append(f"**更新时间**: {format_datetime(updated_time)}")

        # PDF 下载链接
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else ""
        if pdf_url:
            meta.append(f"**PDF**: [下载]({pdf_url})")

        # 中英对照翻译链接
        if arxiv_id:
            meta.append(f"**翻译**: [中英对照](https://hjfy.top/arxiv/{arxiv_id})")

    if meta:
        lines.extend(meta)
        lines.append("")

    # 标签（最多显示 10 个，用行内代码格式）
    tags = article.get("tags", [])
    if tags:
        tag_str = " ".join([f"`{clean_text(t)}`" for t in tags[:10]])
        lines.append(f"**标签**: {tag_str}")
        lines.append("")

    # 摘要/简介
    if include_abstract:
        summary = clean_text(article.get("summary", ""))
        if summary:
            summary = truncate_text(summary, abstract_max_len)
            lines.append("### 摘要")
            lines.append("")
            lines.append(summary)
            lines.append("")

    # AI 生成的内容总结
    content_summary = article.get("content_summary")
    if content_summary:
        lines.append("### 总结")
        lines.append("")
        lines.append(content_summary)
        lines.append("")

    # 文章间的分隔线
    lines.append("---")
    lines.append("")

    return "\n".join(lines)


def render_articles_markdown(
    articles: List[Dict[str, Any]],
    title: str = "文章列表",
    date: Optional[str] = None,
    include_abstract: bool = True,
    abstract_max_len: int = 0,
) -> str:
    """Render multiple articles to a single markdown document.

    将多篇文章渲染为一个完整的 Markdown 文档。
    包含文档标题、日期、文章数量、目录和详细内容。

    Args:
        articles: List of article data dictionaries.
        title: Document title.
        date: Optional date string.
        include_abstract: Whether to include abstracts.
        abstract_max_len: Max abstract length.

    Returns:
        str: Full markdown document content.
    """
    lines = []

    # 文档头部
    lines.append(f"# {title}")
    lines.append("")

    if date:
        lines.append(f"**日期**: {date}")
        lines.append("")

    lines.append(f"**文章数量**: {len(articles)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 目录区域：列出所有文章标题（截断到 50 个字符）
    lines.append("## 目录")
    lines.append("")
    for i, article in enumerate(articles, 1):
        title = clean_text(article.get("title", ""))[:50]
        source = article.get("source_type", "").upper()
        lines.append(f"{i}. [{title}...] - {source}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 文章详情区域
    lines.append("## 文章详情")
    lines.append("")

    for article in articles:
        md = render_article_markdown(
            article,
            include_abstract=include_abstract,
            abstract_max_len=abstract_max_len,
        )
        lines.append(md)

    return "\n".join(lines)


def render_articles_by_source(
    articles: List[Dict[str, Any]],
    date: Optional[str] = None,
    include_abstract: bool = True,
    abstract_max_len: int = 0,
) -> str:
    """Render articles grouped by source type.

    按来源类型分组渲染文章。
    先显示各来源的统计信息，然后按来源分组展示文章详情。

    Args:
        articles: List of article data dictionaries.
        date: Optional date string.
        include_abstract: Whether to include abstracts.
        abstract_max_len: Max abstract length.

    Returns:
        str: Grouped markdown content.
    """
    # 按来源类型分组
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for article in articles:
        source = article.get("source_type", "unknown")
        if source not in groups:
            groups[source] = []
        groups[source].append(article)

    lines = []

    # 文档头部
    lines.append("# 学术资讯聚合")
    lines.append("")

    if date:
        lines.append(f"**日期**: {date}")
        lines.append("")

    lines.append(f"**总文章数**: {len(articles)}")
    lines.append("")

    # 来源统计区域
    lines.append("## 来源统计")
    lines.append("")
    for source, items in sorted(groups.items()):
        lines.append(f"- **{source.upper()}**: {len(items)} 篇")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 按来源分组展示文章
    for source in sorted(groups.keys()):
        items = groups[source]
        # 将英文来源名称映射为中文展示名称
        source_title = source.upper()
        if source == "arxiv":
            source_title = "arXiv 论文"
        elif source == "rss":
            source_title = "RSS 文章"
        elif source == "wechat":
            source_title = "微信公众号"

        lines.append(f"## {source_title} ({len(items)} 篇)")
        lines.append("")

        for article in items:
            md = render_article_markdown(
                article,
                include_abstract=include_abstract,
                abstract_max_len=abstract_max_len,
            )
            lines.append(md)

    return "\n".join(lines)


def save_markdown(content: str, filepath: Path) -> None:
    """Save markdown content to file.

    将 Markdown 内容保存到文件。
    自动创建父目录（如果不存在）。

    Args:
        content: Markdown content.
        filepath: Output file path.

    Side Effects:
        - Creates parent directories if missing.
        - Writes UTF-8 content to disk.
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content, encoding="utf-8")
    logger.info(f"Markdown saved to {filepath}")


def export_user_subscription_markdown(
    articles: List[Dict[str, Any]],
    username: str,
    date: Optional[str] = None,
    output_dir: Path = Path("./data/exports"),
) -> Path:
    """Export user's subscribed articles to markdown.

    导出用户订阅的文章为 Markdown 文件。
    文件名格式：{日期}_{用户名}.md

    Args:
        articles: List of article data dictionaries.
        username: Username used in filename.
        date: Optional date string; defaults to current UTC date.
        output_dir: Output directory path.

    Returns:
        Path: Exported file path.
    """
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 文件名安全处理：将非字母数字和连字符的字符替换为下划线
    safe_username = re.sub(r'[^\w\-]', '_', username)
    filename = f"{date}_{safe_username}.md"
    filepath = output_dir / filename

    # 使用按来源分组的渲染方式
    content = render_articles_by_source(
        articles,
        date=date,
        include_abstract=True,
        abstract_max_len=500,
    )

    # 添加文档尾部生成信息
    content += f"\n\n---\n\n*Generated by ResearchPulse v2 at {datetime.now(timezone.utc).isoformat()}*\n"

    save_markdown(content, filepath)
    return filepath


def export_daily_digest_markdown(
    articles: List[Dict[str, Any]],
    date: Optional[str] = None,
    output_dir: Path = Path("./data/exports"),
) -> Path:
    """Export daily digest to markdown.

    导出每日摘要为 Markdown 文件。
    文件名格式：{日期}_digest.md

    Args:
        articles: List of article data dictionaries.
        date: Optional date string; defaults to current UTC date.
        output_dir: Output directory path.

    Returns:
        Path: Exported file path.
    """
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    filename = f"{date}_digest.md"
    filepath = output_dir / filename

    content = render_articles_by_source(
        articles,
        date=date,
        include_abstract=True,
        abstract_max_len=500,
    )

    # 添加文档尾部生成信息
    content += f"\n\n---\n\n*Generated by ResearchPulse v2 at {datetime.now(timezone.utc).isoformat()}*\n"

    save_markdown(content, filepath)
    return filepath
