"""
系统监控路由
"""
from fastapi import APIRouter, HTTPException
from typing import Dict

from ...monitoring.rate_limiter import monitor

router = APIRouter()


@router.get("/status")
async def get_system_status() -> Dict:
    """获取系统状态"""
    return monitor.get_status()


@router.get("/queue")
async def get_queue_status() -> Dict:
    """获取队列状态"""
    return monitor.request_queue.get_status()


@router.post("/start")
async def start_monitoring():
    """启动监控"""
    monitor.start_monitoring()
    return {"status": "started"}


@router.post("/stop")
async def stop_monitoring():
    """停止监控"""
    monitor.stop_monitoring()
    return {"status": "stopped"}
