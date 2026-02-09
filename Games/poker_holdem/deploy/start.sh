#!/bin/bash

# 获取脚本所在目录的父目录（项目根目录）
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "================================================"
echo "  德州扑克游戏服务器"
echo "================================================"
echo ""
echo "项目目录: $PROJECT_DIR"
echo ""

# 进入项目目录
cd "$PROJECT_DIR"

# 设置环境变量
export PYTHONPATH="$PROJECT_DIR"

# 检查Python是否安装
if ! command -v python &> /dev/null; then
    echo "❌ 错误: 未找到Python"
    exit 1
fi

echo "✓ Python已安装"

# 检查依赖是否安装
echo "检查依赖..."
python -c "import fastapi" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "正在安装依赖..."
    pip install -r requirements.txt
fi

echo "✓ 依赖已就绪"
echo ""

# 启动服务器
echo "================================================"
echo "  启动服务器..."
echo "================================================"
echo ""
echo "服务器地址: http://localhost:8000"
echo ""
echo "按 Ctrl+C 停止服务器"
echo ""

python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
