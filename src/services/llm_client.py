"""
阿里云百炼 API 客户端
"""
import httpx
from typing import Dict, Any, Optional
from ..config import get_settings


class AliyunLLMClient:
    """阿里云百炼 API 异步客户端"""

    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.settings.request_timeout),
                limits=httpx.Limits(max_connections=self.settings.max_concurrent_requests)
            )
        return self._client

    async def close(self):
        """关闭客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def chat_completions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用聊天补全 API

        Args:
            payload: 请求载荷

        Returns:
            API 响应
        """
        client = await self._get_client()

        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json"
        }

        response = await client.post(
            self.settings.api_base_url,
            headers=headers,
            json=payload
        )

        response.raise_for_status()
        return response.json()

    async def chat_completions_stream(self, payload: Dict[str, Any]):
        """
        流式调用聊天补全 API

        Args:
            payload: 请求载荷

        Yields:
            流式响应数据 (SSE 格式)
        """
        client = await self._get_client()

        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json"
        }

        async with client.stream(
            "POST",
            self.settings.api_base_url,
            headers=headers,
            json=payload
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                line = line.strip()
                if line.startswith("data:"):
                    data = line[5:].strip()
                    yield f"data: {data}\n\n"
                    if data == "[DONE]":
                        break


# 全局客户端实例
_client: Optional[AliyunLLMClient] = None


async def get_llm_client() -> AliyunLLMClient:
    """获取 LLM 客户端单例"""
    global _client
    if _client is None:
        _client = AliyunLLMClient()
    return _client


async def close_llm_client():
    """关闭 LLM 客户端"""
    global _client
    if _client:
        await _client.close()
        _client = None