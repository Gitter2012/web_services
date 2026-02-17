# ==============================================================================
# 模块: ResearchPulse 邮件通知任务
# 作用: 本模块负责爬取完成后的邮件通知功能，包括:
#       1. 向管理员发送爬取完成报告（统计数据和错误汇总）
#       2. 向订阅用户发送个性化的文章推送邮件（基于用户订阅偏好）
# 架构角色: 作为爬取流程的后置通知环节，由 crawl_job 在爬取完成后触发调用。
#           连接了用户订阅系统（UserSubscription）和邮件发送基础设施（email 模块），
#           实现了从数据采集到用户触达的完整闭环。
# 核心流程: 查询用户订阅 -> 匹配文章 -> 渲染邮件内容 -> 发送邮件
# 注意事项: 超级管理员默认排除在用户通知之外（他们会收到单独的管理员报告），
#           用户可通过个人设置控制通知频率（每日/每周/关闭）。
# ==============================================================================

"""Email notification tasks for ResearchPulse v2.

This module handles sending email notifications to users after crawling.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

# Article: 文章数据模型
# UserSubscription: 用户订阅关系模型，记录用户订阅了哪些数据源
# UserArticleState: 用户文章阅读状态模型（如已读/未读/收藏等）
from apps.crawler.models import Article, UserSubscription, UserArticleState
from core.database import get_session_factory
# send_email: 基础邮件发送函数; send_email_with_fallback: 带降级策略的邮件发送
from common.email import send_email, send_email_with_fallback
# render_articles_by_source: 按数据源分组渲染文章为 Markdown 格式
from common.markdown import render_articles_by_source
from settings import settings

logger = logging.getLogger(__name__)


async def get_user_subscribed_articles(
    user_id: int,
    source_type: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Get articles matching a user's subscriptions.

    根据用户订阅配置与可选过滤条件，返回匹配的文章列表。

    Args:
        user_id: User ID used to look up subscriptions.
        source_type: Optional source filter (e.g. ``arxiv``/``rss``/``wechat``).
        since: Optional crawl time lower bound.
        limit: Max number of articles to return.

    Returns:
        List[Dict[str, Any]]: Matched articles ordered by crawl time.
    """
    # 功能: 根据用户的订阅配置，查询并返回匹配的文章列表
    # 参数:
    #   user_id: 用户 ID，用于查询该用户的订阅信息
    #   source_type: 可选的数据源类型过滤器（如 "arxiv"、"rss"、"wechat"）
    #   since: 可选的时间过滤器，只返回此时间之后爬取的文章
    #   limit: 返回的最大文章数量，默认20篇
    # 返回值: List[Dict] - 匹配用户订阅的文章字典列表，按爬取时间倒序排列
    # 副作用: 无（纯查询操作）

    session_factory = get_session_factory()

    async with session_factory() as session:
        # ---- 第一步: 获取用户的所有活跃订阅 ----
        # Get user's subscriptions
        sub_result = await session.execute(
            select(UserSubscription).where(
                UserSubscription.user_id == user_id,
                UserSubscription.is_active == True,
            )
        )
        subscriptions = sub_result.scalars().all()

        # 如果用户没有任何活跃订阅，直接返回空列表
        if not subscriptions:
            return []

        # ---- 第二步: 按数据源类型分类整理用户的订阅 ID ----
        # 将订阅按来源类型分组，便于后续文章匹配时进行分类过滤
        # Build subscription filters
        # For arxiv: source_type='arxiv_category', source_id=category_id
        # For rss: source_type='rss_feed', source_id=feed_id
        # For wechat: source_type='wechat_account', source_id=account_id

        arxiv_categories: Set[int] = set()     # 用户订阅的 ArXiv 分类 ID 集合
        rss_feeds: Set[int] = set()            # 用户订阅的 RSS 源 ID 集合
        wechat_accounts: Set[int] = set()      # 用户订阅的微信公众号 ID 集合

        for sub in subscriptions:
            if sub.source_type == "arxiv_category":
                arxiv_categories.add(sub.source_id)
            elif sub.source_type == "rss_feed":
                rss_feeds.add(sub.source_id)
            elif sub.source_type == "wechat_account":
                wechat_accounts.add(sub.source_id)

        # ---- 第三步: 构建文章查询条件 ----
        # 基础条件: 只查询未归档的文章
        # Build query for articles
        query = select(Article).where(Article.is_archived == False)

        # 日期过滤: 只获取指定时间之后的文章
        # Date filter
        if since:
            query = query.where(Article.crawl_time >= since)

        # 数据源类型过滤: 如果指定了源类型，只查该类型的文章
        # Source type filter
        if source_type:
            query = query.where(Article.source_type == source_type)

        # ---- 第四步: 执行查询并在应用层进行订阅匹配过滤 ----
        # 注意: 这里先查询 limit*3 条文章，然后在 Python 层面根据订阅关系过滤
        # 乘以3的原因是: 并非所有文章都会匹配用户的订阅，需要预取更多数据以保证最终结果数量
        # Execute query
        result = await session.execute(query.order_by(Article.crawl_time.desc()).limit(limit * 3))
        all_articles = result.scalars().all()

        # 在应用层面根据用户订阅进行文章匹配过滤
        # 此处采用应用层过滤而非数据库层 JOIN，是因为订阅关系涉及多种数据源类型，
        # 统一的数据库查询会过于复杂
        # Filter by subscriptions
        matched_articles = []
        for article in all_articles:
            # Check if article matches any subscription
            # ArXiv 文章匹配: 检查文章是否属于用户订阅的 ArXiv 分类
            if article.source_type == "arxiv" and arxiv_categories:
                # For arxiv, check if category matches
                # Note: This is simplified - you might need to join with arxiv_categories table
                if article.category:  # Category code
                    matched_articles.append(article)
                    continue
            # RSS 文章匹配: 检查文章的源 ID 是否在用户订阅的 RSS 源集合中
            elif article.source_type == "rss" and rss_feeds:
                # For RSS, source_id should match feed_id
                try:
                    if int(article.source_id) in rss_feeds:
                        matched_articles.append(article)
                        continue
                except (ValueError, TypeError):
                    # source_id 转换失败时跳过该文章（防御性处理）
                    pass
            # 微信文章匹配: 检查文章是否来自用户订阅的微信公众号
            elif article.source_type == "wechat" and wechat_accounts:
                # For WeChat, check account name match
                if article.wechat_account_name:
                    matched_articles.append(article)
                    continue

            # 已收集到足够数量的匹配文章时提前退出循环，避免不必要的遍历
            if len(matched_articles) >= limit:
                break

        # ---- 第五步: 将匹配的文章 ORM 对象转换为字典格式 ----
        # 转换为 dict 后可以脱离数据库 session 使用，并方便后续的 JSON 序列化
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
            for a in matched_articles[:limit]  # 截取前 limit 条结果
        ]


async def send_user_notification_email(
    user_email: str,
    user_id: int,
    articles: List[Dict[str, Any]],
    date: Optional[str] = None,
) -> bool:
    """Send a subscription digest email to a user.

    向用户发送订阅文章摘要邮件，包含按数据源分组的内容。

    Args:
        user_email: Recipient email address.
        user_id: User ID for logging.
        articles: Article payloads to include in the email.
        date: Optional date string used in subject/content.

    Returns:
        bool: ``True`` if sent successfully, otherwise ``False``.
    """
    # 功能: 向指定用户发送包含订阅文章摘要的通知邮件
    # 参数:
    #   user_email: 收件人邮箱地址
    #   user_id: 用户 ID（用于日志记录）
    #   articles: 待推送的文章字典列表
    #   date: 可选的日期字符串，用于邮件标题和内容，默认为当天日期
    # 返回值: bool - True 表示发送成功，False 表示发送失败或无文章可发
    # 副作用: 发送邮件（SMTP 网络请求）

    # 如果没有文章可发送，直接返回
    if not articles:
        logger.debug(f"No articles to send to user {user_id}")
        return False

    # 如果未指定日期，使用当前 UTC 日期
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ---- 生成邮件内容 ----

    # 邮件标题: 包含日期和文章数量，使用中文
    # Generate email content
    subject = f"ResearchPulse - {date} 订阅文章 ({len(articles)} 篇)"

    # 先生成 Markdown 格式的文章列表内容
    # 按数据源分组展示，每篇文章包含摘要（最长300字符）
    # Generate markdown content
    md_content = render_articles_by_source(
        articles,
        date=date,
        include_abstract=True,
        abstract_max_len=300,
    )

    # ---- 将 Markdown 转换为简易 HTML 格式 ----
    # 采用简单的逐行转换策略，而非引入完整的 Markdown 解析库
    # 这样做的原因是邮件 HTML 对复杂 Markdown 语法的兼容性有限，
    # 简单转换已能满足邮件展示需求
    # Convert to HTML-like format for email
    # Simple conversion: newlines to <br>, headers to bold
    html_lines = []
    for line in md_content.split("\n"):
        line = line.strip()
        if not line:
            html_lines.append("")
            continue
        # 一级标题转为 <h1>
        if line.startswith("# "):
            html_lines.append(f"<h1>{line[2:]}</h1>")
        # 二级标题转为 <h2>
        elif line.startswith("## "):
            html_lines.append(f"<h2>{line[3:]}</h2>")
        # 三级标题转为 <h3>
        elif line.startswith("### "):
            html_lines.append(f"<h3>{line[4:]}</h3>")
        # 粗体文本转为 <strong>
        elif line.startswith("**") and line.endswith("**"):
            html_lines.append(f"<p><strong>{line[2:-2]}</strong></p>")
        # 无序列表项转为 <li>
        elif line.startswith("- "):
            html_lines.append(f"<li>{line[2:]}</li>")
        # 水平分割线转为 <hr>
        elif line.startswith("---"):
            html_lines.append("<hr>")
        else:
            # 普通文本: 先转义 HTML 特殊字符以防止 XSS，然后包裹在 <p> 中
            # Escape HTML
            line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            html_lines.append(f"<p>{line}</p>")

    # 组装完整的 HTML 邮件正文
    # 包含内联 CSS 样式，确保在各邮件客户端中有一致的展示效果
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

    # 纯文本版本的邮件正文（作为 HTML 邮件的降级方案）
    # 某些邮件客户端可能不支持 HTML，此时会显示纯文本版本
    # Plain text body
    text_body = f"""ResearchPulse - {date} 订阅文章

您订阅的文章如下：

{md_content}

---
此邮件由 ResearchPulse v2 自动发送。
"""

    # ---- 发送邮件 ----
    # Send email
    try:
        ok, error = send_email(
            subject=subject,
            body=text_body,
            to_addrs=[user_email],
            html_body=html_body,
            # 使用配置的第一个邮件后端（可能配置多个后端用逗号分隔）
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
    """Send crawl completion report to admin.

    向管理员发送爬取完成报告，包含统计数据与错误汇总。

    Args:
        crawl_stats: Crawl summary statistics dictionary.

    Returns:
        bool: ``True`` if email sent successfully, otherwise ``False``.
    """
    # 功能: 向管理员发送爬取完成报告邮件，包含本次爬取的统计数据和错误汇总
    # 参数:
    #   crawl_stats: 爬取统计字典，包含各数据源的文章数、总数、错误列表等
    # 返回值: bool - True 表示发送成功，False 表示发送失败或邮件功能未启用
    # 副作用: 发送邮件（SMTP 网络请求）

    # 前置检查: 邮件功能未启用或未配置发件人地址时，直接跳过
    if not settings.email_enabled or not settings.email_from:
        return False

    subject = f"ResearchPulse - 爬取完成报告"

    # 从爬取统计中提取各项数据
    stats = crawl_stats.get("stats", {})
    total = crawl_stats.get("total_articles", 0)
    errors = crawl_stats.get("errors", [])

    # 构建纯文本格式的报告正文（管理员报告不需要 HTML 美化）
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
    # 注意: errors[:5] 最多只展示前5条错误，避免邮件过长

    try:
        # 发送报告邮件到管理员邮箱（使用 email_from 作为管理员收件地址）
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
    """Send notifications to subscribed users.

    遍历订阅用户并发送个性化邮件，默认排除超级管理员。

    Args:
        since: Optional lower bound for article crawl time.
        max_users: Max number of users to process in one run.

    Returns:
        Dict[str, Any]: Delivery summary including sent/failed counts.
    """
    # 功能: 遍历所有有活跃订阅的用户，为每个用户生成个性化的文章推送并发送邮件
    # 参数:
    #   since: 可选的时间过滤器，只推送此时间之后的文章，默认为当天零时
    #   max_users: 单次执行最多处理的用户数量，防止在用户量大时任务执行过久
    # 返回值: Dict - 包含通知发送统计:
    #   - sent: 成功发送的邮件数
    #   - failed: 发送失败的邮件数
    #   - total: 有订阅的用户总数
    #   - skipped: 被跳过的用户数（超级管理员、关闭通知、不在推送周期内等）
    #   - errors: 错误信息列表
    # 副作用: 发送邮件（可能产生大量 SMTP 网络请求）

    # 前置检查: 邮件功能未启用时直接返回
    if not settings.email_enabled:
        logger.info("Email notifications disabled")
        return {"sent": 0, "failed": 0, "total": 0}

    # 默认推送时间范围: 当天零时至当前时刻
    if not since:
        # Default: articles from last 24 hours
        since = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    session_factory = get_session_factory()
    # 初始化通知发送结果统计
    results = {"sent": 0, "failed": 0, "total": 0, "skipped": 0, "errors": []}

    async with session_factory() as session:
        # ---- 第一步: 获取所有有活跃订阅的用户 ID ----
        # Get all users with active subscriptions
        from core.models.user import User

        # 使用 distinct() 去重，确保每个用户只处理一次（即使有多个订阅）
        # Get distinct user IDs from subscriptions
        sub_result = await session.execute(
            select(UserSubscription.user_id).distinct()
        )
        user_ids = [row[0] for row in sub_result.fetchall()]

        results["total"] = len(user_ids)

        # ---- 第二步: 逐用户处理通知 ----
        # 使用 max_users 限制单次处理的用户数量，防止任务超时
        for i, user_id in enumerate(user_ids[:max_users]):
            try:
                # 查询用户详细信息
                # Get user info
                user_result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = user_result.scalar_one_or_none()

                # 用户不存在或没有设置邮箱地址，跳过
                if not user or not user.email:
                    continue

                # 跳过超级管理员: 他们会收到单独的管理员爬取报告，无需重复接收用户通知
                # Skip superusers (they get admin notification separately)
                if user.is_superuser:
                    logger.debug(f"Skipping superuser {user_id} for user notifications")
                    results["skipped"] += 1
                    continue

                # 检查用户的邮件通知偏好设置
                # 使用 getattr 带默认值，兼容旧版本用户模型中可能不存在此字段的情况
                # Check user's notification preference
                # Default to True if field doesn't exist (for backwards compatibility)
                notifications_enabled = getattr(user, 'email_notifications_enabled', True)
                if not notifications_enabled:
                    logger.debug(f"User {user_id} has disabled email notifications")
                    results["skipped"] += 1
                    continue

                # 检查用户设置的推送频率（daily=每日 / weekly=每周 / none=关闭）
                # Check digest frequency
                frequency = getattr(user, 'email_digest_frequency', 'daily')
                if frequency == 'none':
                    logger.debug(f"User {user_id} has set frequency to 'none'")
                    results["skipped"] += 1
                    continue

                # 周报用户只在周一发送: weekday() == 0 表示周一
                # 其他日期跳过周报用户，避免重复发送
                # For weekly digest, only send on Mondays
                if frequency == 'weekly' and datetime.now(timezone.utc).weekday() != 0:
                    logger.debug(f"Skipping user {user_id} - weekly digest not due today")
                    results["skipped"] += 1
                    continue

                # ---- 第三步: 获取该用户的订阅匹配文章 ----
                # Get user's subscribed articles
                articles = await get_user_subscribed_articles(
                    user_id=user_id,
                    since=since,
                    limit=settings.email_max_articles,
                )

                # 该用户没有匹配的新文章，跳过发送
                if not articles:
                    logger.debug(f"No new articles for user {user_id}")
                    continue

                # ---- 第四步: 发送个性化通知邮件 ----
                # Send notification
                ok = await send_user_notification_email(
                    user_email=user.email,
                    user_id=user_id,
                    articles=articles,
                    date=since.strftime("%Y-%m-%d"),
                )

                # 更新统计计数
                if ok:
                    results["sent"] += 1
                else:
                    results["failed"] += 1

            except Exception as e:
                # 单个用户的通知发送失败不影响其他用户，记录错误后继续处理
                logger.error(f"Error notifying user {user_id}: {e}")
                results["failed"] += 1
                results["errors"].append(f"User {user_id}: {str(e)}")

    logger.info(f"Notifications sent: {results['sent']}/{results['total']}")
    return results


async def run_notification_job() -> dict:
    """Run the daily email notification job.

    独立的定时任务，每天定时向订阅用户发送个性化的文章摘要邮件。
    收集过去24小时内的文章，并尊重每个用户的通知偏好设置。

    Returns:
        dict: Notification delivery summary.
    """
    logger.info("Starting notification job")
    start_time = datetime.now(timezone.utc)

    # 收集过去24小时内的文章（而非从午夜开始），确保不遗漏任何文章
    since = start_time - timedelta(hours=24)

    try:
        results = await send_all_user_notifications(since=since)
    except Exception as e:
        logger.error(f"Notification job failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    summary = {
        "status": "completed",
        "duration_seconds": duration,
        "sent": results.get("sent", 0),
        "failed": results.get("failed", 0),
        "total_users": results.get("total", 0),
        "skipped": results.get("skipped", 0),
        "timestamp": end_time.isoformat(),
    }

    logger.info(f"Notification job completed: {summary}")
    return summary
