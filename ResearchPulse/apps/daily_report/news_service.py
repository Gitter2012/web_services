# =============================================================================
# 模块: apps/daily_report/news_service.py
# 功能: 独立的新闻报告生成服务，按国家/分类生成中英文新闻报告
# 架构角色: 业务逻辑层，复用 DailyReportService 的报告生成 + WeChat 推送逻辑
# 设计决策:
#   - 中文新闻: cn_news 类型文章 + cn_ 前缀 RSS 文章
#   - 英文新闻: en_ 前缀 RSS 文章
#   - 每种类别独立生成一份报告
# =============================================================================

"""News report generation service."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.crawler.models.article import Article
from apps.daily_report.models.daily_report import DailyReport
from apps.daily_report.generator import ReportGenerator
from apps.daily_report.formatters.wechat import WeChatFormatter
from core.database import get_session_factory
from common.feature_config import feature_config

logger = logging.getLogger(__name__)


class NewsReportService:
    """Independent news report generation service.

    独立的新闻报告生成服务，按国家/分类生成报告。

    报告类型:
    1. 中文新闻报告: cn_news 源 + cn_ 前缀 RSS 源的文章
    2. 英文新闻报告: en_ 前缀 RSS 源的文章
    """

    def __init__(self):
        self.generator = ReportGenerator()
        self.wechat_formatter = WeChatFormatter()

    async def _get_cn_news_articles(
        self,
        db: AsyncSession,
        report_date: date,
        max_articles: int = 50,
    ) -> list[Article]:
        """Get Chinese news articles for the given date.

        获取中文新闻文章:
        1. source_crawler_type == "cn_news" 的文章（来自 CnNewsCrawler）
        2. source_type == "rss" 且 category 以 "cn_" 开头的文章（来自 RssCrawler）

        Args:
            db: Database session
            report_date: Report date
            max_articles: Maximum articles to return

        Returns:
            List of Chinese news articles
        """
        start_datetime = datetime.combine(report_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_datetime = start_datetime + timedelta(days=1)

        query = (
            select(Article)
            .where(
                or_(
                    # cn_news 爬虫抓取的文章
                    Article.source_crawler_type == "cn_news",
                    # RSS 中文新闻分类的文章
                    and_(
                        Article.source_type == "rss",
                        Article.category.like("cn_%"),
                    ),
                )
            )
            .where(Article.publish_time >= start_datetime)
            .where(Article.publish_time < end_datetime)
            .where(Article.is_archived.is_(False))
            .order_by(Article.publish_time.desc())
            .limit(max_articles)
        )

        result = await db.execute(query)
        return list(result.scalars().all())

    async def _get_en_news_articles(
        self,
        db: AsyncSession,
        report_date: date,
        max_articles: int = 50,
    ) -> list[Article]:
        """Get English news articles for the given date.

        获取英文新闻文章: source_type == "rss" 且 category 以 "en_" 开头的文章

        Args:
            db: Database session
            report_date: Report date
            max_articles: Maximum articles to return

        Returns:
            List of English news articles
        """
        start_datetime = datetime.combine(report_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_datetime = start_datetime + timedelta(days=1)

        query = (
            select(Article)
            .where(
                Article.source_type == "rss",
                Article.category.like("en_%"),
            )
            .where(Article.publish_time >= start_datetime)
            .where(Article.publish_time < end_datetime)
            .where(Article.is_archived.is_(False))
            .order_by(Article.publish_time.desc())
            .limit(max_articles)
        )

        result = await db.execute(query)
        return list(result.scalars().all())

    async def _generate_news_report(
        self,
        db: AsyncSession,
        report_date: date,
        articles: list[Article],
        report_type: str,
        title: str,
        source_type_label: str,
    ) -> Optional[DailyReport]:
        """Generate a news report from articles.

        Args:
            db: Database session
            report_date: Report date
            articles: Articles to include
            report_type: Report type identifier (e.g., "cn_news_report", "en_news_report")
            title: Report title
            source_type_label: Source type label for generator

        Returns:
            DailyReport or None
        """
        if not articles:
            logger.info(f"No articles found for {report_type} on {report_date}")
            return None

        # 检查是否已存在
        existing = await db.execute(
            select(DailyReport).where(
                and_(
                    DailyReport.report_date == report_date,
                    DailyReport.source_type == report_type,
                    DailyReport.category == "all",
                )
            )
        )
        if existing.scalar_one_or_none():
            logger.info(f"Report already exists for {report_type} on {report_date}")
            return None

        # 生成 Markdown 报告
        date_str = report_date.strftime("%Y年%m月%d日")
        lines = [
            f"# {title}",
            "",
            f"> 共收录 {len(articles)} 条新闻",
            "",
            "---",
            "",
            "## 📌 新闻列表",
            "",
        ]

        for idx, article in enumerate(articles, 1):
            article_title = article.translated_title or article.title or "无标题"
            url = article.url or ""
            author = article.author or "未知来源"
            summary = article.content_summary or article.summary or ""

            lines.append(f"### {idx}. {article_title}")
            lines.append(f"**来源**: {author}")
            if url:
                lines.append(f"**链接**: [查看原文]({url})")
            if summary:
                if len(summary) > 300:
                    summary = summary[:300] + "..."
                lines.extend(["", "**摘要**:", "", summary])
            lines.extend(["", "---", ""])

        lines.extend([
            "",
            "## 📊 统计信息",
            "",
            f"- 总计: {len(articles)} 条新闻",
            f"- 日期: {report_date.strftime('%Y-%m-%d')}",
            "",
            "---",
            "",
            "*由 ResearchPulse 自动生成*",
            f"*报告类型: {source_type_label}*",
        ])

        content_markdown = "\n".join(lines)
        content_wechat = self.wechat_formatter.format(content_markdown)

        # 创建报告
        report = DailyReport(
            report_date=report_date,
            source_type=report_type,
            category="all",
            category_name=source_type_label,
            title=title,
            content_markdown=content_markdown,
            content_wechat=content_wechat,
            article_count=len(articles),
            article_ids=[a.id for a in articles],
            status="draft",
        )

        db.add(report)
        await db.commit()
        await db.refresh(report)

        logger.info(
            f"Generated {report_type} report for {report_date} with {len(articles)} articles"
        )
        return report

    async def generate_news_reports(
        self,
        report_date: Optional[date] = None,
    ) -> list[DailyReport]:
        """Generate all news reports (CN + EN).

        生成新闻报告:
        1. 中文新闻报告（cn_news + cn_ RSS）
        2. 英文新闻报告（en_ RSS）

        Args:
            report_date: Report date, defaults to yesterday

        Returns:
            List of generated reports
        """
        if report_date is None:
            offset_days = feature_config.get_int("daily_report.report_offset_days", 1)
            report_date = date.today() - timedelta(days=offset_days)

        max_articles = feature_config.get_int("daily_report.max_articles", 50)
        reports = []

        session_factory = get_session_factory()
        async with session_factory() as db:
            date_str = report_date.strftime("%Y年%m月%d日")

            # 1. 中文新闻报告
            cn_articles = await self._get_cn_news_articles(db, report_date, max_articles)
            if cn_articles:
                cn_report = await self._generate_news_report(
                    db=db,
                    report_date=report_date,
                    articles=cn_articles,
                    report_type="cn_news_report",
                    title=f"【中文新闻】{date_str} 新闻摘要",
                    source_type_label="中文新闻",
                )
                if cn_report:
                    reports.append(cn_report)

            # 2. 英文新闻报告
            en_articles = await self._get_en_news_articles(db, report_date, max_articles)
            if en_articles:
                en_report = await self._generate_news_report(
                    db=db,
                    report_date=report_date,
                    articles=en_articles,
                    report_type="en_news_report",
                    title=f"【English News】{date_str} News Digest",
                    source_type_label="English News",
                )
                if en_report:
                    reports.append(en_report)

        logger.info(f"Generated {len(reports)} news reports for {report_date}")
        return reports
