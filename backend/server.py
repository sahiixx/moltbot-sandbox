from fastapi import FastAPI, APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Request, Response, Cookie, Depends
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import json
import secrets
import subprocess
import signal
import asyncio
import httpx
import websockets
from websockets.exceptions import ConnectionClosed
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
import re


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'moltbot_app')]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Moltbot Gateway Management
MOLTBOT_PORT = 18789
MOLTBOT_CONTROL_PORT = 18791
CONFIG_DIR = os.path.expanduser("~/.clawdbot")
CONFIG_FILE = os.path.join(CONFIG_DIR, "moltbot.json")
WORKSPACE_DIR = os.path.expanduser("~/clawd")

# Global state for gateway process (per-user)
# In production, this would be per-user instances, but for simplicity we use single instance with owner tracking
gateway_state = {
    "process": None,
    "pid": None,
    "token": None,
    "provider": None,
    "started_at": None,
    "owner_user_id": None  # Track which user owns this instance
}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============== Pydantic Models ==============

class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StatusCheckCreate(BaseModel):
    client_name: str


class MoltbotStartRequest(BaseModel):
    provider: str  # "anthropic" or "openai"
    apiKey: str


class MoltbotStartResponse(BaseModel):
    ok: bool
    controlUrl: str
    token: str
    message: str


class MoltbotStatusResponse(BaseModel):
    running: bool
    pid: Optional[int] = None
    provider: Optional[str] = None
    started_at: Optional[str] = None
    controlUrl: Optional[str] = None
    owner_user_id: Optional[str] = None
    is_owner: Optional[bool] = None


class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    created_at: Optional[datetime] = None


class SessionRequest(BaseModel):
    session_id: str


# ============== Authentication Helpers ==============

EMERGENT_AUTH_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"
SESSION_EXPIRY_DAYS = 7


async def get_current_user(request: Request) -> Optional[User]:
    """
    Get current user from session token.
    Checks cookie first, then Authorization header as fallback.
    Returns None if not authenticated.
    """
    session_token = None
    
    # Check cookie first
    session_token = request.cookies.get("session_token")
    
    # Fallback to Authorization header
    if not session_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            session_token = auth_header.split(" ")[1]
    
    if not session_token:
        return None
    
    # Look up session in database
    session_doc = await db.user_sessions.find_one(
        {"session_token": session_token},
        {"_id": 0}
    )
    
    if not session_doc:
        return None
    
    # Check expiry
    expires_at = session_doc.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    if expires_at < datetime.now(timezone.utc):
        return None
    
    # Get user
    user_doc = await db.users.find_one(
        {"user_id": session_doc["user_id"]},
        {"_id": 0}
    )
    
    if not user_doc:
        return None
    
    return User(**user_doc)


async def require_auth(request: Request) -> User:
    """Dependency that requires authentication"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ============== Auth Endpoints ==============

@api_router.post("/auth/session")
async def create_session(request: SessionRequest, response: Response):
    """
    Exchange session_id from Emergent Auth for a session token.
    Creates user if not exists, creates session, sets cookie.
    """
    try:
        # Call Emergent Auth to get user data
        async with httpx.AsyncClient() as client:
            auth_response = await client.get(
                EMERGENT_AUTH_URL,
                headers={"X-Session-ID": request.session_id},
                timeout=10.0
            )
        
        if auth_response.status_code != 200:
            logger.error(f"Emergent Auth error: {auth_response.status_code} - {auth_response.text}")
            raise HTTPException(status_code=401, detail="Invalid session_id")
        
        auth_data = auth_response.json()
        email = auth_data.get("email")
        name = auth_data.get("name", email.split("@")[0] if email else "User")
        picture = auth_data.get("picture")
        emergent_session_token = auth_data.get("session_token")
        
        if not email:
            raise HTTPException(status_code=400, detail="No email in auth response")
        
        # Check if user exists
        existing_user = await db.users.find_one({"email": email}, {"_id": 0})
        
        if existing_user:
            user_id = existing_user["user_id"]
            # Update user info
            await db.users.update_one(
                {"user_id": user_id},
                {"$set": {"name": name, "picture": picture}}
            )
        else:
            # Create new user
            user_id = f"user_{uuid.uuid4().hex[:12]}"
            await db.users.insert_one({
                "user_id": user_id,
                "email": email,
                "name": name,
                "picture": picture,
                "created_at": datetime.now(timezone.utc)
            })
        
        # Create session
        session_token = secrets.token_hex(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_EXPIRY_DAYS)
        
        await db.user_sessions.insert_one({
            "user_id": user_id,
            "session_token": session_token,
            "expires_at": expires_at,
            "created_at": datetime.now(timezone.utc)
        })
        
        # Set cookie
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=True,
            samesite="none",
            path="/",
            max_age=SESSION_EXPIRY_DAYS * 24 * 60 * 60
        )
        
        # Get user data
        user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
        
        return {
            "ok": True,
            "user": user_doc
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/auth/me")
async def get_me(request: Request):
    """Get current authenticated user"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user.model_dump()


@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    """Logout - delete session and clear cookie"""
    session_token = request.cookies.get("session_token")
    
    if session_token:
        await db.user_sessions.delete_one({"session_token": session_token})
    
    response.delete_cookie(
        key="session_token",
        path="/",
        secure=True,
        samesite="none"
    )
    
    return {"ok": True, "message": "Logged out"}


# ============== Moltbot Helpers ==============

def generate_token():
    """Generate a random gateway token"""
    return secrets.token_hex(32)


def create_moltbot_config(token: str):
    """Create a Moltbot configuration file"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    
    config = {
        "gateway": {
            "mode": "local",
            "port": MOLTBOT_PORT,
            "bind": "lan",
            "auth": {
                "mode": "token",
                "token": token
            },
            "controlUi": {
                "enabled": True,
                "allowInsecureAuth": True
            }
        },
        "agents": {
            "defaults": {
                "workspace": WORKSPACE_DIR
            }
        }
    }
    
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    
    logger.info(f"Created Moltbot config at {CONFIG_FILE}")
    return config


async def start_gateway_process(api_key: str, provider: str, owner_user_id: str):
    """Start the Moltbot gateway process"""
    global gateway_state
    
    # Kill existing process if any
    if gateway_state["process"]:
        try:
            gateway_state["process"].terminate()
            await asyncio.sleep(1)
            gateway_state["process"].kill()
        except:
            pass
        gateway_state["process"] = None
        gateway_state["pid"] = None
    
    # Generate token and create config
    token = generate_token()
    create_moltbot_config(token)
    
    # Set environment variables
    env = os.environ.copy()
    if provider == "anthropic":
        env["ANTHROPIC_API_KEY"] = api_key
    elif provider == "openai":
        env["OPENAI_API_KEY"] = api_key
    
    # Set gateway token for auth
    env["CLAWDBOT_GATEWAY_TOKEN"] = token
    
    # Start the gateway
    logger.info(f"Starting Moltbot gateway on port {MOLTBOT_PORT}...")
    
    process = subprocess.Popen(
        ["clawdbot", "gateway", "--port", str(MOLTBOT_PORT), "--bind", "lan", "--token", token, "--allow-unconfigured"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid  # Create new process group
    )
    
    gateway_state["process"] = process
    gateway_state["pid"] = process.pid
    gateway_state["token"] = token
    gateway_state["provider"] = provider
    gateway_state["started_at"] = datetime.now(timezone.utc).isoformat()
    gateway_state["owner_user_id"] = owner_user_id
    
    # Wait for gateway to be ready
    max_wait = 30
    start_time = asyncio.get_event_loop().time()
    
    async with httpx.AsyncClient() as client:
        while asyncio.get_event_loop().time() - start_time < max_wait:
            try:
                response = await client.get(f"http://127.0.0.1:{MOLTBOT_PORT}/", timeout=2.0)
                if response.status_code == 200:
                    logger.info("Moltbot gateway is ready!")
                    
                    # Store config in database for persistence
                    await db.moltbot_configs.update_one(
                        {"owner_user_id": owner_user_id},
                        {
                            "$set": {
                                "provider": provider,
                                "token": token,
                                "started_at": gateway_state["started_at"],
                                "updated_at": datetime.now(timezone.utc)
                            }
                        },
                        upsert=True
                    )
                    
                    return token
            except Exception as e:
                pass
            await asyncio.sleep(1)
    
    # Check if process died
    if process.poll() is not None:
        stderr = process.stderr.read().decode() if process.stderr else ""
        raise HTTPException(status_code=500, detail=f"Gateway failed to start: {stderr}")
    
    raise HTTPException(status_code=500, detail="Gateway did not become ready in time")


def check_gateway_running():
    """Check if the gateway process is still running"""
    if gateway_state["process"]:
        poll = gateway_state["process"].poll()
        if poll is None:
            return True
        else:
            gateway_state["process"] = None
            gateway_state["pid"] = None
            return False
    return False


# ============== Moltbot API Endpoints (Protected) ==============

@api_router.get("/")
async def root():
    return {"message": "Moltbot Hosting API"}


@api_router.post("/moltbot/start", response_model=MoltbotStartResponse)
async def start_moltbot(request: MoltbotStartRequest, req: Request):
    """Start the Moltbot gateway with the provided API key (requires auth)"""
    user = await require_auth(req)
    
    if request.provider not in ["anthropic", "openai"]:
        raise HTTPException(status_code=400, detail="Invalid provider. Use 'anthropic' or 'openai'")
    
    if not request.apiKey or len(request.apiKey) < 10:
        raise HTTPException(status_code=400, detail="Invalid API key")
    
    # Check if Moltbot is already running by another user
    if check_gateway_running() and gateway_state["owner_user_id"] != user.user_id:
        raise HTTPException(
            status_code=403, 
            detail="Moltbot is already running by another user. Please wait for them to stop it."
        )
    
    try:
        token = await start_gateway_process(request.apiKey, request.provider, user.user_id)
        
        return MoltbotStartResponse(
            ok=True,
            controlUrl="/api/moltbot/ui/",
            token=token,
            message="Moltbot started successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start Moltbot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/moltbot/status", response_model=MoltbotStatusResponse)
async def get_moltbot_status(request: Request):
    """Get the current status of the Moltbot gateway"""
    user = await get_current_user(request)
    running = check_gateway_running()
    
    if running:
        is_owner = user and gateway_state["owner_user_id"] == user.user_id
        return MoltbotStatusResponse(
            running=True,
            pid=gateway_state["pid"],
            provider=gateway_state["provider"],
            started_at=gateway_state["started_at"],
            controlUrl="/api/moltbot/ui/",
            owner_user_id=gateway_state["owner_user_id"],
            is_owner=is_owner
        )
    else:
        return MoltbotStatusResponse(running=False)


@api_router.post("/moltbot/stop")
async def stop_moltbot(request: Request):
    """Stop the Moltbot gateway (only owner can stop)"""
    user = await require_auth(request)
    
    global gateway_state
    
    if not check_gateway_running():
        return {"ok": True, "message": "Moltbot is not running"}
    
    # Check if user is the owner
    if gateway_state["owner_user_id"] != user.user_id:
        raise HTTPException(status_code=403, detail="Only the owner can stop Moltbot")
    
    if gateway_state["process"]:
        try:
            os.killpg(os.getpgid(gateway_state["process"].pid), signal.SIGTERM)
            await asyncio.sleep(2)
            try:
                os.killpg(os.getpgid(gateway_state["process"].pid), signal.SIGKILL)
            except:
                pass
        except Exception as e:
            logger.error(f"Error stopping gateway: {e}")
        
        gateway_state["process"] = None
        gateway_state["pid"] = None
        gateway_state["token"] = None
        gateway_state["provider"] = None
        gateway_state["started_at"] = None
        gateway_state["owner_user_id"] = None
    
    return {"ok": True, "message": "Moltbot stopped"}


@api_router.get("/moltbot/token")
async def get_moltbot_token(request: Request):
    """Get the current gateway token for authentication (only owner)"""
    user = await require_auth(request)
    
    if not check_gateway_running():
        raise HTTPException(status_code=404, detail="Moltbot not running")
    
    # Only owner can get the token
    if gateway_state["owner_user_id"] != user.user_id:
        raise HTTPException(status_code=403, detail="Only the owner can access the token")
    
    return {"token": gateway_state.get("token")}


# ============== Moltbot Proxy (Protected) ==============

@api_router.api_route("/moltbot/ui/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_moltbot_ui(request: Request, path: str = ""):
    """Proxy requests to the Moltbot Control UI (only owner can access)"""
    user = await get_current_user(request)
    
    if not check_gateway_running():
        return HTMLResponse(
            content="<html><body><h1>Moltbot not running</h1><p>Please start Moltbot first.</p><a href='/'>Go to setup</a></body></html>",
            status_code=503
        )
    
    # Check if user is the owner
    if not user or gateway_state["owner_user_id"] != user.user_id:
        return HTMLResponse(
            content="<html><body><h1>Access Denied</h1><p>This Moltbot instance is owned by another user.</p><a href='/'>Go back</a></body></html>",
            status_code=403
        )
    
    target_url = f"http://127.0.0.1:{MOLTBOT_PORT}/{path}"
    
    # Handle query string
    if request.query_params:
        target_url += f"?{request.query_params}"
    
    async with httpx.AsyncClient() as client:
        try:
            # Forward the request
            headers = dict(request.headers)
            headers.pop("host", None)
            headers.pop("content-length", None)
            
            body = await request.body()
            
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                timeout=30.0
            )
            
            # Filter response headers
            exclude_headers = {"content-encoding", "content-length", "transfer-encoding", "connection"}
            response_headers = {
                k: v for k, v in response.headers.items() 
                if k.lower() not in exclude_headers
            }
            
            # Get content and rewrite WebSocket URLs if HTML
            content = response.content
            content_type = response.headers.get("content-type", "")
            
            # Get the current gateway token
            current_token = gateway_state.get("token", "")
            
            # If it's HTML, rewrite any WebSocket URLs to use our proxy
            if "text/html" in content_type:
                content_str = content.decode('utf-8', errors='ignore')
                # Inject WebSocket URL override script with token
                ws_override = f'''
<script>
// Moltbot Proxy Configuration
window.__MOLTBOT_PROXY_TOKEN__ = "{current_token}";
window.__MOLTBOT_PROXY_WS_URL__ = (window.location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + window.location.host + '/api/moltbot/ws';

// Override WebSocket to use proxy path
(function() {{
    const originalWS = window.WebSocket;
    const proxyWsUrl = window.__MOLTBOT_PROXY_WS_URL__;
    
    window.WebSocket = function(url, protocols) {{
        let finalUrl = url;
        
        // Rewrite any Moltbot gateway URLs to use our proxy
        if (url.includes('127.0.0.1:18789') || 
            url.includes('localhost:18789') ||
            url.includes('0.0.0.0:18789') ||
            (url.includes(':18789') && !url.includes('/api/moltbot/'))) {{
            finalUrl = proxyWsUrl;
        }}
        
        // If it's a relative URL or same-origin, redirect to proxy
        try {{
            const urlObj = new URL(url, window.location.origin);
            if (urlObj.port === '18789' || urlObj.pathname === '/' && !url.startsWith(proxyWsUrl)) {{
                finalUrl = proxyWsUrl;
            }}
        }} catch (e) {{}}
        
        console.log('[Moltbot Proxy] WebSocket:', url, '->', finalUrl);
        return new originalWS(finalUrl, protocols);
    }};
    
    // Copy static properties
    window.WebSocket.prototype = originalWS.prototype;
    window.WebSocket.CONNECTING = originalWS.CONNECTING;
    window.WebSocket.OPEN = originalWS.OPEN;
    window.WebSocket.CLOSING = originalWS.CLOSING;
    window.WebSocket.CLOSED = originalWS.CLOSED;
}})();
</script>
'''
                # Insert before </head> or at start of <body>
                if '</head>' in content_str:
                    content_str = content_str.replace('</head>', ws_override + '</head>')
                elif '<body>' in content_str:
                    content_str = content_str.replace('<body>', '<body>' + ws_override)
                else:
                    content_str = ws_override + content_str
                content = content_str.encode('utf-8')
            
            return Response(
                content=content,
                status_code=response.status_code,
                headers=response_headers,
                media_type=response.headers.get("content-type")
            )
        except httpx.RequestError as e:
            logger.error(f"Proxy error: {e}")
            raise HTTPException(status_code=502, detail="Failed to connect to Moltbot")


# Root proxy for Moltbot UI (handles /api/moltbot/ui without trailing path)
@api_router.get("/moltbot/ui")
async def proxy_moltbot_ui_root(request: Request):
    """Redirect to Moltbot UI with trailing slash"""
    return Response(
        status_code=307,
        headers={"Location": "/api/moltbot/ui/"}
    )


# WebSocket proxy for Moltbot (Protected)
@api_router.websocket("/moltbot/ws")
async def websocket_proxy(websocket: WebSocket):
    """WebSocket proxy for Moltbot Control UI"""
    await websocket.accept()
    
    if not check_gateway_running():
        await websocket.close(code=1013, reason="Moltbot not running")
        return
    
    # Note: WebSocket auth is handled by the token in the connection itself
    # The Control UI passes the token in the connect message
    
    # Get the token from state
    token = gateway_state.get("token")
    
    # Moltbot expects WebSocket connection with optional auth in query params
    moltbot_ws_url = f"ws://127.0.0.1:{MOLTBOT_PORT}/"
    
    logger.info(f"WebSocket proxy connecting to: {moltbot_ws_url}")
    
    try:
        # Additional headers for connection
        extra_headers = {}
        if token:
            extra_headers["X-Auth-Token"] = token
        
        async with websockets.connect(
            moltbot_ws_url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=10,
            additional_headers=extra_headers if extra_headers else None
        ) as moltbot_ws:
            
            async def client_to_moltbot():
                try:
                    while True:
                        try:
                            data = await websocket.receive()
                            if data["type"] == "websocket.receive":
                                if "text" in data:
                                    await moltbot_ws.send(data["text"])
                                elif "bytes" in data:
                                    await moltbot_ws.send(data["bytes"])
                            elif data["type"] == "websocket.disconnect":
                                break
                        except WebSocketDisconnect:
                            break
                except Exception as e:
                    logger.error(f"Client to Moltbot error: {e}")
            
            async def moltbot_to_client():
                try:
                    async for message in moltbot_ws:
                        if websocket.client_state == WebSocketState.CONNECTED:
                            if isinstance(message, str):
                                await websocket.send_text(message)
                            else:
                                await websocket.send_bytes(message)
                except ConnectionClosed as e:
                    logger.info(f"Moltbot WebSocket closed: {e}")
                except Exception as e:
                    logger.error(f"Moltbot to client error: {e}")
            
            # Run both directions concurrently
            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(client_to_moltbot()),
                    asyncio.create_task(moltbot_to_client())
                ],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel pending tasks
            for task in pending:
                task.cancel()
                
    except Exception as e:
        logger.error(f"WebSocket proxy error: {e}")
    finally:
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close(code=1011, reason="Proxy connection ended")
        except:
            pass


# ============== Legacy Status Endpoints ==============

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    
    _ = await db.status_checks.insert_one(doc)
    return status_obj


@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    
    return status_checks


# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    # Stop Moltbot gateway on shutdown
    global gateway_state
    if gateway_state["process"]:
        try:
            os.killpg(os.getpgid(gateway_state["process"].pid), signal.SIGTERM)
        except:
            pass
    client.close()
