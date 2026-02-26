# =============================================================================
# 模块: client/demo_sync.py
# 功能: 同步客户端使用示例
# 架构角色: 示例和文档代码，展示 VLLMProxyClient 的各种使用方式。
# 设计理念: 通过多个独立函数展示不同场景的使用方法，便于用户参考和复制。
# =============================================================================

"""同步客户端使用示例

展示 VLLMProxyClient 的各种使用场景:
    - 基础聊天
    - 流式聊天
    - 多轮对话
    - 模型管理
    - 文本补全
    - 嵌入向量
"""

from client import VLLMProxyClient


# =============================================================================
# 示例 1: 基础聊天
# 职责: 展示最简单的聊天补全调用
# =============================================================================
def demo_basic_chat():
    """基础聊天示例

    展示如何发送简单的聊天请求并获取响应。
    """
    print("=" * 50)
    print("示例 1: 基础聊天")
    print("=" * 50)

    # 创建客户端（如果服务配置了 API Key，需要传入）
    client = VLLMProxyClient(
        base_url="http://localhost:8080",
        # api_key="your-api-key"  # 如果需要认证
    )

    try:
        # 检查服务健康状态
        health = client.health_check()
        print(f"服务状态: {health['status']}")
        print(f"GPU: {health['gpu']['name']}")
        print(f"已加载模型数: {health['loaded_models']}")
        print()

        # 列出可用模型
        models = client.list_models()
        print("可用模型:")
        for model in models:
            print(f"  - {model['id']}: {model.get('status', 'unknown')}")
        print()

        # 简单对话
        response = client.chat_completion(
            model="llama2-7b-chat",  # 替换为你的模型 ID
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
        client.close()


# =============================================================================
# 示例 2: 流式聊天
# 职责: 展示如何使用流式输出
# =============================================================================
def demo_stream_chat():
    """流式聊天示例

    展示如何使用流式输出实时显示生成的文本。
    """
    print("=" * 50)
    print("示例 2: 流式聊天")
    print("=" * 50)

    client = VLLMProxyClient(base_url="http://localhost:8080")

    try:
        print("助手回复: ", end="", flush=True)

        # 使用生成器逐块获取响应
        for text in client.chat_completion_stream(
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
        client.close()


# =============================================================================
# 示例 3: 多轮对话
# 职责: 展示如何维护对话上下文
# =============================================================================
def demo_multi_turn():
    """多轮对话示例

    展示如何维护消息列表以实现多轮对话。
    """
    print("=" * 50)
    print("示例 3: 多轮对话")
    print("=" * 50)

    client = VLLMProxyClient(base_url="http://localhost:8080")

    try:
        # 初始化消息列表，包含系统提示
        messages = [
            {"role": "system", "content": "你是一个有帮助的助手。"}
        ]

        # 第一轮对话
        messages.append({"role": "user", "content": "什么是机器学习？"})
        response = client.chat_completion(
            model="llama2-7b-chat",
            messages=messages,
            max_tokens=200
        )
        reply = response['choices'][0]['message']['content']
        print(f"用户: 什么是机器学习？")
        print(f"助手: {reply}\n")
        # 将助手的回复加入消息列表，保持上下文
        messages.append({"role": "assistant", "content": reply})

        # 第二轮对话（模型能理解上下文）
        messages.append({"role": "user", "content": "深度学习呢？"})
        response = client.chat_completion(
            model="llama2-7b-chat",
            messages=messages,
            max_tokens=200
        )
        reply = response['choices'][0]['message']['content']
        print(f"用户: 深度学习呢？")
        print(f"助手: {reply}\n")

    finally:
        client.close()


# =============================================================================
# 示例 4: 模型管理
# 职责: 展示如何手动管理模型的生命周期
# =============================================================================
def demo_model_management():
    """模型管理示例

    展示如何手动预加载和卸载模型。
    """
    print("=" * 50)
    print("示例 4: 模型管理")
    print("=" * 50)

    client = VLLMProxyClient(base_url="http://localhost:8080")

    try:
        # 预加载模型（无需等待请求触发）
        print("预加载模型...")
        result = client.load_model("llama2-7b-chat")
        print(f"加载结果: {result}")
        print()

        # 检查模型状态
        model_info = client.get_model("llama2-7b-chat")
        print(f"模型状态: {model_info}")
        print()

        # 使用已加载的模型
        response = client.chat_completion(
            model="llama2-7b-chat",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=50
        )
        print(f"响应: {response['choices'][0]['message']['content']}")
        print()

        # 手动卸载模型释放资源
        print("卸载模型...")
        result = client.unload_model("llama2-7b-chat")
        print(f"卸载结果: {result}")

    finally:
        client.close()


# =============================================================================
# 示例 5: 文本补全
# 职责: 展示文本补全接口的使用
# =============================================================================
def demo_text_completion():
    """文本补全示例

    展示如何使用文本补全（非聊天）接口。
    """
    print("=" * 50)
    print("示例 5: 文本补全")
    print("=" * 50)

    client = VLLMProxyClient(base_url="http://localhost:8080")

    try:
        response = client.text_completion(
            model="llama2-7b-chat",
            prompt="Once upon a time",
            temperature=0.8,
            max_tokens=100
        )

        print(f"补全结果: {response['choices'][0]['text']}")

    finally:
        client.close()


# =============================================================================
# 示例 6: 嵌入向量
# 职责: 展示如何获取文本嵌入向量
# =============================================================================
def demo_embeddings():
    """嵌入向量示例

    展示如何将文本转换为向量表示。
    """
    print("=" * 50)
    print("示例 6: 文本嵌入")
    print("=" * 50)

    client = VLLMProxyClient(base_url="http://localhost:8080")

    try:
        response = client.embeddings(
            model="bge-large-zh",  # 需要配置嵌入模型
            input_text="这是一段测试文本"
        )

        embedding = response['data'][0]['embedding']
        print(f"向量维度: {len(embedding)}")
        print(f"前 5 个值: {embedding[:5]}")

    finally:
        client.close()


# =============================================================================
# 示例 7: 上下文管理器
# 职责: 展示使用 with 语句自动管理资源
# =============================================================================
def demo_with_context_manager():
    """使用上下文管理器

    展示使用 with 语句自动关闭客户端。
    """
    print("=" * 50)
    print("示例 7: 使用上下文管理器")
    print("=" * 50)

    # 使用 with 语句，退出时自动调用 close()
    with VLLMProxyClient(base_url="http://localhost:8080") as client:
        response = client.chat_completion(
            model="llama2-7b-chat",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=50
        )
        print(f"响应: {response['choices'][0]['message']['content']}")


# =============================================================================
# 主入口
# 职责: 提供示例选择和运行入口
# =============================================================================
if __name__ == "__main__":
    # 运行示例（根据你的环境选择）

    # demo_basic_chat()
    # demo_stream_chat()
    # demo_multi_turn()
    # demo_model_management()
    # demo_text_completion()
    # demo_embeddings()
    # demo_with_context_manager()

    print("请取消注释要运行的示例函数")
    print("确保服务已启动: ./scripts/start.sh")
