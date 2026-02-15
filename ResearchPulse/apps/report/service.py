# ==============================================================================
# 模块: report/service.py
# 功能: 报告模块的业务逻辑服务层 (Service 层)
# 架构角色: 位于 API 层和数据访问层之间, 封装报告相关的所有业务操作。
#           负责报告的 CRUD 操作和周报/月报的生成逻辑。
# 设计说明:
#   - ReportService 类聚合了报告的查询、生成和删除功能
#   - 报告生成过程分为两步: 先收集数据 (generate_report_data), 再格式化 (format_report_markdown)
#   - 周报和月报的主要区别在于时间范围的计算方式
#   - 所有数据库操作通过传入的 AsyncSession 完成, 由调用方管理事务
# ==============================================================================
"""Report service."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Report
from .generator import format_report_markdown, generate_report_data

# 初始化模块级日志记录器
logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# ReportService - 报告业务服务类
# 职责: 提供报告的查询、生成和删除等核心业务操作
# 设计决策:
#   - 采用无状态设计, 每次请求创建新实例
#   - 报告数据收集和格式化逻辑委托给 generator.py 模块
#   - 周报和月报共用相同的数据收集逻辑, 仅时间范围不同
# --------------------------------------------------------------------------
class ReportService:
    """Service class for report operations.

    报告业务逻辑服务类，提供报告查询、生成与删除功能。
    """

    # ----------------------------------------------------------------------
    # list_reports - 查询用户的报告列表
    # 参数:
    #   - user_id: 用户 ID
    #   - db: 异步数据库会话
    #   - limit: 返回数量上限, 默认 20
    # 返回: (报告列表, 总数) 的元组
    # 逻辑: 先统计总数, 再按生成时间倒序获取指定数量的报告
    # ----------------------------------------------------------------------
    async def list_reports(
        self, user_id: int, db: AsyncSession, limit: int = 20
    ) -> tuple[list[Report], int]:
        """List reports for a user.

        查询用户报告列表并返回总数。

        Args:
            user_id: Owner user ID.
            db: Async database session.
            limit: Max number of reports to return.

        Returns:
            tuple[list[Report], int]: (reports, total_count).
        """
        # 统计该用户的报告总数
        count_result = await db.execute(
            select(func.count())
            .select_from(Report)
            .where(Report.user_id == user_id)
        )
        total = count_result.scalar() or 0
        # 按生成时间倒序排列, 最新的报告排在前面
        result = await db.execute(
            select(Report)
            .where(Report.user_id == user_id)
            .order_by(Report.generated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all()), total

    # ----------------------------------------------------------------------
    # get_report - 根据 ID 获取单个报告
    # 参数:
    #   - report_id: 报告 ID
    #   - db: 异步数据库会话
    # 返回: Report 对象, 若不存在则返回 None
    # ----------------------------------------------------------------------
    async def get_report(
        self, report_id: int, db: AsyncSession
    ) -> Report | None:
        """Get a report by ID.

        根据报告 ID 获取报告详情。

        Args:
            report_id: Report ID.
            db: Async database session.

        Returns:
            Report | None: Report instance or ``None`` if not found.
        """
        result = await db.execute(
            select(Report).where(Report.id == report_id)
        )
        return result.scalar_one_or_none()

    # ----------------------------------------------------------------------
    # generate_weekly - 生成周报
    # 参数:
    #   - user_id: 用户 ID
    #   - db: 异步数据库会话
    #   - weeks_ago: 回溯周数, 0=本周, 1=上周, 以此类推
    # 返回: 新生成的 Report 对象
    # 副作用: 向数据库插入一条新的报告记录
    #
    # 时间计算逻辑:
    #   1. 获取当前 UTC 时间
    #   2. 计算目标周的周一: 当前日期 - 当前星期几 - (weeks_ago * 7)
    #   3. 周开始时间设为周一 00:00:00
    #   4. 周结束时间设为周日 23:59:59 (即开始时间 + 6天23小时59分59秒)
    # ----------------------------------------------------------------------
    async def generate_weekly(
        self, user_id: int, db: AsyncSession, weeks_ago: int = 0
    ) -> Report:
        """Generate a weekly report.

        生成指定周的周报并保存到数据库。

        Args:
            user_id: Owner user ID.
            db: Async database session.
            weeks_ago: Weeks to look back (0 = current week).

        Returns:
            Report: Newly generated report.
        """
        today = datetime.now(timezone.utc)
        # 计算目标周的周一 (weekday() 返回 0=周一, 6=周日)
        start = today - timedelta(days=today.weekday() + 7 * weeks_ago)
        # 将时间归零到当天 00:00:00
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        # 周结束时间: 周日 23:59:59
        end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)

        # 收集该时间范围内的报告数据
        data = await generate_report_data(db, start, end)
        # 将数据格式化为 Markdown 内容
        content = format_report_markdown(
            "weekly",
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
            data,
        )

        # 创建报告记录
        report = Report(
            user_id=user_id,
            type="weekly",
            period_start=start.strftime("%Y-%m-%d"),
            period_end=end.strftime("%Y-%m-%d"),
            title=f"周报 {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}",  # 自动生成标题
            content=content,  # Markdown 格式的报告正文
            stats=data,  # JSON 格式的统计数据
            generated_at=datetime.now(timezone.utc),
        )
        db.add(report)
        await db.flush()  # 刷新到数据库以获取自增主键 ID
        await db.refresh(report)  # 刷新对象以获取数据库生成的默认值
        return report

    # ----------------------------------------------------------------------
    # generate_monthly - 生成月报
    # 参数:
    #   - user_id: 用户 ID
    #   - db: 异步数据库会话
    #   - months_ago: 回溯月数, 0=本月, 1=上月, 以此类推
    # 返回: 新生成的 Report 对象
    # 副作用: 向数据库插入一条新的报告记录
    #
    # 时间计算逻辑:
    #   1. 从当前月份减去 months_ago 得到目标月份
    #   2. 如果月份 <= 0, 则回退到上一年 (循环处理)
    #   3. 月开始: 目标月份的第 1 天 00:00:00
    #   4. 月结束: 下一个月第 1 天 00:00:00 减去 1 秒 (即目标月份最后一天 23:59:59)
    # 设计说明: 使用 "下月第一天减1秒" 的方式避免了手动计算每月天数的复杂性
    # ----------------------------------------------------------------------
    async def generate_monthly(
        self, user_id: int, db: AsyncSession, months_ago: int = 0
    ) -> Report:
        """Generate a monthly report.

        生成指定月份的月报并保存到数据库。

        Args:
            user_id: Owner user ID.
            db: Async database session.
            months_ago: Months to look back (0 = current month).

        Returns:
            Report: Newly generated report.
        """
        today = datetime.now(timezone.utc)
        month = today.month - months_ago
        year = today.year
        # 处理跨年情况: 如果月份 <= 0, 回退到上一年
        while month <= 0:
            month += 12
            year -= 1

        # 月开始时间: 目标月份的第 1 天
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        # 月结束时间: 下个月第 1 天减去 1 秒
        if month == 12:
            # 12 月的下个月是次年 1 月
            end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(
                seconds=1
            )
        else:
            end = datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(
                seconds=1
            )

        # 收集该时间范围内的报告数据
        data = await generate_report_data(db, start, end)
        # 将数据格式化为 Markdown 内容
        content = format_report_markdown(
            "monthly",
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
            data,
        )

        # 创建报告记录
        report = Report(
            user_id=user_id,
            type="monthly",
            period_start=start.strftime("%Y-%m-%d"),
            period_end=end.strftime("%Y-%m-%d"),
            title=f"月报 {start.strftime('%Y年%m月')}",  # 自动生成中文月报标题
            content=content,
            stats=data,
            generated_at=datetime.now(timezone.utc),
        )
        db.add(report)
        await db.flush()  # 刷新到数据库以获取自增主键 ID
        await db.refresh(report)  # 刷新对象以获取数据库生成的默认值
        return report

    # ----------------------------------------------------------------------
    # delete_report - 删除报告
    # 参数:
    #   - report_id: 报告 ID
    #   - db: 异步数据库会话
    # 返回: 删除成功返回 True, 报告不存在返回 False
    # ----------------------------------------------------------------------
    async def delete_report(self, report_id: int, db: AsyncSession) -> bool:
        """Delete a report by ID.

        删除指定报告记录。

        Args:
            report_id: Report ID.
            db: Async database session.

        Returns:
            bool: ``True`` if deleted, otherwise ``False``.
        """
        report = await self.get_report(report_id, db)
        if not report:
            return False
        await db.delete(report)
        return True
