from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import delete, func, select

from .config import settings as rss_settings
from .database import close_db, get_session, init_db
from .models import Article, Feed
from .parser import fetch_and_parse_feed

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None
_last_run_at: Optional[str] = None
_last_error: Optional[str] = None

# ---------------------------------------------------------------------------
# Default RSS feeds (62 feeds across 11 categories)
# ---------------------------------------------------------------------------

DEFAULT_FEEDS = [
    # ---- 科技 ----
    {"title": "36氪", "feed_url": "https://36kr.com/feed", "category": "科技"},
    {"title": "少数派", "feed_url": "https://sspai.com/feed", "category": "科技"},
    {"title": "爱范儿", "feed_url": "https://www.ifanr.com/feed", "category": "科技"},
    {"title": "IT之家", "feed_url": "http://www.ithome.com/rss/", "category": "科技"},
    {"title": "虎嗅网", "feed_url": "https://www.huxiu.com/rss/0.xml", "category": "科技"},
    {"title": "TechCrunch", "feed_url": "https://techcrunch.com/feed", "category": "科技"},
    {"title": "The Verge", "feed_url": "https://www.theverge.com/rss/index.xml", "category": "科技"},
    {"title": "MIT Technology Review", "feed_url": "https://www.technologyreview.com/feed", "category": "科技"},
    {"title": "Wired", "feed_url": "https://www.wired.com/feed/rss", "category": "科技"},
    {"title": "量子位", "feed_url": "https://www.qbitai.com/feed", "category": "科技"},
    {"title": "Solidot", "feed_url": "https://www.solidot.org/index.rss", "category": "科技"},
    {"title": "小道消息", "feed_url": "https://happyxiao.com/feed/", "category": "科技"},
    {"title": "人人都是产品经理", "feed_url": "http://www.woshipm.com/feed", "category": "科技"},
    # ---- 新闻时事 ----
    {"title": "NYTimes", "feed_url": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml", "category": "新闻时事"},
    {"title": "NYTimes Tech", "feed_url": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml", "category": "新闻时事"},
    {"title": "CNN", "feed_url": "http://rss.cnn.com/rss/edition.rss", "category": "新闻时事"},
    {"title": "The Guardian", "feed_url": "https://www.theguardian.com/world/rss", "category": "新闻时事"},
    {"title": "Washington Post", "feed_url": "http://feeds.washingtonpost.com/rss/world", "category": "新闻时事"},
    {"title": "The Atlantic", "feed_url": "https://www.theatlantic.com/feed/all/", "category": "新闻时事"},
    {"title": "The New Yorker", "feed_url": "https://www.newyorker.com/feed/everything", "category": "新闻时事"},
    {"title": "TIME", "feed_url": "http://feeds.feedburner.com/time/topstories", "category": "新闻时事"},
    {"title": "联合早报", "feed_url": "https://plink.anyfeeder.com/zaobao/realtime/china", "category": "新闻时事"},
    {"title": "中国日报", "feed_url": "http://www.chinadaily.com.cn/rss/china_rss.xml", "category": "新闻时事"},
    # ---- 商业财经 ----
    {"title": "钛媒体", "feed_url": "http://www.tmtpost.com/feed", "category": "商业财经"},
    {"title": "雪球今日话题", "feed_url": "https://xueqiu.com/hots/topic/rss", "category": "商业财经"},
    {"title": "华丽志", "feed_url": "http://luxe.co/feed/", "category": "商业财经"},
    {"title": "经济观察报", "feed_url": "http://www.eeo.com.cn/rss.xml", "category": "商业财经"},
    # ---- IT/软件开发 ----
    {"title": "阮一峰", "feed_url": "http://www.ruanyifeng.com/blog/atom.xml", "category": "IT/软件开发"},
    {"title": "酷壳", "feed_url": "https://coolshell.cn/feed", "category": "IT/软件开发"},
    {"title": "美团技术团队", "feed_url": "https://tech.meituan.com/feed/", "category": "IT/软件开发"},
    {"title": "V2EX技术", "feed_url": "https://www.v2ex.com/feed/tab/tech.xml", "category": "IT/软件开发"},
    {"title": "博客园", "feed_url": "http://feed.cnblogs.com/blog/sitehome/rss", "category": "IT/软件开发"},
    {"title": "OSCHINA", "feed_url": "https://www.oschina.net/news/rss", "category": "IT/软件开发"},
    {"title": "机器之心", "feed_url": "https://www.jiqizhixin.com/rss", "category": "IT/软件开发"},
    {"title": "技术小黑屋", "feed_url": "https://droidyue.com/atom.xml", "category": "IT/软件开发"},
    {"title": "Hacker News", "feed_url": "https://news.ycombinator.com/rss", "category": "IT/软件开发"},
    {"title": "GitHub Blog", "feed_url": "https://github.blog/feed", "category": "IT/软件开发"},
    {"title": "Stack Overflow Blog", "feed_url": "https://stackoverflow.blog/feed", "category": "IT/软件开发"},
    {"title": "掘金", "feed_url": "https://juejin.cn/rss", "category": "IT/软件开发"},
    {"title": "月光博客", "feed_url": "https://www.williamlong.info/rss.xml", "category": "IT/软件开发"},
    {"title": "TechRepublic", "feed_url": "https://www.techrepublic.com/rssfeeds/articles", "category": "IT/软件开发"},
    # ---- 设计/UI/UX ----
    {"title": "胶片的味道", "feed_url": "http://letsfilm.org/feed", "category": "设计/UI/UX"},
    {"title": "Smashing Magazine", "feed_url": "https://www.smashingmagazine.com/feed", "category": "设计/UI/UX"},
    {"title": "CSS-Tricks", "feed_url": "https://css-tricks.com/feed", "category": "设计/UI/UX"},
    {"title": "A List Apart", "feed_url": "https://alistapart.com/main/feed", "category": "设计/UI/UX"},
    # ---- 游戏 ----
    {"title": "机核", "feed_url": "https://www.gcores.com/rss", "category": "游戏"},
    {"title": "游研社", "feed_url": "http://www.yystv.cn/rss/feed", "category": "游戏"},
    {"title": "触乐", "feed_url": "http://www.chuapp.com/feed", "category": "游戏"},
    # ---- 科学 ----
    {"title": "Nature", "feed_url": "http://feeds.nature.com/nature/rss/current", "category": "科学"},
    {"title": "Science", "feed_url": "https://www.science.org/rss/news_current.xml", "category": "科学"},
    # ---- 读书/文化 ----
    {"title": "书格", "feed_url": "https://new.shuge.org/feed/", "category": "读书/文化"},
    {"title": "海德沙龙", "feed_url": "http://headsalon.org/feed", "category": "读书/文化"},
    {"title": "博海拾贝", "feed_url": "https://bohaishibei.com/feed/", "category": "读书/文化"},
    # ---- 生活 ----
    {"title": "利器", "feed_url": "https://liqi.io/index.xml", "category": "生活"},
    {"title": "理想生活实验室", "feed_url": "http://www.toodaylab.com/feed", "category": "生活"},
    {"title": "Lifehacker", "feed_url": "https://lifehacker.com/rss", "category": "生活"},
    # ---- 产品运营 ----
    {"title": "小众软件", "feed_url": "https://feeds.appinn.com/appinns/", "category": "产品运营"},
    {"title": "异次元软件世界", "feed_url": "http://feed.iplaysoft.com", "category": "产品运营"},
    {"title": "运营派", "feed_url": "https://www.yunyingpai.com/feed", "category": "产品运营"},
    # ---- 精进 ----
    {"title": "数字尾巴", "feed_url": "http://www.dgtle.com/rss/dgtle.xml", "category": "精进"},
    {"title": "VOICER", "feed_url": "http://www.voicer.me/feed", "category": "精进"},
]


def get_status() -> dict:
    return {
        "last_run_at": _last_run_at,
        "last_error": _last_error,
    }


async def _init_default_feeds() -> None:
    """Insert DEFAULT_FEEDS only if the feeds table is empty."""
    async with get_session() as session:
        count_result = await session.execute(select(func.count()).select_from(Feed))
        count = count_result.scalar_one()
        if count > 0:
            return

        for feed_data in DEFAULT_FEEDS:
            feed = Feed(
                title=feed_data["title"],
                feed_url=feed_data["feed_url"],
                category=feed_data["category"],
            )
            session.add(feed)

    logger.info("Initialized %d default RSS feeds", len(DEFAULT_FEEDS))


async def _crawl_all_feeds() -> dict:
    """Fetch all active RSS feeds and store new articles."""
    global _last_run_at, _last_error

    try:
        async with get_session() as session:
            result = await session.execute(
                select(Feed).where(Feed.is_active == True)  # noqa: E712
            )
            feeds = result.scalars().all()

        new_count = 0
        for feed in feeds:
            articles = await fetch_and_parse_feed(
                feed_url=feed.feed_url,
                timeout=rss_settings.http_timeout,
                delay=rss_settings.http_delay_base,
                jitter=rss_settings.http_delay_jitter,
            )

            # Limit articles per feed
            articles = articles[: rss_settings.max_articles_per_feed]

            async with get_session() as session:
                feed_errors = 0
                for article_data in articles:
                    # Deduplication by url
                    existing = await session.execute(
                        select(Article.id).where(
                            Article.url == article_data["url"]
                        )
                    )
                    if existing.scalar_one_or_none() is not None:
                        continue
                    article = Article(feed_id=feed.id, **article_data)
                    session.add(article)
                    new_count += 1

                # Update feed metadata
                feed_obj = await session.get(Feed, feed.id)
                if feed_obj:
                    feed_obj.last_fetched_at = datetime.now(timezone.utc)
                    if not articles:
                        feed_obj.error_count = feed_obj.error_count + 1
                    else:
                        feed_obj.error_count = 0

        _last_run_at = datetime.now(timezone.utc).isoformat()
        _last_error = None
        logger.info("RSS crawl finished", extra={"new_articles": new_count})

    except Exception as exc:
        _last_error = str(exc)
        logger.exception("RSS crawl failed")

    return get_status()


async def _cleanup_old_articles() -> None:
    """Remove articles older than retention_days."""
    if rss_settings.retention_days <= 0:
        return
    cutoff = datetime.now(timezone.utc) - timedelta(days=rss_settings.retention_days)
    async with get_session() as session:
        result = await session.execute(
            delete(Article).where(Article.crawl_time < cutoff)
        )
        deleted = result.rowcount
        if deleted:
            logger.info("Cleaned up old articles", extra={"deleted": deleted})


def _run_crawl_sync() -> None:
    """Synchronous wrapper for scheduler."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_crawl_all_feeds())
        loop.run_until_complete(_cleanup_old_articles())
    finally:
        loop.close()


async def run_crawl() -> dict:
    """Public async entry point for manual trigger."""
    result = await _crawl_all_feeds()
    await _cleanup_old_articles()
    return result


def _build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=rss_settings.schedule_timezone)
    parts = rss_settings.schedule_cron.split()
    if len(parts) == 5:
        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
            timezone=rss_settings.schedule_timezone,
        )
    else:
        trigger = CronTrigger(hour="*/2", timezone=rss_settings.schedule_timezone)
    scheduler.add_job(_run_crawl_sync, trigger, id="rss_crawl", replace_existing=True)
    return scheduler


async def start_scheduler() -> None:
    global _scheduler
    await init_db()
    await _init_default_feeds()
    if _scheduler and _scheduler.running:
        return
    _scheduler = _build_scheduler()
    _scheduler.start()
    logger.info("RSS crawler scheduler started")


async def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    await close_db()
    logger.info("RSS crawler scheduler stopped")


async def run_crawl_on_startup() -> None:
    if not rss_settings.run_on_startup:
        return
    logger.info("RSS startup crawl triggered")

    def _startup():
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_crawl_all_feeds())
        finally:
            loop.close()

    thread = threading.Thread(target=_startup, name="rss-startup-crawl", daemon=True)
    thread.start()
