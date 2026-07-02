"""
数据库配置和模型
"""
from sqlalchemy import create_engine, Column, String, Float, Boolean, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os

# 数据库文件路径
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./vllm_omni.db")

# SQLAlchemy 引擎
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

# Session 工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 声明式基类
Base = declarative_base()


class SessionDB(Base):
    """会话表"""
    __tablename__ = "sessions"
    
    id = Column(String, primary_key=True)
    name = Column(String, default="新会话")
    type = Column(String, default="text")
    pinned = Column(Boolean, default=False)
    created_at = Column(Float)
    updated_at = Column(Float)
    
    # 关联消息
    messages = relationship("MessageDB", back_populates="session", cascade="all, delete-orphan")


class MessageDB(Base):
    """消息表"""
    __tablename__ = "messages"
    
    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"))
    role = Column(String)  # 'user' or 'assistant'
    content = Column(Text)
    timestamp = Column(Float)
    
    # 关联会话
    session = relationship("SessionDB", back_populates="messages")


def init_db():
    """初始化数据库表"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
