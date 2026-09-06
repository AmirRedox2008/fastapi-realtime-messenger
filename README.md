💬 FastAPI Real-time Messenger
PythonFastAPIPostgreSQLWebSockets

A modern, real-time messaging web application inspired by Telegram. This project is a full-stack application featuring a FastAPI backend (with native WebSockets) and a dynamic frontend (Vanilla JS/HTML/CSS).

🌟 Features
Real-time Messaging: Instant messaging powered by FastAPI native WebSockets. No external message broker required!
Authentication & Authorization: Secure login and registration flow using JWT (JSON Web Tokens) and password hashing (Bcrypt).
Live Presence: Live online/offline status indicators for users.
Group & Channel Management: Create, join, leave, and manage groups/channels with roles (Admin/Member) and mute functionality.
Advanced Message Features: Edit, delete, reply, forward, and react to messages with emojis.
User Interactions: Block/Unblock users, search for users/rooms, and view detailed user profiles.
Polls: Create interactive polls in groups and channels.
Responsive UI: A beautiful, Telegram-inspired dark/light theme with smooth animations, optimized for both desktop and mobile devices.
🛠️ Tech Stack
Backend: Python, FastAPI, SQLAlchemy
Database: PostgreSQL
Real-time Communication: FastAPI WebSockets (websocket.py)
Authentication: JWT (python-jose), Passlib (bcrypt)
Frontend: HTML5, CSS3, Vanilla JavaScript (ES6+), Fetch API, WebSockets API
🚀 Getting Started
Follow these instructions to get a copy of the project up and running on your local machine for development and testing purposes.

Prerequisites
Python 3.9+
PostgreSQL
Installation & Setup
Clone the repository:
git clone https://github.com/AmirRedox2008/fastapi-realtime-messenger.gitcd fastapi-realtime-messenger
Create a virtual environment and activate it:
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
Install required Python packages: 
pip install fastapi uvicorn sqlalchemy psycopg2-binary python-jose passlib[bcrypt] httpx python-multipart jinja2
Configure the Database:
Open database.py and update the PostgreSQL connection string with your local database credentials.
Ensure the database specified in the connection string exists.
Run the Application: 
uvicorn main:app --reload
Access the App:
Open your browser and navigate to http://localhost:8000
Register a new account.
Login to start messaging!

📁 Project Structure:

fastapi-realtime-messenger/
├── main.py             # Entry point, includes routers and serves frontend
├── database.py         # SQLAlchemy database connection setup
├── model.py            # SQLAlchemy database models (User, Message, Room, etc.)
├── login.py            # Authentication logic (Register, Login, JWT generation)
├── chat.py             # Core messaging logic (History, Block, Edit, Status)
├── rooms.py            # Group/Channel creation and management endpoints
├── profile.py          # User profile and search endpoints
├── websocket.py        # FastAPI WebSocket manager for real-time communication
├── .gitignore
└── templates/
    └── index.html      # The entire frontend UI and logic

    

