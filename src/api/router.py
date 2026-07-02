"""
API 路由
"""
from fastapi import APIRouter

from .routes import chat, multimodal, sessions, monitor, files

api_router = APIRouter()

api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(multimodal.router, prefix="/multimodal", tags=["multimodal"])
api_router.include_router(sessions.router, prefix="", tags=["sessions"])
api_router.include_router(monitor.router, prefix="/monitor", tags=["monitor"])
api_router.include_router(files.router, prefix="/files", tags=["files"])