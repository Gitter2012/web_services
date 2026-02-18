#!/bin/bash
# =============================================================================
# ResearchPulse v2 手动爬取触发脚本
# =============================================================================
# 用法: ./scripts/crawl.sh [source] [options]
#
# 示例:
#   ./scripts/crawl.sh all                 # 爬取所有已激活的数据源
#   ./scripts/crawl.sh arxiv               # 仅爬取 arXiv
#   ./scripts/crawl.sh arxiv cs.AI cs.CL   # 爬取指定的 arXiv 分类
#   ./scripts/crawl.sh rss                 # 仅爬取 RSS
#   ./scripts/crawl.sh rss <feed_id>       # 爬取指定的 RSS 源
#   ./scripts/crawl.sh weibo               # 爬取微博热搜
#   ./scripts/crawl.sh hackernews          # 爬取 HackerNews
#   ./scripts/crawl.sh reddit              # 爬取 Reddit
#   ./scripts/crawl.sh twitter             # 爬取 Twitter
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
PYTHON_SCRIPT="$PROJECT_DIR/scripts/_crawl_runner.py"

# 默认值
SOURCE="${1:-all}"
shift || true

# 显示帮助
show_help() {
    echo -e "${BLUE}ResearchPulse v2 手动爬取脚本${NC}"
    echo ""
    echo "用法: ./scripts/crawl.sh <source> [options]"
    echo ""
    echo "数据源:"
    echo -e "  ${CYAN}all${NC}         爬取所有已激活的数据源"
    echo -e "  ${CYAN}arxiv${NC}       爬取 arXiv 学术论文"
    echo -e "  ${CYAN}rss${NC}         爬取 RSS 订阅源"
    echo -e "  ${CYAN}weibo${NC}       爬取微博热搜"
    echo -e "  ${CYAN}hackernews${NC}  爬取 HackerNews"
    echo -e "  ${CYAN}reddit${NC}      爬取 Reddit"
    echo -e "  ${CYAN}twitter${NC}     爬取 Twitter"
    echo ""
    echo "选项:"
    echo "  --dry-run      仅模拟运行，不写入数据库"
    echo "  --verbose, -v  显示详细输出"
    echo "  --help, -h     显示此帮助信息"
    echo ""
    echo "示例:"
    echo -e "  ${GREEN}# 爬取所有数据源${NC}"
    echo "  ./scripts/crawl.sh all"
    echo ""
    echo -e "  ${GREEN}# 仅爬取 arXiv${NC}"
    echo "  ./scripts/crawl.sh arxiv"
    echo ""
    echo -e "  ${GREEN}# 爬取指定的 arXiv 分类${NC}"
    echo "  ./scripts/crawl.sh arxiv cs.AI cs.CL cs.LG"
    echo ""
    echo -e "  ${GREEN}# 爬取指定的 RSS 源${NC}"
    echo "  ./scripts/crawl.sh rss feed_id_123"
    echo ""
    echo -e "  ${GREEN}# 模拟运行${NC}"
    echo "  ./scripts/crawl.sh arxiv --dry-run"
    echo ""
}

# 检查环境
check_env() {
    if [ ! -f "$ENV_FILE" ]; then
        echo -e "${RED}错误: .env 文件不存在${NC}"
        echo "请先创建 .env 文件并配置数据库连接"
        exit 1
    fi

    # 加载环境变量
    set -a
    source "$ENV_FILE"
    set +a
}

# 检查 Python 环境
check_python() {
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}错误: 未找到 python3${NC}"
        exit 1
    fi

    # 检查必要的依赖
    python3 -c "import sqlalchemy, httpx" 2>/dev/null || {
        echo -e "${RED}错误: 缺少必要的 Python 依赖${NC}"
        echo "请运行: pip install sqlalchemy httpx"
        exit 1
    }
}

# 解析参数
DRY_RUN=false
VERBOSE=false
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
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
            EXTRA_ARGS+=("$1")
            shift
            ;;
    esac
done

# 显示帮助
if [ "$SOURCE" = "--help" ] || [ "$SOURCE" = "-h" ]; then
    show_help
    exit 0
fi

# 验证数据源
VALID_SOURCES=("all" "arxiv" "rss" "weibo" "hackernews" "reddit" "twitter")
IS_VALID=false
for s in "${VALID_SOURCES[@]}"; do
    if [ "$SOURCE" = "$s" ]; then
        IS_VALID=true
        break
    fi
done

if [ "$IS_VALID" = false ]; then
    echo -e "${RED}错误: 未知的数据源 '$SOURCE'${NC}"
    echo ""
    show_help
    exit 1
fi

# 检查环境
check_env
check_python

# 构建参数
PYTHON_ARGS=("$SOURCE")
if [ "$DRY_RUN" = true ]; then
    PYTHON_ARGS+=("--dry-run")
fi
if [ "$VERBOSE" = true ]; then
    PYTHON_ARGS+=("--verbose")
fi
if [ ${#EXTRA_ARGS[@]} -gt 0 ]; then
    PYTHON_ARGS+=("${EXTRA_ARGS[@]}")
fi

# 显示开始信息
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}ResearchPulse v2 手动爬取${NC}"
echo -e "${BLUE}============================================${NC}"
echo -e "数据源: ${CYAN}$SOURCE${NC}"
[ "$DRY_RUN" = true ] && echo -e "模式: ${YELLOW}模拟运行 (dry-run)${NC}"
[ ${#EXTRA_ARGS[@]} -gt 0 ] && echo -e "额外参数: ${CYAN}${EXTRA_ARGS[*]}${NC}"
echo -e "${BLUE}--------------------------------------------${NC}"
echo ""

# 运行 Python 脚本
cd "$PROJECT_DIR"

# 使用 exec 替换当前进程，或直接运行
python3 "${PYTHON_SCRIPT}" "${PYTHON_ARGS[@]}"

EXIT_CODE=$?

# 显示结果
echo ""
echo -e "${BLUE}--------------------------------------------${NC}"
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}爬取完成${NC}"
else
    echo -e "${RED}爬取失败 (退出码: $EXIT_CODE)${NC}"
fi

exit $EXIT_CODE
