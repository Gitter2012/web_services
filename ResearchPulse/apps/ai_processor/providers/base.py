# =============================================================================
# AI Provider 基类与公用工具模块
# =============================================================================
# 本模块定义了 AI 内容处理的抽象基类和所有 Provider 共用的工具函数。
# 在架构中，它是 Provider 策略模式的核心，确保不同 AI 服务（Ollama、OpenAI）
# 遵循统一的接口契约。
#
# 主要组成：
#   - VALID_CATEGORIES / CATEGORY_ALIASES: 分类体系定义与别名映射
#   - Prompt 模板: PROCESS_PROMPT（详细分析）、SIMPLE_PROMPT（简要分析）、
#                  PAPER_PROMPT（学术论文分析）
#   - 工具函数: normalize_category, smart_truncate, get_content_hash,
#              parse_json_response, _parse_with_regex
#   - BaseAIProvider: 抽象基类，定义 Provider 接口
# =============================================================================

"""Base AI provider abstract class."""

from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod
from typing import Optional


# -----------------------------------------------------------------------------
# 分类体系定义
# 系统支持 10 个预定义分类，所有 AI 输出必须映射到其中之一
# 设计决策：使用固定分类集合而非自由标签，便于下游聚合和展示
# -----------------------------------------------------------------------------
VALID_CATEGORIES = {"AI", "机器学习", "编程", "技术", "创业", "创新", "金融", "研究", "设计", "其他"}

# 分类别名映射表：将 AI 可能返回的近义词/变体统一映射到标准分类
CATEGORY_ALIASES = {
    "经济": "金融", "投资": "金融", "商业": "创业", "产品": "创新",
    "开发": "编程", "科研": "研究", "学术": "研究", "ML": "机器学习",
    "深度学习": "机器学习",
}

# -----------------------------------------------------------------------------
# Prompt 模板定义
# 三种不同层次的分析 Prompt，根据内容类型和价值选择使用
# -----------------------------------------------------------------------------

# 详细分析 Prompt —— 用于高价值内容（content_high 任务类型）
# 输出完整的结构化 JSON：摘要、分类、重要性、一句话总结、关键要点、影响评估、行动项
PROCESS_PROMPT = """分析内容，返回JSON（仅JSON，无其他文字）：
{{
  "summary": "50字中文摘要",
  "category": "只选一个：AI、机器学习、编程、技术、创业、创新、金融、研究、设计、其他",
  "importance": 1-10,
  "one_liner": "一句话结论：这条信息对读者意味着什么",
  "key_points": [
    {{"type": "数字/时间/实体/事实", "value": "关键值", "impact": "影响说明"}}
  ],
  "impact_assessment": {{
    "short_term": "短期影响",
    "long_term": "长期影响",
    "certainty": "certain/uncertain"
  }},
  "actionable_items": [
    {{"type": "跟进/验证/决策/触发器", "description": "具体行动", "priority": "高/中/低"}}
  ]
}}

评分:9-10重大发布/突破性论文,7-8官宣/重要开源/融资,5-6教程/一般研究,3-4普通讨论,1-2招聘/水帖
category：必须是以上10个分类之一，不要组合
key_points：提取最多3个关键点（数字/时间/实体/事实）
actionable_items：仅当importance>=7时提取行动项，否则为空数组

标题：{title}
正文：{content}"""

# 简要分析 Prompt —— 用于低价值内容（content_low / content_minimal 任务类型）
# 仅输出三个核心字段：摘要、分类、重要性
SIMPLE_PROMPT = """返回JSON：{{"summary":"中文摘要50字内","category":"AI|机器学习|编程|技术|创业|创新|金融|研究|设计|其他(选一个)","importance":1-10}}
评分:9-10重大发布,7-8重要更新,5-6一般,1-4低价值

标题：{title}
正文：{content}"""

# 学术论文分析 Prompt —— 用于 arxiv/Nature 等论文内容（paper_full 任务类型）
# 与 PROCESS_PROMPT 类似但侧重学术视角：研究方法、学术影响、工业界影响
PAPER_PROMPT = """分析学术论文，返回JSON（仅JSON，无其他文字）：
{{
  "summary": "100字中文摘要：研究目标、方法、主要发现",
  "category": "只选一个：AI、机器学习、编程、技术、创业、创新、金融、研究、设计、其他",
  "importance": 1-10,
  "one_liner": "一句话：这篇论文最核心的贡献",
  "key_points": [
    {{"type": "方法/数据/结果/局限", "value": "关键信息", "impact": "影响说明"}}
  ],
  "impact_assessment": {{
    "short_term": "学术影响",
    "long_term": "工业界影响",
    "certainty": "certain/uncertain"
  }},
  "actionable_items": [
    {{"type": "复现/跟进/应用/关注", "description": "具体行动", "priority": "高/中/低"}}
  ]
}}

论文评分:10极罕见开创性,9顶级突破,7-8重要贡献,5-6普通研究,3-4一般,1-2低价值
key_points: 最多4个
actionable_items: 仅importance>=7时提取

标题：{title}
摘要/正文：{content}"""

# 翻译 Prompt —— 用于将英文内容翻译为中文
TRANSLATE_PROMPT = "将以下英文翻译成中文，只返回翻译结果，不要解释或添加额外内容：\n\n{text}"

# 批量翻译 Prompt —— 用于一次翻译多个文本
BATCH_TRANSLATE_PROMPT = """将以下 {count} 段英文分别翻译成中文，按序号返回翻译结果，每段翻译占一行，格式为：
[编号] 翻译内容

例如：
[1] 第一段翻译
[2] 第二段翻译

待翻译内容：
{items}"""


def normalize_category(category: str) -> str:
    """Normalize category to a valid value.

    将 AI 返回的分类映射到预定义分类集合。

    Args:
        category: Raw category string.

    Returns:
        str: Normalized category.
    """
    # 将 AI 返回的分类字符串规范化为系统定义的标准分类
    # 处理逻辑（按优先级）：
    #   1. 空值 -> "其他"
    #   2. 精确匹配标准分类 -> 直接返回
    #   3. 匹配别名映射 -> 返回对应标准分类
    #   4. 含有分隔符（如"AI/技术"）-> 尝试拆分后逐一匹配
    #   5. 包含某个标准分类字符串 -> 返回该分类
    #   6. 都不匹配 -> "其他"
    if not category:
        return "其他"
    if category in VALID_CATEGORIES:
        return category
    if category in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[category]
    # 处理 AI 返回的组合分类（如 "AI/技术"、"编程、技术"）
    for sep in ["/", "、", ",", "，"]:
        if sep in category:
            for part in category.split(sep):
                part = part.strip()
                if part in VALID_CATEGORIES:
                    return part
                if part in CATEGORY_ALIASES:
                    return CATEGORY_ALIASES[part]
    # 模糊匹配：检查分类字符串中是否包含某个标准分类
    for valid_cat in VALID_CATEGORIES:
        if valid_cat in category:
            return valid_cat
    return "其他"


def smart_truncate(text: str, max_length: int) -> str:
    """Truncate text at sentence boundaries when possible.

    智能截断文本，尽量在句子或词边界处截断。

    Args:
        text: Input text.
        max_length: Maximum length.

    Returns:
        str: Truncated text.
    """
    # 智能截断文本：优先在句子边界处截断，避免截断在句子中间
    # 截断策略（按优先级）：
    #   1. 文本未超长 -> 直接返回
    #   2. 在截断点 80% 之后寻找句号/问号/换行等句子结束标记
    #   3. 寻找空格/逗号等词边界
    #   4. 都找不到则直接硬截断
    if len(text) <= max_length:
        return text
    truncated = text[:max_length]
    # 从 80% 位置开始向后搜索句子结束标记，避免截断过早
    search_start = int(max_length * 0.8)
    for ending in ["。", "！", "？", ".", "!", "?", "\n\n"]:
        pos = truncated.rfind(ending, search_start)
        if pos > search_start:
            return truncated[:pos + 1] + "..."
    # 退而求其次，在词边界处截断
    for boundary in [" ", "，", ",", "；", ";"]:
        pos = truncated.rfind(boundary, search_start)
        if pos > search_start:
            return truncated[:pos] + "..."
    return truncated + "..."


def get_content_hash(title: str, content: str) -> str:
    """Generate content hash as cache key.

    根据标题与正文生成内容哈希。

    Args:
        title: Content title.
        content: Content body.

    Returns:
        str: Short hash string.
    """
    # 生成内容哈希值，用作缓存的键
    # 将标题和内容组合后计算 SHA-256，取前 16 位作为紧凑的标识符
    combined = f"{title}||{content}"
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def parse_json_response(response: str) -> dict:
    """Parse JSON from AI response, handling markdown code blocks.

    解析 AI 返回的 JSON 响应，支持 ```json ``` 包裹格式。

    Args:
        response: Raw response string.

    Returns:
        dict: Parsed JSON dict (fallback regex parsing if needed).
    """
    # 解析 AI 返回的 JSON 响应
    # AI 模型经常在 JSON 外包裹 markdown 代码块（```json ... ```），需要先剥离
    response = response.strip()
    # 处理 markdown 代码块包裹的情况
    if response.startswith("```"):
        lines = response.split("\n")
        start_idx = 1  # 跳过 ``` 开头行
        end_idx = len(lines)
        # 从末尾向前搜索结束的 ```
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip() == "```":
                end_idx = i
                break
        response = "\n".join(lines[start_idx:end_idx])
    # 提取 JSON 对象的范围（从第一个 { 到最后一个 }）
    json_start = response.find("{")
    json_end = response.rfind("}") + 1
    if json_start != -1 and json_end > json_start:
        response = response[json_start:json_end]
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        # JSON 解析失败时，使用正则表达式作为兜底方案
        return _parse_with_regex(response)


def _parse_with_regex(response: str) -> dict:
    """Fallback parser using regex for malformed JSON.

    当 JSON 无法解析时的降级解析策略。

    Args:
        response: Raw response string.

    Returns:
        dict: Parsed fields with defaults on failure.
    """
    # 当 AI 返回的 JSON 格式不合法时，用正则表达式提取关键字段
    # 这是一种降级策略，确保即使 AI 输出格式异常也能提取基本信息
    summary_match = re.search(r'"summary"\s*:\s*"(.+?)"\s*,\s*"category"', response, re.DOTALL)
    category_match = re.search(r'"category"\s*:\s*"([^"]+)"', response)
    importance_match = re.search(r'"importance"\s*:\s*(\d+)', response)
    if summary_match and category_match and importance_match:
        return {
            "summary": summary_match.group(1).strip(),
            "category": category_match.group(1).strip(),
            "importance": int(importance_match.group(1)),
        }
    # 完全无法解析时返回默认值
    return {"summary": "", "category": "其他", "importance": 5}


# -----------------------------------------------------------------------------
# AI Provider 抽象基类
# 定义所有 AI 服务提供商必须实现的接口。
# 设计决策：使用策略模式，通过抽象基类约束接口，使得切换 AI 服务对上层透明。
# 子类只需实现 process_content 和 is_available 两个方法。
# build_prompt 和 extract_result 作为公共逻辑放在基类中复用。
# -----------------------------------------------------------------------------
class BaseAIProvider(ABC):
    """Abstract base class for AI providers.

    AI 服务提供商抽象基类。
    """

    @abstractmethod
    async def process_content(self, title: str, content: str, task_type: str = "content_high") -> dict:
        """Process content and return structured result dict.

        处理内容并返回结构化结果。

        Args:
            title: Content title.
            content: Content body.
            task_type: Task type (content_high/content_low/paper_full).

        Returns:
            dict: Structured result.
        """
        ...

    async def translate(self, text: str) -> str | None:
        """Translate text to Chinese. Returns None if not implemented."""
        return None

    async def translate_batch(self, texts: list[str], concurrency: int = 5) -> list[str | None]:
        """Translate multiple texts to Chinese concurrently.

        批量翻译（并发实现），提高翻译效率。
        使用 asyncio.gather 并发调用 translate()，失败的项目返回 None。

        Args:
            texts: List of texts to translate.
            concurrency: Maximum concurrent translations (default 5).

        Returns:
            List of translated texts (None for failed items).
        """
        import asyncio

        semaphore = asyncio.Semaphore(concurrency)

        async def translate_with_limit(text: str) -> str | None:
            async with semaphore:
                try:
                    return await self.translate(text)
                except Exception:
                    return None

        # 并发执行所有翻译任务
        tasks = [translate_with_limit(text) for text in texts]
        results = await asyncio.gather(*tasks)
        return list(results)

    async def close(self) -> None:
        """Release resources held by the provider.

        释放 Provider 持有的资源（如 HTTP 连接池）。子类按需覆写。
        """
        pass

    async def warmup(self) -> bool:
        """Pre-load the model to reduce first-request latency.

        预加载模型以减少首次请求延迟。子类按需覆写。
        默认实现为空操作，直接返回 True。

        Returns:
            bool: True if warmup succeeded or is not needed.
        """
        return True

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the provider is available.

        检查提供商是否可用。

        Returns:
            bool: Availability status.
        """
        ...

    def build_prompt(self, title: str, content: str, task_type: str = "content_high", max_content_length: int = 1500) -> str:
        """Build prompt based on task type.

        根据任务类型构建对应 prompt，并按长度截断内容。

        Args:
            title: Content title.
            content: Content body.
            task_type: Task type.
            max_content_length: Max content length for truncation.

        Returns:
            str: Prompt text.
        """
        # 根据任务类型构建对应的 prompt
        # 参数说明：
        #   title: 文章标题
        #   content: 文章正文内容
        #   task_type: 任务类型，决定使用哪个 prompt 模板
        #   max_content_length: 内容最大长度，超过则智能截断（节省 token）
        # 返回值：构建好的完整 prompt 字符串
        if max_content_length > 0 and len(content) > max_content_length:
            content = smart_truncate(content, max_content_length)
        # 标题过长时也进行截断
        title_truncated = smart_truncate(title, 200) if len(title) > 200 else title

        # 根据任务类型选择对应的 prompt 模板
        if task_type == "paper_full":
            return PAPER_PROMPT.format(title=title_truncated, content=content)
        elif task_type in ("content_minimal", "content_low"):
            return SIMPLE_PROMPT.format(title=title_truncated, content=content)
        else:
            # content_high 及其他未知类型都使用完整分析模板
            return PROCESS_PROMPT.format(title=title_truncated, content=content)

    def extract_result(self, data: dict) -> dict:
        """Extract standardized result from parsed JSON.

        从解析后的 JSON 中提取规范化字段。

        Args:
            data: Parsed JSON dictionary.

        Returns:
            dict: Standardized result payload.
        """
        # 从 AI 返回的原始 JSON 中提取并标准化各字段
        # 对每个字段进行类型检查和边界约束，确保输出格式一致

        # 标准化分类：映射到预定义分类集合
        category = normalize_category(data.get("category", "其他"))

        # 标准化重要性评分：确保为 1-10 的整数
        importance = data.get("importance", 5)
        if not isinstance(importance, int):
            try:
                importance = int(importance)
            except (ValueError, TypeError):
                importance = 5
        importance = max(1, min(10, importance))  # 钳制到 1-10 范围

        # 提取关键要点列表，确保每个元素都是字典格式
        key_points = []
        for kp in data.get("key_points", []):
            if isinstance(kp, dict):
                key_points.append({
                    "type": kp.get("type", "事实"),
                    "value": kp.get("value", ""),
                    "impact": kp.get("impact", ""),
                })

        # 提取影响评估（可能为 None）
        impact_assessment = None
        raw_impact = data.get("impact_assessment")
        if isinstance(raw_impact, dict):
            impact_assessment = {
                "short_term": raw_impact.get("short_term", ""),
                "long_term": raw_impact.get("long_term", ""),
                "certainty": raw_impact.get("certainty", "uncertain"),
            }

        # 提取行动项列表
        actionable_items = []
        for action in data.get("actionable_items", []):
            if isinstance(action, dict):
                actionable_items.append({
                    "type": action.get("type", "跟进"),
                    "description": action.get("description", ""),
                    "priority": action.get("priority", "中"),
                })

        return {
            "summary": data.get("summary", ""),
            "category": category,
            "importance_score": importance,
            "one_liner": data.get("one_liner", ""),
            "key_points": key_points,
            "impact_assessment": impact_assessment,
            "actionable_items": actionable_items,
        }
