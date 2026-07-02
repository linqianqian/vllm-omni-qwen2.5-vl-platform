import React, { useRef, useEffect, useState } from 'react'
import { PaperAirplaneIcon, PaperClipIcon, XMarkIcon, ArrowUturnLeftIcon, ClipboardIcon, CheckIcon, ArrowPathIcon, Cog6ToothIcon, ChevronDownIcon, ChevronRightIcon, ChevronUpIcon, MagnifyingGlassIcon, DocumentIcon } from '@heroicons/react/24/solid'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Message } from '../types'
import { uploadFile } from '../api'

// 文件类型定义
interface UploadedFile {
  id: string
  name: string
  type: string
  content: string
}

interface Props {
  messages: Message[]
  input: string
  setInput: (value: string) => void
  onSend: () => void
  isLoading: boolean
  image: string | null
  setImage: (value: string | null) => void
  onImageUpload: (file: File) => void
  onDeleteMessage?: (msgId: string) => void
  onRegenerate?: (msgId: string) => void
  onOpenSettings?: () => void
  uploadedFiles?: UploadedFile[]
  setUploadedFiles?: (files: UploadedFile[]) => void
}

// 用户消息内容组件（支持文件折叠）
interface UserMessageContentProps {
  msg: Message
  isExpanded: boolean
  onToggle: () => void
}

function UserMessageContent({ msg, isExpanded, onToggle }: UserMessageContentProps) {
  // 检查是否包含文件内容
  const hasFileContent = msg.content.includes('--- 文件:') && msg.content.includes('--- 结束 ---')
  
  if (!hasFileContent) {
    // 普通消息，直接显示
    return <p className="whitespace-pre-wrap text-lg leading-relaxed">{msg.content}</p>
  }
  
  // 解析文件内容（不包含 --- 结束 --- 标记）
  const fileRegex = /--- 文件: (.+?) \((.+?)\) ---\n([\s\S]*?)(?=\n--- 结束 ---)/g
  const files: Array<{ name: string; type: string; content: string }> = []
  let match
  let lastIndex = 0
  
  while ((match = fileRegex.exec(msg.content)) !== null) {
    files.push({
      name: match[1],
      type: match[2],
      content: match[3].trim()
    })
    lastIndex = match.index + match[0].length
  }
  
  // 跳过 "--- 结束 ---" 标记，提取用户输入的问题
  let userQuestion = msg.content.substring(lastIndex).trim()
  userQuestion = userQuestion.replace(/^--- 结束 ---\s*/m, '').trim()
  
  return (
    <div className="space-y-3">
      {/* 文件列表 - 使用不同的背景色 */}
      {files.map((file, index) => (
        <div key={index} className="bg-blue-500/30 rounded-lg overflow-hidden border border-blue-400/30">
          {/* 文件标题栏 */}
          <button
            onClick={onToggle}
            className="w-full flex items-center justify-between px-3 py-2 text-sm hover:bg-blue-500/40 transition-colors"
          >
            <div className="flex items-center gap-2">
              <DocumentIcon className="w-4 h-4 text-blue-200" />
              <span className="font-medium text-white">{file.name}</span>
              <span className="text-blue-200 text-xs">({file.type})</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-blue-200">
                {isExpanded ? '点击折叠' : '点击展开'}
              </span>
              {isExpanded ? (
                <ChevronDownIcon className="w-4 h-4" />
              ) : (
                <ChevronRightIcon className="w-4 h-4" />
              )}
            </div>
          </button>
          
          {/* 文件内容（可折叠）- 更深的背景色 */}
          {isExpanded && (
            <div className="px-3 py-2 bg-slate-800/50 text-sm max-h-60 overflow-y-auto">
              <pre className="whitespace-pre-wrap font-mono text-slate-200 text-xs">{file.content}</pre>
            </div>
          )}
        </div>
      ))}
      
      {/* 用户问题 - 保持原有的紫色背景 */}
      {userQuestion && (
        <p className="whitespace-pre-wrap text-lg leading-relaxed">{userQuestion}</p>
      )}
    </div>
  )
}

export default function ChatArea({
  messages,
  input,
  setInput,
  onSend,
  isLoading,
  image,
  setImage,
  onImageUpload,
  onDeleteMessage,
  onRegenerate,
  onOpenSettings,
  uploadedFiles = [],
  setUploadedFiles
}: Props) {
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const docInputRef = useRef<HTMLInputElement>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [copiedCode, setCopiedCode] = useState<string | null>(null)
  const [expandedReasoning, setExpandedReasoning] = useState<Set<string>>(new Set())
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set())
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<number[]>([])
  const [currentResultIndex, setCurrentResultIndex] = useState(0)
  const [isUploading, setIsUploading] = useState(false)

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 搜索消息
  useEffect(() => {
    if (searchQuery.trim()) {
      const results: number[] = []
      messages.forEach((msg, index) => {
        if (msg.content.toLowerCase().includes(searchQuery.toLowerCase())) {
          results.push(index)
        }
      })
      setSearchResults(results)
      setCurrentResultIndex(0)
      
      // 滚动到第一个结果
      if (results.length > 0) {
        setTimeout(() => {
          const element = document.getElementById(`message-${messages[results[0]].id}`)
          element?.scrollIntoView({ behavior: 'smooth', block: 'center' })
        }, 100)
      }
    } else {
      setSearchResults([])
    }
  }, [searchQuery, messages])

  // 跳转到下一个搜索结果
  const goToNextResult = () => {
    if (searchResults.length > 0) {
      const nextIndex = (currentResultIndex + 1) % searchResults.length
      setCurrentResultIndex(nextIndex)
      const msgIndex = searchResults[nextIndex]
      const element = document.getElementById(`message-${messages[msgIndex].id}`)
      element?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }

  // 跳转到上一个搜索结果
  const goToPrevResult = () => {
    if (searchResults.length > 0) {
      const prevIndex = (currentResultIndex - 1 + searchResults.length) % searchResults.length
      setCurrentResultIndex(prevIndex)
      const msgIndex = searchResults[prevIndex]
      const element = document.getElementById(`message-${messages[msgIndex].id}`)
      element?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }

  // 高亮搜索关键词

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 处理图片选择
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      onImageUpload(file)
    }
  }

  // 处理文档上传
  const handleDocChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !setUploadedFiles) return

    // 检查文件大小 (10MB)
    if (file.size > 10 * 1024 * 1024) {
      alert('文件大小不能超过 10MB')
      e.target.value = ''
      return
    }

    setIsUploading(true)
    try {
      const result = await uploadFile(file)
      const newFile: UploadedFile = {
        id: Date.now().toString(),
        name: result.filename,
        type: result.type,
        content: result.content
      }
      setUploadedFiles([...uploadedFiles, newFile])
    } catch (err: any) {
      console.error('文件上传失败:', err)
      const errorMsg = err?.response?.data?.detail || '文件上传失败，请检查后端服务是否正常运行'
      alert(errorMsg)
    } finally {
      setIsUploading(false)
      e.target.value = ''
    }
  }

  // 移除已上传的文件
  const removeFile = (fileId: string) => {
    if (setUploadedFiles) {
      setUploadedFiles(uploadedFiles.filter(f => f.id !== fileId))
    }
  }

  // 处理回车发送
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
    }
  }

  // 复制消息
  const copyMessage = async (msg: Message) => {
    try {
      await navigator.clipboard.writeText(msg.content)
      setCopiedId(msg.id)
      setTimeout(() => setCopiedId(null), 2000)
    } catch (err) {
      console.error('复制失败:', err)
    }
  }

  // 复制代码
  const copyCode = async (code: string, lang: string) => {
    try {
      await navigator.clipboard.writeText(code)
      setCopiedCode(lang)
      setTimeout(() => setCopiedCode(null), 2000)
    } catch (err) {
      console.error('复制代码失败:', err)
    }
  }

  // 渲染代码块
  const renderCodeBlock = (code: string, language: string) => {
    return (
      <div className="relative group my-2">
        <div className="bg-gray-800 rounded-lg overflow-hidden">
          {/* 代码头 */}
          <div className="flex items-center justify-between px-3 py-1.5 bg-gray-700 text-xs text-gray-300">
            <span>{language || 'code'}</span>
            <button
              onClick={() => copyCode(code, language)}
              className="flex items-center gap-1 hover:text-white transition-colors"
            >
              {copiedCode === language ? (
                <>
                  <CheckIcon className="w-3 h-3 text-green-400" />
                  <span className="text-green-400">已复制</span>
                </>
              ) : (
                <>
                  <ClipboardIcon className="w-3 h-3" />
                  <span>复制</span>
                </>
              )}
            </button>
          </div>
          {/* 代码内容 */}
          <pre className="p-4 overflow-x-auto text-sm text-gray-100">
            <code>{code}</code>
          </pre>
        </div>
      </div>
    )
  }

  // 自定义 Markdown 渲染组件
  const MarkdownComponents = {
    code({ node, inline, className, children, ...props }: any) {
      const match = /language-(\w+)/.exec(className || '')
      const code = String(children).replace(/\n$/, '')
      
      if (!inline && match) {
        return renderCodeBlock(code, match[1])
      }
      
      return (
        <code className={`bg-gray-100 px-1.5 py-0.5 rounded text-sm font-mono ${className || ''}`} {...props}>
          {children}
        </code>
      )
    }
  }

  return (
    <div className="flex-1 flex flex-col h-full bg-white">
      {/* 标题栏 */}
      <div className="h-16 border-b border-gray-200 flex items-center justify-between px-6">
        <h2 className="text-xl font-medium text-gray-800">💬 AI 对话</h2>
        <div className="flex items-center gap-3">
          {/* 搜索框 */}
          <div className="flex items-center gap-1 bg-gray-100 rounded-lg px-2 py-1">
            <MagnifyingGlassIcon className="w-4 h-4 text-gray-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索消息..."
              className="bg-transparent border-none outline-none text-sm w-32 placeholder-gray-400"
            />
            {searchQuery && (
              <span className="text-xs text-gray-500">
                {searchResults.length > 0 ? `${currentResultIndex + 1}/${searchResults.length}` : '0/0'}
              </span>
            )}
          </div>
          {searchResults.length > 1 && (
            <div className="flex items-center gap-1">
              <button
                onClick={goToPrevResult}
                className="p-1 text-gray-500 hover:text-indigo-600 rounded"
                title="上一个"
              >
                <ChevronUpIcon className="w-4 h-4" />
              </button>
              <button
                onClick={goToNextResult}
                className="p-1 text-gray-500 hover:text-indigo-600 rounded"
                title="下一个"
              >
                <ChevronDownIcon className="w-4 h-4" />
              </button>
            </div>
          )}
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="p-1 text-gray-400 hover:text-red-500"
              title="清除搜索"
            >
              <XMarkIcon className="w-4 h-4" />
            </button>
          )}
          
          {/* 停止生成按钮 */}
          {isLoading && (
            <button
              onClick={() => window.dispatchEvent(new CustomEvent('stopGeneration'))}
              className="flex items-center gap-1 px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 rounded-lg transition-colors"
            >
              <XMarkIcon className="w-4 h-4" />
              停止
            </button>
          )}
          {/* 设置按钮 */}
          {onOpenSettings && (
            <button
              onClick={onOpenSettings}
              className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
              title="设置"
            >
              <Cog6ToothIcon className="w-4 h-4" />
              设置
            </button>
          )}
          <div className="w-px h-4 bg-gray-300 mx-1"></div>
          <div className="w-2 h-2 rounded-full bg-green-500"></div>
          <span className="text-sm text-gray-500">在线</span>
        </div>
      </div>

      {/* 消息区域 */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <div className="text-6xl mb-4">🤖</div>
            <p className="text-lg">开始一个新的对话吧</p>
          </div>
        )}

        {messages.map((msg, index) => {
          console.log('渲染消息:', msg.id, '角色:', msg.role, '是否是用户:', msg.role === 'user')
          // 检查是否在搜索结果中
          const isInSearchResults = searchQuery && searchResults.includes(index)
          const isCurrentResult = isInSearchResults && searchResults[currentResultIndex] === index
          
          return (
          <div
            id={`message-${msg.id}`}
            key={msg.id}
            className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''} ${
              isCurrentResult ? 'bg-yellow-100 rounded-lg p-2 -mx-2' : ''
            }`}
          >
            {/* 头像 */}
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium flex-shrink-0 ${
                msg.role === 'user'
                  ? 'bg-gradient-to-br from-indigo-500 to-purple-600 text-white'
                  : 'bg-gradient-to-br from-green-500 to-teal-600 text-white'
              }`}
            >
              {msg.role === 'user' ? 'U' : 'AI'}
            </div>

            {/* 消息内容 */}
            <div className="flex flex-col gap-1 max-w-[75%]">
              {/* 用户图片预览 */}
              {msg.role === 'user' && msg.image_url && (
                <div className="mb-2">
                  <img
                    src={msg.image_url}
                    alt="用户图片"
                    className="max-w-[200px] max-h-[150px] rounded-lg object-cover"
                  />
                </div>
              )}

              {/* 思考过程（可折叠） */}
              {msg.role === 'assistant' && msg.reasoning_content && (
                <div className="mb-2">
                  <button
                    onClick={() => {
                      const newExpanded = new Set(expandedReasoning)
                      if (newExpanded.has(msg.id)) {
                        newExpanded.delete(msg.id)
                      } else {
                        newExpanded.add(msg.id)
                      }
                      setExpandedReasoning(newExpanded)
                    }}
                    className="flex items-center gap-1 text-xs text-gray-500 hover:text-indigo-600 transition-colors mb-1"
                  >
                    {expandedReasoning.has(msg.id) ? (
                      <>
                        <ChevronDownIcon className="w-3 h-3" />
                        隐藏思考过程
                      </>
                    ) : (
                      <>
                        <ChevronRightIcon className="w-3 h-3" />
                        查看思考过程
                      </>
                    )}
                  </button>
                  {expandedReasoning.has(msg.id) && (
                    <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-sm text-gray-600">
                      <div className="text-xs text-yellow-600 font-medium mb-1">💭 思考过程</div>
                      <div className="whitespace-pre-wrap">{msg.reasoning_content}</div>
                    </div>
                  )}
                </div>
              )}

              <div
                className={`rounded-2xl px-5 py-4 ${
                  msg.role === 'user'
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-100 text-gray-800'
                }`}
              >
                {msg.role === 'assistant' ? (
                  <div className="markdown-content prose prose-base max-w-none">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents}>
                      {msg.content}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <UserMessageContent 
                    msg={msg} 
                    isExpanded={expandedFiles.has(msg.id)}
                    onToggle={() => {
                      const newExpanded = new Set(expandedFiles)
                      if (newExpanded.has(msg.id)) {
                        newExpanded.delete(msg.id)
                      } else {
                        newExpanded.add(msg.id)
                      }
                      setExpandedFiles(newExpanded)
                    }}
                  />
                )}
              </div>
              
              {/* 消息操作按钮 */}
              <div className={`flex gap-2 self-end ${msg.role === 'user' ? '' : ''}`}>
                {/* AI消息的重新生成按钮 */}
                {msg.role === 'assistant' && onRegenerate && !isLoading && (
                  <button
                    onClick={() => {
                      if (confirm('重新生成将删除该条及之后的所有消息，确定吗？')) {
                        onRegenerate(msg.id)
                      }
                    }}
                    className="flex items-center gap-1 px-2 py-1 text-xs text-gray-400 hover:text-indigo-500 transition-colors"
                    style={{ opacity: 0.6 }}
                    onMouseEnter={(e) => e.currentTarget.style.opacity = '1'}
                    onMouseLeave={(e) => e.currentTarget.style.opacity = '0.6'}
                    title="重新生成"
                  >
                    <ArrowPathIcon className="w-3 h-3" />
                    重新生成
                  </button>
                )}
                
                {/* AI消息的复制按钮 */}
                {msg.role === 'assistant' && (
                  <button
                    onClick={() => copyMessage(msg)}
                    className="flex items-center gap-1 px-2 py-1 text-xs text-gray-400 hover:text-indigo-500 transition-colors"
                    style={{ opacity: 0.6 }}
                    onMouseEnter={(e) => e.currentTarget.style.opacity = '1'}
                    onMouseLeave={(e) => e.currentTarget.style.opacity = '0.6'}
                  >
                    {copiedId === msg.id ? (
                      <>
                        <CheckIcon className="w-3 h-3 text-green-500" />
                        <span className="text-green-500">已复制</span>
                      </>
                    ) : (
                      <>
                        <ClipboardIcon className="w-3 h-3" />
                        复制
                      </>
                    )}
                  </button>
                )}
                
                {/* 消息的撤销按钮 */}
                {onDeleteMessage && (
                  <button
                    onClick={() => {
                      console.log('撤销按钮被点击, 消息ID:', msg.id)
                      onDeleteMessage?.(msg.id)
                    }}
                    className="flex items-center gap-1 px-2 py-1 text-xs text-gray-400 hover:text-red-500 transition-colors"
                    style={{ opacity: 0.6 }}
                    onMouseEnter={(e) => e.currentTarget.style.opacity = '1'}
                    onMouseLeave={(e) => e.currentTarget.style.opacity = '0.6'}
                  >
                    <ArrowUturnLeftIcon className="w-3 h-3" />
                    撤销
                  </button>
                )}
              </div>
            </div>
          </div>
        )})}

        <div ref={messagesEndRef} />
      </div>

      {/* 输入区域 */}
      <div className="border-t border-gray-200 p-4">
        {/* 图片预览 */}
        {image && (
          <div className="mb-3 flex items-center gap-2">
            <div className="relative">
              <img
                src={image}
                alt="Preview"
                className="h-16 w-auto rounded-lg object-cover"
              />
              <button
                onClick={() => setImage(null)}
                className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 text-white rounded-full flex items-center justify-center text-xs"
              >
                <XMarkIcon className="w-3 h-3" />
              </button>
            </div>
          </div>
        )}

        {/* 文档文件列表 */}
        {uploadedFiles.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-2">
            {uploadedFiles.map(file => (
              <div
                key={file.id}
                className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 border border-blue-200 rounded-lg"
              >
                <DocumentIcon className="w-4 h-4 text-blue-600" />
                <span className="text-sm text-blue-800 truncate max-w-[200px]">{file.name}</span>
                <button
                  onClick={() => removeFile(file.id)}
                  className="text-blue-400 hover:text-red-500 transition-colors"
                >
                  <XMarkIcon className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* 输入框 */}
        <div className="flex items-end gap-2 bg-gray-50 rounded-2xl border border-gray-200 p-2">
          {/* 图片上传按钮 */}
          <button
            onClick={() => fileInputRef.current?.click()}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded-xl transition-colors"
            title="上传图片"
          >
            <PaperClipIcon className="w-5 h-5" />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleFileChange}
            className="hidden"
          />

          {/* 文档上传按钮 */}
          <button
            onClick={() => docInputRef.current?.click()}
            disabled={isUploading}
            className={`p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded-xl transition-colors ${
              isUploading ? 'opacity-50 cursor-not-allowed' : ''
            }`}
            title="上传文档 (PDF/Word/Excel)"
          >
            {isUploading ? (
              <span className="w-5 h-5 animate-spin">⏳</span>
            ) : (
              <DocumentIcon className="w-5 h-5" />
            )}
          </button>
          <input
            ref={docInputRef}
            type="file"
            accept=".pdf,.docx,.doc,.xlsx,.xls,.txt,.md,.py,.js,.html,.css,.json,.csv"
            onChange={handleDocChange}
            disabled={isUploading}
            className="hidden"
          />

          {/* 文本输入 */}
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息，Enter 发送..."
            rows={1}
            className="flex-1 bg-transparent border-none outline-none resize-none py-3 px-3 text-base max-h-32"
            style={{ minHeight: '28px' }}
          />

          {/* 发送按钮 */}
          <button
            onClick={onSend}
            disabled={(!input.trim() && !image && uploadedFiles.length === 0) || isLoading || isUploading}
            className={`p-2.5 rounded-xl transition-colors ${
              (input.trim() || image || uploadedFiles.length > 0) && !isLoading && !isUploading
                ? 'bg-indigo-600 text-white hover:bg-indigo-700'
                : 'bg-gray-200 text-gray-400 cursor-not-allowed'
            }`}
          >
            <PaperAirplaneIcon className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  )
}
