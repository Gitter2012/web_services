# 部署文件说明

本目录包含德州扑克游戏的部署配置文件。

## 文件说明

### Dockerfile
Docker镜像配置文件，用于构建应用容器。

### docker-compose.yml
Docker Compose配置文件，用于启动和管理服务。

### nginx.conf
Nginx反向代理配置文件，支持WebSocket连接。

### deploy.sh
云服务器自动部署脚本，包含以下功能：
- 自动安装Docker和Docker Compose
- 构建并启动Docker容器
- 配置Nginx反向代理
- 配置防火墙规则

使用方法：
```bash
chmod +x deploy.sh
sudo ./deploy.sh
```

### start.sh
本地开发环境启动脚本。

使用方法：
```bash
chmod +x start.sh
./start.sh
```

## 部署方式

### 方式一：Docker部署（推荐）

1. 确保已安装Docker和Docker Compose
2. 在项目根目录运行：
```bash
docker-compose build
docker-compose up -d
```

### 方式二：使用部署脚本

1. 将整个项目上传到服务器
2. 进入deploy目录
3. 运行部署脚本：
```bash
chmod +x deploy.sh
sudo ./deploy.sh
```

### 方式三：手动启动

```bash
pip install -r requirements.txt
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

## 端口说明

- 8000: 应用HTTP端口
- 80: Nginx代理端口（如果配置了Nginx）

## 注意事项

1. 确保8000端口未被占用
2. 如果使用Nginx，确保80端口未被占用
3. 部署前请检查并修改nginx.conf中的server_name
4. 生产环境建议使用HTTPS
