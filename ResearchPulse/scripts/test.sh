#!/bin/bash
# =============================================================================
# ResearchPulse v2 测试脚本
# =============================================================================
# 用法: ./scripts/test.sh [command] [options]
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
[ -x "/root/myenv/bin/python" ] && PYTHON_BIN="/root/myenv/bin/python" || PYTHON_BIN="python"

cd "$PROJECT_DIR"

show_help() {
    echo -e "${BLUE}ResearchPulse v2 测试脚本${NC}"
    echo ""
    echo "用法: ./scripts/test.sh [command] [options]"
    echo ""
    echo "命令:"
    echo -e "  ${CYAN}unit${NC}       运行单元测试 (默认)"
    echo -e "  ${CYAN}all${NC}        运行所有测试"
    echo -e "  ${CYAN}coverage${NC}   运行测试并生成覆盖率报告"
    echo -e "  ${CYAN}integration${NC} 运行集成测试 (需要数据库)"
    echo -e "  ${CYAN}e2e${NC}        运行端到端测试 (需要服务运行)"
    echo -e "  ${CYAN}service${NC}    测试服务启动/停止功能"
    echo -e "  ${CYAN}fast${NC}       快速测试 (仅 schema 验证)"
    echo -e "  ${CYAN}watch${NC}      监听模式运行测试"
    echo ""
    echo "选项:"
    echo "  -v, --verbose    详细输出"
    echo "  -k KEYWORD       按关键字过滤测试"
    echo "  --html           生成 HTML 覆盖率报告"
    echo "  --url URL        E2E 测试基础 URL (默认: http://localhost:8000)"
    echo "  --help, -h       显示帮助"
    echo ""
    echo "示例:"
    echo "  ./scripts/test.sh                    # 运行单元测试"
    echo "  ./scripts/test.sh coverage --html    # 生成 HTML 覆盖率报告"
    echo "  ./scripts/test.sh -k auth            # 运行包含 'auth' 的测试"
    echo "  ./scripts/test.sh e2e --url http://localhost:8080"
    echo "  ./scripts/test.sh service            # 测试服务管理功能"
    echo ""
}

run_unit_tests() {
    echo -e "${CYAN}运行单元测试...${NC}"
    $PYTHON_BIN -m pytest tests/ -v --ignore=tests/apps/auth/test_service.py "$@"
}

run_all_tests() {
    echo -e "${CYAN}运行所有测试...${NC}"
    $PYTHON_BIN -m pytest tests/ -v "$@"
}

run_coverage() {
    local HTML_REPORT=false
    for arg in "$@"; do
        [ "$arg" = "--html" ] && HTML_REPORT=true
    done

    echo -e "${CYAN}运行测试并生成覆盖率报告...${NC}"
    if [ "$HTML_REPORT" = true ]; then
        $PYTHON_BIN -m pytest tests/ -v --ignore=tests/apps/auth/test_service.py \
            --cov=. --cov-report=html --cov-report=term "$@"
        echo -e "${GREEN}HTML 覆盖率报告已生成: htmlcov/index.html${NC}"
    else
        $PYTHON_BIN -m pytest tests/ -v --ignore=tests/apps/auth/test_service.py \
            --cov=. --cov-report=term "$@"
    fi
}

run_integration_tests() {
    echo -e "${YELLOW}运行集成测试 (需要数据库连接)...${NC}"
    $PYTHON_BIN -m pytest tests/ -v -m integration "$@"
}

run_fast_tests() {
    echo -e "${CYAN}运行快速测试 (仅 schema 验证)...${NC}"
    $PYTHON_BIN -m pytest tests/ -v -k "schema" --ignore=tests/apps/auth/test_service.py "$@"
}

run_watch() {
    echo -e "${CYAN}监听模式运行测试...${NC}"
    if ! $PYTHON_BIN -c "import pytest_watch" 2>/dev/null; then
        echo -e "${YELLOW}安装 pytest-watch...${NC}"
        pip install pytest-watch
    fi
    ptw tests/ --ignore=tests/apps/auth/test_service.py "$@"
}

run_e2e_tests() {
    local BASE_URL="http://localhost:8000"

    # 解析 --url 参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --url) BASE_URL="$2"; shift 2 ;;
            *) shift ;;
        esac
    done

    echo -e "${CYAN}运行端到端测试...${NC}"
    echo -e "基础 URL: $BASE_URL"
    echo ""

    # 检查服务是否可用
    if ! curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health" 2>/dev/null | grep -q "200"; then
        echo -e "${YELLOW}警告: 服务可能未运行，尝试启动...${NC}"
        "$SCRIPT_DIR/control.sh" start -d
        sleep 3
    fi

    TEST_BASE_URL="$BASE_URL" $PYTHON_BIN -m pytest tests/test_e2e.py -v
}

run_service_tests() {
    echo -e "${BLUE}=============================================================${NC}"
    echo -e "${BLUE}服务功能测试${NC}"
    echo -e "${BLUE}=============================================================${NC}"
    echo ""

    local PASSED=0
    local FAILED=0

    # 测试 1: 检查脚本存在
    echo -e "${CYAN}[1/6] 检查脚本文件...${NC}"
    if [ -f "$SCRIPT_DIR/control.sh" ] && [ -f "$SCRIPT_DIR/service.sh" ]; then
        echo -e "  ${GREEN}✓${NC} 脚本文件存在"
        ((PASSED++))
    else
        echo -e "  ${RED}✗${NC} 脚本文件缺失"
        ((FAILED++))
    fi

    # 测试 2: 检查脚本权限
    echo -e "${CYAN}[2/6] 检查脚本权限...${NC}"
    if [ -x "$SCRIPT_DIR/control.sh" ] && [ -x "$SCRIPT_DIR/service.sh" ]; then
        echo -e "  ${GREEN}✓${NC} 脚本具有执行权限"
        ((PASSED++))
    else
        echo -e "  ${RED}✗${NC} 脚本缺少执行权限"
        ((FAILED++))
    fi

    # 测试 3: 检查帮助命令
    echo -e "${CYAN}[3/6] 测试帮助命令...${NC}"
    if "$SCRIPT_DIR/control.sh" help > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} 帮助命令正常"
        ((PASSED++))
    else
        echo -e "  ${RED}✗${NC} 帮助命令失败"
        ((FAILED++))
    fi

    # 测试 4: 检查状态命令
    echo -e "${CYAN}[4/6] 测试状态命令...${NC}"
    if "$SCRIPT_DIR/control.sh" status > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} 状态命令正常"
        ((PASSED++))
    else
        echo -e "  ${RED}✗${NC} 状态命令失败"
        ((FAILED++))
    fi

    # 测试 5: 检查 .env 文件
    echo -e "${CYAN}[5/6] 检查配置文件...${NC}"
    if [ -f "$PROJECT_DIR/.env" ]; then
        echo -e "  ${GREEN}✓${NC} .env 文件存在"
        ((PASSED++))
    else
        echo -e "  ${RED}✗${NC} .env 文件缺失"
        ((FAILED++))
    fi

    # 测试 6: 检查目录结构
    echo -e "${CYAN}[6/6] 检查目录结构...${NC}"
    local DIRS_OK=true
    [ ! -d "$PROJECT_DIR/logs" ] && mkdir -p "$PROJECT_DIR/logs"
    [ ! -d "$PROJECT_DIR/run" ] && mkdir -p "$PROJECT_DIR/run"
    if [ -d "$PROJECT_DIR/logs" ] && [ -d "$PROJECT_DIR/run" ]; then
        echo -e "  ${GREEN}✓${NC} 必要目录存在"
        ((PASSED++))
    else
        echo -e "  ${RED}✗${NC} 目录创建失败"
        ((FAILED++))
    fi

    echo ""
    echo -e "${BLUE}=============================================================${NC}"
    echo -e "测试结果: ${GREEN}通过 $PASSED${NC} / ${RED}失败 $FAILED${NC}"
    echo -e "${BLUE}=============================================================${NC}"

    if [ $FAILED -gt 0 ]; then
        return 1
    fi
    return 0
}

# 解析命令
COMMAND=${1:-unit}
shift || true

case "$COMMAND" in
    unit|"")
        run_unit_tests "$@"
        ;;
    all)
        run_all_tests "$@"
        ;;
    coverage|cov)
        run_coverage "$@"
        ;;
    integration|int)
        run_integration_tests "$@"
        ;;
    e2e|endtoend)
        run_e2e_tests "$@"
        ;;
    service|svc)
        run_service_tests "$@"
        ;;
    fast)
        run_fast_tests "$@"
        ;;
    watch|w)
        run_watch "$@"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        # 未知命令作为 pytest 参数传递
        $PYTHON_BIN -m pytest tests/ -v --ignore=tests/apps/auth/test_service.py "$COMMAND" "$@"
        ;;
esac
