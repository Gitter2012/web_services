# vLLM Dynamic Proxy

按需加载、自动释放显存的 vLLM 模型服务代理。

## 特性

- **按需加载**: 请求到达时才加载模型，无需预先占用显存
- **自动释放**: 空闲超时时自动卸载模型，释放显存
- **显存管理**: 智能监控 GPU 显存，自动淘汰 LRU 模型
- **OpenAI 兼容**: 提供与 OpenAI API 兼容的接口
- **多模型支持**: 同时管理多个模型，动态切换
- **API Key 认证**: 支持全局和模型级别的 API Key 配置

## 快速开始

### 1. 安装

```bash
# 克隆项目
git clone <repository-url>
cd vllm_proxy

# 运行安装脚本
./scripts/install.sh
```

### 2. 配置

编辑 `configs/config.yaml`，添加你的模型：

```yaml
models:
  llama2-7b-chat:
    model_path: "meta-llama/Llama-2-7b-chat-hf"
    param_count: 7
    precision: "fp16"
    max_model_len: 4096
    # 如果需要 HuggingFace Token
    # api_key: "hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

### 3. 启动服务

```bash
# 前台模式
./scripts/start.sh

# 后台模式
./scripts/start.sh -d

# 指定配置文件
./scripts/start.sh -c configs/config.yaml
```

### 4. 使用 API

```bash
# 查看模型列表
curl http://localhost:8080/v1/models

# 聊天补全
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama2-7b-chat",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### 5. 使用 Client SDK

```python
from client import VLLMProxyClient

client = VLLMProxyClient(base_url="http://localhost:8080")

# 聊天补全
response = client.chat_completion(
    model="llama2-7b-chat",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response['choices'][0]['message']['content'])

# 流式输出
for text in client.chat_completion_stream(
    model="llama2-7b-chat",
    messages=[{"role": "user", "content": "讲个笑话"}]
):
    print(text, end="")
```

## 服务管理

```bash
# 查看状态
./scripts/status.sh

# 查看详细状态
./scripts/status.sh -v

# 停止服务
./scripts/stop.sh

# 强制停止
./scripts/stop.sh -f

# 重启服务
./scripts/restart.sh
```

## Docker 部署

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

## 项目结构

```
vllm_proxy/
├── proxy/                  # 代理服务源代码
│   ├── __init__.py
│   ├── main.py            # 程序入口
│   ├── config.py          # 配置管理
│   ├── gpu_monitor.py     # GPU 监控
│   ├── model_manager.py   # 模型管理
│   └── proxy_server.py    # FastAPI 服务
│
├── client/                 # Client SDK
│   ├── __init__.py
│   ├── client.py          # 同步/异步客户端
│   ├── demo_sync.py       # 同步示例
│   ├── demo_async.py      # 异步示例
│   ├── demo_openai_sdk.py # OpenAI SDK 示例
│   └── requirements.txt
│
├── scripts/                # 管理脚本
│   ├── install.sh
│   ├── start.sh
│   ├── stop.sh
│   ├── restart.sh
│   └── status.sh
│
├── configs/                # 配置文件
│   └── config.yaml
├── docs/                   # 文档
│   ├── ARCHITECTURE.md
│   ├── API.md
│   └── DEPLOYMENT.md
├── logs/                   # 日志目录
├── models/                 # 模型缓存
├── requirements.txt        # Python 依赖
├── Dockerfile             # Docker 构建
└── docker-compose.yml     # Docker Compose 配置
```

## 配置说明

### GPU 配置

```yaml
gpu:
  gpu_id: 0                    # GPU 设备 ID
  reserved_memory_mb: 2048     # 预留显存缓冲
  memory_utilization: 0.9      # vLLM 显存利用率
```

### 代理配置

```yaml
proxy:
  host: "0.0.0.0"             # 监听地址
  port: 8080                   # 服务端口
  idle_timeout_seconds: 300    # 空闲超时（秒）
  # API Key 认证（可选，与 vLLM/OpenAI 兼容）
  # 请求时需在 Header 中提供: Authorization: Bearer <api_key>
  # api_key: "your-secret-key"
```

### 模型配置

```yaml
models:
  model-id:
    model_path: "..."          # HF 模型 ID 或本地路径
    param_count: 7             # 参数量（B）
    precision: "fp16"          # 精度
    max_model_len: 4096        # 最大序列长度
    api_key: "..."             # 模型级 API Key（HF Token）
```

## API 文档

### OpenAI 兼容接口

- `POST /v1/chat/completions` - 聊天补全
- `POST /v1/completions` - 文本补全
- `POST /v1/embeddings` - 文本嵌入
- `GET /v1/models` - 列出模型

### 管理接口

- `GET /health` - 健康检查
- `GET /metrics` - Prometheus 指标
- `POST /admin/models/{id}/load` - 预加载模型
- `POST /admin/models/{id}/unload` - 卸载模型

详细 API 文档请参考 [docs/API.md](docs/API.md)

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `PROXY_PORT` | 代理端口 | 8080 |
| `IDLE_TIMEOUT` | 空闲超时（秒） | 300 |
| `GPU_ID` | GPU 设备 ID | 0 |
| `RESERVED_MEMORY_MB` | 预留显存（MB） | 2048 |
| `LOG_LEVEL` | 日志级别 | INFO |

## 许可证

MIT License
