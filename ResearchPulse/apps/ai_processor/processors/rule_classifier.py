# =============================================================================
# 规则分类器模块
# =============================================================================
# 本模块实现了基于规则的内容预分类系统，在 AI 处理之前对文章进行预筛选。
# 在架构中的角色：
#   - 成本优化层：通过规则过滤掉不需要 AI 分析的低价值内容
#   - 快速分类层：对已知来源域名的内容进行即时分类
#   - 任务路由层：根据内容特征决定使用哪种级别的 AI 分析
#
# 设计理念：
#   "规则能做的不用 AI"—— 用简单的规则覆盖确定性高的场景，
#   将有限的 AI 算力集中用于真正需要智能分析的内容。
# =============================================================================

"""Rule-based classifier for content pre-classification to save AI tokens."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# 学术论文域名集合
# 用于识别内容是否为学术论文，从而选择论文专用的 prompt 模板
# 涵盖主流预印本平台、顶级期刊和学术数据库
# -----------------------------------------------------------------------------
PAPER_DOMAINS = {
    "arxiv.org", "biorxiv.org", "medrxiv.org", "ssrn.com",
    "nature.com", "science.org", "cell.com", "pnas.org",
    "ieee.org", "acm.org", "openreview.net", "aclanthology.org",
    "paperswithcode.com", "springer.com",
}

# -----------------------------------------------------------------------------
# 高置信度域名分类映射
# 对于这些已知域名，可以直接确定文章的类别和基准重要性分数
# 格式: 域名 -> (分类, 重要性基准分)
# 设计决策：只对高置信度的域名进行直接分类，避免误判
# -----------------------------------------------------------------------------
HIGH_CONFIDENCE_DOMAINS = {
    "openai.com": ("AI", 8), "anthropic.com": ("AI", 8),
    "deepmind.com": ("AI", 8), "mistral.ai": ("AI", 8),
    "huggingface.co": ("AI", 7), "stability.ai": ("AI", 7),
    "nature.com": ("研究", 8), "science.org": ("研究", 8),
    "arxiv.org": ("研究", 7), "biorxiv.org": ("研究", 7),
    "blog.google": ("技术", 7), "github.blog": ("编程", 7),
    "pytorch.org": ("编程", 7), "tensorflow.org": ("编程", 7),
    "techcrunch.com": ("创业", 6), "venturebeat.com": ("AI", 6),
    "jiqizhixin.com": ("AI", 7), "36kr.com": ("创业", 6),
    "bloomberg.com": ("金融", 7), "reuters.com": ("金融", 7),
    "producthunt.com": ("创新", 6),
}

# -----------------------------------------------------------------------------
# 跳过处理的正则模式列表
# 匹配到这些模式的内容将完全跳过 AI 处理，节省资源
# 每个元素是 (正则模式, 跳过原因) 的元组
# -----------------------------------------------------------------------------
SKIP_PATTERNS = [
    (r"^\[Discussion\]", "Discussion post"),                                    # 纯讨论帖
    (r"^Ask HN:", "Ask HN post"),                                              # HN 提问帖
    (r"^(Daily|Weekly|Monthly)\s+(Thread|Discussion|Megathread)", "Periodic thread"),  # 周期性讨论帖
    (r"\b(we.?re hiring|job opening|招聘|招人)\b", "Job posting"),                # 招聘帖
    (r"\b(click here|subscribe now|免费领取|限时优惠)\b", "Promotional content"),   # 促销/垃圾内容
]


def should_skip_processing(title: str, content: str, source_type: str = "") -> tuple[bool, str]:
    """Check if content should skip AI processing."""
    # 检查内容是否应跳过 AI 处理
    # 参数：
    #   title: 文章标题
    #   content: 文章内容
    #   source_type: 来源类型（如 "twitter"、"hackernews"）
    # 返回值：(是否跳过, 跳过原因)

    # 空内容直接跳过
    if not content.strip():
        return True, "Empty content"
    # 内容和标题都太短，信息量不足以分析
    if len(content) < 150 and len(title) < 50:
        return True, "Content too short"
    # 合并标题和内容进行模式匹配
    content_lower = content.lower()
    title_combined = f"{title} {content_lower}"
    # 检查是否匹配跳过模式
    for pattern, reason in SKIP_PATTERNS:
        if re.search(pattern, title_combined, re.IGNORECASE):
            return True, reason
    # Twitter 短内容的特殊处理：
    # 短推文通常信息量低，但如果包含重要信号词（发布、上线等）则保留
    if source_type == "twitter" and len(content) < 200:
        high_value_signals = [
            r"\b(announce|launch|release|发布|上线)\b",
            r"\b(GPT|Claude|Gemini|LLM|AI model)\b",
        ]
        if not any(re.search(p, title_combined, re.IGNORECASE) for p in high_value_signals):
            return True, "Twitter short content"
    # 重复内容检测：如果词汇多样性太低（去重后的词数占比 < 30%），视为重复/垃圾内容
    words = content_lower.split()
    if len(words) >= 20 and len(set(words)) / len(words) < 0.3:
        return True, "Repetitive content"
    return False, ""


def is_paper_content(url: str, title: str) -> bool:
    """Detect if content is an academic paper."""
    # 判断内容是否为学术论文
    # 检测方法：
    #   1. URL 域名是否属于学术论文平台
    #   2. URL 路径是否匹配论文 ID 模式
    #   3. 标题是否包含 arXiv 论文编号模式
    if not url:
        return False
    # 方法一：检查域名是否在学术论文域名集合中
    try:
        parsed = urlparse(url.lower())
        domain = parsed.netloc.replace("www.", "")
        for paper_domain in PAPER_DOMAINS:
            if domain == paper_domain or domain.endswith("." + paper_domain):
                return True
    except (ValueError, AttributeError):
        pass
    # 方法二：检查 URL 路径模式（如 /abs/2301.12345、/doi/10.xxxx）
    paper_url_patterns = [r"/abs/\d+\.\d+", r"/pdf/\d+\.\d+", r"/paper/", r"/doi/", r"10\.\d{4,}/"]
    for pattern in paper_url_patterns:
        if re.search(pattern, url.lower()):
            return True
    # 方法三：检查标题中的论文编号模式
    paper_title_patterns = [r"^arXiv:\d+\.\d+", r"^\[\d+\.\d+\]", r"\[arXiv\]"]
    for pattern in paper_title_patterns:
        if re.search(pattern, title, re.IGNORECASE):
            return True
    return False


def classify_by_domain(url: str, domain: str | None = None) -> tuple[str, int] | None:
    """Classify content by URL domain. Returns (category, importance) or None.

    Args:
        url: Article URL.
        domain: Pre-parsed domain (skip urlparse if provided).
    """
    # 根据 URL 域名进行快速分类
    # 参数：url - 文章的 URL
    # 返回值：(分类, 重要性分数) 或 None（无法根据域名分类时）
    if not url and not domain:
        return None
    try:
        if domain is None:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace("www.", "")
        # 精确匹配高置信度域名
        if domain in HIGH_CONFIDENCE_DOMAINS:
            return HIGH_CONFIDENCE_DOMAINS[domain]
        # 子域名匹配（如 blog.openai.com 匹配 openai.com）
        for known_domain, result in HIGH_CONFIDENCE_DOMAINS.items():
            if domain.endswith("." + known_domain):
                return result
    except (ValueError, AttributeError):
        pass
    return None


def estimate_task_type(url: str, title: str, content: str, domain: str | None = None) -> str:
    """Estimate the appropriate task type for processing.

    Args:
        url: Article URL.
        title: Article title.
        content: Article content.
        domain: Pre-parsed domain (skip urlparse if provided).
    """
    # 估算文章应使用的 AI 处理任务类型
    # 返回值：
    #   "paper_full" - 学术论文，使用论文专用的详细分析 prompt
    #   "content_high" - 高价值内容，使用完整分析 prompt
    #   "content_low" - 低价值内容，使用简要分析 prompt
    #
    # 判断逻辑（按优先级）：
    #   1. 学术论文 -> paper_full
    #   2. 高置信度域名且重要性 >= 7 -> content_high
    #   3. 标题/内容包含高价值信号词（发布、融资等） -> content_high
    #   4. 其他 -> content_low

    # 检查是否为学术论文
    if is_paper_content(url, title):
        return "paper_full"
    # 检查域名分类结果，复用已解析的 domain
    domain_result = classify_by_domain(url, domain=domain)
    if domain_result:
        _, importance = domain_result
        if importance >= 7:
            return "content_high"
        return "content_low"
    # 检查高价值信号词
    text = f"{title} {content[:500]}"
    high_value = [r"\b(announce|launch|release|发布|GPT|Claude|Gemini|funding|融资)\b"]
    for p in high_value:
        if re.search(p, text, re.IGNORECASE):
            return "content_high"
    return "content_low"
