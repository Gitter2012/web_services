"""Markdown export utilities for ResearchPulse v2."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def clean_text(text: str) -> str:
    """Clean text for markdown output."""
    if not text:
        return ""
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Unescape HTML entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    # Normalize whitespace
    text = " ".join(text.split())
    return text.strip()


def truncate_text(text: str, max_len: int = 0) -> str:
    """Truncate text if max_len > 0."""
    if max_len <= 0 or len(text) <= max_len:
        return text
    return text[:max_len - 3].rstrip() + "..."


def format_datetime(dt: Optional[datetime]) -> str:
    """Format datetime for display."""
    if not dt:
        return ""
    if isinstance(dt, str):
        return dt
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def render_article_markdown(
    article: Dict[str, Any],
    include_abstract: bool = True,
    abstract_max_len: int = 0,
) -> str:
    """Render a single article to markdown."""
    lines = []

    # Title as heading
    title = clean_text(article.get("title", ""))
    if title:
        lines.append(f"## [{title}]({article.get('url', '')})")
        lines.append("")

    # Meta information
    meta = []

    # Author
    author = clean_text(article.get("author", ""))
    if author:
        meta.append(f"**作者**: {author}")

    # Source type
    source_type = article.get("source_type", "")
    if source_type:
        meta.append(f"**来源**: {source_type.upper()}")

    # Category
    category = article.get("category", "")
    if category:
        meta.append(f"**分类**: {category}")

    # Publish time
    publish_time = article.get("publish_time")
    if publish_time:
        meta.append(f"**发布时间**: {format_datetime(publish_time)}")

    # ArXiv specific
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

        # PDF link
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else ""
        if pdf_url:
            meta.append(f"**PDF**: [下载]({pdf_url})")

        # Translation link
        if arxiv_id:
            meta.append(f"**翻译**: [中英对照](https://hjfy.top/arxiv/{arxiv_id})")

    if meta:
        lines.extend(meta)
        lines.append("")

    # Tags
    tags = article.get("tags", [])
    if tags:
        tag_str = " ".join([f"`{clean_text(t)}`" for t in tags[:10]])
        lines.append(f"**标签**: {tag_str}")
        lines.append("")

    # Abstract/Summary
    if include_abstract:
        summary = clean_text(article.get("summary", ""))
        if summary:
            summary = truncate_text(summary, abstract_max_len)
            lines.append("### 摘要")
            lines.append("")
            lines.append(summary)
            lines.append("")

    # Content summary (AI-generated)
    content_summary = article.get("content_summary")
    if content_summary:
        lines.append("### 总结")
        lines.append("")
        lines.append(content_summary)
        lines.append("")

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
    """Render multiple articles to a single markdown document."""
    lines = []

    # Document header
    lines.append(f"# {title}")
    lines.append("")

    if date:
        lines.append(f"**日期**: {date}")
        lines.append("")

    lines.append(f"**文章数量**: {len(articles)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Table of contents
    lines.append("## 目录")
    lines.append("")
    for i, article in enumerate(articles, 1):
        title = clean_text(article.get("title", ""))[:50]
        source = article.get("source_type", "").upper()
        lines.append(f"{i}. [{title}...] - {source}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Articles
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
    """Render articles grouped by source type."""
    # Group by source
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for article in articles:
        source = article.get("source_type", "unknown")
        if source not in groups:
            groups[source] = []
        groups[source].append(article)

    lines = []

    # Document header
    lines.append("# 学术资讯聚合")
    lines.append("")

    if date:
        lines.append(f"**日期**: {date}")
        lines.append("")

    lines.append(f"**总文章数**: {len(articles)}")
    lines.append("")

    # Summary by source
    lines.append("## 来源统计")
    lines.append("")
    for source, items in sorted(groups.items()):
        lines.append(f"- **{source.upper()}**: {len(items)} 篇")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Articles by source
    for source in sorted(groups.keys()):
        items = groups[source]
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
    """Save markdown content to file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content, encoding="utf-8")
    logger.info(f"Markdown saved to {filepath}")


def export_user_subscription_markdown(
    articles: List[Dict[str, Any]],
    username: str,
    date: Optional[str] = None,
    output_dir: Path = Path("./data/exports"),
) -> Path:
    """Export user's subscribed articles to markdown."""
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Create filename
    safe_username = re.sub(r'[^\w\-]', '_', username)
    filename = f"{date}_{safe_username}.md"
    filepath = output_dir / filename

    # Generate content
    content = render_articles_by_source(
        articles,
        date=date,
        include_abstract=True,
        abstract_max_len=500,
    )

    # Add footer
    content += f"\n\n---\n\n*Generated by ResearchPulse v2 at {datetime.now(timezone.utc).isoformat()}*\n"

    save_markdown(content, filepath)
    return filepath


def export_daily_digest_markdown(
    articles: List[Dict[str, Any]],
    date: Optional[str] = None,
    output_dir: Path = Path("./data/exports"),
) -> Path:
    """Export daily digest to markdown."""
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

    content += f"\n\n---\n\n*Generated by ResearchPulse v2 at {datetime.now(timezone.utc).isoformat()}*\n"

    save_markdown(content, filepath)
    return filepath
