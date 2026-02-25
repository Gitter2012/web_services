# =============================================================================
# 模块: proxy/gpu_monitor.py
# 功能: GPU 监控模块，负责显存监控、使用率统计和容量规划
# 架构角色: 资源管理的核心组件。通过 NVML 库获取 GPU 实时状态，
#           为模型管理器提供显存可用性判断和模型淘汰决策支持。
# 设计理念: 封装 NVML 复杂的 API，提供简洁的接口；支持无 GPU 环境的模拟模式，
#           便于开发和测试；通过算法估算模型显存需求，支持智能资源调度。
# =============================================================================

"""GPU 监控模块

负责显存监控、使用率统计和容量规划
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

try:
    import pynvml
    NVML_AVAILABLE = True
except ImportError:
    NVML_AVAILABLE = False
    logging.warning("pynvml not available, GPU monitoring will be limited")

# 模块级日志器，用于记录 GPU 监控相关的操作日志
logger = logging.getLogger(__name__)


# =============================================================================
# MemoryInfo 数据类
# 职责: 封装 GPU 显存信息
# 设计决策:
#   1. 使用 dataclass 简化数据传递
#   2. 区分 free（物理空闲）和 available（考虑预留后的可用）
# =============================================================================
@dataclass
class MemoryInfo:
    """显存信息

    Attributes:
        total_mb: GPU 总显存（MB）
        used_mb: 已使用显存（MB）
        free_mb: 物理空闲显存（MB）
        available_mb: 可用显存（MB），考虑预留缓冲后的值
    """

    total_mb: int
    used_mb: int
    free_mb: int
    available_mb: int  # 考虑预留缓冲后的可用显存


# =============================================================================
# GPUStats 数据类
# 职责: 封装完整的 GPU 统计信息
# 设计决策:
#   1. 包含温度、利用率、功耗等关键指标
#   2. 嵌套 MemoryInfo，便于一次性获取所有信息
# =============================================================================
@dataclass
class GPUStats:
    """GPU 统计信息

    Attributes:
        gpu_id: GPU 设备 ID
        name: GPU 设备名称（如 "NVIDIA A100-SXM4-80GB"）
        temperature: GPU 温度（摄氏度）
        utilization_percent: GPU 利用率（百分比）
        memory: 显存信息
        power_draw_w: 当前功耗（瓦）
        power_limit_w: 功耗上限（瓦）
    """

    gpu_id: int
    name: str
    temperature: float
    utilization_percent: float
    memory: MemoryInfo
    power_draw_w: float
    power_limit_w: float


# =============================================================================
# GPUMonitor 类
# 职责: GPU 资源监控的核心类
# 设计决策:
#   1. 使用 NVML 库获取 GPU 状态，支持 NVIDIA GPU
#   2. 无 NVML 时提供模拟数据，保证代码可测试
#   3. 提供显存预测算法，帮助判断能否加载特定模型
#   4. 实现 LRU 淘汰策略计算，支持智能资源释放
# =============================================================================
class GPUMonitor:
    """GPU 监控器

    提供 GPU 状态查询、显存预测和模型淘汰决策支持。

    Attributes:
        gpu_id: 监控的 GPU 设备 ID
        reserved_memory_mb: 预留显存缓冲（MB），防止显存耗尽
    """

    def __init__(self, gpu_id: int = 0, reserved_memory_mb: int = 2048):
        """初始化 GPU 监控器

        Args:
            gpu_id: 要监控的 GPU 设备 ID（默认: 0）
            reserved_memory_mb: 预留显存缓冲区大小（MB），默认 2GB
        """
        self.gpu_id = gpu_id
        self.reserved_memory_mb = reserved_memory_mb
        self._initialized = False
        self._handle = None

        # 初始化 NVML 库
        if NVML_AVAILABLE:
            try:
                pynvml.nvmlInit()
                self._handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_id)
                self._initialized = True
                logger.info(f"GPU monitor initialized for GPU {gpu_id}")
            except Exception as e:
                logger.error(f"Failed to initialize GPU monitor: {e}")

    def is_available(self) -> bool:
        """检查 GPU 监控是否可用

        Returns:
            True 如果 NVML 已成功初始化
        """
        return self._initialized

    def get_memory_info(self) -> MemoryInfo:
        """获取显存信息

        Returns:
            MemoryInfo 实例，包含显存的各项指标
        """
        if not self._initialized:
            # 模拟数据，用于无 GPU 的测试环境
            return MemoryInfo(
                total_mb=24576,
                used_mb=4096,
                free_mb=20480,
                available_mb=20480 - self.reserved_memory_mb
            )

        try:
            info = pynvml.nvmlDeviceGetMemoryInfo(self._handle)
            total_mb = info.total // 1024 // 1024
            used_mb = info.used // 1024 // 1024
            free_mb = info.free // 1024 // 1024

            # available = free - reserved，确保不为负
            return MemoryInfo(
                total_mb=total_mb,
                used_mb=used_mb,
                free_mb=free_mb,
                available_mb=max(0, free_mb - self.reserved_memory_mb)
            )
        except Exception as e:
            logger.error(f"Failed to get memory info: {e}")
            raise

    def get_stats(self) -> GPUStats:
        """获取完整的 GPU 统计信息

        Returns:
            GPUStats 实例，包含 GPU 的所有状态指标
        """
        if not self._initialized:
            # 模拟数据，用于无 GPU 的测试环境
            return GPUStats(
                gpu_id=self.gpu_id,
                name="Mock GPU",
                temperature=45.0,
                utilization_percent=30.0,
                memory=self.get_memory_info(),
                power_draw_w=100.0,
                power_limit_w=250.0
            )

        try:
            # 获取 GPU 名称
            name = pynvml.nvmlDeviceGetName(self._handle)
            if isinstance(name, bytes):
                name = name.decode('utf-8')

            # 获取温度
            temperature = pynvml.nvmlDeviceGetTemperature(
                self._handle, pynvml.NVML_TEMPERATURE_GPU
            )

            # 获取利用率
            utilization = pynvml.nvmlDeviceGetUtilizationRates(self._handle)

            # 获取功耗（NVML 返回毫瓦，转换为瓦）
            power_draw = pynvml.nvmlDeviceGetPowerUsage(self._handle) / 1000.0
            power_limit = pynvml.nvmlDeviceGetEnforcedPowerLimit(self._handle) / 1000.0

            return GPUStats(
                gpu_id=self.gpu_id,
                name=name,
                temperature=temperature,
                utilization_percent=utilization.gpu,
                memory=self.get_memory_info(),
                power_draw_w=power_draw,
                power_limit_w=power_limit
            )
        except Exception as e:
            logger.error(f"Failed to get GPU stats: {e}")
            raise

    def can_fit_model(self, required_mb: int) -> bool:
        """检查是否有足够显存容纳指定模型

        Args:
            required_mb: 模型所需显存（MB）

        Returns:
            True 如果可用显存足够
        """
        available = self.get_memory_info().available_mb
        return available >= required_mb

    def predict_memory_need(
        self,
        param_count: float,  # 参数数量（B）
        precision: str = "fp16",
        max_model_len: int = 4096,
        max_num_seqs: int = 16,
        num_layers: int = 32,
        hidden_size: int = 4096,
        num_attention_heads: int = 32,
        num_kv_heads: int = 8,
        explicit_memory_mb: Optional[int] = None
    ) -> int:
        """预测模型显存需求

        根据模型参数和配置估算显存占用。

        计算公式:
            1. 模型权重 = 参数量 × 精度字节数
            2. KV Cache = 2 × num_layers × batch_size × seq_len × num_kv_heads × head_size × 2
            3. 激活值和工作内存（经验值 1-2GB）
            4. 额外开销（CUDA context、缓存等）

        Args:
            param_count: 参数数量（单位：B）
            precision: 精度格式（fp32=4B, fp16=2B, bf16=2B, int8=1B, int4=0.5B）
            max_model_len: 最大上下文长度
            max_num_seqs: 最大并发序列数
            num_layers: 层数
            hidden_size: 隐藏层大小
            num_attention_heads: 注意力头数
            num_kv_heads: KV 头数（用于 GQA）
            explicit_memory_mb: 显式指定显存需求，跳过自动计算

        Returns:
            预估显存需求（MB）
        """
        # 如果显式指定了显存需求，直接返回
        if explicit_memory_mb is not None:
            return explicit_memory_mb

        # 精度映射：每个参数占用的字节数
        precision_map = {
            "fp32": 4,
            "fp16": 2,
            "bf16": 2,
            "int8": 1,
            "int4": 0.5
        }
        bytes_per_param = precision_map.get(precision, 2)

        # 1. 模型权重显存
        # 权重占用 = 参数量 × 每个参数字节数
        model_weights_mb = param_count * 1e9 * bytes_per_param / 1024 / 1024

        # 2. KV Cache 显存
        # KV Cache 用于存储注意力计算的 Key 和 Value
        # 大小 = 2(K和V) × 层数 × batch_size × seq_len × KV头数 × head_size × 2(fp16)
        head_size = hidden_size // num_attention_heads
        kv_cache_mb = (
            2 * num_layers * max_num_seqs * max_model_len *
            num_kv_heads * head_size * 2 / 1024 / 1024
        )

        # 3. 激活值和工作内存（经验值估算）
        # 与 batch size、序列长度相关
        activation_mb = 512 + (max_num_seqs * max_model_len * hidden_size * 2 / 1024 / 1024)

        # 4. 额外开销（CUDA context、框架缓存等）
        overhead_mb = 512

        total_mb = int(model_weights_mb + kv_cache_mb + activation_mb + overhead_mb)

        logger.debug(
            f"Memory prediction for {param_count}B model: "
            f"weights={model_weights_mb:.0f}MB, "
            f"kv_cache={kv_cache_mb:.0f}MB, "
            f"activation={activation_mb:.0f}MB, "
            f"total={total_mb}MB"
        )

        return total_mb

    def calculate_eviction_plan(
        self,
        required_mb: int,
        current_models: List[Tuple[str, int, int, float]]
    ) -> List[str]:
        """计算需要淘汰的模型列表

        当显存不足时，根据 LRU 策略计算需要卸载的模型。

        Args:
            required_mb: 需要的显存（MB）
            current_models: 当前加载的模型列表，每项为
                (model_id, memory_mb, ref_count, last_access_time)
                - model_id: 模型标识
                - memory_mb: 占用显存
                - ref_count: 当前引用计数（活跃请求数）
                - last_access_time: 最后访问时间戳

        Returns:
            需要淘汰的 model_id 列表
        """
        available_mb = self.get_memory_info().free_mb
        need_to_free = required_mb - available_mb + self.reserved_memory_mb

        # 如果当前空闲显存已足够，无需淘汰
        if need_to_free <= 0:
            return []

        # 只考虑空闲模型（ref_count == 0），不能淘汰正在处理请求的模型
        idle_models = [
            (mid, mem, last_access)
            for mid, mem, ref_count, last_access in current_models
            if ref_count == 0
        ]

        # 按最后访问时间排序（LRU：最久未使用的排前面）
        idle_models.sort(key=lambda x: x[2])

        to_evict = []
        freed_mb = 0

        # 依次选择最久未使用的空闲模型进行淘汰
        for model_id, memory_mb, _ in idle_models:
            if freed_mb >= need_to_free:
                break
            to_evict.append(model_id)
            freed_mb += memory_mb

        # 如果释放的显存仍不足，记录警告
        if freed_mb < need_to_free:
            logger.warning(
                f"Cannot free enough memory: need {need_to_free}MB, "
                f"can free {freed_mb}MB"
            )
            # 仍然返回可以释放的模型，让上层决定是否继续

        return to_evict

    async def wait_for_memory(
        self,
        required_mb: int,
        timeout_seconds: float = 60.0,
        check_interval: float = 1.0
    ) -> bool:
        """等待显存可用

        异步等待，直到有足够的显存或超时。
        用于在显存紧张时排队等待。

        Args:
            required_mb: 需要的显存（MB）
            timeout_seconds: 最长等待时间（秒）
            check_interval: 检查间隔（秒）

        Returns:
            True 如果在超时前获得足够显存，False 表示超时
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            if self.can_fit_model(required_mb):
                return True

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout_seconds:
                return False

            await asyncio.sleep(check_interval)

    def get_process_memory(self, pid: int) -> int:
        """获取指定进程的显存占用

        Args:
            pid: 进程 ID

        Returns:
            进程占用的显存（MB）
        """
        if not self._initialized:
            return 0

        try:
            # 获取所有使用 GPU 的进程
            processes = pynvml.nvmlDeviceGetComputeRunningProcesses(self._handle)
            for proc in processes:
                if proc.pid == pid:
                    # usedGpuMemory 返回字节数，转换为 MB
                    return proc.usedGpuMemory // 1024 // 1024 if hasattr(proc, 'usedGpuMemory') else 0
            return 0
        except Exception as e:
            logger.error(f"Failed to get process memory: {e}")
            return 0

    def shutdown(self):
        """关闭 GPU 监控器

        释放 NVML 资源。应在程序退出前调用。
        """
        if self._initialized and NVML_AVAILABLE:
            try:
                pynvml.nvmlShutdown()
                logger.info("GPU monitor shutdown")
            except Exception as e:
                logger.error(f"Error shutting down GPU monitor: {e}")
