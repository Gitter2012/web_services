"""Pydantic schemas for cross-server data sync."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


# =============================================================================
# Article Sync
# =============================================================================

class ArticleSyncItem(BaseModel):
    """Single article for sync - uses natural key for identity.

    Uses (source_type, source_id, external_id) as the natural key
    to match articles across different database instances.
    """

    # Natural key fields (required for matching)
    source_type: str
    source_id: str
    external_id: str

    # Core content fields
    title: str = ""
    url: str = ""
    author: str = ""
    summary: str = ""
    translated_title: str | None = None
    content: str = ""
    cover_image_url: str = ""
    category: str = ""

    # News-specific fields
    news_source_country: str | None = None
    news_category: str | None = None
    image_url: str | None = None
    source_crawler_type: str | None = None

    # Tags (JSON array, e.g. ["cs.AI", "cs.LG"])
    tags: list[str] | dict | None = None

    # Time fields
    publish_time: datetime | None = None
    crawl_time: datetime | None = None

    # Archive fields
    is_archived: bool = False
    archived_at: datetime | None = None

    # arXiv-specific fields
    arxiv_id: str | None = None
    arxiv_primary_category: str | None = None
    arxiv_comment: str | None = None
    arxiv_updated_time: datetime | None = None
    arxiv_paper_type: str | None = None

    # WeChat-specific fields
    wechat_account_name: str | None = None
    wechat_digest: str | None = None

    # AI processing result fields
    content_summary: str | None = None
    ai_summary: str | None = None
    ai_category: str | None = None
    ai_subcategory: str | None = None
    importance_score: int | None = None
    one_liner: str | None = None
    key_points: dict | None = None
    impact_assessment: dict | None = None
    actionable_items: dict | None = None
    ai_processed_at: datetime | None = None
    ai_provider: str | None = None
    ai_model: str | None = None
    token_used: int | None = None
    processing_method: str | None = None

    # Social metrics
    read_count: int = 0
    like_count: int = 0


class ArticleSyncRequest(BaseModel):
    articles: list[ArticleSyncItem]


class ArticleSyncResponse(BaseModel):
    synced: int
    created: int
    updated: int
    id_map: dict[str, int] = Field(
        default_factory=dict,
        description='"{source_type}|{source_id}|{external_id}" -> B\'s article.id',
    )


# =============================================================================
# DailyReport Sync
# =============================================================================

class DailyReportSyncItem(BaseModel):
    """Single daily report for sync.

    Uses article_ref_keys (natural key strings) instead of numeric article IDs
    to decouple from the source database's auto-increment IDs.
    """

    report_date: date
    source_type: str
    category: str
    category_name: str
    title: str
    content_markdown: str
    content_wechat: str | None = None
    article_count: int
    # Natural key references: ["arxiv|cs.LG|2301.12345", ...]
    article_ref_keys: list[str] = Field(default_factory=list)
    status: str = "draft"
    published_at: datetime | None = None
    # WeChat push fields (informational only, don't re-push)
    wechat_draft_media_id: str | None = None
    wechat_push_status: str = "pending"
    wechat_push_error: str | None = None
    wechat_pushed_at: datetime | None = None


class DailyReportSyncRequest(BaseModel):
    reports: list[DailyReportSyncItem]


class DailyReportSyncResponse(BaseModel):
    synced: int
    created: int
    updated: int
    errors: list[str] = Field(default_factory=list)


# =============================================================================
# Weekly/Monthly Report Sync
# =============================================================================

class ReportSyncItem(BaseModel):
    """Weekly/monthly report for sync.

    Uses username (natural identifier) instead of user_id
    to resolve across different database instances.
    """

    username: str
    type: str = Field(description='"weekly" or "monthly"')
    period_start: str = Field(description="YYYY-MM-DD")
    period_end: str
    title: str
    content: str
    stats: dict | None = None
    generated_at: datetime | None = None


class ReportSyncRequest(BaseModel):
    reports: list[ReportSyncItem]


class ReportSyncResponse(BaseModel):
    synced: int
    created: int
    updated: int
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)
