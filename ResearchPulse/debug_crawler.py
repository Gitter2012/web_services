#!/usr/bin/env python
"""Debug script to check ArXiv crawler data flow."""

import asyncio
from apps.crawler.arxiv.crawler import ArxivCrawler, _parse_rss_entry
import feedparser


async def test():
    """Test the ArXiv crawler data parsing."""
    crawler = ArxivCrawler("cs.AI", max_results=2)

    # Test _fetch_atom
    print("Testing _fetch_atom...")
    try:
        from common.http import get_text_async

        params = {
            "search_query": f"cat:{crawler.category}",
            "start": 0,
            "max_results": 2,
            "sortBy": "lastUpdatedDate",
            "sortOrder": "descending",
        }
        feed_text = await get_text_async(
            crawler.atom_url,
            params=params,
            timeout=20.0,
            retries=1,
        )
        print(f"Got feed_text length: {len(feed_text)}")

        feed = feedparser.parse(feed_text)
        print(f"Entries: {len(feed.entries)}")

        if feed.entries:
            entry = feed.entries[0]
            paper = _parse_rss_entry(entry)
            print(f"Paper ID: {paper.arxiv_id}")
            print(f"Title: {paper.title[:80]}...")
            print(f"Authors count: {len(paper.authors)}")
            if paper.authors:
                print(f"First 3 authors: {paper.authors[:3]}")
            print(f"Abstract length: {len(paper.abstract)}")

            # Check to_article_dict
            article_dict = paper.to_article_dict()
            author_val = article_dict.get("author", "N/A")
            print(f"Author in dict (first 100 chars): {author_val[:100] if len(author_val) > 100 else author_val}")
            print(f"Summary length in dict: {len(article_dict.get('summary', ''))}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test())
