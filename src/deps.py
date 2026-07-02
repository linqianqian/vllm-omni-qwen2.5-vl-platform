"""
依赖注入模块
"""
from .llm_client import AliyunLLMClient, get_llm_client, close_llm_client

__all__ = ["AliyunLLMClient", "get_llm_client", "close_llm_client"]