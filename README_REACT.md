# vLLM-Omni (FastAPI + React 版本)

基于 FastAPI + React 的多模态推理平台，替代 Gradio 版本。

## 项目结构

```
vLLM-Omni/
├── src/                    # FastAPI 后端
│   ├── api/
│   │   ├── routes/         # API 路由
│   │   │   ├── chat.py     # 对话接口
│   │   │   ├── sessions.py # 会话管理
│   │   │   └── multimodal.py # 多模态接口
│   │   └── router.py
│   ├── services/
│   │   └── llm_client.py   # LLM 客户端
│   ├── main.py             # FastAPI 入口
│   └── ...
├── frontend/               # React 前端
│   ├── src/
│   │   ├── components/     # React 组件
│   │   │   ├── Chat.tsx
│   │   │   ├── Sidebar.tsx
│   │   │   └── ChatArea.tsx
│   │   ├── api/            # API 客户端
│   │   └── types/          # TypeScript 类型
│   └── package.json
└── requirements.txt
```

## 快速开始

### 1. 安装后端依赖

```bash
pip install -r requirements.txt
```

### 2. 启动后端

```bash
# 从项目根目录
uvicorn src.main:app --reload --port 8000
```

后端启动后访问 http://localhost:8000/docs 查看 API 文档。

### 3. 安装前端依赖

```bash
cd frontend
npm install
```

### 4. 启动前端

```bash
npm run dev
```

前端启动后访问 http://localhost:3000

### 5. 生产构建

```bash
cd frontend
npm run build
```

构建完成后，FastAPI 会自动服务 `frontend/dist` 目录下的静态文件。

## 环境变量

创建 `.env` 文件：

```env
ALIYUN_API_KEY=your_api_key
MODEL_NAME=qwen-vl-max
```

## 功能特性

- ✅ 纯 FastAPI + React，无 Gradio 依赖
- ✅ CSS 样式完全可控（Tailwind CSS）
- ✅ 流式输出支持
- ✅ 会话管理
- ✅ 图片上传
- ✅ 完全类型安全（TypeScript）

## 与 Gradio 版本对比

| 特性 | Gradio 版本 | FastAPI + React |
|------|------------|-----------------|
| 样式定制 | ❌ 困难（类名哈希）| ✅ 完全可控 |
| 开发体验 | ⚠️ CSS 调试困难 | ✅ 热更新，调试友好 |
| 部署 | ✅ 单文件 | ⚠️ 前后端分离 |
| 维护成本 | ✅ 低 | ⚠️ 需要会 React |
| 扩展性 | ⚠️ 受限 | ✅ 完全自由 |
