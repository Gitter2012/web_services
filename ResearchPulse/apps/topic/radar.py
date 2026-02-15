# ==============================================================================
# 模块: topic/radar.py
# 功能: 话题雷达 - 话题追踪与分析引擎
# 架构角色: 提供两个核心功能:
#   1. match_article_to_topics - 将新文章匹配到已有话题, 建立关联关系
#   2. detect_trend - 检测话题在特定时间段内的热度变化趋势
# 设计说明:
#   - 文章匹配采用基于关键词的加权评分算法, 关键词列表中靠前的词权重更高
#   - 趋势检测通过对比当前周期与上一周期的文章数量来判断方向
# ==============================================================================
"""Topic radar for tracking and analyzing topics over time."""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from apps.crawler.models.article import Article
from .models import ArticleTopic, Topic, TopicSnapshot

# 初始化模块级日志记录器
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# match_article_to_topics - 将指定文章匹配到所有活跃话题
# 参数:
#   - article_id: 文章 ID
#   - db: 异步数据库会话
# 返回: 匹配结果列表, 每条包含 topic_id, topic_name, relevance, matched_keywords
# 副作用: 对于匹配成功且尚未关联的文章-话题对, 会创建 ArticleTopic 关联记录
#
# 匹配算法详解:
#   1. 获取文章的完整文本 (标题 + AI摘要/原始摘要 + 正文)
#   2. 遍历所有活跃话题, 检查其关键词是否出现在文章文本中
#   3. 每个命中的关键词贡献一个权重分数:
#      - 权重 = max(0.3, 1.0 - 关键词索引 * 0.05)
#      - 即列表中越靠前的关键词权重越高 (第一个权重 1.0, 逐步递减, 最低 0.3)
#   4. 相关度 = 总分 / 关键词总数, 上限 1.0
#   5. 如果命中 3 个及以上关键词, 相关度额外提升 20% (奖励多维度匹配)
#   6. 相关度阈值 > 0.3 才算有效匹配
# --------------------------------------------------------------------------
async def match_article_to_topics(article_id: int, db: AsyncSession) -> list[dict]:
    """Match an article to relevant topics."""
    from apps.crawler.models.article import Article
    # 查询目标文章
    art_result = await db.execute(select(Article).where(Article.id == article_id))
    article = art_result.scalar_one_or_none()
    if not article:
        return []
    # 查询所有活跃话题
    topics_result = await db.execute(select(Topic).where(Topic.is_active.is_(True)))
    topics = list(topics_result.scalars().all())
    # 将文章标题、摘要和正文拼接为待匹配文本, 转小写以实现大小写不敏感匹配
    text = f"{article.title} {article.ai_summary or article.summary or ''} {article.content or ''}".lower()
    matches = []
    for topic in topics:
        # 确保 keywords 是列表格式
        keywords = topic.keywords if isinstance(topic.keywords, list) else []
        if not keywords:
            continue
        matched = []  # 命中的关键词列表
        score = 0.0  # 累计匹配分数
        for i, kw in enumerate(keywords):
            if kw.lower() in text:
                # 关键词权重递减: 第一个关键词权重最高 (1.0), 之后每个递减 0.05, 最低 0.3
                # 这样设计是因为关键词列表通常按重要性排序, 靠前的更能代表话题核心
                weight = max(0.3, 1.0 - i * 0.05)
                score += weight
                matched.append(kw)
        if not matched:
            continue
        # 计算相关度: 累计分数 / 关键词总数, 归一化到 [0, 1]
        relevance = min(1.0, score / len(keywords))
        # 如果命中 3 个及以上关键词, 给予 1.2 倍加成奖励 (多维度匹配更可靠)
        if len(matched) >= 3:
            relevance = min(1.0, relevance * 1.2)
        # 相关度阈值判断: 仅保留相关度 > 0.3 的匹配
        if relevance > 0.3:
            # Check if association exists
            # 检查该文章-话题的关联关系是否已存在, 避免重复创建
            existing = await db.execute(
                select(ArticleTopic).where(and_(ArticleTopic.article_id == article_id, ArticleTopic.topic_id == topic.id))
            )
            if not existing.scalar_one_or_none():
                # 创建新的文章-话题关联记录
                assoc = ArticleTopic(article_id=article_id, topic_id=topic.id, match_score=round(relevance, 3), matched_keywords=matched)
                db.add(assoc)
            matches.append({"topic_id": topic.id, "topic_name": topic.name, "relevance": round(relevance, 3), "matched_keywords": matched})
    return matches

# --------------------------------------------------------------------------
# detect_trend - 检测话题的热度变化趋势
# 参数:
#   - topic_id: 话题 ID
#   - db: 异步数据库会话
#   - period_days: 统计周期天数, 默认 7 天
# 返回: 趋势信息字典:
#   - direction: 趋势方向 ("up" / "down" / "stable")
#   - change_percent: 变化百分比
#   - current_count: 当前周期文章数
#   - previous_count: 上一周期文章数
#
# 算法逻辑:
#   1. 将时间划分为两个等长周期: 当前周期和上一周期
#   2. 分别统计两个周期内与该话题关联的文章数量
#   3. 计算变化百分比: (当前 - 上一周期) / 上一周期 * 100
#   4. 特殊情况: 上一周期为 0 时, 若当前有文章则变化为 100%, 否则为 0%
#   5. 根据变化百分比判断方向: >20% 为上升, <-20% 为下降, 其余为平稳
# 设计说明: 20% 的阈值避免了小波动被误判为趋势变化
# --------------------------------------------------------------------------
async def detect_trend(topic_id: int, db: AsyncSession, period_days: int = 7) -> dict:
    """Detect trend for a topic."""
    now = datetime.now(timezone.utc)
    # 当前周期: 从 period_days 天前到现在
    current_start = now - timedelta(days=period_days)
    # 上一周期: 从 2 * period_days 天前到 period_days 天前
    previous_start = current_start - timedelta(days=period_days)

    # 统计当前周期内关联该话题的文章数量
    current_result = await db.execute(
        select(func.count()).select_from(ArticleTopic).join(Article, ArticleTopic.article_id == Article.id)
        .where(and_(ArticleTopic.topic_id == topic_id, Article.crawl_time >= current_start))
    )
    current_count = current_result.scalar() or 0

    # 统计上一周期内关联该话题的文章数量
    previous_result = await db.execute(
        select(func.count()).select_from(ArticleTopic).join(Article, ArticleTopic.article_id == Article.id)
        .where(and_(ArticleTopic.topic_id == topic_id, Article.crawl_time >= previous_start, Article.crawl_time < current_start))
    )
    previous_count = previous_result.scalar() or 0

    # 计算变化百分比
    if previous_count == 0:
        # 上一周期无文章: 当前有文章视为 100% 增长, 否则为 0%
        change = 100.0 if current_count > 0 else 0.0
    else:
        change = ((current_count - previous_count) / previous_count) * 100

    # 根据变化百分比判断趋势方向, 使用 20% 作为变化阈值
    direction = "up" if change > 20 else ("down" if change < -20 else "stable")
    return {"direction": direction, "change_percent": round(change, 1), "current_count": current_count, "previous_count": previous_count}
