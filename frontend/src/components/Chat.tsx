import { useState, useEffect } from 'react'
import Sidebar from './Sidebar'
import ChatArea from './ChatArea'
import { Session, Message } from '../types'
import { api } from '../api'
import { XMarkIcon, CheckIcon } from '@heroicons/react/24/outline'

// 文件类型定义
interface UploadedFile {
  id: string
  name: string
  type: string
  content: string
}

interface Settings {
  textModel: string
  visionModel: string
  temperature: number
  maxTokens: number
  thinkingBudget: number
}

const defaultSettings: Settings = {
  textModel: 'qwen-plus',
  visionModel: 'qwen-vl-plus',
  temperature: 0.7,
  maxTokens: 4000,
  thinkingBudget: 8192
}

export default function Chat() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [sessionMessages, setSessionMessages] = useState<Record<string, Message[]>>({})
  const [loadingSessions, setLoadingSessions] = useState<Set<string>>(new Set())
  const [input, setInput] = useState('')
  const [image, setImage] = useState<string | null>(null)
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([])
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settings, setSettings] = useState<Settings>(defaultSettings)
  const [abortController, setAbortController] = useState<AbortController | null>(null)

  const messages = currentSessionId ? sessionMessages[currentSessionId] || [] : []

  // 监听停止生成事件
  useEffect(() => {
    const handleStop = () => {
      if (abortController) {
        abortController.abort()
      }
    }
    window.addEventListener('stopGeneration', handleStop)
    return () => window.removeEventListener('stopGeneration', handleStop)
  }, [abortController])

  // 获取会话列表
  const fetchSessions = async () => {
    try {
      const res = await api.get('/sessions')
      setSessions(res.data)
      if (res.data.length > 0 && !currentSessionId) {
        setCurrentSessionId(res.data[0].id)
      }
    } catch (err) {
      console.error('获取会话失败:', err)
    }
  }

  // 获取消息历史
  const fetchMessages = async (sessionId: string) => {
    try {
      const res = await api.get(`/sessions/${sessionId}/messages`)
      setSessionMessages(prev => ({ ...prev, [sessionId]: res.data }))
    } catch (err) {
      console.error('获取消息失败:', err)
    }
  }

  useEffect(() => {
    fetchSessions()
  }, [])

  useEffect(() => {
    if (currentSessionId) {
      fetchMessages(currentSessionId)
    }
  }, [currentSessionId])

  // 新建会话
  const createSession = async () => {
    try {
      const res = await api.post('/sessions', { name: '新会话', type: 'text' })
      setSessions([res.data, ...sessions])
      setCurrentSessionId(res.data.id)
    } catch (err) {
      console.error('创建会话失败:', err)
    }
  }

  // 切换会话
  const switchSession = (id: string) => {
    setCurrentSessionId(id)
    setInput('')
    setImage(null)
  }

  // 删除单条消息
  const deleteMessage = async (msgId: string) => {
    console.log('deleteMessage 被调用, msgId:', msgId, 'currentSessionId:', currentSessionId)
    if (!currentSessionId) return
    
    try {
      console.log('发送删除请求:', `/sessions/${currentSessionId}/messages/${msgId}`)
      await api.delete(`/sessions/${currentSessionId}/messages/${msgId}`)
      setSessionMessages(prev => ({
        ...prev,
        [currentSessionId]: (prev[currentSessionId] || []).filter(m => m.id !== msgId)
      }))
    } catch (err) {
      console.error('删除消息失败:', err)
    }
  }

  // 删除会话
  const deleteSession = async (id: string) => {
    try {
      await api.delete(`/sessions/${id}`)
      setSessions(sessions.filter(s => s.id !== id))
      setSessionMessages(prev => {
        const { [id]: _, ...rest } = prev
        return rest
      })
      if (currentSessionId === id) {
        setCurrentSessionId(sessions[0]?.id || null)
      }
    } catch (err) {
      console.error('删除会话失败:', err)
    }
  }

  // 重命名会话
  const renameSession = async (id: string, name: string) => {
    try {
      const res = await api.patch(`/sessions/${id}`, { name })
      setSessions(prev => prev.map(s => s.id === id ? { ...s, name: res.data.name } : s))
    } catch (err) {
      console.error('重命名失败:', err)
    }
  }

  // 置顶/取消置顶会话
  const togglePinSession = async (id: string) => {
    try {
      const session = sessions.find(s => s.id === id)
      if (!session) return
      const res = await api.patch(`/sessions/${id}`, { pinned: !session.pinned })
      setSessions(prev => prev.map(s => s.id === id ? { ...s, pinned: res.data.pinned } : s))
    } catch (err) {
      console.error('置顶失败:', err)
    }
  }

  // 获取最后一条用户消息之前的对话
  // 重新生成
  const regenerateResponse = async (targetMsgId: string) => {
    if (!currentSessionId || loadingSessions.has(currentSessionId)) return
    
    const currentMsgs = sessionMessages[currentSessionId] || []
    
    // 找到目标消息的索引
    const targetIndex = currentMsgs.findIndex(m => m.id === targetMsgId)
    if (targetIndex === -1) return
    
    // 保留目标消息之前的所有消息
    const keepMsgs = currentMsgs.slice(0, targetIndex)
    
    // 找到目标消息之前的最后一条用户消息
    let lastUserMsg: Message | null = null
    for (let i = keepMsgs.length - 1; i >= 0; i--) {
      if (keepMsgs[i].role === 'user') {
        lastUserMsg = keepMsgs[i]
        break
      }
    }
    
    if (!lastUserMsg) return
    
    // 更新状态，删除目标消息及之后的所有消息
    setSessionMessages(prev => ({
      ...prev,
      [currentSessionId]: keepMsgs
    }))
    
    // 设置输入为该用户消息
    setInput(lastUserMsg.content.replace('[图片] ', ''))
    
    // 重新发送
    setTimeout(() => {
      sendMessage(lastUserMsg!.content.replace('[图片] ', ''))
    }, 100)
  }

  // 发送消息
  const sendMessage = async (msgContent?: string) => {
    const contentToSend = msgContent !== undefined ? msgContent : input
    if ((!contentToSend.trim() && !image && uploadedFiles.length === 0) || !currentSessionId || loadingSessions.has(currentSessionId)) return

    const sessionId = currentSessionId
    const currentInput = contentToSend
    const currentImage = msgContent !== undefined ? null : image
    const currentFiles = msgContent !== undefined ? [] : [...uploadedFiles]

    // 构建消息内容（包含文件内容）
    let finalContent = currentInput || ''
    if (currentFiles.length > 0) {
      const fileContents = currentFiles.map(file => {
        return `--- 文件: ${file.name} (${file.type}) ---\n${file.content}\n--- 结束 ---`
      }).join('\n\n')
      finalContent = fileContents + (finalContent ? '\n\n' + finalContent : '')
    }

    // 构建显示内容（显示文件名）
    let displayContent = currentInput || ''
    if (currentFiles.length > 0) {
      const fileNames = currentFiles.map(f => `📄 ${f.name}`).join(', ')
      displayContent = displayContent 
        ? `${fileNames}\n\n${displayContent}`
        : fileNames
    } else if (currentImage) {
      displayContent = displayContent || '🖼️ [图片]'
    }

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: displayContent,
      image_url: currentImage || undefined,
      timestamp: Date.now()
    }

    setSessionMessages(prev => ({
      ...prev,
      [sessionId]: [...(prev[sessionId] || []), userMsg]
    }))

    if (msgContent === undefined) {
      setInput('')
      setImage(null)
      setUploadedFiles([])
    }
    setLoadingSessions(prev => new Set(prev).add(sessionId))

    // 添加思考中占位
    const thinkingMsg: Message = {
      id: `thinking-${sessionId}-${Date.now()}`,
      role: 'assistant',
      content: '🤔 思考中...',
      timestamp: Date.now()
    }
    setSessionMessages(prev => ({
      ...prev,
      [sessionId]: [...(prev[sessionId] || []), thinkingMsg]
    }))

    // 创建 AbortController
    const controller = new AbortController()
    setAbortController(controller)

    try {
      const fetchPromise = fetch(
        `${import.meta.env.VITE_API_URL || 'http://localhost:8080'}/api/chat/send`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: sessionId,
            message: finalContent || '[图片]',
            image_url: currentImage,
            settings: {
              text_model: settings.textModel,
              vision_model: settings.visionModel,
              temperature: settings.temperature,
              max_tokens: settings.maxTokens,
              thinking_budget: settings.thinkingBudget
            }
          }),
          signal: controller.signal
        }
      )

      const response = await fetchPromise
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      
      const data = await response.json()
      
      if (data.content) {
        setSessionMessages(prev => ({
          ...prev,
          [sessionId]: (prev[sessionId] || []).map(msg =>
            msg.id === thinkingMsg.id
              ? { 
                  ...msg, 
                  id: Date.now().toString(), 
                  content: data.content,
                  reasoning_content: data.reasoning_content
                }
              : msg
          )
        }))
        if (data.session_name) {
          setSessions(prev =>
            prev.map(s =>
              s.id === sessionId ? { ...s, name: data.session_name } : s
            )
          )
        }
      } else {
        throw new Error('No content returned')
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        setSessionMessages(prev => ({
          ...prev,
          [sessionId]: (prev[sessionId] || []).map(msg =>
            msg.id === thinkingMsg.id
              ? { ...msg, id: Date.now().toString(), content: '⏹️ 已停止生成' }
              : msg
          )
        }))
      } else {
        console.error('发送消息失败:', err)
        setSessionMessages(prev => ({
          ...prev,
          [sessionId]: (prev[sessionId] || []).map(msg =>
            msg.id === thinkingMsg.id
              ? { ...msg, id: Date.now().toString(), content: '❌ 请求失败: ' + err.message }
              : msg
          )
        }))
      }
    } finally {
      setLoadingSessions(prev => {
        const next = new Set(prev)
        next.delete(sessionId)
        return next
      })
      setAbortController(null)
    }
  }

  // 处理图片上传
  const handleImageUpload = async (file: File) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      const img = new Image()
      img.onload = () => {
        const canvas = document.createElement('canvas')
        const maxSize = 1024
        let width = img.width
        let height = img.height
        
        if (width > maxSize || height > maxSize) {
          if (width > height) {
            height = (height / width) * maxSize
            width = maxSize
          } else {
            width = (width / height) * maxSize
            height = maxSize
          }
        }
        
        canvas.width = width
        canvas.height = height
        const ctx = canvas.getContext('2d')
        ctx?.drawImage(img, 0, 0, width, height)
        
        const compressed = canvas.toDataURL('image/jpeg', 0.7)
        setImage(compressed)
      }
      img.src = e.target?.result as string
    }
    reader.readAsDataURL(file)
  }

  return (
    <>
      <Sidebar
        sessions={sessions}
        currentId={currentSessionId}
        messages={messages}
        onCreate={createSession}
        onSwitch={switchSession}
        onDelete={deleteSession}
        onRename={renameSession}
        onTogglePin={togglePinSession}
      />
      
      <div className="flex-1 flex flex-col relative">
        <ChatArea
          messages={messages}
          input={input}
          setInput={setInput}
          onSend={() => sendMessage()}
          isLoading={currentSessionId ? loadingSessions.has(currentSessionId) : false}
          image={image}
          setImage={setImage}
          onImageUpload={handleImageUpload}
          onDeleteMessage={deleteMessage}
          onRegenerate={regenerateResponse}
          onOpenSettings={() => setSettingsOpen(true)}
          uploadedFiles={uploadedFiles}
          setUploadedFiles={setUploadedFiles}
        />

        {/* 设置面板 */}
        {settingsOpen && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-md mx-4">
              {/* 标题栏 */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
                <h3 className="text-lg font-semibold text-gray-800">⚙️ 设置</h3>
                <button
                  onClick={() => setSettingsOpen(false)}
                  className="p-1 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100"
                >
                  <XMarkIcon className="w-5 h-5" />
                </button>
              </div>

              {/* 设置内容 */}
              <div className="p-6 space-y-5">
                {/* 模型选择 */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    文本模型
                  </label>
                  <select
                    value={settings.textModel}
                    onChange={(e) => setSettings({ ...settings, textModel: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                  >
                    <option value="qwen-plus">qwen-plus (推荐)</option>
                    <option value="qwen-max">qwen-max</option>
                    <option value="qwen-turbo">qwen-turbo</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    视觉模型
                  </label>
                  <select
                    value={settings.visionModel}
                    onChange={(e) => setSettings({ ...settings, visionModel: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                  >
                    <option value="qwen-vl-plus">qwen-vl-plus</option>
                    <option value="qwen-vl-max">qwen-vl-max</option>
                  </select>
                </div>

                {/* Temperature */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Temperature: {settings.temperature}
                  </label>
                  <input
                    type="range"
                    min="0"
                    max="2"
                    step="0.1"
                    value={settings.temperature}
                    onChange={(e) => setSettings({ ...settings, temperature: parseFloat(e.target.value) })}
                    className="w-full"
                  />
                  <div className="flex justify-between text-xs text-gray-400 mt-1">
                    <span>精确</span>
                    <span>随机</span>
                  </div>
                </div>

                {/* Max Tokens */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    最大回复长度: {settings.maxTokens}
                  </label>
                  <input
                    type="range"
                    min="500"
                    max="8000"
                    step="500"
                    value={settings.maxTokens}
                    onChange={(e) => setSettings({ ...settings, maxTokens: parseInt(e.target.value) })}
                    className="w-full"
                  />
                </div>

                {/* 思考预算 */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    思考预算: {settings.thinkingBudget}
                  </label>
                  <input
                    type="range"
                    min="0"
                    max="16000"
                    step="1024"
                    value={settings.thinkingBudget}
                    onChange={(e) => setSettings({ ...settings, thinkingBudget: parseInt(e.target.value) })}
                    className="w-full"
                  />
                  <div className="flex justify-between text-xs text-gray-400 mt-1">
                    <span>关闭思考</span>
                    <span>最大思考</span>
                  </div>
                </div>
              </div>

              {/* 底部按钮 */}
              <div className="px-6 py-4 border-t border-gray-200 flex justify-end gap-3">
                <button
                  onClick={() => {
                    setSettings(defaultSettings)
                  }}
                  className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-lg transition-colors"
                >
                  恢复默认
                </button>
                <button
                  onClick={() => setSettingsOpen(false)}
                  className="px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors flex items-center gap-1"
                >
                  <CheckIcon className="w-4 h-4" />
                  保存
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
