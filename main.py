from fastapi import FastAPI
from database import engine, Base
from fastapi import Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import chat,login,profile,rooms,websocket

app = FastAPI()

Base.metadata.create_all(engine)

templates = Jinja2Templates(directory="templates")

app.include_router(login.router)
app.include_router(rooms.router)
app.include_router(profile.router)
app.include_router(chat.router)
app.include_router(websocket.router)

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})