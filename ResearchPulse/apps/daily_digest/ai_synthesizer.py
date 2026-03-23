# =============================================================================
# 模块: apps/daily_digest/ai_synthesizer.py
# 功能: 分层 AI 摘要合成（分类小结 + 全局洞察）
# 架构角色: AI 摘要层，复用 apps/ai_processor/providers/ 中已有的 Provider 抽象
#
# 分层成本控制：
#   - 单篇摘要：复用 article.one_liner，不调用 AI
#   - 分类小结：Ollama 本地模型，每类约 1-2 次调用
#   - 全局洞察：配置的优质模型，1次/天，~800 tokens
# =============================================================================

"""AI synthesis for daily digest: category summaries and global insight."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .selector import ScoredArticle

logger = logging.getLogger(__name__)

# 全局洞察最大输入标题数
MAX_TITLES_FOR_INSIGHT: int = 15

# 分类小结 prompt
CATEGORY_SUMMARY_PROMPT = """请用1-2句话总结以下{count}篇{category}领域文章的共同主题或趋势（纯文字，无markdown）：

{titles}"""

# 全局洞察 prompt
GLOBAL_INSIGHT_PROMPT = """你是一位科技领域分析师。以下是今日精选的{count}篇重要内容的标题和摘要。

请用3-5句话概括今日最重要的技术趋势和动态（纯文字，不超过200字，无markdown标记）：

{content}"""


async def _call_ai(prompt: str, provider_name: Optional[str] = None) -> Optional[str]:
    """调用 AI provider 生成文本。失败时返回 None（不中断流程）。"""
    try:
        from apps.ai_processor.service import get_ai_provider
        provider = get_ai_provider(provider_name)
        try:
            # 使用 translate 接口（纯文本生成，简单可靠）
            result = await provider.translate(prompt)
            return result
        finally:
            await provider.close()
    except Exception as e:
        logger.warning("AI synthesis call failed: %s", e)
        return None


async def generate_category_summary(
    category: str,
    scored_articles: list["ScoredArticle"],
    max_titles: int = 8,
) -> Optional[str]:
    """为某个分类生成 1-2 句话的小结。

    Args:
        category: 分类名称（如 "AI"）。
        scored_articles: 该分类下的精选文章列表。
        max_titles: 最多输入的标题数。

    Returns:
        Optional[str]: AI 生成的小结，失败时返回 None。
    """
    if not scored_articles:
        return None

    titles = []
    for sa in scored_articles[:max_titles]:
        title = sa.article.one_liner or sa.article.translated_title or sa.article.title or ""
        if title:
            titles.append(f"- {title}")

    if not titles:
        return None

    prompt = CATEGORY_SUMMARY_PROMPT.format(
        count=len(titles),
        category=category,
        titles="\n".join(titles),
    )

    return await _call_ai(prompt)


async def generate_global_insight(
    all_selected: list["ScoredArticle"],
) -> Optional[str]:
    """生成全局洞察段落（今日技术趋势，3-5句）。

    Args:
        all_selected: 所有精选文章列表（按全局 rank 排序）。

    Returns:
        Optional[str]: AI 生成的洞察段落，失败时返回 None。
    """
    if not all_selected:
        return None

    items = []
    for sa in all_selected[:MAX_TITLES_FOR_INSIGHT]:
        title = sa.article.translated_title or sa.article.title or ""
        one_liner = sa.article.one_liner or ""
        if title:
            item = f"- {title}"
            if one_liner:
                item += f"：{one_liner}"
            items.append(item)

    if not items:
        return None

    prompt = GLOBAL_INSIGHT_PROMPT.format(
        count=len(items),
        content="\n".join(items),
    )

    return await _call_ai(prompt)


async def generate_all_summaries(
    selected_by_category: dict[str, list["ScoredArticle"]],
    all_selected: list["ScoredArticle"],
) -> tuple[dict[str, Optional[str]], Optional[str]]:
    """并发生成所有分类小结和全局洞察。

    Args:
        selected_by_category: {category: [ScoredArticle, ...]}。
        all_selected: 全局精选列表。

    Returns:
        (category_summaries, global_insight)
            category_summaries: {category: summary_text or None}
            global_insight: str or None
    """
    # 并发生成各分类小结
    category_tasks = {
        cat: generate_category_summary(cat, articles)
        for cat, articles in selected_by_category.items()
        if articles
    }

    # 全局洞察（优先使用配置的优质模型）
    global_insight_task = generate_global_insight(all_selected)

    # 并发执行所有 AI 调用
    results = await asyncio.gather(
        *category_tasks.values(),
        global_insight_task,
        return_exceptions=True,
    )

    # 分割结果
    category_keys = list(category_tasks.keys())
    category_summaries: dict[str, Optional[str]] = {}
    for i, cat in enumerate(category_keys):
        result = results[i]
        if isinstance(result, Exception):
            logger.warning("Category summary failed for %s: %s", cat, result)
            category_summaries[cat] = None
        else:
            category_summaries[cat] = result

    global_result = results[-1] if results else None
    if isinstance(global_result, Exception):
        logger.warning("Global insight generation failed: %s", global_result)
        global_insight = None
    else:
        global_insight = global_result

    return category_summaries, global_insight
