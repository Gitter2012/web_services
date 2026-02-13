"""Email notification tasks for ResearchPulse v2.

This module handles sending email notifications to users after crawling.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from apps.crawler.models import Article, UserSubscription, UserArticleState
from core.database import get_session_factory
from common.email import send_email, send_email_with_fallback
from common.markdown import render_articles_by_source
from settings import settings

logger = logging.getLogger(__name__)


async def get_user_subscribed_articles(
    user_id: int,
    source_type: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Get articles that match a user's subscriptions."""
    session_factory = get_session_factory()

    async with session_factory() as session:
        # Get user's subscriptions
        sub_result = await session.execute(
            select(UserSubscription).where(
                UserSubscription.user_id == user_id,
                UserSubscription.is_active == True,
            )
        )
        subscriptions = sub_result.scalars().all()

        if not subscriptions:
            return []

        # Build subscription filters
        # For arxiv: source_type='arxiv_category', source_id=category_id
        # For rss: source_type='rss_feed', source_id=feed_id
        # For wechat: source_type='wechat_account', source_id=account_id

        arxiv_categories: Set[int] = set()
        rss_feeds: Set[int] = set()
        wechat_accounts: Set[int] = set()

        for sub in subscriptions:
            if sub.source_type == "arxiv_category":
                arxiv_categories.add(sub.source_id)
            elif sub.source_type == "rss_feed":
                rss_feeds.add(sub.source_id)
            elif sub.source_type == "wechat_account":
                wechat_accounts.add(sub.source_id)

        # Build query for articles
        query = select(Article).where(Article.is_archived == False)

        # Date filter
        if since:
            query = query.where(Article.crawl_time >= since)

        # Source type filter
        if source_type:
            query = query.where(Article.source_type == source_type)

        # Execute query
        result = await session.execute(query.order_by(Article.crawl_time.desc()).limit(limit * 3))
        all_articles = result.scalars().all()

        # Filter by subscriptions
        matched_articles = []
        for article in all_articles:
            # Check if article matches any subscription
            if article.source_type == "arxiv" and arxiv_categories:
                # For arxiv, check if category matches
                # Note: This is simplified - you might need to join with arxiv_categories table
                if article.category:  # Category code
                    matched_articles.append(article)
                    continue
            elif article.source_type == "rss" and rss_feeds:
                # For RSS, source_id should match feed_id
                try:
                    if int(article.source_id) in rss_feeds:
                        matched_articles.append(article)
                        continue
                except (ValueError, TypeError):
                    pass
            elif article.source_type == "wechat" and wechat_accounts:
                # For WeChat, check account name match
                if article.wechat_account_name:
                    matched_articles.append(article)
                    continue

            if len(matched_articles) >= limit:
                break

        # Convert to dict
        return [
            {
                "id": a.id,
                "title": a.title,
                "url": a.url,
                "author": a.author,
                "summary": a.summary,
                "source_type": a.source_type,
                "category": a.category,
                "publish_time": a.publish_time.isoformat() if a.publish_time else None,
                "crawl_time": a.crawl_time.isoformat() if a.crawl_time else None,
                "arxiv_id": a.arxiv_id,
                "arxiv_primary_category": a.arxiv_primary_category,
                "arxiv_updated_time": a.arxiv_updated_time.isoformat() if a.arxiv_updated_time else None,
                "wechat_account_name": a.wechat_account_name,
                "tags": a.tags or [],
            }
            for a in matched_articles[:limit]
        ]


async def send_user_notification_email(
    user_email: str,
    user_id: int,
    articles: List[Dict[str, Any]],
    date: Optional[str] = None,
) -> bool:
    """Send notification email to a user."""
    if not articles:
        logger.debug(f"No articles to send to user {user_id}")
        return False

    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Generate email content
    subject = f"ResearchPulse - {date} 订阅文章 ({len(articles)} 篇)"

    # Generate markdown content
    md_content = render_articles_by_source(
        articles,
        date=date,
        include_abstract=True,
        abstract_max_len=300,
    )

    # Convert to HTML-like format for email
    # Simple conversion: newlines to <br>, headers to bold
    html_lines = []
    for line in md_content.split("\n"):
        line = line.strip()
        if not line:
            html_lines.append("")
            continue
        if line.startswith("# "):
            html_lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("### "):
            html_lines.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("**") and line.endswith("**"):
            html_lines.append(f"<p><strong>{line[2:-2]}</strong></p>")
        elif line.startswith("- "):
            html_lines.append(f"<li>{line[2:]}</li>")
        elif line.startswith("---"):
            html_lines.append("<hr>")
        else:
            # Escape HTML
            line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            html_lines.append(f"<p>{line}</p>")

    html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
            h1 {{ color: #1a1a2e; }}
            h2 {{ color: #333; border-bottom: 1px solid #eee; padding-bottom: 10px; }}
            h3 {{ color: #666; }}
            a {{ color: #4ecdc4; }}
            hr {{ border: none; border-top: 1px solid #eee; margin: 20px 0; }}
            code {{ background: #f5f5f5; padding: 2px 6px; border-radius: 4px; }}
        </style>
    </head>
    <body>
        {"".join(html_lines)}
        <hr>
        <p style="color: #888; font-size: 12px;">
            此邮件由 ResearchPulse v2 自动发送。<br>
            访问 <a href="https://your-domain/researchpulse/">ResearchPulse</a> 管理您的订阅。
        </p>
    </body>
    </html>
    """

    # Plain text body
    text_body = f"""ResearchPulse - {date} 订阅文章

您订阅的文章如下：

{md_content}

---
此邮件由 ResearchPulse v2 自动发送。
"""

    # Send email
    try:
        ok, error = send_email(
            subject=subject,
            body=text_body,
            to_addrs=[user_email],
            html_body=html_body,
            backend=settings.email_backend.split(",")[0].strip() or "smtp",
            from_addr=settings.email_from,
        )

        if ok:
            logger.info(f"Email sent to {user_email}: {len(articles)} articles")
            return True
        else:
            logger.error(f"Failed to send email to {user_email}: {error}")
            return False

    except Exception as e:
        logger.error(f"Error sending email to {user_email}: {e}")
        return False


async def send_crawl_completion_notification(
    crawl_stats: Dict[str, Any],
) -> bool:
    """Send notification after crawl completion to admin."""
    if not settings.email_enabled or not settings.email_from:
        return False

    subject = f"ResearchPulse - 爬取完成报告"

    stats = crawl_stats.get("stats", {})
    total = crawl_stats.get("total_articles", 0)
    errors = crawl_stats.get("errors", [])

    body = f"""ResearchPulse 爬取完成报告

时间: {datetime.now(timezone.utc).isoformat()}

统计:
- 总文章数: {total}
- ArXiv: {stats.get('arxiv', 0)}
- RSS: {stats.get('rss', 0)}
- WeChat: {stats.get('wechat', 0)}

错误: {len(errors)}
{chr(10).join([f"- {e}" for e in errors[:5]]) if errors else "无"}

---
ResearchPulse v2
"""

    try:
        ok, _ = send_email(
            subject=subject,
            body=body,
            to_addrs=[settings.email_from],
            backend=settings.email_backend.split(",")[0].strip() or "smtp",
            from_addr=settings.email_from,
        )
        return ok
    except Exception as e:
        logger.error(f"Failed to send crawl notification: {e}")
        return False


async def send_all_user_notifications(
    since: Optional[datetime] = None,
    max_users: int = 100,
) -> Dict[str, Any]:
    """Send notifications to all users with subscriptions.
    
    Note: Superusers are excluded by default from email notifications.
    Users can control their notification preferences via email_notifications_enabled.
    """
    if not settings.email_enabled:
        logger.info("Email notifications disabled")
        return {"sent": 0, "failed": 0, "total": 0}

    if not since:
        # Default: articles from last 24 hours
        since = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    session_factory = get_session_factory()
    results = {"sent": 0, "failed": 0, "total": 0, "skipped": 0, "errors": []}

    async with session_factory() as session:
        # Get all users with active subscriptions
        from core.models.user import User

        # Get distinct user IDs from subscriptions
        sub_result = await session.execute(
            select(UserSubscription.user_id).distinct()
        )
        user_ids = [row[0] for row in sub_result.fetchall()]

        results["total"] = len(user_ids)

        for i, user_id in enumerate(user_ids[:max_users]):
            try:
                # Get user info
                user_result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = user_result.scalar_one_or_none()

                if not user or not user.email:
                    continue

                # Skip superusers (they get admin notification separately)
                if user.is_superuser:
                    logger.debug(f"Skipping superuser {user_id} for user notifications")
                    results["skipped"] += 1
                    continue

                # Check user's notification preference
                # Default to True if field doesn't exist (for backwards compatibility)
                notifications_enabled = getattr(user, 'email_notifications_enabled', True)
                if not notifications_enabled:
                    logger.debug(f"User {user_id} has disabled email notifications")
                    results["skipped"] += 1
                    continue

                # Check digest frequency
                frequency = getattr(user, 'email_digest_frequency', 'daily')
                if frequency == 'none':
                    logger.debug(f"User {user_id} has set frequency to 'none'")
                    results["skipped"] += 1
                    continue

                # For weekly digest, only send on Mondays
                if frequency == 'weekly' and datetime.now(timezone.utc).weekday() != 0:
                    logger.debug(f"Skipping user {user_id} - weekly digest not due today")
                    results["skipped"] += 1
                    continue

                # Get user's subscribed articles
                articles = await get_user_subscribed_articles(
                    user_id=user_id,
                    since=since,
                    limit=settings.email_max_articles,
                )

                if not articles:
                    logger.debug(f"No new articles for user {user_id}")
                    continue

                # Send notification
                ok = await send_user_notification_email(
                    user_email=user.email,
                    user_id=user_id,
                    articles=articles,
                    date=since.strftime("%Y-%m-%d"),
                )

                if ok:
                    results["sent"] += 1
                else:
                    results["failed"] += 1

            except Exception as e:
                logger.error(f"Error notifying user {user_id}: {e}")
                results["failed"] += 1
                results["errors"].append(f"User {user_id}: {str(e)}")

    logger.info(f"Notifications sent: {results['sent']}/{results['total']}")
    return results
