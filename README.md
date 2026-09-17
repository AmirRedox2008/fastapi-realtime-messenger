💬 FastAPI Real-time Messenger

PythonFastAPILicense

A modern, real-time messaging web application inspired by Telegram.Built with a FastAPI backend (native WebSockets) and a dynamicVanilla JS frontend — no external message broker required.
📸 Demo

App Screenshot
🌟 Features
Messaging

    Real-time delivery — native FastAPI WebSockets
    Offline queue — messages sent while a user was offline are delivered on reconnect
    Reply to specific messages (with server-generated previews)
    Emoji reactions on any message
    Edit your own messages
    Polls — create polls with live vote updates
    Channel view counts — each post counts unique views once

Chats

    Direct messages (1-on-1)
    Groups — anyone can post, join/leave freely
    Channels — only admins can broadcast
    Admin roles — promote/demote members, kick users
    Mute notifications per room
    Read states — per-room unread counters

Users

    JWT authentication (Bcrypt password hashing)
    Live presence — online/offline indicators
    Block / unblock users (blocks messaging both ways)
    Search users by username, groups & channels
    Explore — discover public groups & channels
    User profiles — name, username, phone lookup

UI

    Telegram-inspired dark/light theme
    Fully responsive (desktop & mobile)
    Smooth animations, typing indicators, toast notifications

🛠️ Tech Stack
Layer	Technology
Backend	Python, FastAPI, SQLAlchemy
Database	PostgreSQL
Real-time	FastAPI WebSockets (in-memory ConnectionManager)
Auth	python-jose (JWT), Passlib (Bcrypt)
Frontend	HTML5, CSS3, Vanilla JS (ES6+), Fetch API, WebSocket API
🚀 Getting Started
Prerequisites

    Python 3.9+
    PostgreSQL

Installation

# 1. Clonegit clone https://github.com/AmirRedox2008/fastapi-realtime-messenger.gitcd fastapi-realtime-messenger# 2. Virtual environmentpython -m venv venvsource venv/bin/activate        # Windows: venv\Scripts\activate# 3. Dependenciespip install -r requirements.txt# 4. Configure environmentcp .env.example .env# → edit .env: set DB URL and a secure SECRET_KEY#   (generate one: python -c "import secrets; print(secrets.token_hex(32))")# 5. Runuvicorn main:app --reload

Open http://localhost:8000 — register, login, and start chatting!
Interactive API docs: http://localhost:8000/docs
📁 Project Structure
text
 
  
 
 
├── main.py          # App entry, routers, startup
├── websocket.py     # WebSocket endpoint & message handlers
├── login.py         # Auth routes (register/login/me)
├── chat.py          # DM history, block, account
├── rooms.py         # Groups & channels CRUD
├── profile.py       # Username, profile, search
├── model.py         # SQLAlchemy models
├── database.py      # DB engine & session
└── templates/       # Frontend (single-page app)
 
 
🏗️ Architecture Notes

     ConnectionManager keeps one active WebSocket per user
    (new connections replace old ones automatically).
     Messages are persisted first, then pushed — delivery status
    (is_delivered) is updated when the recipient is online.
     Channel posts are admin-only, enforced server-side.

⚠️ Known Limitations

     The WebSocket state lives in-memory — currently the app must run
    with a single uvicorn worker. Redis pub/sub is on the roadmap
    for horizontal scaling.
     Schema is created via Base.metadata.create_all() — no migrations yet
    (Alembic planned).

🗺️ Roadmap

     Redis pub/sub for multi-worker support
     Message forwarding & deletion
     File/media uploads with proper storage
     Alembic migrations
     Rate limiting on auth endpoints
     Docker deployment
