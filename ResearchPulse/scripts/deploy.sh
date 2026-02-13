#!/bin/bash
# =============================================================================
# ResearchPulse v2 部署脚本
# =============================================================================
# 用法: ./scripts/deploy.sh [--skip-deps] [--skip-db]
# =============================================================================

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

SKIP_DEPS=false
SKIP_DB=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-deps)
            SKIP_DEPS=true
            shift
            ;;
        --skip-db)
            SKIP_DB=true
            shift
            ;;
        *)
            shift
            ;;
    esac
done

echo -e "${BLUE}=============================================================${NC}"
echo -e "${BLUE}ResearchPulse v2 部署脚本${NC}"
echo -e "${BLUE}=============================================================${NC}"
echo ""

cd "$PROJECT_DIR"

# 1. 检查 Python
echo -e "${YELLOW}[1/5] 检查 Python...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: Python3 未安装${NC}"
    exit 1
fi
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python 版本: $PYTHON_VERSION"

# 2. 安装依赖
if [ "$SKIP_DEPS" = false ]; then
    echo -e "${YELLOW}[2/5] 安装依赖...${NC}"
    pip install -r requirements.txt -q 2>/dev/null || pip3 install -r requirements.txt -q
    echo -e "${GREEN}依赖安装完成${NC}"
else
    echo -e "${YELLOW}[2/5] 跳过依赖安装${NC}"
fi

# 3. 检查环境配置
echo -e "${YELLOW}[3/5] 检查环境配置...${NC}"
if [ ! -f ".env" ]; then
    echo -e "${RED}错误: .env 文件不存在${NC}"
    echo "请复制 .env.example 到 .env 并填写配置"
    echo "  cp .env.example .env"
    exit 1
fi

source .env
if [ -z "$DB_HOST" ] || [ -z "$DB_NAME" ] || [ -z "$DB_USER" ]; then
    echo -e "${RED}错误: 数据库配置不完整${NC}"
    exit 1
fi
echo -e "${GREEN}环境配置检查通过${NC}"

# 4. 初始化数据库
if [ "$SKIP_DB" = false ]; then
    echo -e "${YELLOW}[4/5] 初始化数据库...${NC}"
    if command -v mysql &> /dev/null; then
        mysql -h "$DB_HOST" -P "${DB_PORT:-3306}" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" < sql/init.sql 2>/dev/null
        echo -e "${GREEN}数据库初始化完成${NC}"
    else
        echo -e "${YELLOW}跳过: mysql 客户端未安装${NC}"
    fi
else
    echo -e "${YELLOW}[4/5] 跳过数据库初始化${NC}"
fi

# 5. 创建目录
echo -e "${YELLOW}[5/5] 创建必要目录...${NC}"
mkdir -p "$PROJECT_DIR/data"
mkdir -p "$PROJECT_DIR/backups"
mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/run"
echo -e "${GREEN}目录创建完成${NC}"

echo ""
echo -e "${GREEN}=============================================================${NC}"
echo -e "${GREEN}部署完成！${NC}"
echo -e "${GREEN}=============================================================${NC}"
echo ""
echo "下一步："
echo "  启动: ./scripts/service.sh start --daemon"
echo "  状态: ./scripts/service.sh status"
echo ""
