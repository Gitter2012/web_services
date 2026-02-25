# =============================================================================
# 模块: proxy/config.py
# 功能: 配置管理模块，负责加载和管理 vLLM Proxy 服务的配置
# 架构角色: 服务配置的核心管理器。提供配置的数据结构定义和多源配置加载能力，
#           支持 YAML 文件配置、环境变量配置及默认配置，并按照优先级进行合并。
# 设计理念: 通过 dataclass 定义类型安全的配置结构，支持配置的分层覆盖，
#           使服务能灵活适应不同的部署环境（开发、测试、生产）。
# =============================================================================

"""配置管理模块"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml


# =============================================================================
# GPUConfig 数据类
# 职责: 定义 GPU 相关的配置参数
# 设计决策:
#   1. 使用 dataclass 简化初始化和比较操作
#   2. 提供合理的默认值，使最小配置即可运行
# =============================================================================
@dataclass
class GPUConfig:
    """GPU 配置

    Attributes:
        gpu_id: 使用的 GPU 设备 ID（默认: 0）
        reserved_memory_mb: 预留显存缓冲区大小（MB），防止显存耗尽（默认: 2048）
        memory_utilization: vLLM 进程的显存利用率（默认: 0.9）
    """

    gpu_id: int = 0
    reserved_memory_mb: int = 2048  # 预留显存缓冲，避免 OOM
    memory_utilization: float = 0.9  # vLLM 显存利用率，0.9 表示使用 90% 的可用显存


# =============================================================================
# ModelConfig 数据类
# 职责: 定义单个模型的配置参数
# 设计决策:
#   1. 包含模型加载所需的全部参数（路径、精度、显存等）
#   2. 支持量化配置（awq, gptq, squeezellm）
#   3. 允许显式指定显存需求，覆盖自动估算
# =============================================================================
@dataclass
class ModelConfig:
    """模型配置

    Attributes:
        model_id: 模型唯一标识符
        model_path: HuggingFace model_id 或本地路径
        param_count: 参数数量（单位：B），用于显存估算
        precision: 精度格式（fp32, fp16, bf16, int8, int4）
        tensor_parallel: 张量并行度
        max_model_len: 最大上下文长度
        max_num_seqs: 最大并发序列数
        quantization: 量化方法（awq, gptq, squeezellm）
        num_layers: 层数，用于 KV Cache 显存估算
        hidden_size: 隐藏层大小
        num_attention_heads: 注意力头数
        num_kv_heads: KV 头数（GQA）
        explicit_memory_mb: 显式指定显存需求（MB），覆盖自动计算
        api_key: 访问受保护模型所需的 API Key（如 HuggingFace Token）
    """

    model_id: str = ""
    model_path: str = ""  # HuggingFace model_id 或本地路径
    param_count: float = 7.0  # 参数数量（B）
    precision: str = "fp16"  # fp32, fp16, bf16, int8, int4
    tensor_parallel: int = 1
    max_model_len: int = 4096
    max_num_seqs: int = 16
    quantization: Optional[str] = None  # awq, gptq, squeezellm
    enforce_eager: bool = False  # 禁用 CUDA graph，某些模型需要
    num_layers: int = 32
    hidden_size: int = 4096
    num_attention_heads: int = 32
    num_kv_heads: int = 8
    # 显式指定显存需求（MB），覆盖自动计算
    explicit_memory_mb: Optional[int] = None
    # API Key 配置（用于访问受保护的模型）
    api_key: Optional[str] = None  # HuggingFace Token 或其他 API Key
    # 额外的 vLLM 命令行参数，支持任意 vLLM 参数透传
    # 格式: ["--arg1", "value1", "--arg2", "value2"]
    # 例如: ["--trust-remote-code", "--enable-prefix-caching"]
    extra_args: List[str] = field(default_factory=list)


# =============================================================================
# ProxyConfig 数据类
# 职责: 定义代理服务的网络和运行参数
# 设计决策:
#   1. 包含服务监听地址、端口分配范围
#   2. 定义空闲超时和健康检查间隔
#   3. 支持可选的 API Key 认证，与 vLLM/OpenAI 兼容
# =============================================================================
@dataclass
class ProxyConfig:
    """代理服务配置

    Attributes:
        host: 服务监听地址（默认: 0.0.0.0）
        port: 服务监听端口（默认: 8080）
        base_port: vLLM 进程起始端口，每个模型分配一个端口
        idle_timeout_seconds: 模型空闲超时时间（秒），超时后自动卸载
        health_check_interval: 健康检查间隔（秒）
        max_start_retries: 模型启动最大重试次数
        start_timeout_seconds: 模型启动超时时间（秒）
        stop_timeout_seconds: 模型停止超时时间（秒）
        api_key: API Key 认证（可选），与 vLLM/OpenAI 兼容格式
    """

    host: str = "0.0.0.0"
    port: int = 8080
    base_port: int = 8000  # vLLM 进程起始端口
    idle_timeout_seconds: int = 300  # 空闲超时时间
    health_check_interval: int = 10
    max_start_retries: int = 3
    start_timeout_seconds: int = 120
    stop_timeout_seconds: int = 30
    # API Key 认证配置（与 vLLM/OpenAI 兼容格式）
    # 如果设置，请求需要在 Header 中提供: Authorization: Bearer <api_key>
    api_key: Optional[str] = None


# =============================================================================
# LoggingConfig 数据类
# 职责: 定义日志输出的配置参数
# 设计决策:
#   1. 支持日志文件轮转，避免日志文件过大
#   2. 可配置日志级别和格式
# =============================================================================
@dataclass
class LoggingConfig:
    """日志配置

    Attributes:
        level: 日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）
        format: 日志格式字符串
        file: 日志文件路径（None 表示不输出到文件）
        max_bytes: 单个日志文件最大大小（字节）
        backup_count: 保留的历史日志文件数量
    """

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: Optional[str] = "logs/vllm_proxy.log"
    max_bytes: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5


# =============================================================================
# Config 数据类
# 职责: 总配置容器，聚合所有子配置
# 设计决策:
#   1. 使用组合模式聚合 GPU、代理、日志和模型配置
#   2. 提供 from_yaml() 和 from_env() 工厂方法，支持多源加载
#   3. merge() 方法实现配置覆盖，环境变量优先级最高
# =============================================================================
@dataclass
class Config:
    """总配置

    Attributes:
        gpu: GPU 配置
        proxy: 代理服务配置
        logging: 日志配置
        models: 模型配置字典，key 为 model_id
    """

    gpu: GPUConfig = field(default_factory=GPUConfig)
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    models: Dict[str, ModelConfig] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        """从 YAML 文件加载配置

        Args:
            path: YAML 配置文件路径

        Returns:
            加载后的 Config 实例
        """
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        config = cls()

        # 解析 GPU 配置
        if 'gpu' in data:
            config.gpu = GPUConfig(**data['gpu'])

        # 解析代理配置
        if 'proxy' in data:
            config.proxy = ProxyConfig(**data['proxy'])

        # 解析日志配置
        if 'logging' in data:
            config.logging = LoggingConfig(**data['logging'])

        # 解析模型配置（每个模型有独立的配置块）
        if 'models' in data:
            for model_id, model_data in data['models'].items():
                config.models[model_id] = ModelConfig(model_id=model_id, **model_data)

        return config

    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量加载配置

        环境变量优先级高于配置文件，用于容器化部署场景。

        支持的环境变量:
            GPU_ID: GPU 设备 ID
            RESERVED_MEMORY_MB: 预留显存（MB）
            GPU_MEMORY_UTILIZATION: 显存利用率
            PROXY_HOST: 服务监听地址
            PROXY_PORT: 服务监听端口
            BASE_PORT: vLLM 起始端口
            IDLE_TIMEOUT: 空闲超时（秒）
            LOG_LEVEL: 日志级别
            LOG_FILE: 日志文件路径

        Returns:
            从环境变量加载的 Config 实例
        """
        config = cls()

        # GPU 配置
        if os.getenv('GPU_ID'):
            config.gpu.gpu_id = int(os.getenv('GPU_ID'))
        if os.getenv('RESERVED_MEMORY_MB'):
            config.gpu.reserved_memory_mb = int(os.getenv('RESERVED_MEMORY_MB'))
        if os.getenv('GPU_MEMORY_UTILIZATION'):
            config.gpu.memory_utilization = float(os.getenv('GPU_MEMORY_UTILIZATION'))

        # 代理配置
        if os.getenv('PROXY_HOST'):
            config.proxy.host = os.getenv('PROXY_HOST')
        if os.getenv('PROXY_PORT'):
            config.proxy.port = int(os.getenv('PROXY_PORT'))
        if os.getenv('BASE_PORT'):
            config.proxy.base_port = int(os.getenv('BASE_PORT'))
        if os.getenv('IDLE_TIMEOUT'):
            config.proxy.idle_timeout_seconds = int(os.getenv('IDLE_TIMEOUT'))

        # 日志配置
        if os.getenv('LOG_LEVEL'):
            config.logging.level = os.getenv('LOG_LEVEL')
        if os.getenv('LOG_FILE'):
            config.logging.file = os.getenv('LOG_FILE')

        return config

    def merge(self, other: "Config") -> "Config":
        """合并配置，other 的非默认值覆盖 self 的值

        用于实现配置的优先级：环境变量 > 配置文件 > 默认值

        Args:
            other: 优先级更高的配置

        Returns:
            合并后的配置（self 被修改）
        """
        # GPU 配置合并：只有非默认值才覆盖
        if other.gpu.gpu_id != 0:
            self.gpu.gpu_id = other.gpu.gpu_id
        if other.gpu.reserved_memory_mb != 2048:
            self.gpu.reserved_memory_mb = other.gpu.reserved_memory_mb
        if other.gpu.memory_utilization != 0.9:
            self.gpu.memory_utilization = other.gpu.memory_utilization

        # 代理配置合并
        if other.proxy.host != "0.0.0.0":
            self.proxy.host = other.proxy.host
        if other.proxy.port != 8080:
            self.proxy.port = other.proxy.port
        if other.proxy.base_port != 8000:
            self.proxy.base_port = other.proxy.base_port
        if other.proxy.idle_timeout_seconds != 300:
            self.proxy.idle_timeout_seconds = other.proxy.idle_timeout_seconds

        # 日志配置合并
        if other.logging.level != "INFO":
            self.logging.level = other.logging.level
        if other.logging.file != "logs/vllm_proxy.log":
            self.logging.file = other.logging.file

        # 模型配置合并：直接更新字典
        self.models.update(other.models)

        return self


# =============================================================================
# load_config 函数
# 职责: 配置加载的主入口函数
# 设计决策:
#   1. 按优先级顺序加载：默认值 -> 配置文件 -> 环境变量
#   2. 配置文件路径通过参数传入，支持灵活指定
# =============================================================================
def load_config(config_path: Optional[str] = None) -> Config:
    """加载配置，按优先级合并

    配置优先级（从低到高）:
        1. 代码中的默认值
        2. 配置文件（YAML）
        3. 环境变量

    Args:
        config_path: 配置文件路径，可选

    Returns:
        合并后的最终配置
    """
    # 1. 加载默认配置
    config = Config()

    # 2. 加载配置文件（如果存在）
    if config_path and Path(config_path).exists():
        file_config = Config.from_yaml(config_path)
        config.merge(file_config)

    # 3. 环境变量覆盖（最高优先级）
    env_config = Config.from_env()
    config.merge(env_config)

    return config
