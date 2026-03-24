"""Sender service for cross-server data sync.

Orchestrates the 3-step sync from Pipeline machine (A) to Display machine (B):
1. Sync articles
2. Sync daily reports (with article_ref_keys translation)
3. Sync weekly/monthly reports (with username resolution)
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.crawler.models.article import Article
from apps.daily_report.models.daily_report import DailyReport
from apps.report.models import Report
from apps.sync.sender_client import SyncClient
from core.database import get_session_factory
from core.models.user import User
from settings import settings

logger = logging.getLogger(__name__)


class SyncSenderService:
    """Orchestrate data sync from Pipeline (A) to Display (B)."""

    async def sync_all(
        self,
        report_date: date,
        daily_reports: list[DailyReport],
    ) -> None:
        """Main entry: sync articles, daily reports, and reports.

        Also updates sync_status on successfully synced reports.

        Args:
            report_date: The report date being synced.
            daily_reports: List of DailyReport instances from A's DB.
        """
        client = SyncClient()
        try:
            # Step 1: Sync articles
            a_to_b_id_map: dict[int, int] = {}
            if settings.sync_sender_sync_articles:
                a_to_b_id_map = await self._sync_articles(client, daily_reports)

            # Step 2: Sync daily reports
            if settings.sync_sender_sync_daily_reports:
                await self._sync_daily_reports(client, daily_reports)

            # Step 3: Sync weekly/monthly reports
            if settings.sync_sender_sync_reports:
                await self._sync_reports(client, report_date)

            # Step 4: Mark synced reports as success
            if daily_reports:
                report_ids = [r.id for r in daily_reports]
                session_factory = get_session_factory()
                async with session_factory() as db:
                    await db.execute(
                        update(DailyReport)
                        .where(DailyReport.id.in_(report_ids))
                        .values(
                            sync_status="success",
                            sync_attempted_at=datetime.now(timezone.utc),
                            sync_error=None,
                        )
                    )
                    await db.commit()
                    logger.info("Marked %d reports as successfully synced", len(report_ids))

            logger.info("Sync completed for %s", report_date)
        except Exception as e:
            logger.error("Sync failed for %s: %s", report_date, e)
            # Optionally mark reports as failed
            if daily_reports:
                report_ids = [r.id for r in daily_reports]
                session_factory = get_session_factory()
                async with session_factory() as db:
                    await db.execute(
                        update(DailyReport)
                        .where(DailyReport.id.in_(report_ids))
                        .values(
                            sync_status="failed",
                            sync_error=str(e)[:500],
                            sync_attempted_at=datetime.now(timezone.utc),
                        )
                    )
                    await db.commit()
            raise
        finally:
            await client.close()

    async def _sync_articles(
        self,
        client: SyncClient,
        reports: list[DailyReport],
    ) -> dict[int, int]:
        """Collect all referenced articles and sync them to B.

        Returns:
            Mapping of A's article.id -> B's article.id
        """
        # Collect unique article IDs from all reports
        a_article_ids: set[int] = set()
        for report in reports:
            if report.article_ids:
                a_article_ids.update(report.article_ids)

        if not a_article_ids:
            return {}

        # Load articles from A's DB
        session_factory = get_session_factory()
        async with session_factory() as db:
            result = await db.execute(
                select(Article).where(Article.id.in_(list(a_article_ids)))
            )
            articles = list(result.scalars().all())

        if not articles:
            return {}

        # Convert to sync dicts (exclude auto-managed fields)
        article_dicts = [self._article_to_dict(a) for a in articles]

        # Push to B, get back id_map {natural_key: B_article_id}
        id_map = await client.sync_articles(article_dicts)

        # Build A_id -> B_id mapping
        a_to_b_map: dict[int, int] = {}
        for article in articles:
            natural_key = f"{article.source_type}|{article.source_id}|{article.external_id}"
            if natural_key in id_map:
                a_to_b_map[article.id] = id_map[natural_key]

        logger.info(
            "Synced %d articles to display machine (mapped %d/%d)",
            len(articles), len(a_to_b_map), len(articles),
        )
        unmapped = len(articles) - len(a_to_b_map)
        if unmapped > 0:
            logger.warning(
                "Article sync incomplete: %d/%d articles not mapped on display machine",
                unmapped, len(articles),
            )
        return a_to_b_map

    async def _sync_daily_reports(
        self,
        client: SyncClient,
        reports: list[DailyReport],
    ) -> None:
        """Sync daily reports, translating article IDs to natural key strings."""
        if not reports:
            return

        # Batch load all natural keys for referenced articles
        all_article_ids: set[int] = set()
        for report in reports:
            if report.article_ids:
                all_article_ids.update(report.article_ids)

        # Build article_id -> natural_key lookup
        id_to_natural_key: dict[int, str] = {}
        if all_article_ids:
            session_factory = get_session_factory()
            async with session_factory() as db:
                result = await db.execute(
                    select(
                        Article.id,
                        Article.source_type,
                        Article.source_id,
                        Article.external_id,
                    ).where(Article.id.in_(list(all_article_ids)))
                )
                for row in result.all():
                    id_to_natural_key[row[0]] = f"{row[1]}|{row[2]}|{row[3]}"

        # Build report sync payloads
        report_dicts = []
        for report in reports:
            # Translate A's article_ids to natural key strings
            article_ref_keys: list[str] = []
            if report.article_ids:
                missing_ids = []
                for aid in report.article_ids:
                    if aid in id_to_natural_key:
                        article_ref_keys.append(id_to_natural_key[aid])
                    else:
                        missing_ids.append(aid)
                if missing_ids:
                    logger.warning(
                        "Daily report %s/%s/%s: %d article IDs not found in DB: %s",
                        report.report_date, report.source_type, report.category,
                        len(missing_ids), missing_ids,
                    )

            report_dicts.append({
                "report_date": report.report_date.isoformat(),
                "source_type": report.source_type,
                "category": report.category,
                "category_name": report.category_name,
                "title": report.title,
                "content_markdown": report.content_markdown,
                "content_wechat": report.content_wechat,
                "article_count": report.article_count,
                "article_ref_keys": article_ref_keys,
                "status": report.status,
                "published_at": report.published_at.isoformat() if report.published_at else None,
                "wechat_draft_media_id": report.wechat_draft_media_id,
                "wechat_push_status": report.wechat_push_status,
                "wechat_push_error": report.wechat_push_error,
                "wechat_pushed_at": report.wechat_pushed_at.isoformat() if report.wechat_pushed_at else None,
            })

        result = await client.sync_daily_reports(report_dicts)
        logger.info(
            "Synced %d daily reports: %d total, %d errors",
            len(reports), result.get("synced", 0), len(result.get("errors", [])),
        )
        for err in result.get("errors", []):
            logger.warning("Daily report sync error: %s", err)

    async def _sync_reports(self, client: SyncClient, report_date: date) -> None:
        """Sync weekly/monthly reports generated on the same date."""
        session_factory = get_session_factory()

        start_dt = datetime.combine(report_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_dt = start_dt + timedelta(days=1)

        async with session_factory() as db:
            result = await db.execute(
                select(Report)
                .where(Report.generated_at >= start_dt)
                .where(Report.generated_at < end_dt)
            )
            reports = list(result.scalars().all())

        if not reports:
            return

        # Build user_id -> username lookup
        user_ids = list({r.user_id for r in reports})
        session_factory = get_session_factory()
        id_to_username: dict[int, str] = {}
        async with session_factory() as db:
            result = await db.execute(
                select(User.id, User.username).where(User.id.in_(user_ids))
            )
            for row in result.all():
                id_to_username[row[0]] = row[1]

        # Build report sync payloads
        report_dicts = []
        for report in reports:
            username = id_to_username.get(report.user_id, "")
            if not username:
                # Try to use the receiver-side default username if configured
                default_user = settings.sync_receiver_default_username
                if default_user:
                    logger.warning(
                        "Report %d: user %d not found locally, sending with default user '%s'",
                        report.id, report.user_id, default_user,
                    )
                    username = default_user
                else:
                    logger.warning("Report %d: user %d not found, skipping", report.id, report.user_id)
                    continue

            report_dicts.append({
                "username": username,
                "type": report.type,
                "period_start": report.period_start,
                "period_end": report.period_end,
                "title": report.title,
                "content": report.content,
                "stats": report.stats,
                "generated_at": report.generated_at.isoformat() if report.generated_at else None,
            })

        if report_dicts:
            result = await client.sync_reports(report_dicts)
            logger.info(
                "Synced reports: %d total, %d skipped",
                result.get("synced", 0), result.get("skipped", 0),
            )
            for err in result.get("errors", []):
                logger.warning("Report sync error: %s", err)

    @staticmethod
    def _article_to_dict(article: Article) -> dict:
        """Convert Article ORM object to sync dict."""
        return {
            "source_type": article.source_type,
            "source_id": article.source_id,
            "external_id": article.external_id,
            "title": article.title,
            "url": article.url,
            "author": article.author,
            "summary": article.summary,
            "translated_title": article.translated_title,
            "content": article.content,
            "cover_image_url": article.cover_image_url,
            "category": article.category,
            "news_source_country": article.news_source_country,
            "news_category": article.news_category,
            "image_url": article.image_url,
            "source_crawler_type": article.source_crawler_type,
            "tags": article.tags,
            "publish_time": article.publish_time.isoformat() if article.publish_time else None,
            "crawl_time": article.crawl_time.isoformat() if article.crawl_time else None,
            "is_archived": article.is_archived,
            "archived_at": article.archived_at.isoformat() if article.archived_at else None,
            "arxiv_id": article.arxiv_id,
            "arxiv_primary_category": article.arxiv_primary_category,
            "arxiv_comment": article.arxiv_comment,
            "arxiv_updated_time": article.arxiv_updated_time.isoformat() if article.arxiv_updated_time else None,
            "arxiv_paper_type": article.arxiv_paper_type,
            "wechat_account_name": article.wechat_account_name,
            "wechat_digest": article.wechat_digest,
            "content_summary": article.content_summary,
            "ai_summary": article.ai_summary,
            "ai_category": article.ai_category,
            "ai_subcategory": article.ai_subcategory,
            "importance_score": article.importance_score,
            "one_liner": article.one_liner,
            "key_points": article.key_points,
            "impact_assessment": article.impact_assessment,
            "actionable_items": article.actionable_items,
            "ai_processed_at": article.ai_processed_at.isoformat() if article.ai_processed_at else None,
            "ai_provider": article.ai_provider,
            "ai_model": article.ai_model,
            "token_used": article.token_used,
            "processing_method": article.processing_method,
            "read_count": article.read_count,
            "like_count": article.like_count,
        }
