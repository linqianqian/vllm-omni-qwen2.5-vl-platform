"""
会话管理路由
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
import uuid

from ...database import get_db, SessionDB, MessageDB

router = APIRouter()


@router.get("/sessions", response_model=List[dict])
async def get_sessions(db: Session = Depends(get_db)):
    """获取所有会话列表（按置顶状态和时间排序）"""
    sessions = db.query(SessionDB).all()
    # 排序：先按置顶，再按更新时间
    sessions.sort(key=lambda x: (-int(x.pinned), -x.updated_at))
    return [{
        "id": s.id,
        "name": s.name,
        "type": s.type,
        "pinned": s.pinned,
        "created_at": s.created_at,
        "updated_at": s.updated_at
    } for s in sessions]


@router.post("/sessions")
async def create_session(request: dict, db: Session = Depends(get_db)):
    """创建新会话"""
    name = request.get("name", "新会话")
    type = request.get("type", "text")
    
    now = datetime.now().timestamp()
    session = SessionDB(
        id=str(uuid.uuid4()),
        name=name,
        type=type,
        pinned=False,
        created_at=now,
        updated_at=now
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    
    return {
        "id": session.id,
        "name": session.name,
        "type": session.type,
        "pinned": session.pinned,
        "created_at": session.created_at,
        "updated_at": session.updated_at
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, db: Session = Depends(get_db)):
    """获取单个会话"""
    session = db.query(SessionDB).filter(SessionDB.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {
        "id": session.id,
        "name": session.name,
        "type": session.type,
        "pinned": session.pinned,
        "created_at": session.created_at,
        "updated_at": session.updated_at
    }


@router.patch("/sessions/{session_id}")
async def update_session(session_id: str, request: dict, db: Session = Depends(get_db)):
    """更新会话（重命名、置顶等）"""
    session = db.query(SessionDB).filter(SessionDB.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    # 更新名称
    if "name" in request:
        session.name = request["name"]
    
    # 更新置顶状态
    if "pinned" in request:
        session.pinned = request["pinned"]
    
    session.updated_at = datetime.now().timestamp()
    db.commit()
    db.refresh(session)
    
    return {
        "id": session.id,
        "name": session.name,
        "type": session.type,
        "pinned": session.pinned,
        "created_at": session.created_at,
        "updated_at": session.updated_at
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, db: Session = Depends(get_db)):
    """删除会话"""
    session = db.query(SessionDB).filter(SessionDB.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    db.delete(session)
    db.commit()
    
    return {"status": "deleted", "id": session_id}


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, db: Session = Depends(get_db)):
    """获取会话消息"""
    session = db.query(SessionDB).filter(SessionDB.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    messages = db.query(MessageDB).filter(MessageDB.session_id == session_id).all()
    return [{
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "timestamp": m.timestamp
    } for m in messages]


@router.post("/sessions/{session_id}/messages")
async def add_message(session_id: str, message: dict, db: Session = Depends(get_db)):
    """添加消息到会话"""
    session = db.query(SessionDB).filter(SessionDB.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    msg = MessageDB(
        id=str(uuid.uuid4()),
        session_id=session_id,
        role=message.get("role", "user"),
        content=message.get("content", ""),
        timestamp=datetime.now().timestamp()
    )
    db.add(msg)
    
    # 更新会话时间
    session.updated_at = datetime.now().timestamp()
    
    db.commit()
    db.refresh(msg)
    
    return {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
        "timestamp": msg.timestamp
    }


@router.delete("/sessions/{session_id}/messages/{message_id}")
async def delete_message(session_id: str, message_id: str, db: Session = Depends(get_db)):
    """删除单条消息"""
    session = db.query(SessionDB).filter(SessionDB.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    message = db.query(MessageDB).filter(
        MessageDB.id == message_id,
        MessageDB.session_id == session_id
    ).first()
    
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")
    
    db.delete(message)
    db.commit()
    
    return {"status": "deleted", "message_id": message_id}
