# vLLM Proxy API 文档

## OpenAI 兼容接口

### 聊天补全

```http
POST /v1/chat/completions
```

**请求体**:
```json
{
  "model": "llama2-7b-chat",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "temperature": 0.7,
  "max_tokens": 256,
  "stream": false
}
```

**响应**:
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "llama2-7b-chat",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "Hello! How can I help you today?"
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 20,
    "total_tokens": 30
  }
}
```

**流式响应** (`stream: true`):
```
data: {"id":"chatcmpl-xxx","choices":[{"delta":{"role":"assistant"}}]}

data: {"id":"chatcmpl-xxx","choices":[{"delta":{"content":"Hello"}}]}

data: {"id":"chatcmpl-xxx","choices":[{"delta":{"content":"!"}}]}

data: [DONE]
```

### 文本补全

```http
POST /v1/completions
```

**请求体**:
```json
{
  "model": "llama2-7b-chat",
  "prompt": "Once upon a time",
  "max_tokens": 100,
  "temperature": 0.7
}
```

### 嵌入向量

```http
POST /v1/embeddings
```

**请求体**:
```json
{
  "model": "bge-large-zh",
  "input": "Hello world"
}
```

### 列出模型

```http
GET /v1/models
```

**响应**:
```json
{
  "object": "list",
  "data": [
    {
      "id": "llama2-7b-chat",
      "object": "model",
      "created": 1234567890,
      "owned_by": "vllm-proxy",
      "status": "running",
      "port": 8001,
      "gpu_memory_mb": 16000,
      "request_count": 2
    }
  ]
}
```

### 获取模型详情

```http
GET /v1/models/{model_id}
```

**响应**:
```json
{
  "id": "llama2-7b-chat",
  "object": "model",
  "status": "running",
  "detail": {
    "model_id": "llama2-7b-chat",
    "status": "running",
    "port": 8001,
    "gpu_memory_mb": 16000,
    "request_count": 0,
    "total_requests": 100,
    "created_at": "2024-01-01T00:00:00",
    "last_used_at": "2024-01-01T12:00:00",
    "idle_seconds": 120
  }
}
```

## 管理接口

### 健康检查

```http
GET /health
```

**响应**:
```json
{
  "status": "healthy",
  "gpu": {
    "id": 0,
    "name": "NVIDIA A100",
    "temperature": 45.0,
    "utilization_percent": 30.0,
    "memory": {
      "total_mb": 24576,
      "used_mb": 16384,
      "free_mb": 8192,
      "available_mb": 6144
    },
    "power_draw_w": 150.0,
    "power_limit_w": 400.0
  },
  "loaded_models": 1,
  "model_status": {
    "llama2-7b-chat": {
      "model_id": "llama2-7b-chat",
      "status": "running",
      "port": 8001,
      "gpu_memory_mb": 16000,
      "request_count": 0
    }
  }
}
```

### 就绪检查 (K8s)

```http
GET /health/ready
```

**响应**:
```json
{
  "ready": true
}
```

### 存活检查 (K8s)

```http
GET /health/live
```

**响应**:
```json
{
  "alive": true
}
```

### Prometheus 指标

```http
GET /metrics
```

**响应** (text/plain):
```
# HELP vllm_gpu_memory_total_mb Total GPU memory in MB
# TYPE vllm_gpu_memory_total_mb gauge
vllm_gpu_memory_total_mb{gpu_id="0"} 24576

# HELP vllm_gpu_memory_used_mb Used GPU memory in MB
# TYPE vllm_gpu_memory_used_mb gauge
vllm_gpu_memory_used_mb{gpu_id="0"} 16384

# HELP vllm_model_loaded Whether model is loaded
# TYPE vllm_model_loaded gauge
vllm_model_loaded{model_id="llama2-7b-chat"} 1
```

### 预加载模型

```http
POST /admin/models/{model_id}/load
```

**响应**:
```json
{
  "success": true,
  "model_id": "llama2-7b-chat",
  "port": 8001,
  "status": "running"
}
```

### 卸载模型

```http
POST /admin/models/{model_id}/unload
```

**响应**:
```json
{
  "success": true,
  "model_id": "llama2-7b-chat"
}
```

## 错误码

| HTTP 状态码 | 说明 | 场景 |
|------------|------|------|
| 200 | 成功 | 请求正常处理 |
| 400 | 请求错误 | 缺少必要参数或格式错误 |
| 404 | 未找到 | 模型不存在 |
| 500 | 服务器错误 | 内部处理错误 |
| 502 | 网关错误 | 模型推理失败 |
| 503 | 服务不可用 | 显存不足或模型加载失败 |

**错误响应格式**:
```json
{
  "detail": "错误描述信息"
}
```

## 使用示例

### Python

```python
import openai

# 配置客户端
client = openai.OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="dummy"  # vLLM 不需要真实 API key
)

# 聊天补全
response = client.chat.completions.create(
    model="llama2-7b-chat",
    messages=[
        {"role": "user", "content": "Hello!"}
    ],
    stream=False
)
print(response.choices[0].message.content)

# 流式响应
for chunk in client.chat.completions.create(
    model="llama2-7b-chat",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True
):
    print(chunk.choices[0].delta.content or "", end="")
```

### cURL

```bash
# 聊天补全
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama2-7b-chat",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'

# 流式响应
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama2-7b-chat",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": true
  }'

# 预加载模型
curl -X POST http://localhost:8080/admin/models/llama2-7b-chat/load

# 卸载模型
curl -X POST http://localhost:8080/admin/models/llama2-7b-chat/unload
```

### JavaScript

```javascript
// 使用 fetch
const response = await fetch('http://localhost:8080/v1/chat/completions', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    model: 'llama2-7b-chat',
    messages: [{ role: 'user', content: 'Hello!' }]
  })
});

const data = await response.json();
console.log(data.choices[0].message.content);
```
