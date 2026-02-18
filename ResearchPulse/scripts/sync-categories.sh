#!/bin/bash
# =============================================================================
# ResearchPulse v2 arXiv 分类同步脚本
# =============================================================================
# 用法: ./scripts/sync-categories.sh [options]
#
# 功能: 从 arXiv 官方网站抓取分类列表并同步到数据库
#
# 选项:
#   --force, -f     强制同步，跳过确认
#   --verbose, -v   显示详细输出
#   --help, -h      显示帮助信息
#
# 示例:
#   ./scripts/sync-categories.sh           # 交互式同步
#   ./scripts/sync-categories.sh --force   # 强制同步
# =============================================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 脚本路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"
PYTHON_SCRIPT="$PROJECT_DIR/scripts/sync_arxiv_categories.py"

# 默认值
FORCE=false
VERBOSE=false

# 显示帮助
show_help() {
    echo -e "${BLUE}ResearchPulse v2 arXiv 分类同步${NC}"
    echo ""
    echo "用法: ./scripts/sync-categories.sh [options]"
    echo ""
    echo "功能:"
    echo "  从 arXiv 官方网站抓取分类列表并同步到数据库"
    echo "  如果网站抓取失败，使用内置的分类列表作为备用"
    echo ""
    echo "选项:"
    echo "  --force, -f     强制同步，跳过确认"
    echo "  --verbose, -v   显示详细输出"
    echo "  --help, -h      显示帮助信息"
    echo ""
    echo "示例:"
    echo "  ./scripts/sync-categories.sh           # 交互式同步"
    echo "  ./scripts/sync-categories.sh --force   # 强制同步"
    echo ""
}

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --force|-f)
            FORCE=true
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            echo -e "${RED}未知参数: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# 检查环境
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}错误: .env 文件不存在${NC}"
    echo "请先创建 .env 文件并配置数据库连接"
    exit 1
fi

# 加载环境变量
set -a
source "$ENV_FILE"
set +a

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到 python3${NC}"
    exit 1
fi

# 显示开始信息
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}ResearchPulse v2 arXiv 分类同步${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# 确认操作
if [ "$FORCE" = false ]; then
    echo -e "${YELLOW}此操作将同步 arXiv 分类到数据库${NC}"
    echo -e "${YELLOW}已存在的分类将被更新，新分类将被添加${NC}"
    echo ""
    read -p "是否继续? [y/N] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}操作已取消${NC}"
        exit 0
    fi
fi

# 运行 Python 脚本
echo -e "${CYAN}正在同步 arXiv 分类...${NC}"
echo ""

cd "$PROJECT_DIR"

if [ "$VERBOSE" = true ]; then
    python3 "$PYTHON_SCRIPT"
else
    python3 "$PYTHON_SCRIPT" 2>&1 | while read -r line; do
        # 过滤掉 DEBUG 级别的日志
        if [[ ! "$line" =~ ^.*DEBUG.*$ ]]; then
            echo "$line"
        fi
    done
fi

EXIT_CODE=$?

# 显示结果
echo ""
echo -e "${BLUE}--------------------------------------------${NC}"
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}同步完成${NC}"
else
    echo -e "${RED}同步失败 (退出码: $EXIT_CODE)${NC}"
fi

exit $EXIT_CODE
