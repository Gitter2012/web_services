# =============================================================================
# 模块: proxy/main.py
# 功能: vLLM Proxy 服务主入口
# 架构角色: 服务启动的引导程序。负责解析命令行参数、加载配置、
#           并启动 uvicorn 服务器运行 FastAPI 应用。
# 设计理念: 保持入口文件的简洁性，将核心逻辑委托给 proxy_server.py；
#           支持通过命令行参数指定配置文件路径。
# =============================================================================

"""vLLM Proxy 主入口"""

import os
import sys

# 添加 proxy 目录到 Python 路径
# 确保可以正确导入同目录下的模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn

from config import load_config
from proxy_server import app


# =============================================================================
# 主程序入口
# 职责: 解析配置并启动服务
# =============================================================================
if __name__ == "__main__":
    # 加载配置获取 host 和 port
    # 支持通过命令行参数指定配置文件路径
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    config = load_config(config_path)

    # 设置配置路径到 app.state，供 lifespan 使用
    app.state.config_path = config_path

    # 打印启动信息
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                  vLLM Dynamic Proxy Service                  ║
╠══════════════════════════════════════════════════════════════╣
║  Version: 1.0.0                                              ║
║  Listen: {config.proxy.host}:{config.proxy.port:<29} ║
║  GPU ID: {config.gpu.gpu_id:<49} ║
║  Idle Timeout: {config.proxy.idle_timeout_seconds}s{' '*39} ║
╚══════════════════════════════════════════════════════════════╝
    """)

    # 启动 uvicorn 服务器
    # 使用 proxy_server:app 作为应用入口
    uvicorn.run(
        "proxy_server:app",
        host=config.proxy.host,
        port=config.proxy.port,
        reload=False,
        log_level=config.logging.level.lower()
    )
