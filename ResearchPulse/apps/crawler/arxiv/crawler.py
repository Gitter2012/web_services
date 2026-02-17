# =============================================================================
# 模块: apps/crawler/arxiv/crawler.py
# 功能: arXiv 学术论文爬虫模块
# 架构角色: 爬虫子系统的具体实现之一，负责从 arXiv.org 获取学术论文。
#           继承 BaseCrawler，实现 fetch() 和 parse() 抽象方法。
# 数据源策略: 采用多源聚合策略，从三个渠道获取论文数据：
#   1. Atom API - arXiv 官方的结构化查询接口（主要数据源）
#   2. RSS Feed - arXiv 的 RSS 订阅源（补充数据源，当 Atom 结果不足时启用）
#   3. HTML 列表页 - arXiv 的网页列表（最新论文列表，确保覆盖面）
#   最后通过 arxiv_id 去重合并，保留最完整的数据。
# 设计理念: 多源冗余确保数据完整性，即使某个数据源暂时不可用也不影响整体爬取。
# =============================================================================

"""ArXiv crawler for ResearchPulse v2."""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

import feedparser

from apps.crawler.base import BaseCrawler
from common.http import get_text_async

# 模块级日志器
logger = logging.getLogger(__name__)


# =============================================================================
# Paper 数据类
# 职责: 作为 arXiv 论文的中间数据表示（DTO），封装论文的核心属性。
# 设计决策: 使用 dataclass 而非普通字典，提供类型安全和属性访问的便利性。
#           同时提供 to_article_dict() 方法将数据转换为 Article 模型兼容的字典格式。
# =============================================================================
@dataclass
class Paper:
    """ArXiv paper data structure.

    arXiv 论文数据的中间表示（DTO）。
    """

    arxiv_id: str                   # arXiv 论文唯一标识符，如 "2301.12345"
    title: str                      # 论文标题
    authors: List[str]              # 作者列表
    primary_category: str           # 主分类，如 "cs.AI"
    categories: List[str]           # 所有分类列表（含交叉分类）
    abstract: str                   # 论文摘要
    pdf_url: str                    # PDF 下载链接
    published: str                  # 首次发布时间（ISO 8601 格式字符串）
    updated: str = ""               # 最后更新时间（论文可能会有多个版本）
    announced_date: str = ""        # 公告日期（在 arXiv 列表页上展示的日期）
    paper_type: str = ""            # 论文类型: "new" 或 "updated"

    def to_article_dict(self) -> Dict[str, Any]:
        """Convert to an Article-compatible dictionary.

        将 Paper 对象转换为 Article 数据库模型兼容的字典格式。

        Notes:
            - source_date: Prefer announced_date, fallback to updated/published date.
            - publish_time: Parse ISO strings into datetime.
            - url: Use abstract page URL (not PDF) for readability.
            - cover_image_url: Store PDF URL for download link.

        Returns:
            Dict[str, Any]: Mapping compatible with Article fields.
        """
        # 确定来源日期：优先使用公告日期，否则从更新时间或发布时间提取日期部分
        # Determine source date
        if self.announced_date:
            source_date = self.announced_date
        else:
            effective_ts = self.updated or self.published
            source_date = effective_ts.split("T")[0] if effective_ts else ""

        # 将发布时间字符串解析为 datetime 对象
        # 处理 ISO 8601 格式，将 "Z" 后缀替换为 "+00:00" 以兼容 fromisoformat
        # Parse publish time
        publish_time = None
        if self.published:
            try:
                publish_time = datetime.fromisoformat(
                    self.published.replace("Z", "+00:00")
                )
            except ValueError:
                pass

        # 将更新时间字符串解析为 datetime 对象
        # Parse updated time
        updated_time = None
        if self.updated:
            try:
                updated_time = datetime.fromisoformat(
                    self.updated.replace("Z", "+00:00")
                )
            except ValueError:
                pass

        # 构建 PDF 下载链接：优先使用解析到的 URL，否则根据 arxiv_id 自动生成
        # PDF URL for direct download
        pdf_url = self.pdf_url if self.pdf_url else f"https://arxiv.org/pdf/{self.arxiv_id}"
        # 论文摘要页 URL，提供更好的阅读体验
        # Abstract page URL
        abs_url = f"https://arxiv.org/abs/{self.arxiv_id}"

        # 构建作者列表字符串，限制最大长度为 1000 字符
        # Build author list string with max length limit
        author_str = ""
        if self.authors:
            author_str = ", ".join(self.authors)
            # 如果超过 950 字符，截断并添加 "et al." 后缀
            if len(author_str) > 950:
                # 尝试在完整的作者处截断
                truncated = author_str[:950]
                last_comma = truncated.rfind(",")
                if last_comma > 0:
                    author_str = truncated[:last_comma] + ", et al."
                else:
                    author_str = truncated + " et al."

        return {
            "external_id": self.arxiv_id,
            "title": self.title,
            "url": abs_url,  # Main URL goes to abstract page
            "author": author_str,  # 使用已截断的作者字符串
            "summary": self.abstract,
            "content": self.abstract,  # arXiv 论文的 content 也使用摘要（正文需单独下载 PDF）
            "category": self.primary_category,
            "tags": self.categories,
            "publish_time": publish_time,
            "arxiv_id": self.arxiv_id,
            "arxiv_primary_category": self.primary_category,
            "arxiv_updated_time": updated_time,
            "arxiv_paper_type": self.paper_type,  # 论文类型: new/updated
            "cover_image_url": pdf_url,  # Store PDF URL for download link
        }


# =============================================================================
# 工具函数区域
# 以下函数用于文本清洗、ID标准化、时间解析、以及各种数据源格式的解析
# =============================================================================

def _clean_text(text: str) -> str:
    """Clean text by stripping HTML and normalizing whitespace.

    清洗文本内容：移除 HTML 标签、反转义 HTML 实体、规范化空白字符。

    Args:
        text: Raw text which may contain HTML tags/entities.

    Returns:
        str: Cleaned plain text.
    """
    if not text:
        return ""
    # 第一步：使用正则去除所有 HTML 标签（如 <b>、<a href="..."> 等）
    cleaned = re.sub(r"<[^>]+>", " ", text)
    # 第二步：将 HTML 实体（如 &amp; &lt;）还原为对应字符
    cleaned = html.unescape(cleaned)
    # 第三步：将换行符替换为空格，并压缩连续空白为单个空格
    return " ".join(cleaned.replace("\n", " ").split()).strip()


def _normalize_arxiv_id(arxiv_id: str) -> str:
    """Normalize arXiv IDs by removing version suffixes.

    arXiv 论文可能有多个版本（如 2301.12345v1, 2301.12345v2），
    去除版本号后缀用于论文去重合并。

    Args:
        arxiv_id: arXiv ID possibly with version suffix.

    Returns:
        str: Normalized arXiv ID without version suffix.
    """
    if not arxiv_id:
        return ""
    return re.sub(r"v\d+$", "", arxiv_id)


def _parse_datetime(value: str) -> str:
    """Parse datetime string into ISO 8601 format.

    支持 ISO 8601 与 RFC 2822 日期格式。

    Args:
        value: Datetime string to parse.

    Returns:
        str: ISO 8601 datetime string or original value if parsing fails.
    """
    if not value:
        return ""
    # 尝试方式一：ISO 8601 格式解析
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.isoformat()
    except ValueError:
        pass
    # 尝试方式二：RFC 2822 邮件日期格式解析（常见于 RSS Feed）
    try:
        from email.utils import parsedate_to_datetime
        parsed = parsedate_to_datetime(value)
        return parsed.isoformat()
    except (ValueError, TypeError):
        pass
    # 所有格式都无法匹配时，返回原始值
    return value


def _parse_rss_entry(entry: feedparser.FeedParserDict) -> Paper:
    """Parse a single RSS/Atom entry into a Paper object.

    处理来自 arXiv Atom API 与 RSS Feed 的条目，提取关键信息。

    Args:
        entry: FeedParser entry dictionary.

    Returns:
        Paper: Parsed paper data object.
    """
    # 从条目的 id 或 link 字段中提取 arXiv ID
    arxiv_id = ""
    entry_id = entry.get("id", "") or entry.get("link", "")
    # 使用正则从 URL 中匹配 arXiv ID（如 arxiv.org/abs/2301.12345v1）
    match = re.search(r"arxiv.org/abs/([\w.]+(?:v\d+)?)", entry_id)
    if match:
        arxiv_id = match.group(1)

    # 清洗标题和摘要中的 HTML 标签
    title = _clean_text(entry.get("title", ""))
    abstract = _clean_text(entry.get("summary", ""))

    # 提取作者列表，支持两种格式：
    # 1. authors 字段（结构化列表，每个元素有 name 属性）
    # 2. author 字段（逗号分隔的字符串）
    authors: List[str] = []
    if entry.get("authors"):
        for author in entry.get("authors", []):
            name = author.get("name", "")
            # 单个 name 字段中可能包含逗号分隔的多位作者
            authors.extend([_clean_text(part) for part in name.split(",") if _clean_text(part)])
    elif entry.get("author"):
        authors = [_clean_text(name) for name in entry.get("author", "").split(",") if _clean_text(name)]

    # 提取分类标签，第一个分类作为主分类
    categories = [_clean_text(tag.get("term", "")) for tag in entry.get("tags", [])]
    primary_category = categories[0] if categories else ""

    # 从 links 中查找 PDF 链接（通过 MIME 类型识别）
    pdf_url = ""
    for link in entry.get("links", []):
        if link.get("type") == "application/pdf":
            pdf_url = link.get("href", "")
            break

    # 解析发布时间和更新时间
    published = _parse_datetime(entry.get("published", ""))
    updated = _parse_datetime(entry.get("updated", ""))
    # 公告日期取发布时间的日期部分
    announced_date = published.split("T")[0] if published else ""

    return Paper(
        arxiv_id=arxiv_id,
        title=title,
        authors=authors,
        primary_category=primary_category,
        categories=categories,
        abstract=abstract,
        pdf_url=pdf_url,
        published=published,
        updated=updated,
        announced_date=announced_date,
    )


def _extract_list_header_date(html_text: str) -> str:
    """Extract date from an arXiv HTML list page header.

    从列表页标题中解析日期并转为 ISO 格式。

    Args:
        html_text: HTML text of the list page.

    Returns:
        str: ISO date string, or empty string if parsing fails.
    """
    # 使用正则匹配 "SHOWING NEW/RECENT LISTINGS FOR" 后面的日期文本
    match = re.search(r"SHOWING (?:NEW|RECENT) LISTINGS FOR\s+([^<]+)", html_text, re.I)
    if not match:
        return ""

    text = match.group(1)
    # 移除可能存在的星期几前缀（如 "Monday, "）
    # Parse human-readable date
    text = re.sub(r"^[A-Za-z]+,\s*", "", text.strip())
    # 移除逗号
    text = text.replace(",", " ")
    # 处理月份缩写的特殊情况：Sept. -> Sep
    text = re.sub(r"\bSept\.?\b", "Sep", text, flags=re.I)
    # 规范化空白并首字母大写
    text = re.sub(r"\s+", " ", text).strip().title()

    # 尝试多种日期格式进行解析
    for fmt in ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _parse_html_list(html_text: str, run_date: str | None = None) -> List[Paper]:
    """Parse arXiv HTML list page into paper entries.

    解析列表页中的 <dt>/<dd> 条目，提取标题、作者、摘要、分类等信息。

    Args:
        html_text: HTML text of the list page.
        run_date: Fallback run date if header date is missing.

    Returns:
        List[Paper]: Parsed paper list.
    """
    papers: List[Paper] = []
    # 尝试从页面标题中提取发布日期
    header_date = _extract_list_header_date(html_text)
    # 页面标题没有日期时，使用调用者传入的运行日期作为回退
    if not header_date and run_date:
        header_date = run_date

    # 将日期转换为 ISO 时间戳格式（午夜时间）
    published = f"{header_date}T00:00:00Z" if header_date else ""

    # 遍历所有 <dt>...<dd>... 标签对，每对代表一篇论文
    for match in re.finditer(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", html_text, re.S):
        dt = match.group(1)  # <dt> 内容，包含论文 ID 链接
        dd = match.group(2)  # <dd> 内容，包含论文详情

        # 从 <dt> 中提取 arXiv ID
        id_match = re.search(r"/abs/([\w.]+(?:v\d+)?)", dt)
        arxiv_id = id_match.group(1) if id_match else ""

        # 从 <dd> 中提取标题
        # 支持新旧两种格式：
        # 新格式: <div class='list-title mathjax'><span class='descriptor'>Title:</span>...</div>
        # 旧格式: <span>Title:</span>...</div>
        title_match = re.search(r"<div\s+class=['\"]list-title[^'\"]*['\"][^>]*>.*?</span>\s*(.*?)</div>", dd, re.S)
        if not title_match:
            # 回退到旧格式
            title_match = re.search(r"Title:</span>\s*(.*?)</div>", dd, re.S)
        title = _clean_text(title_match.group(1)) if title_match else ""

        # 从 <dd> 中提取作者列表
        # 支持新旧两种格式：
        # 新格式: <div class='list-authors'>...</div>
        # 旧格式: <span>Authors:</span>...</div>
        authors_match = re.search(r"<div\s+class=['\"]list-authors['\"][^>]*>(.*?)</div>", dd, re.S)
        if not authors_match:
            # 回退到旧格式
            authors_match = re.search(r"Authors:</span>\s*(.*?)</div>", dd, re.S)
        authors_block = authors_match.group(1) if authors_match else ""
        authors = [_clean_text(a) for a in re.findall(r">\s*([^<]+)\s*</a>", authors_block)]

        # 从 <dd> 中提取摘要
        # 支持新旧两种格式：
        # 新格式: <p class='mathjax'>...</p> (无 Abstract: 前缀)
        # 旧格式: <span>Abstract:</span>...</p>
        # 注意: 新版 arXiv 列表页可能不显示摘要，这里尝试多种匹配方式
        abstract_match = re.search(r"<p\s+class=['\"]mathjax['\"][^>]*>(.*?)</p>", dd, re.S)
        if not abstract_match:
            # 尝试匹配任意 p 标签（排除空的）
            abstract_match = re.search(r"<p[^>]*>(\s*[^<].*?)</p>", dd, re.S)
        if not abstract_match:
            # 回退到旧格式
            abstract_match = re.search(r"Abstract:</span>\s*(.*?)</p>", dd, re.S)
        abstract = _clean_text(abstract_match.group(1)) if abstract_match else ""

        # 从 <dd> 中提取分类信息（以分号或逗号分隔）
        # 支持新旧两种格式：
        # 新格式: <div class='list-subjects'><span class='descriptor'>Subjects:</span>...</div>
        # 旧格式: <span>Subjects:</span>...</div>
        category_match = re.search(r"<div\s+class=['\"]list-subjects['\"][^>]*>.*?</span>\s*(.*?)</div>", dd, re.S)
        if not category_match:
            # 回退到旧格式
            category_match = re.search(r"Subjects:</span>\s*(.*?)</div>", dd, re.S)
        categories_block = category_match.group(1) if category_match else ""
        categories = [_clean_text(cat) for cat in re.split(r";|,", categories_block) if _clean_text(cat)]
        primary_category = categories[0] if categories else ""

        # 根据 arXiv ID 构造 PDF 下载链接
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else ""

        papers.append(Paper(
            arxiv_id=arxiv_id,
            title=title,
            authors=authors,
            primary_category=primary_category,
            categories=categories,
            abstract=abstract,
            pdf_url=pdf_url,
            published=published,
            announced_date=header_date or "",
        ))

    return papers


# =============================================================================
# ArxivCrawler 类
# 职责: 从 arXiv 多个数据源获取论文，去重合并后存储
# 设计决策:
#   1. 多源策略: Atom API + RSS + HTML 列表页，确保数据完整性
#   2. 请求限流: 各请求之间加入随机延迟，避免触发 arXiv 的速率限制
#   3. 智能补充: 当 Atom API 结果不足 max_results 时，才请求 RSS Feed
#   4. 合并去重: 同一论文可能在多个源中出现，按 arxiv_id 去重并合并最完整的数据
# =============================================================================
class ArxivCrawler(BaseCrawler):
    """Crawler for arXiv papers.

    arXiv 论文爬虫实现。
    """

    # 数据源类型标识，用于数据库中区分不同来源的文章
    source_type = "arxiv"

    def __init__(
        self,
        category: str,
        max_results: int = 50,
        delay_base: float = 3.0,
        delay_jitter: float = 1.5,
        sort_modes: List[str] | None = None,
        mark_paper_type: bool = False,
        rss_format: str = "rss",
    ):
        """Initialize arXiv crawler.

        初始化 arXiv 爬虫。

        Args:
            category: arXiv category code (e.g. "cs.AI").
            max_results: Max results for Atom API (per sort mode).
            delay_base: Base delay between requests (seconds).
            delay_jitter: Jitter upper bound for delay (seconds).
            sort_modes: List of sortBy modes, e.g. ["submittedDate", "lastUpdatedDate"].
            mark_paper_type: Whether to mark papers as "new" or "updated".
            rss_format: RSS format, "rss" or "atom".
        """
        super().__init__(category)
        self.category = category
        self.max_results = max_results
        self.delay_base = delay_base
        self.delay_jitter = delay_jitter
        self.sort_modes = sort_modes or ["lastUpdatedDate"]
        self.mark_paper_type = mark_paper_type
        self.rss_format = rss_format

        # 三个数据源的 URL 模板
        # URLs
        self.atom_url = "https://export.arxiv.org/api/query"          # Atom API 端点
        # RSS Feed 模板（旧域名，作为备用）
        self.rss_url_legacy = "https://export.arxiv.org/rss/{category}"
        # RSS Feed 模板（新域名，支持 rss/atom 格式选择）
        self.rss_url = f"https://rss.arxiv.org/{rss_format}/{{category}}"
        self.list_new_url = "https://arxiv.org/list/{category}/new"   # 最新论文列表页模板
        self.list_recent_url = "https://arxiv.org/list/{category}/recent"  # 近期论文列表页模板

    async def fetch(self) -> Dict[str, Any]:
        """Fetch papers from multiple arXiv sources with multiple sort modes.

        执行策略:
            1. 遍历每个排序模式调用 Atom API
            2. 获取 RSS Feed
            3. 抓取 HTML 列表页
            4. 合并去重，标记论文类型

        Returns:
            Dict[str, Any]: Dict with 'papers' list and 'run_date'.
        """
        all_papers: List[Paper] = []
        run_date = datetime.now(timezone.utc).date().isoformat()

        # 数据源 1：Atom API（遍历每个排序模式）
        # Source 1: Atom API with multiple sort modes
        for sort_mode in self.sort_modes:
            mode_papers = await self._fetch_atom(sort_by=sort_mode)

            # 标记论文类型
            if self.mark_paper_type:
                for paper in mode_papers:
                    paper.paper_type = "new" if sort_mode == "submittedDate" else "updated"

            all_papers.extend(mode_papers)
            self.logger.info(f"Atom API ({sort_mode}): {len(mode_papers)} papers")

            # 排序模式之间添加延迟
            if len(self.sort_modes) > 1:
                await self.delay(self.delay_base, self.delay_jitter)

        # 数据源 2：RSS Feed
        # Source 2: RSS Feed
        await self.delay(self.delay_base, self.delay_jitter)
        rss_papers = await self._fetch_rss()
        if self.mark_paper_type:
            for paper in rss_papers:
                paper.paper_type = "new"  # RSS 通常包含最新论文
        all_papers.extend(rss_papers)
        self.logger.info(f"RSS ({self.rss_format}): {len(rss_papers)} papers")

        # 数据源 3：HTML 列表页（始终执行，确保获取当天最新发布的论文）
        # Source 3: HTML list (new)
        await self.delay(self.delay_base, self.delay_jitter)
        html_papers = await self._fetch_html_list(self.list_new_url, run_date)
        if self.mark_paper_type:
            for paper in html_papers:
                paper.paper_type = "new"  # HTML 列表页是新发表论文
        all_papers.extend(html_papers)
        self.logger.info(f"HTML list: {len(html_papers)} papers")

        # 按 arxiv_id 合并去重，保留每篇论文最完整的数据
        # Merge and deduplicate
        merged = self._merge_papers(all_papers)
        self.logger.info(f"Total unique papers: {len(merged)}")

        return {"papers": merged, "run_date": run_date}

    async def _fetch_atom(self, sort_by: str = "lastUpdatedDate") -> List[Paper]:
        """Fetch papers from the Atom API.

        Atom API 是 arXiv 标准数据接口，支持按更新时间或提交时间排序。

        Args:
            sort_by: Sort mode - "submittedDate" or "lastUpdatedDate".

        Returns:
            List[Paper]: Paper list (empty on failure).
        """
        # 构建查询参数
        params = {
            "search_query": f"cat:{self.category}",  # 按分类查询
            "start": 0,                               # 起始位置
            "max_results": self.max_results,          # 最大返回数
            "sortBy": sort_by,                        # 排序方式（参数化）
            "sortOrder": "descending",                # 降序排列（最新的在前）
        }

        try:
            # 使用异步 HTTP 工具函数获取 XML 文本，带超时和重试
            feed_text = await get_text_async(
                self.atom_url,
                params=params,
                timeout=20.0,
                retries=3,
                backoff=1.0,
                delay=self.delay_base,
                jitter=self.delay_jitter,
            )
            # 使用 feedparser 解析 Atom XML
            feed = feedparser.parse(feed_text)
            return [_parse_rss_entry(entry) for entry in feed.entries]
        except Exception as e:
            # Atom API 失败不中断整个爬取流程，记录警告后返回空列表
            self.logger.warning(f"Atom API fetch failed (sortBy={sort_by}): {e}")
            return []

    async def _fetch_rss(self) -> List[Paper]:
        """Fetch papers from RSS feed.

        RSS 作为 Atom API 的补充，通常包含最近发布论文。
        优先使用新域名 rss.arxiv.org，失败时回退到旧域名 export.arxiv.org。

        Returns:
            List[Paper]: Paper list (empty on failure).
        """
        # 将分类代码填入 URL 模板
        url = self.rss_url.format(category=self.category)

        try:
            feed_text = await get_text_async(
                url,
                timeout=20.0,
                retries=3,
                backoff=1.0,
                delay=self.delay_base,
                jitter=self.delay_jitter,
            )
            feed = feedparser.parse(feed_text)
            papers = [_parse_rss_entry(entry) for entry in feed.entries]
            if papers:
                return papers
            # 新域名返回空结果，尝试旧域名
            self.logger.warning(f"New RSS domain returned empty, trying legacy domain")
        except Exception as e:
            self.logger.warning(f"RSS fetch failed (new domain): {e}")

        # 回退到旧域名
        legacy_url = self.rss_url_legacy.format(category=self.category)
        try:
            feed_text = await get_text_async(
                legacy_url,
                timeout=20.0,
                retries=3,
                backoff=1.0,
                delay=self.delay_base,
                jitter=self.delay_jitter,
            )
            feed = feedparser.parse(feed_text)
            return [_parse_rss_entry(entry) for entry in feed.entries]
        except Exception as e:
            self.logger.warning(f"RSS fetch failed (legacy domain): {e}")
            return []

    async def _fetch_html_list(self, url_template: str, run_date: str) -> List[Paper]:
        """Fetch papers from HTML list pages.

        通过 HTML 列表页抓取最新/近期论文。

        Args:
            url_template: URL template with {category} placeholder.
            run_date: Fallback run date if header date missing.

        Returns:
            List[Paper]: Paper list (empty on failure).
        """
        url = url_template.format(category=self.category)

        try:
            html_text = await get_text_async(
                url,
                timeout=15.0,
                retries=3,
                backoff=1.0,
                delay=self.delay_base,
                jitter=self.delay_jitter,
            )
            return _parse_html_list(html_text, run_date=run_date)
        except Exception as e:
            self.logger.warning(f"HTML list fetch failed: {e}")
            return []

    def _merge_papers(self, papers: List[Paper]) -> List[Paper]:
        """Merge and deduplicate papers by arXiv ID.

        当同一论文来自多个数据源或排序模式时，保留最完整字段信息。
        论文类型标记保留首次出现的类型（new 优先于 updated）。

        Args:
            papers: Paper list from multiple sources.

        Returns:
            List[Paper]: Deduplicated list sorted by publish time.
        """
        merged: Dict[str, Paper] = {}

        for paper in papers:
            # 使用标准化的 arXiv ID（去除版本号）作为去重键
            key = _normalize_arxiv_id(paper.arxiv_id)
            if not key:
                continue

            existing = merged.get(key)
            if not existing:
                # 首次遇到此论文，直接加入
                merged[key] = paper
                continue

            # 合并数据：优先使用更完整的数据，而非仅补充空值
            # Merge data: prefer more complete values
            if paper.title and len(paper.title) > len(existing.title):
                existing.title = paper.title
            if paper.authors and (not existing.authors or len(paper.authors) > len(existing.authors)):
                existing.authors = paper.authors
            if paper.abstract and (not existing.abstract or len(paper.abstract) > len(existing.abstract)):
                existing.abstract = paper.abstract
            if paper.primary_category and not existing.primary_category:
                existing.primary_category = paper.primary_category
            if paper.categories and (not existing.categories or len(paper.categories) > len(existing.categories)):
                existing.categories = paper.categories
            if paper.pdf_url and not existing.pdf_url:
                existing.pdf_url = paper.pdf_url

            # 论文类型合并策略：new 优先于 updated
            # 如果新数据标记为 new，则更新为 new
            if self.mark_paper_type and paper.paper_type == "new":
                existing.paper_type = "new"

        # 按发布时间降序排列，最新的论文排在前面
        # Sort by published date
        return sorted(merged.values(), key=lambda p: p.published, reverse=True)

    async def parse(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert fetched papers into article dictionaries.

        调用 Paper.to_article_dict() 转换为 Article 兼容的字典。

        Args:
            raw_data: Dict returned by fetch() containing 'papers'.

        Returns:
            List[Dict[str, Any]]: Article dictionaries.
        """
        papers = raw_data.get("papers", [])
        return [paper.to_article_dict() for paper in papers]
