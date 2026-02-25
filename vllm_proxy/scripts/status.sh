#!/bin/bash
#==============================================================================
# vLLM Proxy 服务状态查询脚本
#==============================================================================

set -e

# 脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
RUN_DIR="${SCRIPT_DIR}/run"
PID_FILE="${RUN_DIR}/vllm_proxy.pid"
CONFIG_FILE="${PROJECT_DIR}/configs/config.yaml"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

log_title() {
    echo -e "${CYAN}$1${NC}"
}

log_label() {
    printf "  %-20s %s\n" "$1:" "$2"
}

show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

查询 vLLM Proxy 服务状态

Options:
    -v, --verbose           显示详细信息
    -j, --json              以 JSON 格式输出
    -h, --help              显示帮助信息

Examples:
    $0                      # 显示基本状态
    $0 -v                   # 显示详细信息
    $0 -j                   # JSON 格式输出

EOF
}

parse_args() {
    VERBOSE=false
    JSON_OUTPUT=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -j|--json)
                JSON_OUTPUT=true
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

check_service_status() {
    local status="stopped"
    local pid=""
    local uptime=""

    if [[ -f "$PID_FILE" ]]; then
        pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            status="running"
            local start_time=$(ps -o lstart= -p "$pid" 2>/dev/null || echo "Unknown")
            uptime=$(ps -o etime= -p "$pid" 2>/dev/null || echo "Unknown")
        else
            status="dead"
            pid=""
        fi
    fi

    echo "$status|$pid|$uptime"
}

get_gpu_info() {
    if ! command -v nvidia-smi &> /dev/null; then
        echo "N/A|N/A|N/A|N/A"
        return
    fi

    local gpu_info=$(nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu,temperature.gpu --format=csv,noheader,nounits 2>/dev/null | head -1)
    if [[ -z "$gpu_info" ]]; then
        echo "N/A|N/A|N/A|N/A"
        return
    fi

    # 解析 CSV
    local index=$(echo "$gpu_info" | cut -d',' -f1 | tr -d ' ')
    local name=$(echo "$gpu_info" | cut -d',' -f2 | sed 's/^ *//')
    local mem_used=$(echo "$gpu_info" | cut -d',' -f3 | tr -d ' ')
    local mem_total=$(echo "$gpu_info" | cut -d',' -f4 | tr -d ' ')
    local util=$(echo "$gpu_info" | cut -d',' -f5 | tr -d ' ')
    local temp=$(echo "$gpu_info" | cut -d',' -f6 | tr -d ' ')

    echo "$name|${mem_used}MiB/${mem_total}MiB|${util}%|${temp}°C"
}

check_health() {
    local port=${PROXY_PORT:-8080}
    local health_url="http://localhost:${port}/health"

    if command -v curl &> /dev/null; then
        curl -s "$health_url" 2>/dev/null || echo "{}"
    elif command -v wget &> /dev/null; then
        wget -qO- "$health_url" 2>/dev/null || echo "{}"
    else
        echo "{}"
    fi
}

show_basic_status() {
    local status_info=$(check_service_status)
    local status=$(echo "$status_info" | cut -d'|' -f1)
    local pid=$(echo "$status_info" | cut -d'|' -f2)
    local uptime=$(echo "$status_info" | cut -d'|' -f3)

    local gpu_info=$(get_gpu_info)
    local gpu_name=$(echo "$gpu_info" | cut -d'|' -f1)
    local gpu_mem=$(echo "$gpu_info" | cut -d'|' -f2)
    local gpu_util=$(echo "$gpu_info" | cut -d'|' -f3)
    local gpu_temp=$(echo "$gpu_info" | cut -d'|' -f4)

    echo ""
    log_title "╔════════════════════════════════════════════════════════════╗"
    log_title "║              vLLM Proxy Service Status                     ║"
    log_title "╚════════════════════════════════════════════════════════════╝"
    echo ""

    # 服务状态
    if [[ "$status" == "running" ]]; then
        echo -e "  服务状态: ${GREEN}运行中${NC}"
        log_label "PID" "$pid"
        log_label "运行时间" "$uptime"
    elif [[ "$status" == "dead" ]]; then
        echo -e "  服务状态: ${RED}已停止 (PID 文件残留)${NC}"
    else
        echo -e "  服务状态: ${YELLOW}已停止${NC}"
    fi

    echo ""
    echo -e "${BLUE}GPU 信息:${NC}"
    log_label "设备" "$gpu_name"
    log_label "显存使用" "$gpu_mem"
    log_label "利用率" "$gpu_util"
    log_label "温度" "$gpu_temp"

    # 已加载模型
    if [[ "$status" == "running" ]]; then
        echo ""
        echo -e "${BLUE}已加载模型:${NC}"

        local health_json=$(check_health)
        local loaded_models=$(echo "$health_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('model_status',{})))" 2>/dev/null || echo "0")

        if [[ "$loaded_models" -gt 0 ]]; then
            echo "$health_json" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for mid, status in data.get('model_status', {}).items():
    print(f'  • {mid}: {status[\"status\"]} (port: {status[\"port\"]}, requests: {status[\"request_count\"]})')
" 2>/dev/null || echo "  (无法解析)"
        else
            echo "  (无)"
        fi
    fi

    echo ""
}

show_verbose_status() {
    show_basic_status

    local status_info=$(check_service_status)
    local status=$(echo "$status_info" | cut -d'|' -f1)

    if [[ "$status" != "running" ]]; then
        return
    fi

    echo -e "${BLUE}详细指标:${NC}"

    local health_json=$(check_health)

    # GPU 详细指标
    echo "$health_json" | python3 -c "
import sys, json
data = json.load(sys.stdin)
gpu = data.get('gpu', {})
mem = gpu.get('memory', {})

print(f'  GPU 名称: {gpu.get(\"name\", \"N/A\")}')
print(f'  GPU 温度: {gpu.get(\"temperature\", \"N/A\")}°C')
print(f'  GPU 利用率: {gpu.get(\"utilization_percent\", \"N/A\")}%')
print(f'  功耗: {gpu.get(\"power_draw_w\", \"N/A\")}W / {gpu.get(\"power_limit_w\", \"N/A\")}W')
print(f'  显存总量: {mem.get(\"total_mb\", \"N/A\")} MB')
print(f'  显存已用: {mem.get(\"used_mb\", \"N/A\")} MB')
print(f'  显存可用: {mem.get(\"available_mb\", \"N/A\")} MB')
" 2>/dev/null || echo "  (无法获取详细指标)"

    # 进程信息
    echo ""
    echo -e "${BLUE}进程信息:${NC}"
    ps aux | grep -E "(vllm|python3 -m src)" | grep -v grep | awk '{printf "  PID: %s, CPU: %s%%, MEM: %s%%, CMD: %s\n", $2, $3, $4, $11}' || echo "  (无相关进程)"

    # 端口监听
    echo ""
    echo -e "${BLUE}端口监听:${NC}"
    local port=${PROXY_PORT:-8080}
    ss -tlnp 2>/dev/null | grep -E ":$port" | awk '{print "  " $0}' || \
    netstat -tlnp 2>/dev/null | grep -E ":$port" | awk '{print "  " $0}' || \
    echo "  (无法获取端口信息)"

    # 日志尾部
    echo ""
    echo -e "${BLUE}最近日志 (最后 10 行):${NC}"
    local log_file="${PROJECT_DIR}/logs/vllm_proxy.log"
    if [[ -f "$log_file" ]]; then
        tail -n 10 "$log_file" | sed 's/^/  /'
    else
        echo "  日志文件不存在"
    fi

    echo ""
}

show_json_status() {
    local status_info=$(check_service_status)
    local status=$(echo "$status_info" | cut -d'|' -f1)
    local pid=$(echo "$status_info" | cut -d'|' -f2)
    local uptime=$(echo "$status_info" | cut -d'|' -f3)

    local gpu_info=$(get_gpu_info)
    local health_json=$(check_health)

    python3 -c "
import json

result = {
    'service': {
        'status': '$status',
        'pid': '$pid' if '$pid' else None,
        'uptime': '$uptime' if '$uptime' else None
    },
    'gpu': {
        'name': '$(echo "$gpu_info" | cut -d'|' -f1)',
        'memory': '$(echo "$gpu_info" | cut -d'|' -f2)',
        'utilization': '$(echo "$gpu_info" | cut -d'|' -f3)',
        'temperature': '$(echo "$gpu_info" | cut -d'|' -f4)'
    }
}

# 合并健康检查数据
try:
    health = json.loads('''$health_json''')
    result['health'] = health
except:
    pass

print(json.dumps(result, indent=2, ensure_ascii=False))
"
}

#==============================================================================
# 主程序
#==============================================================================

main() {
    parse_args "$@"

    if [[ "$JSON_OUTPUT" == true ]]; then
        show_json_status
    elif [[ "$VERBOSE" == true ]]; then
        show_verbose_status
    else
        show_basic_status
    fi
}

main "$@"
