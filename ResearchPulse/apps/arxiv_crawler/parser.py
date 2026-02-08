from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

import feedparser

from common.http import get_text


@dataclass
class Paper:
    arxiv_id: str
    title: str
    authors: List[str]
    primary_category: str
    categories: List[str]
    abstract: str
    pdf_url: str
    published: str

    def to_dict(self) -> Dict[str, str]:
        source_date = self.published.split("T")[0] if self.published else ""
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "authors": ", ".join(self.authors),
            "primary_category": self.primary_category,
            "categories": ", ".join(self.categories),
            "abstract": self.abstract,
            "pdf_url": self.pdf_url,
            "published": self.published,
            "source_date": source_date,
        }


def _clean_text(text: str) -> str:
    return " ".join(text.replace("\n", " ").split()).strip()


def _parse_datetime(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.isoformat()
    except ValueError:
        return value


def _parse_entry(entry: feedparser.FeedParserDict) -> Paper:
    arxiv_id = entry.get("id", "").split("/abs/")[-1]
    title = _clean_text(entry.get("title", ""))
    abstract = _clean_text(entry.get("summary", ""))
    authors = [author.get("name", "") for author in entry.get("authors", [])]

    primary_category = ""
    if "arxiv_primary_category" in entry:
        primary_category = entry.arxiv_primary_category.get("term", "")

    categories = [tag.get("term", "") for tag in entry.get("tags", [])]

    pdf_url = ""
    for link in entry.get("links", []):
        if link.get("type") == "application/pdf":
            pdf_url = link.get("href", "")
            break

    published = _parse_datetime(entry.get("published", ""))

    return Paper(
        arxiv_id=arxiv_id,
        title=title,
        authors=authors,
        primary_category=primary_category,
        categories=categories,
        abstract=abstract,
        pdf_url=pdf_url,
        published=published,
    )


def _parse_rss_entry(entry: feedparser.FeedParserDict) -> Paper:
    arxiv_id = ""
    entry_id = entry.get("id", "") or entry.get("link", "")
    match = re.search(r"arxiv.org/abs/([\w.]+v\d+)", entry_id)
    if match:
        arxiv_id = match.group(1)
    title = _clean_text(entry.get("title", ""))
    abstract = _clean_text(entry.get("summary", ""))

    authors: List[str] = []
    if entry.get("authors"):
        for author in entry.get("authors", []):
            name = author.get("name", "")
            authors.extend([part.strip() for part in name.split(",") if part.strip()])
    elif entry.get("author"):
        authors = [name.strip() for name in entry.get("author", "").split(",") if name.strip()]

    categories = [tag.get("term", "") for tag in entry.get("tags", [])]
    primary_category = categories[0] if categories else ""

    pdf_url = ""
    for link in entry.get("links", []):
        if link.get("type") == "application/pdf":
            pdf_url = link.get("href", "")
            break

    published = _parse_datetime(entry.get("published", ""))

    return Paper(
        arxiv_id=arxiv_id,
        title=title,
        authors=authors,
        primary_category=primary_category,
        categories=categories,
        abstract=abstract,
        pdf_url=pdf_url,
        published=published,
    )


def _parse_html_list(html: str) -> List[Paper]:
    papers: List[Paper] = []
    for match in re.finditer(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", html, re.S):
        dt = match.group(1)
        dd = match.group(2)
        id_match = re.search(r"/abs/([\w.]+v\d+)", dt)
        arxiv_id = id_match.group(1) if id_match else ""

        title_match = re.search(r"Title:</span>\s*(.*?)</div>", dd, re.S)
        title = _clean_text(title_match.group(1)) if title_match else ""

        authors_match = re.search(r"Authors:</span>\s*(.*?)</div>", dd, re.S)
        authors_block = authors_match.group(1) if authors_match else ""
        authors = [
            _clean_text(a)
            for a in re.findall(r">\s*([^<]+)\s*</a>", authors_block)
        ]

        abstract_match = re.search(r"Abstract:</span>\s*(.*?)</p>", dd, re.S)
        abstract = _clean_text(abstract_match.group(1)) if abstract_match else ""

        category_match = re.search(r"Subjects:</span>\s*(.*?)</div>", dd, re.S)
        categories_block = category_match.group(1) if category_match else ""
        categories = [
            _clean_text(cat)
            for cat in re.split(r";|,", categories_block)
            if _clean_text(cat)
        ]
        primary_category = categories[0] if categories else ""

        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else ""

        papers.append(
            Paper(
                arxiv_id=arxiv_id,
                title=title,
                authors=authors,
                primary_category=primary_category,
                categories=categories,
                abstract=abstract,
                pdf_url=pdf_url,
                published="",
            )
        )

    return papers


def _parse_html_search(html: str) -> List[Paper]:
    papers: List[Paper] = []
    for match in re.finditer(r"<li class=\"arxiv-result\">(.*?)</li>", html, re.S):
        block = match.group(1)
        id_match = re.search(r"/abs/([\w.]+v\d+)", block)
        arxiv_id = id_match.group(1) if id_match else ""

        title_match = re.search(r"title is-5 mathjax\">(.*?)</p>", block, re.S)
        title = _clean_text(title_match.group(1)) if title_match else ""

        authors = [
            _clean_text(a)
            for a in re.findall(r"<a href=\"/search/\?searchtype=author.*?\">(.*?)</a>", block)
        ]

        abstract_match = re.search(r"abstract-full\">(.*?)</span>", block, re.S)
        abstract = _clean_text(abstract_match.group(1)) if abstract_match else ""

        subject_match = re.search(r"<span class=\"tag is-small is-link\">(.*?)</span>", block)
        categories = [_clean_text(subject_match.group(1))] if subject_match else []
        primary_category = categories[0] if categories else ""

        pdf_match = re.search(r"href=\"(/pdf/[\w.]+v\d+)\"", block)
        pdf_url = f"https://arxiv.org{pdf_match.group(1)}" if pdf_match else ""

        papers.append(
            Paper(
                arxiv_id=arxiv_id,
                title=title,
                authors=authors,
                primary_category=primary_category,
                categories=categories,
                abstract=abstract,
                pdf_url=pdf_url,
                published="",
            )
        )

    return papers


def fetch_papers_atom(category: str, max_results: int, base_url: str) -> List[Paper]:
    params = {
        "search_query": f"cat:{category}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    feed_text = get_text(base_url, params=params)
    feed = feedparser.parse(feed_text)
    return [_parse_entry(entry) for entry in feed.entries]


def fetch_papers_rss(category: str, rss_url: str) -> List[Paper]:
    feed_text = get_text(rss_url.format(category=category))
    feed = feedparser.parse(feed_text)
    return [_parse_rss_entry(entry) for entry in feed.entries]


def fetch_papers_html_list(category: str, list_url: str) -> List[Paper]:
    html = get_text(list_url.format(category=category))
    return _parse_html_list(html)


def fetch_papers_html_search(category: str, search_url: str, size: int) -> List[Paper]:
    html = get_text(search_url.format(category=category, size=size))
    return _parse_html_search(html)


def merge_unique_by_id(papers: Iterable[Paper]) -> List[Paper]:
    seen = set()
    result: List[Paper] = []
    for paper in papers:
        if not paper.arxiv_id:
            continue
        if paper.arxiv_id in seen:
            continue
        seen.add(paper.arxiv_id)
        result.append(paper)
    return result


def select_by_date_window(
    papers: Iterable[Paper],
    run_date: str,
    fallback_days: int,
) -> List[Paper]:
    if fallback_days <= 0:
        fallback_days = 1
    base_date = datetime.fromisoformat(run_date).date()
    window = {
        (base_date - timedelta(days=offset)).isoformat() for offset in range(fallback_days)
    }
    selected = [paper for paper in papers if paper.published.startswith(tuple(window))]
    return selected


def _paper_date(paper: Paper) -> str:
    return paper.published.split("T")[0] if paper.published else ""


def group_by_published_date(papers: Iterable[Paper]) -> Dict[str, List[Paper]]:
    grouped: Dict[str, List[Paper]] = {}
    for paper in papers:
        date_key = _paper_date(paper)
        if not date_key:
            continue
        grouped.setdefault(date_key, []).append(paper)
    return grouped


def select_backfill_by_date(
    papers: Iterable[Paper],
    run_date: str,
    min_results: int,
    fallback_days: int,
) -> Dict[str, List[Paper]]:
    if fallback_days < 0:
        fallback_days = 0
    if min_results <= 0:
        min_results = 0
    grouped = group_by_published_date(papers)
    base_date = datetime.fromisoformat(run_date).date()
    dates = [
        (base_date - timedelta(days=offset)).isoformat()
        for offset in range(fallback_days + 1)
    ]

    selected: Dict[str, List[Paper]] = {}
    total = 0
    for date_key in dates:
        day_papers = grouped.get(date_key, [])
        if not day_papers:
            continue
        day_sorted = sorted(day_papers, key=lambda p: p.arxiv_id, reverse=True)
        selected[date_key] = day_sorted
        total += len(day_sorted)
        if date_key == run_date and len(day_sorted) >= min_results:
            return {date_key: day_sorted}
        if total >= min_results:
            break
    return selected


def fetch_papers_multi(
    category: str,
    max_results: int,
    min_results: int,
    fallback_days: int,
    base_url: str,
    rss_url: str,
    list_url: str,
    search_url: str,
    run_date: str,
) -> List[Paper]:
    combined: List[Paper] = []

    atom = fetch_papers_atom(category, max_results, base_url)
    combined.extend(atom)
    combined = merge_unique_by_id(combined)

    if len(combined) < min_results:
        rss = fetch_papers_rss(category, rss_url)
        combined = merge_unique_by_id([*combined, *rss])

    if len(combined) < min_results:
        html_list = fetch_papers_html_list(category, list_url)
        combined = merge_unique_by_id([*combined, *html_list])

    if len(combined) < min_results:
        html_search = fetch_papers_html_search(category, search_url, size=max_results)
        combined = merge_unique_by_id([*combined, *html_search])

    combined.sort(key=lambda paper: paper.published, reverse=True)
    return combined


def serialize_papers(papers: Iterable[Paper]) -> List[Dict[str, str]]:
    return [paper.to_dict() for paper in papers]
