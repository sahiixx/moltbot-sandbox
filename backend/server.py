from fastapi import FastAPI, APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.responses import StreamingResponse, HTMLResponse
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
from datetime import datetime, timezone
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

# Global state for gateway process
gateway_state = {
    "process": None,
    "pid": None,
    "token": None,
    "provider": None,
    "started_at": None
}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Pydantic Models
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
            "bind": "loopback",
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


async def start_gateway_process(api_key: str, provider: str):
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
    
    # Start the gateway
    logger.info(f"Starting Moltbot gateway on port {MOLTBOT_PORT}...")
    
    process = subprocess.Popen(
        ["clawdbot", "gateway", "--port", str(MOLTBOT_PORT), "--bind", "any", "--allow-unconfigured"],
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
    
    # Wait for gateway to be ready
    max_wait = 30
    start_time = asyncio.get_event_loop().time()
    
    async with httpx.AsyncClient() as client:
        while asyncio.get_event_loop().time() - start_time < max_wait:
            try:
                response = await client.get(f"http://127.0.0.1:{MOLTBOT_PORT}/", timeout=2.0)
                if response.status_code == 200:
                    logger.info("Moltbot gateway is ready!")
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


# API Routes
@api_router.get("/")
async def root():
    return {"message": "Moltbot Hosting API"}


@api_router.post("/moltbot/start", response_model=MoltbotStartResponse)
async def start_moltbot(request: MoltbotStartRequest):
    """Start the Moltbot gateway with the provided API key"""
    if request.provider not in ["anthropic", "openai"]:
        raise HTTPException(status_code=400, detail="Invalid provider. Use 'anthropic' or 'openai'")
    
    if not request.apiKey or len(request.apiKey) < 10:
        raise HTTPException(status_code=400, detail="Invalid API key")
    
    try:
        token = await start_gateway_process(request.apiKey, request.provider)
        
        # Store in database
        await db.moltbot_sessions.update_one(
            {"_id": "current"},
            {
                "$set": {
                    "provider": request.provider,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "token": token
                }
            },
            upsert=True
        )
        
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
async def get_moltbot_status():
    """Get the current status of the Moltbot gateway"""
    running = check_gateway_running()
    
    if running:
        return MoltbotStatusResponse(
            running=True,
            pid=gateway_state["pid"],
            provider=gateway_state["provider"],
            started_at=gateway_state["started_at"],
            controlUrl="/api/moltbot/ui/"
        )
    else:
        return MoltbotStatusResponse(running=False)


@api_router.post("/moltbot/stop")
async def stop_moltbot():
    """Stop the Moltbot gateway"""
    global gateway_state
    
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
    
    return {"ok": True, "message": "Moltbot stopped"}


# Reverse Proxy for Moltbot Control UI
@api_router.api_route("/moltbot/ui/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_moltbot_ui(request: Request, path: str = ""):
    """Proxy requests to the Moltbot Control UI"""
    if not check_gateway_running():
        return HTMLResponse(
            content="<html><body><h1>Moltbot not running</h1><p>Please start Moltbot first.</p><a href='/'>Go to setup</a></body></html>",
            status_code=503
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
            
            # If it's HTML, rewrite any WebSocket URLs to use our proxy
            if "text/html" in content_type:
                content_str = content.decode('utf-8', errors='ignore')
                # Inject WebSocket URL override script
                ws_override = '''
<script>
// Override WebSocket to use proxy path
(function() {
    const originalWS = window.WebSocket;
    window.WebSocket = function(url, protocols) {
        // Rewrite ws://localhost:18789 or similar to our proxy
        if (url.includes('127.0.0.1:18789') || url.includes('localhost:18789')) {
            const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            url = wsProtocol + '//' + window.location.host + '/api/moltbot/ws';
        }
        // If relative WebSocket URL, make it absolute to our proxy
        if (url.startsWith('/') && !url.startsWith('/api/moltbot/ws')) {
            const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            url = wsProtocol + '//' + window.location.host + '/api/moltbot/ws';
        }
        // Handle case where Control UI uses same-origin WebSocket
        if (url === window.location.origin || url === window.location.origin + '/') {
            const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            url = wsProtocol + '//' + window.location.host + '/api/moltbot/ws';
        }
        console.log('[Moltbot Proxy] WebSocket connecting to:', url);
        return new originalWS(url, protocols);
    };
    window.WebSocket.prototype = originalWS.prototype;
    window.WebSocket.CONNECTING = originalWS.CONNECTING;
    window.WebSocket.OPEN = originalWS.OPEN;
    window.WebSocket.CLOSING = originalWS.CLOSING;
    window.WebSocket.CLOSED = originalWS.CLOSED;
})();
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


# WebSocket proxy for Moltbot
@api_router.websocket("/moltbot/ws")
async def websocket_proxy(websocket: WebSocket):
    """WebSocket proxy for Moltbot Control UI"""
    await websocket.accept()
    
    if not check_gateway_running():
        await websocket.close(code=1013, reason="Moltbot not running")
        return
    
    moltbot_ws_url = f"ws://127.0.0.1:{MOLTBOT_PORT}/"
    
    try:
        async with websockets.connect(moltbot_ws_url) as moltbot_ws:
            async def client_to_moltbot():
                try:
                    while True:
                        data = await websocket.receive_text()
                        await moltbot_ws.send(data)
                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    logger.error(f"Client to Moltbot error: {e}")
            
            async def moltbot_to_client():
                try:
                    async for message in moltbot_ws:
                        await websocket.send_text(message)
                except Exception as e:
                    logger.error(f"Moltbot to client error: {e}")
            
            await asyncio.gather(client_to_moltbot(), moltbot_to_client())
    except Exception as e:
        logger.error(f"WebSocket proxy error: {e}")
        await websocket.close(code=1011, reason="Internal error")


# Legacy status endpoints
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
