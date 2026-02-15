#!/bin/bash
# =============================================================================
# ResearchPulse v2 服务管理脚本
# =============================================================================
# 用法: ./scripts/service.sh <action> [options]
#
# 动作: start | stop | restart | status
# 选项: --port --host --daemon --force --verbose
# =============================================================================

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_FILE="$PROJECT_DIR/run/app.pid"
LOG_FILE="$PROJECT_DIR/logs/app.log"

HOST="0.0.0.0"
PORT=8000
DAEMON=false
FORCE=false
VERBOSE=false
[ -x "/root/myenv/bin/python" ] && PYTHON_BIN="/root/myenv/bin/python" || PYTHON_BIN="python"

# =============================================================================
# 公共函数
# =============================================================================

load_env() {
    cd "$PROJECT_DIR"
    [ -f ".env" ] && source .env
}

get_pid() {
    if [ -f "$PID_FILE" ]; then
        local PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "$PID"
            return 0
        fi
        rm -f "$PID_FILE"
    fi
    echo ""
    return 1
}

is_running() {
    [ -n "$(get_pid)" ]
}

# =============================================================================
# 动作函数
# =============================================================================

do_start() {
    echo -e "${BLUE}=============================================================${NC}"
    echo -e "${BLUE}启动服务${NC}"
    echo -e "${BLUE}=============================================================${NC}"
    echo ""

    if is_running; then
        echo -e "${YELLOW}服务已在运行中 (PID: $(get_pid))${NC}"
        exit 0
    fi

    if [ ! -f ".env" ]; then
        echo -e "${RED}错误: .env 文件不存在${NC}"
        exit 1
    fi

    # 创建必要的目录
    mkdir -p "$PROJECT_DIR/logs"
    mkdir -p "$PROJECT_DIR/run"

    echo "主机: $HOST"
    echo "端口: $PORT"

    # 导出环境变量供 main.py 使用
    export APP_HOST="$HOST"
    export APP_PORT="$PORT"

    if [ "$DAEMON" = true ]; then
        nohup $PYTHON_BIN main.py --host "$HOST" --port "$PORT" > "$LOG_FILE" 2>&1 &
        PID=$!
        echo $PID > "$PID_FILE"
        sleep 2

        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${GREEN}服务启动成功 (PID: $PID)${NC}"
            echo ""
            echo "访问地址:"
            echo "  主页:     http://localhost:$PORT/researchpulse"
            echo "  API 文档: http://localhost:$PORT/docs"
            echo "  健康检查: http://localhost:$PORT/health"
            echo ""
            echo "日志: $LOG_FILE"
        else
            echo -e "${RED}启动失败，查看日志: $LOG_FILE${NC}"
            cat "$LOG_FILE" 2>/dev/null | tail -20
            exit 1
        fi
    else
        echo ""
        echo -e "${GREEN}服务启动中... (Ctrl+C 停止)${NC}"
        echo $$ > "$PID_FILE"
        exec $PYTHON_BIN main.py --host "$HOST" --port "$PORT"
    fi
}

do_stop() {
    echo -e "${BLUE}=============================================================${NC}"
    echo -e "${BLUE}停止服务${NC}"
    echo -e "${BLUE}=============================================================${NC}"
    echo ""
    
    PID=$(get_pid)
    
    if [ -z "$PID" ]; then
        echo -e "${YELLOW}服务未运行${NC}"
        [ "$FORCE" = true ] && { pkill -f "python.*main.py" 2>/dev/null || true; echo -e "${GREEN}已清理残留进程${NC}"; }
        exit 0
    fi
    
    echo "停止服务 (PID: $PID)..."
    
    if [ "$FORCE" = true ]; then
        kill -9 "$PID" 2>/dev/null || true
        echo -e "${GREEN}服务已强制停止${NC}"
    else
        kill "$PID" 2>/dev/null || true
        for i in {1..10}; do
            ! ps -p "$PID" > /dev/null 2>&1 && break
            sleep 1
        done
        if ps -p "$PID" > /dev/null 2>&1; then
            kill -9 "$PID" 2>/dev/null || true
            echo -e "${GREEN}服务已强制停止${NC}"
        else
            echo -e "${GREEN}服务已停止${NC}"
        fi
    fi
    
    rm -f "$PID_FILE"
}

do_restart() {
    echo -e "${BLUE}=============================================================${NC}"
    echo -e "${BLUE}重启服务${NC}"
    echo -e "${BLUE}=============================================================${NC}"
    echo ""
    
    echo -e "${YELLOW}[1/2] 停止服务...${NC}"
    do_stop 2>/dev/null || true
    sleep 2
    
    echo ""
    echo -e "${YELLOW}[2/2] 启动服务...${NC}"
    DAEMON=true do_start
}

do_status() {
    echo -e "${BLUE}=============================================================${NC}"
    echo -e "${BLUE}服务状态${NC}"
    echo -e "${BLUE}=============================================================${NC}"
    echo ""
    
    echo -e "${CYAN}[服务]${NC}"
    PID=$(get_pid)
    if [ -n "$PID" ]; then
        echo -e "  状态:     ${GREEN}运行中${NC}"
        echo "  PID:      $PID"
        [ "$VERBOSE" = true ] && ps -p "$PID" -o pid,%cpu,%mem,etime --no-headers 2>/dev/null | \
            awk '{printf "  CPU:      %s%%\n  内存:     %s%%\n  运行:     %s\n", $2, $3, $4}'
    else
        echo -e "  状态:     ${YELLOW}未运行${NC}"
    fi
    echo ""
    
    echo -e "${CYAN}[数据库]${NC}"
    if [ -n "$DB_HOST" ]; then
        echo "  主机:     $DB_HOST:${DB_PORT:-3306}"
        echo "  数据库:   $DB_NAME"
        if command -v mysql &> /dev/null && [ -n "$DB_PASSWORD" ]; then
            if mysql -h "$DB_HOST" -P "${DB_PORT:-3306}" -u "$DB_USER" -p"$DB_PASSWORD" -e "SELECT 1" > /dev/null 2>&1; then
                echo -e "  连接:     ${GREEN}正常${NC}"
                [ "$VERBOSE" = true ] && echo "  文章数:   $(mysql -h "$DB_HOST" -P "${DB_PORT:-3306}" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" -N -e "SELECT COUNT(*) FROM articles" 2>/dev/null || echo '?')"
            else
                echo -e "  连接:     ${RED}失败${NC}"
            fi
        fi
    fi
    echo ""
    
    echo -e "${CYAN}[HTTP]${NC}"
    if [ -n "$PID" ] && command -v curl &> /dev/null; then
        CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${PORT}/health" 2>/dev/null || echo "000")
        [ "$CODE" = "200" ] && echo -e "  健康检查: ${GREEN}正常${NC}" || echo -e "  健康检查: ${RED}异常${NC}"
        echo "  地址:     http://localhost:$PORT/researchpulse"
    else
        echo "  服务未运行"
    fi
    echo ""
    
    [ "$VERBOSE" = true ] && { echo -e "${CYAN}[磁盘]${NC}"; df -h "$PROJECT_DIR" | tail -1 | awk '{printf "  已用: %s  可用: %s  使用率: %s\n", $3, $4, $5}'; echo ""; }
    
    echo -e "${BLUE}=============================================================${NC}"
}

show_help() {
    echo -e "${BLUE}ResearchPulse v2 服务管理${NC}"
    echo ""
    echo "用法: ./scripts/service.sh <action> [options]"
    echo ""
    echo "动作:"
    echo "  start     启动服务"
    echo "  stop      停止服务"
    echo "  restart   重启服务"
    echo "  status    查看状态"
    echo ""
    echo "选项:"
    echo "  --port PORT      端口 (默认: 8000)"
    echo "  --host HOST      主机 (默认: 0.0.0.0)"
    echo "  --daemon, -d     后台运行"
    echo "  --force, -f      强制操作"
    echo "  --verbose, -v    详细输出"
    echo ""
    echo "示例:"
    echo "  ./scripts/service.sh start --daemon"
    echo "  ./scripts/service.sh start --port 8080 -d"
    echo "  ./scripts/service.sh stop --force"
    echo "  ./scripts/service.sh status -v"
}

# =============================================================================
# 主逻辑
# =============================================================================

ACTION=${1:-help}
shift || true

while [[ $# -gt 0 ]]; do
    case $1 in
        --port) PORT="$2"; shift 2 ;;
        --host) HOST="$2"; shift 2 ;;
        --daemon|-d) DAEMON=true; shift ;;
        --force|-f) FORCE=true; shift ;;
        --verbose|-v) VERBOSE=true; shift ;;
        *) shift ;;
    esac
done

load_env

case "$ACTION" in
    start)   do_start ;;
    stop)    do_stop ;;
    restart) do_restart ;;
    status)  do_status ;;
    help|--help|-h) show_help ;;
    *) echo -e "${RED}未知动作: $ACTION${NC}"; show_help; exit 1 ;;
esac
