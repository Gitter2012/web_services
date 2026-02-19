#!/bin/bash
# =============================================================================
# ResearchPulse v2 手动邮件发送脚本
# =============================================================================
# 用法: ./scripts/email.sh <command> [options]
#
# 命令:
#   test     发送测试邮件，验证邮件配置是否正常
#   notify   触发用户订阅通知（等同于定时任务）
#   send     向指定地址发送自定义邮件
#
# 示例:
#   ./scripts/email.sh test --to admin@example.com
#   ./scripts/email.sh test --to admin@example.com --backend smtp
#   ./scripts/email.sh notify
#   ./scripts/email.sh notify --since 2025-01-01 --max-users 10
#   ./scripts/email.sh send --to user@example.com --subject "标题" --body "内容"
#   ./scripts/email.sh send --to a@x.com,b@x.com --subject "标题" --body-file msg.txt
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
PYTHON_SCRIPT="$PROJECT_DIR/scripts/_email_runner.py"

# 显示帮助
show_help() {
    echo -e "${BLUE}ResearchPulse v2 手动邮件发送脚本${NC}"
    echo ""
    echo "用法: ./scripts/email.sh <command> [options]"
    echo ""
    echo "命令:"
    echo -e "  ${CYAN}test${NC}      发送测试邮件，验证邮件配置"
    echo -e "  ${CYAN}notify${NC}    触发用户订阅通知"
    echo -e "  ${CYAN}send${NC}      向指定地址发送自定义邮件"
    echo ""
    echo "test 选项:"
    echo "  --to <email>                 收件人邮箱地址 (必填)"
    echo "  --backend <smtp|sendgrid|    指定邮件后端 (默认: 按优先级 fallback)"
    echo "             mailgun|brevo>"
    echo ""
    echo "notify 选项:"
    echo "  --since <date>               文章时间下限 (YYYY-MM-DD, 默认: 过去24小时)"
    echo "  --max-users <n>              最大处理用户数 (默认: 100)"
    echo ""
    echo "send 选项:"
    echo "  --to <email[,email,...]>     收件人邮箱 (多个以逗号分隔, 必填)"
    echo "  --subject <subject>          邮件主题 (必填)"
    echo "  --body <text>                邮件正文 (与 --body-file 二选一)"
    echo "  --body-file <path>           从文件读取邮件正文"
    echo "  --html                       将正文视为 HTML 格式"
    echo "  --backend <smtp|sendgrid|    指定邮件后端 (默认: 按优先级 fallback)"
    echo "             mailgun|brevo>"
    echo ""
    echo "示例:"
    echo -e "  ${GREEN}# 发送测试邮件 (使用默认 fallback)${NC}"
    echo "  ./scripts/email.sh test --to admin@example.com"
    echo ""
    echo -e "  ${GREEN}# 指定 SMTP 后端发送测试邮件${NC}"
    echo "  ./scripts/email.sh test --to admin@example.com --backend smtp"
    echo ""
    echo -e "  ${GREEN}# 触发用户订阅通知 (过去 24 小时)${NC}"
    echo "  ./scripts/email.sh notify"
    echo ""
    echo -e "  ${GREEN}# 触发通知，指定时间范围和用户数${NC}"
    echo "  ./scripts/email.sh notify --since 2025-01-01 --max-users 10"
    echo ""
    echo -e "  ${GREEN}# 发送自定义邮件${NC}"
    echo "  ./scripts/email.sh send --to user@example.com --subject '标题' --body '内容'"
    echo ""
    echo -e "  ${GREEN}# 从文件读取正文，发送 HTML 邮件给多人${NC}"
    echo "  ./scripts/email.sh send --to a@x.com,b@x.com --subject '标题' --body-file msg.html --html"
    echo ""
}

# 检查环境
check_env() {
    if [ ! -f "$ENV_FILE" ]; then
        echo -e "${RED}错误: .env 文件不存在${NC}"
        echo "请先创建 .env 文件并配置邮件相关参数"
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
}

# 检查邮件配置
check_email_config() {
    local has_config=false

    # 检查至少有一种邮件后端配置
    if [ -n "$SMTP_HOST" ] && [ -n "$SMTP_USER" ]; then
        has_config=true
    fi
    if [ -n "$SENDGRID_API_KEY" ]; then
        has_config=true
    fi
    if [ -n "$MAILGUN_API_KEY" ]; then
        has_config=true
    fi
    if [ -n "$BREVO_API_KEY" ]; then
        has_config=true
    fi

    if [ "$has_config" = false ]; then
        echo -e "${YELLOW}警告: 未检测到邮件后端配置${NC}"
        echo "请确认 .env 中至少配置了以下其中一组:"
        echo "  - SMTP:     SMTP_HOST, SMTP_USER, SMTP_PASSWORD"
        echo "  - SendGrid: SENDGRID_API_KEY"
        echo "  - Mailgun:  MAILGUN_API_KEY, MAILGUN_DOMAIN"
        echo "  - Brevo:    BREVO_API_KEY"
        echo ""
        echo -e "${YELLOW}继续执行，但可能会发送失败...${NC}"
        echo ""
    fi
}

# 主入口
COMMAND="${1:-}"

# 帮助
if [ -z "$COMMAND" ] || [ "$COMMAND" = "--help" ] || [ "$COMMAND" = "-h" ]; then
    show_help
    exit 0
fi

# 验证命令
VALID_COMMANDS=("test" "notify" "send")
IS_VALID=false
for c in "${VALID_COMMANDS[@]}"; do
    if [ "$COMMAND" = "$c" ]; then
        IS_VALID=true
        break
    fi
done

if [ "$IS_VALID" = false ]; then
    echo -e "${RED}错误: 未知命令 '$COMMAND'${NC}"
    echo ""
    show_help
    exit 1
fi

# 检查环境
check_env
check_python
check_email_config

# 显示开始信息
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}ResearchPulse v2 邮件工具${NC}"
echo -e "${BLUE}============================================${NC}"
echo -e "命令: ${CYAN}$COMMAND${NC}"
echo -e "${BLUE}--------------------------------------------${NC}"
echo ""

# 运行 Python 脚本，传递所有参数
cd "$PROJECT_DIR"
python3 "${PYTHON_SCRIPT}" "$@"

EXIT_CODE=$?

# 显示结果
echo ""
echo -e "${BLUE}--------------------------------------------${NC}"
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}操作完成${NC}"
else
    echo -e "${RED}操作失败 (退出码: $EXIT_CODE)${NC}"
fi

exit $EXIT_CODE
