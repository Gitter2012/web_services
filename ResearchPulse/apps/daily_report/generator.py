# =============================================================================
# 模块: apps/daily_report/generator.py
# 功能: 报告 Markdown 生成器
# 架构角色: 负责将文章数据转换为格式化的 Markdown 报告
# =============================================================================

"""Report Markdown generator."""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.crawler.models.article import Article

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generator for daily arXiv reports in Markdown format.

    每日 arXiv 报告 Markdown 生成器。

    生成的报告格式：
    # 【每日 arXiv】日期 分类领域新论文

    > 共收录 N 篇论文

    ---

    ## 📌 论文列表

    ### 1. 翻译后的标题
    **原文**: Original Title
    **作者**: Author1, Author2
    **链接**: https://arxiv.org/abs/xxxxx

    **摘要**:
    翻译后的中文摘要...

    ---
    """

    def generate(
        self,
        report_date: date,
        category: str,
        category_name: str,
        articles: list[Article],
        source_type: str = "arxiv",
    ) -> str:
        """Generate a Markdown report.

        生成 Markdown 格式的报告。

        Args:
            report_date: Report date.
            category: Category code.
            category_name: Chinese name of the category.
            articles: List of articles to include.
            source_type: Data source type (arxiv, hackernews, reddit, weibo, rss).

        Returns:
            Markdown formatted report string.
        """
        # 根据数据源生成不同的报告头部
        date_str = report_date.strftime("%Y年%m月%d日")

        if source_type == "arxiv":
            header = f"# 【每日 arXiv】{date_str} {category_name}领域新论文"
            stats_item = "篇论文"
            source_label = "arXiv.org"
        elif source_type == "hackernews":
            header = f"# 【Hacker News】{date_str} 热门技术话题"
            stats_item = "条热门话题"
            source_label = "Hacker News"
        elif source_type == "reddit":
            header = f"# 【Reddit】{date_str} 热门讨论"
            stats_item = "条热门讨论"
            source_label = "Reddit"
        elif source_type == "weibo":
            header = f"# 【微博热搜】{date_str} 热点话题"
            stats_item = "条热搜"
            source_label = "微博"
        elif source_type == "rss":
            header = f"# 【RSS 订阅】{date_str} {category_name}精选内容"
            stats_item = "篇内容"
            source_label = "RSS 订阅"
        else:
            header = f"# 【{category_name}】{date_str} 精选内容"
            stats_item = "篇内容"
            source_label = source_type

        # 报告头部
        lines = [
            header,
            "",
            f"> 共收录 {len(articles)} {stats_item}",
            "",
            "---",
            "",
            "## 📌 内容列表",
            "",
        ]

        # 逐篇添加内容信息
        for idx, article in enumerate(articles, 1):
            article_md = self._format_article(idx, article, source_type)
            lines.append(article_md)

        # 报告尾部
        lines.extend([
            "",
            "---",
            "",
            "## 📊 统计信息",
            "",
            f"- 总计: {len(articles)} {stats_item}",
            f"- 分类: {category} ({category_name})",
            f"- 日期: {report_date.strftime('%Y-%m-%d')}",
            "",
            "---",
            "",
            "*由 ResearchPulse 自动生成*",
            f"*数据来源: {source_label}*",
        ])

        return "\n".join(lines)

    def _format_article(self, index: int, article: Article, source_type: str = "arxiv") -> str:
        """Format a single article.

        格式化单篇文章/内容。

        Args:
            index: Article index (1-based).
            article: Article to format.
            source_type: Data source type.

        Returns:
            Markdown formatted article string.
        """
        # 获取标题（优先使用翻译后的标题）
        title = article.translated_title or article.title or "无标题"
        original_title = article.title or ""

        # 获取作者/来源
        authors = article.author or "未知来源"
        if len(authors) > 100:
            authors = authors[:100] + "..."

        # 获取链接
        if source_type == "arxiv":
            url = article.url or f"https://arxiv.org/abs/{article.arxiv_id}" if article.arxiv_id else ""
            link_text = article.arxiv_id or "arXiv"
        else:
            url = article.url or ""
            link_text = "查看原文"

        # 获取摘要（优先使用翻译后的摘要）
        summary = article.content_summary or article.summary or "无摘要"
        # 截断过长的摘要
        if len(summary) > 500:
            summary = summary[:500] + "..."

        # 构建 Markdown
        lines = [
            f"### {index}. {title}",
        ]

        # 如果有翻译标题，显示原文（仅对 arXiv）
        if source_type == "arxiv" and article.translated_title and original_title:
            lines.append(f"**原文**: {original_title}")

        # 根据数据源显示不同字段
        if source_type == "arxiv":
            lines.append(f"**作者**: {authors}")
        else:
            lines.append(f"**来源**: {authors}")

        if url:
            lines.append(f"**链接**: [{link_text}]({url})")

        lines.extend([
            "",
            "**摘要**:",
            "",
            summary,
            "",
            "---",
            "",
        ])

        return "\n".join(lines)

    def generate_article_detail(self, article: Article) -> str:
        """Generate detailed Markdown for a single article.

        为单篇文章生成详细的 Markdown。

        Args:
            article: Article to format.

        Returns:
            Detailed Markdown string.
        """
        title = article.translated_title or article.title or "无标题"
        original_title = article.title or ""
        authors = article.author or "未知作者"
        url = article.url or f"https://arxiv.org/abs/{article.arxiv_id}" if article.arxiv_id else ""
        summary = article.content_summary or article.summary or "无摘要"

        lines = [
            f"# {title}",
            "",
        ]

        if article.translated_title and original_title:
            lines.append(f"**原文标题**: {original_title}")
            lines.append("")

        lines.append(f"**作者**: {authors}")
        lines.append("")

        if article.arxiv_id:
            lines.append(f"**arXiv ID**: {article.arxiv_id}")
            lines.append("")

        if url:
            lines.append(f"**链接**: {url}")
            lines.append("")

        lines.extend([
            "---",
            "",
            "## 摘要",
            "",
            summary,
            "",
        ])

        # 如果有 AI 分析结果
        if article.ai_summary:
            lines.extend([
                "---",
                "",
                "## AI 摘要",
                "",
                article.ai_summary,
                "",
            ])

        if article.one_liner:
            lines.extend([
                "**一句话总结**: " + article.one_liner,
                "",
            ])

        if article.key_points:
            lines.extend([
                "## 关键要点",
                "",
            ])
            for kp in article.key_points:
                if isinstance(kp, dict):
                    kp_type = kp.get("type", "")
                    kp_value = kp.get("value", "")
                    kp_impact = kp.get("impact", "")
                    lines.append(f"- **{kp_type}**: {kp_value}")
                    if kp_impact:
                        lines.append(f"  - 影响: {kp_impact}")
            lines.append("")

        return "\n".join(lines)

    def generate_aggregated_report(
        self,
        report_date: date,
        articles_by_source: dict[str, list[Article]],
        source_order: list[str],
    ) -> str:
        """Generate an aggregated Markdown report for all sources.

        生成聚合报告，将所有数据源的内容整合在一起。
        内容只包含原文标题和链接（超链接形式）。

        Args:
            report_date: Report date.
            articles_by_source: Dict mapping source_type to list of articles.
            source_order: List of source types in desired order.

        Returns:
            Markdown formatted aggregated report string.
        """
        date_str = report_date.strftime("%Y年%m月%d日")
        total_articles = sum(len(a) for a in articles_by_source.values())

        # 报告头部
        lines = [
            f"# 【每日精选】{date_str} 信息聚合",
            "",
            f"> 共收录 {total_articles} 条内容",
            "",
            "---",
            "",
        ]

        # 数据源标签映射
        source_labels = {
            "arxiv": "arXiv 论文",
            "hackernews": "Hacker News",
            "reddit": "Reddit",
            "weibo": "微博热搜",
            "rss": "RSS 订阅",
        }

        # 按 source_order 顺序遍历数据源
        for source_type in source_order:
            articles = articles_by_source.get(source_type, [])
            if not articles:
                continue

            source_label = source_labels.get(source_type, source_type)
            lines.append(f"## {source_label}")
            lines.append("")

            for idx, article in enumerate(articles, 1):
                # 使用原文标题
                title = article.title or "无标题"
                url = article.url or ""

                if url:
                    lines.append(f"{idx}. [{title}]({url})")
                else:
                    lines.append(f"{idx}. {title}")

            lines.append("")

        # 报告尾部
        lines.extend([
            "---",
            "",
            "*由 ResearchPulse 自动生成*",
        ])

        return "\n".join(lines)
