# =============================================================================
# 模块: apps/daily_report/api.py
# 功能: 每日 arXiv 报告 API 端点
# 架构角色: 对外接口层，提供报告的生成、查询、导出功能
# =============================================================================
# 路由顺序说明：
#   FastAPI 按定义顺序匹配路由，更具体的路径应放在参数化路径之前。
#   例如：/tasks 必须放在 /{report_id} 之前，否则 "tasks" 会被当作 report_id。
# =============================================================================

"""Daily report API endpoints."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.dependencies import require_permissions
from common.feature_config import require_feature, feature_config
from .schemas import (
    DailyReportResponse,
    DailyReportListResponse,
    DailyReportDetail,
    GenerateReportRequest,
    GenerateReportResponse,
    ExportResponse,
    DailyExportResponse,
    TaskStatusResponse,
    GenerateReportAsyncResponse,
)
from .service import DailyReportService
from apps.task_manager import TaskManager, BackgroundTask

logger = logging.getLogger(__name__)

# 创建 API 路由器
router = APIRouter(
    prefix="/daily-reports",
    tags=["Daily Reports"],
    dependencies=[require_feature("daily_report.enabled")],
)


# ============================================================================
# 任务相关路由（必须在 /{report_id} 之前定义）
# ============================================================================

# --------------------------------------------------------------------------
# GET /daily-reports/tasks - 获取任务列表
# 功能: 获取任务列表（用于页面刷新后恢复状态）
# --------------------------------------------------------------------------
@router.get("/tasks", response_model=list[TaskStatusResponse])
async def list_tasks(
    status: Optional[str] = Query(None, description="筛选状态：pending, running, completed, failed"),
    limit: int = Query(5, ge=1, le=20, description="返回数量限制"),
    user=Depends(require_permissions("daily_report:read")),
):
    """获取任务列表"""
    task_manager = TaskManager()
    tasks = await task_manager.get_tasks_by_type(
        task_type="daily_report",
        status=status,
        limit=limit,
    )

    return [
        TaskStatusResponse(
            task_id=t.task_id,
            task_type=t.task_type,
            name=t.name,
            status=t.status,
            progress=t.progress,
            progress_message=t.progress_message,
            result=t.result,
            error_message=t.error_message,
            created_at=t.created_at,
            started_at=t.started_at,
            completed_at=t.completed_at,
        )
        for t in tasks
    ]


# --------------------------------------------------------------------------
# GET /daily-reports/tasks/{task_id} - 查询任务状态
# 功能: 查询报告生成任务的进度和状态
# --------------------------------------------------------------------------
@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    user=Depends(require_permissions("daily_report:read")),
):
    """查询报告生成任务状态"""
    task_manager = TaskManager()
    task = await task_manager.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskStatusResponse(
        task_id=task.task_id,
        task_type=task.task_type,
        name=task.name,
        status=task.status,
        progress=task.progress,
        progress_message=task.progress_message,
        result=task.result,
        error_message=task.error_message,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
    )


# ============================================================================
# 报告生成路由
# ============================================================================

# --------------------------------------------------------------------------
# POST /daily-reports/generate - 手动触发报告生成（异步）
# 功能: 异步生成指定日期的报告，返回 task_id 供轮询
# --------------------------------------------------------------------------
@router.post("/generate", response_model=GenerateReportAsyncResponse)
async def generate_reports_async(
    request: GenerateReportRequest = GenerateReportRequest(),
    user=Depends(require_permissions("daily_report:generate")),
):
    """手动触发报告生成（异步）

    返回 task_id，前端可轮询 /daily-reports/tasks/{task_id} 查询进度。
    """
    # 确定日期
    if request.report_date is None:
        offset_days = feature_config.get_int("daily_report.report_offset_days", 1)
        report_date = date.today() - timedelta(days=offset_days)
    else:
        report_date = request.report_date

    # 确定分类
    if request.categories is None:
        categories_str = feature_config.get("daily_report.categories", "cs.LG,cs.CV,cs.CL,cs.AI")
        categories = [c.strip() for c in categories_str.split(",") if c.strip()]
    else:
        categories = request.categories

    # 创建任务名称
    category_str = ", ".join(categories) if categories else "全部"
    task_name = f"生成 {report_date} 报告 ({category_str})"

    # 获取任务管理器
    task_manager = TaskManager()

    # 检查是否有相同参数的待处理任务
    existing_task = await task_manager.get_task(
        await _get_existing_task_id("daily_report", report_date, categories)
    ) if await _check_existing_task("daily_report", report_date, categories) else None

    if existing_task and existing_task.status in ["pending", "running"]:
        return GenerateReportAsyncResponse(
            task_id=existing_task.task_id,
            message=f"已有相同任务正在执行中，状态: {existing_task.status}",
            status=existing_task.status,
        )

    # 创建后台任务
    task = await task_manager.create_task(
        task_type="daily_report",
        name=task_name,
        params={
            "report_date": report_date.isoformat(),
            "categories": categories,
        },
        created_by=user.id if hasattr(user, "id") else None,
    )

    # 定义后台执行的协程
    async def run_generate():
        service = DailyReportService()

        # 定义进度更新回调
        async def update_progress(progress: int, message: str):
            await task_manager.update_progress(task.task_id, progress, message)

        reports = await service.generate_daily_reports(
            report_date=report_date,
            categories=categories,
            progress_callback=update_progress,
        )
        return {
            "report_date": report_date.isoformat(),
            "categories": categories,
            "generated_count": len(reports),
            "report_ids": [r.id for r in reports],
        }

    # 启动后台任务
    asyncio.create_task(task_manager.run_in_background(task, run_generate))

    return GenerateReportAsyncResponse(
        task_id=task.task_id,
        message="报告生成任务已启动，请轮询查询进度",
        status="pending",
    )


async def _check_existing_task(task_type: str, report_date: date, categories: list[str]) -> bool:
    """Check if there's an existing pending/running task with same params."""
    from sqlalchemy import select
    from core.database import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        query = select(BackgroundTask).where(
            BackgroundTask.task_type == task_type,
            BackgroundTask.status.in_(["pending", "running"]),
        )
        result = await db.execute(query)
        tasks = result.scalars().all()

        for t in tasks:
            params = t.params or {}
            if (params.get("report_date") == report_date.isoformat() and
                params.get("categories") == categories):
                return True
    return False


async def _get_existing_task_id(task_type: str, report_date: date, categories: list[str]) -> str:
    """Get existing task ID."""
    from sqlalchemy import select
    from core.database import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        query = select(BackgroundTask).where(
            BackgroundTask.task_type == task_type,
            BackgroundTask.status.in_(["pending", "running"]),
        )
        result = await db.execute(query)
        tasks = result.scalars().all()

        for t in tasks:
            params = t.params or {}
            if (params.get("report_date") == report_date.isoformat() and
                params.get("categories") == categories):
                return t.task_id
    return ""


# --------------------------------------------------------------------------
# POST /daily-reports/generate-sync - 手动触发报告生成（同步，已废弃）
# 功能: 同步生成指定日期的报告（不推荐，可能超时）
# --------------------------------------------------------------------------
@router.post("/generate-sync", response_model=GenerateReportResponse)
async def generate_reports_sync(
    request: GenerateReportRequest = GenerateReportRequest(),
    user=Depends(require_permissions("daily_report:generate")),
):
    """手动触发报告生成（同步模式，已废弃，请使用 /generate）"""
    service = DailyReportService()

    try:
        reports = await service.generate_daily_reports(
            report_date=request.report_date,
            categories=request.categories,
        )

        return GenerateReportResponse(
            success=True,
            message=f"成功生成 {len(reports)} 份报告",
            reports=[DailyReportResponse.model_validate(r) for r in reports],
        )

    except Exception as e:
        logger.error(f"Failed to generate reports: {e}")
        return GenerateReportResponse(
            success=False,
            message=f"报告生成失败: {str(e)}",
            errors=[str(e)],
        )


# ============================================================================
# 导出路由
# ============================================================================

# --------------------------------------------------------------------------
# GET /daily-reports/export-daily - 导出一天所有报告
# 功能: 导出指定日期所有分类的报告（合并版）
# --------------------------------------------------------------------------
@router.get("/export-daily", response_model=DailyExportResponse)
async def export_daily(
    report_date: date = Query(..., description="报告日期"),
    format: str = Query("wechat", description="导出格式: markdown 或 wechat"),
    user=Depends(require_permissions("daily_report:export")),
    db: AsyncSession = Depends(get_session),
):
    """导出一天所有分类的报告（合并版）"""
    service = DailyReportService()
    result = await service.export_daily(db, report_date, format)

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No reports found for {report_date}",
        )

    return DailyExportResponse(
        report_date=result["report_date"],
        format=result["format"],
        total_articles=result["total_articles"],
        categories=result["categories"],
        content=result["content"],
        reports=[DailyReportResponse.model_validate(r) for r in result["reports"]],
    )


# ============================================================================
# 报告查询路由（参数化路由，放在最后）
# ============================================================================

# --------------------------------------------------------------------------
# GET /daily-reports - 获取报告列表
# 功能: 查询每日报告列表，支持按日期、分类、状态筛选
# --------------------------------------------------------------------------
@router.get("", response_model=DailyReportListResponse)
async def list_reports(
    report_date: Optional[date] = Query(None, description="报告日期"),
    category: Optional[str] = Query(None, description="arXiv 分类代码"),
    status: Optional[str] = Query(None, description="报告状态"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    user=Depends(require_permissions("daily_report:read")),
    db: AsyncSession = Depends(get_session),
):
    """获取每日报告列表"""
    service = DailyReportService()
    reports, total = await service.list_reports(
        db,
        report_date=report_date,
        category=category,
        status=status,
        page=page,
        page_size=page_size,
    )

    return DailyReportListResponse(
        total=total,
        page=page,
        page_size=page_size,
        reports=[DailyReportResponse.model_validate(r) for r in reports],
    )


# --------------------------------------------------------------------------
# GET /daily-reports/{report_id} - 获取单个报告详情
# 功能: 根据报告 ID 查询报告的完整内容
# --------------------------------------------------------------------------
@router.get("/{report_id}", response_model=DailyReportDetail)
async def get_report(
    report_id: int,
    user=Depends(require_permissions("daily_report:read")),
    db: AsyncSession = Depends(get_session),
):
    """获取报告详情"""
    service = DailyReportService()
    report = await service.get_report_by_id(db, report_id)

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return DailyReportDetail.model_validate(report)


# --------------------------------------------------------------------------
# GET /daily-reports/{report_id}/export - 导出报告
# 功能: 导出报告为指定格式（markdown 或 wechat）
# --------------------------------------------------------------------------
@router.get("/{report_id}/export", response_model=ExportResponse)
async def export_report(
    report_id: int,
    format: str = Query("markdown", description="导出格式: markdown 或 wechat"),
    user=Depends(require_permissions("daily_report:export")),
    db: AsyncSession = Depends(get_session),
):
    """导出报告"""
    service = DailyReportService()
    result = await service.export_report(db, report_id, format)

    if not result:
        raise HTTPException(status_code=404, detail="Report not found")

    return ExportResponse(**result)
