"""
会话持久化模块 - SQLite 数据库
"""
import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Any


class SessionDB:
    """会话持久化数据库"""

    def __init__(self, db_path: str = "sessions.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """初始化数据库表结构"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT DEFAULT 'text',
                    system_prompt TEXT DEFAULT '你是一个有帮助的AI助手。',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages (session_id)
            """)

            conn.commit()

    def save_session(self, session_id: str, name: str, session_type: str, system_prompt: str, created_at: float, messages: List[Dict[str, Any]]):
        """保存单个会话"""
        updated_at = datetime.now().timestamp()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO sessions (id, name, type, system_prompt, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session_id, name, session_type, system_prompt, created_at, updated_at))

            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            for msg in messages:
                msg_content = json.dumps(msg, ensure_ascii=False)
                conn.execute("""
                    INSERT INTO messages (session_id, role, content, timestamp)
                    VALUES (?, ?, ?, ?)
                """, (session_id, msg.get("role") if isinstance(msg, dict) else "user", msg_content, updated_at))

            conn.commit()

    def load_all_sessions(self) -> List[Dict[str, Any]]:
        """加载所有会话"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT id, name, type, system_prompt, created_at, updated_at
                FROM sessions
                ORDER BY updated_at DESC
            """)
            sessions = []
            for row in cursor.fetchall():
                sessions.append(dict(row))
            return sessions

    def load_session_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """加载单个会话的消息"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT role, content, timestamp
                FROM messages
                WHERE session_id = ?
                ORDER BY timestamp ASC
            """, (session_id,))
            messages = []
            for row in cursor.fetchall():
                role, content, timestamp = row
                try:
                    messages.append(json.loads(content))
                except:
                    messages.append({"role": role, "content": content})
            return messages

    def delete_session(self, session_id: str):
        """删除会话"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
