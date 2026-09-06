from typing import Optional
from model import Room, RoomMember, User, Message
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from login import get_db, db_dependency, get_current_user

router = APIRouter()

class CreateRoomReq(BaseModel):
    name: str
    username: Optional[str] = None
    is_channel: bool
    bio: Optional[str] = None

@router.post("/rooms/create", status_code=status.HTTP_201_CREATED)
async def create_rooms(db: db_dependency, req: CreateRoomReq, current_user: dict = Depends(get_current_user)):
    if req.username:
        existing_room = db.query(Room).filter(Room.username == req.username).first()
        if existing_room:
            raise HTTPException(status_code=400, detail="This username is already taken")
            
    user = db.query(User).filter(User.id == current_user['id']).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    new_room = Room(
        name=req.name, 
        username=req.username, 
        is_channel=req.is_channel, 
        bio=req.bio, 
        creator_id=user.id
    )
    db.add(new_room)
    db.commit()
    db.refresh(new_room)

    new_member = RoomMember(room_id=new_room.id, user_id=user.id, is_admin=True)
    db.add(new_member)
    db.commit()

    return {"id": new_room.id, "name": new_room.name, "username": new_room.username, "is_channel": new_room.is_channel}

@router.get("/rooms/search", status_code=status.HTTP_200_OK)
async def search_rooms(q: str, db: db_dependency, current_user: dict = Depends(get_current_user)):
    if not q.strip():
        return []
    rooms = db.query(Room).filter(Room.username.ilike(f"%{q}%")).limit(20).all()
    return [{"id": r.id, "name": r.name, "username": r.username, "is_channel": r.is_channel} for r in rooms]

@router.get("/rooms/{room_id}", status_code=status.HTTP_200_OK)
async def get_room_info(room_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    members = db.query(RoomMember).filter(RoomMember.room_id == room_id).all()
    member_count = len(members)
    
    current_member = next((m for m in members if m.user_id == current_user['id']), None)
    is_member = current_member is not None
    is_admin = current_member.is_admin if current_member else False
    is_muted = current_member.is_muted if current_member else False

    return {
        "id": room.id,
        "name": room.name,
        "username": room.username,
        "bio": room.bio,
        "is_channel": room.is_channel,
        "member_count": member_count,
        "is_member": is_member,
        "is_admin": is_admin,
        "is_muted": is_muted
    }

@router.get("/rooms/{room_id}/history", status_code=status.HTTP_200_OK)
async def get_room_history(room_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    messages = db.query(Message).filter(Message.room_id == room_id).order_by(Message.id).all()
    result = []
    for msg in messages:
        sender = db.query(User).filter(User.id == msg.sender_id).first()
        sender_name = sender.name or sender.username if sender else "Unknown"
        result.append({
            "sender_id": msg.sender_id,
            "sender_name": sender_name,
            "content": msg.content,
            "created_at": msg.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if msg.created_at else None,
            "views": msg.views or 0
        })
    return result

@router.post("/rooms/{room_id}/join", status_code=status.HTTP_200_OK)
async def join_room(room_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    existing = db.query(RoomMember).filter(RoomMember.room_id == room_id, RoomMember.user_id == current_user['id']).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already a member")
    new_member = RoomMember(room_id=room_id, user_id=current_user['id'], is_admin=False)
    db.add(new_member)
    db.commit()
    return {"message": "Joined successfully"}

@router.post("/rooms/{room_id}/leave", status_code=status.HTTP_200_OK)
async def leave_room(room_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    member = db.query(RoomMember).filter(RoomMember.room_id == room_id, RoomMember.user_id == current_user['id']).first()
    if not member:
        raise HTTPException(status_code=404, detail="You are not a member")
    db.delete(member)
    db.commit()
    return {"message": "Left successfully"}

@router.post("/rooms/{room_id}/mute", status_code=status.HTTP_200_OK)
async def mute_room(room_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    member = db.query(RoomMember).filter(RoomMember.room_id == room_id, RoomMember.user_id == current_user['id']).first()
    if not member:
        raise HTTPException(status_code=404, detail="You are not a member")
    member.is_muted = not member.is_muted
    db.commit()
    return {"message": "Mute toggled", "is_muted": member.is_muted}