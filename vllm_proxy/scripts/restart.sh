#!/bin/bash
#==============================================================================
# vLLM Proxy 服务重启脚本
#==============================================================================

set -e

# 脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

重启 vLLM Proxy 服务

Options:
    -c, --config FILE       指定配置文件
    -d, --daemon            后台模式运行
    -t, --timeout SECONDS   停止超时时间 (默认: 30)
    -f, --force             强制重启
    -h, --help              显示帮助信息

Examples:
    $0                      # 使用默认配置重启
    $0 -c config.yaml -d    # 使用指定配置，后台模式
    $0 -f                   # 强制重启

EOF
}

# 解析参数
CONFIG_FILE="${PROJECT_DIR}/configs/config.yaml"
DAEMON_MODE=false
TIMEOUT=30
FORCE=false

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
        -t|--timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

log_info "正在重启 vLLM Proxy 服务..."

# 构建停止参数
STOP_ARGS=""
if [[ "$FORCE" == true ]]; then
    STOP_ARGS="$STOP_ARGS --force"
fi
STOP_ARGS="$STOP_ARGS --timeout $TIMEOUT"

# 构建启动参数
START_ARGS=""
if [[ -f "$CONFIG_FILE" ]]; then
    START_ARGS="$START_ARGS --config $CONFIG_FILE"
fi
if [[ "$DAEMON_MODE" == true ]]; then
    START_ARGS="$START_ARGS --daemon"
fi

# 停止服务
log_info "步骤 1/2: 停止服务..."
"${SCRIPT_DIR}/stop.sh" $STOP_ARGS

# 等待确保端口释放
sleep 2

# 启动服务
log_info "步骤 2/2: 启动服务..."
"${SCRIPT_DIR}/start.sh" $START_ARGS

log_info "重启完成"
