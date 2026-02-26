# =============================================================================
# 模块: apps/daily_report/service.py
# 功能: 每日报告生成核心服务
# 架构角色: 业务逻辑层，负责协调爬虫、翻译、生成器等组件
# =============================================================================

"""Daily report generation service."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.crawler.models.article import Article
from apps.daily_report.models.daily_report import DailyReport
from apps.daily_report.generator import ReportGenerator
from apps.daily_report.formatters.wechat import WeChatFormatter
from core.database import get_session_factory
from settings import settings
from common.feature_config import feature_config

logger = logging.getLogger(__name__)


def _is_english(text: str) -> bool:
    """Check if text is primarily English by ASCII letter ratio."""
    if not text or len(text) < 10:
        return False
    ascii_letters = sum(1 for c in text if c.isascii() and c.isalpha())
    total_letters = sum(1 for c in text if c.isalpha())
    if total_letters == 0:
        return False
    return ascii_letters / total_letters > 0.5


class DailyReportService:
    """Service for generating daily arXiv reports.

    每日 arXiv 报告生成服务，负责：
    1. 获取指定日期的文章
    2. 确保文章已翻译
    3. 生成 Markdown 报告
    4. 生成微信公众号格式
    5. 保存到数据库
    """

    def __init__(self):
        self.generator = ReportGenerator()
        self.wechat_formatter = WeChatFormatter()
        # 分类名称缓存
        self._category_names_cache: dict[str, str] = {}

    async def _load_category_names(self, db: AsyncSession) -> dict[str, str]:
        """Load category names from database.

        从数据库加载分类名称映射。
        优先使用 name_zh（中文名称），如果为空则使用 name（英文名称）。
        """
        if self._category_names_cache:
            return self._category_names_cache

        try:
            result = await db.execute(
                text("SELECT code, name, name_zh FROM arxiv_categories")
            )
            rows = result.fetchall()

            for row in rows:
                code = row[0]
                name_en = row[1] or ""
                name_zh = row[2] or ""
                # 优先使用中文名称
                self._category_names_cache[code] = name_zh if name_zh else name_en

            logger.info(f"Loaded {len(self._category_names_cache)} category names from database")
        except Exception as e:
            logger.warning(f"Failed to load category names from database: {e}")

        return self._category_names_cache

    def _get_category_name(self, category: str, category_names: dict[str, str]) -> str:
        """Get Chinese name for arXiv category.

        获取 arXiv 分类的中文名称。
        """
        return category_names.get(category, category)

    async def get_articles_for_date(
        self,
        db: AsyncSession,
        report_date: date,
        category: str,
        max_articles: int = 50,
    ) -> list[Article]:
        """Get articles for a specific date and category.

        获取指定日期和分类的文章。

        Args:
            db: Database session.
            report_date: Report date.
            category: arXiv category code.
            max_articles: Maximum number of articles to return.

        Returns:
            List of articles.
        """
        # 计算日期范围（UTC 时区）
        start_datetime = datetime.combine(report_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_datetime = start_datetime + timedelta(days=1)

        # 查询条件：
        # 1. 来源类型为 arxiv
        # 2. 发布时间在指定日期范围内
        # 3. 主分类匹配（arxiv_primary_category 或 category）
        # 4. 未归档
        query = (
            select(Article)
            .where(Article.source_type == "arxiv")
            .where(Article.publish_time >= start_datetime)
            .where(Article.publish_time < end_datetime)
            .where(
                (Article.arxiv_primary_category == category) |
                (Article.category == category)
            )
            .where(Article.is_archived.is_(False))
            .order_by(Article.publish_time.desc())
            .limit(max_articles)
        )

        result = await db.execute(query)
        return list(result.scalars().all())

    async def ensure_translated(
        self,
        articles: list[Article],
        db: AsyncSession,
    ) -> None:
        """Ensure articles have translated title and summary.

        确保文章标题和摘要已翻译。对于未翻译的文章，调用翻译服务。

        Args:
            articles: List of articles.
            db: Database session.
        """
        if not articles:
            return

        # 检查是否启用翻译
        translate_title = feature_config.get_bool("daily_report.translate_title", True)

        # 如果不需要翻译或翻译服务不可用，直接返回
        if not translate_title:
            return

        # 导入翻译服务（延迟导入避免循环依赖）
        from apps.ai_processor.service import get_ai_provider

        try:
            provider = get_ai_provider()
            needs_update = []

            for article in articles:
                updated = False

                # 翻译标题
                if _is_english(article.title or "") and not article.translated_title:
                    try:
                        translated_title = await provider.translate(article.title)
                        if translated_title:
                            article.translated_title = translated_title
                            updated = True
                    except Exception as e:
                        logger.warning(f"Failed to translate title for article {article.id}: {e}")

                # 翻译摘要（存储到 content_summary 字段）
                if _is_english(article.summary or "") and not article.content_summary:
                    try:
                        translated_summary = await provider.translate(article.summary)
                        if translated_summary:
                            article.content_summary = translated_summary
                            updated = True
                    except Exception as e:
                        logger.warning(f"Failed to translate summary for article {article.id}: {e}")

                if updated:
                    needs_update.append(article)

            # 批量更新到数据库
            if needs_update:
                for article in needs_update:
                    db.add(article)
                await db.commit()
                logger.info(f"Translated {len(needs_update)} articles")

        except Exception as e:
            logger.error(f"Translation service error: {e}")
        finally:
            try:
                await provider.close()
            except Exception:
                pass

    async def generate_report(
        self,
        db: AsyncSession,
        report_date: date,
        category: str,
    ) -> Optional[DailyReport]:
        """Generate a daily report for a specific category.

        为指定分类生成每日报告。

        Args:
            db: Database session.
            report_date: Report date.
            category: arXiv category code.

        Returns:
            Generated DailyReport or None if no articles.
        """
        # 检查是否已存在报告
        existing = await self.get_report(db, report_date, category)
        if existing:
            logger.info(f"Report already exists for {report_date} / {category}")
            return existing

        # 加载分类名称
        category_names = await self._load_category_names(db)

        # 获取配置
        max_articles = feature_config.get_int("daily_report.max_articles", 50)
        category_name = self._get_category_name(category, category_names)

        # 获取文章
        articles = await self.get_articles_for_date(
            db, report_date, category, max_articles
        )

        if not articles:
            logger.info(f"No articles found for {report_date} / {category}")
            return None

        # 确保翻译
        await self.ensure_translated(articles, db)

        # 生成报告
        title = f"【每日 arXiv】{report_date.strftime('%Y年%m月%d日')} {category_name}领域新论文"
        content_markdown = self.generator.generate(
            report_date, category, category_name, articles
        )
        content_wechat = self.wechat_formatter.format(content_markdown)

        # 创建报告记录
        report = DailyReport(
            report_date=report_date,
            category=category,
            category_name=category_name,
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

        logger.info(f"Generated report for {report_date} / {category} with {len(articles)} articles")
        return report

    async def generate_daily_reports(
        self,
        report_date: Optional[date] = None,
        categories: Optional[list[str]] = None,
    ) -> list[DailyReport]:
        """Generate daily reports for all configured categories.

        为所有配置的分类生成每日报告。

        Args:
            report_date: Report date, defaults to yesterday.
            categories: Categories to generate, defaults to config.

        Returns:
            List of generated reports.
        """
        # 确定日期
        if report_date is None:
            offset_days = feature_config.get_int("daily_report.report_offset_days", 1)
            report_date = date.today() - timedelta(days=offset_days)

        # 确定分类
        if categories is None:
            categories_str = feature_config.get("daily_report.categories", "cs.LG,cs.CV,cs.CL,cs.AI")
            categories = [c.strip() for c in categories_str.split(",") if c.strip()]

        # 检查功能是否启用
        if not feature_config.get_bool("daily_report.enabled", True):
            logger.info("Daily report feature is disabled")
            return []

        logger.info(f"Generating daily reports for {report_date}, categories: {categories}")

        session_factory = get_session_factory()
        reports = []

        async with session_factory() as db:
            for category in categories:
                try:
                    report = await self.generate_report(db, report_date, category)
                    if report:
                        reports.append(report)
                except Exception as e:
                    logger.error(f"Failed to generate report for {category}: {e}")

        return reports

    async def get_report(
        self,
        db: AsyncSession,
        report_date: date,
        category: str,
    ) -> Optional[DailyReport]:
        """Get a specific report by date and category.

        获取指定日期和分类的报告。
        """
        query = select(DailyReport).where(
            and_(
                DailyReport.report_date == report_date,
                DailyReport.category == category,
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_report_by_id(
        self,
        db: AsyncSession,
        report_id: int,
    ) -> Optional[DailyReport]:
        """Get a specific report by ID.

        通过 ID 获取报告。
        """
        query = select(DailyReport).where(DailyReport.id == report_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def list_reports(
        self,
        db: AsyncSession,
        report_date: Optional[date] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[DailyReport], int]:
        """List reports with filters and pagination.

        列出报告（支持筛选和分页）。
        """
        query = select(DailyReport)

        if report_date:
            query = query.where(DailyReport.report_date == report_date)
        if category:
            query = query.where(DailyReport.category == category)
        if status:
            query = query.where(DailyReport.status == status)

        # 计算总数
        count_query = query
        count_result = await db.execute(count_query)
        total = len(count_result.scalars().all())

        # 分页
        query = query.order_by(DailyReport.report_date.desc(), DailyReport.category)
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        reports = list(result.scalars().all())

        return reports, total

    async def export_report(
        self,
        db: AsyncSession,
        report_id: int,
        format: str = "markdown",
    ) -> Optional[dict]:
        """Export a report in specified format.

        导出报告。
        """
        report = await self.get_report_by_id(db, report_id)
        if not report:
            return None

        content = report.content_markdown
        if format == "wechat":
            content = report.content_wechat or report.content_markdown

        return {
            "id": report.id,
            "report_date": report.report_date,
            "category": report.category,
            "category_name": report.category_name,
            "title": report.title,
            "content": content,
            "format": format,
            "article_count": report.article_count,
        }

    async def export_daily(
        self,
        db: AsyncSession,
        report_date: date,
        format: str = "wechat",
    ) -> Optional[dict]:
        """Export all reports for a day as a single document.

        导出一天所有分类的报告（合并版）。
        """
        reports, total = await self.list_reports(db, report_date=report_date)

        if not reports:
            return None

        # 合并所有报告内容
        combined_content = f"# 【每日 arXiv】{report_date.strftime('%Y年%m月%d日')} 新论文汇总\n\n"
        combined_content += f"> 共收录 {sum(r.article_count for r in reports)} 篇论文，涵盖 {len(reports)} 个分类\n\n"
        combined_content += "---\n\n"

        total_articles = 0
        categories = []

        for report in reports:
            categories.append(report.category_name)
            total_articles += report.article_count

            content = report.content_markdown
            if format == "wechat":
                content = report.content_wechat or report.content_markdown

            # 移除报告标题（已在外层添加）
            lines = content.split("\n")
            if lines and lines[0].startswith("# "):
                content = "\n".join(lines[1:])

            combined_content += content + "\n\n---\n\n"

        return {
            "report_date": report_date,
            "format": format,
            "total_articles": total_articles,
            "categories": categories,
            "content": combined_content.strip(),
            "reports": reports,
        }
