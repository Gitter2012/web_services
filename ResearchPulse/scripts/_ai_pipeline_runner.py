#!/usr/bin/env python3
"""Manual AI pipeline runner for ResearchPulse v2.

手动触发 AI 处理流水线的 CLI 工具，支持按阶段运行或一键运行全部流程。

流水线阶段（按依赖顺序）:
  1. ai        AI 文章处理（摘要、分类、评分）
  2. embedding 向量嵌入计算
  3. event     事件聚类
  4. topic     主题发现

Usage:
    python scripts/_ai_pipeline_runner.py all
    python scripts/_ai_pipeline_runner.py ai
    python scripts/_ai_pipeline_runner.py ai embedding
    python scripts/_ai_pipeline_runner.py embedding event topic
    python scripts/_ai_pipeline_runner.py all --limit 100 --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
import warnings
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ---------------------------------------------------------------------------
# 抑制 aiomysql + SQLAlchemy 异步连接池的 GC 回收警告。
# 当多阶段流水线依次运行时，前一阶段的连接池连接可能在后一阶段的
# 模块导入（如 TensorFlow / sentence-transformers）触发 GC 时被发现。
# 此时连接已不再使用，但 SQLAlchemy 会发出 SAWarning 和 logging.error。
# 这是 aiomysql 与 SQLAlchemy 异步引擎的已知行为，不影响功能正确性。
# ---------------------------------------------------------------------------
warnings.filterwarnings(
    "ignore",
    message=".*garbage collector.*non-checked-in connection.*",
)

# 同时静默 SQLAlchemy pool 模块在 GC 回收时输出的 ERROR 级别日志。
# pool.logger 的名称是 "sqlalchemy.pool.impl.AsyncAdaptedQueuePool"，
# 但 Python logging 的 Filter 不会被子 logger 继承，
# 因此直接将 filter 安装在 root logger 的 handler 上。
_pool_gc_filter = type(
    "_PoolGCFilter",
    (logging.Filter,),
    {
        "_SUPPRESSED": ("non-checked-in connection", "Exception terminating connection"),
        "filter": lambda self, record: not any(
            s in record.getMessage() for s in self._SUPPRESSED
        ),
    },
)()
logging.getLogger("sqlalchemy.pool.impl.AsyncAdaptedQueuePool").addFilter(
    _pool_gc_filter
)

from settings import settings

# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# 对 root logger 也加上同样的过滤器，
# 因为 basicConfig 把所有日志都路由到 root handler
logging.getLogger().addFilter(_pool_gc_filter)

# ---------------------------------------------------------------------------
# ANSI 颜色
# ---------------------------------------------------------------------------
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
CYAN = "\033[0;36m"
NC = "\033[0m"

# ---------------------------------------------------------------------------
# 流水线阶段定义（按依赖顺序）
# ---------------------------------------------------------------------------
STAGES = ("ai", "embedding", "event", "topic")

STAGE_DESCRIPTIONS = {
    "ai": "AI 文章处理（摘要/分类/评分）",
    "embedding": "向量嵌入计算",
    "event": "事件聚类",
    "topic": "主题发现",
}

STAGE_FEATURES = {
    "ai": "feature.ai_processor",
    "embedding": "feature.embedding",
    "event": "feature.event_clustering",
    "topic": "feature.topic_radar",
}


def _print(msg: str, level: str = "info") -> None:
    """Print colored message to stdout."""
    colors = {"info": CYAN, "success": GREEN, "warn": YELLOW, "error": RED}
    color = colors.get(level, NC)
    print(f"{color}{msg}{NC}")


# ---------------------------------------------------------------------------
# 各阶段运行函数
# ---------------------------------------------------------------------------

async def _run_ai(limit: int, verbose: bool) -> dict:
    """Run AI processing stage."""
    from core.database import get_session_factory
    from apps.ai_processor.service import AIProcessorService

    session_factory = get_session_factory()
    async with session_factory() as session:
        service = AIProcessorService()
        try:
            result = await service.process_unprocessed(session, limit=limit)
            await session.commit()
            return result
        except Exception as e:
            logger.error(f"AI processing failed: {e}", exc_info=verbose)
            await session.rollback()
            return {"error": str(e), "processed": 0, "cached": 0, "failed": 0, "total": 0}
        finally:
            await service.close()


async def _run_embedding(limit: int, verbose: bool) -> dict:
    """Run embedding computation stage."""
    from core.database import get_session_factory
    from apps.embedding.service import EmbeddingService

    session_factory = get_session_factory()
    async with session_factory() as session:
        service = EmbeddingService()
        result = await service.compute_uncomputed(session, limit=limit)
        await session.commit()
        return result


async def _run_event(limit: int, verbose: bool) -> dict:
    """Run event clustering stage."""
    from core.database import get_session_factory
    from apps.event.service import EventService

    session_factory = get_session_factory()
    async with session_factory() as session:
        service = EventService()
        result = await service.cluster_articles(session, limit=limit)
        await session.commit()
        return result


async def _run_topic(limit: int, verbose: bool) -> dict:
    """Run topic discovery stage."""
    from core.database import get_session_factory
    from apps.topic.service import TopicService

    session_factory = get_session_factory()
    async with session_factory() as session:
        service = TopicService()
        suggestions = await service.discover(
            session,
            days=settings.topic_lookback_days,
            min_frequency=settings.topic_min_frequency,
        )
        return {"suggestions_count": len(suggestions), "suggestions": suggestions}


STAGE_RUNNERS = {
    "ai": _run_ai,
    "embedding": _run_embedding,
    "event": _run_event,
    "topic": _run_topic,
}


# ---------------------------------------------------------------------------
# 结果格式化
# ---------------------------------------------------------------------------

def _format_result(stage: str, result: dict) -> str:
    """Format stage result as a human-readable line."""
    if "error" in result:
        return f"  错误: {result['error']}"

    if stage == "ai":
        return (
            f"  处理: {result.get('processed', 0)} | "
            f"缓存: {result.get('cached', 0)} | "
            f"失败: {result.get('failed', 0)} | "
            f"总计: {result.get('total', 0)}"
        )
    elif stage == "embedding":
        return (
            f"  计算: {result.get('computed', 0)} | "
            f"跳过: {result.get('skipped', 0)} | "
            f"失败: {result.get('failed', 0)} | "
            f"总计: {result.get('total', 0)}"
        )
    elif stage == "event":
        return (
            f"  聚类: {result.get('clustered', 0)} | "
            f"新建: {result.get('new_clusters', 0)} | "
            f"总计: {result.get('total_processed', 0)}"
        )
    elif stage == "topic":
        return f"  发现主题: {result.get('suggestions_count', 0)}"
    else:
        return f"  {json.dumps(result, ensure_ascii=False)}"


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

async def run_pipeline(
    stages: list[str],
    limit: int,
    skip_disabled: bool,
    verbose: bool,
) -> dict[str, dict]:
    """Run the specified pipeline stages sequentially.

    Args:
        stages: List of stage names to run.
        limit: Per-stage batch size limit.
        skip_disabled: Whether to skip feature-disabled stages.
        verbose: Enable verbose output.

    Returns:
        dict mapping stage name to its result dict.
    """
    from core.database import close_db

    # 预热 feature_config 缓存（避免事件循环冲突）
    from common.feature_config import feature_config
    await feature_config.async_reload()

    results: dict[str, dict] = {}

    try:
        for stage in stages:
            feature_key = STAGE_FEATURES.get(stage, "")
            enabled = feature_config.get_bool(feature_key, False)

            if not enabled and skip_disabled:
                _print(f"[{stage}] 功能未启用 ({feature_key}=false)，跳过", "warn")
                results[stage] = {"skipped": True, "reason": "feature disabled"}
                continue

            if not enabled and not skip_disabled:
                _print(
                    f"[{stage}] 功能未启用 ({feature_key}=false)，"
                    f"使用 --force 强制运行",
                    "warn",
                )

            desc = STAGE_DESCRIPTIONS.get(stage, stage)
            _print(f"[{stage}] 开始: {desc} (limit={limit})")

            t0 = time.time()
            try:
                result = await STAGE_RUNNERS[stage](limit, verbose)
            except Exception as e:
                logger.error(f"Stage '{stage}' failed: {e}", exc_info=verbose)
                result = {"error": str(e)}
            elapsed = time.time() - t0

            results[stage] = result

            # 打印阶段结果
            if "error" in result:
                _print(f"[{stage}] 失败 ({elapsed:.1f}s)", "error")
            else:
                _print(f"[{stage}] 完成 ({elapsed:.1f}s)", "success")
            print(_format_result(stage, result))
            print()
    finally:
        await close_db()

    return results


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="ResearchPulse v2 AI 流水线手动运行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s all                   # 运行全部阶段
  %(prog)s ai                    # 仅运行 AI 处理
  %(prog)s ai embedding          # 运行 AI 处理 + 嵌入计算
  %(prog)s embedding event topic # 运行嵌入 → 事件 → 主题
  %(prog)s all --limit 200       # 每阶段最多处理 200 条
  %(prog)s all --force            # 忽略功能开关，强制运行所有阶段

阶段说明:
  ai        AI 文章处理（摘要/分类/评分）   [feature.ai_processor]
  embedding 向量嵌入计算                     [feature.embedding]
  event     事件聚类                         [feature.event_clustering]
  topic     主题发现                         [feature.topic_radar]
""",
    )

    parser.add_argument(
        "stages",
        nargs="+",
        choices=list(STAGES) + ["all"],
        help="要运行的流水线阶段 (all = 全部按顺序运行)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="每阶段最多处理的文章数 (默认: 50)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="忽略功能开关，强制运行所有指定阶段",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细输出 (包含完整错误栈)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="以 JSON 格式输出结果",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 解析阶段列表
    if "all" in args.stages:
        stages = list(STAGES)
    else:
        # 按流水线依赖顺序排序，去重
        seen = set()
        stages = []
        for s in STAGES:
            if s in args.stages and s not in seen:
                stages.append(s)
                seen.add(s)

    if not stages:
        parser.error("未指定有效的流水线阶段")

    # 打印运行信息
    print()
    _print("=" * 50, "info")
    _print("ResearchPulse v2 AI 流水线", "info")
    _print("=" * 50, "info")
    print(f"阶段: {' → '.join(stages)}")
    print(f"Limit: {args.limit}")
    if args.force:
        print(f"{YELLOW}模式: 强制运行 (忽略功能开关){NC}")
    _print("-" * 50, "info")
    print()

    t_start = time.time()

    try:
        results = asyncio.run(
            run_pipeline(
                stages=stages,
                limit=args.limit,
                skip_disabled=not args.force,
                verbose=args.verbose,
            )
        )
    except KeyboardInterrupt:
        _print("\n用户中断", "warn")
        sys.exit(130)
    except Exception as e:
        _print(f"流水线执行失败: {e}", "error")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    t_total = time.time() - t_start

    # JSON 输出
    if args.json_output:
        # 移除不可序列化的 suggestions 详情
        safe = {}
        for k, v in results.items():
            if "suggestions" in v and isinstance(v["suggestions"], list):
                v = {**v, "suggestions": f"[{len(v['suggestions'])} items]"}
            safe[k] = v
        print(json.dumps(safe, ensure_ascii=False, indent=2))
        sys.exit(0)

    # 汇总
    _print("=" * 50, "info")
    _print("流水线执行完毕", "info")
    _print("=" * 50, "info")

    has_error = False
    for stage in stages:
        r = results.get(stage, {})
        if r.get("skipped"):
            status = f"{YELLOW}跳过{NC}"
        elif "error" in r:
            status = f"{RED}失败{NC}"
            has_error = True
        else:
            status = f"{GREEN}成功{NC}"
        desc = STAGE_DESCRIPTIONS.get(stage, stage)
        print(f"  {stage:12s} {desc:20s} [{status}]")

    print(f"\n总耗时: {t_total:.2f} 秒")
    sys.exit(1 if has_error else 0)


if __name__ == "__main__":
    main()
