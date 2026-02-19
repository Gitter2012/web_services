# 部署文档

> 文档维护说明：部署步骤如有变更，请同步更新此文档。

## 目录

- [环境要求](#环境要求)
- [本地开发部署](#本地开发部署)
- [Milvus 部署](#milvus-部署可选)
- [Ollama 部署](#ollama-部署可选)
- [生产环境部署](#生产环境部署)
- [Docker 部署](#docker-部署)
- [Kubernetes 部署](#kubernetes-部署)
- [Nginx 配置](#nginx-配置)
- [SSL 证书配置](#ssl-证书配置)
- [监控与日志](#监控与日志)
- [备份策略](#备份策略)
- [性能优化](#性能优化)
- [故障排查](#故障排查)

---

## 环境要求

| 软件 | 版本 | 必需 | 说明 |
|------|------|------|------|
| Python | 3.10+ | 是 | 支持 3.10 / 3.11 / 3.12 / 3.13 |
| MySQL | 8.0+ | 是 | 主数据库，utf8mb4 编码 |
| Redis | 6.0+ | 否 | 缓存层（未配置时使用内存缓存） |
| Milvus | 2.3+ | 否 | 向量数据库（启用 embedding 功能时需要） |
| Ollama | 最新版 | 否 | 本地 AI 推理（启用 ai_processor 且使用 ollama 时需要） |
| Nginx | 1.18+ | 否 | 反向代理（生产环境推荐） |
| Docker | 20.10+ | 否 | 容器化部署 |
| Docker Compose | 2.0+ | 否 | 编排多服务 |

**硬件建议：**

| 部署模式 | CPU | 内存 | 磁盘 | GPU |
|---------|-----|------|------|-----|
| 基础（仅爬虫） | 2 核 | 4 GB | 20 GB | 不需要 |
| 标准（含 AI） | 4 核 | 16 GB | 50 GB | 推荐（Ollama） |
| 完整（全功能） | 8 核 | 32 GB | 100 GB | 推荐（Ollama） |

---

## 本地开发部署

### 1. 克隆项目

```bash
git clone https://github.com/web_services/ResearchPulse.git
cd ResearchPulse
```

### 2. 创建虚拟环境

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows
```

### 3. 安装依赖

```bash
# 基础依赖
pip install -r requirements.txt

# 向量嵌入功能（可选）
pip install -e ".[embedding]"

# 开发依赖（测试、lint、类型检查）
pip install -e ".[dev]"
```

### 4. 配置环境变量

```bash
cp .env.example .env
vim .env
```

必填配置：

```bash
# 数据库
DB_HOST=localhost
DB_PORT=3306
DB_NAME=research_pulse
DB_USER=research_user
DB_PASSWORD=your_password

# JWT 密钥
JWT_SECRET_KEY=your-secret-key

# 超级管理员（首次启动时创建）
SUPERUSER_USERNAME=admin
SUPERUSER_EMAIL=admin@example.com
SUPERUSER_PASSWORD=admin_password
```

### 5. 初始化数据库

```bash
# 创建数据库（utf8mb4 编码以支持中文和 emoji）
mysql -u root -p -e "CREATE DATABASE research_pulse CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 创建用户并授权
mysql -u root -p -e "CREATE USER 'research_user'@'%' IDENTIFIED BY 'your_password';"
mysql -u root -p -e "GRANT ALL PRIVILEGES ON research_pulse.* TO 'research_user'@'%';"
mysql -u root -p -e "FLUSH PRIVILEGES;"

# 初始化表结构
mysql -u research_user -p research_pulse < sql/init.sql
```

### 6. 启动服务

```bash
# 方式一：直接运行（使用 settings.py 中配置的 host:port）
python main.py

# 方式二：uvicorn 开发模式（支持热重载）
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 方式三：使用控制台脚本（需先 pip install -e .）
researchpulse --host 0.0.0.0 --port 8000 --reload
```

### 7. 功能开关初始化

首次启动时，系统会自动将 `common/feature_config.py` 中 `DEFAULT_CONFIGS` 的功能开关写入数据库。所有高级功能默认关闭，可通过管理 API 启用：

```bash
# 启用 AI 分析功能
curl -X PUT http://localhost:8000/api/v1/admin/features/feature.ai_processor \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'

# 启用向量嵌入功能
curl -X PUT http://localhost:8000/api/v1/admin/features/feature.embedding \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

### 8. 验证部署

```bash
# 健康检查
curl http://localhost:8000/health

# 应返回
{"status":"healthy","components":{"database":"connected",...}}

# 访问 API 文档
open http://localhost:8000/docs
```

---

## Milvus 部署（可选）

Milvus 是向量嵌入和相似文章检索功能的依赖。仅在启用 `feature.embedding` 时需要。

### 使用项目提供的 docker-compose

项目根目录下提供了 `docker-compose.milvus.yml`，包含 Milvus 及其依赖（etcd、MinIO）：

```bash
docker compose -f docker-compose.milvus.yml up -d
```

该配置启动三个服务：

| 服务 | 容器名 | 端口 | 说明 |
|------|--------|------|------|
| milvus-etcd | rp-milvus-etcd | - | 分布式元数据存储 |
| milvus-minio | rp-milvus-minio | 9001 | 对象存储（MinIO Console） |
| milvus-standalone | rp-milvus | 19530, 9091 | Milvus 向量数据库服务 |

数据存储在 `./volumes/` 目录下（etcd、minio、milvus 各自独立目录）。

### 验证 Milvus

```bash
# 检查 Milvus 健康状态
curl http://localhost:9091/healthz
# 应返回 "OK"

# 检查 MinIO Console
open http://localhost:9001
# 默认用户: minioadmin / minioadmin
```

### 配置连接

```bash
# .env
MILVUS_HOST=localhost
MILVUS_PORT=19530
EMBEDDING_ENABLED=true
```

### 停止和清理

```bash
# 停止服务（保留数据）
docker compose -f docker-compose.milvus.yml stop

# 停止并删除容器（保留数据卷）
docker compose -f docker-compose.milvus.yml down

# 完全清理（包括数据）
docker compose -f docker-compose.milvus.yml down -v
rm -rf ./volumes/
```

---

## Ollama 部署（可选）

Ollama 用于本地 AI 推理。仅在启用 `feature.ai_processor` 且使用 `ollama` 提供方时需要。

### 安装 Ollama

```bash
# Linux
curl -fsSL https://ollama.com/install.sh | sh

# macOS
brew install ollama

# Docker（见下方 Docker 部署章节）
```

### 启动服务

```bash
ollama serve
```

### 下载模型

```bash
# 推荐：qwen3:32b（32B 参数，中英文表现优秀）
ollama pull qwen3:32b

# 轻量替代：qwen3:8b（8B 参数，资源需求低）
ollama pull qwen3:8b

# 查看已下载模型
ollama list
```

### 验证

```bash
# 测试模型是否可用
ollama run qwen3:32b "Hello, summarize this: ResearchPulse is an AI platform."

# 检查 API 可用性
curl http://localhost:11434/api/tags
```

### 配置连接

```bash
# .env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:32b
OLLAMA_MODEL_LIGHT=qwen3:8b  # 可选轻量模型
OLLAMA_TIMEOUT=120
OLLAMA_API_KEY=              # 可选，用于有认证要求的远程 Ollama 部署
```

### GPU 支持

Ollama 自动检测和使用 GPU。确保安装了 NVIDIA 驱动和 CUDA：

```bash
# 检查 GPU 状态
nvidia-smi

# Ollama 会自动使用可用的 GPU
ollama serve

# Docker with GPU（需要 nvidia-container-toolkit）
docker run -d --gpus all -p 11434:11434 ollama/ollama:latest
```

**模型资源需求参考：**

| 模型 | 参数量 | 最小显存 | 推荐显存 | 说明 |
|------|--------|---------|---------|------|
| qwen3:32b | 32B | 16 GB | 24 GB | 推荐，中英文效果好 |
| qwen3:8b | 8B | 6 GB | 8 GB | 轻量替代 |

---

## 生产环境部署

### 使用 Systemd

创建服务文件 `/etc/systemd/system/researchpulse.service`：

```ini
[Unit]
Description=ResearchPulse Service
After=network.target mysql.service
Wants=mysql.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/ResearchPulse
Environment="PATH=/opt/ResearchPulse/venv/bin"
EnvironmentFile=/opt/ResearchPulse/.env
ExecStart=/opt/ResearchPulse/venv/bin/python main.py
Restart=always
RestartSec=5
StartLimitInterval=60
StartLimitBurst=3

# 安全加固
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/opt/ResearchPulse/data /opt/ResearchPulse/backups /opt/ResearchPulse/logs

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable researchpulse
sudo systemctl start researchpulse

# 检查状态
sudo systemctl status researchpulse

# 查看日志
sudo journalctl -u researchpulse -f
```

### 使用 Gunicorn（推荐多 worker）

```bash
pip install gunicorn

gunicorn main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --timeout 120 \
    --graceful-timeout 30 \
    --access-logfile logs/access.log \
    --error-logfile logs/error.log \
    --pid run/gunicorn.pid
```

**Worker 数量建议：** `2 * CPU 核心数 + 1`

---

## Docker 部署

### 项目 Dockerfile

项目提供了多阶段构建的 Dockerfile，特点：

- **多阶段构建**: Builder 阶段安装依赖，Production 阶段仅复制运行时
- **非 root 用户**: 使用 `appuser` 运行应用
- **健康检查**: 内置 `curl /health` 健康检查（30s 间隔）
- **环境优化**: `PYTHONUNBUFFERED=1`，`PYTHONDONTWRITEBYTECODE=1`

```bash
# 构建镜像
docker build -t researchpulse:latest .

# 运行容器
docker run -d \
  --name researchpulse \
  -p 8000:8000 \
  -e DB_HOST=host.docker.internal \
  -e DB_PORT=3306 \
  -e DB_NAME=research_pulse \
  -e DB_USER=research_user \
  -e DB_PASSWORD=your_password \
  -e JWT_SECRET_KEY=your-secret-key \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/backups:/app/backups \
  researchpulse:latest

# 检查容器健康状态
docker inspect --format='{{.State.Health.Status}}' researchpulse
```

### Docker Compose 完整版

`docker-compose.yml`（含所有服务）：

```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DB_HOST=db
      - DB_PORT=3306
      - DB_NAME=research_pulse
      - DB_USER=research_user
      - DB_PASSWORD=${DB_PASSWORD}
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - SUPERUSER_USERNAME=${SUPERUSER_USERNAME:-admin}
      - SUPERUSER_EMAIL=${SUPERUSER_EMAIL:-admin@example.com}
      - SUPERUSER_PASSWORD=${SUPERUSER_PASSWORD}
      - AI_PROVIDER=ollama
      - OLLAMA_BASE_URL=http://ollama:11434
      - OLLAMA_API_KEY=${OLLAMA_API_KEY:-}
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
      - OPENAI_BASE_URL=${OPENAI_BASE_URL:-https://api.openai.com/v1}
      - MILVUS_HOST=milvus
      - MILVUS_PORT=19530
      - REDIS_HOST=redis
      - REDIS_PORT=6379
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - app_data:/app/data
      - app_logs:/app/logs
      - app_backups:/app/backups
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s

  db:
    image: mysql:8.0
    environment:
      - MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD}
      - MYSQL_DATABASE=research_pulse
      - MYSQL_USER=research_user
      - MYSQL_PASSWORD=${DB_PASSWORD}
    volumes:
      - mysql_data:/var/lib/mysql
      - ./sql/init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "3306:3306"
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    command: --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
    restart: unless-stopped

  # Milvus 及依赖（可选，启用 embedding 功能时需要）
  etcd:
    image: quay.io/coreos/etcd:v3.5.5
    environment:
      - ETCD_AUTO_COMPACTION_MODE=revision
      - ETCD_AUTO_COMPACTION_RETENTION=1000
      - ETCD_QUOTA_BACKEND_BYTES=4294967296
      - ETCD_SNAPSHOT_COUNT=50000
    volumes:
      - etcd_data:/etcd
    command: etcd -advertise-client-urls=http://127.0.0.1:2379 -listen-client-urls http://0.0.0.0:2379 --data-dir /etcd
    healthcheck:
      test: ["CMD", "etcdctl", "endpoint", "health"]
      interval: 30s
      timeout: 20s
      retries: 3
    restart: unless-stopped

  minio:
    image: minio/minio:RELEASE.2023-03-20T20-16-18Z
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - minio_data:/minio_data
    command: minio server /minio_data --console-address ":9001"
    ports:
      - "9001:9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3
    restart: unless-stopped

  milvus:
    image: milvusdb/milvus:v2.3.3
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
    ports:
      - "19530:19530"
      - "9091:9091"
    volumes:
      - milvus_data:/var/lib/milvus
    depends_on:
      etcd:
        condition: service_healthy
      minio:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]
      interval: 30s
      timeout: 20s
      retries: 3
    restart: unless-stopped

  # Ollama（可选，启用 AI 分析功能时需要）
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    # 如需 GPU 支持，取消注释以下配置
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: 1
    #           capabilities: [gpu]
    restart: unless-stopped

  # Nginx 反向代理（生产环境推荐）
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - app
    restart: unless-stopped

volumes:
  app_data:
  app_logs:
  app_backups:
  mysql_data:
  redis_data:
  etcd_data:
  minio_data:
  milvus_data:
  ollama_data:
```

**启动命令：**

```bash
# 启动全部服务
docker compose up -d

# 仅启动核心服务（不含 Milvus、Ollama）
docker compose up -d app db redis nginx

# 启动含 Milvus（向量功能）
docker compose up -d app db redis nginx etcd minio milvus

# 下载 Ollama 模型（首次启动后执行）
docker compose exec ollama ollama pull qwen3:32b

# 查看所有服务状态
docker compose ps

# 查看应用日志
docker compose logs -f app
```

---

## Kubernetes 部署

### 健康检查配置

ResearchPulse 提供三个健康检查端点，可直接用于 Kubernetes 探针：

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: researchpulse
spec:
  replicas: 3
  selector:
    matchLabels:
      app: researchpulse
  template:
    metadata:
      labels:
        app: researchpulse
    spec:
      containers:
      - name: researchpulse
        image: researchpulse:latest
        ports:
        - containerPort: 8000
        env:
        - name: DB_HOST
          valueFrom:
            secretKeyRef:
              name: researchpulse-secrets
              key: db-host
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: researchpulse-secrets
              key: db-password
        - name: JWT_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: researchpulse-secrets
              key: jwt-secret
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 30
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
          initialDelaySeconds: 15
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
```

**探针说明：**

| 探针 | 端点 | 检查内容 | 失败行为 |
|------|------|---------|---------|
| livenessProbe | GET /health/live | 应用进程存活 | 重启 Pod |
| readinessProbe | GET /health/ready | 数据库连接就绪 | 从 Service 摘除 |

---

## Nginx 配置

### 基础配置

`/etc/nginx/sites-available/researchpulse`：

```nginx
# HTTP → HTTPS 重定向
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL 配置
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;

    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # 静态文件缓存
    location /static/ {
        alias /opt/ResearchPulse/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # API 和页面反向代理
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket 支持（如需要）
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # 超时设置
        proxy_connect_timeout 60s;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }

    # 文件上传大小限制
    client_max_body_size 10M;

    # 速率限制（建议）
    # limit_req_zone $binary_remote_addr zone=api:10m rate=100r/m;
    # location /api/ {
    #     limit_req zone=api burst=20 nodelay;
    #     proxy_pass http://127.0.0.1:8000;
    # }
}
```

启用配置：

```bash
sudo ln -s /etc/nginx/sites-available/researchpulse /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## SSL 证书配置

使用 Let's Encrypt 免费证书：

```bash
# 安装 certbot
sudo apt install certbot python3-certbot-nginx

# 获取证书（自动配置 Nginx）
sudo certbot --nginx -d your-domain.com

# 测试自动续期
sudo certbot renew --dry-run
```

证书自动续期由 certbot 的 systemd timer 管理，无需手动干预。

---

## 监控与日志

### 日志位置

```
logs/
├── app.log         # 应用日志（INFO 级别）
├── access.log      # 访问日志（Gunicorn/uvicorn）
└── error.log       # 错误日志
```

### 日志配置

日志级别通过环境变量或 `config/defaults.yaml` 配置：

```bash
# 开发环境
DEBUG=true    # 自动使用 DEBUG 级别

# 生产环境
DEBUG=false   # 使用 INFO 级别
```

### 日志轮转

`/etc/logrotate.d/researchpulse`：

```
/opt/ResearchPulse/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0640 www-data www-data
    postrotate
        systemctl reload researchpulse > /dev/null 2>&1 || true
    endscript
}
```

### 健康检查

```bash
# 完整健康检查（数据库 + Redis + Milvus + Ollama）
curl http://localhost:8000/health

# 响应示例
{
  "status": "healthy",
  "components": {
    "database": "connected",
    "redis": "connected",
    "milvus": "connected",
    "ollama": "connected"
  }
}

# Kubernetes 存活探针
curl http://localhost:8000/health/live

# Kubernetes 就绪探针
curl http://localhost:8000/health/ready

# 检查 Milvus
curl http://localhost:9091/healthz

# 检查 Ollama
curl http://localhost:11434/api/tags
```

### 监控指标

建议结合以下工具监控：

| 工具 | 用途 |
|------|------|
| Prometheus + Grafana | 应用指标监控 |
| Loki | 日志聚合与搜索 |
| Alertmanager | 告警通知 |
| MySQL Exporter | 数据库监控 |

---

## 备份策略

### 自动备份

系统内置备份定时任务（`feature.backup`），默认每天凌晨 4 点执行。

通过管理 API 管理：

```bash
# 查看备份列表
curl http://localhost:8000/api/v1/admin/backups \
  -H "Authorization: Bearer <admin_token>"

# 手动创建备份
curl -X POST http://localhost:8000/api/v1/admin/backups/create \
  -H "Authorization: Bearer <admin_token>"
```

### 数据库手动备份

```bash
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/backup/mysql
mkdir -p $BACKUP_DIR

# 导出数据库
mysqldump -h $DB_HOST -u $DB_USER -p$DB_PASSWORD \
  --single-transaction \
  --routines \
  --triggers \
  research_pulse > $BACKUP_DIR/research_pulse_$DATE.sql

# 压缩
gzip $BACKUP_DIR/research_pulse_$DATE.sql

# 保留最近 30 天
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete

echo "Backup completed: research_pulse_$DATE.sql.gz"
```

添加到 crontab：

```bash
# 每天凌晨 5 点备份
0 5 * * * /opt/ResearchPulse/scripts/backup.sh >> /var/log/researchpulse-backup.log 2>&1
```

### Milvus 数据备份

```bash
# 停止 Milvus 后备份数据目录
docker compose -f docker-compose.milvus.yml stop milvus-standalone
tar -czf milvus_backup_$(date +%Y%m%d).tar.gz ./volumes/milvus/
docker compose -f docker-compose.milvus.yml start milvus-standalone
```

### 恢复流程

```bash
# MySQL 恢复
gunzip research_pulse_20260101.sql.gz
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD research_pulse < research_pulse_20260101.sql

# Milvus 恢复
docker compose -f docker-compose.milvus.yml stop milvus-standalone
tar -xzf milvus_backup_20260101.tar.gz -C ./
docker compose -f docker-compose.milvus.yml start milvus-standalone
```

---

## 性能优化

### 数据库优化

```sql
-- 确认索引存在（init.sql 中已创建）
SHOW INDEX FROM articles;

-- 关键索引
CREATE INDEX idx_articles_crawl_time ON articles(crawl_time);
CREATE INDEX idx_articles_source_type ON articles(source_type);
CREATE INDEX idx_articles_publish_time ON articles(publish_time);
CREATE UNIQUE INDEX idx_articles_dedup ON articles(source_type, source_id, external_id);

-- 定期优化表
OPTIMIZE TABLE articles;
OPTIMIZE TABLE ai_processing_logs;
```

### 连接池配置

```bash
# .env 或 config/defaults.yaml
DB_POOL_SIZE=20          # 生产环境建议增大
DB_MAX_OVERFLOW=40       # 突发连接数
DB_POOL_RECYCLE=3600     # 防止 MySQL wait_timeout 断连
```

### Gunicorn Worker 配置

```bash
gunicorn main:app \
    --workers 4 \                    # 2 * CPU 核心数 + 1
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --timeout 120 \                  # AI 处理可能需要较长时间
    --keep-alive 5 \
    --access-logfile logs/access.log \
    --error-logfile logs/error.log
```

---

## 故障排查

### 常见问题

#### 1. 数据库连接失败

```bash
# 检查 MySQL 服务状态
sudo systemctl status mysql

# 测试连接
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD -e "SELECT 1;"

# 检查连接数
mysql -e "SHOW STATUS LIKE 'Threads_connected';"
mysql -e "SHOW VARIABLES LIKE 'max_connections';"
```

#### 2. 端口被占用

```bash
# 查看端口占用
lsof -i :8000
ss -tlnp | grep 8000

# 杀死进程
kill -9 <PID>
```

#### 3. 权限问题

```bash
# 检查文件权限
chown -R www-data:www-data /opt/ResearchPulse
chmod -R 750 /opt/ResearchPulse
```

#### 4. Milvus 连接失败

```bash
# 检查容器状态
docker compose -f docker-compose.milvus.yml ps

# 查看日志
docker compose -f docker-compose.milvus.yml logs milvus-standalone

# 确认端口可达
curl http://localhost:9091/healthz

# 检查 etcd 和 MinIO 依赖
docker compose -f docker-compose.milvus.yml logs milvus-etcd
docker compose -f docker-compose.milvus.yml logs milvus-minio
```

#### 5. Ollama 模型加载失败

```bash
# 检查 Ollama 服务
curl http://localhost:11434/api/tags

# 重新下载模型
ollama pull qwen3:32b

# 检查磁盘空间（32B 模型约 18GB）
df -h

# 检查 GPU 状态
nvidia-smi
```

#### 6. 功能开关未生效

```bash
# 功能开关有 60 秒内存缓存，修改后最多等待 60 秒
# 或重启服务立即生效

# 检查当前功能开关状态
curl http://localhost:8000/api/v1/admin/features \
  -H "Authorization: Bearer <admin_token>"
```

#### 7. AI 处理超时

```bash
# 增加 Ollama 超时时间
OLLAMA_TIMEOUT=300  # 秒

# 或使用轻量模型
OLLAMA_MODEL=qwen3:8b

# 检查 Ollama 资源使用
docker stats ollama
```

#### 8. 邮件发送失败

```bash
# 推荐：使用邮件工具脚本发送测试邮件
./scripts/email.sh test --to your@email.com

# 指定后端测试
./scripts/email.sh test --to your@email.com --backend smtp
./scripts/email.sh test --to your@email.com --backend sendgrid

# 手动触发用户订阅通知
./scripts/email.sh notify

# 也可通过 control.sh 调用
./scripts/control.sh email test --to your@email.com
```

如需直接测试底层 SMTP 连接：

```bash
# Gmail 需要使用"应用专用密码"，不是账号密码
# 参考: https://support.google.com/accounts/answer/185833

python -c "
import smtplib
server = smtplib.SMTP('smtp.gmail.com', 587)
server.starttls()
server.login('your@gmail.com', 'your-app-password')
print('SMTP OK')
server.quit()
"
```

### 查看日志

```bash
# 实时查看应用日志
tail -f logs/app.log

# 查看错误
grep ERROR logs/app.log

# 查看特定模块日志
grep "ai_processor" logs/app.log
grep "crawler" logs/app.log

# Docker 容器日志
docker compose logs -f app
docker compose logs -f --tail=100 app
```
