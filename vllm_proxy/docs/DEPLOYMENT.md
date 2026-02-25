# vLLM Proxy 部署指南

## 系统要求

### 硬件要求

| 组件 | 最低配置 | 推荐配置 |
|------|---------|---------|
| GPU | NVIDIA GPU with 16GB+ VRAM | A100 40GB / A10 24GB |
| CPU | 8 cores | 16+ cores |
| 内存 | 32GB | 64GB+ |
| 磁盘 | 100GB SSD | 500GB+ NVMe SSD |

### 软件要求

- Ubuntu 20.04+ / CentOS 7+ / Debian 10+
- Python 3.8+
- CUDA 11.8+ / 12.1+
- NVIDIA Driver 520+

## 部署方式

### 方式一：直接部署

#### 1. 安装依赖

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Python 和基础工具
sudo apt install -y python3 python3-pip python3-venv git curl

# 安装 CUDA（如果未安装）
# 参考: https://developer.nvidia.com/cuda-downloads
```

#### 2. 部署服务

```bash
# 下载项目
git clone <repository-url>
cd vllm_proxy

# 运行安装脚本
./scripts/install.sh

# 编辑配置
vim configs/config.yaml

# 启动服务
./scripts/start.sh -d

# 检查状态
./scripts/status.sh
```

### 方式二：Docker 部署

#### 1. 安装 Docker 和 NVIDIA Container Toolkit

```bash
# 安装 Docker
curl -fsSL https://get.docker.com | sh

# 安装 NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
    sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo systemctl restart docker
```

#### 2. 构建并运行

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

### 方式三：Kubernetes 部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm-proxy
  labels:
    app: vllm-proxy
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vllm-proxy
  template:
    metadata:
      labels:
        app: vllm-proxy
    spec:
      containers:
      - name: vllm-proxy
        image: vllm-proxy:latest
        ports:
        - containerPort: 8080
        resources:
          limits:
            nvidia.com/gpu: 1
            memory: "32Gi"
            cpu: "8"
          requests:
            nvidia.com/gpu: 1
            memory: "16Gi"
            cpu: "4"
        env:
        - name: IDLE_TIMEOUT
          value: "300"
        - name: RESERVED_MEMORY_MB
          value: "2048"
        volumeMounts:
        - name: model-cache
          mountPath: /app/models
        - name: config
          mountPath: /app/configs/config.yaml
          subPath: config.yaml
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8080
          initialDelaySeconds: 60
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 5
      volumes:
      - name: model-cache
        persistentVolumeClaim:
          claimName: model-cache-pvc
      - name: config
        configMap:
          name: vllm-proxy-config
---
apiVersion: v1
kind: Service
metadata:
  name: vllm-proxy
spec:
  selector:
    app: vllm-proxy
  ports:
  - port: 8080
    targetPort: 8080
  type: ClusterIP
```

## 生产环境配置

### Nginx 反向代理

```nginx
upstream vllm_proxy {
    server 127.0.0.1:8080;
    keepalive 32;
}

server {
    listen 80;
    server_name api.example.com;

    location / {
        proxy_pass http://vllm_proxy;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        # 长连接设置
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;

        # 流式响应缓冲
        proxy_buffering off;
        proxy_cache off;
    }
}
```

### 系统服务 (systemd)

```ini
# /etc/systemd/system/vllm-proxy.service
[Unit]
Description=vLLM Proxy Service
After=network.target

[Service]
Type=simple
User=vllm
Group=vllm
WorkingDirectory=/opt/vllm_proxy
Environment=PYTHONPATH=/opt/vllm_proxy/src
Environment=PROXY_PORT=8080
Environment=IDLE_TIMEOUT=300
Environment=LOG_LEVEL=INFO
ExecStart=/opt/vllm_proxy/venv/bin/python -m src
ExecStop=/opt/vllm_proxy/scripts/stop.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启用服务：
```bash
sudo systemctl daemon-reload
sudo systemctl enable vllm-proxy
sudo systemctl start vllm-proxy
sudo systemctl status vllm-proxy
```

## 监控配置

### Prometheus 采集

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'vllm-proxy'
    static_configs:
      - targets: ['localhost:8080']
    metrics_path: /metrics
    scrape_interval: 15s
```

### Grafana 仪表板

关键指标：
- GPU 显存使用率
- 模型加载/卸载次数
- 请求延迟分布
- 活跃模型数量
- 请求队列长度

### 告警规则

```yaml
groups:
- name: vllm-proxy
  rules:
  - alert: HighGPUMemoryUsage
    expr: vllm_gpu_memory_used_mb / vllm_gpu_memory_total_mb > 0.95
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "GPU memory usage is high"

  - alert: ModelLoadFailure
    expr: increase(vllm_model_load_failures_total[5m]) > 0
    for: 0m
    labels:
      severity: critical
    annotations:
      summary: "Model load failure detected"

  - alert: ServiceDown
    expr: up{job="vllm-proxy"} == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "vLLM Proxy service is down"
```

## 性能优化

### 1. 模型预热

```bash
# 启动时预加载常用模型
curl -X POST http://localhost:8080/admin/models/llama2-7b-chat/load
```

### 2. 调整空闲超时

```yaml
# 高并发场景：延长空闲时间
proxy:
  idle_timeout_seconds: 600  # 10分钟

# 资源紧张场景：缩短空闲时间
proxy:
  idle_timeout_seconds: 60   # 1分钟
```

### 3. 显存优化

```yaml
# 降低预留缓冲
gpu:
  reserved_memory_mb: 1024  # 从 2048 降低到 1024

# 使用量化模型
models:
  llama2-7b-awq:
    quantization: "awq"
    precision: "int4"
```

### 4. 批处理优化

```yaml
models:
  llama2-7b-chat:
    max_num_seqs: 32  # 增加并发批处理大小
```

## 故障排查

### 常见问题

#### 1. 模型加载失败

```bash
# 检查日志
tail -f logs/vllm_proxy.log

# 检查显存
nvidia-smi

# 手动测试 vLLM 启动
python -m vllm.entrypoints.openai.api_server \
    --model meta-llama/Llama-2-7b-chat-hf \
    --port 8001
```

#### 2. 显存不足

```bash
# 查看当前加载的模型
./scripts/status.sh -v

# 手动卸载模型
curl -X POST http://localhost:8080/admin/models/{model_id}/unload

# 调整预留显存
export RESERVED_MEMORY_MB=1024
```

#### 3. 端口冲突

```bash
# 检查端口占用
lsof -i :8080
lsof -i :8001-8010

# 修改基础端口
export BASE_PORT=9000
```

### 日志分析

```bash
# 实时日志
tail -f logs/vllm_proxy.log

# 查找错误
grep ERROR logs/vllm_proxy.log

# 统计模型加载次数
grep "Model.*loaded" logs/vllm_proxy.log | wc -l
```

## 安全建议

1. **网络隔离**: 使用防火墙限制访问
2. **认证**: 在 Nginx 层添加 API Key 认证
3. **HTTPS**: 生产环境使用 TLS
4. **资源限制**: 设置容器资源上限
5. **审计日志**: 记录所有管理操作

```nginx
# API Key 认证示例
location / {
    if ($http_authorization != "Bearer YOUR_API_KEY") {
        return 401;
    }
    proxy_pass http://vllm_proxy;
}
```
