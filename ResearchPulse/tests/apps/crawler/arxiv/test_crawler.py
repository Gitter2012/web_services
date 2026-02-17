"""Tests for apps/crawler/arxiv/crawler.py — ArxivCrawler improvements.

验证 arXiv 爬虫的改进：
1. Paper 数据类的 paper_type 字段
2. _fetch_atom() 支持参数化排序方式
3. _fetch_rss() 支持新域名和旧域名回退
4. _fetch_html_list() 正确解析新版 HTML 结构
5. _merge_papers() 论文类型合并逻辑
6. 完整 fetch() 流程的多排序模式支持
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Dict, Any

from apps.crawler.arxiv.crawler import (
    Paper,
    ArxivCrawler,
    _clean_text,
    _normalize_arxiv_id,
    _parse_html_list,
    _parse_rss_entry,
)


class TestPaperDataClass:
    """Test Paper dataclass and its methods.

    验证 Paper 数据类的字段和 to_article_dict() 方法。
    """

    def test_paper_default_paper_type(self):
        """Paper should have empty paper_type by default.

        paper_type 默认为空字符串。
        """
        paper = Paper(
            arxiv_id="2301.12345",
            title="Test Paper",
            authors=["Author A", "Author B"],
            primary_category="cs.LG",
            categories=["cs.LG", "cs.AI"],
            abstract="This is an abstract.",
            pdf_url="https://arxiv.org/pdf/2301.12345",
            published="2023-01-15T10:00:00Z",
        )
        assert paper.paper_type == ""

    def test_paper_with_paper_type(self):
        """Paper can be created with paper_type set.

        可以创建带有 paper_type 的 Paper。
        """
        paper = Paper(
            arxiv_id="2301.12345",
            title="Test Paper",
            authors=["Author A"],
            primary_category="cs.LG",
            categories=["cs.LG"],
            abstract="Abstract text.",
            pdf_url="https://arxiv.org/pdf/2301.12345",
            published="2023-01-15T10:00:00Z",
            paper_type="new",
        )
        assert paper.paper_type == "new"

    def test_to_article_dict_includes_paper_type(self):
        """to_article_dict() should include arxiv_paper_type.

        to_article_dict() 应该包含 arxiv_paper_type 字段。
        """
        paper = Paper(
            arxiv_id="2301.12345",
            title="Test Paper",
            authors=["Author A"],
            primary_category="cs.LG",
            categories=["cs.LG"],
            abstract="Abstract text.",
            pdf_url="https://arxiv.org/pdf/2301.12345",
            published="2023-01-15T10:00:00Z",
            paper_type="updated",
        )
        result = paper.to_article_dict()
        assert result["arxiv_paper_type"] == "updated"

    def test_to_article_dict_truncates_long_author_list(self):
        """Author list should be truncated if too long.

        作者列表过长时应该被截断。
        """
        authors = [f"Author {i}" for i in range(100)]
        paper = Paper(
            arxiv_id="2301.12345",
            title="Test Paper",
            authors=authors,
            primary_category="cs.LG",
            categories=["cs.LG"],
            abstract="Abstract.",
            pdf_url="https://arxiv.org/pdf/2301.12345",
            published="2023-01-15T10:00:00Z",
        )
        result = paper.to_article_dict()
        assert len(result["author"]) <= 1000


class TestArxivCrawlerInit:
    """Test ArxivCrawler initialization.

    验证 ArxivCrawler 的初始化参数和 URL 模板。
    """

    def test_default_sort_modes(self):
        """Default sort_modes should be ['lastUpdatedDate'].

        默认 sort_modes 应该是 ['lastUpdatedDate']。
        """
        crawler = ArxivCrawler(category="cs.LG")
        assert crawler.sort_modes == ["lastUpdatedDate"]

    def test_custom_sort_modes(self):
        """Custom sort_modes should be set correctly.

        自定义 sort_modes 应该被正确设置。
        """
        crawler = ArxivCrawler(
            category="cs.LG",
            sort_modes=["submittedDate", "lastUpdatedDate"],
        )
        assert crawler.sort_modes == ["submittedDate", "lastUpdatedDate"]

    def test_mark_paper_type_default(self):
        """mark_paper_type should default to False.

        mark_paper_type 默认为 False。
        """
        crawler = ArxivCrawler(category="cs.LG")
        assert crawler.mark_paper_type is False

    def test_mark_paper_type_custom(self):
        """Custom mark_paper_type should be set correctly.

        自定义 mark_paper_type 应该被正确设置。
        """
        crawler = ArxivCrawler(category="cs.LG", mark_paper_type=True)
        assert crawler.mark_paper_type is True

    def test_rss_format_default(self):
        """rss_format should default to 'rss'.

        rss_format 默认为 'rss'。
        """
        crawler = ArxivCrawler(category="cs.LG")
        assert crawler.rss_format == "rss"

    def test_rss_url_new_domain(self):
        """RSS URL should use new domain rss.arxiv.org.

        RSS URL 应该使用新域名 rss.arxiv.org。
        """
        crawler = ArxivCrawler(category="cs.LG", rss_format="rss")
        assert "rss.arxiv.org" in crawler.rss_url
        assert "/rss/" in crawler.rss_url

    def test_rss_url_atom_format(self):
        """RSS URL should support atom format.

        RSS URL 应该支持 atom 格式。
        """
        crawler = ArxivCrawler(category="cs.LG", rss_format="atom")
        assert "/atom/" in crawler.rss_url

    def test_rss_url_legacy_exists(self):
        """Legacy RSS URL should still exist as fallback.

        旧的 RSS URL 应该作为备用存在。
        """
        crawler = ArxivCrawler(category="cs.LG")
        assert hasattr(crawler, "rss_url_legacy")
        assert "export.arxiv.org" in crawler.rss_url_legacy


class TestFetchAtom:
    """Test ArxivCrawler._fetch_atom() method.

    验证 _fetch_atom() 方法的参数化排序支持。
    """

    @pytest.fixture
    def crawler(self):
        """Create a crawler instance for testing."""
        return ArxivCrawler(category="cs.LG", max_results=5)

    @pytest.mark.asyncio
    async def test_fetch_atom_submitted_date(self, crawler):
        """_fetch_atom should accept sort_by='submittedDate'.

        _fetch_atom 应该接受 sort_by='submittedDate' 参数。
        """
        mock_feed_text = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <id>http://arxiv.org/abs/2301.12345</id>
                <title>Test Paper</title>
                <summary>Test abstract</summary>
                <author><name>Author Name</name></author>
                <category term="cs.LG"/>
            </entry>
        </feed>
        """

        with patch("apps.crawler.arxiv.crawler.get_text_async", new_callable=AsyncMock, return_value=mock_feed_text):
            papers = await crawler._fetch_atom(sort_by="submittedDate")
            assert len(papers) == 1
            assert papers[0].arxiv_id == "2301.12345"

    @pytest.mark.asyncio
    async def test_fetch_atom_last_updated_date(self, crawler):
        """_fetch_atom should accept sort_by='lastUpdatedDate'.

        _fetch_atom 应该接受 sort_by='lastUpdatedDate' 参数。
        """
        mock_feed_text = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <id>http://arxiv.org/abs/2301.12346</id>
                <title>Updated Paper</title>
                <summary>Updated abstract</summary>
                <author><name>Another Author</name></author>
                <category term="cs.LG"/>
            </entry>
        </feed>
        """

        with patch("apps.crawler.arxiv.crawler.get_text_async", new_callable=AsyncMock, return_value=mock_feed_text):
            papers = await crawler._fetch_atom(sort_by="lastUpdatedDate")
            assert len(papers) == 1

    @pytest.mark.asyncio
    async def test_fetch_atom_returns_empty_on_failure(self, crawler):
        """_fetch_atom should return empty list on failure.

        _fetch_atom 失败时应该返回空列表。
        """
        with patch("apps.crawler.arxiv.crawler.get_text_async", new_callable=AsyncMock, side_effect=Exception("Network error")):
            papers = await crawler._fetch_atom(sort_by="submittedDate")
            assert papers == []


class TestFetchRss:
    """Test ArxivCrawler._fetch_rss() method.

    验证 _fetch_rss() 方法的新旧域名回退逻辑。
    """

    @pytest.fixture
    def crawler(self):
        """Create a crawler instance for testing."""
        return ArxivCrawler(category="cs.LG")

    @pytest.mark.asyncio
    async def test_fetch_rss_new_domain_success(self, crawler):
        """_fetch_rss should use new domain first.

        _fetch_rss 应该优先使用新域名。
        """
        mock_feed_text = """<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <title>cs.LG</title>
                <item>
                    <title>Test Paper from RSS</title>
                    <link>https://arxiv.org/abs/2301.12347</link>
                    <description>RSS abstract</description>
                </item>
            </channel>
        </rss>
        """

        with patch("apps.crawler.arxiv.crawler.get_text_async", new_callable=AsyncMock, return_value=mock_feed_text):
            papers = await crawler._fetch_rss()
            assert len(papers) == 1
            assert papers[0].title == "Test Paper from RSS"

    @pytest.mark.asyncio
    async def test_fetch_rss_fallback_to_legacy(self, crawler):
        """_fetch_rss should fallback to legacy domain if new domain fails.

        新域名失败时应该回退到旧域名。
        """
        mock_feed_text = """<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <title>cs.LG</title>
                <item>
                    <title>Paper from Legacy RSS</title>
                    <link>https://arxiv.org/abs/2301.12348</link>
                    <description>Legacy abstract</description>
                </item>
            </channel>
        </rss>
        """

        # First call (new domain) fails, second call (legacy) succeeds
        call_count = [0]

        async def mock_get_text(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("New domain failed")
            return mock_feed_text

        with patch("apps.crawler.arxiv.crawler.get_text_async", new_callable=AsyncMock, side_effect=mock_get_text):
            papers = await crawler._fetch_rss()
            assert len(papers) == 1
            assert papers[0].title == "Paper from Legacy RSS"

    @pytest.mark.asyncio
    async def test_fetch_rss_fallback_on_empty_result(self, crawler):
        """_fetch_rss should fallback if new domain returns empty result.

        新域名返回空结果时应该回退到旧域名。
        """
        empty_feed = """<?xml version="1.0"?><rss version="2.0"><channel><title>Empty</title></channel></rss>"""
        valid_feed = """<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <title>cs.LG</title>
                <item>
                    <title>Valid Paper</title>
                    <link>https://arxiv.org/abs/2301.12349</link>
                </item>
            </channel>
        </rss>
        """

        call_count = [0]

        async def mock_get_text(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return empty_feed
            return valid_feed

        with patch("apps.crawler.arxiv.crawler.get_text_async", new_callable=AsyncMock, side_effect=mock_get_text):
            papers = await crawler._fetch_rss()
            assert len(papers) == 1
            assert papers[0].title == "Valid Paper"


class TestFetchHtmlList:
    """Test ArxivCrawler._fetch_html_list() method.

    验证 _fetch_html_list() 方法的新版 HTML 结构解析。
    """

    @pytest.fixture
    def crawler(self):
        """Create a crawler instance for testing."""
        return ArxivCrawler(category="cs.LG")

    @pytest.mark.asyncio
    async def test_fetch_html_list_new_format(self, crawler):
        """_fetch_html_list should parse new HTML format.

        _fetch_html_list 应该正确解析新版 HTML 结构。
        """
        html = """
        <html><body>
        <dt>
            <a href="/abs/2301.12350">arXiv:2301.12350</a>
        </dt>
        <dd>
            <div class='meta'>
                <div class='list-title mathjax'><span class='descriptor'>Title:</span>
                    Test HTML Paper
                </div>
                <div class='list-authors'>
                    <a href="#">Author One</a>, <a href="#">Author Two</a>
                </div>
                <p class='mathjax'>
                    This is the abstract extracted from the new HTML format.
                </p>
            </div>
        </dd>
        </body></html>
        """

        with patch("apps.crawler.arxiv.crawler.get_text_async", new_callable=AsyncMock, return_value=html):
            papers = await crawler._fetch_html_list(crawler.list_new_url, "2023-01-15")
            assert len(papers) == 1
            assert papers[0].arxiv_id == "2301.12350"
            assert papers[0].title == "Test HTML Paper"
            assert len(papers[0].authors) == 2
            assert "abstract" in papers[0].abstract.lower()


class TestMergePapers:
    """Test ArxivCrawler._merge_papers() method.

    验证 _merge_papers() 方法的论文类型合并逻辑。
    """

    def create_paper(self, arxiv_id, title, authors, abstract, paper_type=""):
        """Helper to create a Paper instance."""
        return Paper(
            arxiv_id=arxiv_id,
            title=title,
            authors=authors,
            primary_category="cs.LG",
            categories=["cs.LG"],
            abstract=abstract,
            pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
            published="2023-01-15T10:00:00Z",
            paper_type=paper_type,
        )

    def test_merge_keeps_new_over_updated(self):
        """When merging, 'new' paper_type should have priority over 'updated'.

        合并时 'new' 类型应该优先于 'updated'。
        """
        crawler = ArxivCrawler(category="cs.LG", mark_paper_type=True)

        paper1 = self.create_paper("2301.12345", "Test", ["A"], "Short", "updated")
        paper2 = self.create_paper("2301.12345", "Test Paper Full Title", ["A", "B"], "This is a longer abstract with more details", "new")

        merged = crawler._merge_papers([paper1, paper2])
        assert len(merged) == 1
        assert merged[0].paper_type == "new"

    def test_merge_keeps_longer_content(self):
        """When merging, longer content should be kept.

        合并时应该保留更长的内容。
        """
        crawler = ArxivCrawler(category="cs.LG")

        paper1 = self.create_paper("2301.12345", "Short Title", ["A"], "Short abstract", "")
        paper2 = self.create_paper("2301.12345", "This is a much longer title for the paper", ["A", "B", "C"], "This is a much longer abstract with more details and information about the paper", "")

        merged = crawler._merge_papers([paper1, paper2])
        assert len(merged) == 1
        assert len(merged[0].title) > len("Short Title")
        assert len(merged[0].authors) == 3

    def test_merge_deduplicates_by_normalized_id(self):
        """Papers with version suffix should be deduplicated.

        带版本号的论文 ID 应该被去重。
        """
        crawler = ArxivCrawler(category="cs.LG")

        paper1 = self.create_paper("2301.12345v1", "Paper v1", ["A"], "Abstract v1", "")
        paper2 = self.create_paper("2301.12345v2", "Paper v2", ["A"], "Abstract v2", "")

        merged = crawler._merge_papers([paper1, paper2])
        assert len(merged) == 1


class TestFetchMethod:
    """Test ArxivCrawler.fetch() method integration.

    验证 fetch() 方法的完整流程。
    """

    @pytest.fixture
    def crawler(self):
        """Create a crawler instance with all features enabled."""
        return ArxivCrawler(
            category="cs.LG",
            max_results=5,
            sort_modes=["submittedDate", "lastUpdatedDate"],
            mark_paper_type=True,
            rss_format="rss",
        )

    @pytest.mark.asyncio
    async def test_fetch_marks_paper_types(self, crawler):
        """fetch() should mark paper types based on sort mode.

        fetch() 应该根据排序模式标记论文类型。
        """
        mock_atom_feed = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <id>http://arxiv.org/abs/2301.12345</id>
                <title>Submitted Paper</title>
                <summary>Abstract for submitted paper</summary>
                <author><name>Author</name></author>
                <category term="cs.LG"/>
                <published>2023-01-15T10:00:00Z</published>
            </entry>
        </feed>
        """

        with patch("apps.crawler.arxiv.crawler.get_text_async", new_callable=AsyncMock, return_value=mock_atom_feed):
            # Mock RSS and HTML to return empty
            with patch.object(crawler, "_fetch_rss", new_callable=AsyncMock, return_value=[]):
                with patch.object(crawler, "_fetch_html_list", new_callable=AsyncMock, return_value=[]):
                    result = await crawler.fetch()

        papers = result["papers"]
        assert len(papers) >= 1
        # Paper from submittedDate should be marked as "new"
        for paper in papers:
            if paper.arxiv_id == "2301.12345":
                assert paper.paper_type == "new"


class TestHelperFunctions:
    """Test helper functions in crawler.py.

    验证辅助函数的正确性。
    """

    def test_normalize_arxiv_id_removes_version(self):
        """_normalize_arxiv_id should remove version suffix.

        _normalize_arxiv_id 应该移除版本号后缀。
        """
        assert _normalize_arxiv_id("2301.12345v1") == "2301.12345"
        assert _normalize_arxiv_id("2301.12345v2") == "2301.12345"
        assert _normalize_arxiv_id("2301.12345") == "2301.12345"

    def test_clean_text_strips_html(self):
        """_clean_text should strip HTML tags.

        _clean_text 应该移除 HTML 标签。
        """
        assert _clean_text("<p>Hello <b>World</b></p>") == "Hello World"

    def test_clean_text_unescapes_entities(self):
        """_clean_text should unescape HTML entities.

        _clean_text 应该反转义 HTML 实体。
        """
        assert _clean_text("A &amp; B &lt; C") == "A & B < C"
