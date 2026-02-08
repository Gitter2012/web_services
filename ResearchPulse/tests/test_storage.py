from __future__ import annotations

from pathlib import Path

from common.storage import (
    build_output_path,
    render_aggregated_html,
    render_aggregated_markdown,
    render_html,
    render_markdown,
)


def test_build_output_path() -> None:
    base = Path("/tmp")
    path = build_output_path(base, "cs.LG", "2026-02-07")
    assert path.as_posix().endswith("/arxiv/2026/02/07/2026-02-07_cs.LG.md")

    path2 = build_output_path(base, "astro-ph/HE", "2026-02-07")
    assert "astro-ph-HE" in path2.name


def test_render_markdown_and_html() -> None:
    metadata = {
        "date": "2026-02-07",
        "category": "cs.LG",
        "count": "1",
        "generated_at": "2026-02-07T00:00:00Z",
    }
    papers = [
        {
            "arxiv_id": "1234.5678v1",
            "title": "Paper Title",
            "authors": "Alice, Bob",
            "primary_category": "cs.LG",
            "categories": "cs.LG, cs.AI",
            "abstract": "A" * 20,
            "pdf_url": "http://arxiv.org/pdf/1234.5678v1",
            "published": "2026-02-07T00:00:00Z",
        }
    ]

    markdown = render_markdown(metadata, papers, abstract_max_len=10)
    assert markdown.startswith("# cs.LG (2026-02-07)")
    assert "### [1234.5678v1] Paper Title" in markdown
    assert "**Authors**: Alice, Bob" in markdown
    assert "**Categories**: cs.LG, cs.AI" in markdown
    assert "**Date**: 2026-02-07" in markdown
    assert "**Abstract**: AAAAAAA..." in markdown
    assert "[PDF](http://arxiv.org/pdf/1234.5678v1)" in markdown
    assert "[翻译](https://hjfy.top/arxiv/1234.5678v1)" in markdown

    html = render_html(metadata, papers, abstract_max_len=10)
    assert "<h1>cs.LG (2026-02-07)</h1>" in html
    assert "[1234.5678v1]" in html
    assert "PDF" in html
    assert "翻译" in html
    assert "Abstract:</strong> AAAAAAA..." in html


def test_render_aggregated_outputs() -> None:
    sections = {
        "cs.LG": [
            {
                "arxiv_id": "1234.5678v1",
                "title": "Paper Title",
                "authors": "Alice",
                "primary_category": "cs.LG",
                "categories": "cs.LG",
                "abstract": "B" * 20,
                "pdf_url": "http://arxiv.org/pdf/1234.5678v1",
                "published": "2026-02-07T00:00:00Z",
            }
        ],
        "cs.CV": [
            {
                "arxiv_id": "2222.3333v1",
                "title": "Vision Title",
                "authors": "Bob",
                "primary_category": "cs.CV",
                "categories": "cs.CV",
                "abstract": "C" * 20,
                "pdf_url": "http://arxiv.org/pdf/2222.3333v1",
                "published": "2026-02-07T00:00:00Z",
            }
        ],
    }

    markdown = render_aggregated_markdown("2026-02-07", sections, abstract_max_len=10)
    assert "ResearchPulse 每日学术简报 | 2026-02-07" in markdown
    assert "覆盖分类" in markdown
    assert "### 🔹 cs.CV" in markdown

    html = render_aggregated_html("2026-02-07", sections, abstract_max_len=10)
    assert "ResearchPulse 每日学术简报 | 2026-02-07" in html
    assert "cs.LG" in html
    assert "cs.CV" in html
