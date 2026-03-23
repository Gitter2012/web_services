# =============================================================================
# 模块: apps/daily_digest/selector.py
# 功能: 精选逻辑 —— Top-N 多样性约束选取
# 架构角色: 选取层，在综合评分基础上施加多样性约束，生成最终精选列表
#
# 三阶段选取：
#   阶段一：事件簇热点优先（Cluster-first）
#   阶段二：全局排名 + 多样性约束（Global Top-N）
#   阶段三：关联文章附加（不占排名名额）
# =============================================================================

"""Daily digest article selection with diversity constraints."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from apps.crawler.models.article import Article

logger = logging.getLogger(__name__)

# 默认精选排名位数
DEFAULT_TOP_N: int = 25

# 多样性约束
MAX_SOURCE_RATIO: float = 0.30   # 单来源 ≤ 30%
MAX_CATEGORY_RATIO: float = 0.40  # 单分类 ≤ 40%

# 每个 Cluster 最多附带的关联文章数
MAX_RELATED_PER_CLUSTER: int = 2


@dataclass
class ScoredArticle:
    """带评分的文章，用于选取逻辑。"""
    article: "Article"
    composite_score: float
    components: dict[str, float]
    cluster_id: Optional[int] = None
    cluster_article_count: int = 0
    display_category: str = "其他"
    rank: int = 0
    category_rank: int = 0
    # 关联文章（对于 cluster 代表文章）
    related_articles: list["ScoredArticle"] = field(default_factory=list)


def _get_display_category(article: "Article") -> str:
    """获取文章的展示分类（优先使用 AI 分类）。"""
    return article.ai_category or article.category or "其他"


def select_top_n(
    scored_articles: list[tuple["Article", float, dict[str, float]]],
    cluster_members: dict[int, list[int]],
    article_cluster_map: dict[int, int],
    top_n: int = DEFAULT_TOP_N,
) -> list[ScoredArticle]:
    """从已评分文章中按三阶段逻辑精选 Top-N 篇。

    Args:
        scored_articles: 已排序的 (article, score, components) 列表（降序）。
        cluster_members: {cluster_id: [article_id, ...]}，簇内所有文章 ID。
        article_cluster_map: {article_id: cluster_id}。
        top_n: 精选排名位数（默认 25）。

    Returns:
        List[ScoredArticle]，按全局 rank 排列，代表文章含 related_articles。
    """
    if not scored_articles:
        return []

    # 构建 article_id -> ScoredArticle 映射
    article_id_to_scored: dict[int, ScoredArticle] = {}
    for article, score, components in scored_articles:
        cluster_id = article_cluster_map.get(article.id)
        cluster_count = 0
        if cluster_id is not None:
            cluster_count = len(cluster_members.get(cluster_id, []))
        sa = ScoredArticle(
            article=article,
            composite_score=score,
            components=components,
            cluster_id=cluster_id,
            cluster_article_count=cluster_count,
            display_category=_get_display_category(article),
        )
        article_id_to_scored[article.id] = sa

    # -------------------------------------------------------------------------
    # 阶段一：为每个 Cluster 确定代表文章和关联文章
    # -------------------------------------------------------------------------
    # cluster_id -> (primary_article_id, [related_article_id, ...])
    cluster_primary: dict[int, int] = {}
    cluster_related: dict[int, list[int]] = {}
    processed_cluster_ids: set[int] = set()

    # 按评分顺序遍历，为每个 cluster 的第一次出现的文章设为 primary
    for article, score, _ in scored_articles:
        aid = article.id
        cid = article_cluster_map.get(aid)
        if cid is None:
            continue  # 孤立文章，跳过 cluster 处理
        if cid not in processed_cluster_ids:
            cluster_primary[cid] = aid
            cluster_related[cid] = []
            processed_cluster_ids.add(cid)
        elif len(cluster_related.get(cid, [])) < MAX_RELATED_PER_CLUSTER:
            cluster_related[cid].append(aid)

    # 挂载 related_articles 到代表文章
    for cid, primary_aid in cluster_primary.items():
        primary_sa = article_id_to_scored.get(primary_aid)
        if primary_sa is None:
            continue
        for related_aid in cluster_related.get(cid, []):
            related_sa = article_id_to_scored.get(related_aid)
            if related_sa is not None:
                primary_sa.related_articles.append(related_sa)

    # -------------------------------------------------------------------------
    # 阶段二：全局排名 + 多样性约束
    # 参与排名的单元：代表文章（含关联文章的簇）+ 孤立文章
    # 已被标记为 related 的文章不参与全局排名
    # -------------------------------------------------------------------------
    # 所有 related article IDs（不参与全局排名）
    all_related_aids: set[int] = set()
    for related_list in cluster_related.values():
        all_related_aids.update(related_list)

    # 参与排名的候选（按评分降序，已由 scored_articles 保证）
    ranking_candidates: list[ScoredArticle] = []
    seen_cluster_primary: set[int] = set()  # 每个 cluster 只让 primary 参与一次

    for article, score, _ in scored_articles:
        aid = article.id
        sa = article_id_to_scored.get(aid)
        if sa is None:
            continue

        cid = sa.cluster_id
        if aid in all_related_aids:
            continue  # 关联文章不参与全局排名

        if cid is not None:
            if cid in seen_cluster_primary:
                continue  # 同一 cluster 只保留评分最高的代表
            seen_cluster_primary.add(cid)

        ranking_candidates.append(sa)

    # 多样性约束贪心选取
    selected: list[ScoredArticle] = []
    source_count: dict[str, int] = {}
    category_count: dict[str, int] = {}

    def _can_add(sa: ScoredArticle, current_n: int) -> bool:
        """检查是否可以在当前已选 current_n 个的情况下再加入 sa（多样性约束）。"""
        if current_n == 0:
            return True
        max_src = max(1, int(top_n * MAX_SOURCE_RATIO))
        max_cat = max(1, int(top_n * MAX_CATEGORY_RATIO))
        src = sa.article.source_type or "unknown"
        cat = sa.display_category
        if source_count.get(src, 0) >= max_src:
            return False
        if category_count.get(cat, 0) >= max_cat:
            return False
        return True

    # 先按约束选取
    deferred: list[ScoredArticle] = []
    for sa in ranking_candidates:
        if len(selected) >= top_n:
            break
        if _can_add(sa, len(selected)):
            selected.append(sa)
            src = sa.article.source_type or "unknown"
            cat = sa.display_category
            source_count[src] = source_count.get(src, 0) + 1
            category_count[cat] = category_count.get(cat, 0) + 1
        else:
            deferred.append(sa)

    # 如果不足 top_n，放宽约束补足
    if len(selected) < top_n:
        for sa in deferred:
            if len(selected) >= top_n:
                break
            if sa not in selected:
                selected.append(sa)

    # -------------------------------------------------------------------------
    # 阶段三：分配全局 rank 和 category_rank
    # -------------------------------------------------------------------------
    category_rank_counter: dict[str, int] = {}
    for i, sa in enumerate(selected):
        sa.rank = i + 1
        cat = sa.display_category
        category_rank_counter[cat] = category_rank_counter.get(cat, 0) + 1
        sa.category_rank = category_rank_counter[cat]

        # 关联文章分配 category_rank（相对 primary）
        for j, rsa in enumerate(sa.related_articles):
            rsa.rank = 0  # 不占全局排名
            rsa.category_rank = j + 1

    logger.info(
        "Digest selection: %d candidates → %d selected (top_n=%d, sources=%d, clusters=%d)",
        len(ranking_candidates),
        len(selected),
        top_n,
        len(seen_cluster_primary),
        len(processed_cluster_ids),
    )
    return selected
