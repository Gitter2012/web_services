#!/usr/bin/env python3
"""scripts 包初始化文件。

本模块是 ResearchPulse v2 的工具脚本包，提供以下功能：

数据同步与维护：
    - sync_arxiv_categories: 同步 arXiv 分类到数据库
    - repair_arxiv: 修复缺失的 arXiv 文章元数据
    - clean_thinking_in_articles: 清理 AI 生成的 thinking 标签

手动运行工具（以 _ 开头的文件为内部入口脚本）：
    - _crawl_runner: 手动触发爬虫任务
    - _email_runner: 邮件发送测试和通知触发
    - _ai_pipeline_runner: AI 处理流水线手动运行
    - reprocess_articles: 重新运行 AI 处理流程（调试/刷库）

用法示例：
    # 同步 arXiv 分类
    python scripts/sync_arxiv_categories.py

    # 修复缺失数据
    python scripts/repair_arxiv.py --dry-run

    # 运行爬虫
    python scripts/_crawl_runner.py arxiv cs.AI

    # 运行 AI 流水线
    python scripts/_ai_pipeline_runner.py all --limit 100
"""

__all__ = []
