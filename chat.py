import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from pydantic import BaseModel
from login import get_current_user, db_dependency
from model import Message, User, Room, RoomMember, RoomReadState, Block
from websocket import manager, parse_content, parse_reactions

router = APIRouter()


class Editreq(BaseModel):
    content: str


# ===================== chat history =====================
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
        sender_name = (sender.name or sender.username) if sender else "Unknown"
        text, file_data, poll_data, reply_to = parse_content(m.content)
        result.append({
            "id": m.id,
            "sender_id": m.sender_id,
            "sender_name": sender_name,
            "content": text,
            "file": file_data,
            "poll": poll_data,
            "reply_to": reply_to,
            "created_at": m.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if m.created_at else None,
            "views": m.views or 0,
            "reactions": parse_reactions(m.reactions)
        })
    return result


# ===================== online/offline + block status =====================
@router.get("/status/{user_id}")
async def get_status(user_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    me = current_user['id']

    blocked_by_me = db.query(Block).filter(Block.blocker_id == me, Block.blocked_id == user_id).first()
    blocked_me = db.query(Block).filter(Block.blocker_id == user_id, Block.blocked_id == me).first()
    is_online = manager.is_online(user_id)

    if blocked_by_me:
        status_text = "blocked"
    elif blocked_me:
        status_text = "last seen a long time ago"
    else:
        status_text = "online" if is_online else "last seen recently"

    return {
        "is_online": is_online and not blocked_by_me and not blocked_me,
        "status_text": status_text,
        "blocked_by_me": blocked_by_me is not None,
        "blocked_me": blocked_me is not None
    }


# ===================== block/unblock =====================
@router.post("/block")
async def toggle_block(contact_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    me = current_user['id']
    existing = db.query(Block).filter(Block.blocker_id == me, Block.blocked_id == contact_id).first()
    if existing:
        db.delete(existing)
        db.commit()
        return {"is_blocked": False, "message": "User unblocked"}
    db.add(Block(blocker_id=me, blocked_id=contact_id))
    db.commit()
    return {"is_blocked": True, "message": "User blocked"}


# ===================== delete account =====================
@router.delete("/delete-account")
async def delete_account(db: db_dependency, current_user: dict = Depends(get_current_user)):
    me = current_user['id']
    user = db.query(User).filter(User.id == me).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    db.query(Message).filter(or_(Message.sender_id == me, Message.receiver_id == me)).delete(synchronize_session=False)
    db.query(Block).filter(or_(Block.blocker_id == me, Block.blocked_id == me)).delete(synchronize_session=False)
    db.query(RoomReadState).filter(RoomReadState.user_id == me).delete(synchronize_session=False)
    db.query(RoomMember).filter(RoomMember.user_id == me).delete(synchronize_session=False)

    for room in db.query(Room).filter(Room.creator_id == me).all():
        db.query(Message).filter(Message.room_id == room.id).delete(synchronize_session=False)
        db.query(RoomMember).filter(RoomMember.room_id == room.id).delete(synchronize_session=False)
        db.query(RoomReadState).filter(RoomReadState.room_id == room.id).delete(synchronize_session=False)
        db.delete(room)

    db.delete(user)
    db.commit()
    return {"message": "Account deleted successfully"}


# ===================== edit message =====================
@router.put("/edit-messages/{message_id}")
async def edit_messages(message_id: int, req: Editreq, db: db_dependency, current_user: dict = Depends(get_current_user)):
    msg = db.query(Message).filter(Message.id == message_id,
                                    Message.sender_id == current_user['id']).first()
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Message not found or you don't have permission")

    text, file_data, poll_data, reply_to = parse_content(msg.content)
    if file_data or poll_data or reply_to:
        msg.content = json.dumps({"text": req.content, "file": file_data,
                                  "poll": poll_data, "reply_to": reply_to})
    else:
        msg.content = req.content
    db.commit()
    return {"message": "Message updated successfully"}