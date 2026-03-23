#!/usr/bin/env python3
# =============================================================================
# 脚本: scripts/seed_news_sources.py
# 功能: 播种新闻数据源（英文 RSS + 中文 RSS + 中文官方媒体 HTML 源）
# 用法: python scripts/seed_news_sources.py
# 特性: 幂等操作 — 基于 unique key 做 INSERT IGNORE / upsert
# =============================================================================

"""Seed news sources: EN/CN RSS feeds + CN official media HTML sources."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select, text
from sqlalchemy.dialects.mysql import insert as mysql_insert

from core.database import get_session_factory
from apps.crawler.models.source import RssFeed, NewsSource

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# =============================================================================
# 英文新闻 RSS 种子数据 → rss_feeds 表
# =============================================================================
EN_NEWS_RSS_FEEDS = [
    {
        "title": "TechCrunch",
        "feed_url": "https://techcrunch.com/feed/",
        "site_url": "https://techcrunch.com",
        "category": "en_tech_news",
        "description": "TechCrunch - Startup and Technology News",
    },
    {
        "title": "The Verge",
        "feed_url": "https://www.theverge.com/rss/index.xml",
        "site_url": "https://www.theverge.com",
        "category": "en_tech_news",
        "description": "The Verge - Technology, Science, Art, and Culture",
    },
    {
        "title": "Ars Technica",
        "feed_url": "https://feeds.arstechnica.com/arstechnica/index",
        "site_url": "https://arstechnica.com",
        "category": "en_tech_news",
        "description": "Ars Technica - Technology Lab",
    },
    {
        "title": "Wired",
        "feed_url": "https://www.wired.com/feed/rss",
        "site_url": "https://www.wired.com",
        "category": "en_tech_news",
        "description": "Wired - Latest News",
    },
    {
        "title": "MIT Technology Review",
        "feed_url": "https://www.technologyreview.com/feed/",
        "site_url": "https://www.technologyreview.com",
        "category": "en_tech_news",
        "description": "MIT Technology Review",
    },
    {
        "title": "Reuters Technology",
        "feed_url": "https://feeds.reuters.com/reuters/technologyNews",
        "site_url": "https://www.reuters.com",
        "category": "en_news",
        "description": "Reuters Technology News",
    },
    {
        "title": "BBC News",
        "feed_url": "http://feeds.bbci.co.uk/news/rss.xml",
        "site_url": "https://www.bbc.com/news",
        "category": "en_news",
        "description": "BBC News - Top Stories",
    },
    {
        "title": "BBC Technology",
        "feed_url": "http://feeds.bbci.co.uk/news/technology/rss.xml",
        "site_url": "https://www.bbc.com/news/technology",
        "category": "en_tech_news",
        "description": "BBC News - Technology",
    },
    {
        "title": "NPR News",
        "feed_url": "https://feeds.npr.org/1001/rss.xml",
        "site_url": "https://www.npr.org",
        "category": "en_news",
        "description": "NPR News Headlines",
    },
    {
        "title": "CNN Top Stories",
        "feed_url": "http://rss.cnn.com/rss/edition.rss",
        "site_url": "https://edition.cnn.com",
        "category": "en_news",
        "description": "CNN Top Stories",
    },
]

# =============================================================================
# 中文新闻 RSS 种子数据 → rss_feeds 表
# =============================================================================
CN_NEWS_RSS_FEEDS = [
    {
        "title": "36氪",
        "feed_url": "https://36kr.com/feed",
        "site_url": "https://36kr.com",
        "category": "cn_tech_news",
        "description": "36氪 - 让一部分人先看到未来",
    },
    {
        "title": "少数派",
        "feed_url": "https://sspai.com/feed",
        "site_url": "https://sspai.com",
        "category": "cn_tech_news",
        "description": "少数派 - 高品质数字消费指南",
    },
    {
        "title": "澎湃新闻",
        "feed_url": "https://rsshub.app/thepaper/featured",
        "site_url": "https://www.thepaper.cn",
        "category": "cn_news",
        "description": "澎湃新闻 - 专注时政与思想",
    },
    {
        "title": "虎嗅",
        "feed_url": "https://rsshub.app/huxiu/article",
        "site_url": "https://www.huxiu.com",
        "category": "cn_tech_news",
        "description": "虎嗅 - 有视角的商业资讯与交流",
    },
    {
        "title": "界面新闻",
        "feed_url": "https://rsshub.app/jiemian/list/4",
        "site_url": "https://www.jiemian.com",
        "category": "cn_news",
        "description": "界面新闻 - 只服务于独立思考的人群",
    },
]

# =============================================================================
# 中文官方媒体 HTML 源种子数据 → news_sources 表
# 注意: selectors 需要实际访问页面确认 CSS 选择器，这里预填合理值
# =============================================================================
CN_NEWS_SOURCES = [
    {
        "name": "新华网-时政",
        "site_url": "http://www.xinhuanet.com",
        # 数据通过 dw.js 动态加载的 JSON 数据源文件获取，datasource ID 来自 politics 页面 HTML
        # 对应栏目名称：时政关注（1000 条滚动更新）
        "list_url": "http://www.news.cn/politics/ds_a6d618872de143bdafa2556915a7ae12.json",
        "country": "CN",
        "news_category": "general",
        "encoding": "utf-8",
        "selectors": {
            # fetch_type 存储在 selectors 内，由工厂读取后传给爬虫
            "fetch_type": "json",
            # JSON 响应结构: {"datasource": [...]}
            "data_path": "datasource",
            # 各字段对应 JSON 数据中的 key 名称
            # title 字段包含 HTML 标签（<a href>...），解析时需剥离
            "title": "title",
            "link": "publishUrl",
            "summary": "summary",
            "time": "publishTime",
            "image": "",
        },
    },
    {
        "name": "人民网-国内",
        "site_url": "http://www.people.com.cn",
        "list_url": "http://www.people.com.cn/GB/59476/index.html",
        "country": "CN",
        "news_category": "general",
        "encoding": "gbk",
        "selectors": {
            # 该页面为传统静态 HTML，文章列表位于 <table id="ta_1"> 内的 <td class="p6"> 下
            # <li> 直接放在 <td> 内，无 <ul> 包裹
            "article_list": "td.p6 li",
            "title": "a",
            "link": "a",
            "summary": "",
            "time": "",
            "image": "img",
            "content": "div.rm_txt_con",
        },
    },
    {
        "name": "央视网-新闻",
        "site_url": "https://news.cctv.com",
        # 央视网通过 JSONP 接口加载文章列表，直接请求数据接口
        "list_url": "https://news.cctv.com/2019/07/gaiban/cmsdatainterface/page/china_1.jsonp",
        "country": "CN",
        "news_category": "general",
        "encoding": "utf-8",
        "selectors": {
            # fetch_type 存储在 selectors 内，由工厂读取后传给爬虫
            "fetch_type": "jsonp",
            # JSONP 响应结构: china({"data":{"list":[...]}})
            "data_path": "data.list",
            # 各字段对应 JSONP 数据中的 key 名称
            "title": "title",
            "link": "url",
            "summary": "brief",
            "time": "focus_date",
            "image": "image",
            "content": "div.cnt_bd",
        },
    },
]


async def seed_rss_feeds(feeds: list[dict], label: str) -> int:
    """Seed RSS feeds (idempotent via INSERT IGNORE on unique feed_url).

    Args:
        feeds: Feed data dicts
        label: Label for logging (e.g., "EN News RSS" / "CN News RSS")

    Returns:
        Number of new feeds inserted
    """
    session_factory = get_session_factory()
    inserted = 0

    async with session_factory() as session:
        for feed_data in feeds:
            # 检查是否已存在
            result = await session.execute(
                select(RssFeed).where(RssFeed.feed_url == feed_data["feed_url"])
            )
            existing = result.scalar_one_or_none()

            if existing:
                logger.info(f"  [SKIP] {feed_data['title']} - already exists (id={existing.id})")
                continue

            feed = RssFeed(
                title=feed_data["title"],
                feed_url=feed_data["feed_url"],
                site_url=feed_data.get("site_url", ""),
                category=feed_data.get("category", ""),
                description=feed_data.get("description", ""),
                is_active=True,
            )
            session.add(feed)
            inserted += 1
            logger.info(f"  [ADD] {feed_data['title']} ({feed_data['category']})")

        await session.commit()

    logger.info(f"{label}: inserted {inserted}/{len(feeds)} feeds")
    return inserted


async def seed_news_sources(sources: list[dict]) -> int:
    """Seed HTML news sources (upsert via name — updates selectors/list_url if changed).

    Args:
        sources: NewsSource data dicts

    Returns:
        Number of new sources inserted (updates are not counted)
    """
    session_factory = get_session_factory()
    inserted = 0

    async with session_factory() as session:
        for source_data in sources:
            # 按 name 匹配（list_url 可能已更新）
            result = await session.execute(
                select(NewsSource).where(
                    NewsSource.name == source_data["name"],
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                # 更新可能已变更的字段（selectors / list_url / encoding）
                changed = False
                if existing.list_url != source_data["list_url"]:
                    existing.list_url = source_data["list_url"]
                    changed = True
                if existing.selectors != source_data["selectors"]:
                    existing.selectors = source_data["selectors"]
                    changed = True
                if existing.encoding != source_data.get("encoding", "utf-8"):
                    existing.encoding = source_data.get("encoding", "utf-8")
                    changed = True
                if changed:
                    logger.info(f"  [UPDATE] {source_data['name']} (id={existing.id}) - selectors/list_url updated")
                else:
                    logger.info(f"  [SKIP] {source_data['name']} - already up-to-date (id={existing.id})")
                continue

            source = NewsSource(
                name=source_data["name"],
                site_url=source_data["site_url"],
                list_url=source_data["list_url"],
                selectors=source_data["selectors"],
                country=source_data.get("country", "CN"),
                news_category=source_data.get("news_category", "general"),
                encoding=source_data.get("encoding", "utf-8"),
                is_active=True,
            )
            session.add(source)
            inserted += 1
            logger.info(f"  [ADD] {source_data['name']} ({source_data['country']}/{source_data['news_category']})")

        await session.commit()

    logger.info(f"CN News Sources: inserted {inserted}/{len(sources)} sources")
    return inserted


async def main():
    """Run all seed operations."""
    logger.info("=" * 60)
    logger.info("Seeding news sources for ResearchPulse v2")
    logger.info("=" * 60)

    # 1. 英文新闻 RSS
    logger.info("\n--- EN News RSS Feeds ---")
    en_count = await seed_rss_feeds(EN_NEWS_RSS_FEEDS, "EN News RSS")

    # 2. 中文新闻 RSS
    logger.info("\n--- CN News RSS Feeds ---")
    cn_rss_count = await seed_rss_feeds(CN_NEWS_RSS_FEEDS, "CN News RSS")

    # 3. 中文官方媒体 HTML 源
    logger.info("\n--- CN Official Media Sources ---")
    cn_html_count = await seed_news_sources(CN_NEWS_SOURCES)

    # 总结
    logger.info("\n" + "=" * 60)
    logger.info("Seed Summary:")
    logger.info(f"  EN News RSS feeds: {en_count} new / {len(EN_NEWS_RSS_FEEDS)} total")
    logger.info(f"  CN News RSS feeds: {cn_rss_count} new / {len(CN_NEWS_RSS_FEEDS)} total")
    logger.info(f"  CN HTML sources:   {cn_html_count} new / {len(CN_NEWS_SOURCES)} total")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
