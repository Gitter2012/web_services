from __future__ import annotations

import html
import logging
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

import feedparser

from common.http import get_text

logger = logging.getLogger(__name__)


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
    updated: str = ""
    announced_date: str = ""

    def to_dict(self) -> Dict[str, str]:
        # source_date drives date-window filtering and backfill detection.
        # Use announced_date (the arXiv listing date) when available,
        # otherwise fall back to the date part of updated/published.
        # This prevents precise Atom timestamps (e.g. 2026-02-11T18:59:08Z)
        # from being grouped under a different day than the listing page
        # (which announces them on 2026-02-12).
        if self.announced_date:
            source_date = self.announced_date
        else:
            effective_ts = self.updated or self.published
            source_date = effective_ts.split("T")[0] if effective_ts else ""
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "authors": ", ".join(self.authors),
            "primary_category": self.primary_category,
            "categories": ", ".join(self.categories),
            "abstract": self.abstract,
            "pdf_url": self.pdf_url,
            "published": self.published,
            "updated": self.updated,
            "source_date": source_date,
        }


def _clean_text(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = html.unescape(cleaned)
    return " ".join(cleaned.replace("\n", " ").split()).strip()


def _is_meaningful_abstract(text: str, min_length: int = 20) -> bool:
    cleaned = _clean_text(text)
    return len(cleaned) >= min_length


def _parse_datetime(value: str) -> str:
    """Parse various datetime formats to ISO 8601.

    Handles:
    - ISO 8601: "2026-02-11T18:59:08Z"
    - RFC 2822: "Thu, 12 Feb 2026 00:00:00 -0500" (from RSS feeds)
    """
    if not value:
        return ""
    # Try ISO 8601 first
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.isoformat()
    except ValueError:
        pass
    # Try RFC 2822 (RSS pubDate format)
    try:
        from email.utils import parsedate_to_datetime
        parsed = parsedate_to_datetime(value)
        return parsed.isoformat()
    except (ValueError, TypeError):
        pass
    return value


def _normalize_date_text(value: str) -> str:
    cleaned = re.sub(r"^[A-Za-z]+,\s*", "", value.strip())
    cleaned = cleaned.replace(",", " ")
    cleaned = re.sub(r"\bSept\.?\b", "Sep", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title()


def _parse_human_date(value: str) -> str:
    if not value:
        return ""
    cleaned = _normalize_date_text(value)
    for fmt in ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _extract_human_date(text: str) -> str:
    if not text:
        return ""
    normalized = " ".join(text.split())
    patterns = (
        r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
        r"([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            date_iso = _parse_human_date(match.group(1))
            if date_iso:
                return date_iso
    return ""


def _format_published_date(date_iso: str) -> str:
    if not date_iso:
        return ""
    return f"{date_iso}T00:00:00Z"


def _normalize_arxiv_id(arxiv_id: str) -> str:
    if not arxiv_id:
        return ""
    return re.sub(r"v\d+$", "", arxiv_id)


def _has_version(arxiv_id: str) -> bool:
    return bool(re.search(r"v\d+$", arxiv_id))


def _parse_abs_page(html_text: str) -> Dict[str, str | List[str]]:
    title_match = re.search(
        r"<h1[^>]*class=\"[^\"]*title[^\"]*\"[^>]*>(.*?)</h1>",
        html_text,
        re.S,
    )
    title_raw = title_match.group(1) if title_match else ""
    title = _clean_text(re.sub(r"^Title:\s*", "", title_raw, flags=re.I))

    authors_match = re.search(
        r"<div[^>]*class=\"[^\"]*authors[^\"]*\"[^>]*>(.*?)</div>",
        html_text,
        re.S,
    )
    authors_block = authors_match.group(1) if authors_match else ""
    authors = [
        _clean_text(a)
        for a in re.findall(r">\s*([^<]+)\s*</a>", authors_block)
        if _clean_text(a)
    ]

    abstract_match = re.search(
        r"<blockquote[^>]*class=\"[^\"]*abstract[^\"]*\"[^>]*>(.*?)</blockquote>",
        html_text,
        re.S,
    )
    abstract_raw = abstract_match.group(1) if abstract_match else ""
    abstract = _clean_text(re.sub(r"^Abstract:\s*", "", abstract_raw, flags=re.I))

    subjects_match = re.search(
        r"<td[^>]*class=\"tablecell subjects\"[^>]*>(.*?)</td>",
        html_text,
        re.S,
    )
    subjects_block = subjects_match.group(1) if subjects_match else ""
    subjects = [
        _clean_text(part)
        for part in re.split(r";|,", subjects_block)
        if _clean_text(part)
    ]

    return {
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "subjects": subjects,
    }


def _fill_missing_from_abs(paper: Paper, abs_data: Dict[str, str | List[str]]) -> None:
    if not paper.title and abs_data.get("title"):
        paper.title = str(abs_data["title"])
    if not paper.authors and abs_data.get("authors"):
        paper.authors = list(abs_data["authors"])  # type: ignore[list-item]
    abs_abstract = abs_data.get("abstract")
    if abs_abstract and not _is_meaningful_abstract(paper.abstract):
        paper.abstract = _clean_text(str(abs_abstract))
    if not paper.categories and abs_data.get("subjects"):
        paper.categories = list(abs_data["subjects"])  # type: ignore[list-item]
        paper.primary_category = paper.categories[0] if paper.categories else paper.primary_category



def _extract_list_header_date(html: str) -> str:
    match = re.search(r"SHOWING (?:NEW|RECENT) LISTINGS FOR\s+([^<]+)", html, re.I)
    if not match:
        return ""
    return _extract_human_date(match.group(1))


def _parse_entry(entry: feedparser.FeedParserDict) -> Paper:
    arxiv_id = entry.get("id", "").split("/abs/")[-1]
    title = _clean_text(entry.get("title", ""))
    abstract = _clean_text(entry.get("summary", ""))
    authors = [_clean_text(author.get("name", "")) for author in entry.get("authors", [])]

    primary_category = ""
    if "arxiv_primary_category" in entry:
        primary_category = entry.arxiv_primary_category.get("term", "")

    categories = [_clean_text(tag.get("term", "")) for tag in entry.get("tags", [])]

    pdf_url = ""
    for link in entry.get("links", []):
        if link.get("type") == "application/pdf":
            pdf_url = link.get("href", "")
            break

    published = _parse_datetime(entry.get("published", ""))
    updated = _parse_datetime(entry.get("updated", ""))

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
    )


def _parse_rss_entry(entry: feedparser.FeedParserDict) -> Paper:
    arxiv_id = ""
    entry_id = entry.get("id", "") or entry.get("link", "")
    match = re.search(r"arxiv.org/abs/([\w.]+(?:v\d+)?)", entry_id)
    if match:
        arxiv_id = match.group(1)
    title = _clean_text(entry.get("title", ""))
    abstract = _clean_text(entry.get("summary", ""))

    authors: List[str] = []
    if entry.get("authors"):
        for author in entry.get("authors", []):
            name = author.get("name", "")
            authors.extend([_clean_text(part) for part in name.split(",") if _clean_text(part)])
    elif entry.get("author"):
        authors = [_clean_text(name) for name in entry.get("author", "").split(",") if _clean_text(name)]

    categories = [_clean_text(tag.get("term", "")) for tag in entry.get("tags", [])]
    primary_category = categories[0] if categories else ""

    pdf_url = ""
    for link in entry.get("links", []):
        if link.get("type") == "application/pdf":
            pdf_url = link.get("href", "")
            break

    published = _parse_datetime(entry.get("published", ""))
    updated = _parse_datetime(entry.get("updated", ""))
    # RSS published date represents the announcement date
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


def _parse_html_list(html: str, run_date: str | None = None) -> List[Paper]:
    papers: List[Paper] = []
    header_date = _extract_list_header_date(html)
    if not header_date and run_date:
        header_date = run_date
    published = _format_published_date(header_date)
    for match in re.finditer(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", html, re.S):
        dt = match.group(1)
        dd = match.group(2)
        id_match = re.search(r"/abs/([\w.]+(?:v\d+)?)", dt)
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
                published=published,
                announced_date=header_date or "",
            )
        )

    return papers


def _parse_html_search(html: str, run_date: str | None = None) -> List[Paper]:
    papers: List[Paper] = []
    for match in re.finditer(r"<li class=\"arxiv-result\">(.*?)</li>", html, re.S):
        block = match.group(1)
        id_match = re.search(r"/abs/([\w.]+(?:v\d+)?)", block)
        arxiv_id = id_match.group(1) if id_match else ""

        title_match = re.search(r"title is-5 mathjax\">(.*?)</p>", block, re.S)
        title = _clean_text(title_match.group(1)) if title_match else ""

        authors = [
            _clean_text(a)
            for a in re.findall(r"<a href=\"/search/\?searchtype=author.*?\">(.*?)</a>", block)
        ]

        abstract_match = re.search(
            r"abstract-(?:full|short)\"[^>]*>(.*?)</span>",
            block,
            re.S,
        )
        abstract = _clean_text(abstract_match.group(1)) if abstract_match else ""

        subject_match = re.search(r"<span class=\"tag is-small is-link\">(.*?)</span>", block)
        categories = [_clean_text(subject_match.group(1))] if subject_match else []
        primary_category = categories[0] if categories else ""

        pdf_match = re.search(r"href=\"(/pdf/[\w.]+(?:v\d+)?)\"", block)
        pdf_url = f"https://arxiv.org{pdf_match.group(1)}" if pdf_match else ""

        date_iso = ""
        submitted_match = re.search(r"Submitted\s+([^;<]+)", block, re.I)
        if submitted_match:
            date_iso = _extract_human_date(submitted_match.group(1))
        if not date_iso:
            announced_match = re.search(r"announced\s+([^;<]+)", block, re.I)
            if announced_match:
                date_iso = _extract_human_date(announced_match.group(1))
        if not date_iso and run_date:
            date_iso = run_date
        published = _format_published_date(date_iso)

        papers.append(
            Paper(
                arxiv_id=arxiv_id,
                title=title,
                authors=authors,
                primary_category=primary_category,
                categories=categories,
                abstract=abstract,
                pdf_url=pdf_url,
                published=published,
                announced_date=date_iso or "",
            )
        )

    return papers


def fetch_papers_atom(
    category: str, max_results: int, base_url: str, delay: float = 0.0, jitter: float = 0.0, cache_ttl: int = 0
) -> List[Paper]:
    params = {
        "search_query": f"cat:{category}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "lastUpdatedDate",
        "sortOrder": "descending",
    }
    timeout = 20.0
    retries = 3
    backoff = 1.0
    try:
        feed_text = get_text(
            base_url,
            params=params,
            timeout=timeout,
            retries=retries,
            backoff=backoff,
            delay=delay,
            jitter=jitter,
            cache_ttl=cache_ttl,
        )
    except RuntimeError as exc:
        logger.warning(
            "arXiv Atom fetch failed",
            extra={
                "category": category,
                "url": base_url,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "retries": retries,
                "timeout": timeout,
                "backoff": backoff,
            },
        )
        return []
    feed = feedparser.parse(feed_text)
    return [_parse_entry(entry) for entry in feed.entries]


def fetch_papers_rss(
    category: str, rss_url: str, delay: float = 0.0, jitter: float = 0.0, cache_ttl: int = 0
) -> List[Paper]:
    url = rss_url.format(category=category)
    timeout = 20.0
    retries = 3
    backoff = 1.0
    try:
        feed_text = get_text(
            url, timeout=timeout, retries=retries, backoff=backoff,
            delay=delay, jitter=jitter, cache_ttl=cache_ttl,
        )
    except RuntimeError as exc:
        logger.warning(
            "arXiv RSS fetch failed",
            extra={
                "category": category,
                "url": url,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "retries": retries,
                "timeout": timeout,
                "backoff": backoff,
            },
        )
        return []
    feed = feedparser.parse(feed_text)
    return [_parse_rss_entry(entry) for entry in feed.entries]


def fetch_papers_html_list(
    category: str,
    list_url: str,
    run_date: str | None = None,
    delay: float = 0.0,
    jitter: float = 0.0,
    cache_ttl: int = 0,
) -> List[Paper]:
    url = list_url.format(category=category)
    timeout = 15.0
    retries = 3
    backoff = 1.0
    try:
        html = get_text(url, timeout=timeout, retries=retries, backoff=backoff, delay=delay, jitter=jitter, cache_ttl=cache_ttl)
    except RuntimeError as exc:
        logger.warning(
            "arXiv HTML list fetch failed",
            extra={
                "category": category,
                "url": url,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "retries": retries,
                "timeout": timeout,
                "backoff": backoff,
            },
        )
        return []
    return _parse_html_list(html, run_date=run_date)


def fetch_papers_html_search(
    category: str,
    search_url: str,
    size: int,
    run_date: str | None = None,
    delay: float = 0.0,
    jitter: float = 0.0,
    cache_ttl: int = 0,
) -> List[Paper]:
    url = search_url.format(category=category, size=size)
    timeout = 20.0
    retries = 3
    backoff = 1.0
    try:
        html = get_text(url, timeout=timeout, retries=retries, backoff=backoff, delay=delay, jitter=jitter, cache_ttl=cache_ttl)
    except RuntimeError as exc:
        logger.warning(
            "arXiv HTML search fetch failed",
            extra={
                "category": category,
                "url": url,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "retries": retries,
                "timeout": timeout,
                "backoff": backoff,
            },
        )
        return []
    return _parse_html_search(html, run_date=run_date)


def _is_precise_timestamp(ts: str) -> bool:
    """Return True if the timestamp has real time info (not just midnight).

    Imprecise timestamps are date-only values (from HTML/RSS sources) formatted
    as ``YYYY-MM-DDT00:00:00`` with any timezone suffix (Z, +00:00, -05:00, etc.).
    """
    if not ts or "T" not in ts:
        return False
    # Check for T00:00:00 followed by optional timezone (Z, +HH:MM, -HH:MM)
    return not re.search(r"T00:00:00([Z+\-]|$)", ts)


def merge_unique_by_id(papers: Iterable[Paper]) -> List[Paper]:
    merged: Dict[str, Paper] = {}
    for paper in papers:
        key = _normalize_arxiv_id(paper.arxiv_id)
        if not key:
            continue
        existing = merged.get(key)
        if not existing:
            merged[key] = paper
            continue
        # Prefer precise published timestamps (from Atom API) over
        # date-only timestamps (from HTML/RSS sources like 2026-02-12T00:00:00Z).
        if _is_precise_timestamp(paper.published) and not _is_precise_timestamp(existing.published):
            existing.published = paper.published
        elif not _is_precise_timestamp(paper.published) and _is_precise_timestamp(existing.published):
            pass  # keep existing precise timestamp
        elif _paper_date(paper) > _paper_date(existing):
            existing.published = paper.published
        # Merge updated: prefer non-empty and precise
        if paper.updated and not existing.updated:
            existing.updated = paper.updated
        elif paper.updated and existing.updated:
            if _is_precise_timestamp(paper.updated) and not _is_precise_timestamp(existing.updated):
                existing.updated = paper.updated
            elif not _is_precise_timestamp(paper.updated) and _is_precise_timestamp(existing.updated):
                pass  # keep existing precise timestamp
            elif paper.updated > existing.updated:
                existing.updated = paper.updated
        if existing.arxiv_id and not _has_version(existing.arxiv_id) and _has_version(paper.arxiv_id):
            existing.arxiv_id = paper.arxiv_id
        if not existing.title and paper.title:
            existing.title = paper.title
        if not existing.authors and paper.authors:
            existing.authors = paper.authors
        if not existing.primary_category and paper.primary_category:
            existing.primary_category = paper.primary_category
        if not existing.categories and paper.categories:
            existing.categories = paper.categories
        if not existing.abstract and paper.abstract:
            existing.abstract = paper.abstract
        if not existing.pdf_url and paper.pdf_url:
            existing.pdf_url = paper.pdf_url
        # Merge announced_date: prefer non-empty, then latest
        if paper.announced_date and not existing.announced_date:
            existing.announced_date = paper.announced_date
        elif paper.announced_date and existing.announced_date:
            if paper.announced_date > existing.announced_date:
                existing.announced_date = paper.announced_date
    return list(merged.values())


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
    """Return the effective date for grouping/filtering.

    Prefer ``announced_date`` (the arXiv listing date) when available,
    otherwise fall back to the date part of updated/published.
    This prevents papers with precise Atom timestamps (e.g. 2026-02-11T18:59Z)
    from being grouped under a different day than the HTML listing page
    (which announces them on 2026-02-12).
    """
    if paper.announced_date:
        return paper.announced_date
    ts = paper.updated or paper.published
    return ts.split("T")[0] if ts else ""


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


# ---------------------------------------------------------------------------
# Inter-source delay helper
# ---------------------------------------------------------------------------

def _inter_source_delay(base: float = 2.0, jitter: float = 1.0) -> None:
    """Sleep between different arxiv source fetches to spread load."""
    wait = base + random.uniform(0, jitter)
    time.sleep(max(0.5, wait))


def fetch_papers_multi(
    category: str,
    max_results: int,
    min_results: int,
    fallback_days: int,
    base_url: str,
    rss_url: str,
    list_new_url: str,
    list_recent_url: str,
    search_url: str,
    run_date: str,
    http_delay: float = 0.0,
    http_jitter: float = 0.0,
    http_cache_ttl: int = 0,
) -> List[Paper]:
    combined: List[Paper] = []

    # Source 1: Atom API
    atom = fetch_papers_atom(category, max_results, base_url, delay=http_delay, jitter=http_jitter, cache_ttl=http_cache_ttl)
    combined.extend(atom)
    combined = merge_unique_by_id(combined)

    # Source 2: RSS (only if Atom gave too few results)
    if len(combined) < min_results:
        _inter_source_delay(http_delay, http_jitter)
        rss = fetch_papers_rss(category, rss_url, delay=http_delay, jitter=http_jitter, cache_ttl=http_cache_ttl)
        combined = merge_unique_by_id([*combined, *rss])

    # Source 3: HTML list (new)
    if list_new_url:
        _inter_source_delay(http_delay, http_jitter)
        html_list_new = fetch_papers_html_list(category, list_new_url, run_date=run_date, delay=http_delay, jitter=http_jitter, cache_ttl=http_cache_ttl)
        combined = merge_unique_by_id([*combined, *html_list_new])

    # Source 4: HTML list (recent)
    if list_recent_url and list_recent_url != list_new_url:
        _inter_source_delay(http_delay, http_jitter)
        html_list_recent = fetch_papers_html_list(category, list_recent_url, run_date=run_date, delay=http_delay, jitter=http_jitter, cache_ttl=http_cache_ttl)
        combined = merge_unique_by_id([*combined, *html_list_recent])

    # Source 5: Search page
    if search_url:
        _inter_source_delay(http_delay, http_jitter)
        html_search = fetch_papers_html_search(
            category,
            search_url,
            size=max_results,
            run_date=run_date,
            delay=http_delay,
            jitter=http_jitter,
            cache_ttl=http_cache_ttl,
        )
        combined = merge_unique_by_id([*combined, *html_search])

    # Backfill missing abstracts from individual abs pages
    abs_cache: Dict[str, Dict[str, str | List[str]]] = {}
    abs_fetch_count = 0
    abs_fail_count = 0
    _MAX_ABS_FETCHES = 20       # Don't fetch more than 20 abs pages per category
    _MAX_ABS_CONSECUTIVE_FAILS = 3  # Stop after 3 consecutive failures (rate-limited)
    for paper in combined:
        if abs_fetch_count >= _MAX_ABS_FETCHES:
            logger.info(
                "Reached abs fetch limit (%d), skipping remaining",
                _MAX_ABS_FETCHES,
            )
            break
        if abs_fail_count >= _MAX_ABS_CONSECUTIVE_FAILS:
            logger.info(
                "Too many consecutive abs fetch failures (%d), skipping remaining",
                abs_fail_count,
            )
            break
        if paper.authors and _is_meaningful_abstract(paper.abstract):
            continue
        abs_id = _normalize_arxiv_id(paper.arxiv_id)
        if not abs_id:
            continue
        cached = abs_cache.get(abs_id)
        if cached is None:
            # Progressively increase delay as we fetch more abs pages
            abs_fetch_count += 1
            extra_delay = min(abs_fetch_count * 0.3, 3.0)  # cap at 3s extra
            abs_url = f"https://arxiv.org/abs/{abs_id}"
            timeout = 15.0
            retries = 1
            backoff = 2.0
            try:
                abs_html = get_text(
                    abs_url,
                    timeout=timeout,
                    retries=retries,
                    backoff=backoff,
                    delay=http_delay + extra_delay,
                    jitter=http_jitter,
                    cache_ttl=http_cache_ttl,
                    referer=f"https://arxiv.org/list/{category}/new",
                )
                abs_fail_count = 0  # Reset on success
            except RuntimeError as exc:
                abs_fail_count += 1
                logger.warning(
                    "arXiv abs fetch failed (%d/%d consecutive)",
                    abs_fail_count,
                    _MAX_ABS_CONSECUTIVE_FAILS,
                    extra={
                        "category": category,
                        "url": abs_url,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                        "retries": retries,
                        "timeout": timeout,
                        "backoff": backoff,
                    },
                )
                abs_cache[abs_id] = {}
                continue
            abs_cache[abs_id] = _parse_abs_page(abs_html)
            cached = abs_cache[abs_id]
        if cached:
            _fill_missing_from_abs(paper, cached)

    combined.sort(key=lambda paper: paper.published, reverse=True)
    return combined


def serialize_papers(papers: Iterable[Paper]) -> List[Dict[str, str]]:
    return [paper.to_dict() for paper in papers]
