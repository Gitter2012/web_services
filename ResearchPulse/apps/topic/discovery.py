# ==============================================================================
# 模块: topic/discovery.py
# 功能: 话题自动发现引擎
# 架构角色: 负责从近期已处理的文章中自动发现潜在的新话题候选。
#           采用两种互补的策略:
#   1. 实体识别 (Entity Extraction) - 通过预定义的正则表达式匹配知名实体
#   2. 二元词组提取 (Bigram Extraction) - 提取高频的中英文词组作为关键词候选
# 设计说明:
#   - 实体识别覆盖了 AI 行业的主要公司、产品和人物, 包括中英文实体
#   - 二元词组提取作为实体识别的补充, 可以发现更细粒度的技术趋势
#   - 两种策略的结果会合并去重, 按置信度和频率的综合得分排序
# ==============================================================================
"""Automatic topic discovery."""
from __future__ import annotations
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from apps.crawler.models.article import Article
from .models import Topic

# 初始化模块级日志记录器
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# 实体识别正则表达式模式列表
# 每组正则覆盖一类实体:
#   1. 国际科技巨头: OpenAI, Google, Microsoft, Meta 等
#   2. AI 领域公司: DeepMind, Stability AI, Hugging Face 等
#   3. 中国科技公司: 阿里巴巴, 腾讯, 百度, 字节跳动 等
#   4. AI 产品/模型: GPT-4, Claude, Gemini, Llama, ChatGPT 等
#   5. 关键人物: Sam Altman, Elon Musk, Jensen Huang
# 设计说明: 使用 re.IGNORECASE 忽略大小写, 提高匹配的容错性
# --------------------------------------------------------------------------
_ENTITY_PATTERNS = [
    r"\b(OpenAI|Google|Microsoft|Meta|Apple|Amazon|Tesla|Anthropic|Nvidia)\b",
    r"\b(DeepMind|Stability\s*AI|Hugging\s*Face|Cohere|Mistral|xAI|Perplexity)\b",
    r"(阿里巴巴|腾讯|百度|字节跳动|华为|小米|京东|美团|商汤|智谱|月之暗面)",
    r"\b(GPT-\d+[a-z]*|Claude|Gemini|Llama\s*\d*|ChatGPT|Sora|Grok|DeepSeek|Qwen|Kimi)\b",
    r"\b(Sam\s*Altman|Elon\s*Musk|Jensen\s*Huang)\b",
]
# 预编译所有正则表达式, 避免每次调用时重复编译, 提升性能
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _ENTITY_PATTERNS]

# --------------------------------------------------------------------------
# _extract_entities - 从文本中提取已知实体
# 参数:
#   - text: 待分析的文本内容
# 返回: 识别到的实体名称列表 (可能包含重复)
# 逻辑:
#   - 遍历所有预编译的正则模式
#   - 对每个模式的匹配结果, 处理字符串和元组两种返回格式
#   - 元组格式来自正则中的多个捕获组, 取第一个非空组作为结果
# --------------------------------------------------------------------------
def _extract_entities(text: str) -> list[str]:
    entities = []
    for pattern in _COMPILED:
        for m in pattern.findall(text):
            if isinstance(m, str):
                # 单捕获组的匹配结果, 直接添加
                entities.append(m.strip())
            elif isinstance(m, tuple):
                # 多捕获组的匹配结果, 取第一个非空的组
                for g in m:
                    if g:
                        entities.append(g.strip())
                        break
    return entities

# --------------------------------------------------------------------------
# _extract_bigrams - 从文本中提取二元词组 (中文短语 + 英文双词组合)
# 参数:
#   - text: 待分析的文本内容
# 返回: 提取到的词组列表
# 逻辑:
#   - 中文: 提取 2~4 个连续汉字组成的短语
#   - 英文: 提取相邻的两个有意义单词 (长度>2 且非停用词) 组合
#   - 合并中英文结果返回
# 设计说明: 停用词列表用于过滤常见的英文功能词, 减少噪音
# --------------------------------------------------------------------------
def _extract_bigrams(text: str) -> list[str]:
    # 提取 2~4 个连续汉字的中文短语
    chinese = re.findall(r"[\u4e00-\u9fff]{2,4}", text)
    # 提取英文单词并转为小写
    words = re.findall(r"[a-zA-Z]+", text.lower())
    # 英文停用词集合, 过滤无意义的常见功能词
    stopwords = {"the", "a", "an", "is", "are", "was", "to", "of", "in", "for", "on", "with", "and", "or", "but"}
    bigrams = []
    for i in range(len(words) - 1):
        # 仅保留长度大于 2 且非停用词的相邻单词组合
        if len(words[i]) > 2 and len(words[i+1]) > 2 and words[i] not in stopwords and words[i+1] not in stopwords:
            bigrams.append(f"{words[i]} {words[i+1]}")
    return chinese + bigrams

# --------------------------------------------------------------------------
# discover_topics - 从近期文章中发现潜在话题
# 参数:
#   - db: 异步数据库会话
#   - days: 分析的时间范围天数, 默认 14 天
#   - min_frequency: 实体/词组的最低出现频次阈值, 默认 5 次
# 返回: 话题建议字典列表, 每条包含:
#   - name: 建议话题名称
#   - keywords: 关键词列表
#   - frequency: 出现频次
#   - confidence: 置信度 (0~1)
#   - source: 来源类型 ("entity" 或 "keyword")
#   - sample_titles: 示例文章标题列表 (最多 3 条)
# 算法流程:
#   1. 查询指定时间范围内已经过 AI 处理的文章 (最多 500 篇)
#   2. 第一阶段: 实体频率统计 - 识别高频出现的知名实体
#   3. 第二阶段: 二元词组频率统计 - 发现高频关键词组合
#   4. 过滤: 排除已存在的话题名称, 避免重复推荐
#   5. 去重: 按名称去重, 保留置信度更高的条目
#   6. 排序: 按 confidence * frequency 综合得分降序, 返回前 20 条
# --------------------------------------------------------------------------
async def discover_topics(db: AsyncSession, days: int = 14, min_frequency: int = 5) -> list[dict]:
    """Discover potential topics from recent content."""
    # 计算时间截止点
    cutoff = datetime.now() - timedelta(days=days)
    # 查询已经过 AI 处理的近期文章, 限制最多 500 篇以控制处理时间
    result = await db.execute(
        select(Article).where(Article.ai_processed_at.isnot(None), Article.crawl_time >= cutoff).limit(500)
    )
    articles = list(result.scalars().all())
    if not articles:
        return []

    # ====== 第一阶段: 实体频率统计 ======
    # Entity frequency
    entity_counts = Counter()  # 实体出现次数计数器
    entity_samples = defaultdict(list)  # 实体对应的示例文章标题
    for art in articles:
        # 拼接标题和 AI 摘要作为分析文本
        text = f"{art.title} {art.ai_summary or art.summary or ''}"
        for entity in _extract_entities(text):
            entity_counts[entity] += 1
            # 每个实体最多收集 3 个示例标题
            if len(entity_samples[entity]) < 3:
                entity_samples[entity].append(art.title)

    # ====== 获取已有话题名称, 用于排除已存在的话题 ======
    # Existing topic names
    existing = await db.execute(select(Topic.name))
    existing_names = {r[0].lower() for r in existing.all()}

    # ====== 构建实体类建议 ======
    suggestions = []
    for entity, count in entity_counts.most_common(30):
        # 仅保留频次达标且不与已有话题重名的实体
        if count >= min_frequency and entity.lower() not in existing_names:
            # 置信度计算: 出现次数 / (文章总数 * 0.1), 上限为 1.0
            # 即出现频率越高置信度越高, 最低保底 0.3
            confidence = min(1.0, count / (len(articles) * 0.1))
            suggestions.append({
                "name": entity, "keywords": [entity], "frequency": count,
                "confidence": max(0.3, confidence), "source": "entity",
                "sample_titles": entity_samples[entity],
            })

    # ====== 第二阶段: 二元词组频率统计 ======
    # Bigram frequency
    bigram_counts = Counter()  # 词组出现次数计数器
    bigram_samples = defaultdict(list)  # 词组对应的示例文章标题
    for art in articles:
        text = f"{art.title} {art.ai_summary or ''}"
        for bg in _extract_bigrams(text):
            bigram_counts[bg] += 1
            if len(bigram_samples[bg]) < 3:
                bigram_samples[bg].append(art.title)

    # ====== 构建关键词类建议 ======
    for bg, count in bigram_counts.most_common(20):
        if count >= min_frequency and bg.lower() not in existing_names:
            # 词组的置信度上限设为 0.8 (低于实体的 1.0), 因为词组的准确性通常低于实体
            confidence = min(0.8, count / (len(articles) * 0.15))
            suggestions.append({
                "name": bg.title(), "keywords": [bg], "frequency": count,
                "confidence": max(0.2, confidence), "source": "keyword",
                "sample_titles": bigram_samples[bg],
            })

    # ====== 去重逻辑 ======
    # Deduplicate
    # 按名称 (小写) 去重, 当同名建议存在时保留置信度更高的那条
    seen = {}
    for s in suggestions:
        key = s["name"].lower()
        if key not in seen or s["confidence"] > seen[key]["confidence"]:
            seen[key] = s

    # 按 confidence * frequency 综合得分降序排列, 返回前 20 条建议
    return sorted(seen.values(), key=lambda x: x["confidence"] * x["frequency"], reverse=True)[:20]
