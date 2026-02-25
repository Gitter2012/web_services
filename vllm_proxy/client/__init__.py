# =============================================================================
# 模块: client/__init__.py
# 功能: vLLM Proxy Client SDK 包初始化
# 架构角色: 包的入口文件，定义对外导出的模块和符号。
# 设计理念: 简洁地导出核心类，使用户可以通过 from client import VLLMProxyClient 使用。
# =============================================================================

"""vLLM Proxy Client SDK

提供简单的 Python 客户端用于访问 vLLM Proxy 服务

Usage:
    from client import VLLMProxyClient, VLLMProxyAsyncClient

    # 同步客户端
    with VLLMProxyClient("http://localhost:8080") as client:
        response = client.chat_completion(
            model="llama2-7b-chat",
            messages=[{"role": "user", "content": "Hello"}]
        )

    # 异步客户端
    async with VLLMProxyAsyncClient("http://localhost:8080") as client:
        response = await client.chat_completion(
            model="llama2-7b-chat",
            messages=[{"role": "user", "content": "Hello"}]
        )
"""

from .client import VLLMProxyAsyncClient, VLLMProxyClient

__version__ = "1.0.0"
__all__ = ["VLLMProxyClient", "VLLMProxyAsyncClient"]
