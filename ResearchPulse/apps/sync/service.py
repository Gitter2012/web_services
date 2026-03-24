"""Receiver service for cross-server data sync.

Handles upsert logic for articles, daily reports, and weekly/monthly reports
on the Display machine (B).
"""

from __future__ import annotations

import logging

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.crawler.models.article import Article
from apps.daily_report.models.daily_report import DailyReport
from apps.report.models import Report
from apps.sync.schemas import (
    ArticleSyncItem,
    DailyReportSyncItem,
    ReportSyncItem,
)
from core.models.user import User
from settings import settings

logger = logging.getLogger(__name__)


class SyncReceiverService:
    """Service for receiving and upserting synced data."""

    # Fields to update on conflict (all except natural key and auto-managed fields)
    _ARTICLE_UPDATE_COLS = [
        "title", "url", "author", "summary", "translated_title", "content",
        "cover_image_url", "category", "news_source_country", "news_category",
        "image_url", "source_crawler_type", "tags", "publish_time",
        "crawl_time", "is_archived", "archived_at", "arxiv_id",
        "arxiv_primary_category", "arxiv_comment", "arxiv_updated_time",
        "arxiv_paper_type", "wechat_account_name", "wechat_digest",
        "content_summary", "ai_summary", "ai_category", "ai_subcategory",
        "importance_score", "one_liner", "key_points", "impact_assessment",
        "actionable_items", "ai_processed_at", "ai_provider", "ai_model",
        "token_used", "processing_method", "read_count", "like_count",
    ]

    async def upsert_articles(
        self,
        db: AsyncSession,
        items: list[ArticleSyncItem],
    ) -> tuple[int, int, dict[str, int]]:
        """Upsert articles using natural key (source_type, source_id, external_id).

        Returns:
            (created, updated, id_map) where id_map is
            {"source_type|source_id|external_id": article_id}
        """
        if not items:
            return 0, 0, {}

        created = 0
        updated = 0
        id_map: dict[str, int] = {}

        for item in items:
            try:
                values = item.model_dump()

                stmt = mysql_insert(Article).values(**values)
                update_dict = {
                    k: stmt.inserted[k]
                    for k in self._ARTICLE_UPDATE_COLS
                }
                stmt = stmt.on_duplicate_key_update(**update_dict)
                result = await db.execute(stmt)
                # MySQL rowcount: 1 = inserted, 2 = updated (old+new row affected)
                if result.rowcount == 1:
                    created += 1
                elif result.rowcount == 2:
                    updated += 1
                else:
                    # rowcount=0 means nothing changed (identical data), count as updated
                    updated += 1
            except Exception as e:
                logger.warning("Failed to upsert article %s|%s|%s: %s",
                               item.source_type, item.source_id, item.external_id, e)

        await db.commit()

        # Batch query to get all IDs
        conditions = [
            and_(
                Article.source_type == item.source_type,
                Article.source_id == item.source_id,
                Article.external_id == item.external_id,
            )
            for item in items
        ]
        result = await db.execute(
            select(
                Article.source_type,
                Article.source_id,
                Article.external_id,
                Article.id,
            ).where(or_(*conditions))
        )
        for row in result.all():
            key = f"{row[0]}|{row[1]}|{row[2]}"
            id_map[key] = row[3]

        logger.info("Upserted %d articles (%d created, %d updated)",
                     len(id_map), created, updated)
        return created, updated, id_map

    async def upsert_daily_reports(
        self,
        db: AsyncSession,
        items: list[DailyReportSyncItem],
    ) -> tuple[int, int, list[str]]:
        """Upsert daily reports, resolving article_ref_keys to local article IDs.

        Uses savepoint for transaction isolation: each report upsert is isolated.
        If one fails, others continue without rollback.

        Returns:
            (created, updated, errors)
        """
        created = 0
        updated = 0
        errors: list[str] = []

        for item in items:
            # Use savepoint for transaction isolation
            async with db.begin_nested():  # Create savepoint, auto-rollback on exception
                try:
                    # Resolve article_ref_keys to local article IDs
                    b_article_ids = await self._resolve_article_ids(db, item.article_ref_keys)
                    if len(b_article_ids) != len(item.article_ref_keys):
                        missing = len(item.article_ref_keys) - len(
                            [aid for aid in b_article_ids if aid is not None]
                        )
                        errors.append(
                            f"{item.report_date}/{item.source_type}/{item.category}: "
                            f"{missing} articles not found"
                        )
                        b_article_ids = [aid for aid in b_article_ids if aid is not None]

                    # Check existing by natural key
                    existing = await db.execute(
                        select(DailyReport).where(
                            DailyReport.report_date == item.report_date,
                            DailyReport.source_type == item.source_type,
                            DailyReport.category == item.category,
                        )
                    )
                    report = existing.scalar_one_or_none()

                    if report:
                        report.title = item.title
                        report.category_name = item.category_name
                        report.content_markdown = item.content_markdown
                        report.content_wechat = item.content_wechat
                        report.article_count = item.article_count
                        report.article_ids = b_article_ids
                        report.status = item.status
                        report.published_at = item.published_at
                        report.wechat_draft_media_id = item.wechat_draft_media_id
                        report.wechat_push_status = item.wechat_push_status
                        report.wechat_push_error = item.wechat_push_error
                        report.wechat_pushed_at = item.wechat_pushed_at
                        # Mark sync as pending (will be updated after successful sync)
                        report.sync_status = "pending"
                        report.sync_attempted_at = None
                        updated += 1
                    else:
                        report = DailyReport(
                            report_date=item.report_date,
                            source_type=item.source_type,
                            category=item.category,
                            category_name=item.category_name,
                            title=item.title,
                            content_markdown=item.content_markdown,
                            content_wechat=item.content_wechat,
                            article_count=item.article_count,
                            article_ids=b_article_ids,
                            status=item.status,
                            published_at=item.published_at,
                            wechat_draft_media_id=item.wechat_draft_media_id,
                            wechat_push_status=item.wechat_push_status,
                            wechat_push_error=item.wechat_push_error,
                            wechat_pushed_at=item.wechat_pushed_at,
                            # Mark sync as pending for new reports
                            sync_status="pending",
                        )
                        db.add(report)
                        created += 1
                except Exception as e:
                    errors.append(f"{item.report_date}/{item.source_type}/{item.category}: {e}")
                    logger.warning("Failed to upsert daily report %s/%s/%s: %s",
                                   item.report_date, item.source_type, item.category, e)
                    # Savepoint auto-rolls back, continue with next item

        await db.commit()
        logger.info("Upserted %d daily reports (%d created, %d updated)",
                     created + updated, created, updated)
        return created, updated, errors

    async def upsert_reports(
        self,
        db: AsyncSession,
        items: list[ReportSyncItem],
    ) -> tuple[int, int, int, list[str]]:
        """Upsert weekly/monthly reports, resolving username to local user_id.

        Returns:
            (created, updated, skipped, errors)
        """
        created = 0
        updated = 0
        skipped = 0
        errors: list[str] = []

        for item in items:
            try:
                # Resolve username -> local user_id
                user = await self._resolve_user(db, item.username)
                if user is None:
                    skipped += 1
                    continue

                # Check existing by (user_id, type, period_start)
                existing = await db.execute(
                    select(Report).where(
                        Report.user_id == user.id,
                        Report.type == item.type,
                        Report.period_start == item.period_start,
                    )
                )
                report = existing.scalar_one_or_none()

                if report:
                    report.title = item.title
                    report.content = item.content
                    report.stats = item.stats
                    report.period_end = item.period_end
                    updated += 1
                else:
                    report = Report(
                        user_id=user.id,
                        type=item.type,
                        period_start=item.period_start,
                        period_end=item.period_end,
                        title=item.title,
                        content=item.content,
                        stats=item.stats,
                        generated_at=item.generated_at,
                    )
                    db.add(report)
                    created += 1
            except Exception as e:
                errors.append(f"{item.username}/{item.type}/{item.period_start}: {e}")
                logger.warning("Failed to upsert report %s/%s/%s: %s",
                               item.username, item.type, item.period_start, e)

        await db.commit()
        logger.info("Upserted %d reports (%d created, %d updated, %d skipped)",
                     created + updated, created, updated, skipped)
        return created, updated, skipped, errors

    # =========================================================================
    # Helpers
    # =========================================================================

    async def _resolve_article_ids(
        self, db: AsyncSession, ref_keys: list[str]
    ) -> list[int | None]:
        """Resolve natural key strings to local article IDs.

        Each ref_key is in format "source_type|source_id|external_id".
        """
        if not ref_keys:
            return []

        conditions = []
        key_parts = []
        malformed_keys = []
        for key in ref_keys:
            parts = key.split("|", 2)
            if len(parts) == 3:
                conditions.append(and_(
                    Article.source_type == parts[0],
                    Article.source_id == parts[1],
                    Article.external_id == parts[2],
                ))
                key_parts.append(parts)
            else:
                malformed_keys.append(key)
                conditions.append(None)
                key_parts.append(None)

        if malformed_keys:
            logger.warning("Malformed article ref keys (expected 'source_type|source_id|external_id'): %s",
                           malformed_keys)

        if not conditions:
            return [None] * len(ref_keys)

        # Only query valid conditions
        valid_conditions = [c for c in conditions if c is not None]
        if not valid_conditions:
            return [None] * len(ref_keys)

        result = await db.execute(
            select(
                Article.source_type,
                Article.source_id,
                Article.external_id,
                Article.id,
            ).where(or_(*valid_conditions))
        )
        lookup = {f"{r[0]}|{r[1]}|{r[2]}": r[3] for r in result.all()}
        return [lookup.get(key) for key in ref_keys]

    async def _resolve_user(
        self, db: AsyncSession, username: str
    ) -> User | None:
        """Resolve username to local User, with fallback."""
        result = await db.execute(
            select(User).where(User.username == username)
        )
        user = result.scalar_one_or_none()

        if user is None:
            # Try fallback user
            fallback = settings.sync_receiver_default_username
            if fallback:
                result = await db.execute(
                    select(User).where(User.username == fallback)
                )
                user = result.scalar_one_or_none()
                if user:
                    logger.info(
                        "Report for user '%s' mapped to fallback user '%s'",
                        username, fallback,
                    )

        return user
