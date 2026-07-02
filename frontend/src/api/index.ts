import axios from 'axios'

export const api = axios.create({
  baseURL: 'http://localhost:8080/api',
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 文件上传 API（单独配置，不受默认拦截器影响）
export const uploadFile = async (file: File): Promise<{
  status: string
  filename: string
  type: string
  content: string
  length: number
}> => {
  const formData = new FormData()
  formData.append('file', file)

  const response = await axios.post(
    'http://localhost:8080/api/files/parse',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      timeout: 120000
    }
  )
  return response.data
}

// 获取支持的文件类型
export const getSupportedFileTypes = async (): Promise<{
  supported_types: Array<{ext: string, name: string, icon: string}>
  max_size_mb: number
}> => {
  const response = await api.get('/files/supported')
  return response.data
}

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    console.log('API Request:', config.method?.toUpperCase(), config.url)
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    console.error('API Error:', error.response?.data || error.message)
    return Promise.reject(error)
  }
)
