#!/bin/bash
# =============================================================================
# ResearchPulse v2 统一控制脚本
# =============================================================================
# 用法: ./scripts/control.sh <command> [options]
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_DIR/logs/app.log"

show_help() {
    echo -e "${BLUE}ResearchPulse v2 控制脚本${NC}"
    echo ""
    echo "用法: ./scripts/control.sh <command> [options]"
    echo ""
    echo "命令:"
    echo -e "  ${CYAN}deploy${NC}    部署应用"
    echo "              --skip-deps    跳过依赖"
    echo "              --skip-db      跳过数据库"
    echo ""
    echo -e "  ${CYAN}init${NC}      初始化数据库"
    echo ""
    echo -e "  ${CYAN}start${NC}     启动服务"
    echo "              --port PORT    端口"
    echo "              --daemon, -d   后台运行"
    echo ""
    echo -e "  ${CYAN}stop${NC}      停止服务"
    echo "              --force, -f    强制停止"
    echo ""
    echo -e "  ${CYAN}restart${NC}   重启服务"
    echo ""
    echo -e "  ${CYAN}status${NC}    查看状态"
    echo "              --verbose, -v  详细信息"
    echo ""
    echo -e "  ${CYAN}logs${NC}      查看日志"
    echo "              --follow, -f   实时跟踪"
    echo ""
    echo -e "  ${CYAN}test${NC}      运行测试"
    echo "              unit           单元测试 (默认)"
    echo "              coverage       覆盖率报告"
    echo "              integration    集成测试"
    echo "              --html         HTML 报告"
    echo ""
    echo "示例:"
    echo "  ./scripts/control.sh deploy"
    echo "  ./scripts/control.sh start -d"
    echo "  ./scripts/control.sh status -v"
    echo "  ./scripts/control.sh test coverage --html"
    echo ""
}

show_logs() {
    local FOLLOW=false
    [ "$1" = "-f" ] || [ "$1" = "--follow" ] && FOLLOW=true
    
    if [ ! -f "$LOG_FILE" ]; then
        echo -e "${YELLOW}日志文件不存在${NC}"
        exit 1
    fi
    
    [ "$FOLLOW" = true ] && tail -f "$LOG_FILE" || tail -50 "$LOG_FILE"
}

COMMAND=${1:-help}
shift || true

case "$COMMAND" in
    deploy|init)   "$SCRIPT_DIR/${COMMAND}.sh" "$@" ;;
    start|stop|restart|status) "$SCRIPT_DIR/service.sh" "$COMMAND" "$@" ;;
    test)          "$SCRIPT_DIR/test.sh" "$@" ;;
    logs)          show_logs "$@" ;;
    help|--help|-h) show_help ;;
    *) echo -e "${RED}未知命令: $COMMAND${NC}"; show_help; exit 1 ;;
esac
