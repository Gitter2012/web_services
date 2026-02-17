"""Tests for apps/crawler/rss/crawler.py — RssCrawler content extraction fixes.

验证 RSS 爬虫的正文提取修复：
1. _content_needs_fetch() 正确判断是否需要抓取原文
2. _fetch_full_content() 正确提取网页正文
3. parse() 在 RSS 未提供完整正文时自动补全内容
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from apps.crawler.rss.crawler import RssCrawler


class TestContentNeedsFetch:
    """Test RssCrawler._content_needs_fetch() static method.

    验证判断文章是否需要从原文 URL 提取正文的逻辑。
    """

    def test_empty_content_needs_fetch(self):
        """Content is empty — should fetch.

        content 为空时应该返回 True。
        """
        article = {"content": "", "summary": "Some summary"}
        assert RssCrawler._content_needs_fetch(article) is True

    def test_none_content_needs_fetch(self):
        """Content is None — should fetch.

        content 为 None 时应该返回 True。
        """
        article = {"content": None, "summary": "Some summary"}
        assert RssCrawler._content_needs_fetch(article) is True

    def test_missing_content_needs_fetch(self):
        """Content key missing — should fetch.

        字典中没有 content 键时应该返回 True。
        """
        article = {"summary": "Some summary"}
        assert RssCrawler._content_needs_fetch(article) is True

    def test_content_equals_summary_needs_fetch(self):
        """Content identical to summary — should fetch.

        content 与 summary 完全相同时应该返回 True（说明 RSS 只提供了摘要）。
        """
        text = "This is just a short summary."
        article = {"content": text, "summary": text}
        assert RssCrawler._content_needs_fetch(article) is True

    def test_short_content_needs_fetch(self):
        """Content too short (< 200 chars after stripping HTML) — should fetch.

        去除 HTML 标签后正文不足 200 字符时应该返回 True。
        """
        article = {
            "content": "<p>Short paragraph.</p>",
            "summary": "Different summary",
        }
        assert RssCrawler._content_needs_fetch(article) is True

    def test_long_content_no_fetch(self):
        """Content is long and different from summary — should not fetch.

        正文足够长且与摘要不同时应该返回 False。
        """
        long_text = "A " * 200  # 400 chars of plain text
        article = {
            "content": long_text,
            "summary": "Short summary",
        }
        assert RssCrawler._content_needs_fetch(article) is False

    def test_long_html_content_no_fetch(self):
        """Long content with HTML tags — should not fetch.

        包含 HTML 的长正文（去除标签后仍超过 200 字符）不需要抓取。
        """
        paragraphs = "".join(f"<p>Paragraph number {i} with some text content here.</p>" for i in range(20))
        article = {
            "content": paragraphs,
            "summary": "Short summary",
        }
        assert RssCrawler._content_needs_fetch(article) is False


class TestFetchFullContent:
    """Test RssCrawler._fetch_full_content() async method.

    验证从原文 URL 提取网页正文的逻辑。
    """

    @pytest.fixture
    def crawler(self):
        """Create a RssCrawler instance for testing."""
        return RssCrawler(feed_id="test-feed", feed_url="https://example.com/rss")

    @pytest.mark.asyncio
    async def test_extract_from_article_tag(self, crawler):
        """Extract content from <article> tag.

        优先从 <article> 标签中提取正文。
        """
        html = """
        <html><body>
            <nav>Navigation</nav>
            <article>
                <h1>Article Title</h1>
                <p>This is the first paragraph of the article with enough content to pass the threshold.</p>
                <p>This is the second paragraph with more details about the topic being discussed here.</p>
                <p>And a third paragraph to ensure we have enough text content for extraction to work properly.</p>
            </article>
            <footer>Footer content</footer>
        </body></html>
        """
        with patch("apps.crawler.rss.crawler.get_text_async", new_callable=AsyncMock, return_value=html):
            result = await crawler._fetch_full_content("https://example.com/article")
            assert "first paragraph" in result
            assert "second paragraph" in result
            assert "Navigation" not in result
            assert "Footer" not in result

    @pytest.mark.asyncio
    async def test_extract_from_content_class(self, crawler):
        """Extract content from div with content class when no <article> tag exists.

        没有 <article> 标签时，从 class 匹配的 div 中提取。
        """
        html = """
        <html><body>
            <div class="sidebar">Sidebar content</div>
            <div class="article-content">
                <p>Main article content goes here with enough text to be recognized as the main content area.</p>
                <p>More paragraphs to fill out the body of the article that we want to extract from the page.</p>
                <p>Third paragraph ensuring the content length exceeds the minimum threshold of 100 characters.</p>
            </div>
        </body></html>
        """
        with patch("apps.crawler.rss.crawler.get_text_async", new_callable=AsyncMock, return_value=html):
            result = await crawler._fetch_full_content("https://example.com/article")
            assert "Main article content" in result
            assert "Sidebar" not in result

    @pytest.mark.asyncio
    async def test_extract_from_post_content_class(self, crawler):
        """Extract content from div with post-content class.

        从 post-content class 的 div 中提取。
        """
        html = """
        <html><body>
            <div class="post-content">
                <p>Blog post content is written here with detailed explanations about the topic being covered.</p>
                <p>Additional paragraph with supporting information and evidence for the claims made above.</p>
            </div>
        </body></html>
        """
        with patch("apps.crawler.rss.crawler.get_text_async", new_callable=AsyncMock, return_value=html):
            result = await crawler._fetch_full_content("https://example.com/article")
            assert "Blog post content" in result

    @pytest.mark.asyncio
    async def test_fallback_to_paragraphs(self, crawler):
        """Fall back to collecting <p> tags when no semantic container found.

        没有语义化容器时，降级提取所有 <p> 标签的文本。
        """
        html = """
        <html><body>
            <div>
                <p>First important paragraph with meaningful content about the subject matter discussed.</p>
                <p>Second paragraph providing additional context and details for the reader to understand.</p>
                <p>Third paragraph concluding the article with a summary of the main points covered.</p>
            </div>
        </body></html>
        """
        with patch("apps.crawler.rss.crawler.get_text_async", new_callable=AsyncMock, return_value=html):
            result = await crawler._fetch_full_content("https://example.com/article")
            assert "First important paragraph" in result

    @pytest.mark.asyncio
    async def test_returns_empty_on_fetch_failure(self, crawler):
        """Return empty string when HTTP fetch fails.

        HTTP 请求失败时返回空字符串。
        """
        with patch("apps.crawler.rss.crawler.get_text_async", new_callable=AsyncMock, side_effect=RuntimeError("Network error")):
            result = await crawler._fetch_full_content("https://example.com/article")
            assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_on_empty_html(self, crawler):
        """Return empty string when page has no extractable content.

        页面无可提取内容时返回空字符串。
        """
        html = "<html><body><script>var x = 1;</script></body></html>"
        with patch("apps.crawler.rss.crawler.get_text_async", new_callable=AsyncMock, return_value=html):
            result = await crawler._fetch_full_content("https://example.com/article")
            assert result == ""

    @pytest.mark.asyncio
    async def test_strips_script_and_style_tags(self, crawler):
        """Verify script and style tags are removed before extraction.

        确保 script 和 style 标签在提取前被移除。
        """
        html = """
        <html><body>
            <style>.content { color: red; }</style>
            <script>console.log('tracking');</script>
            <article>
                <p>Clean article content that should be extracted without any scripts or styles mixed in.</p>
                <p>More content here to ensure we pass the minimum length threshold for valid extraction.</p>
            </article>
        </body></html>
        """
        with patch("apps.crawler.rss.crawler.get_text_async", new_callable=AsyncMock, return_value=html):
            result = await crawler._fetch_full_content("https://example.com/article")
            assert "tracking" not in result
            assert "color: red" not in result
            assert "Clean article content" in result


class TestParseWithContentFetch:
    """Test RssCrawler.parse() content fetching integration.

    验证 parse() 方法在 RSS 未提供完整正文时自动从原文 URL 提取内容。
    """

    @pytest.fixture
    def crawler(self):
        """Create a RssCrawler instance for testing."""
        return RssCrawler(feed_id="test-feed", feed_url="https://example.com/rss")

    @pytest.mark.asyncio
    async def test_parse_fetches_content_when_summary_only(self, crawler):
        """Verify parse() fetches full content when RSS only provides summary.

        当 RSS 只提供摘要时，parse() 应该尝试从原文提取完整正文。
        """
        # RSS XML with only summary (no content:encoded)
        rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>Test Feed</title>
                <item>
                    <title>Test Article</title>
                    <link>https://example.com/article/1</link>
                    <description>Short summary only.</description>
                    <author>Author Name</author>
                </item>
            </channel>
        </rss>
        """

        fetched_content = "Full article content extracted from the original page with detailed information. " * 5

        with patch.object(crawler, "_fetch_full_content", new_callable=AsyncMock, return_value=fetched_content):
            articles = await crawler.parse(rss_xml)
            assert len(articles) == 1
            assert articles[0]["content"] == fetched_content
            # summary should remain unchanged
            assert articles[0]["summary"] == "Short summary only."

    @pytest.mark.asyncio
    async def test_parse_keeps_existing_full_content(self, crawler):
        """Verify parse() preserves content when RSS provides full content.

        当 RSS 提供了完整正文时，parse() 不应该替换它。
        """
        long_body = "Detailed article body with lots of information. " * 20

        rss_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
            <channel>
                <title>Test Feed</title>
                <item>
                    <title>Test Article</title>
                    <link>https://example.com/article/1</link>
                    <description>Short summary.</description>
                    <content:encoded><![CDATA[{long_body}]]></content:encoded>
                </item>
            </channel>
        </rss>
        """

        with patch.object(crawler, "_fetch_full_content", new_callable=AsyncMock) as mock_fetch:
            articles = await crawler.parse(rss_xml)
            assert len(articles) == 1
            # _fetch_full_content should NOT be called because content is long enough
            mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_parse_handles_fetch_failure_gracefully(self, crawler):
        """Verify parse() handles content fetch failure gracefully.

        当原文提取失败时，parse() 应该保留原有内容，不报错。
        """
        rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>Test Feed</title>
                <item>
                    <title>Test Article</title>
                    <link>https://example.com/article/1</link>
                    <description>Short summary.</description>
                </item>
            </channel>
        </rss>
        """

        with patch.object(crawler, "_fetch_full_content", new_callable=AsyncMock, side_effect=Exception("Network timeout")):
            articles = await crawler.parse(rss_xml)
            assert len(articles) == 1
            # Article should still be present with original content
            assert articles[0]["summary"] == "Short summary."
