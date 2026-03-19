# =============================================================================
# 模块: common/wechat_mp/draft_service.py
# 功能: 微信公众号草稿推送服务
# 架构角色: 通用基础设施层，负责将报告推送到微信公众号草稿箱
# 设计决策:
#   1. 将多份报告组合为一个多图文草稿（最多 8 篇文章/草稿）
#   2. 超过 8 篇时自动拆分为多个草稿
#   3. 内建失败重试机制（指数退避）
#   4. 推送结果写回数据库（DailyReport 的推送状态字段）
#   5. 失败时发送邮件通知（复用 SUPERUSER_EMAIL）
# =============================================================================

"""WeChat MP draft push service."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from common.wechat_mp.client import WeChatAPIError, WeChatMPClient

logger = logging.getLogger(__name__)

# 微信草稿箱单个草稿最多 8 篇文章
MAX_ARTICLES_PER_DRAFT = 8


class WeChatDraftService:
    """WeChat Official Account draft push service.

    微信公众号草稿推送服务，负责：
    1. 将 DailyReport 列表转换为微信草稿文章格式
    2. 调用微信 API 创建草稿
    3. 更新数据库推送状态
    4. 失败重试和邮件通知

    Usage:
        from common.wechat_mp.client import WeChatMPClient
        from common.wechat_mp.draft_service import WeChatDraftService

        client = WeChatMPClient(appid="...", secret="...")
        service = WeChatDraftService(client, settings)
        results = await service.push_reports(reports, db)
        await client.close()
    """

    def __init__(
        self,
        client: WeChatMPClient,
        *,
        default_thumb_media_id: str = "",
        category_thumbs: Optional[dict[str, str]] = None,
        retry_times: int = 3,
        retry_delay: int = 5,
        author: str = "ResearchPulse",
    ):
        """Initialize WeChatDraftService.

        Args:
            client: WeChatMPClient instance.
            default_thumb_media_id: Default cover image media_id.
            category_thumbs: Mapping of category -> thumb media_id.
            retry_times: Max retry attempts on failure.
            retry_delay: Base delay between retries in seconds.
            author: Default article author name.
        """
        self.client = client
        self.default_thumb_media_id = default_thumb_media_id
        self.category_thumbs = category_thumbs or {}
        self.retry_times = retry_times
        self.retry_delay = retry_delay
        self.author = author

        # 延迟导入 HTML 格式化器（避免循环导入）
        self._html_formatter = None

    def _get_html_formatter(self):
        """Lazy-load the HTML formatter.

        延迟加载 HTML 格式化器，避免模块级循环导入。
        """
        if self._html_formatter is None:
            from apps.daily_report.formatters.wechat_html import WeChatHTMLFormatter
            self._html_formatter = WeChatHTMLFormatter()
        return self._html_formatter

    def _get_thumb_media_id(self, category: str) -> str:
        """Get the cover image media_id for a category.

        获取分类对应的封面图 media_id，未配置时使用默认封面。

        Args:
            category: arXiv category code (e.g., "cs.LG").

        Returns:
            Thumb media_id string (may be empty if not configured).
        """
        thumb = self.category_thumbs.get(category, "")
        if not thumb:
            thumb = self.default_thumb_media_id
        
        if not thumb:
            logger.warning(
                "No cover image configured for category %s. "
                "Draft creation may fail if thumb_media_id is required.",
                category,
            )
        
        return thumb

    def _build_article(self, report: Any) -> dict[str, Any]:
        """Build a WeChat draft article dict from a DailyReport.

        将 DailyReport 转换为微信草稿文章格式。

        Args:
            report: DailyReport instance.

        Returns:
            Article dict for WeChat draft API.
        """
        formatter = self._get_html_formatter()

        # 生成 HTML 内容
        content_html = formatter.format(report.content_markdown)

        # 生成摘要（最多 128 字）
        digest = formatter.generate_digest(report)

        # 标题截断为 32 字
        title = report.title
        if len(title) > 32:
            title = title[:29] + "..."

        # 获取封面图
        thumb_media_id = self._get_thumb_media_id(report.category)

        article = {
            "title": title,
            "author": self.author,
            "digest": digest,
            "content": content_html,
            "thumb_media_id": thumb_media_id,
            "content_source_url": "",
            "need_open_comment": 0,
            "only_fans_can_comment": 0,
        }

        return article

    async def push_reports(
        self,
        reports: list[Any],
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        """Push multiple reports as WeChat draft(s).

        将多份报告推送为微信草稿。如果报告数量超过 8 篇，
        自动拆分为多个草稿。

        Args:
            reports: List of DailyReport instances.
            db: Database session for updating push status.

        Returns:
            List of result dicts, each with keys:
                - success (bool)
                - media_id (str, if success)
                - error (str, if failed)
                - report_ids (list[int])
        """
        if not reports:
            return [{"success": False, "error": "无报告可推送", "report_ids": []}]

        results = []

        # 按最多 8 篇分批
        for batch_start in range(0, len(reports), MAX_ARTICLES_PER_DRAFT):
            batch = reports[batch_start : batch_start + MAX_ARTICLES_PER_DRAFT]
            result = await self._push_batch(batch, db)
            results.append(result)

        return results

    async def _push_batch(
        self,
        reports: list[Any],
        db: AsyncSession,
    ) -> dict[str, Any]:
        """Push a batch of reports (≤8) as a single draft.

        推送一批报告（不超过 8 篇）为单个草稿。

        带有重试机制（指数退避）。

        Args:
            reports: List of DailyReport instances (max 8).
            db: Database session.

        Returns:
            Result dict.
        """
        report_ids = [r.id for r in reports]

        # 构建文章数据
        articles = []
        for report in reports:
            try:
                article = self._build_article(report)
                articles.append(article)
            except Exception as e:
                logger.error(
                    "Failed to build article for report %d (%s): %s",
                    report.id,
                    report.category,
                    e,
                )
                # 标记该报告推送失败
                await self._update_push_status(
                    report, db, success=False, error=f"构建文章失败: {e}"
                )

        if not articles:
            await db.commit()
            return {
                "success": False,
                "error": "所有报告构建失败",
                "report_ids": report_ids,
            }

        # 带重试的推送
        last_error = ""
        for attempt in range(1, self.retry_times + 1):
            try:
                media_id = await self.client.create_draft(articles)

                # 推送成功，更新所有报告状态
                for report in reports:
                    await self._update_push_status(
                        report, db, success=True, media_id=media_id
                    )
                await db.commit()

                logger.info(
                    "WeChat draft pushed successfully: media_id=%s, "
                    "articles=%d, report_ids=%s",
                    media_id,
                    len(articles),
                    report_ids,
                )
                return {
                    "success": True,
                    "media_id": media_id,
                    "article_count": len(articles),
                    "report_ids": report_ids,
                }

            except WeChatAPIError as e:
                last_error = str(e)
                logger.warning(
                    "WeChat draft push attempt %d/%d failed: %s",
                    attempt,
                    self.retry_times,
                    e,
                )
            except Exception as e:
                last_error = str(e)
                logger.error(
                    "WeChat draft push attempt %d/%d unexpected error: %s",
                    attempt,
                    self.retry_times,
                    e,
                )

            # 等待后重试（指数退避）
            if attempt < self.retry_times:
                delay = self.retry_delay * (2 ** (attempt - 1))
                logger.info("Retrying in %d seconds...", delay)
                await asyncio.sleep(delay)

        # 所有重试都失败
        for report in reports:
            await self._update_push_status(
                report, db, success=False, error=last_error
            )
        await db.commit()

        logger.error(
            "WeChat draft push failed after %d attempts: %s, report_ids=%s",
            self.retry_times,
            last_error,
            report_ids,
        )
        return {
            "success": False,
            "error": last_error,
            "report_ids": report_ids,
        }

    async def _update_push_status(
        self,
        report: Any,
        db: AsyncSession,
        *,
        success: bool,
        media_id: str = "",
        error: str = "",
    ) -> None:
        """Update the push status fields on a DailyReport.

        更新 DailyReport 的微信推送状态字段。

        Args:
            report: DailyReport instance.
            db: Database session.
            success: Whether push succeeded.
            media_id: Draft media_id (if success).
            error: Error message (if failed).
        """
        now = datetime.now(timezone.utc)

        if success:
            report.wechat_push_status = "success"
            report.wechat_draft_media_id = media_id
            report.wechat_push_error = None
            report.wechat_pushed_at = now
        else:
            report.wechat_push_status = "failed"
            report.wechat_push_error = error[:2000] if error else ""  # 截断过长的错误信息
            report.wechat_pushed_at = now

        db.add(report)
