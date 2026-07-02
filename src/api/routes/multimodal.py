"""
多模态对话路由
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import time
import httpx

from ...services.llm_client import AliyunLLMClient, get_llm_client
from ...models import MultimodalRequest, ChatResponse

router = APIRouter()


@router.post("/image", response_model=ChatResponse)
async def chat_multimodal(
    request: MultimodalRequest,
    client: AliyunLLMClient = Depends(get_llm_client)
):
    """
    多模态对话接口（支持图片+文本）

    - 支持流式/非流式输出
    - 支持启用思考模式（enable_thinking）
    """
    try:
        # 构建请求载荷
        payload = {
            "model": request.model,
            "messages": [msg.model_dump() for msg in request.messages],
            "stream": request.stream,
            "enable_thinking": request.enable_thinking,
        }

        if request.thinking_budget is not None:
            payload["thinking_budget"] = request.thinking_budget

        # 调用 API
        response = await client.chat_completions(payload)

        return ChatResponse(
            id=response.get("id", f"chatcmpl-{int(time.time())}"),
            created=response.get("created", int(time.time())),
            model=response.get("model", request.model),
            choices=[response["choices"][0]],
            usage=response.get("usage", {})
        )

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/image/stream")
async def chat_multimodal_stream(
    request: MultimodalRequest,
    client: AliyunLLMClient = Depends(get_llm_client)
):
    """
    流式多模态对话接口
    """
    try:
        payload = {
            "model": request.model,
            "messages": [msg.model_dump() for msg in request.messages],
            "stream": True,
            "enable_thinking": request.enable_thinking,
        }

        if request.thinking_budget is not None:
            payload["thinking_budget"] = request.thinking_budget

        return StreamingResponse(
            client.chat_completions_stream(payload),
            media_type="text/event-stream"
        )

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))