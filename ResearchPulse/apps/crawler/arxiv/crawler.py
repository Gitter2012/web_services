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
from common.http import get_text

logger = logging.getLogger(__name__)


@dataclass
class Paper:
    """ArXiv paper data."""

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

    def to_article_dict(self) -> Dict[str, Any]:
        """Convert to article dictionary for database storage."""
        # Determine source date
        if self.announced_date:
            source_date = self.announced_date
        else:
            effective_ts = self.updated or self.published
            source_date = effective_ts.split("T")[0] if effective_ts else ""

        # Parse publish time
        publish_time = None
        if self.published:
            try:
                publish_time = datetime.fromisoformat(
                    self.published.replace("Z", "+00:00")
                )
            except ValueError:
                pass

        # Parse updated time
        updated_time = None
        if self.updated:
            try:
                updated_time = datetime.fromisoformat(
                    self.updated.replace("Z", "+00:00")
                )
            except ValueError:
                pass

        # PDF URL for direct download
        pdf_url = self.pdf_url if self.pdf_url else f"https://arxiv.org/pdf/{self.arxiv_id}"
        # Abstract page URL
        abs_url = f"https://arxiv.org/abs/{self.arxiv_id}"

        return {
            "external_id": self.arxiv_id,
            "title": self.title,
            "url": abs_url,  # Main URL goes to abstract page
            "author": ", ".join(self.authors) if self.authors else "",
            "summary": self.abstract,
            "content": self.abstract,
            "category": self.primary_category,
            "tags": self.categories,
            "publish_time": publish_time,
            "arxiv_id": self.arxiv_id,
            "arxiv_primary_category": self.primary_category,
            "arxiv_updated_time": updated_time,
            "cover_image_url": pdf_url,  # Store PDF URL for download link
        }


def _clean_text(text: str) -> str:
    """Clean HTML and whitespace from text."""
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = html.unescape(cleaned)
    return " ".join(cleaned.replace("\n", " ").split()).strip()


def _normalize_arxiv_id(arxiv_id: str) -> str:
    """Remove version suffix from arxiv ID."""
    if not arxiv_id:
        return ""
    return re.sub(r"v\d+$", "", arxiv_id)


def _parse_datetime(value: str) -> str:
    """Parse various datetime formats to ISO 8601."""
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.isoformat()
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        parsed = parsedate_to_datetime(value)
        return parsed.isoformat()
    except (ValueError, TypeError):
        pass
    return value


def _parse_rss_entry(entry: feedparser.FeedParserDict) -> Paper:
    """Parse a single RSS/Atom entry into a Paper."""
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
    """Extract date from HTML list header."""
    match = re.search(r"SHOWING (?:NEW|RECENT) LISTINGS FOR\s+([^<]+)", html_text, re.I)
    if not match:
        return ""

    text = match.group(1)
    # Parse human-readable date
    text = re.sub(r"^[A-Za-z]+,\s*", "", text.strip())
    text = text.replace(",", " ")
    text = re.sub(r"\bSept\.?\b", "Sep", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip().title()

    for fmt in ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _parse_html_list(html_text: str, run_date: str | None = None) -> List[Paper]:
    """Parse HTML listing page into papers."""
    papers: List[Paper] = []
    header_date = _extract_list_header_date(html_text)
    if not header_date and run_date:
        header_date = run_date

    published = f"{header_date}T00:00:00Z" if header_date else ""

    for match in re.finditer(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", html_text, re.S):
        dt = match.group(1)
        dd = match.group(2)

        id_match = re.search(r"/abs/([\w.]+(?:v\d+)?)", dt)
        arxiv_id = id_match.group(1) if id_match else ""

        title_match = re.search(r"Title:</span>\s*(.*?)</div>", dd, re.S)
        title = _clean_text(title_match.group(1)) if title_match else ""

        authors_match = re.search(r"Authors:</span>\s*(.*?)</div>", dd, re.S)
        authors_block = authors_match.group(1) if authors_match else ""
        authors = [_clean_text(a) for a in re.findall(r">\s*([^<]+)\s*</a>", authors_block)]

        abstract_match = re.search(r"Abstract:</span>\s*(.*?)</p>", dd, re.S)
        abstract = _clean_text(abstract_match.group(1)) if abstract_match else ""

        category_match = re.search(r"Subjects:</span>\s*(.*?)</div>", dd, re.S)
        categories_block = category_match.group(1) if category_match else ""
        categories = [_clean_text(cat) for cat in re.split(r";|,", categories_block) if _clean_text(cat)]
        primary_category = categories[0] if categories else ""

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


class ArxivCrawler(BaseCrawler):
    """Crawler for arXiv papers."""

    source_type = "arxiv"

    def __init__(
        self,
        category: str,
        max_results: int = 50,
        delay_base: float = 3.0,
        delay_jitter: float = 1.5,
    ):
        super().__init__(category)
        self.category = category
        self.max_results = max_results
        self.delay_base = delay_base
        self.delay_jitter = delay_jitter

        # URLs
        self.atom_url = "https://export.arxiv.org/api/query"
        self.rss_url = "https://export.arxiv.org/rss/{category}"
        self.list_new_url = "https://arxiv.org/list/{category}/new"
        self.list_recent_url = "https://arxiv.org/list/{category}/recent"

    async def fetch(self) -> Dict[str, Any]:
        """Fetch papers from multiple arXiv sources."""
        all_papers: List[Paper] = []
        run_date = datetime.now(timezone.utc).date().isoformat()

        # Source 1: Atom API
        atom_papers = await self._fetch_atom()
        all_papers.extend(atom_papers)
        self.logger.info(f"Atom API: {len(atom_papers)} papers")

        # Source 2: RSS (if Atom gave too few results)
        if len(all_papers) < self.max_results:
            await self.delay(self.delay_base, self.delay_jitter)
            rss_papers = await self._fetch_rss()
            all_papers.extend(rss_papers)
            self.logger.info(f"RSS: {len(rss_papers)} papers")

        # Source 3: HTML list (new)
        await self.delay(self.delay_base, self.delay_jitter)
        html_papers = await self._fetch_html_list(self.list_new_url, run_date)
        all_papers.extend(html_papers)
        self.logger.info(f"HTML list: {len(html_papers)} papers")

        # Merge and deduplicate
        merged = self._merge_papers(all_papers)
        self.logger.info(f"Total unique papers: {len(merged)}")

        return {"papers": merged, "run_date": run_date}

    async def _fetch_atom(self) -> List[Paper]:
        """Fetch papers from Atom API."""
        params = {
            "search_query": f"cat:{self.category}",
            "start": 0,
            "max_results": self.max_results,
            "sortBy": "lastUpdatedDate",
            "sortOrder": "descending",
        }

        try:
            feed_text = get_text(
                self.atom_url,
                params=params,
                timeout=20.0,
                retries=3,
                backoff=1.0,
                delay=self.delay_base,
                jitter=self.delay_jitter,
            )
            feed = feedparser.parse(feed_text)
            return [_parse_rss_entry(entry) for entry in feed.entries]
        except Exception as e:
            self.logger.warning(f"Atom API fetch failed: {e}")
            return []

    async def _fetch_rss(self) -> List[Paper]:
        """Fetch papers from RSS feed."""
        url = self.rss_url.format(category=self.category)

        try:
            feed_text = get_text(
                url,
                timeout=20.0,
                retries=3,
                backoff=1.0,
                delay=self.delay_base,
                jitter=self.delay_jitter,
            )
            feed = feedparser.parse(feed_text)
            return [_parse_rss_entry(entry) for entry in feed.entries]
        except Exception as e:
            self.logger.warning(f"RSS fetch failed: {e}")
            return []

    async def _fetch_html_list(self, url_template: str, run_date: str) -> List[Paper]:
        """Fetch papers from HTML listing page."""
        url = url_template.format(category=self.category)

        try:
            html_text = get_text(
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
        """Merge papers by arxiv_id, keeping the best data."""
        merged: Dict[str, Paper] = {}

        for paper in papers:
            key = _normalize_arxiv_id(paper.arxiv_id)
            if not key:
                continue

            existing = merged.get(key)
            if not existing:
                merged[key] = paper
                continue

            # Merge data: prefer non-empty values
            if paper.title and not existing.title:
                existing.title = paper.title
            if paper.authors and not existing.authors:
                existing.authors = paper.authors
            if paper.abstract and not existing.abstract:
                existing.abstract = paper.abstract
            if paper.primary_category and not existing.primary_category:
                existing.primary_category = paper.primary_category
            if paper.categories and not existing.categories:
                existing.categories = paper.categories
            if paper.pdf_url and not existing.pdf_url:
                existing.pdf_url = paper.pdf_url

        # Sort by published date
        return sorted(merged.values(), key=lambda p: p.published, reverse=True)

    async def parse(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse fetched papers into article dictionaries."""
        papers = raw_data.get("papers", [])
        return [paper.to_article_dict() for paper in papers]
