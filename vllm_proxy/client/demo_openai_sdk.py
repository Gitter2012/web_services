# =============================================================================
# 模块: client/demo_openai_sdk.py
# 功能: 使用 OpenAI SDK 访问 vLLM Proxy 的示例
# 架构角色: 示例代码，展示 vLLM Proxy 与 OpenAI SDK 的兼容性。
# 设计理念: 证明 vLLM Proxy 的 API 完全兼容 OpenAI 格式，
#           使用户可以直接使用熟悉的 OpenAI SDK 而无需学习新 API。
# =============================================================================

"""使用 OpenAI SDK 访问 vLLM Proxy

vLLM Proxy 提供与 OpenAI 兼容的 API，因此可以直接使用 openai 库。

优势:
    - 无需修改现有代码，只需更改 base_url
    - 支持所有 OpenAI SDK 的功能（流式、异步等）
    - 兼容 LangChain、LlamaIndex 等框架
"""

import asyncio

from openai import AsyncOpenAI, OpenAI


# =============================================================================
# 示例 1: 使用 OpenAI SDK 同步客户端
# 职责: 展示最基本的 OpenAI SDK 使用方式
# =============================================================================
def demo_with_openai_sdk():
    """使用 OpenAI SDK（同步）

    展示如何使用 OpenAI 官方 SDK 访问 vLLM Proxy。
    只需设置 base_url 指向 vLLM Proxy 服务即可。
    """
    print("=" * 50)
    print("使用 OpenAI SDK 访问 vLLM Proxy")
    print("=" * 50)

    # 创建客户端
    # 注意: base_url 需要包含 /v1 路径
    client = OpenAI(
        base_url="http://localhost:8080/v1",  # 注意路径包含 /v1
        api_key="dummy"  # vLLM 不需要真实的 API key，但 openai 库需要这个参数
    )

    # 列出模型
    print("\n可用模型:")
    models = client.models.list()
    for model in models.data:
        print(f"  - {model.id}")

    # 聊天补全
    print("\n聊天补全:")
    response = client.chat.completions.create(
        model="llama2-7b-chat",
        messages=[
            {"role": "user", "content": "你好，请介绍一下自己"}
        ],
        temperature=0.7,
        max_tokens=256
    )
    print(f"助手: {response.choices[0].message.content}")

    # 流式输出
    print("\n流式输出:")
    stream = client.chat.completions.create(
        model="llama2-7b-chat",
        messages=[
            {"role": "user", "content": "讲一个短笑话"}
        ],
        stream=True,
        max_tokens=100
    )

    print("助手: ", end="", flush=True)
    for chunk in stream:
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
    print()


# =============================================================================
# 示例 2: 使用 API Key 认证
# 职责: 展示如何配置 API Key 认证
# =============================================================================
def demo_with_api_key():
    """使用 API Key 认证

    如果服务配置了 api_key，需要在客户端传入正确的 key。
    """
    print("=" * 50)
    print("使用 API Key 认证")
    print("=" * 50)

    # 如果服务配置了 api_key，需要传入正确的 key
    client = OpenAI(
        base_url="http://localhost:8080/v1",
        api_key="your-secret-api-key"  # 替换为配置中的 api_key
    )

    try:
        response = client.chat.completions.create(
            model="llama2-7b-chat",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=50
        )
        print(f"响应: {response.choices[0].message.content}")
    except Exception as e:
        print(f"错误: {e}")
        print("提示: 如果服务没有配置 api_key，请使用 'dummy' 作为 api_key")


# =============================================================================
# 示例 3: 使用 OpenAI SDK 异步客户端
# 职责: 展示异步客户端的使用
# =============================================================================
async def demo_async_openai():
    """使用 OpenAI SDK（异步）

    展示异步客户端的使用方式，适合高并发场景。
    """
    print("=" * 50)
    print("使用 OpenAI SDK（异步）")
    print("=" * 50)

    client = AsyncOpenAI(
        base_url="http://localhost:8080/v1",
        api_key="dummy"
    )

    async def send_request(prompt: str):
        """发送单个请求"""
        response = await client.chat.completions.create(
            model="llama2-7b-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50
        )
        return response.choices[0].message.content

    prompts = ["什么是 AI？", "什么是 ML？", "什么是 DL？"]

    print("\n并发发送请求...")
    # 并发发送多个请求
    results = await asyncio.gather(*[
        send_request(p) for p in prompts
    ])

    for prompt, result in zip(prompts, results):
        print(f"\nQ: {prompt}")
        print(f"A: {result}")


# =============================================================================
# 主入口
# =============================================================================
if __name__ == "__main__":
    # 运行示例
    demo_with_openai_sdk()
    # demo_with_api_key()
    # asyncio.run(demo_async_openai())
