"""
Pydantic 模型定义
"""
from typing import Optional, List, Union, Dict, Any
from pydantic import BaseModel, Field


# ============ 请求模型 ============

class Message(BaseModel):
    """聊天消息"""
    role: str = Field(..., description="角色: system/user/assistant")
    content: Union[str, List[Dict[str, Any]]] = Field(..., description="消息内容")


class ChatRequest(BaseModel):
    """文本对话请求"""
    model: str = Field(default="qwen-plus", description="模型名称")
    messages: List[Message] = Field(..., description="消息列表")
    stream: bool = Field(default=False, description="是否流式输出")
    temperature: Optional[float] = Field(default=0.7, ge=0, le=2, description="温度参数")
    max_tokens: Optional[int] = Field(default=2048, ge=1, description="最大 token 数")
    top_p: Optional[float] = Field(default=0.9, ge=0, le=1, description="top_p 参数")


class ImageContent(BaseModel):
    """图片内容"""
    type: str = Field(default="image_url")
    image_url: Dict[str, str] = Field(..., description="图片 URL")


class TextContent(BaseModel):
    """文本内容"""
    type: str = Field(default="text")
    text: str = Field(..., description="文本内容")


class MultimodalMessage(BaseModel):
    """多模态消息"""
    role: str = Field(default="user")
    content: List[Dict[str, Any]] = Field(..., description="消息内容列表")


class MultimodalRequest(BaseModel):
    """多模态对话请求"""
    model: str = Field(default="qwen-vl-plus", description="模型名称")
    messages: List[MultimodalMessage] = Field(..., description="消息列表")
    stream: bool = Field(default=False, description="是否流式输出")
    enable_thinking: bool = Field(default=False, description="是否启用思考")
    thinking_budget: Optional[int] = Field(default=81920, description="思考 token 上限")


# ============ 响应模型 ============

class Choice(BaseModel):
    """对话选项"""
    index: int
    message: Dict[str, Any]
    finish_reason: Optional[str] = None


class Usage(BaseModel):
    """用量信息"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    """对话响应"""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Choice]
    usage: Usage


class ErrorResponse(BaseModel):
    """错误响应"""
    error: Dict[str, Any]