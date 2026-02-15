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

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.crawler.models.article import Article
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


def get_ai_provider() -> BaseAIProvider:
    """Get the configured AI provider."""
    # 根据配置文件中的 ai_provider 设置选择对应的 AI 提供商
    # 支持 "ollama"（本地部署）和 "openai"（云端 API）
    # 默认回退到 Ollama，适合开发环境使用
    provider_name = settings.ai_provider
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
        task_type = estimate_task_type(article.url or "", title, content)

        # 第五步：域名快速分类 —— 对已知高置信度域名的短内容直接归类
        # 条件：域名可识别 + 内容不足 1000 字符 + 任务类型为低价值
        # 这一优化可显著减少 AI API 调用量
        domain_result = classify_by_domain(article.url or "")
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
        processing_result["processing_method"] = "ai"
        await self._save_result(article, processing_result, db)

        # 第七步：记录处理日志（用于统计和监控）
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
        db.add(log)

        return {**processing_result, "article_id": article_id}

    async def batch_process(
        self, article_ids: list[int], db: AsyncSession, force: bool = False
    ) -> dict:
        """Process multiple articles."""
        # 逐篇处理文章并统计结果
        # 设计决策：串行处理而非并行，避免对 AI 服务造成过大压力
        results = []
        processed = 0
        cached = 0
        failed = 0

        for article_id in article_ids:
            result = await self.process_article(article_id, db, force=force)
            results.append(result)
            if result.get("success"):
                if result.get("processing_method") == "cached":
                    cached += 1    # 命中缓存
                else:
                    processed += 1  # 实际处理（AI 或规则）
            else:
                failed += 1        # 处理失败

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
