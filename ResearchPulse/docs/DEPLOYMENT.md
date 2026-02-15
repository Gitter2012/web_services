# 部署文档

> 文档维护说明：部署步骤如有变更，请同步更新此文档。

## 环境要求

| 软件 | 版本 | 说明 |
|------|------|------|
| Python | 3.10+ | 运行环境 |
| MySQL | 8.0+ | 主数据库 |
| Redis | 6.0+ | 缓存（可选） |
| Milvus | 2.3+ | 向量数据库（可选，用于嵌入和相似检索） |
| Ollama | 最新版 | 本地 AI 推理（可选，用于 AI 分析） |
| Nginx | 1.18+ | 反向代理（推荐） |

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
pip install -r requirements.txt
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

# JWT
JWT_SECRET_KEY=your-secret-key

# 超级管理员
SUPERUSER_USERNAME=admin
SUPERUSER_EMAIL=admin@example.com
SUPERUSER_PASSWORD=admin_password
```

### 5. 初始化数据库

```bash
# 创建数据库
mysql -u root -p -e "CREATE DATABASE research_pulse CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 创建用户
mysql -u root -p -e "CREATE USER 'research_user'@'%' IDENTIFIED BY 'your_password';"
mysql -u root -p -e "GRANT ALL PRIVILEGES ON research_pulse.* TO 'research_user'@'%';"
mysql -u root -p -e "FLUSH PRIVILEGES;"

# 初始化表结构
mysql -u research_user -p research_pulse < sql/init.sql
```

### 6. 启动服务

```bash
python main.py
```

或使用 uvicorn：

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 7. 启动功能开关初始化

首次启动时，系统会自动将 `common/feature_config.py` 中 `DEFAULT_CONFIGS` 的功能开关写入数据库。所有高级功能默认关闭，可通过管理 API 启用：

```bash
# 启用 AI 分析功能
curl -X PUT http://localhost:8000/api/v1/admin/features/feature.ai_processor \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

---

## Milvus 部署（可选）

Milvus 是向量嵌入和相似文章检索功能的依赖。仅在启用 `feature.embedding` 时需要。

### 使用项目提供的 docker-compose

项目根目录下提供了 `docker-compose.milvus.yml`，包含 Milvus 及其依赖（etcd、MinIO）：

```bash
docker-compose -f docker-compose.milvus.yml up -d
```

该配置启动三个服务：

| 服务 | 容器名 | 端口 | 说明 |
|------|--------|------|------|
| milvus-etcd | rp-milvus-etcd | - | 元数据存储 |
| milvus-minio | rp-milvus-minio | 9001 | 对象存储 |
| milvus-standalone | rp-milvus | 19530, 9091 | Milvus 服务 |

数据存储在 `./volumes/` 目录下。

### 验证 Milvus

```bash
# 检查 Milvus 是否启动
curl http://localhost:9091/healthz

# 应返回 "OK"
```

### 配置连接

```bash
# .env
MILVUS_HOST=localhost
MILVUS_PORT=19530
EMBEDDING_ENABLED=true
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
```

### 启动服务

```bash
ollama serve
```

### 下载模型

```bash
# 下载默认模型
ollama pull qwen3:32b

# 可选：下载轻量模型
ollama pull qwen3:8b
```

### 验证

```bash
# 测试模型
ollama run qwen3:32b "Hello"
```

### 配置连接

```bash
# .env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:32b
```

### GPU 支持

Ollama 自动检测和使用 GPU。确保安装了 NVIDIA 驱动和 CUDA：

```bash
# 检查 GPU
nvidia-smi

# Ollama 会自动使用可用的 GPU
ollama serve
```

---

## 生产环境部署

### 使用 Systemd

创建服务文件 `/etc/systemd/system/researchpulse.service`：

```ini
[Unit]
Description=ResearchPulse Service
After=network.target mysql.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/ResearchPulse
Environment="PATH=/opt/ResearchPulse/venv/bin"
ExecStart=/opt/ResearchPulse/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable researchpulse
sudo systemctl start researchpulse
```

---

### 使用 Docker

#### Dockerfile

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["python", "main.py"]
```

#### docker-compose.yml（完整版，含 Milvus）

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
      - AI_PROVIDER=ollama
      - OLLAMA_BASE_URL=http://ollama:11434
      - MILVUS_HOST=milvus
      - MILVUS_PORT=19530
    depends_on:
      - db
      - redis
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs

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

  redis:
    image: redis:6-alpine
    volumes:
      - redis_data:/data

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

  minio:
    image: minio/minio:RELEASE.2023-03-20T20-16-18Z
    environment:
      MINIO_ACCESS_KEY: minioadmin
      MINIO_SECRET_KEY: minioadmin
    volumes:
      - minio_data:/minio_data
    command: minio server /minio_data --console-address ":9001"

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
      - etcd
      - minio

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

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - app

volumes:
  mysql_data:
  redis_data:
  etcd_data:
  minio_data:
  milvus_data:
  ollama_data:
```

启动：

```bash
# 启动全部服务
docker-compose up -d

# 仅启动核心服务（不含 Milvus、Ollama）
docker-compose up -d app db redis nginx

# 下载 Ollama 模型（首次启动后执行）
docker-compose exec ollama ollama pull qwen3:32b
```

---

### Nginx 配置

`/etc/nginx/sites-available/researchpulse`：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 重定向到 HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL 配置
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # 静态文件缓存
    location /static/ {
        alias /opt/ResearchPulse/static/;
        expires 30d;
    }

    # API 和页面
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket 支持
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # 文件上传大小限制
    client_max_body_size 10M;
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

使用 Let's Encrypt：

```bash
# 安装 certbot
sudo apt install certbot python3-certbot-nginx

# 获取证书
sudo certbot --nginx -d your-domain.com

# 自动续期
sudo certbot renew --dry-run
```

---

## 监控与日志

### 日志位置

```
logs/
├── app.log         # 应用日志
├── access.log      # 访问日志
└── error.log       # 错误日志
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
}
```

### 健康检查

```bash
# 检查服务状态
curl http://localhost:8000/health

# 响应示例
{"status": "healthy", "database": "connected"}

# 检查 Milvus 状态
curl http://localhost:9091/healthz

# 检查 Ollama 状态
curl http://localhost:11434/api/tags
```

---

## 备份策略

### 数据库备份

```bash
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d)
BACKUP_DIR=/backup/mysql
mkdir -p $BACKUP_DIR

mysqldump -h $DB_HOST -u $DB_USER -p$DB_PASSWORD research_pulse > $BACKUP_DIR/research_pulse_$DATE.sql

# 保留最近 30 天
find $BACKUP_DIR -name "*.sql" -mtime +30 -delete
```

添加到 crontab：

```bash
# 每天凌晨 5 点备份
0 5 * * * /opt/ResearchPulse/scripts/backup.sh
```

### Milvus 数据备份

Milvus 数据存储在 `./volumes/milvus/` 目录下。建议定期备份：

```bash
# 停止 Milvus 后备份数据
docker-compose -f docker-compose.milvus.yml stop milvus-standalone
tar -czf milvus_backup_$(date +%Y%m%d).tar.gz ./volumes/milvus/
docker-compose -f docker-compose.milvus.yml start milvus-standalone
```

---

## 性能优化

### 数据库优化

```sql
-- 添加索引
CREATE INDEX idx_articles_crawl_time ON articles(crawl_time);
CREATE INDEX idx_articles_source_type ON articles(source_type);

-- 定期优化表
OPTIMIZE TABLE articles;
```

### 连接池配置

```python
# settings.py
DB_POOL_SIZE = 20
DB_MAX_OVERFLOW = 40
```

### Gunicorn 部署

```bash
pip install gunicorn

gunicorn main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --access-logfile logs/access.log \
    --error-logfile logs/error.log
```

---

## 故障排查

### 常见问题

1. **数据库连接失败**
   ```bash
   # 检查数据库连接
   mysql -h $DB_HOST -u $DB_USER -p
   ```

2. **端口被占用**
   ```bash
   # 查看端口占用
   lsof -i :8000

   # 杀死进程
   kill -9 <PID>
   ```

3. **权限问题**
   ```bash
   # 检查文件权限
   chown -R www-data:www-data /opt/ResearchPulse
   ```

4. **Milvus 连接失败**
   ```bash
   # 检查 Milvus 容器状态
   docker-compose -f docker-compose.milvus.yml ps

   # 查看 Milvus 日志
   docker-compose -f docker-compose.milvus.yml logs milvus-standalone

   # 确认端口可达
   curl http://localhost:9091/healthz
   ```

5. **Ollama 模型加载失败**
   ```bash
   # 检查 Ollama 服务状态
   curl http://localhost:11434/api/tags

   # 重新下载模型
   ollama pull qwen3:32b

   # 检查磁盘空间（模型文件较大）
   df -h
   ```

6. **功能开关未生效**
   ```bash
   # 功能开关有 60 秒缓存，修改后最多等待 60 秒生效
   # 也可以重启服务立即生效

   # 检查当前功能开关状态
   curl http://localhost:8000/api/v1/admin/features \
     -H "Authorization: Bearer <admin_token>"
   ```

### 查看日志

```bash
# 实时查看日志
tail -f logs/app.log

# 查看错误
grep ERROR logs/app.log
```
