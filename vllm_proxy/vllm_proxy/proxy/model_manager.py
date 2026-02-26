# =============================================================================
# 模块: proxy/model_manager.py
# 功能: 模型管理模块，负责模型的生命周期管理：加载、卸载、LRU 缓存、空闲检测
# 架构角色: 核心业务逻辑层。管理多个 vLLM 进程的创建、监控和销毁，
#           实现"按需加载、自动释放"的动态模型服务机制。
# 设计理念: 通过异步进程管理实现非阻塞的模型启停；使用 LRU 策略优化模型缓存；
#           通过空闲检测自动释放资源，最大化 GPU 利用效率。
# =============================================================================

"""模型管理模块

负责模型的生命周期管理：加载、卸载、LRU 缓存、空闲检测
"""

import asyncio
import logging
import os
import signal
import socket
import sys
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import aiohttp

from config import Config, ModelConfig
from gpu_monitor import GPUMonitor

# 模块级日志器
logger = logging.getLogger(__name__)


# =============================================================================
# ModelStatus 枚举
# 职责: 定义模型的生命周期状态
# 设计决策:
#   1. 使用枚举确保状态值的类型安全
#   2. 覆盖模型从停止到运行的完整状态机
# =============================================================================
class ModelStatus(Enum):
    """模型状态

    状态转换流程:
        STOPPED -> STARTING -> RUNNING -> STOPPING -> STOPPED
                        |                    ^
                        v                    |
                      ERROR -----------------+
                        |
                        v
                      EVICTING -> STOPPED
    """

    STOPPED = "stopped"          # 未加载
    STARTING = "starting"        # 启动中
    RUNNING = "running"          # 运行中
    STOPPING = "stopping"        # 停止中
    ERROR = "error"              # 错误状态
    EVICTING = "evicting"        # 淘汰中（显存不足时被强制卸载）


# =============================================================================
# ModelInstance 数据类
# 职责: 封装单个模型实例的运行时状态
# 设计决策:
#   1. 包含模型进程、端口、状态等完整信息
#   2. 跟踪请求计数和访问时间，支持 LRU 和空闲检测
# =============================================================================
@dataclass
class ModelInstance:
    """模型实例

    Attributes:
        model_id: 模型唯一标识符
        config: 模型配置
        process: vLLM 子进程对象
        status: 当前状态
        port: 服务端口
        gpu_memory_mb: 占用的显存（MB）
        created_at: 创建时间
        last_used_at: 最后使用时间
        request_count: 当前处理中的请求数（用于判断是否空闲）
        total_requests: 历史总请求数
        idle_timer: 空闲超时检测任务
        start_retries: 启动重试次数
        error_message: 错误信息（如果状态为 ERROR）
    """

    model_id: str
    config: ModelConfig
    process: Optional[asyncio.subprocess.Process] = None
    status: ModelStatus = ModelStatus.STOPPED
    port: int = 0
    gpu_memory_mb: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    last_used_at: datetime = field(default_factory=datetime.now)
    request_count: int = 0           # 当前处理中的请求数
    total_requests: int = 0          # 历史总请求数
    idle_timer: Optional[asyncio.Task] = None
    start_retries: int = 0
    error_message: Optional[str] = None


# =============================================================================
# ModelManager 类
# 职责: 模型生命周期管理的核心类
# 设计决策:
#   1. 使用 OrderedDict 实现 LRU 缓存
#   2. 每个模型有独立的锁，防止并发操作冲突
#   3. 支持事件回调，便于扩展监控和日志
#   4. 后台健康检查循环，监控进程状态
# =============================================================================
class ModelManager:
    """模型管理器

    负责模型的加载、卸载、状态监控和资源调度。

    Attributes:
        config: 全局配置
        gpu_monitor: GPU 监控器
        models: 已加载的模型字典（LRU 顺序）
    """

    def __init__(self, config: Config, gpu_monitor: GPUMonitor):
        """初始化模型管理器

        Args:
            config: 全局配置对象
            gpu_monitor: GPU 监控器实例
        """
        self.config = config
        self.gpu_monitor = gpu_monitor
        self.proxy_config = config.proxy

        # LRU 缓存：OrderedDict 保持访问顺序
        # 最近使用的模型在字典末尾，淘汰时从头部开始
        self.models: OrderedDict[str, ModelInstance] = OrderedDict()

        # 端口分配
        self._port_counter = config.proxy.base_port
        self._used_ports: set = set()

        # 锁管理：每个模型一个锁，防止同一模型的并发操作
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

        # 事件回调：支持外部监听模型状态变化
        self._event_handlers: Dict[str, List[Callable]] = {
            'model_loaded': [],
            'model_unloaded': [],
            'model_error': [],
        }

        # 运行状态
        self._running = False
        self._health_check_task: Optional[asyncio.Task] = None

    def register_event_handler(self, event: str, handler: Callable):
        """注册事件处理器

        Args:
            event: 事件名称（model_loaded, model_unloaded, model_error）
            handler: 回调函数
        """
        if event in self._event_handlers:
            self._event_handlers[event].append(handler)

    def _emit_event(self, event: str, **kwargs):
        """触发事件

        Args:
            event: 事件名称
            **kwargs: 传递给回调函数的参数
        """
        for handler in self._event_handlers.get(event, []):
            try:
                asyncio.create_task(handler(**kwargs))
            except Exception as e:
                logger.error(f"Event handler error: {e}")

    async def start(self):
        """启动模型管理器

        初始化后台健康检查任务。
        """
        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("Model manager started")

    async def stop(self):
        """停止模型管理器

        取消后台任务，卸载所有已加载的模型。
        """
        self._running = False

        # 取消健康检查任务
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # 并行卸载所有模型
        unload_tasks = [
            self.unload_model(model_id)
            for model_id in list(self.models.keys())
        ]
        await asyncio.gather(*unload_tasks, return_exceptions=True)

        logger.info("Model manager stopped")

    async def get_model(self, model_id: str) -> Optional[ModelInstance]:
        """获取模型实例，如果不存在则创建

        这是主要的入口方法，处理以下场景:
            1. 模型已运行 -> 直接返回
            2. 模型启动中 -> 等待启动完成
            3. 模型不存在 -> 创建新实例
            4. 模型出错 -> 重试加载

        Args:
            model_id: 模型标识符

        Returns:
            模型实例，如果模型配置不存在则返回 None
        """
        # 确保有锁，防止同一模型的并发操作
        if model_id not in self._locks:
            self._locks[model_id] = asyncio.Lock()

        async with self._locks[model_id]:
            # 检查是否已存在
            if model_id in self.models:
                model = self.models[model_id]

                if model.status == ModelStatus.RUNNING:
                    # 模型已运行，更新访问时间并返回
                    self._touch_model(model_id)
                    return model

                elif model.status == ModelStatus.STARTING:
                    # 模型正在启动，等待启动完成
                    logger.info(f"Model {model_id} is starting, waiting...")
                    return await self._wait_for_model_ready(model_id)

                elif model.status == ModelStatus.ERROR:
                    # 之前启动失败，尝试重新加载
                    logger.warning(f"Model {model_id} was in error state, retrying...")
                    return await self._create_model(model_id)

            # 创建新实例
            return await self._create_model(model_id)

    async def _create_model(self, model_id: str) -> Optional[ModelInstance]:
        """创建新模型实例

        Args:
            model_id: 模型标识符

        Returns:
            新创建的模型实例

        Raises:
            RuntimeError: 如果显存不足
        """
        # 查找模型配置
        model_config = None
        for mid, cfg in self.config.models.items():
            if mid == model_id:
                model_config = cfg
                break

        if not model_config:
            logger.error(f"Model config not found: {model_id}")
            return None

        # 计算显存需求
        gpu_memory_mb = model_config.explicit_memory_mb or self.gpu_monitor.predict_memory_need(
            param_count=model_config.param_count,
            precision=model_config.precision,
            max_model_len=model_config.max_model_len,
            max_num_seqs=model_config.max_num_seqs,
            num_layers=model_config.num_layers,
            hidden_size=model_config.hidden_size,
            num_attention_heads=model_config.num_attention_heads,
            num_kv_heads=model_config.num_kv_heads,
        )

        logger.info(f"Creating model {model_id}, estimated GPU memory: {gpu_memory_mb}MB")

        # 确保有足够显存（必要时淘汰空闲模型）
        if not await self._ensure_memory_available(gpu_memory_mb):
            raise RuntimeError(
                f"Cannot allocate {gpu_memory_mb}MB for model {model_id}, "
                f"insufficient GPU memory"
            )

        # 创建实例
        model = ModelInstance(
            model_id=model_id,
            config=model_config,
            gpu_memory_mb=gpu_memory_mb,
            port=self._allocate_port()
        )

        self.models[model_id] = model
        model.status = ModelStatus.STARTING

        # 最大端口重试次数
        max_port_retries = 10
        port_retry_count = 0

        while True:
            try:
                # 启动 vLLM 进程
                await self._start_vllm_process(model)

                # 等待就绪
                await self._wait_for_model_ready(model_id)

                # 启动空闲计时器（自动卸载空闲模型）
                model.idle_timer = asyncio.create_task(
                    self._idle_watcher(model_id)
                )

                self._emit_event('model_loaded', model_id=model_id, port=model.port)
                logger.info(f"Model {model_id} is ready on port {model.port}")

                return model

            except Exception as e:
                error_msg = str(e).lower()

                # 检查是否是端口相关的错误
                is_port_error = (
                    'address already in use' in error_msg or
                    'port' in error_msg and 'in use' in error_msg or
                    'bind' in error_msg or
                    'timeout' in error_msg  # 启动超时也可能是端口问题
                )

                if is_port_error and port_retry_count < max_port_retries:
                    port_retry_count += 1
                    logger.warning(
                        f"Model {model_id} failed to start on port {model.port} "
                        f"(attempt {port_retry_count}/{max_port_retries}): {e}"
                    )

                    # 释放当前端口并分配新端口
                    self._release_port(model.port)
                    old_port = model.port
                    model.port = self._allocate_port()
                    logger.info(f"Retrying with new port: {old_port} -> {model.port}")

                    # 如果进程已启动，先停止它
                    if model.process:
                        try:
                            model.process.kill()
                            await model.process.wait()
                        except Exception:
                            pass
                        model.process = None

                    continue  # 重试

                # 非端口错误或超过重试次数
                model.status = ModelStatus.ERROR
                model.error_message = str(e)
                logger.error(f"Failed to create model {model_id}: {e}")
                self._emit_event('model_error', model_id=model_id, error=str(e))
                raise

    async def _ensure_memory_available(self, required_mb: int) -> bool:
        """确保有足够显存

        如果当前显存不足，淘汰空闲模型以释放空间。

        Args:
            required_mb: 需要的显存（MB）

        Returns:
            True 如果显存已足够
        """
        # 快速检查：如果当前可用显存已足够，直接返回
        if self.gpu_monitor.can_fit_model(required_mb):
            return True

        logger.info(f"Need to free memory for {required_mb}MB")

        # 准备当前模型信息（用于计算淘汰计划）
        current_models = [
            (mid, m.gpu_memory_mb, m.request_count, m.last_used_at.timestamp())
            for mid, m in self.models.items()
            if m.status == ModelStatus.RUNNING
        ]

        # 计算淘汰计划（基于 LRU 策略）
        to_evict = self.gpu_monitor.calculate_eviction_plan(required_mb, current_models)

        if not to_evict:
            logger.error("No idle models to evict")
            return False

        # 执行淘汰
        logger.info(f"Evicting models to free memory: {to_evict}")
        for evict_id in to_evict:
            await self.unload_model(evict_id)

        # 再次检查显存是否足够
        return self.gpu_monitor.can_fit_model(required_mb)

    async def _start_vllm_process(self, model: ModelInstance):
        """启动 vLLM 服务进程

        构建命令行参数并启动 vLLM 的 OpenAI API 服务器。

        Args:
            model: 模型实例
        """
        cfg = model.config

        # 计算实际可用的显存利用率
        # vLLM 的 --gpu-memory-utilization 是相对于 GPU 总显存的比例
        # 需要减去预留显存，计算出实际应该使用的比例
        gpu_total_mb = self.gpu_monitor.get_memory_info().total_mb
        reserved_mb = self.config.gpu.reserved_memory_mb
        config_utilization = self.config.gpu.memory_utilization

        # 实际可用显存 = 总显存 - 预留显存
        usable_mb = gpu_total_mb - reserved_mb
        # 计算实际应该使用的显存比例
        actual_utilization = (usable_mb * config_utilization) / gpu_total_mb
        actual_utilization = min(actual_utilization, 1.0)  # 确保不超过 1.0

        logger.info(f"GPU memory calculation: total={gpu_total_mb}MB, reserved={reserved_mb}MB, "
                    f"usable={usable_mb}MB, config_utilization={config_utilization}, "
                    f"actual_utilization={actual_utilization:.3f}")

        # 构建 vLLM 启动命令 - 使用当前 Python 解释器
        cmd = [
            sys.executable, "-m", "vllm.entrypoints.openai.api_server",
            "--host", "0.0.0.0",
            "--model", cfg.model_path,
            "--port", str(model.port),
            "--served-model-name", model.model_id,  # 使用配置中的 model_id 作为服务名称
            "--tensor-parallel-size", str(cfg.tensor_parallel),
            "--max-model-len", str(cfg.max_model_len),
            "--max-num-seqs", str(cfg.max_num_seqs),
            "--dtype", cfg.precision if cfg.precision not in ["fp32", "fp16", "bf16"] else {
                "fp32": "float32",
                "fp16": "float16",
                "bf16": "bfloat16"
            }.get(cfg.precision, "auto"),
            "--gpu-memory-utilization", f"{actual_utilization:.3f}",
        ]

        # 量化配置
        if cfg.quantization:
            cmd.extend(["--quantization", cfg.quantization])

        # enforce-eager 配置（禁用 CUDA graph，某些模型如 Qwen3-AWQ 需要）
        if cfg.enforce_eager:
            cmd.append("--enforce-eager")

        # 额外参数透传（支持任意 vLLM 参数）
        if cfg.extra_args:
            cmd.extend(cfg.extra_args)

        # 模型下载目录
        cmd.extend(["--download-dir", "/tmp/vllm_models"])

        logger.info(f"Starting vLLM: {' '.join(cmd)}")

        # 准备环境变量
        env = os.environ.copy()
        if cfg.api_key:
            # HuggingFace Token（用于访问受保护的模型）
            env['HF_TOKEN'] = cfg.api_key
            env['HUGGING_FACE_HUB_TOKEN'] = cfg.api_key

        # 启动子进程
        model.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        # 启动日志收集任务
        asyncio.create_task(self._collect_logs(model))

    async def _collect_logs(self, model: ModelInstance):
        """收集 vLLM 进程日志

        将 vLLM 的 stdout 和 stderr 输出到代理服务的日志中。

        Args:
            model: 模型实例
        """
        if not model.process:
            return

        async def read_stream(stream, prefix):
            """读取流并输出日志"""
            while True:
                try:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode('utf-8', errors='replace').rstrip()
                    if decoded:
                        logger.info(f"[{model.model_id}] {prefix}: {decoded}")
                except Exception:
                    break

        # 并行读取 stdout 和 stderr
        await asyncio.gather(
            read_stream(model.process.stdout, "OUT"),
            read_stream(model.process.stderr, "ERR")
        )

    async def _wait_for_model_ready(self, model_id: str, timeout: float = None) -> ModelInstance:
        """等待模型就绪

        轮询模型的健康检查端点，直到服务就绪或超时。

        Args:
            model_id: 模型标识符
            timeout: 超时时间（秒）

        Returns:
            就绪的模型实例

        Raises:
            TimeoutError: 如果超时
            RuntimeError: 如果进程意外退出
        """
        timeout = timeout or self.proxy_config.start_timeout_seconds
        model = self.models[model_id]
        url = f"http://localhost:{model.port}/health"

        start_time = time.time()
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    async with session.get(url, timeout=5) as resp:
                        if resp.status == 200:
                            model.status = ModelStatus.RUNNING
                            return model
                except Exception:
                    pass

                # 检查是否超时
                if time.time() - start_time > timeout:
                    model.status = ModelStatus.ERROR
                    model.error_message = "Start timeout"
                    raise TimeoutError(f"Model {model_id} failed to start within {timeout}s")

                # 检查进程是否已退出
                if model.process and model.process.returncode is not None:
                    model.status = ModelStatus.ERROR
                    model.error_message = f"Process exited with code {model.process.returncode}"
                    raise RuntimeError(f"vLLM process for {model_id} exited unexpectedly")

                await asyncio.sleep(1)

    async def unload_model(self, model_id: str) -> bool:
        """卸载模型

        停止 vLLM 进程并清理资源。

        Args:
            model_id: 模型标识符

        Returns:
            True 如果卸载成功
        """
        if model_id not in self.models:
            return False

        async with self._locks.get(model_id, asyncio.Lock()):
            model = self.models[model_id]

            # 检查是否已在停止中
            if model.status in [ModelStatus.STOPPING, ModelStatus.STOPPED, ModelStatus.EVICTING]:
                return True

            # 如果有活跃请求，等待完成
            if model.request_count > 0:
                logger.warning(
                    f"Model {model_id} has {model.request_count} active requests, "
                    "waiting for completion"
                )
                # 最多等待 30 秒
                for _ in range(30):
                    if model.request_count == 0:
                        break
                    await asyncio.sleep(1)

            model.status = ModelStatus.STOPPING

            # 取消空闲计时器
            if model.idle_timer:
                model.idle_timer.cancel()
                try:
                    await model.idle_timer
                except asyncio.CancelledError:
                    pass

            # 停止进程
            await self._stop_vllm_process(model)

            # 清理资源
            self._release_port(model.port)
            del self.models[model_id]

            self._emit_event('model_unloaded', model_id=model_id)
            logger.info(f"Model {model_id} unloaded")

            return True

    async def _stop_vllm_process(self, model: ModelInstance):
        """优雅停止 vLLM 进程

        先发送 SIGTERM，如果超时则发送 SIGKILL。

        Args:
            model: 模型实例
        """
        if not model.process:
            return

        pid = model.process.pid
        logger.info(f"Stopping vLLM process {pid} for model {model.model_id}")

        try:
            # 发送 SIGTERM（优雅终止）
            model.process.send_signal(signal.SIGTERM)

            # 等待进程结束
            try:
                await asyncio.wait_for(
                    model.process.wait(),
                    timeout=self.proxy_config.stop_timeout_seconds
                )
                logger.info(f"Process {pid} terminated gracefully")
            except asyncio.TimeoutError:
                # 超时后强制终止
                logger.warning(f"Process {pid} did not terminate, killing...")
                model.process.kill()
                await model.process.wait()
                logger.info(f"Process {pid} killed")

        except ProcessLookupError:
            logger.info(f"Process {pid} already exited")
        except Exception as e:
            logger.error(f"Error stopping process {pid}: {e}")

    async def _idle_watcher(self, model_id: str):
        """监控模型空闲状态

        当模型空闲超过配置的超时时间时，自动卸载。

        Args:
            model_id: 模型标识符
        """
        while True:
            try:
                await asyncio.sleep(self.proxy_config.idle_timeout_seconds)

                model = self.models.get(model_id)
                if not model:
                    return

                idle_time = (datetime.now() - model.last_used_at).total_seconds()

                # 检查是否空闲超时
                if model.request_count == 0 and idle_time >= self.proxy_config.idle_timeout_seconds:
                    logger.info(
                        f"Model {model_id} idle for {idle_time:.0f}s, "
                        "initiating eviction"
                    )
                    await self.unload_model(model_id)
                    return

            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(f"Idle watcher error for {model_id}: {e}")
                await asyncio.sleep(10)

    async def _health_check_loop(self):
        """健康检查循环

        定期检查已加载模型的进程状态。
        """
        while self._running:
            try:
                await asyncio.sleep(self.proxy_config.health_check_interval)

                for model_id, model in list(self.models.items()):
                    if model.status != ModelStatus.RUNNING:
                        continue

                    # 检查进程是否存活
                    if model.process and model.process.returncode is not None:
                        logger.error(
                            f"Model {model_id} process exited unexpectedly, "
                            f"code: {model.process.returncode}"
                        )
                        model.status = ModelStatus.ERROR
                        self._emit_event('model_error', model_id=model_id, error="Process crashed")

            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(f"Health check error: {e}")

    def acquire_model(self, model_id: str) -> Optional[ModelInstance]:
        """获取模型引用

        增加请求计数，表示模型正在被使用。

        Args:
            model_id: 模型标识符

        Returns:
            模型实例，如果模型不可用则返回 None
        """
        model = self.models.get(model_id)
        if model and model.status == ModelStatus.RUNNING:
            model.request_count += 1
            model.total_requests += 1
            model.last_used_at = datetime.now()
            self._touch_model(model_id)
            return model
        return None

    def release_model(self, model_id: str):
        """释放模型引用

        减少请求计数，表示请求已完成。

        Args:
            model_id: 模型标识符
        """
        model = self.models.get(model_id)
        if model:
            model.request_count = max(0, model.request_count - 1)

    def _touch_model(self, model_id: str):
        """更新模型访问时间（LRU）

        将模型移动到 OrderedDict 末尾，表示最近使用。

        Args:
            model_id: 模型标识符
        """
        if model_id in self.models:
            model = self.models.pop(model_id)
            model.last_used_at = datetime.now()
            self.models[model_id] = model

    def _is_port_available(self, port: int) -> bool:
        """检查端口是否可用

        Args:
            port: 端口号

        Returns:
            True 如果端口可用（未被占用）
        """
        # 检查是否已被本服务使用
        if port in self._used_ports:
            return False

        # 检查端口是否被系统其他程序占用
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('127.0.0.1', port))
                # 如果连接失败（端口未被监听），则端口可用
                return result != 0
        except Exception:
            # 出现异常时假设端口可用
            return True

    def _allocate_port(self) -> int:
        """分配端口

        从起始端口开始，找到未被占用的端口。
        如果端口被其他程序占用，自动尝试下一个端口。

        Returns:
            分配的端口号
        """
        max_attempts = 1000  # 最大尝试次数，防止无限循环
        attempts = 0

        while attempts < max_attempts:
            port = self._port_counter
            self._port_counter += 1
            attempts += 1

            # 检查端口是否可用
            if self._is_port_available(port):
                self._used_ports.add(port)
                logger.debug(f"Allocated port {port}")
                return port
            else:
                logger.debug(f"Port {port} is not available, trying next")

        # 如果尝试了太多端口仍未找到可用的，抛出异常
        raise RuntimeError(f"Cannot find available port after {max_attempts} attempts")

    def _release_port(self, port: int):
        """释放端口

        Args:
            port: 要释放的端口号
        """
        self._used_ports.discard(port)

    def get_model_status(self, model_id: str = None) -> Dict:
        """获取模型状态

        Args:
            model_id: 模型标识符，为 None 时返回所有模型状态

        Returns:
            模型状态字典
        """
        if model_id:
            model = self.models.get(model_id)
            if not model:
                return None
            return self._model_to_dict(model)

        return {
            mid: self._model_to_dict(m)
            for mid, m in self.models.items()
        }

    def _model_to_dict(self, model: ModelInstance) -> Dict:
        """转换模型信息为字典

        Args:
            model: 模型实例

        Returns:
            包含模型状态的字典
        """
        return {
            "model_id": model.model_id,
            "status": model.status.value,
            "port": model.port,
            "gpu_memory_mb": model.gpu_memory_mb,
            "request_count": model.request_count,
            "total_requests": model.total_requests,
            "created_at": model.created_at.isoformat(),
            "last_used_at": model.last_used_at.isoformat(),
            "idle_seconds": (datetime.now() - model.last_used_at).total_seconds(),
            "error_message": model.error_message,
            "config": {
                "model_path": model.config.model_path,
                "param_count": model.config.param_count,
                "precision": model.config.precision,
            }
        }

    def list_models(self) -> List[str]:
        """列出所有已配置的模型

        Returns:
            模型标识符列表
        """
        return list(self.config.models.keys())
