from __future__ import annotations

import re
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Dict, Iterable, List

from common.utils import window_dates


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _date_parts(run_date: str) -> tuple[str, str, str] | None:
    try:
        parsed = datetime.strptime(run_date, "%Y-%m-%d")
    except ValueError:
        return None
    return parsed.strftime("%Y"), parsed.strftime("%m"), parsed.strftime("%d")


def build_output_path(base_dir: Path, category: str, run_date: str) -> Path:
    safe_category = category.replace("/", "-")
    base_path = base_dir / "arxiv"
    date_parts = _date_parts(run_date)
    if date_parts:
        base_path = base_path / date_parts[0] / date_parts[1] / date_parts[2]
    return base_path / f"{run_date}_{safe_category}.md"


def migrate_legacy_arxiv_outputs(base_dir: Path) -> None:
    arxiv_dir = base_dir / "arxiv"
    if not arxiv_dir.exists():
        return
    for file_path in arxiv_dir.glob("*.md"):
        if not file_path.is_file():
            continue
        match = re.match(r"^(\d{4}-\d{2}-\d{2})_", file_path.name)
        if not match:
            continue
        run_date = match.group(1)
        date_parts = _date_parts(run_date)
        if not date_parts:
            continue
        target_dir = arxiv_dir / date_parts[0] / date_parts[1] / date_parts[2]
        ensure_dir(target_dir)
        target_path = target_dir / file_path.name
        if target_path.exists():
            continue
        file_path.rename(target_path)


def _truncate(text: str, max_len: int) -> str:
    if max_len <= 0 or len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _clean_field(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = escape(cleaned)
    return " ".join(cleaned.replace("\n", " ").split()).strip()


def _abs_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""


def _translate_url(arxiv_id: str) -> str:
    return f"https://hjfy.top/arxiv/{arxiv_id}" if arxiv_id else ""


def _paper_source_date(paper: Dict[str, str]) -> str:
    source_date = paper.get("source_date") or paper.get("published", "").split("T")[0]
    return source_date


def _sort_papers(papers: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    def sort_key(item: Dict[str, str]) -> tuple[str, str]:
        return (_paper_source_date(item), item.get("arxiv_id", ""))

    return sorted(papers, key=sort_key, reverse=True)


def _history_range(dates: List[str]) -> str:
    if not dates:
        return "无"
    return f"{dates[0]} ~ {dates[-1]}"


def _global_stats(
    sections: Dict[str, List[Dict[str, str]]],
    today_dates: set[str],
) -> tuple[int, int, int, List[str], str]:
    categories = list(sections.keys())
    total = sum(len(items) for items in sections.values())
    today = 0
    history = 0
    history_dates: List[str] = []
    for items in sections.values():
        for paper in items:
            date = _paper_source_date(paper)
            if date and date in today_dates:
                today += 1
            else:
                history += 1
                if date:
                    history_dates.append(date)
    history_dates = sorted(set(history_dates))
    history_range = _history_range(history_dates)
    return total, today, history, categories, history_range


def _category_stats(
    papers: List[Dict[str, str]],
    today_dates: set[str],
) -> tuple[int, int, str]:
    today = 0
    history = 0
    history_dates: List[str] = []
    for paper in papers:
        date = _paper_source_date(paper)
        if date and date in today_dates:
            today += 1
        else:
            history += 1
            if date:
                history_dates.append(date)
    history_dates = sorted(set(history_dates))
    history_range = _history_range(history_dates)
    return today, history, history_range


def render_markdown(
    metadata: Dict[str, str],
    papers: Iterable[Dict[str, str]],
    abstract_max_len: int = 800,
) -> str:
    title = f"{metadata.get('category', '')} ({metadata.get('date', '')})"
    lines: List[str] = [f"# {title}", ""]

    for paper in _sort_papers(papers):
        paper_title = _clean_field(paper.get("title", ""))
        arxiv_id = _clean_field(paper.get("arxiv_id", ""))
        pdf_url = paper.get("pdf_url", "")
        translate_url = _translate_url(arxiv_id)
        abstract = _truncate(_clean_field(paper.get("abstract", "")), abstract_max_len)
        source_date = _clean_field(paper.get("source_date") or paper.get("published", "").split("T")[0])
        if not source_date:
            source_date = metadata.get("date", "")
        abs_url = _abs_url(arxiv_id)
        primary_category = _clean_field(paper.get("primary_category", ""))
        categories = _clean_field(paper.get("categories", ""))
        published = _clean_field(paper.get("published", ""))
        updated = _clean_field(paper.get("updated", ""))

        pdf_link = pdf_url or (f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else "")
        lines.append(f"### [{arxiv_id}] {paper_title}")
        lines.append("")
        lines.append(f"**arXiv ID**: {arxiv_id}")
        lines.append(f"**Authors**: {_clean_field(paper.get('authors', ''))}")
        lines.append(f"**Primary Category**: {primary_category}")
        lines.append(f"**Categories**: {categories}")
        lines.append(f"**Published**: {published}")
        lines.append(f"**Updated**: {updated}")
        lines.append(f"**Date**: {source_date}")
        lines.append(f"**Abstract**: {abstract}")
        lines.append("")
        links = []
        if pdf_link:
            links.append(f"[PDF]({pdf_link})")
        if abs_url:
            links.append(f"[abs]({abs_url})")
        if translate_url:
            links.append(f"[翻译]({translate_url})")
        if links:
            lines.append(" | ".join(links))
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def render_html(
    metadata: Dict[str, str],
    papers: Iterable[Dict[str, str]],
    abstract_max_len: int = 800,
) -> str:
    title = f"{metadata.get('category', '')} ({metadata.get('date', '')})"
    parts: List[str] = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "<meta charset='utf-8' />",
        f"<title>{escape(title)}</title>",
        "</head>",
        "<body style='font-family: Arial, sans-serif; line-height: 1.5;'>",
        f"<h1>{escape(title)}</h1>",
    ]

    for paper in _sort_papers(papers):
        paper_title = _clean_field(paper.get("title", ""))
        arxiv_id = _clean_field(paper.get("arxiv_id", ""))
        pdf_url = paper.get("pdf_url", "")
        translate_url = _translate_url(arxiv_id)
        abstract = _truncate(_clean_field(paper.get("abstract", "")), abstract_max_len)
        source_date = _clean_field(_paper_source_date(paper) or metadata.get("date", ""))
        abs_url = _abs_url(arxiv_id)
        primary_category = _clean_field(paper.get("primary_category", ""))
        categories = _clean_field(paper.get("categories", ""))
        published = _clean_field(paper.get("published", ""))
        updated = _clean_field(paper.get("updated", ""))

        pdf_link = pdf_url or (f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else "")
        parts.append(f"<h2>[{arxiv_id}] {paper_title}</h2>")
        parts.append("<ul>")
        parts.append(f"<li><strong>arXiv ID:</strong> {arxiv_id}</li>")
        parts.append(f"<li><strong>Authors:</strong> {_clean_field(paper.get('authors', ''))}</li>")
        parts.append(f"<li><strong>Primary Category:</strong> {primary_category}</li>")
        parts.append(f"<li><strong>Categories:</strong> {categories}</li>")
        parts.append(f"<li><strong>Published:</strong> {published}</li>")
        parts.append(f"<li><strong>Updated:</strong> {updated}</li>")
        parts.append(f"<li><strong>Date:</strong> {source_date}</li>")
        parts.append(f"<li><strong>Abstract:</strong> {abstract}</li>")
        link_items = []
        if pdf_link:
            link_items.append(f"<a href='{escape(pdf_link)}'>PDF</a>")
        if abs_url:
            link_items.append(f"<a href='{escape(abs_url)}'>abs</a>")
        if translate_url:
            link_items.append(f"<a href='{escape(translate_url)}'>翻译</a>")
        if link_items:
            parts.append(f"<li><strong>Links:</strong> {' | '.join(link_items)}</li>")
        parts.append("</ul>")

    parts.extend(["</body>", "</html>"])
    return "\n".join(parts)


def render_aggregated_markdown(
    latest_date: str,
    sections: Dict[str, List[Dict[str, str]]],
    abstract_max_len: int = 800,
    today_window_days: int = 2,
) -> str:
    today_dates = window_dates(latest_date, today_window_days)
    total, today_count, history_count, categories, history_range = _global_stats(
        sections, today_dates
    )
    today_range = _history_range(sorted(today_dates))
    lines: List[str] = [f"# 📬 ResearchPulse 每日学术简报 | {latest_date}", ""]
    lines.append("## 📊 全局统计")
    lines.append(f"- **覆盖分类**: {', '.join(categories)}（共{len(categories)}类）")
    lines.append(f"- **当日新增**: {today_count}篇（{today_range}）")
    lines.append(f"- **历史回溯**: {history_count}篇（{history_range}）")
    lines.append(f"- **总计**: {total}篇")
    lines.append("")
    lines.append("### 分类统计")
    lines.append("| 分类 | 当日 | 历史 | 总计 |")
    lines.append("| --- | ---: | ---: | ---: |")
    for category, items in sections.items():
        papers = _sort_papers(items)
        cat_today, cat_history, _ = _category_stats(papers, today_dates)
        lines.append(
            f"| {category} | {cat_today} | {cat_history} | {len(papers)} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 📚 分类明细")
    lines.append("")

    for category, items in sections.items():
        papers = _sort_papers(items)
        cat_today, cat_history, cat_history_range = _category_stats(papers, today_dates)
        lines.append(f"### 🔹 {category}")
        lines.append(f"- **当日篇数**: {cat_today}篇（{today_range}）")
        lines.append(f"- **历史篇数**: {cat_history}篇（{cat_history_range}）")
        lines.append(f"- **累计**: {len(papers)}篇")
        lines.append("")
        lines.append("#### 论文列表")
        for idx, paper in enumerate(papers, start=1):
            arxiv_id = paper.get("arxiv_id", "")
            paper_title = paper.get("title", "")
            source_date = _paper_source_date(paper)
            backfill_mark = " ← 回溯" if source_date and source_date not in today_dates else ""
            pdf_url = paper.get("pdf_url", "")
            pdf_link = pdf_url or (f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else "")
            translate_url = _translate_url(arxiv_id)
            abs_url = _abs_url(arxiv_id)
            primary_category = paper.get("primary_category", "")
            categories = paper.get("categories", "")
            published = paper.get("published", "")
            abstract = _truncate(paper.get("abstract", ""), abstract_max_len)

            lines.append(f"{idx}. **[{arxiv_id}] {paper_title}**  ")
            lines.append(f"   *arXiv ID*: {arxiv_id}  ")
            lines.append(f"   *Authors*: {paper.get('authors', '')}  ")
            lines.append(f"   *Primary Category*: {primary_category}  ")
            lines.append(f"   *Categories*: {categories}  ")
            lines.append(f"   *Published*: {published}  ")
            lines.append(f"   *Date*: {source_date}{backfill_mark}  ")
            links = []
            if pdf_link:
                links.append(f"[PDF]({pdf_link})")
            if abs_url:
                links.append(f"[abs]({abs_url})")
            if translate_url:
                links.append(f"[翻译]({translate_url})")
            if links:
                lines.append(f"   {' | '.join(links)}  ")
            lines.append(f"   *Abstract*: {abstract}")
            lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def render_aggregated_html(
    latest_date: str,
    sections: Dict[str, List[Dict[str, str]]],
    abstract_max_len: int = 800,
    today_window_days: int = 2,
) -> str:
    today_dates = window_dates(latest_date, today_window_days)
    total, today_count, history_count, categories, history_range = _global_stats(
        sections, today_dates
    )
    today_range = _history_range(sorted(today_dates))
    parts: List[str] = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "<meta charset='utf-8' />",
        f"<title>ResearchPulse 每日学术简报 | {escape(latest_date)}</title>",
        "</head>",
        "<body style='font-family: Arial, sans-serif; line-height: 1.5;'>",
        f"<h1>📬 ResearchPulse 每日学术简报 | {escape(latest_date)}</h1>",
        "<h2>📊 全局统计</h2>",
        f"<p><strong>覆盖分类:</strong> {escape(', '.join(categories))}（共{len(categories)}类）</p>",
        f"<p><strong>当日新增:</strong> {today_count}篇（{escape(today_range)}）</p>",
        f"<p><strong>历史回溯:</strong> {history_count}篇（{escape(history_range)}）</p>",
        f"<p><strong>总计:</strong> {total}篇</p>",
        "<h3>分类统计</h3>",
        "<table border='1' cellpadding='6' cellspacing='0'>",
        "<thead><tr><th>分类</th><th>当日</th><th>历史</th><th>总计</th></tr></thead>",
        "<tbody>",
    ]

    for category, items in sections.items():
        papers = _sort_papers(items)
        cat_today, cat_history, _ = _category_stats(papers, today_dates)
        parts.append(
            f"<tr><td>{escape(category)}</td><td>{cat_today}</td><td>{cat_history}</td><td>{len(papers)}</td></tr>"
        )
    parts.extend(["</tbody>", "</table>", "<hr />", "<h2>📚 分类明细</h2>"])

    for category, items in sections.items():
        papers = _sort_papers(items)
        cat_today, cat_history, cat_history_range = _category_stats(papers, today_dates)
        parts.append(f"<h3>🔹 {escape(category)}</h3>")
        parts.append(
            f"<p><strong>当日篇数:</strong> {cat_today}篇（{escape(today_range)}）</p>"
        )
        parts.append(f"<p><strong>历史篇数:</strong> {cat_history}篇（{escape(cat_history_range)}）</p>")
        parts.append(f"<p><strong>累计:</strong> {len(papers)}篇</p>")
        parts.append("<ol>")
        for paper in papers:
            arxiv_id = paper.get("arxiv_id", "")
            paper_title = paper.get("title", "")
            source_date = _paper_source_date(paper)
            backfill_mark = " ← 回溯" if source_date and source_date not in today_dates else ""
            pdf_url = paper.get("pdf_url", "")
            pdf_link = pdf_url or (f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else "")
            translate_url = _translate_url(arxiv_id)
            abs_url = _abs_url(arxiv_id)
            primary_category = paper.get("primary_category", "")
            categories = paper.get("categories", "")
            published = paper.get("published", "")
            abstract = _truncate(paper.get("abstract", ""), abstract_max_len)

            parts.append("<li>")
            parts.append(f"<strong>[{escape(arxiv_id)}] {escape(paper_title)}</strong><br />")
            parts.append(f"<em>arXiv ID</em>: {escape(arxiv_id)}<br />")
            parts.append(f"<em>Authors</em>: {escape(paper.get('authors', ''))}<br />")
            parts.append(f"<em>Primary Category</em>: {escape(primary_category)}<br />")
            parts.append(f"<em>Categories</em>: {escape(categories)}<br />")
            parts.append(f"<em>Published</em>: {escape(published)}<br />")
            parts.append(f"<em>Date</em>: {escape(source_date)}{escape(backfill_mark)}<br />")
            link_items = []
            if pdf_link:
                link_items.append(f"<a href='{escape(pdf_link)}'>PDF</a>")
            if abs_url:
                link_items.append(f"<a href='{escape(abs_url)}'>abs</a>")
            if translate_url:
                link_items.append(f"<a href='{escape(translate_url)}'>翻译</a>")
            if link_items:
                parts.append(" | ".join(link_items) + "<br />")
            parts.append(f"<em>Abstract</em>: {escape(abstract)}")
            parts.append("</li>")
        parts.append("</ol>")
        parts.append("<hr />")

    parts.extend(["</body>", "</html>"])
    return "\n".join(parts)


def write_markdown(file_path: Path, content: str) -> None:
    ensure_dir(file_path.parent)
    file_path.write_text(content, encoding="utf-8")
