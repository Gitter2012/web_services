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
    ) -> str:
        """Generate a Markdown report.

        生成 Markdown 格式的报告。

        Args:
            report_date: Report date.
            category: arXiv category code.
            category_name: Chinese name of the category.
            articles: List of articles to include.

        Returns:
            Markdown formatted report string.
        """
        # 报告头部
        lines = [
            f"# 【每日 arXiv】{report_date.strftime('%Y年%m月%d日')} {category_name}领域新论文",
            "",
            f"> 共收录 {len(articles)} 篇论文",
            "",
            "---",
            "",
            "## 📌 论文列表",
            "",
        ]

        # 逐篇添加论文信息
        for idx, article in enumerate(articles, 1):
            article_md = self._format_article(idx, article)
            lines.append(article_md)

        # 报告尾部
        lines.extend([
            "",
            "---",
            "",
            "## 📊 统计信息",
            "",
            f"- 总计: {len(articles)} 篇论文",
            f"- 分类: {category} ({category_name})",
            f"- 日期: {report_date.strftime('%Y-%m-%d')}",
            "",
            "---",
            "",
            "*由 ResearchPulse 自动生成*",
            "*数据来源: arXiv.org*",
        ])

        return "\n".join(lines)

    def _format_article(self, index: int, article: Article) -> str:
        """Format a single article.

        格式化单篇论文。

        Args:
            index: Article index (1-based).
            article: Article to format.

        Returns:
            Markdown formatted article string.
        """
        # 获取标题（优先使用翻译后的标题）
        title = article.translated_title or article.title or "无标题"
        original_title = article.title or ""

        # 获取作者
        authors = article.author or "未知作者"
        if len(authors) > 100:
            authors = authors[:100] + "..."

        # 获取链接
        url = article.url or f"https://arxiv.org/abs/{article.arxiv_id}" if article.arxiv_id else ""

        # 获取摘要（优先使用翻译后的摘要）
        summary = article.content_summary or article.summary or "无摘要"
        # 截断过长的摘要
        if len(summary) > 500:
            summary = summary[:500] + "..."

        # 构建 Markdown
        lines = [
            f"### {index}. {title}",
        ]

        # 如果有翻译标题，显示原文
        if article.translated_title and original_title:
            lines.append(f"**原文**: {original_title}")

        lines.append(f"**作者**: {authors}")

        if url:
            lines.append(f"**链接**: [{article.arxiv_id or 'arXiv'}]({url})")

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
