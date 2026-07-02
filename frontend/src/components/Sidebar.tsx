import React, { useState, useRef, useEffect } from 'react'
import { PlusIcon, TrashIcon, ChatBubbleLeftIcon, PhotoIcon, PencilIcon, ArrowUpIcon, DocumentArrowDownIcon, CheckIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { Session, Message } from '../types'

interface Props {
  sessions: Session[]
  currentId: string | null
  messages: Message[]
  onCreate: () => void
  onSwitch: (id: string) => void
  onDelete: (id: string) => void
  onRename: (id: string, name: string) => void
  onTogglePin: (id: string) => void
  width?: number
  onWidthChange?: (width: number) => void
}

export default function Sidebar({ sessions, currentId, messages, onCreate, onSwitch, onDelete, onRename, onTogglePin, width = 260, onWidthChange }: Props) {
  const [menuOpen, setMenuOpen] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [sidebarWidth, setSidebarWidth] = useState(width)
  const [isResizing, setIsResizing] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  // 拖拽开始
  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    setIsResizing(true)
  }

  // 拖拽中
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return
      const newWidth = Math.max(180, Math.min(400, e.clientX))
      setSidebarWidth(newWidth)
      onWidthChange?.(newWidth)
    }

    const handleMouseUp = () => {
      setIsResizing(false)
    }

    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isResizing, onWidthChange])

  // 点击外部关闭菜单
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(null)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // 导出对话为 Markdown
  const exportConversation = (session: Session) => {
    const content = messages.map(msg => {
      const role = msg.role === 'user' ? '**用户**' : '**AI**'
      return `${role}:\n${msg.content}\n\n---\n`
    }).join('\n')
    
    const blob = new Blob([`# ${session.name}\n\n${content}`], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${session.name}.md`
    a.click()
    URL.revokeObjectURL(url)
    setMenuOpen(null)
  }

  // 开始编辑
  const startEdit = (session: Session, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingId(session.id)
    setEditName(session.name)
    setMenuOpen(null)
  }

  // 保存重命名
  const saveRename = (id: string) => {
    if (editName.trim()) {
      onRename(id, editName.trim())
    }
    setEditingId(null)
  }

  // 取消编辑
  const cancelEdit = () => {
    setEditingId(null)
    setEditName('')
  }

  // 按置顶状态排序
  const sortedSessions = [...sessions].sort((a, b) => {
    if (a.pinned && !b.pinned) return -1
    if (!a.pinned && b.pinned) return 1
    return b.updated_at - a.updated_at
  })

  return (
    <div className="flex h-full">
      {/* 侧边栏 */}
      <div style={{ width: sidebarWidth, minWidth: sidebarWidth }} className="bg-gray-50 border-r border-gray-200 flex flex-col h-full">
        {/* Logo */}
        <div className="p-4 border-b border-gray-200">
          <h1 className="text-xl font-semibold text-gray-800">🤖 vLLM-Omni</h1>
        </div>

        {/* 新对话按钮 */}
        <div className="p-3">
          <button
            onClick={onCreate}
            className="w-full flex items-center justify-center gap-2 bg-white border border-gray-300 rounded-lg py-3 px-4 text-base font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-400 transition-colors"
          >
            <PlusIcon className="w-5 h-5" />
            新对话
          </button>
        </div>

        {/* 导航 */}
        <div className="px-3 pb-2">
          <button className="w-full flex items-center gap-3 px-3 py-3 rounded-lg text-base font-medium text-gray-700 hover:bg-gray-100 transition-colors">
            <ChatBubbleLeftIcon className="w-5 h-5 text-gray-500" />
            AI 对话
          </button>
        </div>

        {/* 会话列表标题 */}
        <div className="px-4 py-2 text-sm font-medium text-gray-500 uppercase tracking-wider">
          💬 历史会话
        </div>

      {/* 会话列表 */}
      <div className="flex-1 overflow-y-auto px-3">
        {sortedSessions.map((session) => (
          <div
            key={session.id}
            className={`group relative flex items-center gap-2 px-3 py-2.5 rounded-lg cursor-pointer transition-colors mb-1 ${
              currentId === session.id
                ? 'bg-indigo-100 text-indigo-700'
                : 'hover:bg-gray-100 text-gray-700'
            }`}
            onClick={() => onSwitch(session.id)}
          >
            {/* 置顶标识 */}
            {session.pinned && (
              <ArrowUpIcon className="w-3 h-3 text-orange-500 flex-shrink-0" />
            )}
            
            {session.type === 'image' ? (
              <PhotoIcon className="w-4 h-4 flex-shrink-0" />
            ) : (
              <ChatBubbleLeftIcon className="w-4 h-4 flex-shrink-0" />
            )}
            
            {/* 编辑模式 */}
            {editingId === session.id ? (
              <div className="flex-1 flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="flex-1 px-2 py-1 text-sm border border-indigo-300 rounded focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') saveRename(session.id)
                    if (e.key === 'Escape') cancelEdit()
                  }}
                />
                <button
                  onClick={() => saveRename(session.id)}
                  className="p-1 text-green-600 hover:bg-green-100 rounded"
                >
                  <CheckIcon className="w-4 h-4" />
                </button>
                <button
                  onClick={cancelEdit}
                  className="p-1 text-red-600 hover:bg-red-100 rounded"
                >
                  <XMarkIcon className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <>
                <span className="flex-1 text-base truncate">{session.name}</span>

                {/* 更多菜单按钮 */}
                <button
                  className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-gray-200 transition-all"
                  onClick={(e) => {
                    e.stopPropagation()
                    setMenuOpen(menuOpen === session.id ? null : session.id)
                  }}
                >
                  <span className="text-gray-400">⋯</span>
                </button>

                {/* 菜单 */}
                {menuOpen === session.id && (
                  <div 
                    ref={menuRef}
                    className="absolute right-2 top-8 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-10 min-w-[140px]"
                  >
                    <button
                      onClick={(e) => startEdit(session, e)}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
                    >
                      <PencilIcon className="w-4 h-4" />
                      重命名
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        onTogglePin(session.id)
                        setMenuOpen(null)
                      }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
                    >
                      <ArrowUpIcon className="w-4 h-4" />
                      {session.pinned ? '取消置顶' : '置顶'}
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        exportConversation(session)
                      }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
                    >
                      <DocumentArrowDownIcon className="w-4 h-4" />
                      导出对话
                    </button>
                    <div className="border-t border-gray-100 my-1" />
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        onDelete(session.id)
                        setMenuOpen(null)
                      }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50"
                    >
                      <TrashIcon className="w-4 h-4" />
                      删除
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        ))}
      </div>

      {/* 底部 */}
      <div className="p-3 border-t border-gray-200">
        <div className="text-xs text-gray-400 text-center">
          vLLM-Omni
        </div>
      </div>
    </div>

    {/* 拖拽分割线 */}
    <div
      className={`w-1 cursor-col-resize hover:bg-indigo-300 transition-colors ${
        isResizing ? 'bg-indigo-400' : 'bg-transparent'
      }`}
      onMouseDown={handleMouseDown}
    />
  </div>
  )
}
