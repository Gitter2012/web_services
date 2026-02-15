#!/bin/bash
# =============================================================================
# ResearchPulse v2 初始化脚本
# =============================================================================
# 用法: ./scripts/init.sh [--with-sample-data]
# =============================================================================

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
[ -x "/root/myenv/bin/python" ] && PYTHON_BIN="/root/myenv/bin/python" || PYTHON_BIN="python"

WITH_SAMPLE_DATA=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --with-sample-data)
            WITH_SAMPLE_DATA=true
            shift
            ;;
        *)
            shift
            ;;
    esac
done

echo -e "${BLUE}=============================================================${NC}"
echo -e "${BLUE}ResearchPulse v2 初始化脚本${NC}"
echo -e "${BLUE}=============================================================${NC}"
echo ""

cd "$PROJECT_DIR"

if [ -f ".env" ]; then
    source .env
else
    echo -e "${RED}错误: .env 文件不存在${NC}"
    exit 1
fi

# 1. 数据库表结构
echo -e "${YELLOW}[1/2] 初始化数据库表结构...${NC}"

if command -v mysql &> /dev/null; then
    mysql -h "$DB_HOST" -P "${DB_PORT:-3306}" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" < sql/init.sql 2>&1 | grep -v "Warning" || true
    echo -e "${GREEN}数据库表结构初始化完成${NC}"
else
    echo -e "${RED}错误: mysql 客户端未安装${NC}"
    echo "请手动执行: mysql -h $DB_HOST -u $DB_USER -p $DB_NAME < sql/init.sql"
    exit 1
fi

# 2. 默认数据
echo -e "${YELLOW}[2/2] 初始化默认数据...${NC}"

$PYTHON_BIN << 'PYTHON_SCRIPT'
import asyncio

async def init_data():
    from core.database import get_session_factory
    from core.models.permission import DEFAULT_PERMISSIONS, DEFAULT_ROLES
    from sqlalchemy import text
    
    factory = get_session_factory()
    
    async with factory() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM roles"))
        if result.scalar() > 0:
            print("  数据已存在，跳过初始化")
            return
        
        for perm in DEFAULT_PERMISSIONS:
            await session.execute(
                text("INSERT IGNORE INTO permissions (name, resource, action, description) VALUES (:name, :resource, :action, :description)"),
                perm
            )
        
        for role_name, role_data in DEFAULT_ROLES.items():
            await session.execute(
                text("INSERT IGNORE INTO roles (name, description) VALUES (:name, :description)"),
                {"name": role_name, "description": role_data["description"]}
            )
        
        for role_name, role_data in DEFAULT_ROLES.items():
            for perm_name in role_data["permissions"]:
                await session.execute(
                    text("INSERT IGNORE INTO role_permissions (role_id, permission_id) SELECT r.id, p.id FROM roles r, permissions p WHERE r.name = :role AND p.name = :perm"),
                    {"role": role_name, "perm": perm_name}
                )
        
        await session.commit()
        print("  默认角色和权限初始化完成")

asyncio.run(init_data())
PYTHON_SCRIPT

echo -e "${GREEN}初始化完成${NC}"
echo ""
echo "数据库: $DB_HOST:${DB_PORT:-3306}/$DB_NAME"
echo "启动:   ./scripts/service.sh start --daemon"
echo ""
