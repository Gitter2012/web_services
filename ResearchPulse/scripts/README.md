# ResearchPulse v2 运维脚本

## 脚本列表

| 脚本 | 描述 |
|------|------|
| `control.sh` | 统一入口（推荐） |
| `service.sh` | 服务管理 |
| `deploy.sh` | 部署 |
| `init.sh` | 初始化 |

## 快速使用

```bash
# 部署
./scripts/control.sh deploy

# 启动（后台）
./scripts/control.sh start -d

# 状态
./scripts/control.sh status -v

# 停止
./scripts/control.sh stop

# 重启
./scripts/control.sh restart

# 日志
./scripts/control.sh logs -f
```

## 服务管理

```bash
./scripts/service.sh start --port 8080 -d
./scripts/service.sh stop --force
./scripts/service.sh restart
./scripts/service.sh status -v
```

## 环境变量

项目根目录创建 `.env`：

```env
DB_HOST=localhost
DB_PORT=3306
DB_NAME=research_pulse
DB_USER=research_user
DB_PASSWORD=your_password
JWT_SECRET_KEY=your_secret
```
