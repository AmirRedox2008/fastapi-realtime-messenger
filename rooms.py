from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from login import get_db, db_dependency, get_current_user
from model import Room, RoomMember, User, Message
from websocket import parse_content, parse_reactions

router = APIRouter()


class CreateRoomReq(BaseModel):
    name: str
    username: Optional[str] = None
    is_channel: bool
    bio: Optional[str] = None


@router.post("/rooms/create", status_code=status.HTTP_201_CREATED)
async def create_rooms(db: db_dependency, req: CreateRoomReq, current_user: dict = Depends(get_current_user)):
    if req.username:
        existing = db.query(Room).filter(Room.username == req.username).first()
        if existing:
            raise HTTPException(status_code=400, detail="This username is already taken")

    user = db.query(User).filter(User.id == current_user['id']).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    new_room = Room(name=req.name, username=req.username, is_channel=req.is_channel,
                    bio=req.bio, creator_id=user.id)
    db.add(new_room)
    db.commit()
    db.refresh(new_room)
    print(f"[ROOM CREATED] id={new_room.id} name={new_room.name} is_channel={new_room.is_channel}", flush=True)

    db.add(RoomMember(room_id=new_room.id, user_id=user.id, is_admin=True))
    db.commit()

    return {"id": new_room.id, "name": new_room.name, "username": new_room.username, "is_channel": new_room.is_channel}


@router.get("/rooms/search", status_code=status.HTTP_200_OK)
async def search_rooms(q: str, db: db_dependency, current_user: dict = Depends(get_current_user)):
    if not q.strip():
        return []
    rooms = db.query(Room).filter(Room.username.ilike(f"%{q}%")).limit(20).all()
    return [{"id": r.id, "name": r.name, "username": r.username, "is_channel": r.is_channel} for r in rooms]


# NEW: explore public channels/groups (must be registered BEFORE /rooms/{room_id})
@router.get("/rooms/explore", status_code=status.HTTP_200_OK)
async def explore_rooms(db: db_dependency, current_user: dict = Depends(get_current_user)):
    rooms = db.query(Room).order_by(Room.id.desc()).limit(50).all()
    out = []
    for r in rooms:
        count = db.query(RoomMember).filter(RoomMember.room_id == r.id).count()
        out.append({"id": r.id, "name": r.name, "username": r.username, "bio": r.bio,
                    "is_channel": r.is_channel, "member_count": count})
    out.sort(key=lambda x: (-x["member_count"], -x["id"]))
    return out[:24]


@router.get("/rooms/{room_id}", status_code=status.HTTP_200_OK)
async def get_room_info(room_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    me = db.query(RoomMember).filter(RoomMember.room_id == room_id,
                                     RoomMember.user_id == current_user['id']).first()

    return {
        "id": room.id,
        "name": room.name,
        "username": room.username,
        "bio": room.bio,
        "is_channel": room.is_channel,
        "creator_id": room.creator_id,
        "member_count": db.query(RoomMember).filter(RoomMember.room_id == room_id).count(),
        "is_member": me is not None,
        "is_admin": me.is_admin if me else False,
        "is_muted": me.is_muted if me else False
    }


@router.get("/rooms/{room_id}/history", status_code=status.HTTP_200_OK)
async def get_room_history(room_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    me = db.query(RoomMember).filter(RoomMember.room_id == room_id,
                                     RoomMember.user_id == current_user['id']).first()
    if not me and not room.is_channel:
        raise HTTPException(status_code=403, detail="Join this group to see its messages")

    messages = db.query(Message).filter(Message.room_id == room_id).order_by(Message.id).all()
    result = []
    for msg in messages:
        sender = db.query(User).filter(User.id == msg.sender_id).first()
        sender_name = (sender.name or sender.username) if sender else "Unknown"
        text, file_data, poll_data, reply_to = parse_content(msg.content)
        result.append({
            "id": msg.id,
            "sender_id": msg.sender_id,
            "sender_name": sender_name,
            "content": text,
            "file": file_data,
            "poll": poll_data,
            "reply_to": reply_to,
            "created_at": msg.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if msg.created_at else None,
            "views": msg.views or 0,
            "reactions": parse_reactions(msg.reactions)
        })
    return result


@router.post("/rooms/{room_id}/join", status_code=status.HTTP_200_OK)
async def join_room(room_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    existing = db.query(RoomMember).filter(RoomMember.room_id == room_id,
                                           RoomMember.user_id == current_user['id']).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already a member")
    db.add(RoomMember(room_id=room_id, user_id=current_user['id'], is_admin=False))
    db.commit()
    return {"message": "Joined successfully"}


@router.post("/rooms/{room_id}/leave", status_code=status.HTTP_200_OK)
async def leave_room(room_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    member = db.query(RoomMember).filter(RoomMember.room_id == room_id,
                                         RoomMember.user_id == current_user['id']).first()
    if not member:
        raise HTTPException(status_code=404, detail="You are not a member")
    if room.creator_id == current_user['id']:
        raise HTTPException(status_code=400, detail="The creator cannot leave the chat")
    db.delete(member)
    db.commit()
    return {"message": "Left successfully"}


@router.post("/rooms/{room_id}/mute", status_code=status.HTTP_200_OK)
async def mute_room(room_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    member = db.query(RoomMember).filter(RoomMember.room_id == room_id,
                                         RoomMember.user_id == current_user['id']).first()
    if not member:
        raise HTTPException(status_code=404, detail="You are not a member")
    member.is_muted = not member.is_muted
    db.commit()
    return {"message": "Mute toggled", "is_muted": member.is_muted}


@router.get("/rooms/{room_id}/members", status_code=status.HTTP_200_OK)
async def get_room_members(room_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    me = db.query(RoomMember).filter(RoomMember.room_id == room_id,
                                     RoomMember.user_id == current_user['id']).first()
    if not me and not room.is_channel:
        raise HTTPException(status_code=403, detail="Join this group first")

    out = []
    for m in db.query(RoomMember).filter(RoomMember.room_id == room_id).all():
        u = db.query(User).filter(User.id == m.user_id).first()
        out.append({
            "user_id": m.user_id,
            "name": (u.name or u.username or u.number) if u else "???",
            "is_admin": m.is_admin
        })
    return out


@router.post("/rooms/{room_id}/admins/{user_id}", status_code=status.HTTP_200_OK)
async def toggle_room_admin(room_id: int, user_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    me = db.query(RoomMember).filter(RoomMember.room_id == room_id,
                                     RoomMember.user_id == current_user['id']).first()
    if not me or not me.is_admin:
        raise HTTPException(status_code=403, detail="Admins only")
    if user_id == room.creator_id:
        raise HTTPException(status_code=400, detail="Cannot change the creator's role")
    target = db.query(RoomMember).filter(RoomMember.room_id == room_id,
                                         RoomMember.user_id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")
    target.is_admin = not target.is_admin
    db.commit()
    return {"user_id": user_id, "is_admin": target.is_admin}


@router.delete("/rooms/{room_id}/members/{user_id}", status_code=status.HTTP_200_OK)
async def kick_member(room_id: int, user_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    me = db.query(RoomMember).filter(RoomMember.room_id == room_id,
                                     RoomMember.user_id == current_user['id']).first()
    if not me or not me.is_admin:
        raise HTTPException(status_code=403, detail="Admins only")
    if user_id == room.creator_id:
        raise HTTPException(status_code=400, detail="Cannot remove the creator")
    if user_id == current_user['id']:
        raise HTTPException(status_code=400, detail="Use leave instead")
    target = db.query(RoomMember).filter(RoomMember.room_id == room_id,
                                         RoomMember.user_id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")
    db.delete(target)
    db.commit()
    return {"message": "Member removed"}


# @router.get("/debug/rooms")
# async def debug_rooms(db: db_dependency):
#     out = []
#     for r in db.query(Room).all():
#         members = []
#         for m in db.query(RoomMember).filter(RoomMember.room_id == r.id).all():
#             u = db.query(User).filter(User.id == m.user_id).first()
#             members.append({"user_id": m.user_id,
#                             "name": (u.name or u.username or u.number) if u else "???",
#                             "is_admin": m.is_admin})
#         out.append({"id": r.id, "name": r.name, "is_channel": r.is_channel,
#                     "creator_id": r.creator_id, "members": members})
#     return out