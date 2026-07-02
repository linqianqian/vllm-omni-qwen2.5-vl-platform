export interface Session {
  id: string
  name: string
  type: 'text' | 'image'
  pinned?: boolean
  created_at: number
  updated_at: number
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  reasoning_content?: string
  image_url?: string
  timestamp: number
}

export interface ChatRequest {
  session_id: string
  message: string
  model: string
  stream?: boolean
  image_url?: string
}

export interface ChatResponse {
  id: string
  content: string
  model: string
  usage?: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
  }
}
