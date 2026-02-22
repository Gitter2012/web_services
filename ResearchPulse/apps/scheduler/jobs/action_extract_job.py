# ==============================================================================
# 模块: ResearchPulse 行动项批量提取定时任务
# 作用: 定时扫描已经过 AI 处理但尚未提取行动项的文章，
#       自动从文章的 actionable_items 字段中提取结构化行动项记录。
# 架构角色: 数据处理流水线中 AI 处理之后的增值环节。
#           将 AI 输出的非结构化行动建议转化为可追踪的 ActionItem 记录。
# 前置条件: 需要在功能配置中启用 feature.action_items 开关。
# 执行方式: 由 APScheduler 的 IntervalTrigger 按固定间隔（默认每2小时）自动触发。
# ==============================================================================

"""Action item extraction scheduled job."""

from __future__ import annotations

import logging

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session_factory

logger = logging.getLogger(__name__)


async def run_action_extract_job() -> dict:
    """Extract action items from AI-processed articles.

    扫描已 AI 处理且重要性 >= 6 的文章，从中提取行动项。
    行动项归属于第一个超级管理员用户（系统级行动项）。

    Returns:
        dict: Extraction statistics.
    """
    from common.feature_config import feature_config

    if not feature_config.get_bool("feature.action_items", False):
        logger.info("Action items extraction disabled, skipping")
        return {"skipped": True, "reason": "feature disabled"}

    logger.info("Starting action item extraction job")

    session_factory = get_session_factory()
    extracted_total = 0
    articles_processed = 0

    async with session_factory() as session:
        try:
            # 获取系统用户（第一个 superuser）作为行动项 owner
            from core.models.user import User
            import core.models.permission  # noqa: F401 — ensure Role mapper is initialized
            user_result = await session.execute(
                select(User.id)
                .where(User.is_superuser.is_(True))
                .limit(1)
            )
            system_user_id = user_result.scalar()
            if not system_user_id:
                logger.warning("No superuser found, skipping action extraction")
                return {"skipped": True, "reason": "no superuser"}

            # 延迟导入
            from apps.crawler.models.article import Article
            from apps.action.models import ActionItem
            from apps.action.extractor import extract_actions_from_article

            batch_limit = feature_config.get_int("pipeline.action_batch_limit", 200)

            # 循环处理：每次取 batch_limit 篇文章，直到没有待处理文章为止
            while True:
                result = await session.execute(
                    select(Article.id)
                    .outerjoin(ActionItem, Article.id == ActionItem.article_id)
                    .where(
                        and_(
                            ActionItem.id.is_(None),
                            Article.ai_processed_at.isnot(None),
                            Article.is_archived.is_(False),
                            Article.importance_score >= 6,
                            Article.actionable_items.isnot(None),
                        )
                    )
                    .order_by(Article.crawl_time.desc())
                    .limit(batch_limit)
                )
                article_ids = [row[0] for row in result.all()]

                if not article_ids:
                    break

                # 逐篇提取行动项
                for article_id in article_ids:
                    try:
                        actions = await extract_actions_from_article(
                            article_id, system_user_id, session
                        )
                        extracted_total += len(actions)
                        articles_processed += 1
                    except Exception as e:
                        logger.warning(
                            f"Failed to extract actions from article {article_id}: {e}"
                        )

                # 每批次提交一次，避免长事务
                await session.commit()

                if len(article_ids) < batch_limit:
                    break

                logger.info(
                    f"Action extraction batch done ({len(article_ids)} articles), "
                    f"continuing next batch..."
                )

            # 将提取结果保存为 AIGC 文章
            if extracted_total > 0:
                await _save_action_aigc_article(
                    session, articles_processed, extracted_total
                )
                await session.commit()

        except Exception as e:
            logger.error(f"Action extraction job failed: {e}", exc_info=True)
            await session.rollback()
            return {"error": str(e), "articles_processed": articles_processed, "extracted": extracted_total}

    logger.info(
        f"Action extraction job completed: "
        f"{extracted_total} items from {articles_processed} articles"
    )
    return {"articles_processed": articles_processed, "extracted": extracted_total}


async def _save_action_aigc_article(
    session, articles_processed: int, extracted_total: int
) -> None:
    """Generate an AIGC summary article for action item extraction results."""
    from datetime import datetime, timezone
    from apps.aigc.article_writer import save_aigc_article

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    title = f"行动建议日报 - {today}"
    lines = [
        f"# {title}\n",
        f"本次从 **{articles_processed}** 篇文章中提取了 **{extracted_total}** 条行动项。\n",
    ]

    # Try to include recent action items
    try:
        from sqlalchemy import select
        from apps.action.models import ActionItem

        recent = await session.execute(
            select(ActionItem)
            .where(ActionItem.status == "pending")
            .order_by(ActionItem.id.desc())
            .limit(10)
        )
        items = recent.scalars().all()
        if items:
            lines.append("## 最新待处理行动项\n")
            lines.append("| 类型 | 优先级 | 描述 |")
            lines.append("|------|--------|------|")
            for item in items:
                desc = item.description[:80] + "..." if len(item.description) > 80 else item.description
                lines.append(f"| {item.type} | {item.priority} | {desc} |")
            lines.append("")
    except Exception:
        pass

    content = "\n".join(lines)
    await save_aigc_article(
        session,
        source_id="action_items",
        external_id=f"action_{today}",
        title=title,
        content=content,
        tags=["行动建议", "AIGC", today],
    )
