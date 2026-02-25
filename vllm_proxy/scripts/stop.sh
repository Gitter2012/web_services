#!/bin/bash
#==============================================================================
# vLLM Proxy 服务停止脚本
#==============================================================================

set -e

# 脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
RUN_DIR="${SCRIPT_DIR}/run"
PID_FILE="${RUN_DIR}/vllm_proxy.pid"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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
Usage: $0 [OPTIONS]

停止 vLLM Proxy 服务

Options:
    -f, --force             强制停止（发送 SIGKILL）
    -t, --timeout SECONDS   优雅停止超时时间 (默认: 30)
    -h, --help              显示帮助信息

Examples:
    $0                      # 优雅停止服务
    $0 -f                   # 强制停止
    $0 -t 60                # 60秒超时

EOF
}

parse_args() {
    FORCE=false
    TIMEOUT=30

    while [[ $# -gt 0 ]]; do
        case $1 in
            -f|--force)
                FORCE=true
                shift
                ;;
            -t|--timeout)
                TIMEOUT="$2"
                shift 2
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

stop_service() {
    if [[ ! -f "$PID_FILE" ]]; then
        log_warn "PID 文件不存在，服务可能未运行"

        # 尝试查找进程
        local pids=$(pgrep -f "python3 proxy/main.py" || true)
        if [[ -n "$pids" ]]; then
            log_info "发现相关进程:"
            ps -fp $pids
            echo ""
            read -p "是否停止这些进程? [y/N] " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo "$pids" | xargs kill -TERM 2>/dev/null || true
                log_info "已发送停止信号"
            fi
        fi
        return
    fi

    local pid=$(cat "$PID_FILE")

    if ! ps -p "$pid" > /dev/null 2>&1; then
        log_warn "进程 $pid 不存在"
        rm -f "$PID_FILE"
        return
    fi

    log_info "正在停止服务 (PID: $pid)..."

    if [[ "$FORCE" == true ]]; then
        log_warn "强制停止服务..."
        kill -9 "$pid" 2>/dev/null || true
    else
        # 优雅停止
        log_info "发送 SIGTERM 信号..."
        kill -TERM "$pid" 2>/dev/null || true

        # 等待进程结束
        local count=0
        while ps -p "$pid" > /dev/null 2>&1; do
            sleep 1
            count=$((count + 1))

            if [[ $count -ge $TIMEOUT ]]; then
                log_warn "优雅停止超时，强制终止..."
                kill -9 "$pid" 2>/dev/null || true
                break
            fi

            if [[ $((count % 5)) -eq 0 ]]; then
                log_info "等待服务停止... ($count/$TIMEOUT)"
            fi
        done
    fi

    # 清理
    rm -f "$PID_FILE"

    # 检查是否还有残留进程
    local remaining=$(pgrep -f "vllm.entrypoints.openai" || true)
    if [[ -n "$remaining" ]]; then
        log_warn "发现残留的 vLLM 进程:"
        ps -fp $remaining
        echo ""
        read -p "是否清理这些进程? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "$remaining" | xargs kill -TERM 2>/dev/null || true
            sleep 2
            remaining=$(pgrep -f "vllm.entrypoints.openai" || true)
            if [[ -n "$remaining" ]]; then
                echo "$remaining" | xargs kill -9 2>/dev/null || true
            fi
            log_info "已清理残留进程"
        fi
    fi

    log_info "服务已停止"
}

#==============================================================================
# 主程序
#==============================================================================

main() {
    parse_args "$@"
    stop_service
}

main "$@"
