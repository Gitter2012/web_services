# =============================================================================
# 模块: proxy/proxy_server.py
# 功能: FastAPI 代理服务，提供 OpenAI 兼容的 API 接口
# 架构角色: API 层的核心组件。作为服务的入口点，处理所有 HTTP 请求，
#           并将请求转发给对应的后端 vLLM 服务进程。
# 设计理念: 完全兼容 OpenAI API 格式，使客户端无需修改即可使用；
#           支持流式和非流式响应；提供健康检查和监控端点；
#           支持可选的 API Key 认证。
# =============================================================================

"""FastAPI 代理服务

提供 OpenAI 兼容的 API 接口
"""

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import aiohttp
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from config import Config, load_config
from gpu_monitor import GPUMonitor
from model_manager import ModelManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 全局组件实例
config: Config = None
gpu_monitor: GPUMonitor = None
model_manager: ModelManager = None


# =============================================================================
# lifespan 异步上下文管理器
# 职责: 管理 FastAPI 应用的生命周期
# 设计决策:
#   1. 启动时初始化配置、GPU 监控器和模型管理器
#   2. 关闭时优雅停止所有模型并释放资源
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理

    处理应用的启动和关闭逻辑。
    """
    global config, gpu_monitor, model_manager

    # ========== 启动阶段 ==========
    logger.info("Starting vLLM Proxy Service...")

    # 加载配置
    config_path = app.state.config_path if hasattr(app.state, 'config_path') else None
    config = load_config(config_path)

    # 初始化 GPU 监控器
    gpu_monitor = GPUMonitor(
        gpu_id=config.gpu.gpu_id,
        reserved_memory_mb=config.gpu.reserved_memory_mb
    )

    # 初始化模型管理器
    model_manager = ModelManager(config, gpu_monitor)
    await model_manager.start()

    logger.info(f"vLLM Proxy started on {config.proxy.host}:{config.proxy.port}")
    logger.info(f"Registered models: {list(config.models.keys())}")

    yield

    # ========== 关闭阶段 ==========
    logger.info("Shutting down vLLM Proxy Service...")
    await model_manager.stop()
    gpu_monitor.shutdown()
    logger.info("vLLM Proxy stopped")


# =============================================================================
# FastAPI 应用实例
# 职责: 定义 FastAPI 应用及其元数据
# =============================================================================
app = FastAPI(
    title="vLLM Dynamic Proxy",
    description="按需加载、自动释放的 vLLM 模型服务代理",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 中间件：允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# 请求日志中间件
# 职责: 记录所有请求的方法、路径、状态码和耗时
# =============================================================================
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """请求日志中间件

    记录每个请求的处理时间和响应状态。
    """
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time

    logger.info(
        f"{request.method} {request.url.path} "
        f"- {response.status_code} - {process_time:.3f}s"
    )
    return response


# =============================================================================
# API Key 验证函数
# 职责: 验证请求中的 API Key
# 设计决策:
#   1. 如果服务未配置 api_key，跳过验证
#   2. 支持 "Bearer <key>" 和直接 "<key>" 两种格式
# =============================================================================
def verify_api_key(request: Request) -> bool:
    """验证 API Key（与 vLLM/OpenAI 兼容格式）

    支持格式:
        - Authorization: Bearer <api_key>
        - Authorization: <api_key>

    Args:
        request: FastAPI 请求对象

    Returns:
        True 如果验证通过
    """
    if not config or not config.proxy.api_key:
        return True

    auth_header = request.headers.get("Authorization", "")

    # 提取 api_key（支持 "Bearer <key>" 或直接 "<key>"）
    if auth_header.startswith("Bearer "):
        provided_key = auth_header[7:]  # 去掉 "Bearer " 前缀
    else:
        provided_key = auth_header

    return provided_key == config.proxy.api_key


# =============================================================================
# API Key 认证中间件
# 职责: 拦截需要认证的请求
# 设计决策:
#   1. 跳过健康检查和监控端点
#   2. 返回 OpenAI 兼容的错误格式
# =============================================================================
@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    """API Key 认证中间件"""
    # 跳过健康检查端点
    if request.url.path in ['/health', '/health/ready', '/health/live', '/metrics']:
        return await call_next(request)

    # 验证 API Key
    if not verify_api_key(request):
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "message": "Incorrect API key provided",
                    "type": "invalid_request_error",
                    "param": None,
                    "code": "invalid_api_key"
                }
            }
        )

    return await call_next(request)


# =============================================================================
# OpenAI 兼容 API - 聊天补全
# 职责: 处理 /v1/chat/completions 请求
# 设计决策:
#   1. 支持 stream 和非 stream 两种模式
#   2. 自动获取或加载模型
#   3. 使用引用计数管理模型生命周期
# =============================================================================
@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """OpenAI 兼容的聊天补全接口

    处理聊天补全请求，支持流式和非流式响应。

    Request Body:
        model: 模型标识符（必需）
        messages: 消息列表（必需）
        stream: 是否流式输出（可选，默认 False）
        其他参数: temperature, max_tokens, top_p 等

    Returns:
        聊天补全结果（JSON 或 SSE 流）
    """
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON body")

    model_id = body.get("model")
    if not model_id:
        raise HTTPException(400, "Missing 'model' field")

    stream = body.get("stream", False)

    # 获取或加载模型
    try:
        model = await model_manager.get_model(model_id)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        logger.error(f"Failed to load model {model_id}: {e}")
        raise HTTPException(500, f"Failed to load model: {e}")

    if not model:
        raise HTTPException(404, f"Model '{model_id}' not found")

    # 获取模型引用（增加请求计数）
    if not model_manager.acquire_model(model_id):
        raise HTTPException(503, f"Model '{model_id}' is not ready")

    target_url = f"http://localhost:{model.port}/v1/chat/completions"

    try:
        if stream:
            # 流式响应
            return StreamingResponse(
                _stream_proxy(request, body, target_url, model_id),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )
        else:
            # 非流式响应
            return await _proxy_request(request, body, target_url, model_id)

    except Exception as e:
        model_manager.release_model(model_id)
        raise


# =============================================================================
# OpenAI 兼容 API - 文本补全
# 职责: 处理 /v1/completions 请求
# =============================================================================
@app.post("/v1/completions")
async def completions(request: Request):
    """OpenAI 兼容的补全接口

    处理文本补全请求。
    """
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON body")

    model_id = body.get("model")
    if not model_id:
        raise HTTPException(400, "Missing 'model' field")

    stream = body.get("stream", False)

    try:
        model = await model_manager.get_model(model_id)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to load model: {e}")

    if not model:
        raise HTTPException(404, f"Model '{model_id}' not found")

    if not model_manager.acquire_model(model_id):
        raise HTTPException(503, f"Model '{model_id}' is not ready")

    target_url = f"http://localhost:{model.port}/v1/completions"

    try:
        if stream:
            return StreamingResponse(
                _stream_proxy(request, body, target_url, model_id),
                media_type="text/event-stream"
            )
        else:
            return await _proxy_request(request, body, target_url, model_id)
    except Exception:
        model_manager.release_model(model_id)
        raise


# =============================================================================
# OpenAI 兼容 API - 嵌入向量
# 职责: 处理 /v1/embeddings 请求
# =============================================================================
@app.post("/v1/embeddings")
async def embeddings(request: Request):
    """OpenAI 兼容的嵌入接口

    处理文本嵌入向量生成请求。
    """
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON body")

    model_id = body.get("model")
    if not model_id:
        raise HTTPException(400, "Missing 'model' field")

    try:
        model = await model_manager.get_model(model_id)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to load model: {e}")

    if not model:
        raise HTTPException(404, f"Model '{model_id}' not found")

    if not model_manager.acquire_model(model_id):
        raise HTTPException(503, f"Model '{model_id}' is not ready")

    target_url = f"http://localhost:{model.port}/v1/embeddings"

    try:
        return await _proxy_request(request, body, target_url, model_id)
    except Exception:
        model_manager.release_model(model_id)
        raise


# =============================================================================
# _proxy_request 函数
# 职责: 代理非流式请求到 vLLM 后端
# =============================================================================
async def _proxy_request(
    request: Request,
    body: dict,
    target_url: str,
    model_id: str
) -> JSONResponse:
    """代理非流式请求

    将请求转发给 vLLM 后端并返回响应。

    Args:
        request: 原始请求对象
        body: 请求体
        target_url: 目标 URL
        model_id: 模型标识符

    Returns:
        JSON 响应
    """
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                target_url,
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=300)
            ) as resp:
                result = await resp.json()

                if resp.status != 200:
                    raise HTTPException(resp.status, result.get("error", "Unknown error"))

                return JSONResponse(content=result)

        except aiohttp.ClientError as e:
            logger.error(f"Proxy request failed: {e}")
            raise HTTPException(502, f"Model inference failed: {e}")
        finally:
            # 释放模型引用
            model_manager.release_model(model_id)


# =============================================================================
# _stream_proxy 函数
# 职责: 代理流式请求到 vLLM 后端
# =============================================================================
async def _stream_proxy(
    request: Request,
    body: dict,
    target_url: str,
    model_id: str
) -> AsyncGenerator[str, None]:
    """代理流式请求

    将请求转发给 vLLM 后端并以生成器形式返回流式响应。

    Args:
        request: 原始请求对象
        body: 请求体
        target_url: 目标 URL
        model_id: 模型标识符

    Yields:
        SSE 格式的数据块
    """
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                target_url,
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=300)
            ) as resp:

                if resp.status != 200:
                    error_body = await resp.text()
                    yield f"data: {json.dumps({'error': error_body})}\n\n"
                    return

                # 逐块读取并转发响应
                async for chunk in resp.content:
                    if chunk:
                        yield chunk.decode('utf-8')

        except aiohttp.ClientError as e:
            logger.error(f"Stream proxy failed: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            # 释放模型引用
            model_manager.release_model(model_id)


# =============================================================================
# 模型管理 API - 列出模型
# 职责: 返回所有可用模型及其状态
# =============================================================================
@app.get("/v1/models")
async def list_models():
    """列出可用模型

    返回所有已配置的模型及其当前状态。
    """
    models = []

    for model_id, cfg in config.models.items():
        status = model_manager.get_model_status(model_id)

        model_info = {
            "id": model_id,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "vllm-proxy",
            "status": status["status"] if status else "stopped",
            "config": {
                "model_path": cfg.model_path,
                "param_count": cfg.param_count,
                "precision": cfg.precision,
            }
        }

        if status:
            model_info.update({
                "port": status["port"],
                "gpu_memory_mb": status["gpu_memory_mb"],
                "request_count": status["request_count"],
                "last_used_at": status["last_used_at"],
            })

        models.append(model_info)

    return {"object": "list", "data": models}


# =============================================================================
# 模型管理 API - 获取模型详情
# 职责: 返回指定模型的详细状态
# =============================================================================
@app.get("/v1/models/{model_id}")
async def get_model(model_id: str):
    """获取模型详情

    Args:
        model_id: 模型标识符

    Returns:
        模型详细信息
    """
    if model_id not in config.models:
        raise HTTPException(404, f"Model '{model_id}' not found")

    status = model_manager.get_model_status(model_id)

    return {
        "id": model_id,
        "object": "model",
        "status": status["status"] if status else "stopped",
        "detail": status
    }


# =============================================================================
# 管理员 API - 预加载模型
# 职责: 手动预加载指定模型
# =============================================================================
@app.post("/admin/models/{model_id}/load")
async def admin_load_model(model_id: str):
    """管理员接口：预加载模型

    手动加载指定模型，无需等待请求触发。

    Args:
        model_id: 模型标识符

    Returns:
        加载结果
    """
    if model_id not in config.models:
        raise HTTPException(404, f"Model '{model_id}' not found")

    try:
        model = await model_manager.get_model(model_id)
        return {
            "success": True,
            "model_id": model_id,
            "port": model.port,
            "status": model.status.value
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# =============================================================================
# 管理员 API - 卸载模型
# 职责: 手动卸载指定模型
# =============================================================================
@app.post("/admin/models/{model_id}/unload")
async def admin_unload_model(model_id: str):
    """管理员接口：卸载模型

    手动卸载指定模型，释放显存资源。

    Args:
        model_id: 模型标识符

    Returns:
        卸载结果
    """
    success = await model_manager.unload_model(model_id)
    if not success:
        raise HTTPException(404, f"Model '{model_id}' not loaded")

    return {"success": True, "model_id": model_id}


# =============================================================================
# 系统状态 API - 健康检查
# 职责: 返回服务健康状态和 GPU 信息
# =============================================================================
@app.get("/health")
async def health_check():
    """健康检查

    返回服务健康状态、GPU 状态和已加载模型信息。
    """
    gpu_stats = gpu_monitor.get_stats()

    return {
        "status": "healthy",
        "gpu": {
            "id": gpu_stats.gpu_id,
            "name": gpu_stats.name,
            "temperature": gpu_stats.temperature,
            "utilization_percent": gpu_stats.utilization_percent,
            "memory": {
                "total_mb": gpu_stats.memory.total_mb,
                "used_mb": gpu_stats.memory.used_mb,
                "free_mb": gpu_stats.memory.free_mb,
                "available_mb": gpu_stats.memory.available_mb,
            },
            "power_draw_w": gpu_stats.power_draw_w,
            "power_limit_w": gpu_stats.power_limit_w,
        },
        "loaded_models": len(model_manager.models),
        "model_status": model_manager.get_model_status()
    }


# =============================================================================
# 系统状态 API - 就绪检查
# 职责: Kubernetes 就绪探针端点
# =============================================================================
@app.get("/health/ready")
async def readiness_check():
    """就绪检查（用于 K8s）

    检查服务是否已准备好接收请求。
    """
    return {"ready": True}


# =============================================================================
# 系统状态 API - 存活检查
# 职责: Kubernetes 存活探针端点
# =============================================================================
@app.get("/health/live")
async def liveness_check():
    """存活检查（用于 K8s）

    检查服务是否存活。
    """
    return {"alive": True}


# =============================================================================
# 系统状态 API - Prometheus 指标
# 职责: 返回 Prometheus 格式的监控指标
# =============================================================================
@app.get("/metrics")
async def metrics():
    """Prometheus 格式的指标

    返回 GPU 和模型相关的监控指标。
    """
    gpu_stats = gpu_monitor.get_stats()
    model_status = model_manager.get_model_status()

    lines = [
        "# HELP vllm_gpu_memory_total_mb Total GPU memory in MB",
        "# TYPE vllm_gpu_memory_total_mb gauge",
        f"vllm_gpu_memory_total_mb{{gpu_id=\"{gpu_stats.gpu_id}\"}} {gpu_stats.memory.total_mb}",
        "",
        "# HELP vllm_gpu_memory_used_mb Used GPU memory in MB",
        "# TYPE vllm_gpu_memory_used_mb gauge",
        f"vllm_gpu_memory_used_mb{{gpu_id=\"{gpu_stats.gpu_id}\"}} {gpu_stats.memory.used_mb}",
        "",
        "# HELP vllm_gpu_utilization_percent GPU utilization percentage",
        "# TYPE vllm_gpu_utilization_percent gauge",
        f"vllm_gpu_utilization_percent{{gpu_id=\"{gpu_stats.gpu_id}\"}} {gpu_stats.utilization_percent}",
        "",
        "# HELP vllm_model_loaded Whether model is loaded",
        "# TYPE vllm_model_loaded gauge",
    ]

    # 添加模型加载状态指标
    for model_id in config.models.keys():
        loaded = 1 if model_id in model_manager.models else 0
        lines.append(f'vllm_model_loaded{{model_id="{model_id}"}} {loaded}')

    lines.extend([
        "",
        "# HELP vllm_model_requests_active Active requests per model",
        "# TYPE vllm_model_requests_active gauge",
    ])

    # 添加活跃请求指标
    for model_id, status in model_status.items():
        lines.append(f'vllm_model_requests_active{{model_id="{model_id}"}} {status["request_count"]}')

    return StreamingResponse(
        iter("\n".join(lines) + "\n"),
        media_type="text/plain"
    )


# =============================================================================
# 主入口
# 职责: 支持直接运行此文件启动服务
# =============================================================================
if __name__ == "__main__":
    import sys
    import uvicorn

    # 解析命令行参数
    config_path = None
    if len(sys.argv) > 1:
        config_path = sys.argv[1]

    # 设置配置路径
    app.state.config_path = config_path

    # 启动服务
    uvicorn.run(
        app,
        host=config.proxy.host if config else "0.0.0.0",
        port=config.proxy.port if config else 8080,
        log_level="info"
    )
