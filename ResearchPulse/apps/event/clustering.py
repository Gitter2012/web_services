# =============================================================================
# Event 聚类算法模块
# =============================================================================
# 本模块实现了事件聚类的核心算法。
# 在架构中的角色：
#   - 提供文章与事件聚类之间的匹配分数计算
#   - 提供文本的实体提取、关键词提取、标题相似度计算等工具
#
# 匹配分数计算策略（compute_cluster_score）：
#   总分 = 模型名匹配分 + 标题相似度分 + 实体重叠分 + 关键词重叠分 + 分类一致性分
#   - 模型名匹配（权重最高，0.40-0.50）：AI 模型名称完全匹配
#   - 标题相似度（0.35 * Jaccard）：基于关键词的 Jaccard 相似度
#   - 实体重叠（最高 0.40）：命名实体的交集数量
#   - 关键词重叠（最高 0.10）：通用关键词的交集
#   - 分类一致性（0.05）：文章和聚类分类相同的加分
#
# 性能优化：
#   - 使用 @lru_cache 缓存实体提取、关键词提取和标题规范化结果
#   - 避免对相同文本重复计算
# =============================================================================

"""Event clustering algorithm."""
from __future__ import annotations
import logging
import re
from datetime import datetime, timezone
from functools import lru_cache

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# 命名实体识别正则模式
# 覆盖主要的科技公司、AI 实验室、AI 产品/模型、中国科技公司、
# 以及中英文的关键行为动词
# -----------------------------------------------------------------------------
_ENTITY_PATTERNS = [
    r"\b(OpenAI|Google|Microsoft|Meta|Apple|Amazon|Tesla|Anthropic|Nvidia|AMD|Intel)\b",
    r"\b(DeepMind|Stability|Hugging\s*Face|Cohere|Mistral|xAI|Perplexity)\b",
    r"\b(GPT-[\d.]+|Claude|Gemini|Llama|ChatGPT|Copilot|DALL-E|Midjourney|Stable\s*Diffusion)\b",
    r"\b(Sora|Grok|Flux|DeepSeek|Qwen|Yi|Kimi)\b",
    r"(阿里巴巴|腾讯|百度|字节跳动|华为|小米|京东|美团)",
    r"(发布|上线|宣布|收购|融资|IPO|裁员|合并|开源|升级|更新)",
    r"\b(launch|release|announce|acquire|funding|merger|layoff|update)\b",
]

# AI 模型名称的详细正则模式
# 用于精确匹配各种 AI 模型的版本号命名格式
_MODEL_NAME_PATTERN = re.compile(
    r"\b(Step[- ]?[\d.]+[- ]?\w+|GLM[- ]?(?:[\d.]+|OCR|V\d+)|GPT[- ]?[\d.]+|"
    r"DeepSeek[- ]?v?[\d.]+|Qwen[- ]?[\d.]+|Llama[- ]?[\d.]+|Claude[- ]?[\d.]+|"
    r"Gemini[- ]?[\d.]+)\b", re.IGNORECASE
)

# 停用词集合：在关键词提取时过滤掉的常见功能词
# 包含英文和中文停用词
_STOPWORDS = {"the", "a", "an", "is", "are", "was", "were", "be", "to", "of", "in", "for", "on", "with", "at", "by", "from", "as", "and", "or", "but", "if", "so", "just", "have", "has", "do", "does", "的", "是", "在", "了", "和", "与"}


@lru_cache(maxsize=1024)
def extract_entities(text: str) -> frozenset[str]:
    """Extract named entities from text."""
    # 从文本中提取命名实体
    # 使用预定义的正则模式匹配公司名、产品名、行为动词等
    # 参数：text - 待提取的文本
    # 返回值：提取到的实体集合（小写、不可变集合，支持 LRU 缓存）
    entities = set()
    for pattern in _ENTITY_PATTERNS:
        for m in re.findall(pattern, text, re.IGNORECASE):
            if isinstance(m, str):
                entities.add(m.lower())
            elif isinstance(m, tuple):
                # 多个捕获组时，取第一个非空的
                for g in m:
                    if g:
                        entities.add(g.lower())
                        break
    return frozenset(entities)


@lru_cache(maxsize=1024)
def extract_keywords(text: str) -> frozenset[str]:
    """Extract keywords from text."""
    # 从文本中提取关键词
    # 提取逻辑：
    #   1. 先提取 AI 模型名称（特殊处理）
    #   2. 用正则提取中文词和英文单词
    #   3. 过滤掉单字符和停用词
    # 返回值：关键词集合（小写、不可变）
    model_names = set()
    for match in _MODEL_NAME_PATTERN.finditer(text):
        model_names.add(match.group(1).lower())
    # 提取中文连续字符和英文/数字单词
    words = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+", text.lower())
    # 过滤：长度 > 1 且不在停用词表中
    keywords = frozenset(w for w in words if len(w) > 1 and w not in _STOPWORDS)
    return keywords | frozenset(model_names)


@lru_cache(maxsize=1024)
def extract_model_names(text: str) -> frozenset[str]:
    """Extract AI model names from text."""
    # 从文本中精确提取 AI 模型名称
    # 同时保存原始格式和去除分隔符的格式（如 "GPT-4o" 和 "gpt4o"）
    # 这样可以处理不同来源中模型名称格式不一致的情况
    models = set()
    for match in _MODEL_NAME_PATTERN.finditer(text):
        models.add(match.group(1).lower())
        # 去除分隔符的变体，提高匹配成功率
        models.add(re.sub(r"[- ]+", "", match.group(1).lower()))
    return frozenset(models)


def calculate_title_similarity(title1: str, title2: str) -> float:
    """Calculate Jaccard similarity between two titles."""
    # 计算两个标题之间的 Jaccard 相似度
    # Jaccard 系数 = |A ∩ B| / |A ∪ B|
    # 先对标题进行规范化处理，再基于关键词集合计算
    if not title1 or not title2:
        return 0.0
    # 规范化标题：去除前缀、URL 等噪声
    norm1 = _normalize_title(title1)
    norm2 = _normalize_title(title2)
    # 完全相同的标题直接返回 1.0
    if norm1 == norm2:
        return 1.0
    # 提取关键词并计算 Jaccard 系数
    kw1 = extract_keywords(norm1)
    kw2 = extract_keywords(norm2)
    if not kw1 or not kw2:
        return 0.0
    intersection = len(kw1 & kw2)  # 交集大小
    union = len(kw1 | kw2)         # 并集大小
    return intersection / union if union > 0 else 0.0


@lru_cache(maxsize=1024)
def _normalize_title(text: str) -> str:
    """Normalize title for comparison."""
    # 规范化标题，去除噪声以提高比较准确性
    # 处理步骤：
    #   1. 去除 RT（转发）前缀
    #   2. 去除 HN 风格前缀（Ask/Show/Tell/Launch HN）
    #   3. 去除 @用户名 前缀
    #   4. 去除 URL
    #   5. 合并连续空格并转小写
    if not text:
        return ""
    text = re.sub(r"^RT\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(Ask|Show|Tell|Launch) HN[:\s]+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^@\w+[:\s]+", "", text)
    text = re.sub(r"https?://\S+", "", text)
    return " ".join(text.split()).strip().lower()


def compute_cluster_score(
    item_title: str,
    item_content: str,
    cluster_title: str,
    item_category: str = "",
    cluster_category: str = "",
) -> tuple[float, str]:
    """Compute matching score between an article and a cluster.
    Returns (score, method).
    """
    # 计算文章与事件聚类之间的匹配分数
    # 参数：
    #   item_title: 文章标题
    #   item_content: 文章内容
    #   cluster_title: 事件聚类标题
    #   item_category: 文章分类
    #   cluster_category: 聚类分类
    # 返回值：(总分, 主要匹配方法)
    #
    # 评分维度及权重：
    #   1. AI 模型名匹配: 0.40-0.50（最强信号，如两篇文章都提到 "GPT-5"）
    #   2. 标题相似度: 0.35 * Jaccard（标题关键词重叠）
    #   3. 实体重叠: 最高 0.40（公司/产品名等命名实体）
    #   4. 关键词重叠: 最高 0.10（通用关键词）
    #   5. 分类一致性: 0.05（同分类加分）

    score = 0.0
    method = "keyword"  # 默认匹配方法

    # 合并标题和内容用于实体提取
    item_text = f"{item_title} {item_content or ''}"

    # ---- 维度 1：AI 模型名称匹配 ----
    # 如果文章和聚类都提到相同的 AI 模型名，这是很强的关联信号
    item_models = extract_model_names(item_title)
    cluster_models = extract_model_names(cluster_title)
    model_overlap = item_models & cluster_models
    if model_overlap:
        score += 0.40 if len(model_overlap) == 1 else 0.50  # 多个模型匹配给更高分
        method = "model"

    # ---- 维度 2：标题相似度 ----
    title_sim = calculate_title_similarity(item_title, cluster_title)
    if title_sim > 0:
        score += 0.35 * title_sim
        # 标题高度相似（>= 0.8）时标记匹配方法为 title
        if title_sim >= 0.8 and method == "keyword":
            method = "title"

    # ---- 维度 3：命名实体重叠 ----
    item_entities = extract_entities(item_text)
    cluster_entities = extract_entities(cluster_title)
    entity_overlap = item_entities & cluster_entities
    if entity_overlap:
        # 实体重叠分数随重叠数量增长，最多 3 个
        entity_score = 0.25 * min(len(entity_overlap), 3) / 3
        # 两个以上实体重叠给额外奖励
        if len(entity_overlap) >= 2:
            entity_score += 0.15
        score += entity_score
        if entity_score > 0.2 and method == "keyword":
            method = "entity"

    # ---- 维度 4：关键词重叠 ----
    item_keywords = extract_keywords(item_title)
    cluster_keywords = extract_keywords(cluster_title)
    keyword_overlap = item_keywords & cluster_keywords
    if keyword_overlap:
        # 关键词重叠分数，最多计 5 个关键词
        score += 0.10 * min(len(keyword_overlap), 5) / 5

    # ---- 维度 5：分类一致性 ----
    # 文章和聚类属于同一分类时给予小幅加分
    if item_category and cluster_category == item_category:
        score += 0.05

    return score, method
