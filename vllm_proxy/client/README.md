# vLLM Proxy Client SDK

Python 客户端 SDK，用于访问 vLLM Proxy 服务。

## 安装

```bash
# 安装客户端依赖
pip install -r client/requirements.txt

# 或者使用 OpenAI SDK
pip install openai
```

## 快速开始

### 同步客户端

```python
from client import VLLMProxyClient

# 创建客户端
client = VLLMProxyClient(
    base_url="http://localhost:8080",
    api_key="your-api-key"  # 如果服务配置了认证
)

# 聊天补全
response = client.chat_completion(
    model="llama2-7b-chat",
    messages=[
        {"role": "user", "content": "Hello!"}
    ]
)
print(response['choices'][0]['message']['content'])

# 流式输出
for text in client.chat_completion_stream(
    model="llama2-7b-chat",
    messages=[{"role": "user", "content": "讲个笑话"}]
):
    print(text, end="")
```

### 异步客户端

```python
import asyncio
from client import VLLMProxyAsyncClient

async def main():
    client = VLLMProxyAsyncClient(base_url="http://localhost:8080")

    # 聊天补全
    response = await client.chat_completion(
        model="llama2-7b-chat",
        messages=[{"role": "user", "content": "Hello!"}]
    )
    print(response['choices'][0]['message']['content'])

    # 流式输出
    async for text in client.chat_completion_stream(
        model="llama2-7b-chat",
        messages=[{"role": "user", "content": "讲个笑话"}]
    ):
        print(text, end="")

    await client.close()

asyncio.run(main())
```

### 使用 OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="dummy"
)

response = client.chat.completions.create(
    model="llama2-7b-chat",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)
```

## API 参考

### VLLMProxyClient

#### 初始化

```python
VLLMProxyClient(
    base_url: str = "http://localhost:8080",
    api_key: Optional[str] = None,
    timeout: float = 300.0
)
```

#### 方法

| 方法 | 说明 |
|------|------|
| `health_check()` | 健康检查 |
| `list_models()` | 列出可用模型 |
| `get_model(model_id)` | 获取模型详情 |
| `load_model(model_id)` | 预加载模型 |
| `unload_model(model_id)` | 卸载模型 |
| `chat_completion(...)` | 聊天补全 |
| `chat_completion_stream(...)` | 流式聊天补全 |
| `text_completion(...)` | 文本补全 |
| `embeddings(...)` | 获取嵌入向量 |

## 运行示例

```bash
# 确保服务已启动
./scripts/start.sh

# 运行同步示例
cd client
python demo_sync.py

# 运行异步示例
python demo_async.py

# 运行 OpenAI SDK 示例
python demo_openai_sdk.py
```
