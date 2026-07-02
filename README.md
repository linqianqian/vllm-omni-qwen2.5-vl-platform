# vLLM-Omni 多模态推理平台

高并发多模态推理服务平台，基于 FastAPI + Gradio + 阿里云百炼 API。

## ✨ 特性

- 💬 文本对话 (qwen2.5-7b-instruct)
- 🖼️ 多模态对话/图文理解 (qwen2.5-vl-7b-instruct)
- 🎨 美观的 Web UI 界面
- 🚀 高并发异步处理
- 📚 OpenAPI 接口文档

## 📦 安装依赖

```bash
pip install -r requirements.txt
```

## 🚀 启动服务

```bash
python run.py
```

服务启动后访问：

| 功能 | 地址 | 说明 |
|------|------|------|
| **Web UI** | http://localhost:8000 | Gradio 聊天界面 |
| **API 文档** | http://localhost:8000/docs | Swagger 接口文档 |
| **健康检查** | http://localhost:8000/health | 服务状态 |

## 📝 使用说明

1. **文本对话**：在输入框中输入问题，点击发送
2. **多模态对话**：切换到"多模态对话"标签，上传图片并输入问题

## 🔧 技术栈

- FastAPI - 高性能异步 Web 框架
- Gradio - 可视化界面
- httpx - 异步 HTTP 客户端
- Qwen2.5-VL - 阿里云百炼多模态模型
