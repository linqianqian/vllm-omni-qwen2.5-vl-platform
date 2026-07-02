"""
GPU 监控模块 - 读取真实 NVIDIA GPU 指标
"""
from typing import Dict, List, Any

try:
    import pynvml
    PYNVML_AVAILABLE = True
except ImportError:
    PYNVML_AVAILABLE = False
    print("警告: pynvml 模块未安装，GPU 监控将使用模拟数据")


class GPUMonitor:
    """GPU 监控类"""
    
    def __init__(self):
        self.initialized = False
        self.device_count = 0
        
    def initialize(self):
        """初始化 NVML"""
        if not PYNVML_AVAILABLE:
            return False
        try:
            pynvml.nvmlInit()
            self.initialized = True
            self.device_count = pynvml.nvmlDeviceGetCount()
            return True
        except Exception as e:
            print(f"NVML 初始化失败: {e}")
            return False
    
    def get_device_metrics(self, device_index: int = 0) -> Dict[str, Any]:
        """
        获取单个 GPU 的详细指标
        
        Returns:
            GPU 指标字典
        """
        if not PYNVML_AVAILABLE:
            # 返回模拟数据
            return {
                "util": 15,
                "mem_used": 4.2,
                "mem_total": 24,
                "temperature": 45,
                "name": "Simulated GPU",
                "status": "normal"
            }
        
        if not self.initialized:
            self.initialize()
        
        if device_index >= self.device_count:
            return {
                "util": 0,
                "mem_used": 0,
                "mem_total": 24,
                "temperature": 0,
                "name": "N/A",
                "status": "offline"
            }
        
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(device_index)
            
            # GPU 利用率
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            
            # 显存信息
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            
            # 温度
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            
            # GPU 名称
            name = pynvml.nvmlDeviceGetName(handle).decode('utf-8')
            
            # 功耗（如果支持）
            try:
                power = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000  # 转为瓦特
            except:
                power = 0
            
            # 确定状态
            status = "normal"
            if temp > 85:
                status = "warning"
            if util.gpu > 95:
                status = "overload"
            
            return {
                "util": util.gpu,
                "mem_used": mem.used / 1024**3,
                "mem_total": mem.total / 1024**3,
                "temperature": temp,
                "name": name,
                "power": power,
                "status": status,
                "index": device_index
            }
            
        except Exception as e:
            print(f"读取 GPU {device_index} 指标失败: {e}")
            return {
                "util": 0,
                "mem_used": 0,
                "mem_total": 24,
                "temperature": 0,
                "name": f"GPU {device_index}",
                "status": "error"
            }
    
    def get_all_metrics(self) -> List[Dict[str, Any]]:
        """获取所有 GPU 的指标"""
        metrics = []
        if not self.initialized:
            self.initialize()
        
        for i in range(self.device_count):
            metrics.append(self.get_device_metrics(i))
        
        return metrics
    
    def get_system_summary(self) -> Dict[str, Any]:
        """获取系统级摘要"""
        metrics = self.get_all_metrics()
        
        if not metrics:
            return {
                "total_gpus": 0,
                "total_util": 0,
                "total_mem_used": 0,
                "total_mem_total": 0,
                "avg_temp": 0,
                "status": "no_gpu"
            }
        
        total_util = sum(m["util"] for m in metrics) / len(metrics)
        total_mem_used = sum(m["mem_used"] for m in metrics)
        total_mem_total = sum(m["mem_total"] for m in metrics)
        avg_temp = sum(m["temperature"] for m in metrics) / len(metrics)
        
        # 系统状态
        if any(m["status"] == "overload" for m in metrics):
            system_status = "overload"
        elif any(m["status"] == "warning" for m in metrics):
            system_status = "warning"
        elif any(m["status"] == "error" for m in metrics):
            system_status = "error"
        else:
            system_status = "normal"
        
        return {
            "total_gpus": len(metrics),
            "total_util": round(total_util, 1),
            "total_mem_used": round(total_mem_used, 1),
            "total_mem_total": round(total_mem_total, 1),
            "avg_temp": round(avg_temp, 1),
            "status": system_status,
            "gpus": metrics
        }
    
    def close(self):
        """关闭 NVML"""
        if self.initialized and PYNVML_AVAILABLE:
            pynvml.nvmlShutdown()
            self.initialized = False


# 全局实例
gpu_monitor = GPUMonitor()