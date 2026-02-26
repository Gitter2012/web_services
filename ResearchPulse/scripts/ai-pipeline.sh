#!/bin/bash
# =============================================================================
# ResearchPulse v2 AI 流水线手动运行脚本
# =============================================================================
# 用法: ./scripts/ai-pipeline.sh [stages] [options]
#
# 流水线阶段（按依赖顺序）:
#   ai        AI 文章处理（摘要/分类/评分）
#   translate arXiv 文章标题翻译
#   embedding 向量嵌入计算
#   event     事件聚类
#   topic     主题发现
#
# 重处理（独立子命令）:
#   reprocess 对已有文章重新运行 AI 分析流程
#   clean-thinking 清理文章中的 thinking 标签内容
#
# 示例:
#   ./scripts/ai-pipeline.sh all                   # 运行全部阶段
#   ./scripts/ai-pipeline.sh ai                    # 仅运行 AI 处理
#   ./scripts/ai-pipeline.sh ai translate          # 运行 AI 处理 + 标题翻译
#   ./scripts/ai-pipeline.sh translate             # 仅翻译 arXiv 文章标题
#   ./scripts/ai-pipeline.sh all --limit 200       # 每阶段最多处理 200 条
#   ./scripts/ai-pipeline.sh all --force            # 忽略功能开关，强制运行
#   ./scripts/ai-pipeline.sh reprocess --debug      # Debug 模式重处理 3 篇
#   ./scripts/ai-pipeline.sh reprocess --limit 100  # 批量重处理 100 篇
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
REPROCESS_SCRIPT="$PROJECT_DIR/scripts/reprocess_articles.py"
CLEAN_THINKING_SCRIPT="$PROJECT_DIR/scripts/clean_thinking_in_articles.py"

# 显示帮助
show_help() {
    echo -e "${BLUE}ResearchPulse v2 AI 流水线手动运行脚本${NC}"
    echo ""
    echo "用法: ./scripts/ai-pipeline.sh <stages...> [options]"
    echo ""
    echo "阶段 (按流水线顺序):"
    echo -e "  ${CYAN}all${NC}         运行全部阶段（按顺序依次执行）"
    echo -e "  ${CYAN}ai${NC}          AI 文章处理（摘要/分类/评分）   [feature.ai_processor]"
    echo -e "  ${CYAN}translate${NC}   arXiv 文章标题翻译               [feature.ai_processor]"
    echo -e "  ${CYAN}embedding${NC}   向量嵌入计算                     [feature.embedding]"
    echo -e "  ${CYAN}event${NC}       事件聚类                         [feature.event_clustering]"
    echo -e "  ${CYAN}topic${NC}       主题发现                         [feature.topic_radar]"
    echo ""
    echo "子命令:"
    echo -e "  ${CYAN}reprocess${NC}   对已有文章重新运行 AI 分析流程"
    echo "              --debug, -d        打印完整输入输出（默认处理 3 篇）"
    echo "              --limit <n>        处理数量上限"
    echo "              --ids <id...>      指定文章 ID"
    echo "              --unprocessed      仅处理未处理的文章"
    echo "              --source-type <t>  按来源类型筛选"
    echo "              --concurrency, -c  并行数（默认: 1 串行，debug 模式强制串行）"
    echo ""
    echo -e "  ${CYAN}clean-thinking${NC} 清理文章中的 thinking 标签内容"
    echo "              --field, -f <field>  指定清理字段（默认: content）"
    echo "              --stats              仅统计不执行"
    echo "              --ids <id...>        指定文章 ID"
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
    echo -e "  ${GREEN}# 仅运行 AI 处理${NC}"
    echo "  ./scripts/ai-pipeline.sh ai"
    echo ""
    echo -e "  ${GREEN}# 仅翻译 arXiv 文章标题${NC}"
    echo "  ./scripts/ai-pipeline.sh translate"
    echo ""
    echo -e "  ${GREEN}# Debug 模式重处理（打印 AI prompt 和完整输出）${NC}"
    echo "  ./scripts/ai-pipeline.sh reprocess --debug"
    echo ""
    echo -e "  ${GREEN}# 重处理指定文章${NC}"
    echo "  ./scripts/ai-pipeline.sh reprocess --ids 12188 12189 --debug"
    echo ""
    echo -e "  ${GREEN}# 批量重处理 100 篇（并行 4 个 worker）${NC}"
    echo "  ./scripts/ai-pipeline.sh reprocess --limit 100 --concurrency 4"
    echo ""
    echo -e "  ${GREEN}# 清理文章中的 thinking 标签${NC}"
    echo "  ./scripts/ai-pipeline.sh clean-thinking"
    echo ""
    echo -e "  ${GREEN}# 清理指定字段和文章${NC}"
    echo "  ./scripts/ai-pipeline.sh clean-thinking --field content --field ai_summary --ids 17652"
    echo ""
    echo -e "  ${GREEN}# 每阶段最多处理 200 条文章${NC}"
    echo "  ./scripts/ai-pipeline.sh all --limit 200"
    echo ""
    echo -e "  ${GREEN}# 忽略功能开关，强制运行${NC}"
    echo "  ./scripts/ai-pipeline.sh all --force"
    echo ""
    echo "流水线依赖关系:"
    echo "  ai → translate → embedding → event → topic"
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
IS_REPROCESS=false
IS_CLEAN_THINKING=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            SHOW_HELP=true
            shift
            ;;
        reprocess)
            IS_REPROCESS=true
            shift
            ;;
        clean-thinking)
            IS_CLEAN_THINKING=true
            shift
            ;;
        --limit)
            OPTIONS+=("$1")
            if [ -n "$2" ]; then
                shift
                OPTIONS+=("$1")
            fi
            shift
            ;;
        --force|--verbose|-v|--json|--trigger)
            # 这些参数仅适用于流水线阶段，不适用于 reprocess
            OPTIONS+=("$1")
            shift
            ;;
        # reprocess 专用参数
        --debug|-d|--unprocessed)
            OPTIONS+=("$1")
            shift
            ;;
        # clean-thinking 专用参数
        --field|-f|--stats)
            OPTIONS+=("$1")
            if [ "$1" = "--field" ] || [ "$1" = "-f" ]; then
                if [ -n "$2" ]; then
                    shift
                    OPTIONS+=("$1")
                fi
            fi
            shift
            ;;
        --concurrency|-c)
            OPTIONS+=("$1")
            if [ -n "$2" ]; then
                shift
                OPTIONS+=("$1")
            fi
            shift
            ;;
        --ids)
            OPTIONS+=("$1")
            shift
            # 收集后续所有数字参数作为 ID
            while [[ $# -gt 0 ]] && [[ "$1" =~ ^[0-9]+$ ]]; do
                OPTIONS+=("$1")
                shift
            done
            ;;
        --source-type)
            OPTIONS+=("$1")
            if [ -n "$2" ]; then
                shift
                OPTIONS+=("$1")
            fi
            shift
            ;;
        all|ai|translate|embedding|event|topic|action|report)
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
if [ "$SHOW_HELP" = true ] || { [ "$IS_REPROCESS" = false ] && [ "$IS_CLEAN_THINKING" = false ] && [ ${#STAGES[@]} -eq 0 ]; }; then
    show_help
    exit 0
fi

# 检查环境
check_env
check_python

# ---- clean-thinking 子命令 ----
if [ "$IS_CLEAN_THINKING" = true ]; then
    if [ ! -f "$CLEAN_THINKING_SCRIPT" ]; then
        echo -e "${RED}错误: 清理脚本不存在: ${CLEAN_THINKING_SCRIPT}${NC}"
        exit 1
    fi

    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}ResearchPulse v2 清理 Thinking 标签${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""

    cd "$PROJECT_DIR"
    python3 "${CLEAN_THINKING_SCRIPT}" "${OPTIONS[@]}"

    EXIT_CODE=$?

    echo ""
    echo -e "${BLUE}--------------------------------------------${NC}"
    if [ $EXIT_CODE -eq 0 ]; then
        echo -e "${GREEN}清理完毕${NC}"
    else
        echo -e "${RED}清理失败 (退出码: $EXIT_CODE)${NC}"
    fi

    exit $EXIT_CODE
fi

# ---- reprocess 子命令 ----
if [ "$IS_REPROCESS" = true ]; then
    if [ ! -f "$REPROCESS_SCRIPT" ]; then
        echo -e "${RED}错误: 重处理脚本不存在: ${REPROCESS_SCRIPT}${NC}"
        exit 1
    fi

    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}ResearchPulse v2 文章重处理${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""

    cd "$PROJECT_DIR"
    python3 "${REPROCESS_SCRIPT}" "${OPTIONS[@]}"

    EXIT_CODE=$?

    echo ""
    echo -e "${BLUE}--------------------------------------------${NC}"
    if [ $EXIT_CODE -eq 0 ]; then
        echo -e "${GREEN}重处理完毕${NC}"
    else
        echo -e "${RED}重处理失败 (退出码: $EXIT_CODE)${NC}"
    fi

    exit $EXIT_CODE
fi

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
