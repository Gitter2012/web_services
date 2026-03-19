# =============================================================================
# 模块: common/wechat_mp/__init__.py
# 功能: 微信公众号通用模块
# 架构角色: 通用基础设施层，提供微信公众号 API 集成能力
# 设计决策:
#   - 放置在 common 目录下，与业务逻辑解耦，可被任意 app 模块复用
#   - 提供 API 客户端、Token 管理、草稿推送等子模块
# =============================================================================

"""WeChat Official Account (微信公众号) integration module.

Provides:
- WeChatMPClient: API client for WeChat MP platform
- TokenManager: Access token lifecycle management with caching
- WeChatDraftService: Draft article push service
"""

from common.wechat_mp.client import WeChatMPClient
from common.wechat_mp.token_manager import TokenManager

__all__ = [
    "WeChatMPClient",
    "TokenManager",
]
