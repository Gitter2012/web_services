# =============================================================================
# 模块: apps/daily_digest/service.py
# 功能: 每日精选日报业务编排服务
# 架构角色: 业务层，协调 scorer/selector/ai_synthesizer/generator 完整生成流程
#
# 核心设计：
#   - category="all"  → 全量跨源精选（所有 AI 分类）
#   - category="AI"   → 仅精选 ai_category="AI" 的文章
#   - category="金融" → 仅精选 ai_category="金融" 的文章
#   通过 (report_date, source_type="digest", category) 唯一约束区分每种精选
#
# 业务流程（Step 1-9）：
#   1. 幂等检查（已存在且 force=False → 直接返回）
#   2. 查询候选文章（过去 N h，importance_score ≥ 门槛，可按分类过滤）
#   3. 查询事件聚类信息（EventMember → EventCluster）
#   4. 计算各源最大互动数（归一化基准）
#   5. 综合评分（scorer.py）
#   6. 精选 Top-N（selector.py）
#   7. AI 摘要合成（ai_synthesizer.py）
#   8. 渲染 Markdown（generator.py）
#   9. 保存 DailyReport（source_type="digest", category=<category>）
# =============================================================================

"""Daily digest service orchestration."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.crawler.models.article import Article
from apps.daily_report.models.daily_report import DailyReport
from apps.event.models import EventCluster, EventMember
from core.database import get_session_factory
from common.feature_config import feature_config

from .scorer import score_articles
from .selector import select_top_n, ScoredArticle
from .ai_synthesizer import generate_all_summaries
from .generator import DigestGenerator

logger = logging.getLogger(__name__)

# ─── 精选日报标识符常量 ──────────────────────────────────────────────────────
DIGEST_SOURCE_TYPE = "digest"

# category="all" 表示跨所有 AI 分类的全量聚合精选
DIGEST_CATEGORY_ALL = "all"

# 分类名称映射（ai_category 代码 → 展示名称）
CATEGORY_NAME_MAP: dict[str, str] = {
    "all":    "每日精选",
    "AI":     "AI 精选",
    "金融":   "财经精选",
    "技术":   "科技精选",
    "编程":   "编程精选",
    "研究":   "研究精选",
    "创业":   "创业精选",
    "设计":   "设计精选",
    "其他":   "综合精选",
}

# ─── 默认配置值（从 feature_config 读取，这里是代码兜底） ─────────────────────
_DEFAULT_CANDIDATE_WINDOW_HOURS: int = 28
_DEFAULT_MIN_IMPORTANCE_SCORE: int = 4
_DEFAULT_TOP_N: int = 25
_DEFAULT_MAX_CANDIDATES: int = 2000
_DEFAULT_CLUSTER_ACTIVE_WINDOW_HOURS: int = 48


def _get_category_name(category: str) -> str:
    """获取分类展示名称。"""
    return CATEGORY_NAME_MAP.get(category, f"{category}精选")


async def _progress(callback: Optional[Callable], progress: int, message: str) -> None:
    """安全调用进度回调。"""
    if callback:
        try:
            await callback(progress, message)
        except Exception:
            pass


class DailyDigestService:
    """每日精选日报生成服务。

    复用 DailyReport ORM 存储精选日报，通过
    (source_type="digest", category=<category>) 区分不同类型的精选。

    支持：
      - category="all"  → 全量跨源精选
      - category="AI"   → 仅 AI 类别
      - category="金融" → 仅财经类别
      - 其他 ai_category 值
    """

    def __init__(self) -> None:
        self.generator = DigestGenerator()

    # ─────────────────────────────────────────────────────────────────────────
    # 公开接口
    # ─────────────────────────────────────────────────────────────────────────

    async def generate_digest(
        self,
        report_date: Optional[date] = None,
        category: str = DIGEST_CATEGORY_ALL,
        force: bool = False,
        top_n: Optional[int] = None,
        progress_callback: Optional[Callable] = None,
    ) -> Optional[DailyReport]:
        """生成指定日期、指定分类的每日精选日报。

        Args:
            report_date: 日报日期，默认**今天**。
            category: 精选分类。"all" 为跨源全量精选，其他值按 ai_category 过滤。
            force: 是否强制重新生成（已存在时删除旧记录重新生成）。
            top_n: 精选排名位数，None 时从配置读取（默认 25）。
            progress_callback: 进度回调 async (progress: int, message: str)。

        Returns:
            生成的 DailyReport，或已存在且未 force 时的旧记录；无候选时返回 None。
        """
        if report_date is None:
            report_date = date.today()

        # 从配置读取运行时参数
        if top_n is None:
            top_n = feature_config.get_int("daily_digest.top_n", _DEFAULT_TOP_N)
        candidate_window = feature_config.get_int(
            "daily_digest.candidate_window_hours", _DEFAULT_CANDIDATE_WINDOW_HOURS
        )
        min_importance = feature_config.get_int(
            "daily_digest.min_importance_score", _DEFAULT_MIN_IMPORTANCE_SCORE
        )
        max_candidates = feature_config.get_int(
            "daily_digest.max_candidates", _DEFAULT_MAX_CANDIDATES
        )

        category_name = _get_category_name(category)
        date_str = report_date.strftime("%Y-%m-%d")

        session_factory = get_session_factory()

        async with session_factory() as db:
            # ----------------------------------------------------------------
            # Step 1: 幂等检查
            # ----------------------------------------------------------------
            await _progress(progress_callback, 0, f"检查已存在日报 [{category_name}]...")
            existing = await self._get_existing(db, report_date, category)

            if existing:
                if not force:
                    logger.info(
                        "Digest [%s] for %s already exists (id=%d), skipping",
                        category, report_date, existing.id
                    )
                    await _progress(
                        progress_callback, 100,
                        f"[{category_name}] 日报已存在（id={existing.id}），跳过"
                    )
                    return existing
                else:
                    logger.info(
                        "Force regenerating digest [%s] for %s (existing id=%d)",
                        category, report_date, existing.id
                    )
                    await db.delete(existing)
                    await db.commit()

            # ----------------------------------------------------------------
            # Step 2: 查询候选文章
            # ----------------------------------------------------------------
            await _progress(progress_callback, 5, f"[{category_name}] 查询候选文章...")
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=candidate_window)
            candidates = await self._fetch_candidates(
                db, cutoff_time, category, min_importance, max_candidates
            )

            if not candidates:
                logger.info(
                    "No candidates for digest [%s] on %s", category, report_date
                )
                await _progress(progress_callback, 100, f"[{category_name}] 无候选文章，跳过")
                return None

            logger.info(
                "Digest [%s] on %s: %d candidates", category, report_date, len(candidates)
            )
            await _progress(
                progress_callback, 15,
                f"[{category_name}] 找到 {len(candidates)} 篇候选文章"
            )

            # ----------------------------------------------------------------
            # Step 3: 查询事件聚类信息
            # ----------------------------------------------------------------
            await _progress(progress_callback, 20, f"[{category_name}] 查询事件聚类...")
            cluster_active_cutoff = datetime.now(timezone.utc) - timedelta(
                hours=_DEFAULT_CLUSTER_ACTIVE_WINDOW_HOURS
            )
            article_cluster_map, cluster_members = await self._fetch_cluster_info(
                db, [a.id for a in candidates], cluster_active_cutoff
            )

            # ----------------------------------------------------------------
            # Step 4: 计算各源最大互动数
            # ----------------------------------------------------------------
            await _progress(progress_callback, 25, f"[{category_name}] 计算互动数基准...")
            max_engagement_by_source = self._compute_max_engagement(candidates)

            # ----------------------------------------------------------------
            # Step 5: 综合评分
            # ----------------------------------------------------------------
            await _progress(progress_callback, 30, f"[{category_name}] 计算综合评分...")
            now = datetime.now(timezone.utc)
            cluster_map_for_scorer = {
                aid: len(cluster_members.get(cid, []))
                for aid, cid in article_cluster_map.items()
            }
            scored = score_articles(
                candidates, cluster_map_for_scorer, max_engagement_by_source, now
            )

            # ----------------------------------------------------------------
            # Step 6: 精选 Top-N
            # ----------------------------------------------------------------
            await _progress(progress_callback, 40, f"[{category_name}] 精选 Top {top_n}...")
            selected = select_top_n(
                scored_articles=scored,
                cluster_members=cluster_members,
                article_cluster_map=article_cluster_map,
                top_n=top_n,
            )

            if not selected:
                logger.warning(
                    "No articles selected for digest [%s] on %s", category, report_date
                )
                await _progress(progress_callback, 100, f"[{category_name}] 精选结果为空，跳过")
                return None

            logger.info("Digest [%s]: selected %d articles", category, len(selected))

            # ----------------------------------------------------------------
            # Step 7: AI 摘要合成
            # ----------------------------------------------------------------
            await _progress(progress_callback, 55, f"[{category_name}] AI 生成摘要...")
            selected_by_category: dict[str, list[ScoredArticle]] = {}
            for sa in selected:
                cat = sa.display_category
                if cat not in selected_by_category:
                    selected_by_category[cat] = []
                selected_by_category[cat].append(sa)

            enable_ai = feature_config.get_bool("daily_digest.ai_synthesis", True)
            if enable_ai:
                category_summaries, global_insight = await generate_all_summaries(
                    selected_by_category, selected
                )
            else:
                category_summaries = {cat: None for cat in selected_by_category}
                global_insight = None

            # ----------------------------------------------------------------
            # Step 8: 渲染 Markdown
            # ----------------------------------------------------------------
            await _progress(progress_callback, 80, f"[{category_name}] 渲染 Markdown...")

            source_breakdown: dict[str, int] = {}
            for sa in selected:
                src = sa.article.source_type or "unknown"
                source_breakdown[src] = source_breakdown.get(src, 0) + 1

            content_markdown = self.generator.generate(
                report_date=report_date,
                selected=selected,
                total_crawled=len(candidates),
                source_breakdown=source_breakdown,
                category_summaries=category_summaries,
                global_insight=global_insight,
                digest_category=category,
                digest_category_name=category_name,
            )

            # ----------------------------------------------------------------
            # Step 9: 保存 DailyReport
            # ----------------------------------------------------------------
            await _progress(progress_callback, 90, f"[{category_name}] 保存日报记录...")

            all_article_ids: list[int] = []
            for sa in selected:
                all_article_ids.append(sa.article.id)
                for rsa in sa.related_articles:
                    all_article_ids.append(rsa.article.id)

            report = DailyReport(
                report_date=report_date,
                source_type=DIGEST_SOURCE_TYPE,
                category=category,
                category_name=category_name,
                title=f"📰 {category_name} · {date_str}",
                content_markdown=content_markdown,
                article_count=len(selected),
                article_ids=all_article_ids,
                status="published",
            )

            db.add(report)
            await db.commit()
            await db.refresh(report)

            logger.info(
                "Digest [%s] generated: id=%d, date=%s, selected=%d, candidates=%d",
                category, report.id, report_date, len(selected), len(candidates),
            )
            await _progress(
                progress_callback, 100,
                f"[{category_name}] 精选日报生成完成（id={report.id}，精选 {len(selected)} 篇）"
            )
            return report

    async def generate_multi_digests(
        self,
        report_date: Optional[date] = None,
        categories: Optional[list[str]] = None,
        force: bool = False,
        top_n: Optional[int] = None,
        progress_callback: Optional[Callable] = None,
    ) -> list[DailyReport]:
        """批量生成多个分类的精选日报。

        Args:
            report_date: 日报日期，默认今天。
            categories: 要生成的分类列表，None 时从配置读取。
            force: 是否强制重新生成。
            top_n: 精选排名位数，None 时从配置读取。
            progress_callback: 进度回调。

        Returns:
            成功生成的 DailyReport 列表。
        """
        if report_date is None:
            report_date = date.today()

        if categories is None:
            cats_str = feature_config.get(
                "daily_digest.categories", "all,AI,金融,技术"
            )
            categories = [c.strip() for c in cats_str.split(",") if c.strip()]

        reports: list[DailyReport] = []
        total = len(categories)

        for idx, category in enumerate(categories):
            cat_name = _get_category_name(category)
            logger.info(
                "Generating digest [%s] (%d/%d) for %s",
                category, idx + 1, total, report_date
            )
            # 包装进度回调以反映整体进度
            async def _cat_progress(p: int, msg: str, _i=idx, _t=total) -> None:
                if progress_callback:
                    overall = int((_i / _t + p / 100 / _t) * 100)
                    await _progress(progress_callback, overall, msg)

            try:
                report = await self.generate_digest(
                    report_date=report_date,
                    category=category,
                    force=force,
                    top_n=top_n,
                    progress_callback=_cat_progress,
                )
                if report:
                    reports.append(report)
            except Exception as e:
                logger.error(
                    "Digest [%s] generation failed for %s: %s",
                    category, report_date, e, exc_info=True
                )

        await _progress(
            progress_callback, 100,
            f"批量精选完成：{len(reports)}/{total} 个分类生成成功"
        )
        return reports

    # ─────────────────────────────────────────────────────────────────────────
    # 查询接口
    # ─────────────────────────────────────────────────────────────────────────

    async def get_digest(
        self,
        db: AsyncSession,
        report_date: date,
        category: str = DIGEST_CATEGORY_ALL,
    ) -> Optional[DailyReport]:
        """获取指定日期、分类的精选日报。"""
        return await self._get_existing(db, report_date, category)

    async def list_digests_by_date(
        self,
        db: AsyncSession,
        report_date: date,
    ) -> list[DailyReport]:
        """获取指定日期的所有分类精选日报列表。"""
        result = await db.execute(
            select(DailyReport)
            .where(
                and_(
                    DailyReport.report_date == report_date,
                    DailyReport.source_type == DIGEST_SOURCE_TYPE,
                )
            )
            .order_by(DailyReport.category)
        )
        return list(result.scalars().all())

    async def get_status(
        self,
        db: AsyncSession,
        report_date: date,
        category: str = DIGEST_CATEGORY_ALL,
    ) -> dict:
        """查询指定日期、分类的精选日报生成状态。"""
        report = await self._get_existing(db, report_date, category)
        if report is None:
            return {
                "date": str(report_date),
                "category": category,
                "status": "not_generated",
                "report_id": None,
                "article_count": 0,
            }
        return {
            "date": str(report_date),
            "category": category,
            "status": report.status,
            "report_id": report.id,
            "article_count": report.article_count,
            "title": report.title,
            "created_at": report.created_at.isoformat() if report.created_at else None,
        }

    async def list_status_by_date(self, db: AsyncSession, report_date: date) -> list[dict]:
        """获取指定日期所有分类精选日报的状态列表。"""
        reports = await self.list_digests_by_date(db, report_date)
        return [
            {
                "date": str(r.report_date),
                "category": r.category,
                "category_name": r.category_name,
                "status": r.status,
                "report_id": r.id,
                "article_count": r.article_count,
                "title": r.title,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ]

    # ─────────────────────────────────────────────────────────────────────────
    # 内部辅助方法
    # ─────────────────────────────────────────────────────────────────────────

    async def _get_existing(
        self,
        db: AsyncSession,
        report_date: date,
        category: str = DIGEST_CATEGORY_ALL,
    ) -> Optional[DailyReport]:
        """查询已存在的精选日报。"""
        result = await db.execute(
            select(DailyReport).where(
                and_(
                    DailyReport.report_date == report_date,
                    DailyReport.source_type == DIGEST_SOURCE_TYPE,
                    DailyReport.category == category,
                )
            )
        )
        return result.scalar_one_or_none()

    async def _fetch_candidates(
        self,
        db: AsyncSession,
        cutoff_time: datetime,
        category: str = DIGEST_CATEGORY_ALL,
        min_importance: int = _DEFAULT_MIN_IMPORTANCE_SCORE,
        max_candidates: int = _DEFAULT_MAX_CANDIDATES,
    ) -> list[Article]:
        """查询候选文章。

        当 category != "all" 时，按 Article.ai_category 过滤。
        """
        conditions = [
            Article.is_archived.is_(False),
            Article.importance_score >= min_importance,
            Article.publish_time >= cutoff_time,
        ]

        # 分类精选：按 ai_category 过滤
        if category != DIGEST_CATEGORY_ALL:
            conditions.append(Article.ai_category == category)

        query = (
            select(Article)
            .where(and_(*conditions))
            .order_by(Article.importance_score.desc(), Article.publish_time.desc())
            .limit(max_candidates)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def _fetch_cluster_info(
        self,
        db: AsyncSession,
        article_ids: list[int],
        cluster_active_cutoff: datetime,
    ) -> tuple[dict[int, int], dict[int, list[int]]]:
        """查询候选文章的事件聚类信息。

        Returns:
            (article_cluster_map, cluster_members)
        """
        if not article_ids:
            return {}, {}

        try:
            query = (
                select(EventMember.article_id, EventMember.event_id)
                .join(EventCluster, EventMember.event_id == EventCluster.id)
                .where(
                    and_(
                        EventMember.article_id.in_(article_ids),
                        EventCluster.is_active.is_(True),
                        EventCluster.last_updated_at >= cluster_active_cutoff,
                    )
                )
            )
            result = await db.execute(query)
            rows = result.all()

            article_cluster_map: dict[int, int] = {}
            cluster_members: dict[int, list[int]] = {}

            for row in rows:
                aid, cid = row[0], row[1]
                article_cluster_map[aid] = cid
                if cid not in cluster_members:
                    cluster_members[cid] = []
                cluster_members[cid].append(aid)

            return article_cluster_map, cluster_members

        except Exception as e:
            logger.warning("Failed to fetch cluster info: %s", e)
            return {}, {}

    def _compute_max_engagement(self, articles: list[Article]) -> dict[str, float]:
        """计算各来源最大互动数（用于 log 归一化）。"""
        max_by_source: dict[str, float] = {}
        for article in articles:
            src = article.source_type or "unknown"
            read = getattr(article, "read_count", 0) or 0
            like = getattr(article, "like_count", 0) or 0
            engagement = read + like * 3
            if engagement > max_by_source.get(src, 0.0):
                max_by_source[src] = float(engagement)
        return max_by_source
