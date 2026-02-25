# =============================================================================
# 模块: client/demo_async.py
# 功能: 异步客户端使用示例
# 架构角色: 示例和文档代码，展示 VLLMProxyAsyncClient 的各种使用方式。
# 设计理念: 展示异步客户端的优势场景：并发请求、流式处理、负载测试等。
# =============================================================================

"""异步客户端使用示例

展示 VLLMProxyAsyncClient 的各种使用场景:
    - 基础聊天
    - 流式聊天
    - 并发请求
    - 负载测试
    - 模型生命周期管理
"""

import asyncio

from client import VLLMProxyAsyncClient


# =============================================================================
# 示例 1: 基础聊天
# 职责: 展示异步聊天的基本用法
# =============================================================================
async def demo_basic_chat():
    """基础聊天示例"""
    print("=" * 50)
    print("异步示例 1: 基础聊天")
    print("=" * 50)

    client = VLLMProxyAsyncClient(base_url="http://localhost:8080")

    try:
        # 检查服务健康状态
        health = await client.health_check()
        print(f"服务状态: {health['status']}")
        print(f"GPU: {health['gpu']['name']}")
        print()

        # 列出可用模型
        models = await client.list_models()
        print("可用模型:")
        for model in models:
            print(f"  - {model['id']}: {model.get('status', 'unknown')}")
        print()

        # 简单对话
        response = await client.chat_completion(
            model="llama2-7b-chat",
            messages=[
                {"role": "user", "content": "你好，请介绍一下自己"}
            ],
            temperature=0.7,
            max_tokens=256
        )

        print("助手回复:")
        print(response['choices'][0]['message']['content'])
        print()

    finally:
        await client.close()


# =============================================================================
# 示例 2: 流式聊天
# 职责: 展示异步流式输出
# =============================================================================
async def demo_stream_chat():
    """流式聊天示例"""
    print("=" * 50)
    print("异步示例 2: 流式聊天")
    print("=" * 50)

    client = VLLMProxyAsyncClient(base_url="http://localhost:8080")

    try:
        print("助手回复: ", end="", flush=True)

        # 使用异步生成器逐块获取响应
        async for text in client.chat_completion_stream(
            model="llama2-7b-chat",
            messages=[
                {"role": "user", "content": "讲一个短笑话"}
            ],
            temperature=0.8,
            max_tokens=200
        ):
            print(text, end="", flush=True)

        print("\n")

    finally:
        await client.close()


# =============================================================================
# 示例 3: 并发请求
# 职责: 展示异步客户端的并发优势
# =============================================================================
async def demo_concurrent_requests():
    """并发请求示例

    展示如何使用 asyncio.gather 并发发送多个请求。
    这是异步客户端相对于同步客户端的主要优势。
    """
    print("=" * 50)
    print("异步示例 3: 并发请求")
    print("=" * 50)

    client = VLLMProxyAsyncClient(base_url="http://localhost:8080")

    async def send_request(prompt: str) -> str:
        """发送单个请求的辅助函数"""
        response = await client.chat_completion(
            model="llama2-7b-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100
        )
        return response['choices'][0]['message']['content']

    try:
        prompts = [
            "什么是 Python？",
            "什么是 JavaScript？",
            "什么是 Go？",
        ]

        # 并发发送所有请求（同时发送，并行处理）
        print("并发发送 3 个请求...")
        results = await asyncio.gather(*[
            send_request(p) for p in prompts
        ])

        for prompt, result in zip(prompts, results):
            print(f"\n问题: {prompt}")
            print(f"回答: {result[:100]}...")

    finally:
        await client.close()


# =============================================================================
# 示例 4: 负载测试
# 职责: 展示如何进行简单的性能测试
# =============================================================================
async def demo_load_balance():
    """负载测试示例

    展示如何测试服务的吞吐量和延迟。
    """
    print("=" * 50)
    print("异步示例 4: 负载测试")
    print("=" * 50)

    client = VLLMProxyAsyncClient(base_url="http://localhost:8080")

    async def single_request(idx: int) -> float:
        """发送单个请求并返回耗时"""
        import time
        start = time.time()

        response = await client.chat_completion(
            model="llama2-7b-chat",
            messages=[{"role": "user", "content": f"这是第 {idx} 个测试请求"}],
            max_tokens=50
        )

        elapsed = time.time() - start
        return elapsed

    try:
        num_requests = 10
        print(f"发送 {num_requests} 个并发请求...")

        start = asyncio.get_event_loop().time()
        times = await asyncio.gather(*[
            single_request(i) for i in range(num_requests)
        ])
        total_time = asyncio.get_event_loop().time() - start

        print(f"\n总耗时: {total_time:.2f}s")
        print(f"平均耗时: {sum(times)/len(times):.2f}s")
        print(f"最小耗时: {min(times):.2f}s")
        print(f"最大耗时: {max(times):.2f}s")
        print(f"吞吐量: {num_requests/total_time:.2f} req/s")

    finally:
        await client.close()


# =============================================================================
# 示例 5: 模型生命周期管理
# 职责: 展示异步的模型管理操作
# =============================================================================
async def demo_model_lifecycle():
    """模型生命周期管理示例"""
    print("=" * 50)
    print("异步示例 5: 模型生命周期管理")
    print("=" * 50)

    client = VLLMProxyAsyncClient(base_url="http://localhost:8080")

    try:
        # 检查初始状态
        print("初始状态:")
        health = await client.health_check()
        print(f"  已加载模型: {health['loaded_models']}")
        print()

        # 加载模型
        print("加载模型...")
        result = await client.load_model("llama2-7b-chat")
        print(f"  结果: {result['success']}")
        print()

        # 等待模型就绪
        await asyncio.sleep(2)

        # 检查状态
        print("加载后状态:")
        health = await client.health_check()
        print(f"  已加载模型: {health['loaded_models']}")
        print()

        # 发送请求
        print("发送请求...")
        response = await client.chat_completion(
            model="llama2-7b-chat",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=30
        )
        print(f"  响应: {response['choices'][0]['message']['content']}")
        print()

        # 卸载模型
        print("卸载模型...")
        result = await client.unload_model("llama2-7b-chat")
        print(f"  结果: {result['success']}")

    finally:
        await client.close()


# =============================================================================
# 示例 6: 异步上下文管理器
# 职责: 展示使用 async with 语句
# =============================================================================
async def demo_with_context_manager():
    """使用异步上下文管理器"""
    print("=" * 50)
    print("异步示例 6: 使用上下文管理器")
    print("=" * 50)

    # 使用 async with 语句，退出时自动调用 close()
    async with VLLMProxyAsyncClient(base_url="http://localhost:8080") as client:
        response = await client.chat_completion(
            model="llama2-7b-chat",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=50
        )
        print(f"响应: {response['choices'][0]['message']['content']}")


# =============================================================================
# 主入口
# 职责: 提供示例选择和运行入口
# =============================================================================
async def main():
    """运行所有示例"""
    # 选择要运行的示例

    await demo_basic_chat()
    # await demo_stream_chat()
    # await demo_concurrent_requests()
    # await demo_load_balance()
    # await demo_model_lifecycle()
    # await demo_with_context_manager()


if __name__ == "__main__":
    print("请取消注释要运行的示例函数")
    print("确保服务已启动: ./scripts/start.sh")
    print()

    # 运行选中的示例
    # asyncio.run(main())
