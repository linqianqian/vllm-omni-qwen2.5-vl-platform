"""
文本对话路由
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import time
import httpx
import json
from datetime import datetime

from ...services.llm_client import AliyunLLMClient, get_llm_client
from ...models import ChatRequest, ChatResponse, ErrorResponse
from ...config import get_settings
from ...database import get_db, SessionDB, MessageDB
from ...monitoring.rate_limiter import monitor

router = APIRouter()


@router.post("/text", response_model=ChatResponse)
async def chat_text(
    request: ChatRequest,
    client: AliyunLLMClient = Depends(get_llm_client)
):
    """
    文本对话接口
    """
    try:
        payload = {
            "model": request.model,
            "messages": [msg.model_dump() for msg in request.messages],
            "stream": request.stream,
        }

        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.top_p is not None:
            payload["top_p"] = request.top_p

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


@router.post("/text/stream")
async def chat_text_stream(
    request: ChatRequest,
    client: AliyunLLMClient = Depends(get_llm_client)
):
    """
    流式文本对话接口
    """
    try:
        payload = {
            "model": request.model,
            "messages": [msg.model_dump() for msg in request.messages],
            "stream": True,
        }

        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        return StreamingResponse(
            client.chat_completions_stream(payload),
            media_type="text/event-stream"
        )

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send")
async def chat_send(
    request: dict,
    client: AliyunLLMClient = Depends(get_llm_client),
    db: Session = Depends(get_db)
):
    """
    简化的发送消息接口（用于前端）
    """
    # 限流检查
    if not monitor.rate_limiter.is_allowed():
        raise HTTPException(
            status_code=429, 
            detail="请求过于频繁，请稍后再试"
        )
    
    # 获取队列槽位
    if not await monitor.request_queue.acquire():
        raise HTTPException(
            status_code=503, 
            detail="系统繁忙，请稍后再试"
        )
    
    start_time = time.time()
    
    try:
        session_id = request.get("session_id")
        message = request.get("message", "")
        image_url = request.get("image_url")
        
        settings = get_settings()
        model = settings.vision_model if image_url else settings.text_model

        if not session_id or not message:
            raise HTTPException(status_code=400, detail="session_id 和 message 不能为空")

        # 获取会话
        session = db.query(SessionDB).filter(SessionDB.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")

        # 获取会话历史消息
        history_msgs = db.query(MessageDB).filter(
            MessageDB.session_id == session_id
        ).order_by(MessageDB.timestamp).all()

        # 构建消息列表
        messages = []
        for msg in history_msgs[-10:]:
            messages.append({"role": msg.role, "content": msg.content})

        # 添加用户消息（支持图片）
        if image_url:
            user_message = {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": message}
                ]
            }
        else:
            user_message = {"role": "user", "content": message}

        messages.append(user_message)

        # 保存用户消息到数据库
        now = datetime.now().timestamp()
        user_msg = MessageDB(
            id=str(time.time()),
            session_id=session_id,
            role="user",
            content=message,
            timestamp=now
        )
        db.add(user_msg)
        session.updated_at = now
        db.commit()

        # 调用 LLM
        payload = {
            "model": model,
            "messages": messages
        }

        print(f"[DEBUG] Request payload: {payload}")
        
        print(f"[DEBUG] Using model: {model}, has_image: {bool(image_url)}")

        response = await client.chat_completions(payload)

        # 保存助手回复
        assistant_content = response["choices"][0]["message"]["content"]
        # 获取思考过程（如果存在）
        reasoning_content = response["choices"][0]["message"].get("reasoning_content", "")
        
        assistant_msg = MessageDB(
            id=response.get("id", str(time.time())),
            session_id=session_id,
            role="assistant",
            content=assistant_content,
            timestamp=datetime.now().timestamp()
        )
        db.add(assistant_msg)
        session.updated_at = datetime.now().timestamp()
        db.commit()

        # 如果是第一条消息且会话名是"新会话"，自动生成标题
        if session.name == "新会话":
            user_msg_count = db.query(MessageDB).filter(
                MessageDB.session_id == session_id,
                MessageDB.role == "user"
            ).count()
            
            if user_msg_count == 1:
                try:
                    title_payload = {
                        "model": model,
                        "messages": [
                            {"role": "user", "content": f"请根据以下用户问题生成一个简短的会话标题（不超过10个字），直接返回标题，不要有任何解释：{message}"}
                        ],
                        "stream": False
                    }
                    title_response = await client.chat_completions(title_payload)
                    title = title_response["choices"][0]["message"]["content"].strip().replace('"', '').replace("'", "")
                    if title:
                        session.name = title[:20]
                        session.updated_at = datetime.now().timestamp()
                        db.commit()
                except Exception as e:
                    print(f"生成标题失败: {e}")

        return {
            "id": response.get("id"),
            "content": assistant_content,
            "reasoning_content": reasoning_content,
            "model": response.get("model", model),
            "session_name": session.name
        }

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        import traceback
        print(f"[ERROR] {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 释放队列槽位
        response_time = time.time() - start_time
        monitor.request_queue.release(response_time)


@router.post("/send/stream")
async def chat_send_stream(
    request: dict,
    client: AliyunLLMClient = Depends(get_llm_client),
    db: Session = Depends(get_db)
):
    """
    流式发送消息接口（用于前端）
    """
    try:
        session_id = request.get("session_id")
        message = request.get("message", "")
        model = request.get("model", "qwen-vl-max")
        image_url = request.get("image_url")

        if not session_id or not message:
            raise HTTPException(status_code=400, detail="session_id 和 message 不能为空")

        # 获取会话
        session = db.query(SessionDB).filter(SessionDB.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")

        # 获取会话历史
        history_msgs = db.query(MessageDB).filter(
            MessageDB.session_id == session_id
        ).order_by(MessageDB.timestamp).all()

        # 构建消息列表
        messages = []
        for msg in history_msgs[-10:]:
            messages.append({"role": msg.role, "content": msg.content})

        # 添加用户消息
        if image_url:
            user_content = f"{message}\n[图片: {image_url}]"
        else:
            user_content = message

        messages.append({"role": "user", "content": user_content})

        # 保存用户消息
        now = datetime.now().timestamp()
        user_msg = MessageDB(
            id=str(time.time()),
            session_id=session_id,
            role="user",
            content=message,
            timestamp=now
        )
        db.add(user_msg)
        session.updated_at = now
        db.commit()

        # 构建 payload
        payload = {
            "model": model,
            "messages": messages,
            "stream": True
        }

        async def generate():
            full_content = ""
            async for line in client.chat_completions_stream(payload):
                yield line
                
                line_str = line.strip()
                if line_str.startswith("data: "):
                    data_str = line_str[6:].strip()
                    if data_str == "[DONE]":
                        continue
                    try:
                        data = json.loads(data_str)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        reasoning = delta.get("reasoning_content", "")
                        if content:
                            full_content += content
                        elif reasoning:
                            full_content += reasoning
                    except Exception as e:
                        print(f"Parse error: {e}")

            # 保存完整回复到数据库
            assistant_msg = MessageDB(
                id=str(time.time()),
                session_id=session_id,
                role="assistant",
                content=full_content,
                timestamp=datetime.now().timestamp()
            )
            db.add(assistant_msg)
            session.updated_at = datetime.now().timestamp()
            db.commit()

        return StreamingResponse(
            generate(),
            media_type="text/event-stream"
        )

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
