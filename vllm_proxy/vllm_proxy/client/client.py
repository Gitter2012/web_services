# =============================================================================
# 模块: client/client.py
# 功能: vLLM Proxy 客户端 SDK，支持同步和异步两种调用模式
# 架构角色: 客户端 SDK 层。封装 HTTP 请求细节，提供简洁的 Python API，
#           使开发者能够轻松调用 vLLM Proxy 服务。
# 设计理念: 提供同步（VLLMProxyClient）和异步（VLLMProxyAsyncClient）两种客户端，
#           适应不同的使用场景；支持流式和非流式响应；支持上下文管理器模式。
# =============================================================================

"""vLLM Proxy 客户端实现

支持同步和异步两种模式
"""

import json
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

import aiohttp
import requests


# =============================================================================
# VLLMProxyClient 类
# 职责: 同步客户端实现
# 设计决策:
#   1. 使用 requests 库实现同步 HTTP 请求
#   2. 支持上下文管理器模式（with 语句）
#   3. 支持 API Key 认证
# =============================================================================
class VLLMProxyClient:
    """同步客户端

    提供同步方式调用 vLLM Proxy 服务的 API。

    Attributes:
        base_url: 服务地址
        api_key: API Key（可选）
        timeout: 请求超时时间（秒）
        session: requests Session 对象
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        api_key: Optional[str] = None,
        timeout: float = 300.0
    ):
        """初始化客户端

        Args:
            base_url: 服务地址（默认: http://localhost:8080）
            api_key: API Key（如果服务配置了认证）
            timeout: 请求超时时间（秒），默认 5 分钟
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()

        # 设置默认请求头
        self.session.headers.update({
            "Content-Type": "application/json"
        })

        # 添加认证头（如果提供了 API Key）
        if api_key:
            self.session.headers.update({
                "Authorization": f"Bearer {api_key}"
            })

    def _make_url(self, path: str) -> str:
        """构建完整 URL

        Args:
            path: API 路径

        Returns:
            完整的 URL
        """
        return f"{self.base_url}{path}"

    def health_check(self) -> Dict[str, Any]:
        """健康检查

        Returns:
            服务健康状态信息
        """
        response = self.session.get(
            self._make_url("/health"),
            timeout=10.0
        )
        response.raise_for_status()
        return response.json()

    def list_models(self) -> List[Dict[str, Any]]:
        """列出可用模型

        Returns:
            模型列表，每个元素包含模型 ID、状态等信息
        """
        response = self.session.get(
            self._make_url("/v1/models"),
            timeout=self.timeout
        )
        response.raise_for_status()
        data = response.json()
        return data.get("data", [])

    def get_model(self, model_id: str) -> Dict[str, Any]:
        """获取模型详情

        Args:
            model_id: 模型标识符

        Returns:
            模型详细信息
        """
        response = self.session.get(
            self._make_url(f"/v1/models/{model_id}"),
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def load_model(self, model_id: str) -> Dict[str, Any]:
        """预加载模型

        手动触发模型加载，无需等待请求触发。

        Args:
            model_id: 模型标识符

        Returns:
            加载结果
        """
        response = self.session.post(
            self._make_url(f"/admin/models/{model_id}/load"),
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def unload_model(self, model_id: str) -> Dict[str, Any]:
        """卸载模型

        手动卸载模型以释放显存资源。

        Args:
            model_id: 模型标识符

        Returns:
            卸载结果
        """
        response = self.session.post(
            self._make_url(f"/admin/models/{model_id}/unload"),
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 256,
        top_p: float = 1.0,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """聊天补全

        发送聊天补全请求，返回模型生成的回复。

        Args:
            model: 模型标识符
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}]
            temperature: 采样温度（0-2），越高输出越随机
            max_tokens: 最大生成 token 数
            top_p: 核采样参数（0-1）
            stream: 是否流式输出（此方法仅支持 False）
            **kwargs: 其他参数（如 stop, presence_penalty 等）

        Returns:
            补全结果，包含生成的消息内容
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": stream,
            **kwargs
        }

        response = self.session.post(
            self._make_url("/v1/chat/completions"),
            json=payload,
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def chat_completion_stream(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 256,
        top_p: float = 1.0,
        **kwargs
    ) -> Iterator[str]:
        """流式聊天补全

        以生成器形式返回流式响应，适合实时显示输出。

        Args:
            model: 模型标识符
            messages: 消息列表
            temperature: 采样温度
            max_tokens: 最大生成 token 数
            top_p: 核采样参数
            **kwargs: 其他参数

        Yields:
            生成的文本片段
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": True,
            **kwargs
        }

        response = self.session.post(
            self._make_url("/v1/chat/completions"),
            json=payload,
            stream=True,
            timeout=self.timeout
        )
        response.raise_for_status()

        # 解析 SSE 流
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    data = line[6:]
                    if data == '[DONE]':
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk.get('choices', [{}])[0].get('delta', {})
                        content = delta.get('content', '')
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    def text_completion(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 256,
        **kwargs
    ) -> Dict[str, Any]:
        """文本补全

        发送文本补全请求，根据提示生成文本。

        Args:
            model: 模型标识符
            prompt: 提示文本
            temperature: 采样温度
            max_tokens: 最大生成 token 数
            **kwargs: 其他参数

        Returns:
            补全结果
        """
        payload = {
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }

        response = self.session.post(
            self._make_url("/v1/completions"),
            json=payload,
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def embeddings(
        self,
        model: str,
        input_text: str
    ) -> Dict[str, Any]:
        """获取文本嵌入向量

        将文本转换为向量表示。

        Args:
            model: 模型标识符
            input_text: 输入文本

        Returns:
            嵌入向量结果
        """
        payload = {
            "model": model,
            "input": input_text
        }

        response = self.session.post(
            self._make_url("/v1/embeddings"),
            json=payload,
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def close(self):
        """关闭客户端

        释放 requests Session 资源。
        """
        self.session.close()

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()


# =============================================================================
# VLLMProxyAsyncClient 类
# 职责: 异步客户端实现
# 设计决策:
#   1. 使用 aiohttp 库实现异步 HTTP 请求
#   2. 支持异步上下文管理器模式（async with 语句）
#   3. 延迟创建 session，支持多次使用
# =============================================================================
class VLLMProxyAsyncClient:
    """异步客户端

    提供异步方式调用 vLLM Proxy 服务的 API。
    适用于高并发场景。

    Attributes:
        base_url: 服务地址
        api_key: API Key（可选）
        timeout: 请求超时时间
        _session: aiohttp ClientSession 对象（延迟创建）
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        api_key: Optional[str] = None,
        timeout: float = 300.0
    ):
        """初始化异步客户端

        Args:
            base_url: 服务地址
            api_key: API Key（可选）
            timeout: 请求超时时间（秒）
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 session

        延迟创建 session，支持复用。

        Returns:
            aiohttp ClientSession 实例
        """
        if self._session is None or self._session.closed:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=self.timeout
            )
        return self._session

    def _make_url(self, path: str) -> str:
        """构建完整 URL"""
        return f"{self.base_url}{path}"

    async def health_check(self) -> Dict[str, Any]:
        """健康检查

        Returns:
            服务健康状态信息
        """
        session = await self._get_session()
        async with session.get(self._make_url("/health")) as response:
            response.raise_for_status()
            return await response.json()

    async def list_models(self) -> List[Dict[str, Any]]:
        """列出可用模型"""
        session = await self._get_session()
        async with session.get(self._make_url("/v1/models")) as response:
            response.raise_for_status()
            data = await response.json()
            return data.get("data", [])

    async def get_model(self, model_id: str) -> Dict[str, Any]:
        """获取模型详情"""
        session = await self._get_session()
        async with session.get(self._make_url(f"/v1/models/{model_id}")) as response:
            response.raise_for_status()
            return await response.json()

    async def load_model(self, model_id: str) -> Dict[str, Any]:
        """预加载模型"""
        session = await self._get_session()
        async with session.post(self._make_url(f"/admin/models/{model_id}/load")) as response:
            response.raise_for_status()
            return await response.json()

    async def unload_model(self, model_id: str) -> Dict[str, Any]:
        """卸载模型"""
        session = await self._get_session()
        async with session.post(self._make_url(f"/admin/models/{model_id}/unload")) as response:
            response.raise_for_status()
            return await response.json()

    async def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 256,
        top_p: float = 1.0,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """聊天补全"""
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": stream,
            **kwargs
        }

        session = await self._get_session()
        async with session.post(
            self._make_url("/v1/chat/completions"),
            json=payload
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def chat_completion_stream(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 256,
        top_p: float = 1.0,
        **kwargs
    ) -> AsyncIterator[str]:
        """流式聊天补全

        Yields:
            生成的文本片段
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": True,
            **kwargs
        }

        session = await self._get_session()
        async with session.post(
            self._make_url("/v1/chat/completions"),
            json=payload
        ) as response:
            response.raise_for_status()

            # 解析 SSE 流
            async for line in response.content:
                line = line.decode('utf-8').strip()
                if line.startswith('data: '):
                    data = line[6:]
                    if data == '[DONE]':
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk.get('choices', [{}])[0].get('delta', {})
                        content = delta.get('content', '')
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    async def text_completion(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 256,
        **kwargs
    ) -> Dict[str, Any]:
        """文本补全"""
        payload = {
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }

        session = await self._get_session()
        async with session.post(
            self._make_url("/v1/completions"),
            json=payload
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def embeddings(
        self,
        model: str,
        input_text: str
    ) -> Dict[str, Any]:
        """获取文本嵌入向量"""
        payload = {
            "model": model,
            "input": input_text
        }

        session = await self._get_session()
        async with session.post(
            self._make_url("/v1/embeddings"),
            json=payload
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def close(self):
        """关闭客户端

        释放 aiohttp ClientSession 资源。
        """
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
