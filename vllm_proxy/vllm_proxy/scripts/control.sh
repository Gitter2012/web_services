#!/bin/bash
#==============================================================================
# vLLM Proxy 服务控制脚本 - 统一入口
#==============================================================================
#
# 本脚本是所有服务管理操作的统一入口，提供 start/stop/restart/status 等命令
# 启动时会将进程ID写入 scripts/run/ 目录，便于管理和重启
#
# Usage:
#   ./control.sh <command> [options]
#
# Commands:
#   start     启动服务
#   stop      停止服务
#   restart   重启服务
#   status    查看状态
#   install   安装依赖
#   help      显示帮助信息
#
#==============================================================================

set -e

# 脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# PID 文件目录 (用于存储进程ID)
RUN_DIR="${SCRIPT_DIR}/run"
PID_FILE="${RUN_DIR}/vllm_proxy.pid"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

#==============================================================================
# 函数定义
#==============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_help() {
    cat << EOF
${CYAN}vLLM Proxy 服务控制脚本${NC}

Usage:
    $0 <command> [options]

Commands:
    start       启动服务
                Options: -c, --config FILE   指定配置文件
                         -d, --daemon        后台模式运行

    stop        停止服务
                Options: -f, --force         强制停止
                         -t, --timeout N     超时时间(秒)

    restart     重启服务
                Options: -c, --config FILE   指定配置文件
                         -d, --daemon        后台模式运行
                         -f, --force         强制重启

    status      查看服务状态
                Options: -v, --verbose       详细信息
                         -j, --json          JSON 格式输出

    install     安装依赖
                Options: --dev              安装开发依赖

    help        显示帮助信息

Examples:
    $0 start                    # 前台启动
    $0 start -d                 # 后台启动
    $0 stop                     # 停止服务
    $0 restart -d               # 后台重启
    $0 status -v                # 详细状态

PID 文件位置: ${RUN_DIR}/

EOF
}

# 启动服务
do_start() {
    log_info "启动 vLLM Proxy 服务..."
    "${SCRIPT_DIR}/start.sh" "$@"
}

# 停止服务
do_stop() {
    log_info "停止 vLLM Proxy 服务..."
    "${SCRIPT_DIR}/stop.sh" "$@"
}

# 重启服务
do_restart() {
    log_info "重启 vLLM Proxy 服务..."
    "${SCRIPT_DIR}/restart.sh" "$@"
}

# 查看状态
do_status() {
    "${SCRIPT_DIR}/status.sh" "$@"
}

# 安装依赖
do_install() {
    "${SCRIPT_DIR}/install.sh" "$@"
}

#==============================================================================
# 主程序
#==============================================================================

main() {
    if [[ $# -eq 0 ]]; then
        show_help
        exit 0
    fi

    local command=$1
    shift

    case $command in
        start)
            do_start "$@"
            ;;
        stop)
            do_stop "$@"
            ;;
        restart)
            do_restart "$@"
            ;;
        status)
            do_status "$@"
            ;;
        install)
            do_install "$@"
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "未知命令: $command"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

main "$@"
