#!/bin/bash

echo "================================================"
echo "  德州扑克游戏 - 云服务器部署脚本"
echo "================================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查是否为root用户
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}请使用root用户运行此脚本${NC}"
    exit 1
fi

echo "1. 更新系统包..."
apt-get update

echo ""
echo "2. 安装必要的软件..."
apt-get install -y python3 python3-pip nginx git curl

echo ""
echo "3. 安装Docker（如果未安装）..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
    echo -e "${GREEN}✓ Docker安装完成${NC}"
else
    echo -e "${GREEN}✓ Docker已安装${NC}"
fi

echo ""
echo "4. 安装Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    curl -L "https://github.com/docker/compose/releases/download/1.29.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    echo -e "${GREEN}✓ Docker Compose安装完成${NC}"
else
    echo -e "${GREEN}✓ Docker Compose已安装${NC}"
fi

echo ""
echo "5. 创建应用目录..."
APP_DIR="/opt/poker-game"
mkdir -p $APP_DIR
cd $APP_DIR

echo ""
echo "6. 复制应用文件..."
# 假设已经将文件上传到服务器
echo "请确保已将以下文件/目录上传到 $APP_DIR:"
echo "  - src/ (包含main.py, poker_game.py, ai_player.py)"
echo "  - web/ (包含index.html)"
echo "  - requirements.txt"
echo "  - Dockerfile"
echo "  - docker-compose.yml"
echo "  - nginx.conf"

read -p "是否继续? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

echo ""
echo "7. 构建Docker镜像..."
docker-compose build

echo ""
echo "8. 启动应用..."
docker-compose up -d

echo ""
echo "9. 配置Nginx..."
# 如果nginx.conf存在，复制到Nginx配置目录
if [ -f "$APP_DIR/nginx.conf" ]; then
    cp nginx.conf /etc/nginx/sites-available/poker-game
    ln -sf /etc/nginx/sites-available/poker-game /etc/nginx/sites-enabled/
else
    echo -e "${YELLOW}⚠ nginx.conf文件不存在，跳过Nginx配置${NC}"
    echo "  应用将通过 http://your-server-ip:8000 直接访问"
    echo ""
    echo "如果需要Nginx代理，请手动配置"
fi

if [ -f "/etc/nginx/sites-available/poker-game" ]; then
    # 删除默认配置
    rm -f /etc/nginx/sites-enabled/default

    # 测试Nginx配置
    nginx -t

    if [ $? -eq 0 ]; then
        # 重启Nginx
        systemctl restart nginx
        echo -e "${GREEN}✓ Nginx配置完成${NC}"
    else
        echo -e "${RED}✗ Nginx配置错误${NC}"
        exit 1
    fi
fi

echo ""
echo "10. 配置防火墙..."
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 22/tcp
echo -e "${YELLOW}注意：如需启用防火墙，请运行: ufw enable${NC}"

echo ""
echo "================================================"
echo "  部署完成！"
echo "================================================"
echo ""
echo "应用已启动，可以通过以下方式访问："
if [ -f "/etc/nginx/sites-available/poker-game" ]; then
    echo "  HTTP:  http://your-server-ip"
else
    echo "  HTTP:  http://your-server-ip:8000"
fi
echo ""
echo "常用命令："
echo "  查看日志: docker-compose logs -f"
echo "  重启应用: docker-compose restart"
echo "  停止应用: docker-compose down"
echo "  更新应用: docker-compose up -d --build"
echo ""
if [ -f "/etc/nginx/sites-available/poker-game" ]; then
    echo "Nginx配置文件: /etc/nginx/sites-available/poker-game"
fi
echo ""
echo -e "${GREEN}部署成功！${NC}"
