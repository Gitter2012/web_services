# vLLM Proxy 架构设计文档

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Client Layer                                │
│                    (OpenAI API / Web UI / CLI)                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            Proxy Service                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────┐  │
│  │  API Router  │  │ GPU Monitor  │  │      Model Manager           │  │
│  │              │  │              │  │  ┌────────────────────────┐  │  │
│  │ /v1/chat     │  │ - 显存监控    │  │  │   LRU Cache            │  │  │
│  │ /v1/models   │  │ - 容量规划    │  │  │   - model_id           │  │  │
│  │ /health      │  │ - 淘汰决策    │  │  │   - last_used          │  │  │
│  └──────────────┘  └──────────────┘  │  │   - ref_count          │  │  │
│           │                 │        │  └────────────────────────┘  │  │
│           └─────────────────┼────────┘                              │  │
│                             │                                       │  │
│  ┌──────────────────────────┼────────────────────────────────────┐ │  │
│  │         vLLM Process Pool (动态管理)                          │ │  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐       ┌─────────┐       │ │  │
│  │  │ Model A │ │ Model B │ │ Model C │  ...  │ Model N │       │ │  │
│  │  │:8001    │ │:8002    │ │:8003    │       │ (idle)  │       │ │  │
│  │  └────┬────┘ └────┬────┘ └────┬────┘       └────┬────┘       │ │  │
│  │       └─────────────┴───────────┘                │            │ │  │
│  │                    GPU 0                         │            │ │  │
│  │              ┌─────────────────┐                 │            │ │  │
│  │              │   显存: 24GB    │                 │            │ │  │
│  │              │   已用: 20GB    │                 │            │ │  │
│  │              │   可用: 2GB     │                 │            │ │  │
│  │              └─────────────────┘                 │            │ │  │
│  └──────────────────────────────────────────────────┘            │  │
└─────────────────────────────────────────────────────────────────────────┘
```

## 核心组件

### 1. GPU Monitor (GPU 监控器)

**职责**: 监控 GPU 显存使用情况，为模型加载决策提供数据支持。

**功能**:
- 实时显存监控
- 显存需求预测
- 淘汰计划计算

**显存计算公式**:
```
总显存需求 = 模型权重 + KV Cache + 激活值 + 开销

模型权重 = 参数量(B) × 1e9 × 精度字节数 / 1024 / 1024
KV Cache = 2 × num_layers × batch_size × seq_len × num_kv_heads × head_size × 2 / 1024 / 1024
激活值 ≈ 512MB + batch_size × seq_len × hidden_size × 2 / 1024 / 1024
开销 = 512MB (CUDA context 等)
```

### 2. Model Manager (模型管理器)

**职责**: 管理模型的完整生命周期。

**状态机**:
```
                    ┌──────────┐
         ┌─────────▶│ STOPPED  │◀────────┐
         │          └────┬─────┘         │
         │               │ start()       │ unload()
         │               ▼               │
    unload()      ┌──────────┐           │
         │        │ STARTING │           │
         │        └────┬─────┘           │
         │             │ ready           │
         │             ▼                 │
         │        ┌──────────┐           │
         └────────│ RUNNING  │───────────┘
   (on error)      └────┬─────┘
                       │
                       ▼
                  ┌──────────┐
                  │  ERROR   │
                  └──────────┘
```

**LRU 淘汰策略**:
1. 当新模型请求显存不足时触发
2. 只考虑 `ref_count == 0` 的空闲模型
3. 按 `last_used_at` 排序，淘汰最久未使用的
4. 累计释放显存直到满足需求

### 3. Proxy Server (代理服务)

**职责**: 提供 OpenAI 兼容的 API 接口。

**请求处理流程**:
```
1. 接收请求
   │
2. 解析 model_id
   │
3. 调用 ModelManager.get_model(model_id)
   │
4. 等待模型就绪（如果需要加载）
   │
5. 增加引用计数 acquire_model()
   │
6. 转发请求到 vLLM 进程
   │
7. 返回响应
   │
8. 减少引用计数 release_model()
```

## 并发控制

### 锁机制

```python
# 全局锁：保护 models 字典和端口分配
_global_lock: asyncio.Lock

# 模型锁：每个模型一个锁，防止并发操作
_locks: Dict[str, asyncio.Lock]
```

### 引用计数

```python
request_count: int  # 当前处理中的请求数

# 请求开始时 +1
acquire_model(model_id)

# 请求结束时 -1
release_model(model_id)

# 只有 request_count == 0 时才能淘汰
```

## 空闲检测与自动释放

```python
async def _idle_watcher(model_id: str):
    while True:
        await asyncio.sleep(idle_timeout)

        idle_time = now() - last_used_at

        if request_count == 0 and idle_time >= idle_timeout:
            await unload_model(model_id)
            return
```

每个运行的模型都有一个独立的 `idle_watcher` 任务，在模型加载时启动，卸载时取消。

## 显存管理策略

### 场景 1: 显存充足

```
当前显存: 24GB
已用: 10GB
可用: 14GB

新模型需求: 8GB
决策: 直接加载，无需淘汰
```

### 场景 2: 显存不足，有空闲模型

```
当前显存: 24GB
已用: 22GB
可用: 2GB

新模型需求: 8GB
空闲模型: Model A (6GB, idle 10min), Model B (5GB, idle 5min)

决策:
1. 淘汰 Model A (LRU)，释放 6GB
2. 可用显存: 2 + 6 = 8GB
3. 加载新模型
```

### 场景 3: 显存不足，无空闲模型

```
当前显存: 24GB
已用: 22GB
可用: 2GB

新模型需求: 8GB
所有模型都有活跃请求

决策:
1. 无法淘汰任何模型
2. 返回 503 Service Unavailable
3. 客户端可重试或排队
```

## 进程管理

### vLLM 进程启动

```bash
python -m vllm.entrypoints.openai.api_server \
    --model <model_path> \
    --port <allocated_port> \
    --tensor-parallel-size <tp> \
    --max-model-len <max_len> \
    --gpu-memory-utilization <util>
```

### 优雅关闭

```python
# 1. 发送 SIGTERM
process.send_signal(signal.SIGTERM)

# 2. 等待进程结束（超时 30s）
try:
    await asyncio.wait_for(process.wait(), timeout=30)
except TimeoutError:
    # 3. 超时后 SIGKILL
    process.kill()
```

## vLLM V1 性能优化

### torch.compile 优化

vLLM 0.17.0+ 支持 `torch.compile` (inductor 后端) 进行模型编译优化，可在不使用 CUDA Graph 的情况下获得显著的性能提升。

**配置示例**:
```yaml
models:
  your-model:
    enforce_eager: false
    extra_args:
      - "--compilation-config"
      - '{"cudagraph_mode": 0}'  # 禁用 CUDA Graph
```

**效果**:
- 推理速度提升 70-80x（在 T4 GPU 上测试）
- GPU 利用率从 0-52% 提升到 76-83%

### Encoder Cache 优化（多模态模型）

对于多模态模型（如 Qwen3.5），可以通过以下参数优化 encoder cache profiling 时间：

```yaml
models:
  qwen3.5-9b-awq:
    extra_args:
      - "--mm-processor-kwargs"
      - '{"max_pixels": 1003520}'  # 限制图像最大像素
      - "--max-num-batched-tokens"
      - "1024"  # 控制 encoder budget
```

**参数说明**:
- `max_pixels`: 限制图像处理器最大像素数，默认值可能导致 profiling 枯慢
- `max_num_batched_tokens`: 控制 encoder cache budget，影响 profiling 图像数

**优化公式**:
```
profiling_images = encoder_budget // tokens_per_image
tokens_per_image = max_pixels // 1024
encoder_budget = max_num_batched_tokens
```

### Thinking 模式控制
对于推理模型（Qwen3/DeepSeek），可以控制是否输出思维链：

```yaml
models:
  your-reasoning-model:
    extra_args:
      - "--default-chat-template-kwargs"
      - '{"enable_thinking": false}'  # 默认关闭
```

请求时可以临时启用: `{"chat_template_kwargs": {"enable_thinking": true}}`

### 环境变量优化

系统会自动设置以下环境变量：
- `PYTORCH_ALLOC_CONF=expandable_segments:True`: 减少显存碎片
- `TRITON_CACHE_DIR`: 持久化 Triton kernel 自动调优结果

### 故障处理

#### 场景 1: vLLM 进程崩溃
```
1. Health Check 检测到进程退出
2. 标记模型状态为 ERROR
3. 发送告警（可选）
4. 下次请求时重新启动
```

#### 场景 2: 显存 OOM
```
1. vLLM 报告 OOM
2. 代理返回 503
3. 尝试淘汰其他模型
4. 客户端重试
```

#### 场景 3: 模型加载超时
```
1. 启动计时器（默认 600s）
2. 超时后终止进程组
3. 标记 ERROR 状态
4. 返回 500 错误
```

#### 场景 4: Triton 自动调优 OOM
```
1. 首次推理时 Triton kernel 自动调优占用额外显存
2. 解决方案:
   - 设置 enforce_eager: true
   - 或设置 cudagraph_mode: 0 禁用 CUDA Graph
```

#### 场景 5: HuggingFace 限速 (429)
```
1. 系统检测本地模型缓存
2. 自动设置 HF_HUB_OFFLINE=1
3. 在离线模式下启动
4. 如果模型不完整，启动失败并返回错误
```

### 多 GPU 支持

```yaml
# 配置多 GPU
gpu:
  gpu_id: 0,1,2,3  # 或 all

models:
  large-model:
    tensor_parallel: 4  # 跨 4 张卡
```

### 分布式部署

```
┌─────────────┐
│   Load      │
│  Balancer   │
└──────┬──────┘
       │
   ┌───┴───┐
   ▼       ▼
┌─────┐ ┌─────┐
│Proxy│ │Proxy│
│ GPU0│ │ GPU1│
└─────┘ └─────┘
```

## 监控指标

### Prometheus 指标

```
# GPU 显存
vllm_gpu_memory_total_mb{gpu_id="0"}
vllm_gpu_memory_used_mb{gpu_id="0"}
vllm_gpu_utilization_percent{gpu_id="0"}

# 模型状态
vllm_model_loaded{model_id="llama2-7b"}
vllm_model_requests_active{model_id="llama2-7b"}

# 请求统计
vllm_requests_total{model_id="llama2-7b"}
vllm_request_duration_seconds{model_id="llama2-7b"}
```

## 故障处理

### 场景 1: vLLM 进程崩溃

```
1. Health Check 检测到进程退出
2. 标记模型状态为 ERROR
3. 发送告警（可选）
4. 下次请求时重新启动
```

### 场景 2: 显存 OOM

```
1. vLLM 报告 OOM
2. 代理返回 503
3. 尝试淘汰其他模型
4. 客户端重试
```

### 场景 3: 模型加载超时

```
1. 启动计时器（默认 120s）
2. 超时后终止进程
3. 标记 ERROR 状态
4. 返回 500 错误
```
