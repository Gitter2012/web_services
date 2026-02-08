from __future__ import annotations

from apps.arxiv_crawler import tasks
from apps.arxiv_crawler.parser import Paper


def _make_paper(arxiv_id: str, published: str) -> Paper:
    return Paper(
        arxiv_id=arxiv_id,
        title="Title",
        authors=["Alice"],
        primary_category="cs.LG",
        categories=["cs.LG"],
        abstract="Abstract",
        pdf_url=f"http://arxiv.org/pdf/{arxiv_id}",
        published=published,
    )


def test_run_crawl(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(tasks, "utc_today_str", lambda: "2026-02-07")
    monkeypatch.setattr(tasks.settings, "data_dir", tmp_path)

    monkeypatch.setattr(tasks.arxiv_settings, "arxiv_categories", "cs.LG,cs.CV")
    monkeypatch.setattr(tasks.arxiv_settings, "arxiv_max_results", 3)
    monkeypatch.setattr(tasks.arxiv_settings, "arxiv_min_results", 2)
    monkeypatch.setattr(tasks.arxiv_settings, "arxiv_fallback_days", 7)
    monkeypatch.setattr(tasks.arxiv_settings, "arxiv_base_url", "http://example.com")
    monkeypatch.setattr(tasks.arxiv_settings, "arxiv_rss_url", "http://example.com/rss")
    monkeypatch.setattr(tasks.arxiv_settings, "arxiv_html_list_url", "http://example.com/list")
    monkeypatch.setattr(tasks.arxiv_settings, "arxiv_html_search_url", "http://example.com/search")

    monkeypatch.setattr(tasks.arxiv_settings, "email_enabled", True)
    monkeypatch.setattr(tasks.arxiv_settings, "email_html_enabled", True)
    monkeypatch.setattr(tasks.arxiv_settings, "abstract_max_len", 50)

    monkeypatch.setattr(tasks.arxiv_settings, "email_from", "from@example.com")
    monkeypatch.setattr(tasks.arxiv_settings, "email_to", "to@example.com")
    monkeypatch.setattr(tasks.arxiv_settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(tasks.arxiv_settings, "smtp_port", 587)
    monkeypatch.setattr(tasks.arxiv_settings, "smtp_user", "user")
    monkeypatch.setattr(tasks.arxiv_settings, "smtp_password", "pass")

    papers_by_category = {
        "cs.LG": [_make_paper("1234.0001v1", "2026-02-07T00:00:00Z")],
        "cs.CV": [],
    }

    def fake_fetch_papers_multi(category: str, **kwargs):
        return papers_by_category[category]

    monkeypatch.setattr(tasks, "fetch_papers_multi", fake_fetch_papers_multi)
    monkeypatch.setattr(tasks, "write_markdown", lambda path, content: None)

    sent = {}

    def fake_send_email(**kwargs):
        sent["called"] = True
        sent["subject"] = kwargs.get("subject")
        sent["body"] = kwargs.get("body")
        sent["html_body"] = kwargs.get("html_body")
        return True, ""

    monkeypatch.setattr(tasks, "send_email", fake_send_email)

    status = tasks.run_crawl()
    assert status["last_error"] is None
    assert status["last_files"]
    assert sent.get("called") is True
    assert "多分类论文汇总" in sent.get("subject", "")
    assert "共1篇" in sent.get("subject", "")
    assert "### 🔹 cs.LG" in sent.get("body", "")
    assert "### 🔹 cs.CV" not in sent.get("body", "")
    assert sent.get("html_body")
