from fastapi import FastAPI
from database import engine, Base
from fastapi import Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import chat, login, profile, rooms, websocket

app = FastAPI()

Base.metadata.create_all(engine)

templates = Jinja2Templates(directory="templates")

app.include_router(login.router)
app.include_router(rooms.router)
app.include_router(profile.router)
app.include_router(chat.router)
app.include_router(websocket.router)


@app.on_event("startup")
async def startup():
    print("\n" + "=" * 60)
    print("  >>> MY MESSENGER RUNNING - all fixes active <<<")
    print("  >>> backend tester: http://localhost:8000/test-ws")
    print("  >>> room inspector: http://localhost:8000/debug/rooms")
    print("=" * 60 + "\n")


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request, "index.html")


TEST_PAGE = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>WS tester</title></head>
<body style="font-family:monospace;background:#111;color:#eee;padding:20px">
<h3>Backend tester</h3>
<p>1) Login with the account you want to test &nbsp; 2) fill room_id &nbsp; 3) Send</p>
<input id="phone" placeholder="phone number">
<input id="pass" type="password" placeholder="password">
<button onclick="doLogin()">Login</button>
<hr>
<input id="to" placeholder="to (user id, DM only)" size="30">
<input id="room" placeholder="room_id (channel/group)" size="30">
<input id="txt" placeholder="message text" size="30">
<button onclick="sendMsg()">Send</button>
<pre id="log" style="background:#000;padding:10px;max-height:400px;overflow:auto"></pre>
<script>
let socket=null;
function log(s){document.getElementById('log').textContent+=s+"\\n";}
async function doLogin(){
  const body=new URLSearchParams({username:document.getElementById('phone').value,
                                  password:document.getElementById('pass').value});
  const r=await fetch('/login',{method:'POST',body});
  const j=await r.json();
  if(!j.access_token){log("LOGIN FAILED "+JSON.stringify(j));return;}
  log("login OK");
  socket=new WebSocket("ws://"+location.host+"/ws?token="+j.access_token);
  socket.onopen=()=>log("WS CONNECTED");
  socket.onmessage=e=>log("<< "+e.data);
  socket.onclose=e=>log("WS CLOSED code="+e.code);
}
function sendMsg(){
  if(!socket){log("login first");return;}
  const m={text:document.getElementById('txt').value,temp_id:Date.now()};
  const to=document.getElementById('to').value;
  const room=document.getElementById('room').value;
  if(to)m.to=parseInt(to);
  if(room)m.room_id=parseInt(room);
  log(">> "+JSON.stringify(m));
  socket.send(JSON.stringify(m));
}
</script>
</body>
</html>"""


@app.get("/test-ws", response_class=HTMLResponse)
async def test_ws():
    return HTMLResponse(TEST_PAGE)