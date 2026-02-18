#!/bin/bash
# =============================================================================
# ResearchPulse v2 arXiv 数据修复脚本
# =============================================================================
# 用法: ./scripts/repair-arxiv.sh [options]
#
# 功能: 修复数据库中 arXiv 文章缺失的作者和摘要数据
#       从 arXiv Atom API 获取完整元数据并回填到数据库
#
# 选项:
#   --dry-run       仅检查缺失数据，不执行修复
#   --batch-size N  每批请求的 arXiv ID 数量 (默认: 20)
#   --verbose, -v   显示详细输出
#   --help, -h      显示帮助信息
#
# 示例:
#   ./scripts/repair-arxiv.sh                  # 执行修复
#   ./scripts/repair-arxiv.sh --dry-run        # 仅检查
#   ./scripts/repair-arxiv.sh --batch-size 50  # 自定义批次大小
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
PYTHON_SCRIPT="$PROJECT_DIR/scripts/repair_arxiv.py"

# 显示帮助
show_help() {
    echo -e "${BLUE}ResearchPulse v2 arXiv 数据修复${NC}"
    echo ""
    echo "用法: ./scripts/repair-arxiv.sh [options]"
    echo ""
    echo "功能:"
    echo "  修复数据库中 arXiv 文章缺失的作者和摘要数据"
    echo "  从 arXiv Atom API 获取完整元数据并回填到数据库"
    echo ""
    echo "选项:"
    echo "  --dry-run       仅检查缺失数据，不执行修复"
    echo "  --batch-size N  每批请求的 arXiv ID 数量 (默认: 20)"
    echo "  --verbose, -v   显示详细输出"
    echo "  --help, -h      显示帮助信息"
    echo ""
    echo "示例:"
    echo -e "  ${GREEN}# 检查缺失数据${NC}"
    echo "  ./scripts/repair-arxiv.sh --dry-run"
    echo ""
    echo -e "  ${GREEN}# 执行修复${NC}"
    echo "  ./scripts/repair-arxiv.sh"
    echo ""
    echo -e "  ${GREEN}# 大批次修复${NC}"
    echo "  ./scripts/repair-arxiv.sh --batch-size 50"
    echo ""
}

# 解析参数
PYTHON_ARGS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            PYTHON_ARGS+=("--dry-run")
            shift
            ;;
        --batch-size)
            PYTHON_ARGS+=("--batch-size" "$2")
            shift 2
            ;;
        --verbose|-v)
            PYTHON_ARGS+=("--verbose")
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
echo -e "${BLUE}ResearchPulse v2 arXiv 数据修复${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# 运行 Python 脚本
cd "$PROJECT_DIR"
python3 "$PYTHON_SCRIPT" "${PYTHON_ARGS[@]}"

EXIT_CODE=$?

# 显示结果
echo ""
echo -e "${BLUE}--------------------------------------------${NC}"
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}修复完成${NC}"
else
    echo -e "${RED}修复失败或仍有缺失数据 (退出码: $EXIT_CODE)${NC}"
fi

exit $EXIT_CODE
