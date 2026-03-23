# =============================================================================
# 模块: apps/daily_digest/scorer.py
# 功能: 每日精选综合评分算法
# 架构角色: 评分层，负责为候选文章计算多维度综合评分
#
# 评分体系：
#   单篇文章评分 = Σ(分量_i × 权重_i) / 10
#   - importance  × 4.0  ← AI 重要性评分 (article.importance_score, 1-10)
#   - source      × 2.0  ← 来源质量权重 (SOURCE_WEIGHTS, 0-1)
#   - recency     × 2.0  ← 时效性衰减 (半衰期 18h)
#   - engagement  × 1.0  ← 互动热度 (同源内 log 归一化)
#   - cluster     × 1.0  ← 事件聚类热度加成
#
# 总分范围: [0, 10]
# =============================================================================

"""Daily digest scoring algorithm."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from apps.crawler.models.article import Article

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# 来源质量权重表（可通过配置调整）
# 值越高表示该来源信噪比越高
# -----------------------------------------------------------------------------
SOURCE_WEIGHTS: dict[str, float] = {
    "hackernews": 0.95,  # 技术社区精英过滤，信噪比极高
    "arxiv": 0.90,       # 学术严谨，内容质量稳定
    "twitter": 0.80,     # 实时性强，信息密度中等
    "rss": 0.80,         # 取决于源，默认中等
    "reddit": 0.75,      # 社区热度强，噪声较多
    "cn_news": 0.75,     # 中文资讯，质量中等
    "weibo": 0.65,       # 社交媒体，噪声较大
    "wechat": 0.70,      # 微信公众号，质量中等偏上
}

# 未知来源的默认权重
DEFAULT_SOURCE_WEIGHT: float = 0.70

# 时效性半衰期（小时）
RECENCY_HALF_LIFE_HOURS: float = 18.0

# 事件簇热度加成表（按簇内文章数映射 cluster 分量）
CLUSTER_HEAT_MAP: list[tuple[int, float]] = [
    (0, 0.20),   # 未聚类，孤立文章
    (1, 0.30),   # 仅自身
    (2, 0.55),   # 有跟进报道
    (4, 0.75),   # 话题扩散（3-4篇）
    (7, 0.90),   # 热点事件（5-7篇）
    (999, 1.00), # 全面热点（8+篇）
]

# 事件簇聚合热度乘数（文章数 → 乘数）
CLUSTER_MULTIPLIER_MAP: list[tuple[int, float]] = [
    (1, 1.00),   # 单篇，无加成
    (2, 1.05),   # 2篇
    (4, 1.10),   # 3-4篇
    (7, 1.15),   # 5-7篇
    (999, 1.20), # 8+篇
]

# 评分权重（总权重 = 10.0）
WEIGHT_IMPORTANCE: float = 4.0
WEIGHT_SOURCE: float = 2.0
WEIGHT_RECENCY: float = 2.0
WEIGHT_ENGAGEMENT: float = 1.0
WEIGHT_CLUSTER: float = 1.0


def get_cluster_heat_component(article_count: int) -> float:
    """根据簇内文章数返回 cluster 分量值 [0, 1]。

    Args:
        article_count: 簇内文章总数（0 表示未聚类）。

    Returns:
        float: cluster 分量 [0, 1]
    """
    result = 0.20
    for threshold, value in CLUSTER_HEAT_MAP:
        if article_count <= threshold:
            return value
        result = value
    return result


def get_cluster_multiplier(article_count: int) -> float:
    """根据簇内文章数返回聚合热度乘数。

    Args:
        article_count: 簇内文章总数。

    Returns:
        float: 热度乘数 [1.0, 1.2]
    """
    result = 1.00
    for threshold, multiplier in CLUSTER_MULTIPLIER_MAP:
        if article_count <= threshold:
            return multiplier
        result = multiplier
    return result


def compute_recency_component(publish_time: Optional[datetime], now: Optional[datetime] = None) -> float:
    """计算时效性分量（指数衰减）。

    f(t) = 2^(-t / half_life)，半衰期 RECENCY_HALF_LIFE_HOURS 小时。

    Args:
        publish_time: 文章发布时间（带时区）。
        now: 当前时间（可选，默认 UTC now）。

    Returns:
        float: 时效性分量 [0, 1]
    """
    if not publish_time:
        # 无发布时间时给予中等分
        return 0.5

    if now is None:
        now = datetime.now(timezone.utc)

    # 确保时区一致
    if publish_time.tzinfo is None:
        publish_time = publish_time.replace(tzinfo=timezone.utc)

    elapsed_hours = (now - publish_time).total_seconds() / 3600.0
    elapsed_hours = max(0.0, elapsed_hours)
    return math.pow(2.0, -elapsed_hours / RECENCY_HALF_LIFE_HOURS)


def compute_engagement_component(article: "Article", max_engagement_by_source: dict[str, float]) -> float:
    """计算互动热度分量（同源内 log 归一化）。

    避免微博高阅读量压制 arXiv 论文（无互动数据时给基础分）。

    Args:
        article: 文章对象。
        max_engagement_by_source: 各来源的最大互动数（用于归一化）。

    Returns:
        float: 互动热度分量 [0, 1]
    """
    source = article.source_type or "unknown"
    raw = 0.0

    # 获取互动指标（read_count + like_count，加权合并）
    read_count = getattr(article, "read_count", 0) or 0
    like_count = getattr(article, "like_count", 0) or 0
    raw = read_count + like_count * 3  # 点赞权重更高

    if raw <= 0:
        # 无互动数据时（arXiv/RSS 等学术源）给基础分 0.4，不惩罚
        return 0.4

    max_raw = max_engagement_by_source.get(source, 1.0)
    if max_raw <= 0:
        return 0.4

    # log 归一化：log1p(raw) / log1p(max_raw)
    normalized = math.log1p(raw) / math.log1p(max_raw)
    return min(1.0, normalized)


def compute_article_score(
    article: "Article",
    cluster_article_count: int,
    max_engagement_by_source: dict[str, float],
    now: Optional[datetime] = None,
) -> tuple[float, dict[str, float]]:
    """计算单篇文章综合评分及各分量细节。

    Args:
        article: 文章对象。
        cluster_article_count: 所属 EventCluster 的文章总数（0=未聚类）。
        max_engagement_by_source: 各来源最大互动数（归一化基准）。
        now: 当前时间（可选）。

    Returns:
        tuple: (composite_score [0-10], component_dict)
            component_dict 包含各分量及权重贡献。
    """
    # 1. importance 分量（直接使用 AI 评分，归一化到 [0, 1]）
    importance_raw = article.importance_score or 5
    importance_component = max(0.0, min(10.0, float(importance_raw))) / 10.0

    # 2. source 分量
    source_component = SOURCE_WEIGHTS.get(article.source_type or "", DEFAULT_SOURCE_WEIGHT)

    # 3. recency 分量
    recency_component = compute_recency_component(article.publish_time, now)

    # 4. engagement 分量
    engagement_component = compute_engagement_component(article, max_engagement_by_source)

    # 5. cluster 分量
    cluster_component = get_cluster_heat_component(cluster_article_count)

    # 加权求和，归一化到 [0, 10]
    composite_score = (
        importance_component * WEIGHT_IMPORTANCE
        + source_component * WEIGHT_SOURCE
        + recency_component * WEIGHT_RECENCY
        + engagement_component * WEIGHT_ENGAGEMENT
        + cluster_component * WEIGHT_CLUSTER
    )
    # 最大可能得分 = 1*4 + 1*2 + 1*2 + 1*1 + 1*1 = 10.0
    # 已经在 [0, 10] 范围内

    components = {
        "importance_component": round(importance_component, 4),
        "source_component": round(source_component, 4),
        "recency_component": round(recency_component, 4),
        "engagement_component": round(engagement_component, 4),
        "cluster_component": round(cluster_component, 4),
        "composite_score": round(composite_score, 4),
    }

    return composite_score, components


def score_articles(
    articles: list["Article"],
    cluster_map: dict[int, int],
    max_engagement_by_source: dict[str, float],
    now: Optional[datetime] = None,
) -> list[tuple["Article", float, dict[str, float]]]:
    """批量评分文章列表。

    Args:
        articles: 候选文章列表。
        cluster_map: {article_id: cluster_article_count}，未聚类文章值为 0。
        max_engagement_by_source: 各来源最大互动数。
        now: 当前时间（可选）。

    Returns:
        List of (article, composite_score, components), 按 composite_score 降序排序。
    """
    if now is None:
        now = datetime.now(timezone.utc)

    results = []
    for article in articles:
        cluster_count = cluster_map.get(article.id, 0)
        score, components = compute_article_score(
            article, cluster_count, max_engagement_by_source, now
        )
        results.append((article, score, components))

    # 按综合评分降序排序
    results.sort(key=lambda x: x[1], reverse=True)
    return results
