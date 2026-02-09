from __future__ import annotations

import feedparser

from apps.arxiv_crawler import parser
from apps.arxiv_crawler.parser import Paper

ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/1234.5678v1</id>
    <updated>2026-02-07T00:00:00Z</updated>
    <published>2026-02-07T00:00:00Z</published>
    <title>  Test Paper  </title>
    <summary>  This is an abstract. </summary>
    <author><name>Alice</name></author>
    <author><name>Bob</name></author>
    <arxiv:primary_category term="cs.LG" scheme="http://arxiv.org/schemas/atom" />
    <category term="cs.LG" />
    <category term="cs.AI" />
    <link rel="alternate" type="text/html" href="http://arxiv.org/abs/1234.5678v1" />
    <link title="pdf" rel="related" type="application/pdf" href="http://arxiv.org/pdf/1234.5678v1" />
  </entry>
</feed>
"""

RSS_FEED = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <item>
      <title>RSS Paper</title>
      <link>http://arxiv.org/abs/1111.2222v1</link>
      <description>RSS abstract</description>
      <author>Alice,Bob</author>
      <category>cs.LG</category>
      <pubDate>Wed, 07 Feb 2026 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

HTML_LIST = """<h3>SHOWING NEW LISTINGS FOR MONDAY, 9 FEBRUARY 2026</h3>
<dl>
<dt><a href="/abs/3333.4444v1">arXiv:3333.4444v1</a></dt>
<dd>
<div class="list-title mathjax"><span class="descriptor">Title:</span> HTML List Paper</div>
<div class="list-authors"><span class="descriptor">Authors:</span>
<a href="/search/?searchtype=author&amp;query=Alice">Alice</a>
</div>
<p class="mathjax"><span class="descriptor">Abstract:</span> List abstract</p>
<div class="list-subjects"><span class="descriptor">Subjects:</span> cs.LG; cs.AI</div>
</dd>
</dl>
"""

HTML_LIST_RECENT = """<h3>SHOWING RECENT LISTINGS FOR MONDAY, 10 FEBRUARY 2026</h3>
<dl>
<dt><a href="/abs/4444.5555">arXiv:4444.5555</a></dt>
<dd>
<div class="list-title mathjax"><span class="descriptor">Title:</span> HTML Recent Paper</div>
<div class="list-authors"><span class="descriptor">Authors:</span>
<a href="/search/?searchtype=author&amp;query=Alice">Alice</a>
</div>
<p class="mathjax"><span class="descriptor">Abstract:</span> Recent abstract</p>
<div class="list-subjects"><span class="descriptor">Subjects:</span> cs.LG; cs.AI</div>
</dd>
</dl>
"""

HTML_SEARCH = """<li class="arxiv-result">
<p class="title is-5 mathjax">Search Paper</p>
<p class="authors">
<a href="/search/?searchtype=author&amp;query=Bob">Bob</a>
</p>
<p class="is-size-7">Submitted 9 February 2026</p>
<span class="abstract-full">Search abstract</span>
<span class="tag is-small is-link">cs.LG</span>
<a href="/pdf/5555.6666v1">pdf</a>
<a href="/abs/5555.6666v1">abs</a>
</li>
"""

HTML_SEARCH_NO_DATE = """<li class="arxiv-result">
<p class="title is-5 mathjax">Search Paper</p>
<p class="authors">
<a href="/search/?searchtype=author&amp;query=Bob">Bob</a>
</p>
<span class="abstract-full">Search abstract</span>
<span class="tag is-small is-link">cs.LG</span>
<a href="/pdf/5555.6666v1">pdf</a>
<a href="/abs/5555.6666v1">abs</a>
</li>
"""


def test_parse_entry_fields() -> None:
    feed = feedparser.parse(ATOM_FEED)
    paper = parser._parse_entry(feed.entries[0])

    assert paper.arxiv_id == "1234.5678v1"
    assert paper.title == "Test Paper"
    assert paper.authors == ["Alice", "Bob"]
    assert paper.primary_category == "cs.LG"
    assert "cs.AI" in paper.categories
    assert paper.pdf_url.endswith("1234.5678v1")
    assert paper.published.startswith("2026-02-07")


def test_parse_rss_entry() -> None:
    feed = feedparser.parse(RSS_FEED)
    paper = parser._parse_rss_entry(feed.entries[0])
    assert paper.arxiv_id == "1111.2222v1"
    assert paper.title == "RSS Paper"
    assert "Alice" in paper.authors


def test_parse_html_list() -> None:
    papers = parser._parse_html_list(HTML_LIST)
    assert papers[0].arxiv_id == "3333.4444v1"
    assert papers[0].title == "HTML List Paper"
    assert "Alice" in papers[0].authors
    assert papers[0].published.startswith("2026-02-09")


def test_parse_html_search() -> None:
    papers = parser._parse_html_search(HTML_SEARCH)
    assert papers[0].arxiv_id == "5555.6666v1"
    assert papers[0].title == "Search Paper"
    assert "Bob" in papers[0].authors
    assert papers[0].published.startswith("2026-02-09")


def test_parse_html_list_recent() -> None:
    papers = parser._parse_html_list(HTML_LIST_RECENT)
    assert papers[0].arxiv_id == "4444.5555"
    assert papers[0].published.startswith("2026-02-10")


def test_parse_html_search_fallback_date() -> None:
    papers = parser._parse_html_search(HTML_SEARCH_NO_DATE, run_date="2026-02-10")
    assert papers[0].published.startswith("2026-02-10")


def test_merge_unique_by_id_normalizes_versions() -> None:
    papers = [
        Paper(
            arxiv_id="2602.06935v1",
            title="Title",
            authors=["Author"],
            primary_category="cs.IR",
            categories=["cs.IR"],
            abstract="Abstract",
            pdf_url="",
            published="2026-02-05T00:00:00Z",
        ),
        Paper(
            arxiv_id="2602.06935",
            title="",
            authors=[],
            primary_category="",
            categories=[],
            abstract="",
            pdf_url="",
            published="2026-02-09T00:00:00Z",
        ),
    ]
    merged = parser.merge_unique_by_id(papers)
    assert len(merged) == 1
    assert merged[0].arxiv_id == "2602.06935v1"
    assert merged[0].published.startswith("2026-02-09")


def test_clean_text() -> None:
    assert parser._clean_text("  a \n b  ") == "a b"


def test_serialize_papers() -> None:
    paper = Paper(
        arxiv_id="9999.0000v1",
        title="Title",
        authors=["Author"],
        primary_category="cs.LG",
        categories=["cs.LG"],
        abstract="Abstract",
        pdf_url="http://arxiv.org/pdf/9999.0000v1",
        published="2026-02-07T00:00:00Z",
    )
    serialized = parser.serialize_papers([paper])
    assert serialized[0]["arxiv_id"] == "9999.0000v1"
    assert serialized[0]["authors"] == "Author"
