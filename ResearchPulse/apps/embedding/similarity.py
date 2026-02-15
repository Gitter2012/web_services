# =============================================================================
# 相似度计算工具模块
# =============================================================================
# 本模块提供了向量相似度计算的工具函数。
# 在架构中的角色：
#   - 提供纯函数形式的相似度计算工具
#   - 支持规则分数和语义分数的混合计算
# 这些函数可被 Event 聚类、相似文章推荐等多个模块复用。
# =============================================================================

"""Similarity computation utilities."""

from __future__ import annotations


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    计算两个向量之间的余弦相似度。

    Args:
        vec1: First vector.
        vec2: Second vector.

    Returns:
        float: Similarity score in [-1, 1].
    """
    # 计算两个向量之间的余弦相似度
    # 公式：cos(theta) = (A . B) / (||A|| * ||B||)
    # 参数：
    #   vec1: 第一个向量
    #   vec2: 第二个向量
    # 返回值：相似度分数，范围 [-1, 1]，值越大表示越相似
    dot_product = sum(a * b for a, b in zip(vec1, vec2))  # 计算点积
    norm1 = sum(a * a for a in vec1) ** 0.5               # 计算第一个向量的范数
    norm2 = sum(b * b for b in vec2) ** 0.5               # 计算第二个向量的范数
    # 零向量保护：避免除以零
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot_product / (norm1 * norm2)


def compute_hybrid_similarity(
    rule_score: float,
    semantic_score: float,
    rule_weight: float = 0.4,
    semantic_weight: float = 0.6,
    embeddings_available: bool = True,
) -> float:
    """Compute hybrid similarity combining rule-based and semantic scores.

    计算规则分数与语义分数的加权混合相似度。

    Args:
        rule_score: Rule-based similarity score.
        semantic_score: Semantic similarity score.
        rule_weight: Weight for rule score.
        semantic_weight: Weight for semantic score.
        embeddings_available: Whether embeddings are available.

    Returns:
        float: Hybrid similarity score.
    """
    # 计算混合相似度：将规则分数和语义分数按权重加权组合
    # 参数：
    #   rule_score: 基于规则的相似度分数（关键词匹配、实体匹配等）
    #   semantic_score: 基于语义向量的相似度分数
    #   rule_weight: 规则分数的权重，默认 0.4
    #   semantic_weight: 语义分数的权重，默认 0.6
    #   embeddings_available: 嵌入系统是否可用
    # 返回值：混合相似度分数
    #
    # 设计决策：语义分数权重（0.6）高于规则分数（0.4），
    # 因为语义相似度能捕捉更深层的内容关联。
    # 当嵌入系统不可用时，退化为纯规则分数。
    if not embeddings_available and semantic_score == 0.0:
        return rule_score  # 嵌入不可用时仅使用规则分数
    return rule_weight * rule_score + semantic_weight * semantic_score
