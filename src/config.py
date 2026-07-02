"""
配置文件
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置"""

    # API 配置
    api_base_url: str = "https://llm-vkfffdxg8newc2bp.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions"
    api_key: str = "sk-42944cd0e43047beab2a04de61bfe934"

    # 模型配置（阿里云百炼）
    text_model: str = "qwen-plus"  # 或 qwen-max, qwen-turbo
    vision_model: str = "qwen-vl-plus"  # 或 qwen-vl-max

    # 服务配置
    app_name: str = "vLLM-Omni 多模态推理平台"
    app_version: str = "0.1.0"
    debug: bool = False

    # 高并发配置
    max_concurrent_requests: int = 100
    request_timeout: int = 120

    # 限流配置
    rate_limit_per_minute: int = 60

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()