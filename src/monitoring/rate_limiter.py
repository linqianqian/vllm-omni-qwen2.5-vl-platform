"""
限流和并发控制
"""
import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Optional
import psutil


@dataclass
class SystemStatus:
    """系统状态"""
    active_requests: int = 0
    queued_requests: int = 0
    total_requests: int = 0
    requests_per_minute: int = 0
    avg_response_time: float = 0.0
    gpu_usage: float = 0.0
    gpu_memory: float = 0.0
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    timestamp: float = field(default_factory=time.time)


class RateLimiter:
    """限流器"""
    def __init__(self, max_requests_per_minute: int = 60):
        self.max_requests = max_requests_per_minute
        self.requests: Dict[str, list] = {}
        
    def is_allowed(self, client_id: str = "default") -> bool:
        """检查是否允许请求"""
        now = time.time()
        minute_ago = now - 60
        
        # 清理过期请求记录
        if client_id in self.requests:
            self.requests[client_id] = [
                t for t in self.requests[client_id] if t > minute_ago
            ]
        else:
            self.requests[client_id] = []
        
        # 检查是否超过限制
        if len(self.requests[client_id]) >= self.max_requests:
            return False
        
        # 记录请求
        self.requests[client_id].append(now)
        return True
    
    def get_remaining(self, client_id: str = "default") -> int:
        """获取剩余请求次数"""
        if client_id not in self.requests:
            return self.max_requests
        return max(0, self.max_requests - len(self.requests[client_id]))


class RequestQueue:
    """请求队列管理"""
    def __init__(self, max_concurrent: int = 10, max_queue_size: int = 100):
        self.max_concurrent = max_concurrent
        self.max_queue_size = max_queue_size
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.queue_size = 0
        self.active_count = 0
        self.total_processed = 0
        self.response_times: list = []
        
    async def acquire(self) -> bool:
        """获取执行槽位"""
        if self.queue_size >= self.max_queue_size:
            return False
        
        self.queue_size += 1
        await self.semaphore.acquire()
        self.queue_size -= 1
        self.active_count += 1
        return True
    
    def release(self, response_time: float = 0):
        """释放执行槽位"""
        self.semaphore.release()
        self.active_count -= 1
        self.total_processed += 1
        
        if response_time > 0:
            self.response_times.append(response_time)
            # 只保留最近100个响应时间
            if len(self.response_times) > 100:
                self.response_times.pop(0)
    
    def get_avg_response_time(self) -> float:
        """获取平均响应时间"""
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)
    
    def get_status(self) -> Dict:
        """获取队列状态"""
        return {
            "active": self.active_count,
            "queued": self.queue_size,
            "max_concurrent": self.max_concurrent,
            "max_queue": self.max_queue_size,
            "total_processed": self.total_processed,
            "avg_response_time": round(self.get_avg_response_time(), 2)
        }


class SystemMonitor:
    """系统监控"""
    def __init__(self):
        self.rate_limiter = RateLimiter()
        self.request_queue = RequestQueue()
        self.status = SystemStatus()
        self._running = False
        
    def start_monitoring(self):
        """开始监控"""
        self._running = True
        asyncio.create_task(self._update_metrics())
    
    def stop_monitoring(self):
        """停止监控"""
        self._running = False
    
    async def _update_metrics(self):
        """定期更新系统指标"""
        while self._running:
            try:
                # 更新CPU和内存
                self.status.cpu_usage = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                self.status.memory_usage = memory.percent
                
                # 更新队列状态
                queue_status = self.request_queue.get_status()
                self.status.active_requests = queue_status["active"]
                self.status.queued_requests = queue_status["queued"]
                self.status.avg_response_time = queue_status["avg_response_time"]
                
                # TODO: 添加GPU监控（需要nvidia-ml-py）
                # 暂时用模拟数据
                self.status.gpu_usage = min(100, self.status.active_requests * 10 + 20)
                self.status.gpu_memory = min(100, self.status.active_requests * 8 + 15)
                
            except Exception as e:
                print(f"监控更新失败: {e}")
            
            await asyncio.sleep(2)  # 每2秒更新一次
    
    def get_status(self) -> Dict:
        """获取当前状态"""
        return {
            "active_requests": self.status.active_requests,
            "queued_requests": self.status.queued_requests,
            "requests_per_minute": self.rate_limiter.max_requests,
            "avg_response_time": self.status.avg_response_time,
            "gpu_usage": self.status.gpu_usage,
            "gpu_memory": self.status.gpu_memory,
            "cpu_usage": self.status.cpu_usage,
            "memory_usage": self.status.memory_usage,
            "timestamp": time.time()
        }


# 全局监控实例
monitor = SystemMonitor()
