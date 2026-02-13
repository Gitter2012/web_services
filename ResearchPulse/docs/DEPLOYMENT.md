# 部署文档

## 环境要求

| 软件 | 版本 | 说明 |
|------|------|------|
| Python | 3.10+ | 运行环境 |
| MySQL | 8.0+ | 主数据库 |
| Redis | 6.0+ | 缓存（可选） |
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

#### docker-compose.yml

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
```

启动：

```bash
docker-compose up -d
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

### 查看日志

```bash
# 实时查看日志
tail -f logs/app.log

# 查看错误
grep ERROR logs/app.log
```
