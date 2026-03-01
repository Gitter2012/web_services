# =============================================================================
# 模块: apps/crawler/base.py
# 功能: 爬虫基类模块，定义了所有爬虫的统一接口和通用行为
# 架构角色: 爬虫子系统的核心抽象层。采用模板方法模式(Template Method Pattern)，
#           将爬取流程（fetch -> parse -> save -> run）标准化。
#           所有具体爬虫（ArXiv、RSS、微信公众号）都必须继承此基类，
#           并实现 fetch() 和 parse() 两个抽象方法。
# 设计理念: 通过抽象基类强制子类遵循统一的爬取协议，同时将去重存储、
#           错误处理、运行日志等通用逻辑集中在基类中，避免子类重复实现。
# =============================================================================

"""Base crawler class for ResearchPulse v2."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.crawler.models import Article

# 模块级日志器，用于记录爬虫基类的通用操作日志
logger = logging.getLogger(__name__)


# =============================================================================
# BaseCrawler 抽象基类
# 职责: 定义爬虫的标准生命周期（获取 -> 解析 -> 存储 -> 执行）
# 设计决策:
#   1. 使用 ABC 抽象基类确保子类必须实现 fetch() 和 parse()
#   2. save() 提供了带去重逻辑的默认实现，子类一般无需重写
#   3. run() 是主入口方法，编排完整的爬取流程
#   4. 每个爬虫实例绑定一个 source_type 和 source_id，用于数据归属和去重
# =============================================================================
class BaseCrawler(ABC):
    """Abstract base class for all crawlers.

    Subclasses must implement:
    - fetch(): Fetch raw data from source
    - parse(): Parse raw data into article dictionaries
    """

    # 子类必须定义 source_type，用于标识数据来源类型
    source_type: str  # 'arxiv', 'rss', 'wechat'
    # source_id 标识具体的数据源（如 arXiv 分类代码、RSS Feed ID、微信公众号名称）
    source_id: str  # Category code, feed ID, or account name

    def __init__(self, source_id: str):
        """Initialize a crawler instance.

        初始化爬虫实例。

        Args:
            source_id: Unique source identifier, e.g. "cs.AI", "feed-123".
        """
        self.source_id = source_id
        # 创建带有来源类型和来源ID的日志器，方便在日志中快速定位问题
        self.logger = logging.getLogger(f"{__name__}.{self.source_type}.{source_id}")

    @abstractmethod
    async def fetch(self) -> Any:
        """Fetch raw data from the source.

        从数据源获取原始数据（抽象方法，子类必须实现）。

        Returns:
            Any: Raw data from the source (str/dict/list etc.).
        """
        # 不同的数据源返回不同格式的原始数据：
        # - ArXiv: 返回包含论文列表和运行日期的字典
        # - RSS: 返回 XML 格式的 RSS Feed 字符串
        # - 微信: 返回 RSS Feed 字符串（通过 RSSHub 中转）
        pass

    @abstractmethod
    async def parse(self, raw_data: Any) -> List[Dict[str, Any]]:
        """将原始数据解析为文章字典列表（抽象方法，子类必须实现）。

        Args:
            raw_data: Raw data from fetch()

        Returns:
            List of article dictionaries with keys matching Article model
        """
        # 解析后的字典键名必须与 Article 模型的字段名对应，
        # 以便 save() 方法能直接创建或更新数据库记录
        pass

    async def save(self, articles: List[Dict[str, Any]], session: AsyncSession) -> tuple[int, List[int]]:
        """将文章列表保存到数据库，带有去重逻辑。

        去重策略:
            - ArXiv: 通过 arxiv_id 全局去重（不使用 source_id）
            - 其他源: 通过 (source_type, source_id, external_id) 三元组唯一标识
        如果文章已存在则更新非空字段，否则创建新记录。

        Args:
            articles: List of article dictionaries
            session: Database session

        Returns:
            Tuple of (Number of new articles saved, List of saved article IDs)
        """
        # 空列表直接返回，避免不必要的数据库操作
        if not articles:
            return 0, []

        saved_count = 0
        saved_ids: List[int] = []
        for article_data in articles:
            try:
                # 提取文章的外部唯一标识，用于去重判断
                # external_id 来自数据源本身的ID（如 arXiv ID、文章 GUID 等）
                external_id = article_data.get("external_id", "")
                url = article_data.get("url", "")
                arxiv_id = article_data.get("arxiv_id", "")

                # 根据数据源类型选择不同的去重策略
                existing = None

                if self.source_type == "arxiv" and arxiv_id:
                    # ArXiv 论文使用 arxiv_id 全局去重
                    # 这样同一篇论文不会因为属于多个分类而重复
                    stmt = select(Article).where(
                        Article.source_type == self.source_type,
                        Article.arxiv_id == arxiv_id,
                    )
                    result = await session.execute(stmt)
                    existing = result.scalar_one_or_none()
                else:
                    # 其他数据源使用三元组去重
                    # 通过 (source_type, source_id, external_id) 查询是否已存在
                    stmt = select(Article).where(
                        Article.source_type == self.source_type,
                        Article.source_id == self.source_id,
                        Article.external_id == external_id,
                    )
                    result = await session.execute(stmt)
                    existing = result.scalar_one_or_none()

                if existing:
                    # 文章已存在：更新已有记录，优先使用更完整的数据
                    # 仅在新值非空且比旧值更完整时才更新
                    for key, value in article_data.items():
                        if hasattr(existing, key) and value is not None:
                            existing_value = getattr(existing, key, None)
                            # 对于字符串类型，只有新值更长或旧值为空时才更新
                            if isinstance(value, str):
                                if value and (not existing_value or len(value) >= len(str(existing_value))):
                                    setattr(existing, key, value)
                            else:
                                # 非字符串类型，仅当旧值为空时更新
                                if value is not None and existing_value is None:
                                    setattr(existing, key, value)
                    # 更新修改时间，用于追踪数据变化
                    existing.updated_at = datetime.now(timezone.utc)
                    # 记录已存在文章的 ID（用于翻译钩子）
                    if existing.id:
                        saved_ids.append(existing.id)
                else:
                    # 文章不存在：创建新记录
                    # 自动填入 source_type、source_id 和 crawl_time
                    # 过滤掉非 Article 模型字段，避免子类爬虫传入额外字段导致 TypeError
                    valid_columns = {c.key for c in Article.__table__.columns}
                    filtered_data = {k: v for k, v in article_data.items() if k in valid_columns}
                    article = Article(
                        source_type=self.source_type,
                        source_id=self.source_id,
                        crawl_time=datetime.now(timezone.utc),
                        **filtered_data,
                    )
                    session.add(article)
                    saved_count += 1

            except Exception as e:
                # 单篇文章保存失败不影响其他文章的处理
                # 增强错误日志，记录文章关键信息便于排查
                article_title = article_data.get('title', 'N/A')
                article_url = article_data.get('url', 'N/A')
                article_external_id = article_data.get('external_id', 'N/A')
                self.logger.error(
                    f"Failed to save article: title='{article_title[:50] if len(article_title) > 50 else article_title}', "
                    f"external_id='{article_external_id}', url='{article_url}': {e}"
                )
                continue

        # flush() 将挂起的操作发送到数据库，但不提交事务
        # 这样可以获取新创建文章的 ID
        await session.flush()

        # 收集新创建文章的 ID
        for article_data in articles:
            # 新创建的文章没有 ID，需要从 session 中获取
            # 通过 arxiv_id 或 external_id 查询刚保存的文章 ID
            arxiv_id = article_data.get("arxiv_id", "")
            external_id = article_data.get("external_id", "")
            if arxiv_id and self.source_type == "arxiv":
                stmt = select(Article.id).where(
                    Article.source_type == self.source_type,
                    Article.arxiv_id == arxiv_id,
                )
                result = await session.execute(stmt)
                article_id = result.scalar_one_or_none()
                if article_id and article_id not in saved_ids:
                    saved_ids.append(article_id)
            elif external_id:
                stmt = select(Article.id).where(
                    Article.source_type == self.source_type,
                    Article.source_id == self.source_id,
                    Article.external_id == external_id,
                )
                result = await session.execute(stmt)
                article_id = result.scalar_one_or_none()
                if article_id and article_id not in saved_ids:
                    saved_ids.append(article_id)

        return saved_count, saved_ids

    async def run(self) -> Dict[str, Any]:
        """执行完整的爬取流程（主入口方法）。

        流程步骤:
            1. fetch() - 从数据源获取原始数据
            2. parse() - 将原始数据解析为文章字典
            3. save()  - 将解析后的文章保存到数据库（带去重）
            4. commit  - 提交数据库事务

        Returns:
            Dictionary with crawl results
        """
        # 记录爬取开始时间，用于计算耗时
        start_time = datetime.now(timezone.utc)
        self.logger.info(f"Starting crawl for {self.source_type}:{self.source_id}")

        try:
            # 第一步：从数据源获取原始数据
            # Fetch raw data
            raw_data = await self.fetch()

            # 第二步：将原始数据解析为标准化的文章字典列表
            # Parse into articles
            articles = await self.parse(raw_data)

            # 第三步：获取数据库会话并保存文章
            # 延迟导入 get_session_factory 避免循环导入问题
            # Save to database
            from core.database import get_session_factory
            factory = get_session_factory()
            async with factory() as session:
                saved_count, saved_ids = await self.save(articles, session)
                # 提交事务，确保所有数据持久化
                await session.commit()

            # 计算爬取耗时
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()

            # 构建成功结果字典，包含关键统计指标
            result = {
                "source_type": self.source_type,
                "source_id": self.source_id,
                "fetched_count": len(articles),   # 总共获取的文章数
                "saved_count": saved_count,        # 新增保存的文章数（去重后）
                "saved_ids": saved_ids,            # 保存的文章 ID 列表（用于后续翻译）
                "duration_seconds": duration,      # 爬取总耗时（秒）
                "status": "success",
                "timestamp": end_time.isoformat(),
            }

            self.logger.info(f"Crawl completed: {saved_count} new articles in {duration:.2f}s")
            return result

        except Exception as e:
            # 捕获所有异常，记录完整的堆栈信息（exception 会自动附带 traceback）
            # 返回错误结果字典而非抛出异常，确保调用者能正常处理失败情况
            self.logger.exception(f"Crawl failed: {e}")
            return {
                "source_type": self.source_type,
                "source_id": self.source_id,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    async def delay(self, base: float = 3.0, jitter: float = 1.0) -> None:
        """添加带随机抖动的延迟，用于规避目标站点的速率限制。

        通过在基础延迟上叠加随机抖动，使请求间隔不完全相同，
        降低被目标服务器识别为爬虫的概率。

        参数:
            base: 基础延迟时间（秒），默认 3.0 秒
            jitter: 随机抖动的最大值（秒），实际抖动为 [0, jitter) 的均匀分布
        """
        import random

        # 实际延迟 = 基础延迟 + 随机抖动值
        delay_time = base + random.uniform(0, jitter)
        await asyncio.sleep(delay_time)
