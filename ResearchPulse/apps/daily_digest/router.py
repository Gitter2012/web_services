# =============================================================================
# 模块: apps/daily_digest/router.py
# 功能: 每日精选日报 API 端点
# 架构角色: 接口层，提供便利端点；大量复用现有 daily_report API
#
# 端点（前缀 /researchpulse/api/digest）：
#   GET  /today                → 获取今日全量精选（category=all）
#   GET  /                     → 列出某日所有分类的精选日报
#   POST /generate             → 触发生成（管理员，后台异步）
#   GET  /status/{date}        → 查询某日所有分类的生成状态
#   GET  /{report_date}/{cat}  → 获取指定日期+分类的精选日报
# =============================================================================

"""Daily digest API endpoints."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.dependencies import get_superuser, require_permissions
from common.feature_config import require_feature, feature_config

from .service import DailyDigestService, DIGEST_CATEGORY_ALL

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/digest",
    tags=["Daily Digest"],
    dependencies=[require_feature("daily_digest.enabled")],
)


# --------------------------------------------------------------------------
# GET /digest/today — 获取今日全量精选日报（category=all）
# --------------------------------------------------------------------------
@router.get("/today")
async def get_today_digest(
    category: str = Query(DIGEST_CATEGORY_ALL, description="精选分类，默认 all（全量聚合）"),
    db: AsyncSession = Depends(get_session),
    user=Depends(require_permissions("daily_report:read")),
):
    """获取今日精选日报。

    默认返回全量聚合精选（category=all），可通过 category 参数获取
    指定分类精选（如 AI / 金融 / 技术）。
    若今天尚未生成则回退到昨天。
    """
    today = date.today()
    service = DailyDigestService()
    report = await service.get_digest(db, today, category)

    if not report:
        yesterday = today - timedelta(days=1)
        report = await service.get_digest(db, yesterday, category)

    if not report:
        raise HTTPException(
            status_code=404,
            detail=f"精选日报（category={category}）尚未生成，请通过 POST /digest/generate 触发",
        )

    return _report_to_dict(report)


# --------------------------------------------------------------------------
# GET /digest/ — 列出某日所有分类的精选日报摘要
# --------------------------------------------------------------------------
@router.get("/")
async def list_digests(
    report_date: Optional[date] = Query(None, description="日报日期，默认今天"),
    db: AsyncSession = Depends(get_session),
    user=Depends(require_permissions("daily_report:read")),
):
    """列出指定日期所有已生成的精选分类日报。

    返回该日期下 source_type="digest" 的所有分类摘要列表。
    """
    if report_date is None:
        report_date = date.today()

    service = DailyDigestService()
    reports = await service.list_digests_by_date(db, report_date)

    return {
        "date": str(report_date),
        "count": len(reports),
        "digests": [_report_to_summary(r) for r in reports],
    }


# --------------------------------------------------------------------------
# GET /digest/{report_date}/{category} — 获取指定日期+分类的精选日报
# --------------------------------------------------------------------------
@router.get("/{report_date}/{category}")
async def get_digest_by_date_category(
    report_date: date,
    category: str,
    db: AsyncSession = Depends(get_session),
    user=Depends(require_permissions("daily_report:read")),
):
    """获取指定日期、指定分类的精选日报。

    Args:
        report_date: 日报日期（如 2026-03-23）。
        category: 精选分类（如 all / AI / 金融 / 技术）。
    """
    service = DailyDigestService()
    report = await service.get_digest(db, report_date, category)

    if not report:
        raise HTTPException(
            status_code=404,
            detail=f"精选日报不存在：date={report_date}, category={category}",
        )

    return _report_to_dict(report)


# --------------------------------------------------------------------------
# POST /digest/generate — 触发生成（管理员权限，后台异步）
# --------------------------------------------------------------------------
@router.post("/generate")
async def generate_digest(
    report_date: Optional[date] = Query(None, description="日报日期，默认今天"),
    category: Optional[str] = Query(
        None,
        description="精选分类。不传则按配置 daily_digest.categories 生成所有分类；"
                    "传入 all/AI/金融/技术 则只生成该分类。"
    ),
    force: bool = Query(False, description="是否强制重新生成（覆盖已有日报）"),
    user=Depends(get_superuser),
):
    """触发每日精选日报生成（管理员权限，后台异步执行）。

    - 不传 category：按 daily_digest.categories 配置生成所有分类（如 all/AI/金融/技术）
    - 传入 category：只生成该分类
    - report_date 默认今天，可传入历史日期补生成
    """
    if report_date is None:
        report_date = date.today()

    date_str = str(report_date)
    logger.info(
        "Digest generation triggered: user=%s, date=%s, category=%s, force=%s",
        getattr(user, "id", "?"), date_str, category, force,
    )

    async def _run():
        service = DailyDigestService()
        try:
            if category is not None:
                # 只生成指定分类
                top_n = feature_config.get_int("daily_digest.top_n", 25)
                await service.generate_digest(
                    report_date=report_date,
                    category=category,
                    force=force,
                    top_n=top_n,
                )
                logger.info("Single-category digest [%s] completed for %s", category, date_str)
            else:
                # 生成所有配置分类
                await service.generate_multi_digests(
                    report_date=report_date,
                    force=force,
                )
                logger.info("Multi-category digest completed for %s", date_str)
        except Exception as e:
            logger.error("Digest generation failed for %s: %s", date_str, e, exc_info=True)

    asyncio.create_task(_run())

    return {
        "message": (
            f"精选日报生成任务已启动（{date_str}，category={category or '全部配置分类'}，force={force}）"
        ),
        "report_date": date_str,
        "category": category,
        "force": force,
        "status": "queued",
    }


# --------------------------------------------------------------------------
# GET /digest/status/{date} — 查询某日所有分类生成状态
# --------------------------------------------------------------------------
@router.get("/status/{report_date}")
async def get_digest_status(
    report_date: date,
    category: Optional[str] = Query(None, description="不传则返回该日期所有分类的状态"),
    db: AsyncSession = Depends(get_session),
    user=Depends(require_permissions("daily_report:read")),
):
    """查询指定日期精选日报的生成状态。

    - 不传 category：返回该日期所有分类的状态列表。
    - 传入 category：返回该分类的单条状态。
    """
    service = DailyDigestService()
    if category is not None:
        return await service.get_status(db, report_date, category)
    return {
        "date": str(report_date),
        "categories": await service.list_status_by_date(db, report_date),
    }


# --------------------------------------------------------------------------
# 辅助函数
# --------------------------------------------------------------------------

def _report_to_dict(report) -> dict:
    """DailyReport → 完整响应字典（含内容）。"""
    return {
        "id": report.id,
        "report_date": str(report.report_date),
        "category": report.category,
        "category_name": report.category_name,
        "title": report.title,
        "status": report.status,
        "article_count": report.article_count,
        "content_markdown": report.content_markdown,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


def _report_to_summary(report) -> dict:
    """DailyReport → 摘要响应字典（不含内容）。"""
    return {
        "id": report.id,
        "report_date": str(report.report_date),
        "category": report.category,
        "category_name": report.category_name,
        "title": report.title,
        "status": report.status,
        "article_count": report.article_count,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }
