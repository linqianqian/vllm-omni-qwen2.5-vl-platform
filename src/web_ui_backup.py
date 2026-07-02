"""
vLLM-Omni 多模态推理平台 - 真实 GPU 监控版本
"""
import gradio as gr
import httpx
import random
import uuid
import time
from typing import List, Dict, Any, Optional


class Session:
    """会话对象"""
    def __init__(self, name: str = None, session_type: str = "text"):
        self.id = str(uuid.uuid4())[:8]
        self.name = name or f"会话"
        self.type = session_type
        self.messages: List[Dict[str, Any]] = []
        self.system_prompt = "你是一个有帮助的AI助手。"
        self.created_at = time.time()

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})

    def clear(self):
        self.messages = []


class AppState:
    """全局应用状态 - 支持异步并发"""
    def __init__(self, api_base="http://localhost:8080"):
        self.api_base = api_base
        self.client: Optional[httpx.AsyncClient] = None  # 改为异步客户端
        self.sessions: Dict[str, Session] = {}
        self.current_session_id: str = None
        self.request_count = 0  # 并发请求计数
        self.max_concurrent = 10  # 最大并发数
        self.stop_generating = False  # 停止生成标志
        
        # 初始化默认会话
        default_session = Session("默认会话", "text")
        self.sessions[default_session.id] = default_session
        self.current_session_id = default_session.id
        
        self.api_keys = [
            {"name": "default", "key": "sk-xxxx-xxxx", "status": "active", "daily_limit": 1000}
        ]

    async def get_client(self) -> httpx.AsyncClient:
        """获取异步HTTP客户端"""
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=self.api_base,
                timeout=httpx.Timeout(180.0),
                limits=httpx.Limits(
                    max_connections=self.max_concurrent,
                    max_keepalive_connections=20
                )
            )
        return self.client

    def get_session_choices(self):
        return [f"{'💬' if s.type == 'text' else '🖼️'} {s.name}" for s in self.sessions.values()]

    def get_current_index(self):
        ids = list(self.sessions.keys())
        return ids.index(self.current_session_id) if self.current_session_id in ids else 0

    def auto_name_session(self, message: str, image=None) -> str:
        """根据消息内容自动命名会话"""
        if not message.strip() and not image:
            return "新会话"
        
        # 优先使用图片
        if image:
            return "🖼️ 图片对话"
        
        # 文本消息：取前20个字符
        name = message.strip()[:20]
        if len(message.strip()) > 20:
            name += "..."
        return name

    def create_empty_session(self):
        """创建空白会话（等待第一条消息自动命名）"""
        session = Session("新会话", "text")
        self.sessions[session.id] = session
        self.current_session_id = session.id
        choices = self.get_session_choices()
        return choices[-1], [], "### 💬 欢迎使用"

    def switch_session(self, selected: str):
        if not selected:
            return [], "## 无会话"
        idx = self.get_session_choices().index(selected)
        session_id = list(self.sessions.keys())[idx]
        self.current_session_id = session_id
        session = self.sessions[session_id]
        history = [{"role": m["role"], "content": m["content"]} for m in session.messages]
        icon = "💬" if session.type == "text" else "🖼️"
        return history, f"### {icon} {session.name}"

    def delete_session(self):
        if self.current_session_id:
            del self.sessions[self.current_session_id]
        if self.sessions:
            self.current_session_id = list(self.sessions.keys())[0]
            session = self.sessions[self.current_session_id]
        else:
            session = Session("新会话", "text")
            self.sessions[session.id] = session
            self.current_session_id = session.id
        choices = self.get_session_choices()
        return choices[0], [], f"### 💬 {session.name}"

    def rename_session(self, new_name: str):
        if self.current_session_id and new_name.strip():
            self.sessions[self.current_session_id].name = new_name.strip()
        choices = self.get_session_choices()
        idx = self.get_current_index()
        return choices[idx]

    def clear_session(self):
        session = self.sessions.get(self.current_session_id)
        if session:
            session.clear()
        return []

    def get_gpu_metrics(self) -> Dict[str, Any]:
        """获取真实 GPU 指标"""
        try:
            from .monitoring.gpu import gpu_monitor
            summary = gpu_monitor.get_system_summary()
            
            return {
                "util": summary["total_util"],
                "mem_used": summary["total_mem_used"],
                "mem_total": summary["total_mem_total"],
                "temperature": summary["avg_temp"],
                "gpus": summary.get("gpus", []),
                "status": summary["status"],
                "device_count": summary["total_gpus"]
            }
        except Exception as e:
            print(f"获取 GPU 指标失败: {e}")
            return {
                "util": 0,
                "mem_used": 0,
                "mem_total": 24,
                "temperature": 0,
                "gpus": [],
                "status": "error",
                "device_count": 0
            }

    async def chat_stream(self, message: str, temp: float, top_p: float, max_tok: int):
        """流式文本对话 - 实时返回结果"""
        if not message.strip():
            return

        session = self.sessions.get(self.current_session_id)
        if not session:
            return

        self.request_count += 1
        client = await self.get_client()
        messages = [{"role": "system", "content": session.system_prompt}]
        for msg in session.messages:
            messages.append(msg)
        messages.append({"role": "user", "content": message})

        try:
            # 先添加用户消息
            session.add_message("user", message)

            # 流式调用 - 使用流式端点
            full_reply = ""
            async with client.stream("POST", self.api_base + "/api/chat/text/stream", json={
                "model": "qwen3.6-flash",
                "messages": messages,
                "temperature": temp,
                "top_p": top_p,
                "max_tokens": max_tok
            }) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    # 检查是否被要求停止
                    if self.stop_generating:
                        break
                    if line.startswith("data: "):
                        data = line[6:]
                        if data and data != "[DONE]":
                            try:
                                import json
                                chunk = json.loads(data)
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                if delta:
                                    content = delta.get("content", "")
                                    if content:
                                        full_reply += content
                                        yield content
                            except:
                                pass
                    elif line == "data: [DONE]":
                        break

            # 保存完整回复
            session.add_message("assistant", full_reply)

        except Exception as e:
            yield f"\n\n❌ 错误: {str(e)}"
        finally:
            self.request_count -= 1

    async def chat(self, message: str, history: list, temp: float, top_p: float, max_tok: int):
        """异步文本对话 - 支持并发（非流式）"""
        if not message.strip():
            return history, ""

        session = self.sessions.get(self.current_session_id)
        if not session:
            return history, ""

        self.request_count += 1
        client = await self.get_client()
        messages = [{"role": "system", "content": session.system_prompt}]
        for msg in session.messages:
            messages.append(msg)
        messages.append({"role": "user", "content": message})

        try:
            r = await client.post("/api/chat/text", json={
                "model": "qwen3.6-flash",
                "messages": messages,
                "temperature": temp,
                "top_p": top_p,
                "max_tokens": max_tok
            })
            r.raise_for_status()
            data = r.json()
            reply = data["choices"][0]["message"]["content"]
            session.add_message("user", message)
            session.add_message("assistant", reply)
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": reply})
            return history, ""
        except Exception as e:
            history.append({"role": "assistant", "content": f"❌ 错误: {str(e)}"})
            return history, ""
        finally:
            self.request_count -= 1

    async def chat_multimodal(self, message: str, image, history: list, thinking: bool, temp: float):
        """异步多模态对话 - 支持并发"""
        session = self.sessions.get(self.current_session_id)
        if not session or not image:
            return history, "", None

        import base64
        try:
            with open(image, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            image_url = f"data:image/jpeg;base64,{image_data}"
        except Exception as e:
            history.append({"role": "assistant", "content": f"图片读取失败: {str(e)}"})
            return history, message, None

        self.request_count += 1
        client = await self.get_client()
        content = [{"type": "image_url", "image_url": {"url": image_url}}]
        user_text = message.strip() if message else ""
        if user_text:
            content.append({"type": "text", "text": user_text})

        try:
            r = await client.post("/api/multimodal/image", json={
                "model": "qwen3-vl-flash",
                "messages": [{"role": "user", "content": content}],
                "enable_thinking": thinking,
                "temperature": temp
            })
            r.raise_for_status()
            data = r.json()
            reply = data["choices"][0]["message"]["content"]
            user_content = user_text if user_text else "[图片]"
            session.add_message("user", user_content)
            session.add_message("assistant", reply)
            history.append({"role": "user", "content": user_content})
            history.append({"role": "assistant", "content": reply})
            return history, "", None
        except Exception as e:
            history.append({"role": "assistant", "content": f"❌ 错误: {str(e)}"})
            return history, message, image
        finally:
            self.request_count -= 1


state = AppState()


def create_ui():
    # 全屏无边框 CSS
    custom_css = """
    /* 强制全屏 - 覆盖 Gradio 默认样式 */
    .gradio-container {
        max-width: 100vw !important;
        width: 100vw !important;
        height: 100vh !important;
        margin: 0 !important;
        padding: 0 !important;
        border-radius: 0 !important;
        background: #fff !important;
    }
    
    .container {
        max-width: 100% !important;
        width: 100% !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    
    /* 主布局 - 左右分栏 */
    #main-row {
        height: 100vh !important;
        margin: 0 !important;
        padding: 0 !important;
        display: flex !important;
    }
    
    /* 左侧边栏 - 固定 280px */
    .left-sidebar {
        width: 280px !important;
        min-width: 280px !important;
        max-width: 280px !important;
        height: 100vh !important;
        background: #f5f5f5 !important;
        border-right: 1px solid #e0e0e0 !important;
        padding: 20px 16px !important;
        margin: 0 !important;
        display: flex;
        flex-direction: column;
        box-sizing: border-box !important;
    }
    
    /* Logo区域 */
    .logo-area {
        padding-bottom: 20px;
        border-bottom: 1px solid #e0e0e0;
        margin-bottom: 20px;
    }
    
    /* 新建对话按钮 */
    .new-chat-btn {
        background: #fff !important;
        border: 1px solid #d0d0d0 !important;
        border-radius: 8px !important;
        color: #333 !important;
        font-weight: 500 !important;
        padding: 12px 16px !important;
        width: 100% !important;
        margin-bottom: 24px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08) !important;
    }
    .new-chat-btn:hover {
        background: #f8f8f8 !important;
        border-color: #b0b0b0 !important;
    }
    
    /* 功能导航 */
    .nav-section {
        margin-bottom: 24px;
    }
    
    .nav-btn {
        background: transparent !important;
        border: none !important;
        color: #555 !important;
        text-align: left !important;
        padding: 10px 12px !important;
        margin: 2px 0 !important;
        border-radius: 6px !important;
        font-size: 14px !important;
    }
    .nav-btn:hover {
        background: #e8e8e8 !important;
        color: #000 !important;
    }
    
    /* 会话列表 */
    .session-list {
        flex: 1;
        overflow-y: auto;
        margin-bottom: 16px;
    }
    
    .session-item {
        background: transparent !important;
        border: 1px solid transparent !important;
        border-radius: 6px !important;
        padding: 8px 12px !important;
        margin: 4px 0 !important;
        text-align: left !important;
        font-size: 13px !important;
        color: #333 !important;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .session-item:hover {
        background: #e8e8e8 !important;
    }
    .session-item.selected {
        background: #fff !important;
        border-color: #d0d0d0 !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
    }
    
    /* 右侧主区域 - 自适应 */
    .main-content {
        flex: 1;
        height: 100vh !important;
        display: flex;
        flex-direction: column;
        margin: 0 !important;
        padding: 0 !important;
        background: #fff !important;
        overflow: hidden;
    }
    
    /* 对话包装器 */
    .chat-wrapper {
        height: 100vh !important;
        display: flex;
        flex-direction: column;
    }
    
    /* 顶部标题栏 */
    .header-bar {
        height: 60px;
        padding: 0 24px;
        border-bottom: 1px solid #f0f0f0;
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: #fff;
        flex-shrink: 0;
    }
    
    /* 聊天区域 - 自适应高度 */
    .chat-area {
        flex: 1;
        overflow-y: auto;
        padding: 20px 24px;
        background: #fff;
    }
    
    #chatbot {
        height: 100% !important;
        min-height: unset !important;
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        font-size: 15px !important;
    }
    
    /* 移除 Gradio Chatbot 内部边框 */
    #chatbot .message-bubble {
        border: none !important;
        box-shadow: none !important;
    }
    
    #chatbot .message {
        border: none !important;
        background: transparent !important;
    }
    
    /* 输入框无边框 */
    .input-box {
        background: #f8f8f8 !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 12px 16px !important;
        font-size: 15px !important;
        box-shadow: inset 0 1px 2px rgba(0,0,0,0.05) !important;
    }
    
    /* 底部输入区域 - 固定底部 */
    .input-container {
        padding: 16px 24px 24px 24px;
        background: #fff;
        border-top: 1px solid #f0f0f0;
        flex-shrink: 0;
    }
    
    .input-box {
        background: #f8f8f8 !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 12px 16px !important;
        font-size: 15px !important;
        box-shadow: inset 0 1px 2px rgba(0,0,0,0.05) !important;
    }
    .input-box:focus {
        background: #fff !important;
        box-shadow: inset 0 1px 2px rgba(0,0,0,0.08), 0 0 0 2px rgba(74,144,217,0.2) !important;
    }
    
    /* 输入容器边框 */
    .input-container > div {
        border: none !important;
        box-shadow: none !important;
    }
    
    /* 工具栏 */
    .tool-bar {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-top: 8px;
    }
    
    .tool-btn {
        background: transparent !important;
        border: none !important;
        color: #666 !important;
        font-size: 13px !important;
        padding: 6px 10px !important;
        border-radius: 6px !important;
    }
    .tool-btn:hover {
        background: #f0f0f0 !important;
        color: #333 !important;
    }
    
    .send-btn {
        background: #4a90d9 !important;
        color: #fff !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 8px 20px !important;
        font-weight: 500 !important;
    }
    .send-btn:hover {
        background: #3a7bc8 !important;
    }
    
    /* 底部用户信息 */
    .user-footer {
        padding-top: 16px;
        border-top: 1px solid #e0e0e0;
        display: flex;
        align-items: center;
        gap: 10px;
        margin-top: auto;
    }
    
    .user-avatar {
        width: 32px;
        height: 32px;
        border-radius: 50%;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-weight: 600;
        font-size: 14px;
    }
    
    /* 隐藏 Gradio 默认元素 */
    footer { display: none !important; }
    .built-with { display: none !important; }
    
    /* 移除所有默认边框和阴影 */
    .gr-box, .gr-form, .gr-panel, .gr-card {
        border: none !important;
        box-shadow: none !important;
    }
    
    .gr-column {
        border: none !important;
        box-shadow: none !important;
    }
    
    .gr-row {
        border: none !important;
        box-shadow: none !important;
    }
    
    /* Chatbot 消息样式 - 无边框 */
    .message-wrap {
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
    }
    
    .message-body {
        border: none !important;
        box-shadow: none !important;
    }
    
    /* 输入框容器 */
    .gr-textbox {
        border: none !important;
        box-shadow: none !important;
    }
    
    .gr-textbox > div {
        border: none !important;
        box-shadow: none !important;
    }
    """
    
    with gr.Blocks(
        title="vLLM-Omni",
        css=custom_css
    ) as app:
        
        with gr.Row(elem_id="main-row"):
            # ========== 左侧边栏（豆包风格）==========
            with gr.Column(scale=1, min_width=260, elem_classes=["left-sidebar"]):
                # Logo
                gr.Markdown("""
                <div class="logo-area">
                    <span style="font-size: 20px; font-weight: 600; color: #1a1a1a;">🤖 vLLM-Omni</span>
                </div>
                """)
                
                # 新建对话按钮
                new_chat_btn = gr.Button("➕ 新建对话", elem_classes=["new-chat-btn"])
                
                # 功能导航
                with gr.Column():
                    gr.Markdown("<div style='color: #999; font-size: 12px; margin-bottom: 8px;'>功能</div>")
                    demo_tab = gr.Button("💬 AI 对话", variant="secondary", size="sm")
                    ops_tab = gr.Button("📊 运维监控", variant="secondary", size="sm")
                
                gr.Markdown("<div style='height: 20px;'></div>")
                
                # 历史会话
                with gr.Column(elem_classes=["session-list"]):
                    gr.Markdown("<div style='color: #999; font-size: 12px; margin-bottom: 8px;'>历史会话</div>")
                    session_list = gr.Radio(
                        choices=state.get_session_choices(),
                        value=state.get_session_choices()[0] if state.get_session_choices() else None,
                        show_label=False,
                        interactive=True
                    )
                    
                    with gr.Row():
                        delete_btn = gr.Button("🗑️", size="sm", scale=1)
                        rename_btn = gr.Button("✏️", size="sm", scale=1)
                
                gr.Markdown("<div style='flex: 1;'></div>")
                
                # 底部用户区
                gr.Markdown("""
                <div style="padding: 12px; border-top: 1px solid #e5e5e5; margin-top: auto; display: flex; align-items: center; gap: 10px;">
                    <div style="width: 32px; height: 32px; border-radius: 50%; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); display: flex; align-items: center; justify-content: center; color: white; font-weight: 600;">U</div>
                    <div>
                        <div style="font-size: 14px; color: #333; font-weight: 500;">用户</div>
                        <div style="font-size: 12px; color: #999;">在线</div>
                    </div>
                </div>
                """)
            
            # ========== 右侧主区域 ==========
            with gr.Column(scale=4, elem_classes=["main-content"]):
                
                # ===== 对话页面 =====
                with gr.Column(visible=True, elem_classes=["chat-wrapper"]) as demo_panel:
                    # 顶部标题
                    gr.Markdown("""
                    <div class="header-bar">
                        <span style="font-size: 16px; font-weight: 500; color: #333;">AI 对话</span>
                    </div>
                    """)
                    
                    # 聊天区域（自适应高度）
                    with gr.Column(elem_classes=["chat-area"]):
                        chatbot = gr.Chatbot(
                            show_label=False, 
                            elem_id="chatbot"
                        )
                    
                    # 底部输入区域（固定）
                    with gr.Column(elem_classes=["input-container"]):
                        msg_input = gr.Textbox(
                            placeholder="输入消息，按 Enter 发送...",
                            show_label=False,
                            container=False,
                            elem_classes=["input-box"]
                        )
                        
                        # 功能工具栏
                        with gr.Row(elem_classes=["tool-bar"]):
                            image_btn = gr.Button("🖼️ 图片", elem_classes=["tool-btn"], size="sm")
                            file_btn = gr.Button("📎 附件", elem_classes=["tool-btn"], size="sm")
                            gr.Column(scale=1)  # 占位
                            send_btn = gr.Button("发送", variant="primary", size="sm", min_width=80, elem_classes=["send-btn"])
                            stop_btn = gr.Button("停止", size="sm", min_width=80, visible=False)
                    
                    # 隐藏的图片上传
                    with gr.Row(visible=False):
                        image_input = gr.Image(label="", type="filepath", height=100)
                
                # ===== 运维监控页面 =====
                with gr.Column(visible=False) as ops_panel:
                    gr.Markdown("""
                    <div class="header-bar">
                        <span style="font-size: 16px; font-weight: 500; color: #333;">运维监控</span>
                    </div>
                    """)
                    
                    with gr.Row():
                        with gr.Column(scale=1, min_width=200):
                            gr.Markdown("### ⚙️ 参数设置")
                            temp_slider = gr.Slider(0.0, 2.0, 0.7, label="Temperature", step=0.1)
                            top_p_slider = gr.Slider(0.0, 1.0, 0.9, label="Top P", step=0.05)
                            max_tok_slider = gr.Slider(256, 8192, 2048, label="Max Tokens", step=256)
                        
                        with gr.Column(scale=3):
                            gr.Markdown("### 📊 GPU 监控")
                            # GPU 监控卡片
                            with gr.Row():
                                with gr.Column():
                                    gr.Markdown("""
                                    <div style='padding: 20px; background: #f8f9fa; border-radius: 12px; text-align: center;'>
                                        <div style='font-size: 13px; color: #666; margin-bottom: 8px;'>GPU 利用率</div>
                                        <div style='font-size: 32px; font-weight: 600; color: #333;'>0%</div>
                                    </div>
                                    """)
                                with gr.Column():
                                    gr.Markdown("""
                                    <div style='padding: 20px; background: #f8f9fa; border-radius: 12px; text-align: center;'>
                                        <div style='font-size: 13px; color: #666; margin-bottom: 8px;'>显存使用</div>
                                        <div style='font-size: 32px; font-weight: 600; color: #333;'>0 GB</div>
                                    </div>
                                    """)
                                with gr.Column():
                                    gr.Markdown("""
                                    <div style='padding: 20px; background: #f8f9fa; border-radius: 12px; text-align: center;'>
                                        <div style='font-size: 13px; color: #666; margin-bottom: 8px;'>温度</div>
                                        <div style='font-size: 32px; font-weight: 600; color: #333;'>0°C</div>
                                    </div>
                                    """)
                            
                            with gr.Row():
                                refresh_gpu_btn = gr.Button("🔄 刷新数据", variant="primary")
                                test_nvml_btn = gr.Button("🧪 测试 NVML")

        # ========== 事件绑定 ==========
        
        # 导航切换
        def show_demo():
            return gr.update(visible=True), gr.update(visible=False)
        
        def show_ops():
            return gr.update(visible=False), gr.update(visible=True)
        
        demo_tab.click(show_demo, outputs=[demo_panel, ops_panel])
        ops_tab.click(show_ops, outputs=[demo_panel, ops_panel])
        
        # 会话管理 - 使用 Radio 列表
        def on_session_select(selected):
            """切换会话"""
            if not selected:
                return [], "## 无会话"
            idx = state.get_session_choices().index(selected)
            session_id = list(state.sessions.keys())[idx]
            state.current_session_id = session_id
            session = state.sessions[session_id]
            history = [{"role": m["role"], "content": m["content"]} for m in session.messages]
            icon = "💬" if session.type == "text" else "🖼️"
            return history, f"### {icon} {session.name}"
        
        session_list.change(
            on_session_select,
            inputs=[session_list],
            outputs=[chatbot]
        )

        def on_new_chat():
            """新建会话 - 豆包风格直接创建空白会话"""
            choices, _, _ = state.create_empty_session()
            return state.get_session_choices(), choices
        
        new_chat_btn.click(
            on_new_chat,
            outputs=[session_list, session_list]
        )

        def on_delete():
            """删除当前会话"""
            if state.current_session_id:
                del state.sessions[state.current_session_id]
            if state.sessions:
                state.current_session_id = list(state.sessions.keys())[0]
            else:
                default = Session("新会话", "text")
                state.sessions[default.id] = default
                state.current_session_id = default.id
            choices = state.get_session_choices()
            return choices[0], choices
        
        delete_btn.click(
            on_delete,
            outputs=[session_list, session_list]
        )

        # 停止生成
        def stop_generation():
            state.stop_generating = True
            return

        # 发送消息 - 自动命名会话
        async def handle_send(msg, history, temp, top_p, max_tok, img):
            """发送消息，如果是新会话则自动命名"""
            # 重置停止标志
            state.stop_generating = False

            if not msg.strip() and not img:
                yield history, "", state.get_session_choices()[state.get_current_index()]
                return

            session = state.sessions.get(state.current_session_id)

            # 如果是新会话（名字是"新会话"），自动命名
            if session and session.name == "新会话":
                new_name = state.auto_name_session(msg, img)
                session.name = new_name
                session.type = "multimodal" if img else "text"

            # 多模态（有图片）
            if img:
                result = await state.chat_multimodal(msg, img, history, False, temp)
                choices = state.get_session_choices()
                idx = state.get_current_index()
                yield result[0], "", choices[idx]
                return

            # 流式文本对话 - 先显示用户消息
            history.append({"role": "user", "content": msg})
            history.append({"role": "assistant", "content": "🤔 思考中..."})
            yield history.copy(), "", state.get_session_choices()[state.get_current_index()]

            full_reply = ""
            async for chunk in state.chat_stream(msg, temp, top_p, max_tok):
                full_reply += chunk
                history[-1] = {"role": "assistant", "content": full_reply}
                yield history.copy(), "", state.get_session_choices()[state.get_current_index()]

            # 流式结束
            return

        send_btn.click(
            handle_send,
            inputs=[msg_input, chatbot, temp_slider, top_p_slider, max_tok_slider, image_input],
            outputs=[chatbot, msg_input, session_list]
        )
        msg_input.submit(
            handle_send,
            inputs=[msg_input, chatbot, temp_slider, top_p_slider, max_tok_slider, image_input],
            outputs=[chatbot, msg_input, session_list]
        )

        # 停止生成按钮
        stop_btn.click(
            stop_generation,
            outputs=[]
        )

        # GPU 监控刷新
        def refresh_gpu_data():
            """刷新 GPU 真实数据"""
            metrics = state.get_gpu_metrics()
            
            status_map = {
                "normal": "🟢 正常",
                "warning": "🟡 高负载",
                "overload": "🔴 过载",
                "error": "❌ 异常",
                "no_gpu": "⚠️ 无GPU"
            }
            
            gpus_info = []
            for gpu in metrics.get("gpus", []):
                gpus_info.append(f"{gpu.get('name', 'Unknown')} - {gpu.get('util', 0)}% 利用")
            
            return (
                metrics.get("util", 0),  # GPU 利用率
                round(metrics.get("mem_used", 0), 1),  # 显存使用
                metrics.get("temperature", 0),  # 温度
                status_map.get(metrics.get("status", "normal"), "🟢 正常"),  # 状态
                "\n".join(gpus_info) if gpus_info else metrics.get("gpus", [{}])[0].get("name", "Unknown") if metrics.get("gpus") else "无数据",
                str(metrics.get("device_count", 0))
            )
        
        def test_nvml():
            """测试 NVML 连接"""
            try:
                from .monitoring.gpu import gpu_monitor
                summary = gpu_monitor.get_system_summary()
                return f"✅ NVML 连接成功！检测到 {summary['total_gpus']} 个 GPU"
            except Exception as e:
                return f"❌ NVML 错误: {str(e)}"
        
        # GPU 按钮事件
        def simple_gpu_refresh():
            """简化的 GPU 刷新"""
            try:
                from .monitoring.gpu import gpu_monitor
                summary = gpu_monitor.get_system_summary()
                return f"✅ 已刷新: {summary['total_gpus']} 个 GPU"
            except Exception as e:
                return f"❌ 错误: {str(e)}"
        
        refresh_gpu_btn.click(simple_gpu_refresh, outputs=[])
        test_nvml_btn.click(test_nvml, outputs=[])

    return app


if __name__ == "__main__":
    app = create_ui()
    app.launch(server_name="0.0.0.0", server_port=7860)

# 导出给 start.py 使用
gradio_app = create_ui()
