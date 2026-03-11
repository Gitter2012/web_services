# vLLM Dynamic Proxy

按需加载、自动释放显存的 vLLM 模型服务代理。

## 特性

- **按需加载**: 请求到达时才加载模型，无需预先占用显存
- **自动释放**: 空闲超时时自动卸载模型，释放显存
- **显存管理**: 智能监控 GPU 显存，自动淘汰 LRU 模型
- **OpenAI 兼容**: 提供与 OpenAI API 兼容的接口
- **多模型支持**: 同时管理多个模型，动态切换
- **API Key 认证**: 支持全局和模型级别的 API Key 配置
- **性能优化**: 支持 torch.compile、CUDA Graph、Encoder Cache 优化

## 系统要求

- Python 3.10+
- CUDA 13.0+
- NVIDIA Driver 520+
- vLLM 0.17.0+

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
  qwen3.5-9b-awq:
    model_path: "CYANKIWI/QWEN3.5-9B-AWQ-4BIT"
    param_count: 9
    precision: "fp16"
    quantization: "compressed-tensors"
    max_model_len: 8192
    enforce_eager: false
    extra_args:
      - "--trust-remote-code"
      - "--mm-processor-kwargs"
      - '{"max_pixels": 1003520}'
      - "--max-num-batched-tokens"
      - "1024"
      - "--default-chat-template-kwargs"
      - '{"enable_thinking": false}'
      - "--compilation-config"
      - '{"cudagraph_mode": 0}'
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
curl http://localhost:11436/v1/models

# 聊天补全
curl http://localhost:11436/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3.5-9b-awq",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 100
  }'
```

### 5. 使用 Client SDK

```python
from client import VLLMProxyClient

client = VLLMProxyClient(base_url="http://localhost:11436")

# 聊天补全
response = client.chat_completion(
    model="qwen3.5-9b-awq",
    messages=[{"role": "user", "content": "Hello!"}],
    max_tokens=100
)
print(response['choices'][0]['message']['content'])

# 流式输出
for text in client.chat_completion_stream(
    model="qwen3.5-9b-awq",
    messages=[{"role": "user", "content": "讲个笑话"}],
    max_tokens=100
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
│   └── README.md
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
├── requirements.txt        # Python 依赖
├── Dockerfile             # Docker 构建
└── docker-compose.yml     # Docker Compose 配置
```

## 配置说明

### GPU 配置

```yaml
gpu:
  gpu_id: 0                    # GPU 设备 ID
  reserved_memory_mb: 1024     # 预留显存缓冲 (MB)
  memory_utilization: 0.95     # vLLM 显存利用率
```

### 代理配置

```yaml
proxy:
  host: "127.0.0.1"           # 监听地址
  port: 11436                  # 服务端口
  base_port: 8000              # vLLM 进程起始端口
  idle_timeout_seconds: 300    # 空闲超时（秒）
  health_check_interval: 10    # 健康检查间隔（秒）
  max_start_retries: 3         # 启动失败最大重试次数
  start_timeout_seconds: 600   # 模型启动超时（秒）
  stop_timeout_seconds: 30     # 模型停止超时（秒）
  # API Key 认证（可选）
  # api_key: "your-secret-key"
```

### 模型配置

```yaml
models:
  model-id:
    model_path: "..."          # HF 模型 ID 或本地路径
    param_count: 7             # 参数量（B）
    precision: "fp16"          # 精度
    quantization: "awq"        # 量化方式
    max_model_len: 4096        # 最大序列长度
    max_num_seqs: 16           # 最大并发序列数
    enforce_eager: false       # 是否禁用 CUDA Graph
    extra_args: []             # 额外的 vLLM 参数
    api_key: "..."             # 模型级 API Key（HF Token）
```

## 性能优化

### torch.compile + CUDA Graph

对于支持 CUDA Graph 的模型，可以启用 torch.compile 来提升推理速度：

```yaml
models:
  qwen3.5-9b-awq:
    enforce_eager: false
    extra_args:
      # 启用 torch.compile 但禁用 CUDA Graph（避免 Triton OOM）
      - "--compilation-config"
      - '{"cudagraph_mode": 0}'
```

**性能对比**:
| 配置 | 推理速度 |
|-----|---------|
| `enforce_eager: true` | ~0.4 tok/s |
| `enforce_eager: false` + `cudagraph_mode: 0` | ~30 tok/s |

### Encoder Cache 优化

对于多模态模型，可以优化 Encoder Cache Profiling 时间：

```yaml
extra_args:
  # 限制图像最大像素数
  - "--mm-processor-kwargs"
  - '{"max_pixels": 1003520}'
  # 控制 encoder cache budget
  - "--max-num-batched-tokens"
  - "1024"
```

### Thinking 模式控制

对于 Qwen3/DeepSeek 推理模型，可以默认关闭 thinking 模式：

```yaml
extra_args:
  - "--default-chat-template-kwargs"
  - '{"enable_thinking": false}'
```

请求时可以临时启用：`{"enable_thinking": true}`

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
| `PROXY_PORT` | 代理端口 | 11436 |
| `IDLE_TIMEOUT` | 空闲超时（秒） | 300 |
| `GPU_ID` | GPU 设备 ID | 0 |
| `RESERVED_MEMORY_MB` | 预留显存（MB） | 1024 |
| `LOG_LEVEL` | 日志级别 | INFO |

## 故障排查

### 常见问题

**1. 模型启动超时**
```bash
# 检查日志
tail -f logs/vllm_proxy.log

# 调整启动超时配置
proxy:
  start_timeout_seconds: 600  # 增加超时时间
```

**2. Triton OOM 错误**
```yaml
# 启用 enforce_eager 或禁用 CUDA Graph
models:
  your-model:
    enforce_eager: true
    # 或者
    extra_args:
      - "--compilation-config"
      - '{"cudagraph_mode": 0}'
```

**3. HuggingFace 429 限速**
- 系统会自动检测本地缓存并启用离线模式
- 确保模型已完整下载到本地

详细故障排查请参考 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

## 许可证

MIT License
