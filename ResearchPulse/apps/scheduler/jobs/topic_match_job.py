# ==============================================================================
# 模块: ResearchPulse 话题匹配定时任务
# 作用: 本模块负责定时将文章匹配到已有话题，建立文章与话题的关联关系。
# 架构角色: 数据分析流水线的关联环节，连接文章内容与话题标签。
# 前置条件: 需要在功能配置中启用 feature.topic_radar 开关。
# 执行方式: 由 APScheduler 的 IntervalTrigger 定时触发（默认每 2 小时）。
#           也可通过管理后台 API 手动触发。
# ==============================================================================

"""Topic match scheduled job for ResearchPulse."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select, outerjoin
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session_factory
from common.feature_config import feature_config

logger = logging.getLogger(__name__)


async def run_topic_match_job(
    days: int | None = None,
    limit: int | None = None,
) -> dict:
    """Match articles to existing topics.

    批量将文章匹配到已有话题，建立文章-话题关联关系。

    策略：查找最近 N 天内爬取且尚未关联任何话题的文章，
    调用 match_article_to_topics 进行匹配，创建 ArticleTopic 关联记录。

    Args:
        days: 回溯天数，从配置读取，默认 7 天
        limit: 单次处理文章数量上限，从配置读取，默认 500

    Returns:
        dict: 匹配结果统计:
            - matched_count: 成功匹配的文章数
            - total_processed: 处理的文章总数
            - associations_created: 创建的关联数
            - skipped: True 表示功能被禁用
    """
    # 功能开关检查
    if not feature_config.get_bool("feature.topic_match", False):
        logger.info("Topic match disabled, skipping")
        return {"skipped": True, "reason": "feature disabled"}

    # 从配置读取参数
    if days is None:
        days = feature_config.get_int("scheduler.topic_match_days", 7)
    if limit is None:
        limit = feature_config.get_int("scheduler.topic_match_limit", 500)

    logger.info(f"Starting topic match job: days={days}, limit={limit}")

    session_factory = get_session_factory()
    matched_count = 0
    total_processed = 0
    associations_created = 0

    async with session_factory() as session:
        # 查询待匹配的文章：
        # 条件：最近 N 天内爬取 AND 无话题关联记录
        from apps.crawler.models.article import Article
        from apps.topic.models import ArticleTopic, Topic

        # 计算时间阈值
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)

        # 子查询：已有关联的文章 ID
        # 使用 NOT EXISTS 或 LEFT JOIN + IS NULL 查找未关联文章
        subquery = select(ArticleTopic.article_id).where(
            ArticleTopic.article_id.isnot(None)
        ).distinct()

        # 主查询：未关联话题的文章
        result = await session.execute(
            select(Article)
            .where(
                and_(
                    Article.crawl_time >= cutoff_time,
                    Article.id.notin_(subquery),
                )
            )
            .order_by(Article.crawl_time.desc())
            .limit(limit)
        )
        articles = list(result.scalars().all())

        if not articles:
            logger.info("No articles to match")
            return {
                "matched_count": 0,
                "total_processed": 0,
                "associations_created": 0,
                "message": "No articles to match",
            }

        logger.info(f"Found {len(articles)} articles to process")

        # 导入匹配函数
        from apps.topic.radar import match_article_to_topics

        # 逐篇匹配
        for article in articles:
            total_processed += 1
            try:
                matches = await match_article_to_topics(article.id, session)
                if matches:
                    matched_count += 1
                    associations_created += len(matches)
                    logger.debug(
                        f"Article {article.id} matched to {len(matches)} topics"
                    )
            except Exception as e:
                logger.warning(f"Failed to match article {article.id}: {e}")
                continue

        # 提交所有关联
        await session.commit()

    logger.info(
        f"Topic match job completed: "
        f"matched={matched_count}/{total_processed}, "
        f"associations={associations_created}"
    )

    return {
        "matched_count": matched_count,
        "total_processed": total_processed,
        "associations_created": associations_created,
    }
