# =============================================================================
# 模块: apps/sync/api.py
# 功能: 跨服务器数据同步接收端 API + 手动触发端点
# 架构角色:
#   - router: 接收来自 Pipeline 机器的数据同步请求（机器间通信，API Key 认证）
#   - trigger_router: 供登录用户手动触发同步（用户权限认证）
# =============================================================================

"""Sync receiver API endpoints and manual trigger endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.dependencies import require_permissions
from apps.daily_report.models.daily_report import DailyReport
from .auth import verify_sync_api_key
from .schemas import (
    ArticleSyncRequest,
    ArticleSyncResponse,
    DailyReportSyncRequest,
    DailyReportSyncResponse,
    ReportSyncRequest,
    ReportSyncResponse,
    TriggerReportsSyncRequest,
    TriggerReportsSyncResponse,
)
from .service import SyncReceiverService
from .sender_service import SyncSenderService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 接收端路由：供 Pipeline A 机器调用，使用 API Key 认证
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# 手动触发路由：供登录用户手动触发同步，使用用户权限认证
# ---------------------------------------------------------------------------
trigger_router = APIRouter(
    prefix="/sync",
    tags=["Sync"],
)


@trigger_router.post("/trigger-reports", response_model=TriggerReportsSyncResponse)
async def trigger_reports_sync(
    request: TriggerReportsSyncRequest,
    user=Depends(require_permissions("sync:manual")),
    db: AsyncSession = Depends(get_session),
) -> TriggerReportsSyncResponse:
    """手动触发将 Pipeline A 数据库中指定日期的日报同步到 Display B。

    - 查询本地数据库中指定日期（和可选数据源类型）的报告
    - 调用 SyncSenderService 推送到远端展示服务器
    - 返回同步结果统计
    """
    # 查询本地数据库中指定日期的报告
    stmt = select(DailyReport).where(DailyReport.report_date == request.report_date)
    if request.source_types:
        stmt = stmt.where(DailyReport.source_type.in_(request.source_types))
    result = await db.execute(stmt)
    reports = list(result.scalars().all())

    if not reports:
        logger.info(
            "Manual sync: no reports found for %s (source_types=%s)",
            request.report_date, request.source_types,
        )
        return TriggerReportsSyncResponse(
            report_date=str(request.report_date),
            synced_count=0,
            status="no_reports",
        )

    logger.info(
        "Manual sync triggered by user %s: %d reports for %s",
        getattr(user, "username", user), len(reports), request.report_date,
    )

    try:
        sync_service = SyncSenderService()
        await sync_service.sync_all(request.report_date, reports)
        return TriggerReportsSyncResponse(
            report_date=str(request.report_date),
            synced_count=len(reports),
            status="success",
        )
    except Exception as e:
        logger.error("Manual sync failed for %s: %s", request.report_date, e)
        return TriggerReportsSyncResponse(
            report_date=str(request.report_date),
            synced_count=0,
            status="failed",
            error=str(e),
        )
