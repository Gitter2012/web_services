# =============================================================================
# 模块: apps/daily_digest/generator.py
# 功能: 每日精选日报 Markdown 渲染器
# 架构角色: 渲染层，使用 Jinja2 模板将精选结果渲染为 Markdown
# =============================================================================

"""Daily digest Markdown report generator using Jinja2."""

from __future__ import annotations

import logging
import pathlib
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Optional

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    _JINJA2_AVAILABLE = True
except ImportError:
    _JINJA2_AVAILABLE = False

if TYPE_CHECKING:
    from .selector import ScoredArticle

logger = logging.getLogger(__name__)

# Jinja2 模板目录
_TEMPLATE_DIR = pathlib.Path(__file__).parent / "templates"

# 分类 Emoji 映射
_CATEGORY_EMOJI: dict[str, str] = {
    "AI": "🤖",
    "编程": "💻",
    "研究": "🔬",
    "创业": "🚀",
    "金融": "📈",
    "设计": "🎨",
    "技术": "⚙️",
    "其他": "📌",
}

# 来源标签（用于报告头部的覆盖来源列表）
_SOURCE_LABELS: dict[str, str] = {
    "arxiv": "arXiv",
    "hackernews": "HN",
    "reddit": "Reddit",
    "weibo": "微博",
    "rss": "RSS",
    "cn_news": "中文新闻",
    "twitter": "Twitter",
    "wechat": "微信",
}


def _format_time(dt: Optional[datetime]) -> str:
    """格式化时间为 MM-DD HH:MM。"""
    if not dt:
        return "--"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%m-%d %H:%M")


def _category_emoji(category: str) -> str:
    """获取分类 Emoji。"""
    return _CATEGORY_EMOJI.get(category, "📌")


def _cluster_sources(sa: "ScoredArticle") -> str:
    """获取 cluster 内所有文章的来源标签拼接字符串。"""
    sources = set()
    src = sa.article.source_type or "unknown"
    sources.add(_SOURCE_LABELS.get(src, src.upper()))
    for rsa in sa.related_articles:
        rsrc = rsa.article.source_type or "unknown"
        sources.add(_SOURCE_LABELS.get(rsrc, rsrc.upper()))
    return " / ".join(sorted(sources))


def _truncate(text: str, length: int = 200) -> str:
    """截断文本。"""
    if not text:
        return ""
    if len(text) <= length:
        return text
    return text[:length] + "…"


class DigestGenerator:
    """每日精选日报 Markdown 渲染器。"""

    def __init__(self) -> None:
        if _JINJA2_AVAILABLE:
            self._env = Environment(
                loader=FileSystemLoader(str(_TEMPLATE_DIR)),
                autoescape=select_autoescape([]),  # Markdown 不需要 HTML 转义
                keep_trailing_newline=True,
            )
            # 注册自定义过滤器和函数
            self._env.filters["format_time"] = _format_time
            self._env.filters["truncate"] = _truncate
            self._env.globals["category_emoji"] = _category_emoji
            self._env.filters["cluster_sources"] = _cluster_sources
        else:
            self._env = None
            logger.warning("Jinja2 not available, using fallback generator")

    def generate(
        self,
        report_date: date,
        selected: list["ScoredArticle"],
        total_crawled: int,
        source_breakdown: dict[str, int],
        category_summaries: dict[str, Optional[str]],
        global_insight: Optional[str],
        digest_category: str = "all",
        digest_category_name: str = "每日精选",
    ) -> str:
        """渲染每日精选 Markdown 报告。

        Args:
            report_date: 报告日期。
            selected: 精选文章列表（已按 rank 排序）。
            total_crawled: 今日抓取总量。
            source_breakdown: 各来源文章数统计。
            category_summaries: 各分类 AI 小结。
            global_insight: 全局洞察段落。
            digest_category: 精选分类（"all" / "AI" / "金融" 等）。
            digest_category_name: 精选分类展示名称。

        Returns:
            str: 完整的 Markdown 报告内容。
        """
        if self._env is not None:
            return self._render_with_jinja2(
                report_date, selected, total_crawled, source_breakdown,
                category_summaries, global_insight,
                digest_category, digest_category_name,
            )
        return self._render_fallback(
            report_date, selected, total_crawled, source_breakdown,
            category_summaries, global_insight,
            digest_category, digest_category_name,
        )

    def _build_context(
        self,
        report_date: date,
        selected: list["ScoredArticle"],
        total_crawled: int,
        source_breakdown: dict[str, int],
        category_summaries: dict[str, Optional[str]],
        global_insight: Optional[str],
        digest_category: str = "all",
        digest_category_name: str = "每日精选",
    ) -> dict:
        """构建 Jinja2 模板上下文。"""
        # 按分类分组（保持 rank 顺序）
        categories_data: dict[str, list] = {}
        category_cluster_counts: dict[str, int] = {}
        hot_cluster_ids: set[int] = set()

        for sa in selected:
            cat = sa.display_category
            if cat not in categories_data:
                categories_data[cat] = []
                category_cluster_counts[cat] = 0
            categories_data[cat].append(sa)
            if sa.cluster_id is not None and sa.cluster_article_count >= 2:
                hot_cluster_ids.add(sa.cluster_id)
                category_cluster_counts[cat] = category_cluster_counts.get(cat, 0) + 1

        # 统计关联文章总数
        related_count = sum(len(sa.related_articles) for sa in selected)

        # 来源列表（去重）
        sources_seen: set[str] = set()
        for src in source_breakdown.keys():
            sources_seen.add(_SOURCE_LABELS.get(src, src.upper()))
        source_list = " / ".join(sorted(sources_seen))

        return {
            "report_date": report_date.strftime("%Y-%m-%d"),
            "digest_category": digest_category,
            "digest_category_name": digest_category_name,
            "total_crawled": total_crawled,
            "selected_count": len(selected),
            "hot_cluster_count": len(hot_cluster_ids),
            "source_list": source_list,
            "category_count": len(categories_data),
            "global_insight": global_insight,
            "categories_data": categories_data,
            "category_cluster_counts": category_cluster_counts,
            "category_summaries": category_summaries,
            "source_breakdown": source_breakdown,
            "related_count": related_count,
            "generated_at": datetime.now(timezone.utc).strftime("%H:%M"),
        }

    def _render_with_jinja2(
        self,
        report_date: date,
        selected: list["ScoredArticle"],
        total_crawled: int,
        source_breakdown: dict[str, int],
        category_summaries: dict[str, Optional[str]],
        global_insight: Optional[str],
        digest_category: str = "all",
        digest_category_name: str = "每日精选",
    ) -> str:
        """使用 Jinja2 模板渲染。"""
        try:
            template = self._env.get_template("daily_digest.md.j2")
            context = self._build_context(
                report_date, selected, total_crawled, source_breakdown,
                category_summaries, global_insight,
                digest_category, digest_category_name,
            )
            return template.render(**context)
        except Exception as e:
            logger.error("Jinja2 rendering failed: %s, using fallback", e)
            return self._render_fallback(
                report_date, selected, total_crawled, source_breakdown,
                category_summaries, global_insight,
                digest_category, digest_category_name,
            )

    def _render_fallback(
        self,
        report_date: date,
        selected: list["ScoredArticle"],
        total_crawled: int,
        source_breakdown: dict[str, int],
        category_summaries: dict[str, Optional[str]],
        global_insight: Optional[str],
        digest_category: str = "all",
        digest_category_name: str = "每日精选",
    ) -> str:
        """不依赖 Jinja2 的纯 Python 兜底渲染。"""
        date_str = report_date.strftime("%Y-%m-%d")
        lines: list[str] = []

        # 统计热点事件
        hot_cluster_ids: set[int] = set()
        for sa in selected:
            if sa.cluster_id is not None and sa.cluster_article_count >= 2:
                hot_cluster_ids.add(sa.cluster_id)

        sources_seen: set[str] = {_SOURCE_LABELS.get(s, s.upper()) for s in source_breakdown}
        source_list = " / ".join(sorted(sources_seen))
        related_count = sum(len(sa.related_articles) for sa in selected)

        lines += [
            f"# 📰 ResearchPulse {digest_category_name} · {date_str}",
            f"> 今日从 **{total_crawled}** 篇内容中精选 **{len(selected)}** 个重点 · 发现 **{len(hot_cluster_ids)}** 个热点事件",
            f"> 覆盖来源：{source_list}",
            "",
            "---",
            "",
            "## 🔭 今日洞察",
            "",
        ]

        if global_insight:
            lines.append(global_insight)
        else:
            lines.append("*今日精选已就绪。*")
        lines.extend(["", "---", ""])

        # 按分类分组
        categories_data: dict[str, list] = {}
        for sa in selected:
            cat = sa.display_category
            if cat not in categories_data:
                categories_data[cat] = []
            categories_data[cat].append(sa)

        for cat, items in categories_data.items():
            cluster_cnt = sum(
                1 for sa in items
                if sa.cluster_id is not None and sa.cluster_article_count >= 2
            )
            emoji = _category_emoji(cat)
            header = f"## {emoji} {cat}（{len(items)}篇"
            if cluster_cnt > 0:
                header += f" · {cluster_cnt}个热点"
            header += "）"
            lines.append(header)
            lines.append("")

            summary = category_summaries.get(cat)
            if summary:
                lines.append(f"> {summary}")
                lines.append("")

            for sa in items:
                title = _truncate(
                    sa.article.translated_title or sa.article.title or "无标题", 80
                )
                url = sa.article.url or "#"
                time_str = _format_time(sa.article.publish_time)
                src = (sa.article.source_type or "unknown").upper()

                if sa.cluster_id is not None and sa.cluster_article_count >= 2:
                    lines += [
                        f"### 🔥 {sa.rank}. {title}",
                        f"> 本话题共有 **{sa.cluster_article_count}** 篇报道（来自 {_cluster_sources(sa)}）",
                    ]
                    one_liner = sa.article.one_liner or ""
                    if one_liner:
                        lines.append(f"> **事件概述**：{_truncate(one_liner, 150)}")
                    lines += [
                        "",
                        f"**📌 代表报道**（综合评分 {sa.composite_score:.1f}）",
                        f"**来源** `{src}` · **时间** `{time_str}` · 🔗 [原文]({url})",
                    ]
                    summary_text = (
                        sa.article.content_summary
                        or sa.article.ai_summary
                        or sa.article.summary
                        or ""
                    )
                    if summary_text:
                        lines.append(f"> {_truncate(summary_text, 200)}")
                    if sa.related_articles:
                        lines += ["", "**🔗 相关报道**"]
                        for rsa in sa.related_articles:
                            rtitle = _truncate(
                                rsa.article.translated_title or rsa.article.title or "无标题", 60
                            )
                            rsrc = (rsa.article.source_type or "unknown").upper()
                            rurl = rsa.article.url or "#"
                            lines.append(
                                f"- `{rsrc}` [{rtitle}]({rurl}) — 评分 {rsa.composite_score:.1f}"
                            )
                else:
                    lines.append(f"### {sa.rank}. {title}")
                    lines.append(
                        f"**评分** `{sa.composite_score:.1f}/10` · **来源** `{src}` · **时间** `{time_str}` · 🔗 [原文]({url})"
                    )
                    one_liner = (
                        sa.article.one_liner
                        or sa.article.content_summary
                        or sa.article.ai_summary
                        or ""
                    )
                    if one_liner:
                        lines.append(f"> {_truncate(one_liner, 200)}")

                lines.extend(["", "---", ""])

        # 数据一览
        lines += [
            "## 📊 数据一览",
            "| 指标 | 数值 |",
            "|------|------|",
            f"| 抓取总量 | {total_crawled} 篇 |",
            f"| 热点事件数（≥2篇） | {len(hot_cluster_ids)} 个 |",
            f"| 精选排名位 | {len(selected)} |",
            f"| 附带关联报道 | {related_count} 篇 |",
        ]
        for src, cnt in source_breakdown.items():
            label = _SOURCE_LABELS.get(src, src)
            lines.append(f"| {label} | {cnt} 篇 |")

        generated_at = datetime.now(timezone.utc).strftime("%H:%M")
        lines += [
            "",
            f"*🤖 ResearchPulse AI 生成 · {date_str} {generated_at}*",
        ]

        return "\n".join(lines)
