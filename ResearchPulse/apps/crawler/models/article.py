# =============================================================================
# 模块: apps/crawler/models/article.py
# 功能: 文章数据模型定义
# 架构角色: 数据持久化层的核心模型，定义了统一的文章数据结构。
#           所有爬虫（arXiv、RSS、微信公众号）爬取的内容最终都存储为 Article 记录。
#           同时定义了 UserArticleState 模型，用于追踪用户对文章的阅读和收藏状态。
# 设计决策:
#   1. 统一模型: 所有来源的文章使用同一张表，通过 source_type 区分来源类型，
#      避免为每种来源创建独立表导致查询和聚合逻辑复杂化。
#   2. 扩展字段: 不同来源的特有字段（如 arxiv_id、wechat_account_name）
#      作为可空字段存储在同一张表中。虽然会有部分空间浪费，但大幅简化了数据查询逻辑。
#   3. AI 处理字段: 文章表中集成了 AI 摘要、分类、评分等字段，
#      支持后续的 AI 处理流水线将结果直接回写到文章记录中。
# =============================================================================

"""Article models for ResearchPulse v2."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin


# =============================================================================
# Article 模型
# 职责: 表示一篇来自任意数据源的文章/论文
# 表名: articles
# 去重机制: 通过唯一索引 (source_type, source_id, external_id) 确保同一来源
#           的同一篇文章不会被重复插入。
# 字段分组:
#   - 通用字段: id, source_type, source_id, external_id, title, url, author, ...
#   - arXiv 专用: arxiv_id, arxiv_primary_category, arxiv_comment, arxiv_updated_time
#   - 微信专用: wechat_account_name, wechat_digest
#   - AI 处理结果: ai_summary, ai_category, importance_score, key_points, ...
#   - 社交指标: read_count, like_count
# =============================================================================
class Article(Base, TimestampMixin):
    """Unified article model for all sources (arxiv, rss, wechat).

    统一文章数据模型，覆盖多来源字段与 AI 处理结果。
    """

    __tablename__ = "articles"

    # ---- 主键 ----
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # ---- 来源标识字段 ----
    # source_type + source_id + external_id 构成唯一约束，用于去重
    source_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Source type: arxiv, rss, wechat",
    )
    source_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="ID of the source (category code, feed id, account id)",
    )
    # 来自数据源的外部唯一标识（如 arXiv ID、RSS GUID、微信 sn 参数等）
    external_id: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
        comment="External ID from source (arxiv_id, article GUID, etc)",
    )

    # ---- 文章核心内容字段 ----
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="",
    )
    url: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        default="",
    )
    author: Mapped[str] = mapped_column(
        String(1000),  # 扩展到 1000 字符以支持多作者论文
        nullable=False,
        default="",
    )
    # 文章摘要（简短描述）
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    # 文章正文内容（完整内容或 HTML）
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    # 封面图片 URL（对于 arXiv 论文，此字段复用为 PDF 下载链接）
    cover_image_url: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        default="",
    )
    # 文章分类（如 arXiv 的 cs.AI，RSS 文章的自定义分类等）
    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        index=True,
    )
    # 标签列表，以 JSON 数组形式存储（如 ["cs.AI", "cs.LG"]）
    tags: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="JSON array of tags",
    )

    # ---- 时间相关字段 ----
    # 文章在原始来源的发布时间
    publish_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        # NOTE: index defined in __table_args__ as ix_articles_publish_time
    )
    # 爬虫抓取此文章的时间
    crawl_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        # NOTE: index defined in __table_args__ as ix_articles_crawl_time
    )

    # ---- 归档相关字段 ----
    # 用于数据生命周期管理，过期文章可标记为归档
    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        # NOTE: index defined in __table_args__ as ix_articles_archived
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ---- arXiv 专用字段 ----
    # 这些字段仅在 source_type='arxiv' 时有值
    # Additional fields for specific sources
    # arxiv specific
    arxiv_id: Mapped[str] = mapped_column(
        String(50),
        nullable=True,
        comment="arXiv paper ID",
    )
    arxiv_primary_category: Mapped[str] = mapped_column(
        String(200),
        nullable=True,
        comment="arXiv primary category",
    )
    arxiv_comment: Mapped[str] = mapped_column(
        Text,
        nullable=True,
        comment="arXiv comment field",
    )
    arxiv_updated_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="arXiv updated time",
    )

    # ---- 微信公众号专用字段 ----
    # 这些字段仅在 source_type='wechat' 时有值
    # wechat specific
    wechat_account_name: Mapped[str] = mapped_column(
        String(200),
        nullable=True,
        comment="WeChat account name",
    )
    wechat_digest: Mapped[str] = mapped_column(
        Text,
        nullable=True,
        comment="WeChat article digest",
    )

    # ---- AI 处理结果字段 ----
    # 以下字段由 AI 处理流水线填充，用于智能摘要、分类和评估

    # AI 生成的内容摘要或翻译后的摘要
    # AI-generated summary or translated abstract
    content_summary: Mapped[str] = mapped_column(
        Text,
        nullable=True,
        comment="AI summary or translated abstract",
    )

    # AI 生成的中文摘要
    # AI processing results
    ai_summary: Mapped[str] = mapped_column(
        Text,
        nullable=True,
        comment="AI-generated Chinese summary",
    )
    # AI 自动分类结果
    ai_category: Mapped[str] = mapped_column(
        String(50),
        nullable=True,
        comment="AI classification: AI, 机器学习, 编程, 技术, 创业, 创新, 金融, 研究, 设计, 其他",
    )
    # AI 评估的重要性评分（1-10 分）
    importance_score: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="AI importance score 1-10",
    )
    # 一句话结论：帮助读者快速判断文章是否值得深入阅读
    one_liner: Mapped[str] = mapped_column(
        String(500),
        nullable=True,
        comment="One-line conclusion for the reader",
    )
    # 关键要点列表，JSON 格式：[{type, value, impact}, ...]
    key_points: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Key points: [{type, value, impact}]",
    )
    # 影响力评估，JSON 格式：{short_term, long_term, certainty}
    impact_assessment: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Impact: {short_term, long_term, certainty}",
    )
    # 可执行建议列表，JSON 格式：[{type, description, priority}, ...]
    actionable_items: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Actions: [{type, description, priority}]",
    )
    # AI 处理完成时间
    ai_processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When AI processing was completed",
    )
    # AI 服务提供商标识
    ai_provider: Mapped[str] = mapped_column(
        String(50),
        nullable=True,
        comment="AI provider: ollama, openai, claude",
    )
    # 具体使用的模型名称
    ai_model: Mapped[str] = mapped_column(
        String(100),
        nullable=True,
        comment="Specific model name used",
    )
    # 处理此文章消耗的 token 数量（用于成本追踪）
    token_used: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Token consumption for this article",
    )
    # 处理方式标识：ai（AI处理）、rule（规则匹配）、cached（缓存命中）、screen（筛选）
    processing_method: Mapped[str] = mapped_column(
        String(20),
        nullable=True,
        comment="Processing method: ai, rule, cached, screen",
    )

    # ---- 社交互动指标 ----
    # 主要用于微信公众号文章
    read_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Read count for WeChat articles",
    )
    like_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Like count for WeChat articles",
    )

    # ---- 数据库索引定义 ----
    # 通过联合索引优化常见查询场景
    __table_args__ = (
        # 三元组唯一索引：确保同一来源的同一篇文章不会重复插入
        Index("ix_articles_source_external", "source_type", "source_id", "external_id", unique=True),
        # 发布时间索引：支持按时间排序和范围查询
        Index("ix_articles_publish_time", "publish_time"),
        # 爬取时间索引：支持查询最近爬取的文章
        Index("ix_articles_crawl_time", "crawl_time"),
        # 归档状态索引：支持过滤已归档/未归档的文章
        Index("ix_articles_archived", "is_archived"),
    )

    def __repr__(self) -> str:
        """Return a readable article representation.

        返回文章对象的字符串表示，用于调试和日志输出。
        """
        return f"<Article(id={self.id}, title={self.title[:30]}...)>"


# =============================================================================
# UserArticleState 模型
# 职责: 追踪用户对文章的个人交互状态（已读/收藏）
# 表名: user_article_states
# 设计决策:
#   1. 将用户状态与文章数据分离，避免修改文章主表的频率过高
#   2. (user_id, article_id) 组成唯一约束，确保每个用户对每篇文章只有一条状态记录
#   3. 提供 mark_read() 和 toggle_star() 便捷方法封装状态变更逻辑
# =============================================================================
class UserArticleState(Base, TimestampMixin):
    """User's reading state for articles.

    追踪用户对文章的已读/收藏状态。
    """

    __tablename__ = "user_article_states"

    # ---- 主键 ----
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # ---- 关联字段 ----
    # 用户ID，关联 users 表，用户删除时级联删除其所有状态记录
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 文章ID，关联 articles 表，文章删除时级联删除相关状态记录
    article_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ---- 状态字段 ----
    # 是否已读
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    # 是否已收藏
    is_starred: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    # 标记为已读的时间
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # 收藏/取消收藏的时间
    starred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ---- 唯一约束 ----
    # 确保每个用户对每篇文章只有一条状态记录
    __table_args__ = (
        Index("ix_user_article_unique", "user_id", "article_id", unique=True),
    )

    def mark_read(self) -> None:
        """Mark the article as read.

        将文章标记为已读。

        Side Effects:
            - Sets ``is_read`` to True.
            - Updates ``read_at`` to current UTC time.
        """
        self.is_read = True
        self.read_at = datetime.now(timezone.utc)

    def toggle_star(self) -> bool:
        """Toggle article star status.

        切换文章的收藏状态（已收藏 -> 取消收藏，未收藏 -> 收藏）。

        Side Effects:
            - Toggles ``is_starred``.
            - Updates ``starred_at`` when starred, clears when unstarred.

        Returns:
            bool: New starred status (True if starred).
        """
        self.is_starred = not self.is_starred
        if self.is_starred:
            self.starred_at = datetime.now(timezone.utc)
        else:
            # 取消收藏时清除收藏时间
            self.starred_at = None
        return self.is_starred

    def __repr__(self) -> str:
        """Return a readable user-article state representation.

        返回用户文章状态对象的字符串表示。
        """
        return f"<UserArticleState(user_id={self.user_id}, article_id={self.article_id})>"
