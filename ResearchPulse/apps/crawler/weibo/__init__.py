# =============================================================================
# 模块: apps/crawler/weibo
# 功能: 微博热搜数据爬取模块
# 架构角色: 爬虫子系统的一个具体实现，负责从微博获取热搜榜单数据
# 支持榜单: 热搜榜(realtimehot)、要闻榜(socialevent)、文娱榜(entrank)、
#          体育榜(sport)、游戏榜(game)
# =============================================================================

"""Weibo hot search crawler module."""

from apps.crawler.weibo.crawler import WeiboCrawler

__all__ = ["WeiboCrawler"]
