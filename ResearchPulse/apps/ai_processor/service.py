# =============================================================================
# AI 处理器服务层模块
# =============================================================================
# 本模块是 AI 处理器的核心业务逻辑层，承上启下：
#   - 上层：被 API 端点和调度任务调用
#   - 下层：调用 AI Provider（Ollama/OpenAI）和规则分类器
# 核心职责：
#   1. 单篇/批量文章的 AI 分析处理
#   2. 缓存判断 —— 已处理过的文章直接返回缓存结果
#   3. 规则预筛选 —— 通过规则分类器跳过低价值内容，节省 AI 调用成本
#   4. 域名快速分类 —— 对已知域名的短内容直接用规则归类
#   5. 处理结果持久化 —— 将 AI 输出写回文章记录并记录日志
# =============================================================================

"""AI processor service layer."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.parse import urlparse

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.crawler.models.article import Article
from core.database import get_session_factory
from settings import settings
from common.feature_config import feature_config

from .models import AIProcessingLog
from .providers.base import BaseAIProvider, get_content_hash
from .processors.rule_classifier import (
    classify_by_domain,
    estimate_task_type,
    is_paper_content,
    should_skip_processing,
)

logger = logging.getLogger(__name__)


def _is_english(text: str) -> bool:
    """Check if text is primarily English by ASCII letter ratio."""
    if not text or len(text) < 20:
        return False
    ascii_letters = sum(1 for c in text if c.isascii() and c.isalpha())
    total_letters = sum(1 for c in text if c.isalpha())
    if total_letters == 0:
        return False
    return ascii_letters / total_letters > 0.5


def get_ai_provider(provider_name: str | None = None) -> BaseAIProvider:
    """Get an AI provider by name.

    Args:
        provider_name: Provider name override. Defaults to settings.ai_provider.
    """
    # 根据配置文件中的 ai_provider 设置选择对应的 AI 提供商
    # 支持 "ollama"（本地部署）和 "openai"（云端 API）
    # 默认回退到 Ollama，适合开发环境使用
    provider_name = provider_name or feature_config.get("ai.provider", settings.ai_provider)
    if provider_name == "ollama":
        from .providers.ollama_provider import OllamaProvider
        return OllamaProvider()
    elif provider_name == "openai":
        from .providers.openai_provider import OpenAIProvider
        return OpenAIProvider()
    else:
        # 未知的 provider 名称时默认使用 Ollama
        from .providers.ollama_provider import OllamaProvider
        return OllamaProvider()


# -----------------------------------------------------------------------------
# AI 处理器服务类
# 封装所有 AI 内容处理的业务逻辑。
# 设计决策：
#   - 支持依赖注入（通过构造函数传入 provider），方便单元测试
#   - 采用"规则优先、AI 兜底"的分层处理策略，平衡成本和质量
# -----------------------------------------------------------------------------
class AIProcessorService:
    """Service for AI content processing."""

    def __init__(self, provider: BaseAIProvider | None = None):
        # 如果未显式传入 provider，则根据全局配置自动创建
        self.provider = provider or get_ai_provider()
        # 降级回退 Provider（懒初始化，仅在主 Provider 失败时创建）
        self._fallback_provider: BaseAIProvider | None = None

    def _get_fallback_provider(self) -> BaseAIProvider | None:
        """Get or create the fallback AI provider.

        获取或创建降级回退 Provider。仅在配置了 ai_fallback_provider 时可用。

        Returns:
            BaseAIProvider | None: Fallback provider or None.
        """
        fallback_name = feature_config.get("ai.fallback_provider") or settings.ai_fallback_provider
        if not fallback_name:
            return None
        if self._fallback_provider is None:
            self._fallback_provider = get_ai_provider(fallback_name)
        return self._fallback_provider

    async def close(self) -> None:
        """Release resources held by the service (HTTP clients etc.)."""
        await self.provider.close()
        if self._fallback_provider:
            await self._fallback_provider.close()

    async def warmup(self) -> bool:
        """Pre-load the AI model to reduce first-request latency.

        委托给底层 Provider 的 warmup() 方法。失败不抛异常。

        Returns:
            bool: True if warmup succeeded or is not needed.
        """
        try:
            return await self.provider.warmup()
        except Exception as e:
            logger.warning(f"Model warmup failed: {e}")
            return False

    async def process_article(
        self, article_id: int, db: AsyncSession, force: bool = False
    ) -> dict:
        """Process a single article with AI."""
        # 第一步：从数据库查询文章
        result = await db.execute(select(Article).where(Article.id == article_id))
        article = result.scalar_one_or_none()
        if not article:
            return {"success": False, "error_message": f"Article {article_id} not found"}

        # 第二步：缓存检查 —— 如果文章已处理过且未强制重处理，直接返回缓存结果
        if article.ai_processed_at and not force:
            return {
                "success": True,
                "article_id": article_id,
                "summary": article.ai_summary or "",
                "category": article.ai_category or "",
                "importance_score": article.importance_score or 5,
                "processing_method": "cached",
            }

        # 准备文章标题和内容，优先使用完整内容，其次使用摘要
        title = article.title or ""
        content = article.content or article.summary or ""

        # 预解析 URL 域名，避免下游函数重复 urlparse
        url = article.url or ""
        domain = None
        if url:
            try:
                parsed = urlparse(url)
                domain = parsed.netloc.lower().replace("www.", "")
            except (ValueError, AttributeError):
                pass

        # 第三步：规则预筛选 —— 检查内容是否应跳过 AI 处理
        # 跳过条件包括：内容为空、过短、招聘帖、促销内容、重复内容等
        should_skip, skip_reason = should_skip_processing(
            title, content, article.source_type or ""
        )
        if should_skip:
            # 对跳过的内容生成最低重要性的占位结果
            processing_result = {
                "summary": f"[Skipped] {title[:40]}...",
                "category": "其他",
                "importance_score": 1,
                "one_liner": "",
                "key_points": [],
                "impact_assessment": None,
                "actionable_items": [],
                "provider": "rule",
                "model": "rule_classifier",
                "success": True,
                "processing_method": "rule",
            }
            await self._save_result(article, processing_result, db)
            return {**processing_result, "article_id": article_id}

        # 第四步：估算任务类型（paper_full / content_high / content_low）
        # 不同任务类型对应不同的 prompt 模板和生成长度
        task_type = estimate_task_type(url, title, content, domain=domain)

        # 第五步：域名快速分类 —— 对已知高置信度域名的短内容直接归类
        # 条件：域名可识别 + 内容不足 1000 字符 + 任务类型为低价值
        # 这一优化可显著减少 AI API 调用量
        domain_result = classify_by_domain(url, domain=domain)
        if domain_result and len(content) < 1000 and task_type == "content_low":
            category, importance = domain_result
            processing_result = {
                "summary": title[:100],
                "category": category,
                "importance_score": min(6, importance),  # 规则分类的分数上限设为 6，避免过高评分
                "one_liner": f"{category}动态：{title[:50]}",
                "key_points": [],
                "impact_assessment": None,
                "actionable_items": [],
                "provider": "rule",
                "model": "domain_classifier",
                "success": True,
                "processing_method": "rule",
            }
            await self._save_result(article, processing_result, db)
            return {**processing_result, "article_id": article_id}

        # 第六步：真正的 AI 处理 —— 调用配置的 AI Provider 进行内容分析
        processing_result = await self.provider.process_content(title, content, task_type)

        # 如果主 Provider 失败且配置了降级回退 Provider，尝试用备用 Provider 重新处理
        if not processing_result.get("success"):
            fallback = self._get_fallback_provider()
            if fallback:
                logger.warning(
                    f"Primary provider failed for article {article_id}, "
                    f"trying fallback: {feature_config.get('ai.fallback_provider') or settings.ai_fallback_provider}"
                )
                processing_result = await fallback.process_content(title, content, task_type)

        processing_result["processing_method"] = "ai" if processing_result.get("success") else "failed"

        # 英文标题翻译：检测后请求 AI 翻译
        if processing_result.get("success") and _is_english(article.title or ""):
            try:
                translated_title = await self.provider.translate(article.title)
                if translated_title:
                    processing_result["_translated_title"] = translated_title
            except Exception as e:
                logger.debug(f"Title translation skipped for article {article_id}: {e}")

        # 英文 summary 翻译：检测后请求 AI 翻译，成功则存入 content
        if processing_result.get("success") and _is_english(article.summary or ""):
            try:
                translated = await self.provider.translate(article.summary)
                if translated:
                    processing_result["_translated_content"] = translated
            except Exception as e:
                logger.debug(f"Translation skipped for article {article_id}: {e}")

        await self._save_result(article, processing_result, db)

        # 第七步：构建处理日志对象并返回（由调用方统一持久化）
        log = AIProcessingLog(
            article_id=article_id,
            provider=processing_result.get("provider", "unknown"),
            model=processing_result.get("model", "unknown"),
            task_type=task_type,
            input_chars=processing_result.get("input_chars", 0),
            output_chars=processing_result.get("output_chars", 0),
            duration_ms=processing_result.get("duration_ms", 0),
            success=processing_result.get("success", False),
            error_message=processing_result.get("error_message"),
            cached=False,
        )
        # 在非并发模式下（单篇处理 API 调用），直接写入 session
        # 并发模式下由 batch_process 统一写入
        if not getattr(self, '_batch_mode', False):
            db.add(log)

        result_dict = {**processing_result, "article_id": article_id}
        result_dict["_log"] = log
        return result_dict

    async def batch_process(
        self,
        article_ids: list[int],
        force: bool = False,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> dict:
        """Process multiple articles, dispatching to serial or concurrent path.

        根据 settings.ai_batch_concurrency 配置选择串行或并行处理路径。
        默认值为 1（串行），可通过 .env 中 AI_BATCH_CONCURRENCY 修改。

        Args:
            article_ids: List of article IDs to process.
            force: Force reprocessing even if already processed.
            progress_callback: Optional callback for progress updates.
                Called with (current_index, total_count, message).

        Returns:
            dict: Summary with total, processed, cached, failed counts.
        """
        if not article_ids:
            return {"total": 0, "processed": 0, "cached": 0, "failed": 0, "results": []}

        concurrency = feature_config.get_int("ai.batch_concurrency", settings.ai_batch_concurrency)
        if concurrency > 1:
            logger.info(
                f"Batch processing {len(article_ids)} articles "
                f"with concurrency={concurrency}"
            )
            results = await self._batch_process_concurrent(
                article_ids, force=force, concurrency=concurrency, progress_callback=progress_callback
            )
        else:
            logger.info(f"Batch processing {len(article_ids)} articles serially")
            results = await self._batch_process_serial(article_ids, force=force, progress_callback=progress_callback)

        return self._summarize_results(results)

    async def _batch_process_serial(
        self,
        article_ids: list[int],
        force: bool = False,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> list[dict]:
        """Process articles one by one, each with an independent DB session.

        串行逐篇处理，每篇文章使用独立 session，安全可靠。

        Args:
            article_ids: List of article IDs to process.
            force: Force reprocessing.
            progress_callback: Optional progress callback.
        """
        session_factory = get_session_factory()
        results: list[dict] = []
        total = len(article_ids)

        for idx, article_id in enumerate(article_ids, 1):
            try:
                if progress_callback:
                    progress_callback(idx, total, f"Processing article {article_id}")
                async with session_factory() as session:
                    result = await self.process_article(article_id, session, force=force)
                    await session.commit()
                    result.pop("_log", None)
                    results.append(result)
            except Exception as e:
                logger.error(f"Error processing article {article_id}: {e}")
                await self._mark_article_failed(article_id, e)
                results.append({
                    "success": False,
                    "article_id": article_id,
                    "error_message": str(e),
                })

        return results

    async def _batch_process_concurrent(
        self,
        article_ids: list[int],
        force: bool = False,
        concurrency: int = 3,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> list[dict]:
        """Process articles concurrently with independent service instances.

        并行处理文章。每个并发任务创建独立的 AIProcessorService 实例
        （含独立的 Provider 和 httpx.AsyncClient），彻底避免共享状态。
        使用 asyncio.Semaphore 控制并发上限。

        Args:
            article_ids: List of article IDs to process.
            force: Force reprocessing.
            concurrency: Max concurrent tasks.
            progress_callback: Optional progress callback.
        """
        semaphore = asyncio.Semaphore(concurrency)
        session_factory = get_session_factory()
        total = len(article_ids)
        # 使用计数器追踪进度
        progress_counter = [0]  # 使用列表以便在闭包中修改
        progress_lock = asyncio.Lock()

        async def _process_one(article_id: int) -> dict:
            async with semaphore:
                # 每个任务创建独立的 service 实例，避免共享 HTTP 客户端
                task_service = AIProcessorService()
                try:
                    async with session_factory() as session:
                        result = await task_service.process_article(
                            article_id, session, force=force
                        )
                        await session.commit()
                        result.pop("_log", None)

                        # 更新进度
                        if progress_callback:
                            async with progress_lock:
                                progress_counter[0] += 1
                                progress_callback(
                                    progress_counter[0],
                                    total,
                                    f"Completed article {article_id}"
                                )

                        return result
                except Exception as e:
                    logger.error(f"Error processing article {article_id}: {e}")
                    await self._mark_article_failed(article_id, e)
                    if progress_callback:
                        async with progress_lock:
                            progress_counter[0] += 1
                            progress_callback(
                                progress_counter[0],
                                total,
                                f"Failed article {article_id}"
                            )
                    return {
                        "success": False,
                        "article_id": article_id,
                        "error_message": str(e),
                    }
                finally:
                    await task_service.close()

        tasks = [_process_one(aid) for aid in article_ids]
        return await asyncio.gather(*tasks)

    async def _mark_article_failed(self, article_id: int, error: Exception) -> None:
        """Mark an article as failed so it won't block the processing queue.

        标记文章为处理失败，避免下次调度时反复处理同一批失败文章。
        """
        session_factory = get_session_factory()
        try:
            async with session_factory() as err_session:
                await err_session.execute(
                    update(Article).where(Article.id == article_id).values(
                        ai_processed_at=datetime.now(timezone.utc),
                        processing_method="failed",
                        ai_summary=f"[处理失败] {str(error)[:200]}",
                    )
                )
                await err_session.commit()
        except Exception:
            logger.warning(f"Failed to mark article {article_id} as failed")

    @staticmethod
    def _summarize_results(results: list[dict]) -> dict:
        """Aggregate per-article results into batch statistics.

        统计批处理结果：成功、缓存、失败数量。
        """
        processed = 0
        cached = 0
        failed = 0
        for r in results:
            if r.get("success"):
                if r.get("processing_method") == "cached":
                    cached += 1
                else:
                    processed += 1
            else:
                failed += 1

        return {
            "total": len(results),
            "processed": processed,
            "cached": cached,
            "failed": failed,
            "results": results,
        }

    async def process_unprocessed(
        self,
        db: AsyncSession,
        limit: int = 50,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> dict:
        """Process articles that haven't been AI-processed yet.

        Args:
            db: Async database session.
            limit: Max number of articles to process.
            progress_callback: Optional callback for progress updates.

        Returns:
            dict: Batch processing summary.
        """
        # 查询尚未经过 AI 处理的文章（未归档的），按爬取时间倒序排列
        # 此方法通常由定时调度任务调用
        result = await db.execute(
            select(Article.id)
            .where(Article.ai_processed_at.is_(None))
            .where(Article.is_archived.is_(False))
            .where(Article.source_type != "aigc")
            .order_by(Article.crawl_time.desc())
            .limit(limit)
        )
        article_ids = [row[0] for row in result.all()]
        if not article_ids:
            return {"total": 0, "processed": 0, "cached": 0, "failed": 0, "results": []}
        return await self.batch_process(article_ids, progress_callback=progress_callback)

    async def _save_result(
        self, article: Article, result: dict, db: AsyncSession
    ) -> None:
        """Save processing result to article."""
        # 将 AI 处理结果更新到文章记录中
        # 包括摘要、分类、重要性评分、一句话总结、关键要点、影响评估、行动项等
        # 同时记录处理时间和使用的 provider/model 信息
        values = dict(
            ai_summary=result.get("summary", ""),
            ai_category=result.get("category", "其他"),
            importance_score=result.get("importance_score", 5),
            one_liner=result.get("one_liner", ""),
            key_points=result.get("key_points"),
            impact_assessment=result.get("impact_assessment"),
            actionable_items=result.get("actionable_items"),
            ai_processed_at=datetime.now(timezone.utc),
            ai_provider=result.get("provider", ""),
            ai_model=result.get("model", ""),
            processing_method=result.get("processing_method", ""),
        )
        translated_content = result.get("_translated_content")
        if translated_content:
            # 翻译后的摘要存储到 content_summary 字段（与报告生成保持一致）
            values["content_summary"] = translated_content
        translated_title = result.get("_translated_title")
        if translated_title:
            values["translated_title"] = translated_title

        await db.execute(
            update(Article)
            .where(Article.id == article.id)
            .values(**values)
        )
