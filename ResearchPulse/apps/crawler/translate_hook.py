# =============================================================================
# 模块: apps/crawler/translate_hook.py
# 功能: 抓取后翻译钩子，在爬虫完成后自动翻译 arXiv 英文标题和摘要
# 架构角色: 爬虫子系统的后置处理钩子
# 设计理念:
#   1. 流程独立：抓取后立即翻译，不等待 AI 处理流程
#   2. 配置依赖：需要 feature.ai_processor 开启才能使用 AI Provider
#   3. 轻量级：委托给 apps/ai_processor/article_translate.py，不重复实现
# =============================================================================

"""Post-crawl translation hook for ResearchPulse.

This module provides a translation hook that runs after crawling completes.
It translates arXiv English titles and summaries to Chinese.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def translate_after_crawl(article_ids: list[int]) -> dict[str, Any]:
    """Translate newly crawled articles if AI processor is enabled.

    抓取后翻译钩子：检查配置后翻译指定文章的英文标题和摘要。

    设计原则：
    - 流程独立：抓取后立即翻译，不等待 AI 处理流程
    - 配置依赖：需要 feature.ai_processor 开启才能使用 AI Provider

    Args:
        article_ids: List of newly saved article IDs.

    Returns:
        dict: Translation statistics or skipped status.
            - skipped: True if translation was skipped
            - reason: Reason for skipping
            - translated_titles: Number of titles translated
            - translated_summaries: Number of summaries translated
            - total: Total articles processed
    """
    from common.feature_config import feature_config

    # 检查 AI 处理开关（配置依赖）
    # 翻译需要 AI Provider，所以依赖 feature.ai_processor
    if not feature_config.get_bool("feature.ai_processor", False):
        logger.debug("Translation skipped: feature.ai_processor disabled")
        return {"skipped": True, "reason": "feature.ai_processor disabled"}

    if not article_ids:
        return {"skipped": True, "reason": "no articles to translate"}

    # 使用 ai_processor 层的翻译逻辑
    try:
        from apps.ai_processor.article_translate import translate_articles

        logger.info(f"Post-crawl translation starting for {len(article_ids)} articles")
        result = await translate_articles(article_ids=article_ids)

        if not result.get("error"):
            logger.info(
                f"Post-crawl translation completed: "
                f"{result.get('translated_titles', 0)} titles, "
                f"{result.get('translated_summaries', 0)} summaries"
            )

        return result

    except Exception as e:
        logger.error(f"Translation hook failed: {e}")
        return {"error": str(e), "translated_titles": 0, "translated_summaries": 0, "total": 0}
