#!/bin/bash
#==============================================================================
# vLLM Proxy 安装脚本
#==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP $1/5]${NC} $2"
}

#==============================================================================
# 安装步骤
#==============================================================================

check_system() {
    log_step 1 "检查系统环境"

    # 检查操作系统
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        log_info "操作系统: $NAME $VERSION_ID"
    fi

    # 检查 Python 版本
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 未安装，请先安装 Python 3.8+"
        exit 1
    fi

    local python_version=$(python3 --version 2>&1 | awk '{print $2}')
    log_info "Python 版本: $python_version"

    # 检查 pip
    if ! command -v pip3 &> /dev/null; then
        log_warn "pip3 未安装，尝试安装..."
        python3 -m ensurepip --upgrade || {
            log_error "无法安装 pip，请手动安装"
            exit 1
        }
    fi

    # 检查 CUDA
    if command -v nvidia-smi &> /dev/null; then
        log_info "CUDA 可用:"
        nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader | head -1
    else
        log_warn "CUDA 未检测到，GPU 功能将不可用"
    fi
}

install_dependencies() {
    log_step 2 "安装 Python 依赖"

    cd "$PROJECT_DIR"

    # 创建虚拟环境（可选）
    if [[ ! -d "venv" ]]; then
        log_info "创建虚拟环境..."
        python3 -m venv venv
    fi

    # 激活虚拟环境
    source venv/bin/activate

    # 升级 pip
    pip install --upgrade pip

    # 安装依赖
    if [[ -f "requirements.txt" ]]; then
        log_info "安装依赖包..."
        pip install -r requirements.txt
    else
        log_error "requirements.txt 不存在"
        exit 1
    fi

    log_info "依赖安装完成"
}

setup_directories() {
    log_step 3 "创建目录结构"

    mkdir -p "$PROJECT_DIR"/{logs,models,tmp,proxy,client}

    # 设置权限
    chmod 755 "$PROJECT_DIR"/logs
    chmod 755 "$PROJECT_DIR"/models
    chmod 755 "$PROJECT_DIR"/tmp

    log_info "目录结构创建完成"
}

setup_config() {
    log_step 4 "配置初始化"

    local config_file="$PROJECT_DIR/configs/config.yaml"

    if [[ ! -f "$config_file" ]]; then
        log_info "创建默认配置文件..."
        cat > "$config_file" << 'EOF'
# vLLM Proxy 配置文件

# GPU 配置
gpu:
  gpu_id: 0
  reserved_memory_mb: 2048
  memory_utilization: 0.9

# 代理服务配置
proxy:
  host: "0.0.0.0"
  port: 8080
  base_port: 8000
  idle_timeout_seconds: 300
  health_check_interval: 10
  max_start_retries: 3
  start_timeout_seconds: 120
  stop_timeout_seconds: 30

# 日志配置
logging:
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: "logs/vllm_proxy.log"
  max_bytes: 10485760
  backup_count: 5

# 模型配置
models:
  # 示例模型配置
  llama2-7b-chat:
    model_path: "meta-llama/Llama-2-7b-chat-hf"
    param_count: 7
    precision: "fp16"
    tensor_parallel: 1
    max_model_len: 4096
    max_num_seqs: 16
    num_layers: 32
    hidden_size: 4096
    num_attention_heads: 32
    num_kv_heads: 32

  # 更多模型...
  # qwen-7b-chat:
  #   model_path: "Qwen/Qwen-7B-Chat"
  #   param_count: 7
  #   precision: "bf16"
  #   max_model_len: 8192
EOF
    fi

    log_info "配置文件: $config_file"
    log_warn "请根据实际需求修改配置文件"
}

setup_scripts() {
    log_step 5 "设置执行权限"

    chmod +x "$PROJECT_DIR"/scripts/*.sh

    log_info "脚本权限设置完成"
}

show_summary() {
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║              安装完成！                                    ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "使用说明:"
    echo "  1. 编辑配置文件: configs/config.yaml"
    echo "  2. 启动服务:     ./scripts/start.sh"
    echo "  3. 查看状态:     ./scripts/status.sh"
    echo "  4. 停止服务:     ./scripts/stop.sh"
    echo ""
    echo "快速开始:"
    echo "  cd $PROJECT_DIR"
    echo "  ./scripts/start.sh -d"
    echo ""
    echo "API 端点:"
    echo "  Health:   http://localhost:8080/health"
    echo "  Models:   http://localhost:8080/v1/models"
    echo "  Chat:     http://localhost:8080/v1/chat/completions"
    echo ""
}

#==============================================================================
# 主程序
#==============================================================================

main() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║           vLLM Proxy 安装程序                              ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    check_system
    install_dependencies
    setup_directories
    setup_config
    setup_scripts
    show_summary
}

main "$@"
