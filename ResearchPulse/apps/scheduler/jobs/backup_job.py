# ==============================================================================
# 模块: ResearchPulse 数据备份定时任务
# 作用: 本模块负责在物理删除过期文章之前，将其导出为 JSON 备份文件，
#       随后记录备份信息并执行物理删除，确保数据不会因清理而永久丢失。
# 架构角色: 数据生命周期管理的第二环（承接 cleanup_job 的归档操作）。
#           cleanup_job 负责归档标记 -> backup_job 负责备份并物理删除。
# 设计思路: 遵循"先备份后删除"原则，备份文件以 JSON 格式存储，包含完整的文章元数据和内容，
#           便于后续需要时进行数据恢复。同时在数据库中记录备份元信息（BackupRecord），
#           形成可追溯的备份历史。
# 执行方式: 由 APScheduler 的 CronTrigger 每天定时触发，通常安排在清理任务之后。
# ==============================================================================

"""Backup job for ResearchPulse v2."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from core.database import get_session_factory
# Article: 文章数据模型; BackupRecord: 备份记录模型，用于追踪备份历史
from apps.crawler.models import Article, BackupRecord
from settings import settings

logger = logging.getLogger(__name__)


async def run_backup_job() -> dict:
    """Back up and delete expired articles.

    备份超过归档期限的文章，记录备份信息并执行物理删除。

    Returns:
        dict: Backup summary including counts, file path, and status.
    """
    # 功能: 查找超过归档期限的文章，导出为 JSON 备份文件，记录备份信息，然后物理删除这些文章
    # 参数: 无（归档天数、备份目录等配置从 settings 中读取）
    # 返回值: dict - 包含备份任务的执行统计（备份文章数、删除数、备份文件路径、文件大小等）
    # 副作用:
    #   1. 文件系统: 创建 JSON 备份文件到指定目录
    #   2. 数据库写入: 新增 BackupRecord 记录
    #   3. 数据库删除: 物理删除已备份的文章记录

    # 前置检查: 如果备份功能在配置中被禁用，则直接跳过
    if not settings.backup_enabled:
        logger.info("Backup is disabled, skipping")
        return {"status": "skipped", "reason": "backup_disabled"}

    logger.info("Starting backup job")
    start_time = datetime.now(timezone.utc)

    # 计算删除阈值: 爬取时间早于此阈值的文章将被备份后删除
    # data_archive_days 定义了文章在数据库中的最长保留天数
    delete_threshold = datetime.now(timezone.utc) - timedelta(days=settings.data_archive_days)

    # 初始化结果统计
    results = {
        "backed_up": 0,      # 备份的文章数量
        "deleted": 0,        # 删除的文章数量
        "backup_file": None, # 备份文件的路径
        "errors": [],        # 备份过程中的错误列表
    }

    session_factory = get_session_factory()
    async with session_factory() as session:
        # ---- 第一步: 查询待删除的文章 ----
        # 筛选条件: 爬取时间早于删除阈值的所有文章
        # Find articles to delete
        result = await session.execute(
            select(Article).where(Article.crawl_time < delete_threshold)
        )
        articles = result.scalars().all()

        # 如果没有需要备份的文章，提前返回
        if not articles:
            logger.info("No articles to backup")
            return {
                "status": "completed",
                "backed_up": 0,
                "deleted": 0,
            }

        # ---- 第二步: 准备备份目录 ----
        # 如果配置的备份目录是相对路径，则将其转换为基于 data_dir 的绝对路径
        # Create backup directory
        backup_dir = settings.backup_dir
        if not backup_dir.is_absolute():
            backup_dir = settings.data_dir / backup_dir
        # 递归创建目录，exist_ok=True 避免目录已存在时抛出异常
        backup_dir.mkdir(parents=True, exist_ok=True)

        # ---- 第三步: 创建备份文件 ----
        # 使用时间戳作为文件名的一部分，确保每次备份生成唯一的文件名
        # Create backup file
        backup_date = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"articles_{backup_date}.json"

        # ---- 第四步: 将文章数据序列化为字典列表 ----
        # 提取文章的所有关键字段，时间字段转换为 ISO 格式字符串以保证可序列化
        # Export articles
        articles_data = []
        for article in articles:
            articles_data.append({
                "id": article.id,
                "source_type": article.source_type,       # 数据来源类型（arxiv/rss/wechat）
                "source_id": article.source_id,           # 数据源 ID
                "external_id": article.external_id,       # 外部系统中的唯一标识
                "title": article.title,
                "url": article.url,
                "author": article.author,
                "summary": article.summary,
                "content": article.content,
                "category": article.category,
                "tags": article.tags,
                # 时间字段使用 ISO 格式序列化，None 值保持为 None
                "publish_time": article.publish_time.isoformat() if article.publish_time else None,
                "crawl_time": article.crawl_time.isoformat() if article.crawl_time else None,
            })

        # ---- 第五步: 写入 JSON 备份文件 ----
        # ensure_ascii=False: 保留中文等非 ASCII 字符的原始形式，提高可读性
        # indent=2: 格式化输出，便于人工查阅和排查问题
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump({
                "backup_date": backup_date,
                "article_count": len(articles_data),
                "articles": articles_data,
            }, f, ensure_ascii=False, indent=2)

        results["backed_up"] = len(articles_data)
        results["backup_file"] = str(backup_file)
        # 获取备份文件大小（字节），用于备份记录和监控
        backup_size = backup_file.stat().st_size

        # ---- 第六步: 在数据库中记录备份信息 ----
        # BackupRecord 提供备份历史的可追溯性，便于后续查询和数据恢复
        # Record backup
        backup_record = BackupRecord(
            backup_date=datetime.now(timezone.utc),
            backup_file=str(backup_file),
            backup_size=backup_size,
            article_count=len(articles_data),
            status="completed",
            completed_at=datetime.now(timezone.utc),
        )
        session.add(backup_record)

        # ---- 第七步: 物理删除已备份的文章 ----
        # 逐条删除文章记录（而非批量 DELETE 语句），
        # 这样做可以触发 ORM 级别的级联删除和事件钩子
        # Delete articles
        for article in articles:
            await session.delete(article)

        results["deleted"] = len(articles)

        # 提交事务: 备份记录的写入和文章的删除在同一个事务中完成，
        # 确保原子性 —— 要么全部成功，要么全部回滚
        await session.commit()

    # 生成任务执行摘要
    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    summary = {
        "status": "completed",
        "duration_seconds": duration,
        "articles_backed_up": results["backed_up"],
        "articles_deleted": results["deleted"],
        "backup_file": results["backup_file"],
        "backup_size_bytes": backup_size,
        "timestamp": end_time.isoformat(),
    }

    logger.info(f"Backup job completed: {summary}")
    return summary
