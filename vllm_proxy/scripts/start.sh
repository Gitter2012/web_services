#!/bin/bash
#==============================================================================
# vLLM Proxy 服务启动脚本
#==============================================================================

set -e

# 脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 默认配置
CONFIG_FILE="${PROJECT_DIR}/configs/config.yaml"
LOG_DIR="${PROJECT_DIR}/logs"
RUN_DIR="${SCRIPT_DIR}/run"
PID_FILE="${RUN_DIR}/vllm_proxy.pid"
DAEMON_MODE=false

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

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

启动 vLLM Proxy 服务

Options:
    -c, --config FILE       指定配置文件 (默认: configs/config.yaml)
    -d, --daemon            后台模式运行
    -h, --help              显示帮助信息

Environment Variables:
    PROXY_PORT              代理服务端口 (默认: 8080)
    IDLE_TIMEOUT            空闲超时时间秒数 (默认: 300)
    GPU_ID                  使用的 GPU ID (默认: 0)
    LOG_LEVEL               日志级别 (默认: INFO)

Examples:
    $0                      # 使用默认配置启动
    $0 -c /path/to/config.yaml
    $0 -d                   # 后台模式启动
    $0 -c config.yaml -d

EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -c|--config)
                CONFIG_FILE="$2"
                shift 2
                ;;
            -d|--daemon)
                DAEMON_MODE=true
                shift
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

check_environment() {
    log_info "检查运行环境..."

    # 检查 Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 未安装"
        exit 1
    fi

    # 检查 CUDA
    if ! command -v nvidia-smi &> /dev/null; then
        log_warn "nvidia-smi 未找到，GPU 监控可能不可用"
    else
        log_info "CUDA 版本: $(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)"
    fi

    # 检查配置文件
    if [[ ! -f "$CONFIG_FILE" ]]; then
        log_warn "配置文件不存在: $CONFIG_FILE"
        log_info "将使用默认配置"
    fi

    # 创建必要目录
    mkdir -p "$LOG_DIR"
    mkdir -p "$RUN_DIR"

    # 检查端口占用（从配置文件读取端口）
    # 如果配置文件存在，尝试解析端口
    local port=8080
    if [[ -f "$CONFIG_FILE" ]]; then
        # 使用 Python 解析 YAML 获取端口
        port=$(python3 -c "
import yaml
with open('$CONFIG_FILE', 'r') as f:
    data = yaml.safe_load(f)
print(data.get('proxy', {}).get('port', 8080))
" 2>/dev/null || echo "8080")
    fi
    # 也支持环境变量覆盖
    port=${PROXY_PORT:-$port}
    if lsof -Pi :"$port" -sTCP:LISTEN -t >/dev/null 2>&1; then
        log_error "端口 $port 已被占用"
        exit 1
    fi
}

check_already_running() {
    if [[ -f "$PID_FILE" ]]; then
        local pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            log_error "服务已在运行 (PID: $pid)"
            log_info "使用 ./status.sh 查看状态，或 ./stop.sh 停止服务"
            exit 1
        else
            log_warn "发现残留 PID 文件，清理中..."
            rm -f "$PID_FILE"
        fi
    fi
}

start_service() {
    log_info "启动 vLLM Proxy 服务..."
    log_info "配置文件: $CONFIG_FILE"
    log_info "日志目录: $LOG_DIR"

    cd "$PROJECT_DIR"

    # 设置 Python 路径
    export PYTHONPATH="${PROJECT_DIR}:${PYTHONPATH}"

    # 构建启动命令
    local cmd="python3 proxy/main.py"
    if [[ -f "$CONFIG_FILE" ]]; then
        cmd="$cmd $CONFIG_FILE"
    fi

    if [[ "$DAEMON_MODE" == true ]]; then
        # 后台模式
        log_info "以后台模式启动..."
        nohup $cmd > "${LOG_DIR}/vllm_proxy.out" 2>&1 &
        local pid=$!
        echo $pid > "$PID_FILE"

        # 等待服务启动
        sleep 3
        if ps -p "$pid" > /dev/null 2>&1; then
            log_info "服务已启动 (PID: $pid)"
            log_info "日志文件: ${LOG_DIR}/vllm_proxy.out"
            log_info "使用 ./status.sh 查看状态"
        else
            log_error "服务启动失败，请检查日志"
            rm -f "$PID_FILE"
            exit 1
        fi
    else
        # 前台模式
        log_info "以前台模式启动，按 Ctrl+C 停止..."
        echo "----------------------------------------"
        $cmd
    fi
}

#==============================================================================
# 主程序
#==============================================================================

main() {
    parse_args "$@"
    check_already_running
    check_environment
    start_service
}

main "$@"
