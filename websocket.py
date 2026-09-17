from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
from sqlalchemy import or_, func
from datetime import datetime
import json

from login import session_local, SECRET_KEY, ALGORITHM
from model import Message, User, Room, RoomMember, RoomReadState, Block, MessageView

router = APIRouter()

CONTENT_KEYS = ("text", "content", "msg", "body", "message")


def to_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_content(content):
    """Splits a stored message into (text, file, poll, reply_to)."""
    if content is None:
        return "", None, None, None
    if isinstance(content, str) and content.startswith("{"):
        try:
            obj = json.loads(content)
            if isinstance(obj, dict) and ("file" in obj or "poll" in obj
                                          or "text" in obj or "reply_to" in obj):
                return (obj.get("text") or "", obj.get("file"),
                        obj.get("poll"), obj.get("reply_to"))
        except (ValueError, TypeError):
            pass
    return content, None, None, None


def parse_reactions(raw):
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def make_preview(text, file_data=None, poll_data=None):
    if poll_data:
        return "📊 " + str(poll_data.get("question") or "Poll")
    if file_data:
        name = "file"
        if isinstance(file_data, dict):
            name = file_data.get("name") or file_data.get("filename") or "file"
        return "📎 " + str(name)
    t = (text or "").strip()
    if not t:
        return "New message"
    return t[:60] + ("..." if len(t) > 60 else "")


def get_sender_name(db, user_id):
    u = db.query(User).filter(User.id == user_id, User.number != None).first()
    if u:
        return u.name or u.username or u.number or f"User {user_id}"
    return f"User {user_id}"


# ----------------------------------------------------------------------
# Connection manager
# ----------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        old = self.active_connections.get(user_id)
        if old is not None:
            try:
                await old.close(code=1000)
            except Exception:
                pass
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: int, websocket: WebSocket = None) -> bool:
        if websocket is None:
            return self.active_connections.pop(user_id, None) is not None
        if self.active_connections.get(user_id) is websocket:
            self.active_connections.pop(user_id)
            return True
        return False

    async def send_to_user(self, user_id: int, data: dict) -> bool:
        conn = self.active_connections.get(user_id)
        if conn is None:
            return False
        try:
            await conn.send_json(data)
            return True
        except Exception:
            if self.active_connections.get(user_id) is conn:
                self.active_connections.pop(user_id)
            return False

    def is_online(self, user_id: int) -> bool:
        return user_id in self.active_connections


manager = ConnectionManager()


async def broadcast_status(user_id: int, online: bool):
    for uid, conn in list(manager.active_connections.items()):
        if uid != user_id:
            try:
                await conn.send_json({"type": "status", "user_id": user_id, "online": online})
            except Exception:
                pass


# ----------------------------------------------------------------------
# Message handler
# ----------------------------------------------------------------------
async def handle_message(db, websocket, user_id, data):
    to_user = to_int(data.get("to"))
    room_id = to_int(data.get("room_id"))
    if not to_user:
        to_user = None
    if not room_id:
        room_id = None

    text = ""
    for key in CONTENT_KEYS:
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            text = v
            break

    file_data = data.get("file") or data.get("attachment")
    poll_data = data.get("poll")
    if isinstance(poll_data, dict):
        poll_data.setdefault("votes", {})
    temp_id = data.get("temp_id")

    if not text and not file_data and not poll_data:
        await websocket.send_json({"type": "error", "message": "Empty message"})
        return

    # ---- routing: room_id always wins ----
    if room_id is None and to_user is not None:
        maybe_room = db.query(Room).filter(Room.id == to_user).first()
        real_user = db.query(User).filter(User.id == to_user, User.number != None).first()
        if maybe_room and not real_user:
            room_id = to_user
            to_user = None

    if room_id is not None:
        to_user = None

    room = None
    if room_id is not None:
        room = db.query(Room).filter(Room.id == room_id).first()
        if not room:
            await websocket.send_json({"type": "error", "message": "Room not found"})
            return
        membership = db.query(RoomMember).filter(
            RoomMember.room_id == room_id,
            RoomMember.user_id == user_id
        ).first()

        if room.is_channel:
            # *** ONLY ADMINS CAN POST IN A CHANNEL ***
            if membership is None or not membership.is_admin:
                print(f"[WS DENY] user {user_id} tried to post in channel {room_id}", flush=True)
                await websocket.send_json({
                    "type": "error",
                    "message": "Only channel admins can post in this channel",
                    "room_id": room_id
                })
                return
        else:
            if membership is None:
                await websocket.send_json({
                    "type": "error",
                    "message": "Join this group before sending messages",
                    "room_id": room_id
                })
                return

    elif to_user is not None:
        recipient = db.query(User).filter(User.id == to_user, User.number != None).first()
        if not recipient:
            await websocket.send_json({"type": "error", "message": "User not found"})
            return
        blocked = db.query(Block).filter(or_(
            (Block.blocker_id == to_user) & (Block.blocked_id == user_id),
            (Block.blocker_id == user_id) & (Block.blocked_id == to_user)
        )).first()
        if blocked:
            await websocket.send_json({"type": "error", "message": "You cannot message this user"})
            return
        room_id = None
    else:
        await websocket.send_json({"type": "error", "message": "Message has no recipient"})
        return

    # ---- reply preview built from the ORIGINAL message (server-side) ----
    reply_obj = None
    reply_to_id = to_int(data.get("reply_to"))
    if reply_to_id is not None:
        orig = db.query(Message).filter(Message.id == reply_to_id).first()
        if orig:
            valid = False
            if room_id is not None:
                valid = (orig.room_id == room_id)
            elif to_user is not None:
                valid = ((orig.sender_id == to_user and orig.receiver_id == user_id) or
                         (orig.sender_id == user_id and orig.receiver_id == to_user))
            if valid:
                r_text, r_file, r_poll, _ = parse_content(orig.content)
                if r_poll:
                    r_preview = "📊 " + str(r_poll.get("question") or "Poll")
                elif r_file:
                    fname = "file"
                    if isinstance(r_file, dict):
                        fname = r_file.get("name") or r_file.get("filename") or "file"
                    r_preview = "📎 " + str(fname)
                else:
                    r_preview = r_text or ""
                reply_obj = {
                    "id": orig.id,
                    "sender_id": orig.sender_id,
                    "sender_name": get_sender_name(db, orig.sender_id),
                    "text": str(r_preview)[:80]
                }

    # ---- build stored content ----
    if poll_data:
        stored = json.dumps({"poll": poll_data, "text": text, "reply_to": reply_obj})
    elif file_data:
        stored = json.dumps({"file": file_data, "text": text, "reply_to": reply_obj})
    elif reply_obj:
        stored = json.dumps({"reply_to": reply_obj, "text": text})
    else:
        stored = text

    new_msg = Message(sender_id=user_id, content=stored,
                      receiver_id=to_user, room_id=room_id)
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)
    print(f"[WS MSG] id={new_msg.id} from={user_id} to={to_user} "
          f"room={room_id} channel={bool(room and room.is_channel)}", flush=True)

    sender_name = get_sender_name(db, user_id)

    msg_payload = {
        "type": "message",
        "id": new_msg.id,
        "content": text,
        "sender_id": user_id,
        "sender_name": sender_name,
        "receiver_id": to_user,
        "room_id": room_id,
        "created_at": new_msg.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if new_msg.created_at else None,
        "views": new_msg.views or 0,
        "file": file_data,
        "poll": poll_data,
        "reply_to": reply_obj,
        "reactions": {}
    }

    notification = {
        "type": "notification",
        "chat_type": "room" if room_id is not None else "direct",
        "chat_id": room_id if room_id is not None else to_user,
        "chat_name": (room.name if room else sender_name),
        "sender_id": user_id,
        "sender_name": sender_name,
        "preview": make_preview(text, file_data, poll_data),
        "message_id": new_msg.id
    }

    if to_user is not None:
        if manager.is_online(to_user):
            delivered = await manager.send_to_user(to_user, msg_payload)
            if delivered:
                await manager.send_to_user(to_user, notification)
                new_msg.is_delivered = True
                db.commit()
    else:
        for member in db.query(RoomMember).filter(RoomMember.room_id == room_id).all():
            if member.user_id == user_id:
                continue
            if await manager.send_to_user(member.user_id, msg_payload):
                await manager.send_to_user(member.user_id, notification)
                state = db.query(RoomReadState).filter(
                    RoomReadState.room_id == room_id,
                    RoomReadState.user_id == member.user_id).first()
                if state is None:
                    db.add(RoomReadState(room_id=room_id, user_id=member.user_id, last_read_id=new_msg.id))
                elif (state.last_read_id or 0) < new_msg.id:
                    state.last_read_id = new_msg.id
        db.commit()

    await websocket.send_json({
        "type": "ack",
        "temp_id": temp_id,
        "db_id": new_msg.id
    })


# ----------------------------------------------------------------------
# Reactions
# ----------------------------------------------------------------------
async def handle_reaction(db, websocket, user_id, data):
    message_id = to_int(data.get("message_id"))
    emoji = data.get("emoji")
    if message_id is None or not emoji:
        await websocket.send_json({"type": "error", "message": "Invalid reaction"})
        return

    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        await websocket.send_json({"type": "error", "message": "Message not found"})
        return

    if msg.room_id:
        membership = db.query(RoomMember).filter(
            RoomMember.room_id == msg.room_id, RoomMember.user_id == user_id).first()
        if not membership:
            await websocket.send_json({"type": "error", "message": "Join the chat before reacting"})
            return
    elif msg.receiver_id and user_id not in (msg.sender_id, msg.receiver_id):
        await websocket.send_json({"type": "error", "message": "Not allowed"})
        return

    reactions = parse_reactions(msg.reactions)
    removed = reactions.get(str(user_id)) == emoji
    if removed:
        reactions.pop(str(user_id), None)
    else:
        reactions[str(user_id)] = emoji
    msg.reactions = json.dumps(reactions)
    db.commit()

    event = {
        "type": "reaction",
        "message_id": message_id,
        "emoji": emoji,
        "user_id": user_id,
        "user_name": get_sender_name(db, user_id),
        "removed": removed,
        "reactions": reactions
    }

    if msg.room_id:
        for member in db.query(RoomMember).filter(RoomMember.room_id == msg.room_id).all():
            if member.user_id != user_id:
                await manager.send_to_user(member.user_id, event)
    elif msg.receiver_id:
        other = msg.sender_id if user_id == msg.receiver_id else msg.receiver_id
        await manager.send_to_user(other, event)

    await websocket.send_json(event)


# ----------------------------------------------------------------------
# Poll votes
# ----------------------------------------------------------------------
async def handle_poll_vote(db, websocket, user_id, data):
    message_id = to_int(data.get("message_id"))
    option = to_int(data.get("option"))
    if message_id is None or option is None:
        await websocket.send_json({"type": "error", "message": "Invalid vote"})
        return

    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        await websocket.send_json({"type": "error", "message": "Message not found"})
        return

    text, file_data, poll_data, reply_to = parse_content(msg.content)
    if not poll_data:
        await websocket.send_json({"type": "error", "message": "This message is not a poll"})
        return

    if msg.room_id:
        membership = db.query(RoomMember).filter(
            RoomMember.room_id == msg.room_id, RoomMember.user_id == user_id).first()
        if not membership:
            await websocket.send_json({"type": "error", "message": "Join the chat before voting"})
            return

    options = poll_data.get("options") or []
    if option < 0 or option >= len(options):
        await websocket.send_json({"type": "error", "message": "Invalid option"})
        return

    votes = {str(k): list(v) for k, v in (poll_data.get("votes") or {}).items()}
    current = None
    for k, voters in votes.items():
        if user_id in voters:
            current = int(k)
            break

    if current == option:
        votes[str(option)] = [u for u in votes.get(str(option), []) if u != user_id]
    else:
        if current is not None:
            votes[str(current)] = [u for u in votes.get(str(current), []) if u != user_id]
        votes.setdefault(str(option), [])
        if user_id not in votes[str(option)]:
            votes[str(option)].append(user_id)

    poll_data["votes"] = votes
    msg.content = json.dumps({"poll": poll_data, "text": text or "",
                              "file": file_data, "reply_to": reply_to})
    db.commit()

    event = {"type": "poll_update", "message_id": message_id, "poll": poll_data}
    if msg.room_id:
        for member in db.query(RoomMember).filter(RoomMember.room_id == msg.room_id).all():
            if member.user_id != user_id:
                await manager.send_to_user(member.user_id, event)
    elif msg.receiver_id:
        other = msg.sender_id if user_id == msg.receiver_id else msg.receiver_id
        await manager.send_to_user(other, event)
    await websocket.send_json(event)


# ----------------------------------------------------------------------
# Channel view counts (each user counts ONCE per post) — optimized
# ----------------------------------------------------------------------
async def handle_view(db, websocket, user_id, data):
    room_id = to_int(data.get("room_id"))
    if room_id is None:
        return
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        return

    messages = db.query(Message).filter(Message.room_id == room_id).order_by(Message.id).all()
    if not messages:
        return
    msg_ids = [m.id for m in messages]

    already = set(
        r[0] for r in db.query(MessageView.message_id).filter(
            MessageView.user_id == user_id,
            MessageView.message_id.in_(msg_ids)).all()
    )
    for msg in messages:
        if msg.sender_id == user_id:
            continue
        if msg.id not in already:
            db.add(MessageView(message_id=msg.id, user_id=user_id))
    db.commit()

    counts = dict(
        db.query(MessageView.message_id, func.count(MessageView.id))
          .filter(MessageView.message_id.in_(msg_ids))
          .group_by(MessageView.message_id).all()
    )

    updates = []
    for msg in messages:
        c = counts.get(msg.id, 0)
        updates.append({"message_id": msg.id, "views": c})
        if (msg.views or 0) != c:
            msg.views = c
    db.commit()

    event = {"type": "views_update", "room_id": room_id, "updates": updates}
    recipients = set()
    for member in db.query(RoomMember).filter(RoomMember.room_id == room_id).all():
        if manager.is_online(member.user_id):
            recipients.add(member.user_id)
    recipients.add(user_id)
    for uid in recipients:
        await manager.send_to_user(uid, event)


# ----------------------------------------------------------------------
# WebSocket endpoint
# ----------------------------------------------------------------------
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

    user_id = int(user_id)
    await manager.connect(websocket, user_id)
    print(f"[WS] user {user_id} connected", flush=True)
    await broadcast_status(user_id, True)

    # ---- deliver messages sent while the user was offline ----
    db = session_local()
    try:
        pending = db.query(Message).filter(
            Message.receiver_id == user_id,
            Message.is_delivered == False
        ).order_by(Message.id).all()

        for msg in pending:
            sender_name = get_sender_name(db, msg.sender_id)
            text, file_data, poll_data, reply_to = parse_content(msg.content)
            await manager.send_to_user(user_id, {
                "type": "message",
                "id": msg.id,
                "content": text,
                "sender_id": msg.sender_id,
                "sender_name": sender_name,
                "receiver_id": msg.receiver_id,
                "room_id": msg.room_id,
                "created_at": msg.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if msg.created_at else None,
                "views": msg.views or 0,
                "file": file_data,
                "poll": poll_data,
                "reply_to": reply_to,
                "reactions": parse_reactions(msg.reactions)
            })
            await manager.send_to_user(user_id, {
                "type": "notification",
                "chat_type": "direct",
                "chat_id": msg.sender_id,
                "chat_name": sender_name,
                "sender_id": msg.sender_id,
                "sender_name": sender_name,
                "preview": make_preview(text, file_data, poll_data),
                "message_id": msg.id
            })
            msg.is_delivered = True

        for m in db.query(RoomMember).filter(RoomMember.user_id == user_id).all():
            state = db.query(RoomReadState).filter(
                RoomReadState.room_id == m.room_id,
                RoomReadState.user_id == user_id).first()
            last_id = db.query(func.max(Message.id)).filter(
                Message.room_id == m.room_id).scalar() or 0
            if state is None:
                db.add(RoomReadState(room_id=m.room_id, user_id=user_id, last_read_id=last_id))
                continue
            if last_id > (state.last_read_id or 0):
                unread = db.query(Message).filter(
                    Message.room_id == m.room_id,
                    Message.id > (state.last_read_id or 0),
                    Message.sender_id != user_id
                ).order_by(Message.id).all()
                if unread:
                    r = db.query(Room).filter(Room.id == m.room_id).first()
                    last_msg = unread[-1]
                    text, _, _, _ = parse_content(last_msg.content)
                    await manager.send_to_user(user_id, {
                        "type": "notification",
                        "chat_type": "room",
                        "chat_id": m.room_id,
                        "chat_name": r.name if r else "Chat",
                        "sender_id": last_msg.sender_id,
                        "sender_name": get_sender_name(db, last_msg.sender_id),
                        "preview": make_preview(text),
                        "count": len(unread),
                        "message_id": last_msg.id
                    })
                state.last_read_id = last_id
        db.commit()
    except Exception as e:
        print(f"[WS ERROR] on-connect delivery: {type(e).__name__}: {e}", flush=True)
    finally:
        db.close()

    # ---- main loop ----
    try:
        while True:
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:
                raise
            except Exception:
                continue
            if not isinstance(data, dict):
                continue

            try:
                preview = json.dumps(data, ensure_ascii=False)
                if len(preview) > 300:
                    preview = preview[:300] + "...(truncated)"
            except Exception:
                preview = str(data)[:300]
            print(f"[WS IN] user={user_id} data={preview}", flush=True)

            db = session_local()
            try:
                msg_type = data.get("type")

                if msg_type == "typing":
                    to_user = to_int(data.get("to"))
                    room_id = to_int(data.get("room_id"))
                    if not to_user:
                        to_user = None
                    if not room_id:
                        room_id = None
                    typing_event = {"type": "typing", "user_id": user_id}
                    if to_user is not None:
                        await manager.send_to_user(to_user, typing_event)
                    elif room_id is not None:
                        for member in db.query(RoomMember).filter(RoomMember.room_id == room_id).all():
                            if member.user_id != user_id:
                                await manager.send_to_user(member.user_id, typing_event)

                elif msg_type in ("reaction", "react"):
                    await handle_reaction(db, websocket, user_id, data)

                elif msg_type in ("poll_vote", "vote"):
                    await handle_poll_vote(db, websocket, user_id, data)

                elif msg_type == "read":
                    room_id = to_int(data.get("room_id"))
                    if room_id:
                        state = db.query(RoomReadState).filter(
                            RoomReadState.room_id == room_id,
                            RoomReadState.user_id == user_id).first()
                        last_id = db.query(func.max(Message.id)).filter(
                            Message.room_id == room_id).scalar() or 0
                        if state is None:
                            db.add(RoomReadState(room_id=room_id, user_id=user_id, last_read_id=last_id))
                        else:
                            state.last_read_id = max(state.last_read_id or 0, last_id)
                        db.commit()

                elif msg_type == "view":
                    await handle_view(db, websocket, user_id, data)

                elif msg_type in ("ping", "pong"):
                    pass

                else:
                    if (msg_type in ("message", "msg", "chat", "send", "send_message",
                                     "text", "poll", "file")
                            or any(k in data for k in CONTENT_KEYS)
                            or "file" in data or "poll" in data
                            or "to" in data or "room_id" in data):
                        await handle_message(db, websocket, user_id, data)

            except Exception as e:
                print(f"[WS ERROR] {type(e).__name__}: {e}", flush=True)
                try:
                    await websocket.send_json({"type": "error",
                                               "message": f"{type(e).__name__}: {e}"})
                except Exception:
                    pass
            finally:
                db.close()

    except WebSocketDisconnect:
        pass
    finally:
        if manager.disconnect(user_id, websocket):
            await broadcast_status(user_id, False)