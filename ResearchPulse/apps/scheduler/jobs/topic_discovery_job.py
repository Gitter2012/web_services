# ==============================================================================
# 模块: ResearchPulse 主题发现定时任务
# 作用: 本模块负责定时从近期文章中自动发现新兴研究主题和热点趋势，
#       为用户提供研究领域的前沿动态感知能力。
# 架构角色: 数据分析流水线的高层洞察环节。
#           基于一段时间内的文章数据，通过统计分析和自然语言处理技术
#           识别出频繁出现的新主题，帮助用户发现值得关注的研究方向。
# 前置条件: 需要在功能配置中启用 feature.topic_radar 开关。
# 执行方式: 由 APScheduler 的 CronTrigger 每周定时触发（默认每周一凌晨1:00 AM）。
#           采用周级别执行频率的原因是主题发现需要积累足够的文章样本量才能产生有意义的结果。
# ==============================================================================

"""Topic discovery scheduled job for ResearchPulse."""

from __future__ import annotations

import logging

from core.database import get_session_factory
from settings import settings

logger = logging.getLogger(__name__)


async def run_topic_discovery_job() -> dict:
    """Discover new topics from recent articles.

    基于近期文章统计分析发现新兴研究主题与趋势。

    Returns:
        dict: Suggestions list and count, or skipped status when disabled.
    """
    # 功能: 分析近期文章内容，自动发现新兴研究主题和趋势
    # 参数: 无（回溯天数和最小频率阈值从 settings 中读取）
    # 返回值: dict - 包含主题发现结果:
    #   - suggestions_count: 发现的主题建议数量
    #   - suggestions: 主题建议列表（包含主题名称、频率、相关文章等信息）
    #   - 或 skipped=True 表示功能被禁用
    # 副作用: 主要为只读分析操作，不直接修改文章数据
    #         （但 TopicService.discover 内部可能会将发现结果持久化）

    # 延迟导入功能配置，避免模块加载时的循环依赖
    from common.feature_config import feature_config

    # 双重检查功能开关: 运行时再次确认主题发现功能是否仍然启用
    if not feature_config.get_bool("feature.topic_radar", False):
        logger.info("Topic discovery disabled, skipping")
        return {"skipped": True, "reason": "feature disabled"}

    logger.info("Starting topic discovery job")

    session_factory = get_session_factory()
    async with session_factory() as session:
        # 延迟导入主题发现服务，仅在功能启用且实际执行时才加载
        from apps.topic.service import TopicService

        # 创建主题发现服务实例
        service = TopicService()
        # 执行主题发现分析
        # days: 回溯分析的天数范围，决定了分析的时间窗口（如最近7天的文章）
        # min_frequency: 最小出现频率阈值，低于此频率的主题不会被纳入建议，
        #                用于过滤噪声，只保留有足够支撑度的主题
        suggestions = await service.discover(
            session,
            days=settings.topic_lookback_days,
            min_frequency=settings.topic_min_frequency,
        )

        # 将发现结果保存为 AIGC 文章
        if suggestions:
            await _save_topic_aigc_article(session, suggestions)
            await session.commit()

    logger.info(f"Topic discovery job completed: {len(suggestions)} suggestions found")
    # 返回发现的主题建议数量和详细列表
    return {"suggestions_count": len(suggestions), "suggestions": suggestions}


async def _save_topic_aigc_article(session, suggestions: list) -> None:
    """Generate an AIGC summary article for topic discovery results."""
    from datetime import datetime, timezone
    from apps.aigc.article_writer import save_aigc_article

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    count = len(suggestions)

    title = f"话题趋势日报 - {today}"
    lines = [
        f"# {title}\n",
        f"本次分析发现 **{count}** 个热门话题：\n",
        "| 排名 | 话题 | 关键词 | 频率 |",
        "|------|------|--------|------|",
    ]

    for i, s in enumerate(suggestions[:20], 1):
        name = s.get("name", s) if isinstance(s, dict) else str(s)
        keywords = ", ".join(s.get("keywords", [])) if isinstance(s, dict) else ""
        freq = s.get("frequency", "") if isinstance(s, dict) else ""
        lines.append(f"| {i} | {name} | {keywords} | {freq} |")

    lines.append("")
    content = "\n".join(lines)

    await save_aigc_article(
        session,
        source_id="topic_radar",
        external_id=f"topic_{today}",
        title=title,
        content=content,
        tags=["话题趋势", "AIGC", today],
    )
