import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from pydantic import BaseModel
from login import get_current_user, db_dependency
from model import Message, User

router = APIRouter()

class Editreq(BaseModel):
    content: str 

#====================================

# chat history

#====================================

@router.get("/history")
async def get_history(db: db_dependency, contact_id: int, current_user: dict = Depends(get_current_user)):
    me = current_user['id']
    messages = db.query(Message).filter(
        or_(
            (Message.sender_id == me) & (Message.receiver_id == contact_id),
            (Message.sender_id == contact_id) & (Message.receiver_id == me)
        )
    ).order_by(Message.id).all()

    result = []
    for m in messages:
        sender = db.query(User).filter(User.id == m.sender_id).first()
        sender_name = sender.name or sender.username if sender else "Unknown"
        result.append({
            "sender_id": m.sender_id,
            "sender_name": sender_name,
            "content": m.content,
            "created_at": m.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if m.created_at else None,
            "views": m.views or 0
        })
    return result

#====================================

#online/offline status

#====================================

@router.get("/status/{user_id}")
async def get_status(user_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    me = current_user['id']
    
    # Check if blocked by me
    is_blocked_by_me = db.query(User).filter(
        User.blocker_id == me, User.blocked_id == user_id
    ).first()
    if is_blocked_by_me:
        return {"is_online": False, "status_text": "blocked"}
    
    # Check if I am blocked by them
    is_me_blocked = db.query(User).filter(
        User.blocker_id == user_id, User.blocked_id == me
    ).first()
    if is_me_blocked:
        return {"is_online": False, "status_text": "last seen a long time ago"}
    
    # Ask Go server if the user is online
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://localhost:8001/internal/status/{user_id}")
            is_online = resp.json().get("is_online", False)
    except:
        is_online = False
        
    return {"is_online": is_online, "status_text": "online" if is_online else "last seen recently"}

# ==========================================

# block/unblock

# ==========================================
@router.post("/block")
async def toggle_block(contact_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    me = current_user['id']
    
    existing_block = db.query(User).filter(
        User.blocker_id == me, 
        User.blocked_id == contact_id
    ).first()
    
    if existing_block:
        db.delete(existing_block)
        db.commit()
        return {"is_blocked": False, "message": "User unblocked"}
    else:
        new_block = User(blocker_id=me, blocked_id=contact_id)
        db.add(new_block)
        db.commit()
        return {"is_blocked": True, "message": "User blocked"}

# ==========================================

# del acc

# ==========================================
@router.delete("/delete-account")
async def delete_account(db: db_dependency, current_user: dict = Depends(get_current_user)):
    me = current_user['id']
    user = db.query(User).filter(User.id == me).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    db.query(Message).filter(or_(Message.sender_id == me, Message.receiver_id == me)).delete()
    db.query(User).filter(or_(User.blocker_id == me, User.blocked_id == me)).delete()
    db.delete(user)
    db.commit()
    return {"message": "Account deleted successfully"}

# ==========================================

# edit msg

# ==========================================
@router.put("/edit-messages/{message_id}")
async def edit_messages(message_id: int, req: Editreq, db: db_dependency, current_user: dict = Depends(get_current_user)):
    msg = db.query(Message).filter(
        Message.id == message_id, 
        Message.sender_id == current_user['id']
    ).first()
    
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found or you don't have permission")
    
    msg.content = req.content
    db.commit()
    return {"message": "Message updated successfully"}

