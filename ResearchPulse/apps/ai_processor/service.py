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
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.crawler.models.article import Article
from core.database import get_session_factory
from settings import settings

from .models import AIProcessingLog
from .providers.base import BaseAIProvider, get_content_hash
from .processors.rule_classifier import (
    classify_by_domain,
    estimate_task_type,
    is_paper_content,
    should_skip_processing,
)

logger = logging.getLogger(__name__)


def get_ai_provider(provider_name: str | None = None) -> BaseAIProvider:
    """Get an AI provider by name.

    Args:
        provider_name: Provider name override. Defaults to settings.ai_provider.
    """
    # 根据配置文件中的 ai_provider 设置选择对应的 AI 提供商
    # 支持 "ollama"（本地部署）和 "openai"（云端 API）
    # 默认回退到 Ollama，适合开发环境使用
    provider_name = provider_name or settings.ai_provider
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
        if not settings.ai_fallback_provider:
            return None
        if self._fallback_provider is None:
            self._fallback_provider = get_ai_provider(settings.ai_fallback_provider)
        return self._fallback_provider

    async def close(self) -> None:
        """Release resources held by the service (HTTP clients etc.)."""
        await self.provider.close()
        if self._fallback_provider:
            await self._fallback_provider.close()

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
                    f"trying fallback: {settings.ai_fallback_provider}"
                )
                processing_result = await fallback.process_content(title, content, task_type)

        processing_result["processing_method"] = "ai"
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
        self, article_ids: list[int], db: AsyncSession, force: bool = False
    ) -> dict:
        """Process multiple articles concurrently.

        使用 asyncio.Semaphore 控制并发度，每个并发任务使用独立的 DB session，
        避免 AsyncSession 的并发安全问题。处理日志统一批量写入。
        """
        if not article_ids:
            return {"total": 0, "processed": 0, "cached": 0, "failed": 0, "results": []}

        self._batch_mode = True
        semaphore = asyncio.Semaphore(settings.ai_batch_concurrency)
        session_factory = get_session_factory()
        results: list[dict] = [{}] * len(article_ids)
        logs: list[AIProcessingLog] = []

        async def _process_one(index: int, article_id: int) -> None:
            """Process a single article within the semaphore-guarded context."""
            async with semaphore:
                try:
                    # 每个并发任务使用独立的 session
                    async with session_factory() as session:
                        result = await self.process_article(article_id, session, force=force)
                        await session.commit()
                        # 提取日志对象
                        log = result.pop("_log", None)
                        if log:
                            logs.append(log)
                        results[index] = result
                except Exception as e:
                    logger.error(f"Error processing article {article_id}: {e}")
                    results[index] = {
                        "success": False,
                        "article_id": article_id,
                        "error_message": str(e),
                    }

        # 并发执行所有文章处理任务
        tasks = [
            _process_one(i, aid) for i, aid in enumerate(article_ids)
        ]
        await asyncio.gather(*tasks)

        self._batch_mode = False

        # O12: 批量写入所有处理日志
        if logs:
            db.add_all(logs)

        # 统计结果
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
            "total": len(article_ids),
            "processed": processed,
            "cached": cached,
            "failed": failed,
            "results": results,
        }

    async def process_unprocessed(
        self, db: AsyncSession, limit: int = 50
    ) -> dict:
        """Process articles that haven't been AI-processed yet."""
        # 查询尚未经过 AI 处理的文章（未归档的），按爬取时间倒序排列
        # 此方法通常由定时调度任务调用
        result = await db.execute(
            select(Article.id)
            .where(Article.ai_processed_at.is_(None))
            .where(Article.is_archived.is_(False))
            .order_by(Article.crawl_time.desc())
            .limit(limit)
        )
        article_ids = [row[0] for row in result.all()]
        if not article_ids:
            return {"total": 0, "processed": 0, "cached": 0, "failed": 0, "results": []}
        return await self.batch_process(article_ids, db)

    async def _save_result(
        self, article: Article, result: dict, db: AsyncSession
    ) -> None:
        """Save processing result to article."""
        # 将 AI 处理结果更新到文章记录中
        # 包括摘要、分类、重要性评分、一句话总结、关键要点、影响评估、行动项等
        # 同时记录处理时间和使用的 provider/model 信息
        await db.execute(
            update(Article)
            .where(Article.id == article.id)
            .values(
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
        )
