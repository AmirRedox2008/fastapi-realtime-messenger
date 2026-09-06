from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from login import session_local, SECRET_KEY, ALGORITHM
from model import Message, User, RoomMember
from database import Base

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: int):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_to_user(self, user_id: int, data: dict):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_json(data)

    def is_online(self, user_id: int) -> bool:
        return user_id in self.active_connections

manager = ConnectionManager()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")
        if not user_id:
            await websocket.close(code=1008)
            return
    except JWTError:
        await websocket.close(code=1008)
        return

    
    await manager.connect(websocket, user_id)
    

    for uid, conn in manager.active_connections.items():
        if uid != user_id:
            await conn.send_json({"type": "status", "user_id": user_id, "online": True})

    try:
        while True:
            data = await websocket.receive_json()
            db = session_local()
            
            # مدیریت رویداد تایپ کردن
            if data.get("type") == "typing":
                to_user = data.get("to")
                await manager.send_to_user(to_user, {"type": "typing", "user_id": user_id})
                
            # مدیریت ری‌اکشن‌ها
            elif data.get("type") == "reaction":
                to_user = data.get("to")
                room_id = data.get("room_id")
                reaction_data = {
                    "type": "reaction",
                    "message_id": data.get("message_id"),
                    "emoji": data.get("emoji"),
                    "user_id": user_id
                }
                if to_user:
                    await manager.send_to_user(to_user, reaction_data)
                elif room_id:
                    members = db.query(RoomMember).filter(RoomMember.room_id == room_id).all()
                    for member in members:
                        if member.user_id != user_id:
                            await manager.send_to_user(member.user_id, reaction_data)
                            
         
            elif "text" in data:
                to_user = data.get("to")
                room_id = data.get("room_id")
                content = data.get("text")
                temp_id = data.get("temp_id")
                file_data = data.get("file")
                
                
                new_msg = Message(
                    sender_id=user_id, 
                    content=content,
                    receiver_id=to_user,
                    room_id=room_id
                )
                db.add(new_msg)
                db.commit()
                db.refresh(new_msg)
                
                
                sender = db.query(User).filter(User.id == user_id).first()
                sender_name = sender.name or sender.username if sender else "Unknown"
                
                
                msg_payload = {
                    "type": "message",
                    "id": new_msg.id,
                    "content": content,
                    "sender_id": user_id,
                    "sender_name": sender_name,
                    "created_at": new_msg.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "views": new_msg.views or 0,
                    "file": file_data
                }
                
                
                if to_user:
                    await manager.send_to_user(to_user, msg_payload)
                elif room_id:
                    members = db.query(RoomMember).filter(RoomMember.room_id == room_id).all()
                    for member in members:
                        if member.user_id != user_id:
                            await manager.send_to_user(member.user_id, msg_payload)
                            
              
                await websocket.send_json({
                    "type": "ack",
                    "temp_id": temp_id,
                    "db_id": new_msg.id
                })
                
            db.close()

    except WebSocketDisconnect:
        manager.disconnect(user_id)
        for uid, conn in manager.active_connections.items():
            await conn.send_json({"type": "status", "user_id": user_id, "online": False})