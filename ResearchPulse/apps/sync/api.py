# =============================================================================
# 模块: apps/sync/api.py
# 功能: 跨服务器数据同步接收端 API
# 架构角色: 接收来自 Pipeline 机器的数据同步请求
# =============================================================================

"""Sync receiver API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from .auth import verify_sync_api_key
from .schemas import (
    ArticleSyncRequest,
    ArticleSyncResponse,
    DailyReportSyncRequest,
    DailyReportSyncResponse,
    ReportSyncRequest,
    ReportSyncResponse,
)
from .service import SyncReceiverService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/sync",
    tags=["Sync"],
    dependencies=[Depends(verify_sync_api_key)],
)

receiver_service = SyncReceiverService()


@router.post("/articles", response_model=ArticleSyncResponse)
async def sync_articles(
    request: ArticleSyncRequest,
    db: AsyncSession = Depends(get_session),
) -> ArticleSyncResponse:
    """Batch upsert articles using natural key (source_type, source_id, external_id)."""
    created, updated, id_map = await receiver_service.upsert_articles(
        db, request.articles
    )
    return ArticleSyncResponse(
        synced=created + updated,
        created=created,
        updated=updated,
        id_map=id_map,
    )


@router.post("/daily-reports", response_model=DailyReportSyncResponse)
async def sync_daily_reports(
    request: DailyReportSyncRequest,
    db: AsyncSession = Depends(get_session),
) -> DailyReportSyncResponse:
    """Batch upsert daily reports. Resolves article_ref_keys to local article IDs."""
    created, updated, errors = await receiver_service.upsert_daily_reports(
        db, request.reports
    )
    return DailyReportSyncResponse(
        synced=created + updated,
        created=created,
        updated=updated,
        errors=errors,
    )


@router.post("/reports", response_model=ReportSyncResponse)
async def sync_reports(
    request: ReportSyncRequest,
    db: AsyncSession = Depends(get_session),
) -> ReportSyncResponse:
    """Batch upsert weekly/monthly reports. Resolves username to local user_id."""
    created, updated, skipped, errors = await receiver_service.upsert_reports(
        db, request.reports
    )
    return ReportSyncResponse(
        synced=created + updated,
        created=created,
        updated=updated,
        skipped=skipped,
        errors=errors,
    )
