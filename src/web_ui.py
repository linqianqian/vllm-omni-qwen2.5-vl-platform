"""
vLLM-Omni 多模态推理平台 - 高并发多会话版本
"""
import gradio as gr
import httpx
import uuid
import time
import base64
import json
import os
import asyncio
from typing import List, Dict, Any, Optional

# 添加项目路径
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.session_db import SessionDB


class Session:
    def __init__(self, name: str = None, session_type: str = "text"):
        self.id = str(uuid.uuid4())[:8]
        self.name = name or f"新会话"
        self.type = session_type
        self.messages: List[Dict[str, Any]] = []
        self.system_prompt = "你是一个有帮助的AI助手。"
        self.created_at = time.time()
        self._app_state = None
        
        # 高并发支持：每个会话独立控制
        self.stop_flag = False          # 独立停止标志
        self.is_generating = False      # 是否正在生成
        self.partial_reply = ""         # 已累积的回复内容

    def set_app_state(self, app_state):
        self._app_state = app_state

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        if self._app_state:
            self._app_state._save_session(self.id)

    def clear(self):
        self.messages = []
        if self._app_state:
            self._app_state._save_session(self.id)


class AppState:
    def __init__(self, api_base="http://localhost:8080"):
        self.api_base = api_base
        self.client: Optional[httpx.AsyncClient] = None
        self.sessions: Dict[str, Session] = {}
        self.current_session_id: str = None
        self.request_count = 0
        self.max_concurrent = 10
        self.stop_generating = False
        self._background_tasks: Dict[str, dict] = {}  # session_id -> {task, partial_history}

        # 初始化数据库
        self.db = SessionDB()
        self._load_sessions()

        # 性能监控指标
        self.metrics = {
            "total_requests": 0,
            "total_tokens": 0,
            "avg_latency_ms": 0,
            "qps": 0,
            "active_requests": 0,
            "error_count": 0,
            "latency_history": [],
            "start_time": time.time()
        }
        
        # 请求链路追踪
        self.request_traces = {}
        self.trace_counter = 0

    async def get_client(self) -> httpx.AsyncClient:
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=self.api_base,
                timeout=httpx.Timeout(180.0),
                limits=httpx.Limits(max_connections=self.max_concurrent, max_keepalive_connections=20)
            )
        return self.client

    def _load_sessions(self):
        try:
            db_sessions = self.db.load_all_sessions()
            for sess_data in db_sessions:
                name = sess_data.get("name") or "新会话"
                session = Session(name, sess_data.get("type", "text"))
                session.id = sess_data["id"]
                session.system_prompt = sess_data.get("system_prompt", "你是一个有帮助的AI助手。")
                session.created_at = sess_data.get("created_at", time.time())
                session.messages = self.db.load_session_messages(sess_data["id"])
                session.set_app_state(self)
                self.sessions[session.id] = session
            if not self.sessions:
                default_session = Session("新会话", "text")
                default_session.set_app_state(self)
                self.sessions[default_session.id] = default_session
                self.current_session_id = default_session.id
            else:
                self.current_session_id = list(self.sessions.keys())[0]
        except Exception as e:
            print(f"⚠️  加载会话失败: {e}")
            default_session = Session("新会话", "text")
            default_session.set_app_state(self)
            self.sessions[default_session.id] = default_session
            self.current_session_id = default_session.id

    def _save_session(self, session_id: str):
        session = self.sessions.get(session_id)
        if not session:
            return
        try:
            self.db.save_session(
                session.id, session.name, session.type,
                session.system_prompt, session.created_at, session.messages
            )
        except Exception as e:
            print(f"⚠️  保存会话失败: {e}")

    # ---- 会话管理 ----

    def get_session_choices(self):
        choices = []
        for s in self.sessions.values():
            name = s.name if s.name else "新会话"
            icon = "💬" if s.type == "text" else "🖼️"
            status = " ⏳" if s.is_generating else ""
            choices.append(f"{icon} {name}{status}")
        return choices

    def get_current_index(self):
        """获取当前会话索引"""
        for idx, sid in enumerate(self.sessions.keys()):
            if sid == self.current_session_id:
                return idx
        return 0

    def get_session_list_html(self):
        """生成豆包风格的会话列表 HTML，带更多菜单"""
        current_id = self.current_session_id
        items = []
        for idx, s in enumerate(self.sessions.values()):
            sid = s.id
            name = s.name if s.name else "新会话"
            icon = "💬" if s.type == "text" else "🖼️"
            is_active = "active" if sid == current_id else ""
            items.append('<div class="session-item ' + is_active + '">'
                '<button type="button" class="session-main" onclick="window.switchSession(' + str(idx) + ')">'
                '<span class="session-icon">' + icon + '</span>'
                '<span class="session-name">' + name + '</span>'
                '</button>'
                '<button class="session-more-btn" onclick="toggleMenu(event, \'' + sid + '\')">⋯</button>'
                '<div class="session-menu" id="menu-' + sid + '" style="display:none!important;visibility:hidden!important;opacity:0!important;">'
                '<div class="menu-item" onclick="sessionAction(\'pin\', \'' + sid + '\', event)">📌 置顶</div>'
                '<div class="menu-item" onclick="sessionAction(\'share\', \'' + sid + '\', event)">🔗 分享</div>'
                '<div class="menu-item" onclick="sessionAction(\'rename\', \'' + sid + '\', event)">✏️ 重命名</div>'
                '<div class="menu-item" onclick="sessionAction(\'report\', \'' + sid + '\', event)">⚠️ 举报</div>'
                '<div class="menu-item menu-item-delete" onclick="sessionAction(\'delete\', \'' + sid + '\', event)">🗑️ 删除</div>'
                '</div>'
                '</div>')
        return '<div class="session-list-container">' + ''.join(items) + '</div>'

    def auto_name_session(self, message: str, image=None) -> str:
        if not message.strip() and not image:
            return "新会话"
        if image:
            return "🖼️ 图片对话"
        name = message.strip()[:20]
        if len(message.strip()) > 20:
            name += "..."
        return name

    def create_empty_session(self):
        session = Session("新会话", "text")
        session.set_app_state(self)
        self.sessions[session.id] = session
        self.current_session_id = session.id
        self._save_session(session.id)
        choices = self.get_session_choices()
        return choices, [], "### 新会话"

    def switch_session_by_index(self, idx: int):
        """通过索引切换会话"""
        sessions_list = list(self.sessions.keys())
        if idx < 0 or idx >= len(sessions_list):
            return [], "## 无会话"
        session_id = sessions_list[idx]
        self.current_session_id = session_id
        session = self.sessions[session_id]
        history = [{"role": m["role"], "content": m["content"]} for m in session.messages]
        if session.is_generating and session.partial_reply:
            if history and history[-1].get("role") == "assistant" and history[-1].get("content") == "🤔 思考中...":
                history[-1] = {"role": "assistant", "content": session.partial_reply}
            else:
                history.append({"role": "assistant", "content": session.partial_reply})
        icon = "💬" if session.type == "text" else "🖼️"
        return history, f"### {icon} {session.name}"

    def switch_session(self, selected: str):
        if not selected:
            return [], "## 无会话"
        choices = self.get_session_choices()
        if selected not in choices:
            return [], "## 无会话"
        idx = choices.index(selected)
        session_id = list(self.sessions.keys())[idx]
        self.current_session_id = session_id
        session = self.sessions[session_id]
        # 如果当前会话在后台生成中，读取 partial_reply 作为最后一条
        history = [{"role": m["role"], "content": m["content"]} for m in session.messages]
        if session.is_generating and session.partial_reply:
            # 找一个占位的"思考中"消息或已累积的回复
            if history and history[-1].get("role") == "assistant" and history[-1].get("content") == "🤔 思考中...":
                history[-1] = {"role": "assistant", "content": session.partial_reply}
            else:
                history.append({"role": "assistant", "content": session.partial_reply})
        icon = "💬" if session.type == "text" else "🖼️"
        return history, f"### {icon} {session.name}"

    def delete_session(self):
        if self.current_session_id:
            self.db.delete_session(self.current_session_id)
            del self.sessions[self.current_session_id]
        if self.sessions:
            self.current_session_id = list(self.sessions.keys())[0]
            session = self.sessions[self.current_session_id]
        else:
            session = Session("新会话", "text")
            session.set_app_state(self)
            self.sessions[session.id] = session
            self.current_session_id = session.id
        choices = self.get_session_choices()
        return choices[0], [], f"### {session.name}"

    # ---- 流式推理（后台任务版，不阻塞UI） ----

    async def _run_background_stream(self, session_id: str, message: str, image_path: str):
        """后台运行流式推理，结果逐步写入 session.partial_reply"""
        session = self.sessions.get(session_id)
        if not session:
            return
        
        session.is_generating = True
        session.stop_flag = False
        session.partial_reply = ""
        had_error = False
        
        self.metrics["total_requests"] += 1
        self.metrics["active_requests"] += 1
        start_time = time.time()
        
        client = await self.get_client()
        
        if image_path:
            # 多模态
            image_base64 = ""
            try:
                with open(image_path, "rb") as f:
                    image_base64 = base64.b64encode(f.read()).decode('utf-8')
            except Exception as e:
                session.partial_reply = f"❌ 图片读取错误: {str(e)}"
                session.is_generating = False
                self.metrics["active_requests"] -= 1
                self.metrics["error_count"] += 1
                return
            
            content = []
            if image_base64:
                content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}})
            if message.strip():
                content.append({"type": "text", "text": message})
            
            messages = [{"role": "user", "content": content}]
            
            try:
                full_reply = ""
                async with client.stream("POST", self.api_base + "/api/multimodal/image/stream", json={
                    "model": "qwen3-vl-flash", "messages": messages, "stream": True, "enable_thinking": False
                }) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if session.stop_flag:
                            break
                        if line.startswith("data: "):
                            data = line[6:]
                            if data and data != "[DONE]":
                                try:
                                    chunk = json.loads(data)
                                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                                    if delta:
                                        content_text = delta.get("content", "")
                                        if content_text:
                                            full_reply += content_text
                                            session.partial_reply = full_reply
                                except:
                                    pass
                        elif line == "data: [DONE]":
                            break
                if not session.stop_flag:
                    session.add_message("assistant", full_reply)
            except Exception as e:
                self.metrics["error_count"] += 1
                session.partial_reply = f"❌ 错误: {str(e)}"
        else:
            # 纯文本
            messages = [{"role": "system", "content": session.system_prompt}]
            for msg in session.messages:
                messages.append(msg)
            messages.append({"role": "user", "content": message})
            
            try:
                full_reply = ""
                async with client.stream("POST", self.api_base + "/api/chat/text/stream", json={
                    "model": "qwen3.6-flash", "messages": messages,
                    "temperature": 0.7, "top_p": 0.9, "max_tokens": 2048
                }) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if session.stop_flag:
                            break
                        line = line.strip()
                        if line.startswith("data:"):
                            data = line[5:].strip()
                            if data and data != "[DONE]":
                                try:
                                    chunk = json.loads(data)
                                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                                    if delta:
                                        content_text = delta.get("content", "")
                                        if content_text:
                                            full_reply += content_text
                                            session.partial_reply = full_reply
                                except Exception as e:
                                    print(f"解析 chunk 错误: {e}, data: {data[:100]}")
                                    pass
                            elif data == "[DONE]":
                                break
                if not session.stop_flag:
                    session.add_message("assistant", full_reply)
            except Exception as e:
                self.metrics["error_count"] += 1
                session.partial_reply = f"❌ 错误: {str(e)}"
        
        # 更新指标
        self.metrics["active_requests"] -= 1
        latency = (time.time() - start_time) * 1000
        self.metrics["latency_history"].append(latency)
        if len(self.metrics["latency_history"]) > 100:
            self.metrics["latency_history"].pop(0)
        self.metrics["avg_latency_ms"] = sum(self.metrics["latency_history"]) / len(self.metrics["latency_history"])
        self.metrics["total_tokens"] += len(session.partial_reply)
        
        session.is_generating = False
        # 从后台任务记录中移除
        if session_id in self._background_tasks:
            del self._background_tasks[session_id]

    def start_background_stream(self, session_id: str, message: str, image_path: str):
        """启动后台流式任务（非阻塞）"""
        if session_id in self._background_tasks:
            return
        # 使用 asyncio.ensure_future 确保在任何上下文中都能运行
        task = asyncio.ensure_future(self._run_background_stream(session_id, message, image_path))
        self._background_tasks[session_id] = {"task": task}

    def stop_session(self, session_id: str):
        """停止指定会话的生成"""
        session = self.sessions.get(session_id)
        if session:
            session.stop_flag = True

    def is_any_generating(self) -> bool:
        """是否有会话在生成"""
        return any(s.is_generating for s in self.sessions.values())

    def get_generating_count(self) -> int:
        """获取正在生成的会话数"""
        return sum(1 for s in self.sessions.values() if s.is_generating)

    def update_qps(self):
        if self.metrics["total_requests"] > 0:
            uptime = time.time() - self.metrics["start_time"]
            self.metrics["qps"] = self.metrics["total_requests"] / uptime if uptime > 0 else 0
        return self.metrics["qps"]

    # ---- 并发压测 ----

    async def run_concurrent_benchmark(self, count: int = 5, message: str = "你好，请简单介绍一下你自己"):
        """并发压测：同时启动多个会话进行推理"""
        results = {"success": 0, "failed": 0, "latencies": []}
        sessions = list(self.sessions.keys())

        async def bench_one(session_id):
            session = self.sessions.get(session_id)
            if not session:
                return
            self.metrics["total_requests"] += 1
            self.metrics["active_requests"] += 1
            start = time.time()
            client = await self.get_client()
            try:
                payload = {
                    "model": "qwen3.6-flash",
                    "messages": [
                        {"role": "system", "content": "你是一个有帮助的AI助手。"},
                        {"role": "user", "content": message}
                    ],
                    "temperature": 0.7, "top_p": 0.9, "max_tokens": 512
                }
                async with client.stream("POST", self.api_base + "/api/chat/text/stream", json=payload) as resp:
                    resp.raise_for_status()
                    async for _ in resp.aiter_lines():
                        pass
                results["success"] += 1
            except Exception as e:
                results["failed"] += 1
                self.metrics["error_count"] += 1
            finally:
                lat = (time.time() - start) * 1000
                results["latencies"].append(lat)
                self.metrics["active_requests"] -= 1

        # 获取所有空闲会话
        available = [s.id for s in self.sessions.values() if not s.is_generating]
        if len(available) < count:
            available = list(self.sessions.keys())
        
        selected = available[:count]
        tasks = [bench_one(sid) for sid in selected]
        await asyncio.gather(*tasks)

        avg_lat = sum(results["latencies"]) / len(results["latencies"]) if results["latencies"] else 0
        return {
            "success": results["success"],
            "failed": results["failed"],
            "avg_latency_ms": f"{avg_lat:.1f}",
            "concurrency": count
        }


state = AppState()


def get_metrics_display():
    state.update_qps()
    metrics = state.metrics
    uptime = time.time() - metrics["start_time"]
    generating_count = state.get_generating_count()
    
    latency_sorted = sorted(metrics["latency_history"])
    p99_latency = latency_sorted[int(len(latency_sorted) * 0.99)] if latency_sorted else 0
    throughput = metrics["total_tokens"] / uptime if uptime > 0 else 0
    
    return f"""
### 📊 运维监控

**基础指标**
- 总请求数：{metrics["total_requests"]}
- 活跃请求：{metrics["active_requests"]}
- 并发生成中：{generating_count} 会话
- 错误次数：{metrics["error_count"]}
- 运行时长：{int(uptime // 60)}:{int(uptime % 60):02d}

**性能指标**
- QPS：{metrics["qps"]:.2f}
- 平均延迟：{metrics["avg_latency_ms"]:.1f} ms
- P99 延迟：{p99_latency:.1f} ms
- 吞吐量：{throughput:.1f} tokens/s
- 总 Token：{metrics["total_tokens"]}
"""


def export_chat_to_markdown(session_id: str) -> str:
    session = state.sessions.get(session_id)
    if not session:
        return "# 会话不存在\n"
    content = f"# 对话记录：{session.name}\n\n"
    content += f"- 会话ID：{session.id}\n"
    content += f"- 创建时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(session.created_at))}\n"
    content += f"- 消息数量：{len(session.messages)}\n\n---\n\n"
    for i, msg in enumerate(session.messages, 1):
        role = "用户" if msg.get("role") == "user" else "助手"
        content += f"## {role} ({i})\n\n{msg.get('content', '')}\n\n---\n\n"
    return content


def create_ui():
    custom_css = """
    * { box-sizing: border-box !important; margin: 0 !important; padding: 0 !important; }
    body { background: #f7f8fa !important; }
    .gradio-container { max-width: 100vw !important; width: 100vw !important; height: 100vh !important; margin: 0 !important; padding: 0 !important; font-size: 20px !important; background: #fff !important; }
    #main-row { height: 100vh !important; margin: 0 !important; padding: 0 !important; gap: 0 !important; position: relative !important; }
    
    /* ===== 侧边栏固定 ===== */
    #main-row { display: flex !important; }
    
    /* 侧边栏独立滚动 */
    #sidebar { 
        width: 180px !important; 
        min-width: 180px !important;
        max-width: 180px !important;
        background: #f8f9fb !important; 
        border-right: 1px solid #e8ecf0 !important; 
        padding: 12px 4px 12px 0 !important; 
        font-size: 15px !important; 
        display: flex !important; 
        flex-direction: column !important; 
        height: 100vh !important; 
        overflow-y: auto !important;
        overflow-x: hidden !important;
        position: relative !important;
        margin: 0 !important;
    }
    /* 移除 Gradio 默认的间距 */
    #sidebar > div { margin: 0 !important; padding: 0 !important; }
    #sidebar .group-title { font-size: 12px !important; color: #999 !important; font-weight: 600 !important; padding: 8px 4px 2px !important; }
    .nav-btn { background: transparent !important; border: none !important; color: #333 !important; text-align: left !important; padding: 8px 10px !important; margin: 0 !important; border-radius: 6px !important; font-size: 17px !important; font-weight: 500 !important; }
    .nav-btn:hover { background: #eef1f6 !important; }
    .new-btn { width: 28px !important; height: 28px !important; padding: 0 !important; background: transparent !important; border: none !important; border-radius: 6px !important; color: #666 !important; font-size: 16px !important; }
    .new-btn:hover { background: #eef1f6 !important; }
    /* 侧边栏按钮样式 - Gradio 6.x 兼容 */
    #sidebar button, #sidebar .button, #sidebar [data-testid="button"], .sidebar button { background: #f0f2f5 !important; border: none !important; color: #444 !important; padding: 12px 24px !important; border-radius: 8px !important; font-size: 22px !important; font-weight: 500 !important; margin: 4px 0 !important; width: 100% !important; min-height: 48px !important; }
    #sidebar button:hover, #sidebar .button:hover, #sidebar [data-testid="button"]:hover, .sidebar button:hover { background: #e3e8f0 !important; }
    #sidebar button span, #sidebar button div, #sidebar .button span { font-size: 22px !important; }
    /* 豆包风格会话列表 - Radio 样式 */
    .session-radio-list {
        background: #f8f9fa !important;
        border-radius: 12px !important;
        padding: 8px !important;
    }
    .session-radio-list .wrap {
        display: flex !important;
        flex-direction: column !important;
        gap: 4px !important;
    }
    .session-radio-list label {
        display: flex !important;
        align-items: center !important;
        padding: 10px 12px !important;
        border-radius: 8px !important;
        cursor: pointer !important;
        transition: all 0.15s !important;
        background: transparent !important;
        border: none !important;
        font-size: 15px !important;
        color: #333 !important;
        margin: 0 !important;
    }
    .session-radio-list label:hover {
        background: #e8edf5 !important;
    }
    /* 强制隐藏 radio 圆圈 - 终极方案 */
    .session-radio-list input[type="radio"],
    .session-radio-list [role="radio"],
    .session-radio-list .radio,
    .session-radio-list label > *:first-child:not(span),
    .session-radio-list label::before,
    .session-radio-list ::part(radio),
    gr-radio *::part(radio),
    [data-testid="radio"] .icon,
    [data-testid="radio"] svg,
    .session-radio-list fieldset > div > div > span:first-child,
    .session-radio-list label > div:first-child,
    .session-radio-list label > span:not(.session-name):not(.session-icon) {
        display: none !important;
        visibility: hidden !important;
        width: 0 !important;
        height: 0 !important;
        opacity: 0 !important;
        position: absolute !important;
        margin: 0 !important;
        padding: 0 !important;
        border: none !important;
        background: none !important;
    }
    /* Radio 容器样式 */
    .session-radio-list {
        background: #f8f9fa !important;
        border-radius: 12px !important;
        padding: 8px !important;
        border: 1px solid #e8ecf0 !important;
    }
    .session-radio-list fieldset {
        border: none !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    /* label 样式 */
    .session-radio-list label {
        display: flex !important;
        align-items: center !important;
        padding: 10px 12px !important;
        border-radius: 8px !important;
        cursor: pointer !important;
        transition: all 0.15s !important;
        background: transparent !important;
        margin: 2px 0 !important;
        gap: 8px !important;
    }
    .session-radio-list label:hover {
        background: #e8edf5 !important;
    }
    /* 选中项样式 */
    .session-radio-list label[data-selected="true"],
    .session-radio-list input:checked + label,
    .session-radio-list label:has(input:checked) {
        background: #667eea !important;
        color: white !important;
    }
    .session-radio-list label:has(input:checked) {
        background: #667eea !important;
        color: white !important;
        font-weight: 500 !important;
    }
    .session-radio-list .check {
        display: none !important;
    }

    /* 豆包风格会话列表 */
    .session-list-container {
        display: flex;
        flex-direction: column;
        gap: 2px;
        max-height: 280px;
        overflow-y: auto;
        padding: 8px;
        background: #f8f9fa;
        border-radius: 12px;
    }
    .session-list-container::-webkit-scrollbar { width: 4px; }
    .session-list-container::-webkit-scrollbar-thumb { background: #d0d0d0; border-radius: 2px; }
    .session-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 8px 12px;
        border-radius: 8px;
        cursor: pointer !important;
        transition: all 0.15s;
        background: transparent;
        font-size: 15px;
        color: #333;
        position: relative;
        user-select: none;
    }
    .session-item:hover {
        background: #e8edf5;
    }
    .session-item.active {
        background: #e0e7f0;
    }
    button.session-main, .session-main {
        display: flex !important;
        align-items: center !important;
        gap: 10px !important;
        flex: 1 !important;
        overflow: hidden !important;
        cursor: pointer !important;
        pointer-events: auto !important;
        background: transparent !important;
        border: none !important;
        padding: 8px 12px !important;
        font-size: 15px !important;
        color: #333 !important;
        text-align: left !important;
        width: 100% !important;
    }
    button.session-main:hover {
        background: transparent !important;
    }
    .session-icon { font-size: 15px; flex-shrink: 0; }
    .session-name { 
        flex: 1; 
        overflow: hidden; 
        text-overflow: ellipsis; 
        white-space: nowrap; 
    }
    .session-more-btn {
        background: transparent;
        border: none;
        color: #999;
        font-size: 18px;
        cursor: pointer;
        padding: 4px 8px;
        border-radius: 6px;
        opacity: 0;
        transition: all 0.15s;
    }
    .session-item:hover .session-more-btn {
        opacity: 1;
    }
    .session-more-btn:hover {
        background: #d0d8e4;
        color: #666;
    }
    /* 菜单默认隐藏 */
    div.session-menu, .session-menu, #sidebar .session-menu, .gradio-container .session-menu {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        position: absolute;
        right: 8px;
        top: 36px;
        background: white;
        border-radius: 10px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.15);
        padding: 6px 0;
        min-width: 120px;
        z-index: 100;
    }
    /* 菜单显示状态 */
    div.session-menu.show, .session-menu.show, #sidebar .session-menu.show, .gradio-container .session-menu.show {
        display: block !important;
        visibility: visible !important;
        opacity: 1 !important;
    }
    .menu-item {
        padding: 8px 14px;
        font-size: 14px;
        color: #333;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .menu-item:hover {
        background: #f5f7fa;
    }
    .menu-item-delete {
        color: #e74c3c;
    }
    .menu-item-delete:hover {
        background: #fef2f2;
    }
        background: #e8edf5;
        font-weight: 500;
    }
    .session-icon { font-size: 16px; }
    .session-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    #sidebar .gr-box, #sidebar .gr-form, .sidebar .gr-box, .sidebar .gr-form { padding: 0 !important; margin: 0 !important; }
    
    /* ===== 主区域 - 独立滚动 ===== */
    .main-area { 
        flex: 1 !important; 
        background: #f5f6f8 !important; 
        padding: 2px !important; 
        min-width: 0 !important;
    }
    .chat-card { background: #fff !important; border-radius: 10px !important; padding: 8px 6px 6px 6px !important; height: auto !important; min-height: 500px !important; display: flex !important; flex-direction: column !important; box-shadow: 0 1px 4px rgba(0,0,0,0.04) !important; margin: 0 !important; }
    
    /* ===== 聊天区域 ===== */
    .chatbot { flex: 1 !important; min-height: 0 !important; }
    
    /* ===== 底部输入栏 - 豆包风格卡片 ===== */
    .input-bar { 
        align-items: center !important; 
        margin: 8px 12px 12px 12px !important; 
        gap: 8px !important; 
        padding: 8px 12px !important;
        background: #fff !important;
        border-radius: 16px !important;
        box-shadow: 0 2px 12px rgba(0,0,0,0.08) !important;
        border: 1px solid #f0f0f0 !important;
        height: auto !important;
        flex-shrink: 0 !important;
    }
    .input-bar > * { align-self: center !important; display: flex !important; align-items: center !important; margin: 0 !important; }
    .input-bar textarea { 
        border: none !important; 
        border-radius: 12px !important; 
        padding: 12px 16px !important; 
        font-size: 16px !important; 
        resize: none !important; 
        background: transparent !important; 
        flex: 1 !important; 
        height: 44px !important; 
        min-height: 44px !important; 
        max-height: 120px !important;
        line-height: 1.5 !important;
    }
    .input-bar textarea:focus { 
        outline: none !important; 
        background: transparent !important; 
        box-shadow: none !important;
    }
    .input-bar textarea::placeholder { color: #9ca3af !important; opacity: 1 !important; font-size: 15px !important; }
    /* 附件按钮 - 圆形 */
    .mic-btn { 
        border-radius: 50% !important; 
        background: #f3f4f6 !important; 
        border: none !important; 
        width: 40px !important; 
        height: 40px !important; 
        min-width: 40px !important; 
        font-size: 18px !important; 
        margin: 0 !important; 
        padding: 0 !important; 
        display: flex !important; 
        align-items: center !important; 
        justify-content: center !important;
        transition: all 0.2s !important;
    }
    .mic-btn:hover { background: #e5e7eb !important; transform: scale(1.05) !important; }
    /* 发送按钮 - 圆形渐变 */
    .send-btn { 
        border-radius: 50% !important; 
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important; 
        color: white !important; 
        border: none !important; 
        width: 40px !important; 
        height: 40px !important; 
        min-width: 40px !important;
        padding: 0 !important; 
        font-weight: 600 !important; 
        font-size: 14px !important; 
        margin: 0 !important; 
        display: flex !important; 
        align-items: center !important; 
        justify-content: center !important;
        transition: all 0.2s !important;
        box-shadow: 0 2px 8px rgba(102,126,234,0.3) !important;
    }
    .send-btn:hover { 
        transform: scale(1.05) !important; 
        box-shadow: 0 4px 12px rgba(102,126,234,0.4) !important;
    }
    
    /* ===== 聊天气泡 ===== */
    .message-wrap[data-testid="chat-message-user"] .message-content { background: #f0f7ff !important; border-radius: 12px 2px 12px 12px !important; }
    .message-wrap[data-testid="chat-message-bot"] .message-content { background: #f8f9fa !important; border-radius: 2px 12px 12px 12px !important; }
    .message-wrap .message-content { display: inline-block !important; max-width: 80% !important; padding: 12px 18px !important; font-size: 20px !important; line-height: 1.6 !important; }
    .message-wrap { margin: 4px 0 !important; }
    
    /* ===== Markdown ===== */
    .markdown { font-size: 20px !important; line-height: 1.6 !important; }
    .markdown h1, .markdown h2, .markdown h3 { color: #1a1a2e !important; margin: 12px 0 6px !important; }
    .markdown h3 { font-size: 22px !important; font-weight: 700 !important; }
    .markdown p { margin: 6px 0 !important; line-height: 1.6 !important; }
    .markdown table { border-collapse: collapse !important; width: 100% !important; margin: 8px 0 !important; font-size: 18px !important; }
    .markdown th, .markdown td { border: 1px solid #e2e5ea !important; padding: 5px 8px !important; }
    .markdown th { background: #f5f7fa !important; font-weight: 600 !important; }
    .markdown tr:nth-child(even) { background: #fafbfc !important; }
    .markdown code { background: #f0f2f5 !important; padding: 1px 4px !important; border-radius: 3px !important; font-size: 16px !important; }
    .markdown pre { background: #f5f7fa !important; padding: 10px !important; border-radius: 8px !important; overflow-x: auto !important; }
    .markdown pre code { background: transparent !important; padding: 0 !important; }
    
    /* 隐藏水印和 footer - Gradio 6.x */
    footer, .built-with, .gr-footer, .gradio-footer, [class*="footer"], [class*="built"], [class*="watermark"] { display: none !important; visibility: hidden !important; opacity: 0 !important; }
    .svelte-1av8eaw, .svelte-q3gblj, [class*="svelte-"] footer, .gradio-container footer { display: none !important; }
    .gradio-container > footer, .gradio-container > div:last-child, .gradio-container > div:last-of-type { display: none !important; }
    /* 强制隐藏底部所有链接和文字 */
    .gradio-container a[href*="gradio"], .gradio-container a[href*="api"], .gradio-container div:has(> a[href*="gradio"]) { display: none !important; }
    /* 隐藏 Gradio 底部信息栏 - 增强版 */
    .gradio-container > div:has(> a), .gradio-container > div > div:has(> a[href*="gradio"]), .gradio-container > div > div:has(> span), .gradio-container > div > div:has(> svg), .gradio-container > div[style*="center"], .gradio-container > div > div[style*="center"] { display: none !important; }
    /* Gradio 6.x 底部栏 */
    .gradio-container > div:has(> div > a[href*="gradio"]), .gradio-container > div:has(> a[href*="gradio"]), .gradio-container > div:has(> a[href*="api"]) { display: none !important; }
    [class*="gradio"][class*="footer"], [class*="gradio-footer"], div[class*="footer"]:last-child { display: none !important; }
    /* 强制隐藏底部所有可能元素 */
    footer, .gradio-footer, .built-with, [class*="footer"], [class*="watermark"] { display: none !important; visibility: hidden !important; opacity: 0 !important; height: 0 !important; min-height: 0 !important; max-height: 0 !important; overflow: hidden !important; }
    .gradio-container > div:last-child, .gradio-container > div:last-of-type, .gradio-container > div:has(> div:last-child > a) { display: none !important; }
    /* 隐藏 Textbox 标签 */
    .chat-input label, .input-bar label { display: none !important; }
    .input-bar .form-group { margin: 0 !important; }
    
    /* 预览区域 */
    .file-preview { margin-bottom: 4px !important; }
    .file-preview img { max-height: 28px !important; border-radius: 4px !important; }
    
    /* 全局缩减默认间距 */
    .gr-box, .gr-form, .gr-panel { gap: 2px !important; }
    .svelte-1l0i8j6 { gap: 2px !important; }
    .gr-row { padding: 2px 0 !important; }
    """
    
    with gr.Blocks(title="vLLM-Omni", head=f"<style>{custom_css}</style>") as app:
        # 注入 JS 彻底删除底部 Gradio 水印
        gr.HTML("""
        <script>
        (function() {
            function removeFooter() {
                // 多种选择器尝试删除底部水印
                var selectors = [
                    'footer',
                    '.gradio-footer',
                    '.built-with',
                    '.gradio-container > div:last-child',
                    'a[href*="gradio"]',
                    'a[href*="api"]',
                    '[class*="footer"]',
                    '[class*="watermark"]'
                ];
                selectors.forEach(function(sel) {
                    document.querySelectorAll(sel).forEach(function(el) {
                        if (el && el.textContent && (
                            el.textContent.includes('Gradio') ||
                            el.textContent.includes('API') ||
                            el.textContent.includes('构建') ||
                            el.textContent.includes('使用')
                        )) {
                            el.remove();
                        }
                    });
                });
                // 直接隐藏底部行
                var container = document.querySelector('.gradio-container');
                if (container && container.lastElementChild) {
                    var last = container.lastElementChild;
                    if (last.tagName === 'DIV') {
                        last.style.display = 'none';
                        last.remove();
                    }
                }
            }
            // 立即执行 + 定时执行
            removeFooter();
            setInterval(removeFooter, 500);
        })();

        // 会话切换函数
        window.switchSession = function(idx) {
            // 关闭所有菜单
            document.querySelectorAll('.session-menu').forEach(m => m.classList.remove('show'));
            // 找到 Radio 组件并更新选中值
            var radioInputs = document.querySelectorAll('.session-radio-list input[type="radio"], [class*="session-radio-list"] input[type="radio"]');
            if (radioInputs[idx]) {
                radioInputs[idx].checked = true;
                // 触发 change 事件
                var event = new Event('change', { bubbles: true });
                radioInputs[idx].dispatchEvent(event);
            }
        }

        // 切换菜单显示
        window.toggleMenu = function(event, sessionId) {
            event.stopPropagation();
            var menu = document.getElementById('menu-' + sessionId);
            if (!menu) return;
            // 关闭其他菜单
            document.querySelectorAll('.session-menu').forEach(m => {
                if (m.id !== 'menu-' + sessionId) {
                    m.classList.remove('show');
                    m.style.cssText = 'display:none!important;visibility:hidden!important;opacity:0!important;';
                }
            });
            // 切换当前菜单
            if (menu.classList.contains('show')) {
                menu.classList.remove('show');
                menu.style.cssText = 'display:none!important;visibility:hidden!important;opacity:0!important;';
            } else {
                menu.classList.add('show');
                menu.style.cssText = 'display:block!important;visibility:visible!important;opacity:1!important;';
            }
        }

        // 菜单操作
        window.sessionAction = function(action, sessionId, evt) {
            if (evt) { evt.stopPropagation(); }
            var menu = document.getElementById('menu-' + sessionId);
            if (menu) {
                menu.classList.remove('show');
                menu.style.cssText = 'display:none!important;visibility:hidden!important;opacity:0!important;';
            }

            switch(action) {
                case 'pin':
                    console.log('置顶会话:', sessionId);
                    break;
                case 'share':
                    navigator.clipboard.writeText(window.location.href + '?session=' + sessionId);
                    alert('链接已复制到剪贴板');
                    break;
                case 'rename':
                    var newName = prompt('请输入新名称:');
                    if (newName) {
                        console.log('重命名会话:', sessionId, newName);
                    }
                    break;
                case 'report':
                    alert('举报已提交');
                    break;
                case 'delete':
                    if (confirm('确定要删除这个会话吗?')) {
                        document.querySelector('#sidebar button').click();
                    }
                    break;
            }
        }

        // 点击页面其他地方关闭菜单
        document.addEventListener('click', function(e) {
            if (!e.target.closest('.session-more-btn') && !e.target.closest('.session-menu')) {
                document.querySelectorAll('.session-menu').forEach(m => m.classList.remove('show'));
            }
        });
        </script>
        """, visible=False)

        with gr.Row(elem_id="main-row"):
            # 侧边栏
            with gr.Column(scale=0, min_width=180, elem_id="sidebar", elem_classes=["sidebar"]):
                gr.Markdown("<span style='font-size: 17px; font-weight: 600; display: block; margin-left: -12px;'>🤖 vLLM-Omni</span>")
                new_chat_btn = gr.Button("➕ 新对话", elem_classes=["nav-btn"], scale=1)
                gr.Markdown("<div style='height: 2px;'></div>")

                gr.Markdown("<div style='height: 4px;'></div>")
                demo_tab = gr.Button("💬 AI 对话", elem_classes=["nav-btn"])
                ops_tab = gr.Button("📊 运维监控", elem_classes=["nav-btn"])
                gr.Markdown("<div style='height: 8px;'></div>")
                gr.Markdown("<span style='font-size: 14px; color: #999; margin-bottom: 8px; display: block;'>💬 历史会话</span>")

                # 会话列表 - 使用 Radio 实现扁平列表样式
                session_dropdown = gr.Radio(
                    choices=state.get_session_choices(),
                    value=state.get_session_choices()[0] if state.get_session_choices() else None,
                    show_label=False,
                    interactive=True,
                    elem_classes=["session-radio-list"]
                )

                with gr.Row():
                    delete_btn = gr.Button("🗑️ 删除", elem_classes="sidebar-btn", scale=0)
                    export_md_btn = gr.Button("📄 导出", elem_classes="sidebar-btn", scale=0)

                gr.Markdown("<hr style='margin: 6px 0;'>")
                gr.Markdown("<span style='font-size: 12px; color: #999;'>⚡ 并发压测</span>")
                with gr.Row():
                    bench_5_btn = gr.Button("5路并发", elem_classes="sidebar-btn", scale=0)
                    bench_10_btn = gr.Button("10路并发", elem_classes="sidebar-btn", scale=0)
                bench_result = gr.Markdown("")

            # 主区域
            with gr.Column(scale=1, elem_classes=["main-area"]):
                with gr.Column(elem_classes=["chat-card"], visible=True) as chat_panel:
                    with gr.Row():
                        with gr.Column(scale=1):
                            title_md = gr.Markdown("### 💬 AI 对话")
                        with gr.Column(scale=0):
                            user_html = gr.HTML("""
                            <div style='display: flex; align-items: center; gap: 8px; justify-content: flex-end; width: 100%;'>
                                <div style='width: 28px; height: 28px; border-radius: 50%; background: linear-gradient(135deg, #667eea, #764ba2); display: flex; align-items: center; justify-content: center; color: white; font-weight: 600; font-size: 12px;'>U</div>
                                <div>
                                    <div style='font-size: 13px; color: #333;'>用户</div>
                                    <div style='font-size: 11px; color: #999;'>🟢 在线</div>
                                </div>
                            </div>
                            """)
                    
                    chatbot = gr.Chatbot(show_label=False, height=1000, elem_classes="chatbot")
                    
                    # 图片预览区域
                    with gr.Row(visible=False, elem_classes="file-preview") as preview_row:
                        preview_html = gr.HTML("")
                    
                    # 底部输入区 - 豆包风格单行布局
                    with gr.Row(elem_classes="input-bar"):
                        mic_btn = gr.UploadButton("📎", file_types=["image"], scale=0, min_width=44, elem_classes="mic-btn")
                        msg_input = gr.Textbox(lines=2, placeholder="输入消息，Enter 发送...", show_label=False, scale=10, elem_classes="chat-input")
                        send_btn = gr.Button("➤", variant="primary", scale=0, min_width=44, elem_classes="send-btn")
                    
                    # 停止按钮（隐藏，通过 send 控制逻辑触发停止）
                    stop_btn = gr.Button("⏹", visible=False, elem_classes="tool-btn stop-btn")
                
                with gr.Column(elem_classes=["chat-card"], visible=False) as monitor_panel:
                    ops_title_md = gr.Markdown("### 📊 运维监控")
                    ops_metrics = gr.Markdown(get_metrics_display())
                    with gr.Row():
                        ops_refresh_btn = gr.Button("🔄 刷新", variant="secondary", scale=0)
        
        # ---- 事件绑定 ----
        
        # 图片上传 - 豆包风格
        def on_image_upload(file):
            """选择图片后显示预览"""
            if file is None:
                return gr.update(visible=False), gr.update(value="")
            file_name = os.path.basename(file)
            preview = f"""<div style='display:flex;align-items:center;gap:8px;padding:4px 8px;background:#f8f8f8;border-radius:6px;'>
                <img src='/file={file}' style='height:36px;width:auto;border-radius:4px;'>
                <span style='font-size:12px;color:#666;'>{file_name}</span>
                <span id='close-preview' style='cursor:pointer;margin-left:8px;color:#999;font-size:16px;' onclick='this.parentElement.parentElement.parentElement.style.display=\"none\"'>✕</span>
            </div>"""
            return gr.update(visible=True), gr.update(value=preview)
        
        def clear_preview():
            return gr.update(visible=False), gr.update(value="")
        
        mic_btn.upload(on_image_upload, inputs=[mic_btn], outputs=[preview_row, preview_html])
        
        # 导航切换
        def show_chat():
            return gr.update(visible=True), gr.update(visible=False)
        def show_ops():
            return gr.update(visible=False), gr.update(visible=True)
        demo_tab.click(show_chat, outputs=[chat_panel, monitor_panel])
        ops_tab.click(show_ops, outputs=[chat_panel, monitor_panel])
        
        # 刷新监控
        def refresh_metrics():
            return get_metrics_display()
        ops_refresh_btn.click(refresh_metrics, outputs=[ops_metrics])
        
        # 会话切换
        def on_session_change(selected):
            if not selected:
                return [], "### 无会话"
            history, title = state.switch_session(selected)
            return history, title
        session_dropdown.change(on_session_change, inputs=[session_dropdown], outputs=[chatbot, title_md])
        
        # 删除会话
        def on_delete_session():
            new_choice, history, title = state.delete_session()
            return gr.update(choices=state.get_session_choices(), value=new_choice), history, title
        delete_btn.click(on_delete_session, outputs=[session_dropdown, chatbot, title_md])
        
        # 新建会话
        def on_new_chat():
            choices, history, title = state.create_empty_session()
            new_value = choices[-1] if choices else None
            return gr.update(choices=choices, value=new_value), history, title
        new_chat_btn.click(on_new_chat, outputs=[session_dropdown, chatbot, title_md])
        
        # ---- 核心：发送消息（彻底非阻塞模式） ----
        
        async def handle_send(msg, image_file, history):
            """异步启动后台任务，立即返回，不阻塞UI"""
            # 从 UploadButton 取文件路径
            image = image_file if image_file else None
            
            if not msg.strip() and not image:
                return history, "", None
            
            session_id = state.current_session_id
            session = state.sessions.get(session_id)
            if not session:
                return history, "", None
            
            if session.is_generating:
                return history, "", None
            
            if session.name == "新会话":
                session.name = state.auto_name_session(msg, image)
            
            # Gradio 6.x Chatbot 只支持纯文本格式，图片无法渲染
            # 所以统一用纯文本显示
            if image and msg.strip():
                display_text = f"[图片] {msg}"
            elif image:
                display_text = "[图片]"
            else:
                display_text = msg
            
            history.append({"role": "user", "content": display_text})
            history.append({"role": "assistant", "content": "🤔 思考中..."})
            
            # 保存用户消息
            if image:
                session.add_message("user", f"[图片] {msg}" if msg.strip() else "[图片]")
            else:
                session.add_message("user", msg)
            
            # 在主事件循环上启动后台任务
            image_path = image if image else None
            task = asyncio.create_task(state._run_background_stream(session_id, msg, image_path))
            
            return history, "", None
        
        send_btn.click(
            handle_send,
            inputs=[msg_input, mic_btn, chatbot],
            outputs=[chatbot, msg_input, mic_btn]
        )
        msg_input.submit(
            handle_send,
            inputs=[msg_input, mic_btn, chatbot],
            outputs=[chatbot, msg_input, mic_btn]
        )
        
        # ---- 自动轮询更新（不阻塞UI） ----
        def poll_current_session():
            """定时检查当前会话的生成状态，完整重建 chatbot"""
            session_id = state.current_session_id
            if not session_id:
                return gr.update()
            session = state.sessions.get(session_id)
            if not session:
                return gr.update()
            
            # 从 session 消息重建完整 history（纯文本）
            history = []
            for m in session.messages:
                role = m.get("role", "user")
                content = m.get("content", "")
                if isinstance(content, list):
                    content = "[图片]"
                if isinstance(content, str) and content.startswith("[图片]"):
                    content = "[📷] 图片"
                history.append({"role": role, "content": content})
            
            if session.is_generating:
                if session.partial_reply:
                    history.append({"role": "assistant", "content": session.partial_reply})
                else:
                    history.append({"role": "assistant", "content": "🤔 思考中..."})
            
            return gr.update(value=history)
        
        # Gradio 6.x 定时轮询：用 Button 组件 + JS 点击
        # 轮询更新聊天内容
        timer = gr.Timer(0.5, active=True)
        timer.tick(poll_current_session, outputs=[chatbot])
        
        # 停止当前会话
        def stop_current_gen():
            state.stop_session(state.current_session_id)
        stop_btn.click(stop_current_gen, outputs=[])
        
        # 导出
        def handle_export_md():
            session_id = state.current_session_id
            content = export_chat_to_markdown(session_id)
            path = f"chat_export_{session_id}_{int(time.time())}.md"
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return gr.update(value=f"✅ 已导出: {path}")
        export_md_btn.click(handle_export_md, outputs=[gr.Textbox(visible=False)])
        
        # ---- 并发压测 ----
        
        async def run_bench_5():
            result = await state.run_concurrent_benchmark(5)
            return f"**⚡ 5路并发结果** | 成功: {result['success']} | 失败: {result['failed']} | 平均延迟: {result['avg_latency_ms']}ms"
        
        async def run_bench_10():
            result = await state.run_concurrent_benchmark(10)
            return f"**⚡ 10路并发结果** | 成功: {result['success']} | 失败: {result['failed']} | 平均延迟: {result['avg_latency_ms']}ms"
        
        bench_5_btn.click(run_bench_5, outputs=[bench_result])
        bench_10_btn.click(run_bench_10, outputs=[bench_result])
    
    return app


if __name__ == "__main__":
    app = create_ui()
    app.launch(server_name="0.0.0.0", server_port=7860)

gradio_app = create_ui()
