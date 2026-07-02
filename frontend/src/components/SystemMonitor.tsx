import { useState, useEffect } from 'react'
import { CpuChipIcon, CircleStackIcon, BoltIcon, ChartBarIcon, ChevronRightIcon, ChevronLeftIcon } from '@heroicons/react/24/outline'

interface SystemStatus {
  active_requests: number
  queued_requests: number
  requests_per_minute: number
  avg_response_time: number
  gpu_usage: number
  gpu_memory: number
  cpu_usage: number
  memory_usage: number
}

export default function SystemMonitor() {
  const [collapsed, setCollapsed] = useState(true)
  const [status, setStatus] = useState<SystemStatus | null>(null)

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch('http://localhost:8080/api/monitor/status')
        if (res.ok) {
          const data = await res.json()
          setStatus(data)
        }
      } catch (err) {
        console.error('获取系统状态失败:', err)
      }
    }

    fetchStatus()
    const interval = setInterval(fetchStatus, 3000) // 每3秒更新
    return () => clearInterval(interval)
  }, [])

  if (!status) return null

  return (
    <div className={`fixed right-0 top-16 z-40 transition-all duration-300 ${collapsed ? 'w-10' : 'w-64'}`}>
      {/* 折叠按钮 */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="absolute left-0 top-0 w-10 h-10 bg-white border border-gray-200 rounded-l-lg shadow-md flex items-center justify-center hover:bg-gray-50"
      >
        {collapsed ? (
          <ChevronLeftIcon className="w-5 h-5 text-gray-600" />
        ) : (
          <ChevronRightIcon className="w-5 h-5 text-gray-600" />
        )}
      </button>

      {/* 面板内容 */}
      {!collapsed && (
        <div className="ml-10 bg-white border border-gray-200 rounded-l-lg shadow-lg p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
            <ChartBarIcon className="w-4 h-4" />
            系统监控
          </h3>

          {/* GPU 状态 */}
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm">
              <BoltIcon className="w-4 h-4 text-yellow-500" />
              <span className="text-gray-600 flex-1">GPU 使用率</span>
              <span className="font-medium text-gray-800">{status.gpu_usage.toFixed(1)}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-1.5">
              <div
                className={`h-1.5 rounded-full transition-all ${
                  status.gpu_usage > 80 ? 'bg-red-500' : status.gpu_usage > 50 ? 'bg-yellow-500' : 'bg-green-500'
                }`}
                style={{ width: `${status.gpu_usage}%` }}
              />
            </div>

            <div className="flex items-center gap-2 text-sm">
              <CircleStackIcon className="w-4 h-4 text-blue-500" />
              <span className="text-gray-600 flex-1">GPU 显存</span>
              <span className="font-medium text-gray-800">{status.gpu_memory.toFixed(1)}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-1.5">
              <div
                className="h-1.5 rounded-full bg-blue-500 transition-all"
                style={{ width: `${status.gpu_memory}%` }}
              />
            </div>

            {/* 请求状态 */}
            <div className="pt-2 border-t border-gray-100">
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-gray-50 rounded p-2">
                  <div className="text-gray-500">活跃请求</div>
                  <div className="text-lg font-semibold text-indigo-600">{status.active_requests}</div>
                </div>
                <div className="bg-gray-50 rounded p-2">
                  <div className="text-gray-500">队列等待</div>
                  <div className="text-lg font-semibold text-orange-500">{status.queued_requests}</div>
                </div>
              </div>
            </div>

            {/* 响应时间 */}
            <div className="flex items-center justify-between text-xs text-gray-500 pt-1">
              <span>平均响应</span>
              <span className="font-medium">{status.avg_response_time.toFixed(2)}s</span>
            </div>

            {/* CPU & 内存 */}
            <div className="pt-2 border-t border-gray-100 space-y-2">
              <div className="flex items-center gap-2 text-xs">
                <CpuChipIcon className="w-3 h-3 text-gray-400" />
                <span className="text-gray-500 flex-1">CPU</span>
                <span className="text-gray-700">{status.cpu_usage.toFixed(1)}%</span>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <CircleStackIcon className="w-3 h-3 text-gray-400" />
                <span className="text-gray-500 flex-1">内存</span>
                <span className="text-gray-700">{status.memory_usage.toFixed(1)}%</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
