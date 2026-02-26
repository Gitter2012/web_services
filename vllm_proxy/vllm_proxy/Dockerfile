#==============================================================================
# vLLM Proxy Docker 镜像
#==============================================================================

FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# 设置工作目录
WORKDIR /app

# 防止交互式配置提示
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

#==============================================================================
# 安装系统依赖
#==============================================================================
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    python3.10-venv \
    git \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# 设置 Python3 为默认
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.10 1
RUN update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

#==============================================================================
# 安装 Python 依赖
#==============================================================================
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

#==============================================================================
# 复制项目代码
#==============================================================================
COPY proxy/ ./proxy/
COPY client/ ./client/
COPY configs/ ./configs/
COPY scripts/ ./scripts/

# 创建必要目录
RUN mkdir -p logs models tmp

# 设置脚本权限
RUN chmod +x scripts/*.sh

#==============================================================================
# 环境变量配置
#==============================================================================

# 代理服务配置
ENV PROXY_HOST=0.0.0.0
ENV PROXY_PORT=8080
ENV IDLE_TIMEOUT=300

# GPU 配置
ENV GPU_ID=0
ENV RESERVED_MEMORY_MB=2048
ENV GPU_MEMORY_UTILIZATION=0.9

# 日志配置
ENV LOG_LEVEL=INFO
ENV LOG_FILE=logs/vllm_proxy.log

# Python 路径
ENV PYTHONPATH=/app:$PYTHONPATH

# HuggingFace 缓存目录
ENV HF_HOME=/app/models
ENV TRANSFORMERS_CACHE=/app/models

#==============================================================================
# 健康检查
#==============================================================================
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health/live || exit 1

#==============================================================================
# 暴露端口
#==============================================================================
EXPOSE 8080

#==============================================================================
# 启动命令
#==============================================================================
CMD ["python3", "proxy/main.py"]
