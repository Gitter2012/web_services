#!/bin/bash
# =============================================================================
# ResearchPulse v2 AI 流水线手动运行脚本
# =============================================================================
# 用法: ./scripts/ai-pipeline.sh [stages] [options]
#
# 流水线阶段（按依赖顺序）:
#   ai        AI 文章处理（摘要/分类/评分）
#   embedding 向量嵌入计算
#   event     事件聚类
#   topic     主题发现
#
# 示例:
#   ./scripts/ai-pipeline.sh all                   # 运行全部阶段
#   ./scripts/ai-pipeline.sh ai                    # 仅运行 AI 处理
#   ./scripts/ai-pipeline.sh ai embedding          # 运行 AI 处理 + 嵌入计算
#   ./scripts/ai-pipeline.sh all --limit 200       # 每阶段最多处理 200 条
#   ./scripts/ai-pipeline.sh all --force            # 忽略功能开关，强制运行
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
PYTHON_SCRIPT="$PROJECT_DIR/scripts/_ai_pipeline_runner.py"

# 显示帮助
show_help() {
    echo -e "${BLUE}ResearchPulse v2 AI 流水线手动运行脚本${NC}"
    echo ""
    echo "用法: ./scripts/ai-pipeline.sh <stages...> [options]"
    echo ""
    echo "阶段 (按流水线顺序):"
    echo -e "  ${CYAN}all${NC}         运行全部阶段（按顺序依次执行）"
    echo -e "  ${CYAN}ai${NC}          AI 文章处理（摘要/分类/评分）   [feature.ai_processor]"
    echo -e "  ${CYAN}embedding${NC}   向量嵌入计算                     [feature.embedding]"
    echo -e "  ${CYAN}event${NC}       事件聚类                         [feature.event_clustering]"
    echo -e "  ${CYAN}topic${NC}       主题发现                         [feature.topic_radar]"
    echo ""
    echo "选项:"
    echo "  --limit <n>    每阶段最多处理的文章数 (默认: 50)"
    echo "  --force        忽略功能开关，强制运行所有指定阶段"
    echo "  --verbose, -v  显示详细输出（包含完整错误栈）"
    echo "  --json         以 JSON 格式输出结果"
    echo "  --help, -h     显示此帮助信息"
    echo ""
    echo "示例:"
    echo -e "  ${GREEN}# 运行完整的 AI 流水线${NC}"
    echo "  ./scripts/ai-pipeline.sh all"
    echo ""
    echo -e "  ${GREEN}# 仅运行 AI 处理阶段${NC}"
    echo "  ./scripts/ai-pipeline.sh ai"
    echo ""
    echo -e "  ${GREEN}# 运行 AI 处理 + 嵌入计算${NC}"
    echo "  ./scripts/ai-pipeline.sh ai embedding"
    echo ""
    echo -e "  ${GREEN}# 每阶段最多处理 200 条文章${NC}"
    echo "  ./scripts/ai-pipeline.sh all --limit 200"
    echo ""
    echo -e "  ${GREEN}# 忽略功能开关，强制运行${NC}"
    echo "  ./scripts/ai-pipeline.sh all --force"
    echo ""
    echo -e "  ${GREEN}# 仅运行嵌入到主题发现（跳过 AI 处理）${NC}"
    echo "  ./scripts/ai-pipeline.sh embedding event topic"
    echo ""
    echo "流水线依赖关系:"
    echo "  ai → embedding → event → topic"
    echo "  各阶段按此顺序自动排列，无论命令行中的输入顺序如何。"
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

    if [ ! -f "$PYTHON_SCRIPT" ]; then
        echo -e "${RED}错误: Python 脚本不存在: ${PYTHON_SCRIPT}${NC}"
        exit 1
    fi

    # 检查必要的依赖
    python3 -c "import sqlalchemy, httpx" 2>/dev/null || {
        echo -e "${RED}错误: 缺少必要的 Python 依赖${NC}"
        echo "请运行: pip install -r requirements.txt"
        exit 1
    }
}

# 解析参数
STAGES=()
OPTIONS=()
SHOW_HELP=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            SHOW_HELP=true
            shift
            ;;
        --limit|--force|--verbose|-v|--json)
            OPTIONS+=("$1")
            # --limit 需要带参数值
            if [ "$1" = "--limit" ] && [ -n "$2" ]; then
                shift
                OPTIONS+=("$1")
            fi
            shift
            ;;
        all|ai|embedding|event|topic)
            STAGES+=("$1")
            shift
            ;;
        *)
            echo -e "${RED}错误: 未知参数 '$1'${NC}"
            echo ""
            show_help
            exit 1
            ;;
    esac
done

# 显示帮助
if [ "$SHOW_HELP" = true ] || [ ${#STAGES[@]} -eq 0 ]; then
    show_help
    exit 0
fi

# 检查环境
check_env
check_python

# 构建参数
PYTHON_ARGS=("${STAGES[@]}" "${OPTIONS[@]}")

# 显示开始信息
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}ResearchPulse v2 AI 流水线${NC}"
echo -e "${BLUE}============================================${NC}"
echo -e "阶段: ${CYAN}${STAGES[*]}${NC}"
echo -e "${BLUE}--------------------------------------------${NC}"
echo ""

# 运行 Python 脚本
cd "$PROJECT_DIR"
python3 "${PYTHON_SCRIPT}" "${PYTHON_ARGS[@]}"

EXIT_CODE=$?

# 显示结果
echo ""
echo -e "${BLUE}--------------------------------------------${NC}"
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}流水线执行完毕${NC}"
else
    echo -e "${RED}流水线执行失败 (退出码: $EXIT_CODE)${NC}"
fi

exit $EXIT_CODE
