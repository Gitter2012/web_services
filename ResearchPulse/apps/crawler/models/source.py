# =============================================================================
# 模块: apps/crawler/models/source.py
# 功能: 数据源模型定义（arXiv 分类、RSS 订阅源、微信公众号）
# 架构角色: 数据持久化层的来源管理模型。定义了系统支持的三种数据源类型，
#           每种数据源对应一个独立的模型/表，存储该来源的配置和状态信息。
# 核心模型:
#   - ArxivCategory: arXiv 学科分类（如 cs.AI、stat.ML）
#   - RssFeed: RSS/Atom 订阅源
#   - WechatAccount: 微信公众号账户
# 设计理念:
#   1. 每种数据源独立建模，因为不同来源的配置属性差异较大
#      （URL 格式、状态字段、层级关系等各不相同）
#   2. 所有数据源模型都包含 is_active 字段，支持软禁用（不删除数据但停止爬取）
#   3. RSS 和微信模型包含 error_count 和 last_fetched_at 字段，
#      用于追踪数据源的健康状态和自动禁用策略
# =============================================================================

"""Source models for ResearchPulse v2."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin


# =============================================================================
# ArxivCategory 模型
# 职责: 存储 arXiv 学科分类信息
# 表名: arxiv_categories
# 使用场景: 用户订阅 arXiv 分类时，从此表选择要关注的分类；
#           爬虫调度时，从此表获取所有活跃分类来决定需要爬取哪些分类。
# 设计决策:
#   1. code 字段设有唯一约束（如 "cs.AI"），是分类的自然键
#   2. parent_code 支持分类层级关系（如 "cs" 是 "cs.AI" 的父分类）
#   3. is_active 控制是否参与爬取调度
# =============================================================================
class ArxivCategory(Base, TimestampMixin):
    """arXiv category model.

    arXiv 分类配置模型。
    """

    __tablename__ = "arxiv_categories"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 分类代码（如 "cs.AI"、"cs.LG"、"stat.ML"），唯一且有索引
    code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Category code (e.g., cs.LG)",
    )
    # 分类的完整名称（如 "Artificial Intelligence"）
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Full category name",
    )
    # 父分类代码，用于构建分类层级树（如 "cs" 是 "cs.AI" 的父分类）
    parent_code: Mapped[str] = mapped_column(
        String(50),
        default="",
        nullable=False,
        comment="Parent category code",
    )
    # 分类描述信息
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    # 是否活跃：False 表示已停用，爬虫不再抓取此分类的论文
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    def __repr__(self) -> str:
        """Return a readable category representation.

        返回 arXiv 分类的字符串表示。
        """
        return f"<ArxivCategory(code={self.code}, name={self.name})>"


# =============================================================================
# RssFeed 模型
# 职责: 存储 RSS/Atom 订阅源的配置和运行状态
# 表名: rss_feeds
# 使用场景: 用户添加 RSS 订阅源时创建记录；
#           爬虫调度时查询所有活跃的 RSS 源进行爬取。
# 设计决策:
#   1. feed_url 设有唯一约束，防止重复添加同一个 RSS 源
#   2. error_count 记录连续失败次数，可用于自动禁用频繁出错的订阅源
#   3. last_fetched_at 记录最后一次成功抓取时间，用于判断数据时效性
# =============================================================================
class RssFeed(Base, TimestampMixin):
    """RSS feed subscription model.

    RSS 订阅源配置模型。
    """

    __tablename__ = "rss_feeds"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 订阅源标题（从 Feed 中自动获取或用户手动设置）
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="",
    )
    # RSS/Atom Feed 的 URL（唯一约束防止重复添加）
    feed_url: Mapped[str] = mapped_column(
        String(2000),
        unique=True,
        nullable=False,
    )
    # 订阅源对应的网站 URL
    site_url: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        default="",
    )
    # 订阅源分类（用户自定义，用于前端分组展示）
    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        index=True,
    )
    # 订阅源描述信息
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    # 是否活跃：False 表示已停用
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    # 最后一次成功抓取的时间（用于判断数据是否过期）
    last_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # 连续抓取失败的次数（可用于实现自动禁用策略，如连续失败 N 次后自动停用）
    error_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    def __repr__(self) -> str:
        """Return a readable RSS feed representation.

        返回 RSS 订阅源的字符串表示。
        """
        return f"<RssFeed(id={self.id}, title={self.title[:30]}...)>"


# =============================================================================
# WechatAccount 模型
# 职责: 存储微信公众号的配置和运行状态
# 表名: wechat_accounts
# 使用场景: 用户关注微信公众号时创建记录；
#           爬虫调度时查询所有活跃的公众号进行爬取。
# 设计决策:
#   1. account_name 作为唯一标识（微信公众号的 biz ID），设有唯一约束
#   2. display_name 存储公众号的显示名称（可能与 account_name 不同）
#   3. 与 RssFeed 类似，包含 error_count 和 last_fetched_at 用于健康监控
# =============================================================================
class WechatAccount(Base, TimestampMixin):
    """WeChat official account model.

    微信公众号配置模型。
    """

    __tablename__ = "wechat_accounts"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 微信公众号的唯一标识名称（biz ID），设有唯一约束和索引
    account_name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="WeChat account name (biz)",
    )
    # 公众号的显示名称（用于前端展示）
    display_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="",
        comment="Display name of the account",
    )
    # 公众号描述信息
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    # 公众号头像 URL
    avatar_url: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        default="",
    )
    # 是否活跃：False 表示已停用
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    # 最后一次成功抓取的时间
    last_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # 连续抓取失败次数
    error_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    def __repr__(self) -> str:
        """Return a readable WeChat account representation.

        返回微信公众号的字符串表示。
        """
        return f"<WechatAccount(account_name={self.account_name})>"


# =============================================================================
# WeiboHotSearch 模型
# 职责: 存储微博热搜榜单的配置和运行状态
# 表名: weibo_hot_searches
# 使用场景: 配置需要抓取的微博榜单类型；
#           爬虫调度时查询所有活跃的榜单进行爬取。
# 设计决策:
#   1. board_type 作为榜单类型标识（realtimehot, socialevent, entrank, sport, game）
#   2. board_name 存储榜单的中文名称（热搜榜、要闻榜、文娱榜、体育榜、游戏榜）
#   3. 与其他数据源类似，包含 error_count 和 last_fetched_at 用于健康监控
# =============================================================================
class WeiboHotSearch(Base, TimestampMixin):
    """Weibo hot search board model.

    微博热搜榜单配置模型。
    """

    __tablename__ = "weibo_hot_searches"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 榜单类型标识（realtimehot, socialevent, entrank, sport, game）
    board_type: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Board type (e.g., realtimehot, socialevent)",
    )
    # 榜单中文名称
    board_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Board display name in Chinese",
    )
    # 榜单描述信息
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    # 是否活跃：False 表示已停用
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    # 最后一次成功抓取的时间
    last_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # 连续抓取失败次数
    error_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    def __repr__(self) -> str:
        """Return a readable Weibo hot search board representation.

        返回微博热搜榜单的字符串表示。
        """
        return f"<WeiboHotSearch(board_type={self.board_type}, board_name={self.board_name})>"


# =============================================================================
# HackerNewsSource 模型
# 职责: 存储 HackerNews 板块的配置和运行状态
# 表名: hackernews_sources
# 使用场景: 配置需要抓取的 HN 板块类型；
#           爬虫调度时查询所有活跃的板块进行爬取。
# 设计决策:
#   1. feed_type 作为板块类型标识（front, new, best, ask, show）
#   2. feed_name 存储板块的显示名称（首页、最新、精选、Ask HN、Show HN）
#   3. 与其他数据源类似，包含 error_count 和 last_fetched_at 用于健康监控
# =============================================================================
class HackerNewsSource(Base, TimestampMixin):
    """HackerNews feed source model.

    HackerNews 板块配置模型。
    """

    __tablename__ = "hackernews_sources"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 板块类型标识（front, new, best, ask, show）
    feed_type: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Feed type (front, new, best, ask, show)",
    )
    # 板块显示名称
    feed_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Feed display name",
    )
    # 板块描述信息
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    # 是否活跃：False 表示已停用
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    # 最后一次成功抓取的时间
    last_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # 连续抓取失败次数
    error_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    def __repr__(self) -> str:
        """Return a readable HackerNews source representation.

        返回 HackerNews 板块的字符串表示。
        """
        return f"<HackerNewsSource(feed_type={self.feed_type}, feed_name={self.feed_name})>"


# =============================================================================
# RedditSource 模型
# 职责: 存储 Reddit 订阅源的配置和运行状态
# 表名: reddit_sources
# 使用场景: 配置需要抓取的 Subreddit 或 User；
#           爬虫调度时查询所有活跃的订阅源进行爬取。
# 设计决策:
#   1. source_type 区分 "subreddit" 和 "user" 两种订阅类型
#   2. source_name 存储 Subreddit 名称或 Reddit 用户名
#   3. 与其他数据源类似，包含 error_count 和 last_fetched_at 用于健康监控
# =============================================================================
class RedditSource(Base, TimestampMixin):
    """Reddit source model.

    Reddit 订阅源配置模型。
    """

    __tablename__ = "reddit_sources"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 源类型（subreddit 或 user）
    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Source type (subreddit or user)",
    )
    # 源名称（Subreddit 名称或 Reddit 用户名）
    source_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Subreddit name or Reddit username",
    )
    # 显示名称
    display_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="",
        comment="Display name for the source",
    )
    # 描述信息
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    # 是否活跃：False 表示已停用
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    # 最后一次成功抓取的时间
    last_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # 连续抓取失败次数
    error_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # 联合唯一约束：同一类型下的名称不能重复
    __table_args__ = (
        Index("ix_reddit_source_unique", "source_type", "source_name", unique=True),
    )

    def __repr__(self) -> str:
        """Return a readable Reddit source representation.

        返回 Reddit 订阅源的字符串表示。
        """
        return f"<RedditSource(type={self.source_type}, name={self.source_name})>"


# =============================================================================
# TwitterSource 模型
# 职责: 存储 Twitter 用户订阅的配置和运行状态
# 表名: twitter_sources
# 使用场景: 配置需要抓取的 Twitter 用户；
#           爬虫调度时查询所有活跃的用户进行爬取。
# 设计决策:
#   1. username 存储 Twitter 用户名（不含 @）
#   2. last_tweet_id 用于增量抓取，避免重复抓取旧推文
#   3. 与其他数据源类似，包含 error_count 和 last_fetched_at 用于健康监控
# =============================================================================
class TwitterSource(Base, TimestampMixin):
    """Twitter source model.

    Twitter 用户订阅配置模型。
    """

    __tablename__ = "twitter_sources"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Twitter 用户名（不含 @）
    username: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Twitter username (without @)",
    )
    # 显示名称
    display_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="",
        comment="Display name of the user",
    )
    # 描述信息
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    # 是否活跃：False 表示已停用
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    # 最后一次成功抓取的时间
    last_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # 连续抓取失败次数
    error_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    def __repr__(self) -> str:
        """Return a readable Twitter source representation.

        返回 Twitter 订阅源的字符串表示。
        """
        return f"<TwitterSource(username={self.username})>"
