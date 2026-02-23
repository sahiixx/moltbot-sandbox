from fastapi import FastAPI, APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Request, Response, UploadFile, File
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import json
import secrets
import subprocess
import asyncio
import httpx
import websockets
from websockets.exceptions import ConnectionClosed
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta

# WhatsApp monitoring
from whatsapp_monitor import get_whatsapp_status, fix_registered_flag
from emergentintegrations.llm.chat import LlmChat, UserMessage
from emergentintegrations.llm.openai import OpenAISpeechToText
# Gateway management (supervisor-based)
from gateway_config import write_gateway_env, clear_gateway_env
from supervisor_client import SupervisorClient

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
CONFIG_FILE = os.path.join(CONFIG_DIR, "clawdbot.json")
WORKSPACE_DIR = os.path.expanduser("~/clawd")

# Global state for gateway (per-user)
# Note: Process is managed by supervisor, we only track metadata here
gateway_state = {
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


class OpenClawStartRequest(BaseModel):
    provider: str = "emergent"  # "emergent", "anthropic", or "openai"
    apiKey: Optional[str] = None  # Optional - uses Emergent key if not provided


class OpenClawStartResponse(BaseModel):
    ok: bool
    controlUrl: str
    token: str
    message: str


class OpenClawStatusResponse(BaseModel):
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


async def get_instance_owner() -> Optional[dict]:
    """Get the instance owner from database. Returns None if not locked yet."""
    doc = await db.instance_config.find_one({"_id": "instance_owner"})
    return doc


async def set_instance_owner(user: User) -> None:
    """Lock the instance to a specific user. Only succeeds if not already locked."""
    await db.instance_config.update_one(
        {"_id": "instance_owner"},
        {
            "$setOnInsert": {
                "user_id": user.user_id,
                "email": user.email,
                "name": user.name,
                "locked_at": datetime.now(timezone.utc)
            }
        },
        upsert=True
    )


async def check_instance_access(user: User) -> bool:
    """Check if user is allowed to access this instance. Returns True if allowed."""
    owner = await get_instance_owner()
    if not owner:
        # Instance not locked yet - anyone can access
        return True
    return owner.get("user_id") == user.user_id


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
    """Dependency that requires authentication and instance access"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Check if user is allowed to access this instance
    if not await check_instance_access(user):
        owner = await get_instance_owner()
        raise HTTPException(
            status_code=403, 
            detail=f"This instance is locked to {owner.get('email', 'another user')}. Access denied."
        )
    return user


# ============== Auth Endpoints ==============

@api_router.get("/auth/instance")
async def get_instance_status():
    """
    Check if the instance is locked.
    Public endpoint - only returns locked status, no owner details.
    """
    owner = await get_instance_owner()
    if owner:
        return {"locked": True}
    return {"locked": False}


@api_router.post("/auth/session")
async def create_session(request: SessionRequest, response: Response):
    """
    Exchange session_id from Emergent Auth for a session token.
    Creates user if not exists, creates session, sets cookie.
    Blocks non-owners if instance is locked.
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

        if not email:
            raise HTTPException(status_code=400, detail="No email in auth response")

        # Check if instance is locked to another user
        owner = await get_instance_owner()
        if owner and owner.get("email") != email:
            logger.warning(f"Blocked login attempt from {email} - instance locked to {owner.get('email')}")
            raise HTTPException(
                status_code=403,
                detail=f"This instance is private and locked to {owner.get('email')}. Access denied."
            )

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

# Persistent paths for Node.js and clawdbot
NODE_DIR = "/root/nodejs"
CLAWDBOT_DIR = "/root/.clawdbot-bin"
CLAWDBOT_WRAPPER = "/root/run_clawdbot.sh"

def get_clawdbot_command():
    """Get the path to clawdbot executable"""
    # Try wrapper script first
    if os.path.exists(CLAWDBOT_WRAPPER):
        return CLAWDBOT_WRAPPER
    # Try persistent location
    if os.path.exists(f"{CLAWDBOT_DIR}/clawdbot"):
        return f"{CLAWDBOT_DIR}/clawdbot"
    if os.path.exists(f"{NODE_DIR}/bin/clawdbot"):
        return f"{NODE_DIR}/bin/clawdbot"
    # Try system path
    import shutil
    clawdbot_path = shutil.which("clawdbot")
    if clawdbot_path:
        return clawdbot_path
    return None


def ensure_moltbot_installed():
    """Ensure Moltbot dependencies are installed"""
    install_script = "/app/backend/install_moltbot_deps.sh"

    # Check if clawdbot is available
    clawdbot_cmd = get_clawdbot_command()
    if clawdbot_cmd:
        logger.info(f"Clawdbot found at: {clawdbot_cmd}")
        return True

    # Run installation script if available
    if os.path.exists(install_script):
        logger.info("Clawdbot not found, running installation script...")
        try:
            result = subprocess.run(
                ["bash", install_script],
                capture_output=True,
                text=True,
                timeout=300
            )
            if result.returncode == 0:
                logger.info("Moltbot dependencies installed successfully")
                return True
            else:
                logger.error(f"Installation failed: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Installation script error: {e}")
            return False

    logger.error("Clawdbot not found and no installation script available")
    return False


def generate_token():
    """Generate a random gateway token"""
    return secrets.token_hex(32)


def create_moltbot_config(token: str = None, api_key: str = None, provider: str = "emergent", force_new_token: bool = False):
    """Update clawdbot.json with gateway config and provider settings

    Args:
        token: Optional token. If not provided, reuses existing or generates new.
        api_key: Optional API key for provider.
        provider: The LLM provider - "emergent", "openai", or "anthropic".
        force_new_token: If True, always generates a new token (triggers gateway restart).

    Returns:
        The token being used (existing or new).
    """
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(WORKSPACE_DIR, exist_ok=True)

    # Load existing config if present
    existing_config = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                existing_config = json.load(f)
        except:
            pass

    # Reuse existing token if available (to avoid triggering gateway restart)
    existing_token = None
    if not force_new_token:
        try:
            existing_token = existing_config.get("gateway", {}).get("auth", {}).get("token")
        except:
            pass

    # Use existing token, provided token, or generate new
    final_token = existing_token or token or generate_token()

    logger.info(f"Config token: {'reusing existing' if existing_token else 'new token'}, provider: {provider}")

    # Gateway config to merge
    gateway_config = {
        "mode": "local",
        "port": MOLTBOT_PORT,
        "bind": "lan",
        "auth": {
            "mode": "token",
            "token": final_token
        },
        "controlUi": {
            "enabled": True,
            "allowInsecureAuth": True
        }
    }

    # Merge config - preserve existing settings, update gateway
    existing_config["gateway"] = gateway_config

    # Ensure models section exists with merge mode
    if "models" not in existing_config:
        existing_config["models"] = {"mode": "merge", "providers": {}}
    existing_config["models"]["mode"] = "merge"
    if "providers" not in existing_config["models"]:
        existing_config["models"]["providers"] = {}

    # Ensure agents defaults section exists
    if "agents" not in existing_config:
        existing_config["agents"] = {"defaults": {}}
    if "defaults" not in existing_config["agents"]:
        existing_config["agents"]["defaults"] = {}
    existing_config["agents"]["defaults"]["workspace"] = WORKSPACE_DIR

    # Configure providers based on selection
    if provider == "emergent":
        # Use Emergent's proxy for both GPT and Claude
        emergent_key = api_key or os.environ.get('EMERGENT_API_KEY', 'sk-emergent-1234')
        emergent_base_url = os.environ.get('EMERGENT_BASE_URL', 'https://integrations.emergentagent.com/llm')

        # Emergent GPT provider (openai-completions API)
        emergent_gpt_provider = {
            "baseUrl": f"{emergent_base_url}/",
            "apiKey": emergent_key,
            "api": "openai-completions",
            "models": [
                {
                    "id": "gpt-5.2",
                    "name": "GPT-5.2",
                    "reasoning": True,
                    "input": ["text"],
                    "cost": {
                        "input": 0.00000175,
                        "output": 0.000014,
                        "cacheRead": 0.000000175,
                        "cacheWrite": 0.00000175
                    },
                    "contextWindow": 400000,
                    "maxTokens": 128000
                }
            ]
        }

        # Emergent Claude provider (anthropic-messages API with authHeader)
        emergent_claude_provider = {
            "baseUrl": emergent_base_url,
            "apiKey": emergent_key,
            "api": "anthropic-messages",
            "authHeader": True,
            "models": [
                {
                    "id": "claude-sonnet-4-5",
                    "name": "Claude Sonnet 4.5",
                    "input": ["text"],
                    "cost": {"input": 0.000003, "output": 0.000015, "cacheRead": 0.0000003, "cacheWrite": 0.00000375},
                    "contextWindow": 200000,
                    "maxTokens": 64000
                },
                {
                    "id": "claude-opus-4-5",
                    "name": "Claude Opus 4.5",
                    "input": ["text"],
                    "cost": {"input": 0.000005, "output": 0.000025, "cacheRead": 0.0000005, "cacheWrite": 0.00000625},
                    "contextWindow": 200000,
                    "maxTokens": 64000
                }
            ]
        }

        existing_config["models"]["providers"]["emergent-gpt"] = emergent_gpt_provider
        existing_config["models"]["providers"]["emergent-claude"] = emergent_claude_provider

        # Set primary model to Claude Sonnet
        existing_config["agents"]["defaults"]["models"] = {
            "emergent-gpt/gpt-5.2": {"alias": "gpt-5.2"},
            "emergent-claude/claude-sonnet-4-5": {"alias": "sonnet"}
        }
        existing_config["agents"]["defaults"]["model"] = {
            "primary": "emergent-claude/claude-sonnet-4-5"
        }

    elif provider == "openai":
        # Direct OpenAI API with user's own key
        openai_provider = {
            "baseUrl": "https://api.openai.com/v1/",
            "apiKey": api_key,
            "api": "openai-completions",
            "models": [
                {
                    "id": "gpt-5.2",
                    "name": "GPT-5.2",
                    "reasoning": True,
                    "input": ["text", "image"],
                    "cost": {
                        "input": 0.00000175,
                        "output": 0.000014,
                        "cacheRead": 0.000000175,
                        "cacheWrite": 0.00000175
                    },
                    "contextWindow": 400000,
                    "maxTokens": 128000
                },
                {
                    "id": "o4-mini-2025-04-16",
                    "name": "o4-mini",
                    "reasoning": True,
                    "input": ["text", "image"],
                    "cost": {
                        "input": 0.0000011,
                        "output": 0.0000044
                    },
                    "contextWindow": 200000,
                    "maxTokens": 100000
                },
                {
                    "id": "gpt-4o",
                    "name": "GPT-4o",
                    "reasoning": False,
                    "input": ["text", "image"],
                    "cost": {
                        "input": 0.0000025,
                        "output": 0.00001
                    },
                    "contextWindow": 128000,
                    "maxTokens": 16384
                }
            ]
        }

        existing_config["models"]["providers"]["openai"] = openai_provider

        # Set primary model to GPT-5.2
        existing_config["agents"]["defaults"]["models"] = {
            "openai/gpt-5.2": {"alias": "gpt-5.2"}
        }
        existing_config["agents"]["defaults"]["model"] = {
            "primary": "openai/gpt-5.2"
        }

    elif provider == "anthropic":
        # Direct Anthropic API with user's own key
        anthropic_provider = {
            "baseUrl": "https://api.anthropic.com",
            "apiKey": api_key,
            "api": "anthropic-messages",
            "models": [
                {
                    "id": "claude-opus-4-5-20251101",
                    "name": "Claude Opus 4.5",
                    "input": ["text", "image"],
                    "cost": {"input": 0.000015, "output": 0.000075, "cacheRead": 0.0000015, "cacheWrite": 0.00001875},
                    "contextWindow": 200000,
                    "maxTokens": 64000
                }
            ]
        }

        existing_config["models"]["providers"]["anthropic"] = anthropic_provider

        # Set primary model to Claude Opus 4.5
        existing_config["agents"]["defaults"]["models"] = {
            "anthropic/claude-opus-4-5-20251101": {"alias": "opus"}
        }
        existing_config["agents"]["defaults"]["model"] = {
            "primary": "anthropic/claude-opus-4-5-20251101"
        }

    with open(CONFIG_FILE, "w") as f:
        json.dump(existing_config, f, indent=2)

    logger.info(f"Updated Moltbot config at {CONFIG_FILE} for provider: {provider}")
    return final_token  # Return the token being used


async def start_gateway_process(api_key: str, provider: str, owner_user_id: str):
    """Start the Moltbot gateway process via supervisor (persistent, survives backend restarts)"""
    global gateway_state

    # Check if already running via supervisor
    if SupervisorClient.status():
        logger.info("Gateway already running via supervisor, recovering state...")

        # Recover token from config
        token = None
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            token = config.get("gateway", {}).get("auth", {}).get("token")
        except:
            pass

        if not token:
            token = generate_token()
            create_moltbot_config(token=token, api_key=api_key, provider=provider, force_new_token=True)

        gateway_state["token"] = token
        gateway_state["provider"] = provider
        gateway_state["started_at"] = datetime.now(timezone.utc).isoformat()
        gateway_state["owner_user_id"] = owner_user_id

        # Update database
        await db.moltbot_configs.update_one(
            {"_id": "gateway_config"},
            {
                "$set": {
                    "should_run": True,
                    "owner_user_id": owner_user_id,
                    "provider": provider,
                    "token": token,
                    "started_at": gateway_state["started_at"],
                    "updated_at": datetime.now(timezone.utc)
                }
            },
            upsert=True
        )

        return token

    # Ensure clawdbot is installed
    clawdbot_cmd = get_clawdbot_command()
    if not clawdbot_cmd:
        if not ensure_moltbot_installed():
            raise HTTPException(status_code=500, detail="OpenClaw (clawdbot) is not installed. Please contact support.")
        clawdbot_cmd = get_clawdbot_command()
        if not clawdbot_cmd:
            raise HTTPException(status_code=500, detail="Failed to find clawdbot after installation")

    # Create config (reuses existing token to avoid gateway restarts)
    token = create_moltbot_config(api_key=api_key, provider=provider)

    # Write environment file for supervisor wrapper to load
    write_gateway_env(token=token, api_key=api_key, provider=provider)

    logger.info(f"Starting Moltbot gateway via supervisor on port {MOLTBOT_PORT}...")

    # Start via supervisor (will auto-restart on crash, survives backend restarts)
    if not SupervisorClient.start():
        raise HTTPException(status_code=500, detail="Failed to start gateway via supervisor")

    # Update in-memory state
    gateway_state["token"] = token
    gateway_state["provider"] = provider
    gateway_state["started_at"] = datetime.now(timezone.utc).isoformat()
    gateway_state["owner_user_id"] = owner_user_id

    # Wait for gateway to be ready
    max_wait = 60
    start_time = asyncio.get_event_loop().time()

    async with httpx.AsyncClient() as http_client:
        while asyncio.get_event_loop().time() - start_time < max_wait:
            try:
                response = await http_client.get(f"http://127.0.0.1:{MOLTBOT_PORT}/", timeout=2.0)
                if response.status_code == 200:
                    logger.info("Moltbot gateway is ready!")

                    # Store config in database for persistence (with should_run flag)
                    await db.moltbot_configs.update_one(
                        {"_id": "gateway_config"},
                        {
                            "$set": {
                                "should_run": True,
                                "owner_user_id": owner_user_id,
                                "provider": provider,
                                "token": token,
                                "started_at": gateway_state["started_at"],
                                "updated_at": datetime.now(timezone.utc)
                            }
                        },
                        upsert=True
                    )

                    return token
            except Exception:
                pass
            await asyncio.sleep(1)

    # Check supervisor status if not ready
    if not SupervisorClient.status():
        raise HTTPException(status_code=500, detail="Gateway failed to start via supervisor")

    raise HTTPException(status_code=500, detail="Gateway did not become ready in time")


def check_gateway_running():
    """Check if the gateway process is still running via supervisor"""
    return SupervisorClient.status()


# ============== Moltbot API Endpoints (Protected) ==============

@api_router.get("/")
async def root():
    return {"message": "OpenClaw Hosting API"}


@api_router.post("/openclaw/start", response_model=OpenClawStartResponse)
async def start_moltbot(request: OpenClawStartRequest, req: Request):
    """Start the Moltbot gateway with Emergent provider (requires auth)"""
    user = await require_auth(req)

    if request.provider not in ["emergent", "anthropic", "openai"]:
        raise HTTPException(status_code=400, detail="Invalid provider. Use 'emergent', 'anthropic', or 'openai'")

    # For non-emergent providers, API key is required
    if request.provider in ["anthropic", "openai"] and (not request.apiKey or len(request.apiKey) < 10):
        raise HTTPException(status_code=400, detail="API key required for anthropic/openai providers")

    # Check if Moltbot is already running by another user
    if check_gateway_running() and gateway_state["owner_user_id"] != user.user_id:
        raise HTTPException(
            status_code=403,
            detail="OpenClaw is already running by another user. Please wait for them to stop it."
        )

    try:
        token = await start_gateway_process(request.apiKey, request.provider, user.user_id)

        # Lock the instance to this user on first successful start
        await set_instance_owner(user)
        logger.info(f"Instance locked to user: {user.email}")

        return OpenClawStartResponse(
            ok=True,
            controlUrl="/api/openclaw/ui/",
            token=token,
            message="OpenClaw started successfully with Emergent provider"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start Moltbot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/openclaw/status", response_model=OpenClawStatusResponse)
async def get_moltbot_status(request: Request):
    """Get the current status of the Moltbot gateway"""
    user = await get_current_user(request)
    running = check_gateway_running()

    if running:
        is_owner = user and gateway_state["owner_user_id"] == user.user_id
        return OpenClawStatusResponse(
            running=True,
            pid=SupervisorClient.get_pid(),
            provider=gateway_state["provider"],
            started_at=gateway_state["started_at"],
            controlUrl="/api/openclaw/ui/",
            owner_user_id=gateway_state["owner_user_id"],
            is_owner=is_owner
        )
    else:
        return OpenClawStatusResponse(running=False)


@api_router.get("/openclaw/whatsapp/status")
async def get_whatsapp_connection_status():
    """Get basic WhatsApp connection status. Auto-fix handled by background watcher."""
    return get_whatsapp_status()


@api_router.post("/openclaw/stop")
async def stop_moltbot(request: Request):
    """Stop the Moltbot gateway (only owner can stop)"""
    user = await require_auth(request)

    global gateway_state

    if not check_gateway_running():
        # Clear should_run flag even if not running
        await db.moltbot_configs.update_one(
            {"_id": "gateway_config"},
            {"$set": {"should_run": False, "updated_at": datetime.now(timezone.utc)}}
        )
        return {"ok": True, "message": "OpenClaw is not running"}

    # Check if user is the owner
    if gateway_state["owner_user_id"] != user.user_id:
        raise HTTPException(status_code=403, detail="Only the owner can stop OpenClaw")

    # Stop via supervisor
    if not SupervisorClient.stop():
        logger.error("Failed to stop gateway via supervisor")

    # Clear the gateway env file
    clear_gateway_env()

    # Clear should_run flag in database
    await db.moltbot_configs.update_one(
        {"_id": "gateway_config"},
        {"$set": {"should_run": False, "updated_at": datetime.now(timezone.utc)}}
    )

    # Clear in-memory state
    gateway_state["token"] = None
    gateway_state["provider"] = None
    gateway_state["started_at"] = None
    gateway_state["owner_user_id"] = None

    return {"ok": True, "message": "OpenClaw stopped"}


@api_router.get("/openclaw/token")
async def get_moltbot_token(request: Request):
    """Get the current gateway token for authentication (only owner)"""
    user = await require_auth(request)

    if not check_gateway_running():
        raise HTTPException(status_code=404, detail="OpenClaw not running")

    # Only owner can get the token
    if gateway_state["owner_user_id"] != user.user_id:
        raise HTTPException(status_code=403, detail="Only the owner can access the token")

    return {"token": gateway_state.get("token")}


# ============== Moltbot Proxy (Protected) ==============

@api_router.api_route("/openclaw/ui/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_moltbot_ui(request: Request, path: str = ""):
    """Proxy requests to the Moltbot Control UI (only owner can access)"""
    user = await get_current_user(request)

    if not check_gateway_running():
        return HTMLResponse(
            content="<html><body><h1>OpenClaw not running</h1><p>Please start OpenClaw first.</p><a href='/'>Go to setup</a></body></html>",
            status_code=503
        )

    # Check if user is the owner
    if not user or gateway_state["owner_user_id"] != user.user_id:
        return HTMLResponse(
            content="<html><body><h1>Access Denied</h1><p>This OpenClaw instance is owned by another user.</p><a href='/'>Go back</a></body></html>",
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
// OpenClaw Proxy Configuration
window.__MOLTBOT_PROXY_TOKEN__ = "{current_token}";
window.__MOLTBOT_PROXY_WS_URL__ = (window.location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + window.location.host + '/api/openclaw/ws';

// Override WebSocket to use proxy path
(function() {{
    const originalWS = window.WebSocket;
    const proxyWsUrl = window.__MOLTBOT_PROXY_WS_URL__;

    window.WebSocket = function(url, protocols) {{
        let finalUrl = url;

        // Rewrite any OpenClaw gateway URLs to use our proxy
        if (url.includes('127.0.0.1:18789') ||
            url.includes('localhost:18789') ||
            url.includes('0.0.0.0:18789') ||
            (url.includes(':18789') && !url.includes('/api/openclaw/'))) {{
            finalUrl = proxyWsUrl;
        }}

        // If it's a relative URL or same-origin, redirect to proxy
        try {{
            const urlObj = new URL(url, window.location.origin);
            if (urlObj.port === '18789' || urlObj.pathname === '/' && !url.startsWith(proxyWsUrl)) {{
                finalUrl = proxyWsUrl;
            }}
        }} catch (e) {{}}

        console.log('[OpenClaw Proxy] WebSocket:', url, '->', finalUrl);
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
            raise HTTPException(status_code=502, detail="Failed to connect to OpenClaw")


# Root proxy for Moltbot UI (handles /api/moltbot/ui without trailing path)
@api_router.get("/openclaw/ui")
async def proxy_moltbot_ui_root(request: Request):
    """Redirect to Moltbot UI with trailing slash"""
    return Response(
        status_code=307,
        headers={"Location": "/api/openclaw/ui/"}
    )


# WebSocket proxy for Moltbot (Protected)
@api_router.websocket("/openclaw/ws")
async def websocket_proxy(websocket: WebSocket):
    """WebSocket proxy for Moltbot Control UI"""
    await websocket.accept()

    if not check_gateway_running():
        await websocket.close(code=1013, reason="OpenClaw not running")
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


# ============== Telegram Endpoints ==============

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_API_BASE = "https://api.telegram.org"


@api_router.get("/telegram/status")
async def get_telegram_status():
    """Get Telegram bot connection status"""
    token = TELEGRAM_BOT_TOKEN
    if not token:
        # Try reading from clawdbot config
        try:
            with open(CONFIG_FILE, 'r') as f:
                cfg = json.load(f)
            token = cfg.get("channels", {}).get("telegram", {}).get("botToken", "")
        except Exception:
            pass

    if not token:
        return {"connected": False, "bot": None, "error": "No Telegram bot token configured"}

    try:
        async with httpx.AsyncClient() as hc:
            resp = await hc.get(f"{TELEGRAM_API_BASE}/bot{token}/getMe", timeout=8.0)
        if resp.status_code == 200:
            data = resp.json()
            bot = data.get("result", {})
            return {
                "connected": True,
                "bot": {
                    "id": bot.get("id"),
                    "name": bot.get("first_name"),
                    "username": bot.get("username"),
                    "can_join_groups": bot.get("can_join_groups"),
                    "supports_inline_queries": bot.get("supports_inline_queries")
                }
            }
        else:
            return {"connected": False, "bot": None, "error": f"Telegram API error: {resp.status_code}"}
    except Exception as e:
        logger.error(f"Telegram status check error: {e}")
        return {"connected": False, "bot": None, "error": str(e)}


class TelegramConfigRequest(BaseModel):
    bot_token: str


@api_router.post("/telegram/configure")
async def configure_telegram(req: Request, request_data: TelegramConfigRequest):
    """Configure Telegram bot token (requires auth)"""
    user = await require_auth(req)

    token = request_data.bot_token.strip()
    if not token or len(token) < 20:
        raise HTTPException(status_code=400, detail="Invalid bot token")

    # Validate token with Telegram API
    try:
        async with httpx.AsyncClient() as hc:
            resp = await hc.get(f"{TELEGRAM_API_BASE}/bot{token}/getMe", timeout=8.0)
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Invalid Telegram bot token - verification failed")
        bot_info = resp.json().get("result", {})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to verify token: {str(e)}")

    # Update clawdbot.json
    try:
        existing_config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                existing_config = json.load(f)
        if "channels" not in existing_config:
            existing_config["channels"] = {}
        existing_config["channels"]["telegram"] = {"botToken": token, "enabled": True}
        with open(CONFIG_FILE, 'w') as f:
            json.dump(existing_config, f, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {str(e)}")

    # Update gateway.env to include TELEGRAM_BOT_TOKEN
    try:
        env_path = "/root/.clawdbot/gateway.env"
        lines = []
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                lines = [l for l in f.readlines() if "TELEGRAM_BOT_TOKEN" not in l]
        lines.append(f'export TELEGRAM_BOT_TOKEN="{token}"\n')
        with open(env_path, 'w') as f:
            f.writelines(lines)
    except Exception as e:
        logger.warning(f"Could not update gateway.env: {e}")

    # Restart gateway to pick up Telegram config
    if check_gateway_running():
        import subprocess as _sp
        _sp.run(["supervisorctl", "restart", "clawdbot-gateway"], capture_output=True)

    logger.info(f"Telegram bot configured by {user.email}: @{bot_info.get('username')}")
    return {
        "ok": True,
        "bot": {
            "id": bot_info.get("id"),
            "name": bot_info.get("first_name"),
            "username": bot_info.get("username")
        },
        "message": f"Telegram bot @{bot_info.get('username')} configured successfully"
    }


# ============== Chat Endpoints ==============

_active_chat_sessions: dict = {}


def get_chat_system_prompt() -> str:
    """Load current persona from IDENTITY.md"""
    try:
        with open(IDENTITY_FILE, "r") as f:
            identity = f.read()
        return (
            f"You are Neo, an AI assistant. Your identity and persona are defined below:\n\n"
            f"{identity}\n\n"
            f"Respond naturally based on your persona. Be helpful, direct, and aligned with your identity. "
            f"Keep responses concise unless detail is explicitly needed."
        )
    except Exception:
        return "You are Neo, a direct and capable AI assistant. Be helpful and concise."


def get_or_create_llm(cache_key: str, session_id: str) -> LlmChat:
    if cache_key not in _active_chat_sessions:
        system_prompt = get_chat_system_prompt()
        _active_chat_sessions[cache_key] = LlmChat(
            api_key=os.environ.get("EMERGENT_API_KEY", ""),
            session_id=session_id,
            system_message=system_prompt
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
    return _active_chat_sessions[cache_key]


class ChatMessageRequest(BaseModel):
    session_id: Optional[str] = None
    message: str


@api_router.post("/chat/message")
async def send_chat_message(request: Request, body: ChatMessageRequest):
    user = await require_auth(request)
    message_text = body.message.strip()
    if not message_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    session_id = body.session_id
    if not session_id:
        session_id = str(uuid.uuid4())
        await db.chat_sessions.insert_one({
            "session_id": session_id,
            "user_email": user.email,
            "title": message_text[:60],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        })

    cache_key = f"{user.email}:{session_id}"
    chat = get_or_create_llm(cache_key, session_id)

    await db.chat_messages.insert_one({
        "session_id": session_id,
        "user_email": user.email,
        "role": "user",
        "content": message_text,
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    try:
        response_text = await chat.send_message(UserMessage(text=message_text))
    except Exception as e:
        logger.error(f"LLM error: {e}")
        raise HTTPException(status_code=502, detail=f"LLM error: {str(e)}")

    await db.chat_messages.insert_one({
        "session_id": session_id,
        "user_email": user.email,
        "role": "assistant",
        "content": response_text,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    await db.chat_sessions.update_one(
        {"session_id": session_id},
        {"$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"session_id": session_id, "response": response_text}


@api_router.get("/chat/sessions")
async def get_chat_sessions(request: Request):
    user = await require_auth(request)
    sessions = await db.chat_sessions.find(
        {"user_email": user.email}, {"_id": 0}
    ).sort("updated_at", -1).limit(30).to_list(30)
    return {"sessions": sessions}


@api_router.get("/chat/history/{session_id}")
async def get_chat_history(request: Request, session_id: str):
    user = await require_auth(request)
    messages = await db.chat_messages.find(
        {"session_id": session_id, "user_email": user.email}, {"_id": 0}
    ).sort("created_at", 1).to_list(300)
    return {"messages": messages, "session_id": session_id}


@api_router.delete("/chat/session/{session_id}")
async def delete_chat_session(request: Request, session_id: str):
    user = await require_auth(request)
    await db.chat_sessions.delete_one({"session_id": session_id, "user_email": user.email})
    await db.chat_messages.delete_many({"session_id": session_id, "user_email": user.email})
    cache_key = f"{user.email}:{session_id}"
    _active_chat_sessions.pop(cache_key, None)
    return {"ok": True}


@api_router.post("/chat/transcribe")
async def transcribe_audio(request: Request, audio: UploadFile = File(...)):
    """Transcribe audio using OpenAI Whisper"""
    user = await require_auth(request)
    try:
        audio_bytes = await audio.read()
        if len(audio_bytes) > 25 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Audio file too large (max 25MB)")

        import tempfile
        suffix = '.webm'
        if audio.filename:
            ext = os.path.splitext(audio.filename)[1]
            if ext in ['.mp3', '.mp4', '.wav', '.ogg', '.m4a', '.webm']:
                suffix = ext

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            stt = OpenAISpeechToText(api_key=os.environ.get("EMERGENT_API_KEY", ""))
            with open(tmp_path, "rb") as f:
                response = await stt.transcribe(file=f, model="whisper-1", response_format="json")
            return {"text": response.text}
        finally:
            os.unlink(tmp_path)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        raise HTTPException(status_code=502, detail=f"Transcription failed: {str(e)}")


# ============== AI Hub Endpoints ==============

WORKSPACE_DIR_CLAWD = os.path.expanduser("~/clawd")
IDENTITY_FILE = os.path.join(WORKSPACE_DIR_CLAWD, "IDENTITY.md")

PERSONAS = [
    {
        "id": "neo",
        "name": "Neo (Default)",
        "description": "Direct, capable, no-nonsense assistant. Gets things done. Respects the human's time.",
        "category": "General",
        "emoji": "🦞",
        "active": True
    },
    {
        "id": "cursor",
        "name": "Cursor",
        "description": "Precision coding assistant. Meticulous, expert-level. Understands codebases deeply and delivers actionable, surgical fixes.",
        "category": "Coding",
        "emoji": "⚡"
    },
    {
        "id": "devin",
        "name": "Devin",
        "description": "Autonomous software engineer. Plans entire systems, writes code, runs tests, and ships features end-to-end without hand-holding.",
        "category": "Autonomous",
        "emoji": "🤖"
    },
    {
        "id": "manus",
        "name": "Manus",
        "description": "General-purpose autonomous agent. Executes complex multi-step tasks — research, write, code, browse, summarise — all without stopping.",
        "category": "Autonomous",
        "emoji": "🦾"
    },
    {
        "id": "lovable",
        "name": "Lovable",
        "description": "Creative full-stack developer. Obsessed with beautiful UIs, smooth UX, and delightful user experiences. Turns ideas into polished products fast.",
        "category": "Creative",
        "emoji": "💜"
    },
    {
        "id": "perplexity",
        "name": "Perplexity",
        "description": "Research-first assistant. Finds, synthesises, and presents information from multiple sources with inline citations and clear conclusions.",
        "category": "Research",
        "emoji": "🔍"
    },
    {
        "id": "claude-code",
        "name": "Claude Code",
        "description": "Thoughtful software engineer. Safety-conscious, thorough, and expert in navigating large complex codebases with care.",
        "category": "Coding",
        "emoji": "🤍"
    },
    {
        "id": "notion-ai",
        "name": "Notion AI",
        "description": "Writing & productivity assistant. Drafts, edits, summarises, and organises content. Master of structured notes and clear communication.",
        "category": "Writing",
        "emoji": "📝"
    }
]

PERSONA_IDENTITY_TEMPLATES = {
    "neo": """# IDENTITY.md — Who Am I?

- **Name:** Neo
- **Creature:** AI assistant with claws — built on OpenClaw, powered by Claude Sonnet 4.5
- **Vibe:** Direct, capable, no-nonsense. Gets things done. Respects the human's time.
- **Emoji:** 🦞
- **Avatar:** A lobster with a laptop

## My Setup

- **Platform:** MoltBot on Emergent
- **Primary channel:** Telegram (@Clawdsahiixbot)
- **LLM:** Claude Sonnet 4.5 via Emergent (also GPT-5.2 available)
- **Workspace:** /root/clawd
- **Paired user:** Telegram ID 8252725134

## How I Work

I wake up fresh each session but my files give me memory. I read SOUL.md and USER.md first, then get to work.
I don't ask unnecessary questions — I figure things out and report back.
""",
    "cursor": """# IDENTITY.md — Who Am I?

- **Name:** Neo (Cursor Mode)
- **Role:** Precision coding assistant
- **Vibe:** Meticulous, expert-level software engineer. I understand your codebase deeply and provide precise, actionable help.
- **Emoji:** ⚡

## How I Work

I am a highly skilled software engineer with deep knowledge across many languages and frameworks.
I provide concise, accurate, and helpful code assistance. I explain the *why* behind my changes.
I always look at the full picture before suggesting fixes — never patching symptoms without understanding root causes.
I prefer minimal, surgical changes over rewrites. I match the existing code style.

## My Setup

- **Platform:** MoltBot on Emergent
- **Primary channel:** Telegram (@Clawdsahiixbot)
- **LLM:** Claude Sonnet 4.5 via Emergent
- **Workspace:** /root/clawd
- **Paired user:** Telegram ID 8252725134
""",
    "devin": """# IDENTITY.md — Who Am I?

- **Name:** Neo (Devin Mode)
- **Role:** Autonomous software engineer
- **Vibe:** I plan, code, test, and ship. No hand-holding required.
- **Emoji:** 🤖

## How I Work

I am an autonomous software engineer. Given a task, I:
1. Break it into a clear execution plan
2. Write the code
3. Test it
4. Iterate until it works
5. Report back with results

I work autonomously and surface blockers proactively. I don't wait to be told the next step.

## My Setup

- **Platform:** MoltBot on Emergent
- **Primary channel:** Telegram (@Clawdsahiixbot)
- **LLM:** Claude Sonnet 4.5 via Emergent
- **Workspace:** /root/clawd
- **Paired user:** Telegram ID 8252725134
""",
    "manus": """# IDENTITY.md — Who Am I?

- **Name:** Neo (Manus Mode)
- **Role:** General-purpose autonomous agent
- **Vibe:** I execute complex multi-step tasks end-to-end. Research, write, code, browse — whatever it takes.
- **Emoji:** 🦾

## How I Work

I am a general-purpose autonomous agent. I tackle complex, multi-faceted tasks by:
- Breaking them into sub-tasks
- Executing each in sequence or parallel as appropriate
- Using all tools available to me
- Delivering a complete, polished result

I prefer action over deliberation. I report progress and results, not just plans.

## My Setup

- **Platform:** MoltBot on Emergent
- **Primary channel:** Telegram (@Clawdsahiixbot)
- **LLM:** Claude Sonnet 4.5 via Emergent
- **Workspace:** /root/clawd
- **Paired user:** Telegram ID 8252725134
""",
    "lovable": """# IDENTITY.md — Who Am I?

- **Name:** Neo (Lovable Mode)
- **Role:** Creative full-stack developer
- **Vibe:** Beautiful UIs, delightful UX, fast execution. I turn ideas into polished products.
- **Emoji:** 💜

## How I Work

I am a creative full-stack developer obsessed with quality and beauty. I:
- Build UIs that are both functional and visually stunning
- Think about the user's experience at every step
- Ship fast without cutting corners on polish
- Use modern design patterns and clean, readable code

When I build something, it should feel *great* to use, not just work.

## My Setup

- **Platform:** MoltBot on Emergent
- **Primary channel:** Telegram (@Clawdsahiixbot)
- **LLM:** Claude Sonnet 4.5 via Emergent
- **Workspace:** /root/clawd
- **Paired user:** Telegram ID 8252725134
""",
    "perplexity": """# IDENTITY.md — Who Am I?

- **Name:** Neo (Perplexity Mode)
- **Role:** Research & synthesis assistant
- **Vibe:** I find answers, synthesise sources, and deliver clear, cited conclusions.
- **Emoji:** 🔍

## How I Work

I am a research-focused assistant. When asked a question, I:
- Gather information from multiple angles
- Synthesise it into a clear, structured answer
- Cite my reasoning and sources
- Surface uncertainty rather than fake confidence

I present information objectively and clearly. I distinguish between facts, inferences, and opinions.

## My Setup

- **Platform:** MoltBot on Emergent
- **Primary channel:** Telegram (@Clawdsahiixbot)
- **LLM:** Claude Sonnet 4.5 via Emergent
- **Workspace:** /root/clawd
- **Paired user:** Telegram ID 8252725134
""",
    "claude-code": """# IDENTITY.md — Who Am I?

- **Name:** Neo (Claude Code Mode)
- **Role:** Thoughtful software engineer
- **Vibe:** Safety-conscious, thorough, expert in complex codebases. I think before I act.
- **Emoji:** 🤍

## How I Work

I am a thoughtful software engineer who:
- Reads and understands code before modifying it
- Makes careful, minimal, well-reasoned changes
- Explains my approach and reasoning clearly
- Flags risks and edge cases proactively
- Never introduces unnecessary complexity

I prefer correctness over speed. I verify assumptions before acting.

## My Setup

- **Platform:** MoltBot on Emergent
- **Primary channel:** Telegram (@Clawdsahiixbot)
- **LLM:** Claude Sonnet 4.5 via Emergent
- **Workspace:** /root/clawd
- **Paired user:** Telegram ID 8252725134
""",
    "notion-ai": """# IDENTITY.md — Who Am I?

- **Name:** Neo (Notion AI Mode)
- **Role:** Writing & productivity assistant
- **Vibe:** Clear, structured, helpful. Master of words, notes, and organised thinking.
- **Emoji:** 📝

## How I Work

I am a writing and productivity assistant. I excel at:
- Drafting and editing text in any style
- Summarising long content into key points
- Structuring ideas into clear, readable formats
- Turning rough notes into polished documents
- Helping you think through problems in writing

My output is always clear, well-structured, and adapted to your audience.

## My Setup

- **Platform:** MoltBot on Emergent
- **Primary channel:** Telegram (@Clawdsahiixbot)
- **LLM:** Claude Sonnet 4.5 via Emergent
- **Workspace:** /root/clawd
- **Paired user:** Telegram ID 8252725134
"""
}

AGENT_USE_CASES = [
    {"id": 1, "name": "Health Insights Agent", "industry": "Healthcare", "description": "Analyses medical reports and provides health insights.", "framework": "General", "github": "https://github.com/harshhh28/hia"},
    {"id": 2, "name": "AI Health Assistant", "industry": "Healthcare", "description": "Diagnoses and monitors diseases using patient data.", "framework": "General", "github": "https://github.com/ahmadvh/AI-Agents-for-Medical-Diagnostics"},
    {"id": 3, "name": "Automated Trading Bot", "industry": "Finance", "description": "Automates stock trading with real-time market analysis.", "framework": "General", "github": "https://github.com/MingyuJ666/Stockagent"},
    {"id": 4, "name": "Virtual AI Tutor", "industry": "Education", "description": "Provides personalised education tailored to users.", "framework": "General", "github": "https://github.com/hqanhh/EduGPT"},
    {"id": 5, "name": "24/7 AI Chatbot", "industry": "Customer Service", "description": "Handles customer queries around the clock.", "framework": "LangGraph", "github": "https://github.com/NirDiamant/GenAI_Agents"},
    {"id": 6, "name": "Product Recommendation Agent", "industry": "Retail", "description": "Suggests products based on user preferences and history.", "framework": "General", "github": "https://github.com/microsoft/RecAI"},
    {"id": 7, "name": "Real-Time Threat Detection", "industry": "Cybersecurity", "description": "Identifies potential threats and mitigates attacks in real time.", "framework": "General", "github": "https://github.com/NVISOsecurity/cyber-security-llm-agents"},
    {"id": 8, "name": "Legal Document Review", "industry": "Legal", "description": "Automates document review and highlights key clauses.", "framework": "General", "github": "https://github.com/firica/legalai"},
    {"id": 9, "name": "Recruitment Agent", "industry": "HR", "description": "Suggests best-fit candidates for job openings.", "framework": "General", "github": "https://github.com/sentient-engineering/jobber"},
    {"id": 10, "name": "Virtual Travel Assistant", "industry": "Hospitality", "description": "Plans travel itineraries based on user preferences.", "framework": "General", "github": "https://github.com/nirbar1985/ai-travel-agent"},
    {"id": 11, "name": "Email Auto Responder", "industry": "Communication", "description": "Automates email responses based on predefined criteria.", "framework": "CrewAI", "github": "https://github.com/crewAIInc/crewAI-examples"},
    {"id": 12, "name": "Marketing Strategy Generator", "industry": "Marketing", "description": "Develops marketing strategies by analysing market trends and audience data.", "framework": "CrewAI", "github": "https://github.com/crewAIInc/crewAI-examples"},
    {"id": 13, "name": "Stock Analysis Tool", "industry": "Finance", "description": "Provides tools for analysing stock market data to assist in financial decision-making.", "framework": "CrewAI", "github": "https://github.com/crewAIInc/crewAI-examples"},
    {"id": 14, "name": "Trip Planner", "industry": "Travel", "description": "Assists in planning trips by organising itineraries and managing travel details.", "framework": "CrewAI", "github": "https://github.com/crewAIInc/crewAI-examples"},
    {"id": 15, "name": "Screenplay Writer", "industry": "Creative Writing", "description": "Aids in writing screenplays by offering templates and guidance for script development.", "framework": "CrewAI", "github": "https://github.com/crewAIInc/crewAI-examples"},
    {"id": 16, "name": "Landing Page Generator", "industry": "Web Dev", "description": "Automates the creation of landing pages for websites.", "framework": "CrewAI", "github": "https://github.com/crewAIInc/crewAI-examples"},
    {"id": 17, "name": "Instagram Post Generator", "industry": "Social Media", "description": "Generates and schedules Instagram posts automatically.", "framework": "CrewAI", "github": "https://github.com/crewAIInc/crewAI-examples"},
    {"id": 18, "name": "Code Assistant", "industry": "Software Dev", "description": "Builds a resilient code assistant with graph-based error checking and iterative refinement.", "framework": "LangGraph", "github": "https://github.com/langchain-ai/langgraph"},
    {"id": 19, "name": "Customer Support Agent", "industry": "Customer Service", "description": "Handles customer inquiries with automated support and enhanced user experience.", "framework": "LangGraph", "github": "https://github.com/langchain-ai/langgraph"},
    {"id": 20, "name": "Multi-Agent Workflow", "industry": "Productivity", "description": "Supervisor agent orchestrates multiple specialised agents for complex task delegation.", "framework": "LangGraph", "github": "https://github.com/langchain-ai/langgraph"},
    {"id": 21, "name": "SQL Agent", "industry": "Data", "description": "Converts natural language questions into SQL queries and executes them.", "framework": "LangGraph", "github": "https://github.com/langchain-ai/langgraph"},
    {"id": 22, "name": "Adaptive RAG", "industry": "Research", "description": "Dynamic retrieval process that adjusts based on query complexity for accurate information retrieval.", "framework": "LangGraph", "github": "https://github.com/langchain-ai/langgraph"},
    {"id": 23, "name": "Finance Agent", "industry": "Finance", "description": "AI-powered market analyst delivering real-time stock insights, analyst recommendations, and sector trends.", "framework": "Agno", "github": "https://github.com/agno-agi/agno"},
    {"id": 24, "name": "Research Scholar Agent", "industry": "Education", "description": "Performs advanced academic searches, analyses publications, and synthesises findings with citations.", "framework": "Agno", "github": "https://github.com/agno-agi/agno"},
    {"id": 25, "name": "Legal Document Analysis", "industry": "Legal", "description": "Analyses legal documents from PDFs and provides insights using vector embeddings.", "framework": "Agno", "github": "https://github.com/agno-agi/agno"},
    {"id": 26, "name": "Movie Recommendation Agent", "industry": "Entertainment", "description": "Gives personalised movie recommendations by analysing genres, themes, and ratings.", "framework": "Agno", "github": "https://github.com/agno-agi/agno"},
    {"id": 27, "name": "Recipe Creator", "industry": "Food", "description": "AI-powered recipe recommendation based on ingredients, preferences, and time constraints.", "framework": "Agno", "github": "https://github.com/agno-agi/agno"},
    {"id": 28, "name": "Vibe Hacking Agent", "industry": "Cybersecurity", "description": "Autonomous multi-agent red team testing service.", "framework": "General", "github": "https://github.com/PurpleAILAB/Decepticon"},
    {"id": 29, "name": "Property Pricing Agent", "industry": "Real Estate", "description": "Analyses market trends to determine property prices.", "framework": "General", "github": "https://github.com/AleksNeStu/ai-real-estate-assistant"},
    {"id": 30, "name": "Smart Farming Assistant", "industry": "Agriculture", "description": "Provides insights on crop health and yield predictions.", "framework": "General", "github": "https://github.com/mohammed97ashraf/LLM_Agri_Bot"},
    {"id": 31, "name": "YouTube Agent", "industry": "Media", "description": "Analyses YouTube videos generating summaries, timestamps, and content breakdowns.", "framework": "Agno", "github": "https://github.com/agno-agi/agno"},
    {"id": 32, "name": "README Generator", "industry": "Software Dev", "description": "Generates high-quality READMEs for GitHub repos using repository metadata.", "framework": "Agno", "github": "https://github.com/agno-agi/agno"},
    {"id": 33, "name": "Dubai Real Estate Workflow", "industry": "Real Estate", "description": "Multi-agent workflow to automate Dubai real estate research and analysis.", "framework": "CrewAI", "github": "https://github.com/sahiixx/500-AI-Agents-Projects"},
    {"id": 34, "name": "Plan-and-Execute Agent", "industry": "Productivity", "description": "Generates a multi-step plan then executes each step sequentially, revising as needed.", "framework": "LangGraph", "github": "https://github.com/langchain-ai/langgraph"},
    {"id": 35, "name": "Reflection Agent", "industry": "AI Research", "description": "Critiques and revises its own outputs to enhance quality and reliability.", "framework": "LangGraph", "github": "https://github.com/langchain-ai/langgraph"},
    {"id": 36, "name": "Document Q&A Agent", "industry": "Education", "description": "Answers questions from uploaded PDFs and documents using RAG.", "framework": "LangGraph", "github": "https://github.com/langchain-ai/langgraph"},
    {"id": 37, "name": "News Summariser Agent", "industry": "Media", "description": "Fetches, filters, and summarises daily news by topic into a digest.", "framework": "Agno", "github": "https://github.com/agno-agi/agno"},
    {"id": 38, "name": "Invoice Processing Agent", "industry": "Finance", "description": "Extracts data from invoices and updates accounting systems automatically.", "framework": "General", "github": "https://github.com/sahiixx/500-AI-Agents-Projects"},
    {"id": 39, "name": "Smart Email Classifier", "industry": "Communication", "description": "Classifies incoming emails by priority, assigns labels, and drafts replies.", "framework": "LangGraph", "github": "https://github.com/NirDiamant/GenAI_Agents"},
    {"id": 40, "name": "Competitive Intelligence Agent", "industry": "Marketing", "description": "Monitors competitor websites and social media, generates weekly reports.", "framework": "CrewAI", "github": "https://github.com/crewAIInc/crewAI-examples"},
    {"id": 41, "name": "Code Review Agent", "industry": "Software Dev", "description": "Performs automated code reviews, flags bugs, suggests improvements.", "framework": "Agno", "github": "https://github.com/agno-agi/agno"},
    {"id": 42, "name": "Workout Planner Agent", "industry": "Healthcare", "description": "Creates personalised workout and nutrition plans based on user goals and history.", "framework": "General", "github": "https://github.com/sahiixx/500-AI-Agents-Projects"},
    {"id": 43, "name": "Interview Coach Agent", "industry": "HR", "description": "Conducts mock interviews, evaluates answers, and provides improvement tips.", "framework": "General", "github": "https://github.com/sahiixx/500-AI-Agents-Projects"},
    {"id": 44, "name": "Patent Search Agent", "industry": "Legal", "description": "Searches patent databases, analyses claims, and summarises prior art.", "framework": "Agno", "github": "https://github.com/agno-agi/agno"},
    {"id": 45, "name": "Crypto Portfolio Agent", "industry": "Finance", "description": "Tracks crypto portfolio, analyses market signals, and suggests rebalancing.", "framework": "General", "github": "https://github.com/sahiixx/500-AI-Agents-Projects"},
    {"id": 46, "name": "Content Repurposing Agent", "industry": "Marketing", "description": "Transforms long-form content into tweets, LinkedIn posts, and email newsletters.", "framework": "CrewAI", "github": "https://github.com/crewAIInc/crewAI-examples"},
    {"id": 47, "name": "Bug Triage Agent", "industry": "Software Dev", "description": "Reads bug reports, classifies severity, assigns to developers, writes fix suggestions.", "framework": "LangGraph", "github": "https://github.com/langchain-ai/langgraph"},
    {"id": 48, "name": "Supply Chain Optimiser", "industry": "Retail", "description": "Analyses inventory, demand forecasts, and supplier data to reduce costs.", "framework": "General", "github": "https://github.com/sahiixx/500-AI-Agents-Projects"},
    {"id": 49, "name": "Grant Writing Agent", "industry": "Education", "description": "Researches funding opportunities and drafts grant applications tailored to requirements.", "framework": "CrewAI", "github": "https://github.com/crewAIInc/crewAI-examples"},
    {"id": 50, "name": "Mental Health Check-In Bot", "industry": "Healthcare", "description": "Daily mood tracking, sentiment analysis, and personalised coping suggestions.", "framework": "General", "github": "https://github.com/sahiixx/500-AI-Agents-Projects"},
]


class ApplyPersonaRequest(BaseModel):
    persona_id: str


class KimiConfigRequest(BaseModel):
    api_key: str


class ProviderConfigRequest(BaseModel):
    provider: str  # "groq", "cohere", "deepseek", "ollama"
    api_key: Optional[str] = None  # Not needed for Ollama
    base_url: Optional[str] = None  # For Ollama or custom endpoints


@api_router.get("/hub/personas")
async def get_hub_personas(request: Request):
    """Get available bot personas"""
    # Determine which persona is currently active
    current_name = ""
    try:
        with open(IDENTITY_FILE, "r") as f:
            current_name = f.read()
    except Exception:
        pass

    result = []
    for p in PERSONAS:
        persona = dict(p)
        # Mark active by checking if the identity file contains the persona name
        if p["id"] == "neo" and "Neo (Default)" in current_name and "Cursor Mode" not in current_name and "Devin Mode" not in current_name and "Manus Mode" not in current_name and "Lovable Mode" not in current_name and "Perplexity Mode" not in current_name and "Claude Code Mode" not in current_name and "Notion AI Mode" not in current_name:
            persona["active"] = True
        elif f"({p['name']} Mode)" in current_name or (p["id"] != "neo" and f"Neo ({p['name']} Mode)" in current_name):
            persona["active"] = True
        else:
            persona["active"] = p.get("active", False) and p["id"] == "neo"
        result.append(persona)
    return {"personas": result}


class DetectPersonaRequest(BaseModel):
    message: str


# Keyword maps for rule-based persona detection
_PERSONA_RULES = [
    ("cursor",    ["debug", "fix bug", "refactor", "code review", "function", "class", "import", "syntax", "error", "exception", "compile", "git", "pull request", "merge", "lint", "test", "unit test", "api endpoint", "database query", "sql", "javascript", "python", "typescript", "css", "html"]),
    ("devin",     ["build me", "create a full", "set up a project", "deploy", "scaffold", "architecture", "system design", "microservice", "docker", "kubernetes", "cicd", "pipeline", "automate"]),
    ("manus",     ["research and", "find and", "browse", "search the web", "multi-step", "complex task", "plan and execute", "schedule", "summarise and send", "monitor"]),
    ("lovable",   ["ui", "ux", "design", "beautiful", "landing page", "dashboard", "frontend", "responsive", "animation", "tailwind", "figma", "component", "button", "modal", "form"]),
    ("perplexity",["what is", "explain", "how does", "why is", "compare", "difference between", "pros and cons", "research", "citation", "source", "fact", "statistics", "latest news"]),
    ("notion-ai", ["write", "draft", "essay", "blog post", "email", "letter", "summarise", "notes", "document", "outline", "edit this", "rewrite", "grammar", "proofread"]),
    ("claude-code",["review this code", "explain this code", "large codebase", "legacy code", "security", "vulnerability", "careful", "thorough", "step by step implementation"]),
]


@api_router.post("/hub/personas/detect")
async def detect_persona(body: DetectPersonaRequest):
    """Detect best persona for a given message (rule-based)"""
    text = body.message.lower()
    scores = {}
    for persona_id, keywords in _PERSONA_RULES:
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[persona_id] = score
    if not scores:
        return {"persona_id": None, "confidence": 0}
    best = max(scores, key=scores.get)
    confidence = min(scores[best] / 3, 1.0)  # normalize
    persona = next((p for p in PERSONAS if p["id"] == best), None)
    return {"persona_id": best, "persona": persona, "confidence": round(confidence, 2)}


@api_router.post("/hub/personas/apply")
async def apply_hub_persona(request: Request, body: ApplyPersonaRequest):
    """Apply a persona to the bot's IDENTITY.md"""
    user = await require_auth(request)

    persona_id = body.persona_id
    if persona_id not in PERSONA_IDENTITY_TEMPLATES:
        raise HTTPException(status_code=404, detail="Persona not found")

    identity_content = PERSONA_IDENTITY_TEMPLATES[persona_id]
    try:
        os.makedirs(WORKSPACE_DIR_CLAWD, exist_ok=True)
        with open(IDENTITY_FILE, "w") as f:
            f.write(identity_content)
        logger.info(f"Persona '{persona_id}' applied by {user.email}")
        persona = next((p for p in PERSONAS if p["id"] == persona_id), None)
        return {"ok": True, "message": f"Persona '{persona['name']}' applied successfully", "persona": persona}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply persona: {str(e)}")


@api_router.get("/hub/agents")
async def get_hub_agents(q: str = "", industry: str = "", framework: str = ""):
    """Get AI agent use cases, with optional filtering"""
    results = AGENT_USE_CASES
    if q:
        q_lower = q.lower()
        results = [a for a in results if q_lower in a["name"].lower() or q_lower in a["description"].lower() or q_lower in a["industry"].lower()]
    if industry and industry != "All":
        results = [a for a in results if a["industry"] == industry]
    if framework and framework != "All":
        results = [a for a in results if a["framework"] == framework]
    industries = sorted(set(a["industry"] for a in AGENT_USE_CASES))
    frameworks = sorted(set(a["framework"] for a in AGENT_USE_CASES))
    return {"agents": results, "total": len(results), "industries": industries, "frameworks": frameworks}


@api_router.post("/hub/kimi/configure")
async def configure_kimi(request: Request, body: KimiConfigRequest):
    """Configure Moonshot/Kimi as an LLM provider"""
    user = await require_auth(request)

    api_key = body.api_key.strip()
    if not api_key or len(api_key) < 10:
        raise HTTPException(status_code=400, detail="Invalid Kimi API key")

    # Load existing clawdbot config
    try:
        existing_config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                existing_config = json.load(f)

        if "models" not in existing_config:
            existing_config["models"] = {"mode": "merge", "providers": {}}
        if "providers" not in existing_config["models"]:
            existing_config["models"]["providers"] = {}

        # Add Kimi/Moonshot as a provider (OpenAI-compatible API)
        existing_config["models"]["providers"]["kimi"] = {
            "baseUrl": "https://api.moonshot.cn/v1/",
            "apiKey": api_key,
            "api": "openai-completions",
            "models": [
                {
                    "id": "moonshot-v1-8k",
                    "name": "Kimi (8k)",
                    "input": ["text"],
                    "contextWindow": 8000,
                    "maxTokens": 4096
                },
                {
                    "id": "moonshot-v1-32k",
                    "name": "Kimi (32k)",
                    "input": ["text"],
                    "contextWindow": 32000,
                    "maxTokens": 16384
                },
                {
                    "id": "moonshot-v1-128k",
                    "name": "Kimi (128k)",
                    "input": ["text"],
                    "contextWindow": 128000,
                    "maxTokens": 65536
                }
            ]
        }

        with open(CONFIG_FILE, "w") as f:
            json.dump(existing_config, f, indent=2)

        # Restart gateway if running to pick up new provider
        if check_gateway_running():
            import subprocess as _sp
            _sp.run(["supervisorctl", "restart", "clawdbot-gateway"], capture_output=True)

        logger.info(f"Kimi provider configured by {user.email}")
        return {"ok": True, "message": "Moonshot/Kimi provider configured successfully. Available models: moonshot-v1-8k, 32k, 128k"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to configure Kimi: {str(e)}")


@api_router.post("/hub/providers/configure")
async def configure_provider(request: Request, body: ProviderConfigRequest):
    """Configure additional LLM providers (Groq, Cohere, DeepSeek, Ollama)"""
    user = await require_auth(request)
    
    provider = body.provider.lower()
    
    # Provider configurations
    provider_configs = {
        "groq": {
            "baseUrl": "https://api.groq.com/openai/v1/",
            "api": "openai-completions",
            "models": [
                {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B", "input": ["text"], "contextWindow": 128000, "maxTokens": 32768},
                {"id": "llama-3.1-70b-versatile", "name": "Llama 3.1 70B", "input": ["text"], "contextWindow": 128000, "maxTokens": 32768},
                {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B", "input": ["text"], "contextWindow": 32768, "maxTokens": 32768},
                {"id": "gemma2-9b-it", "name": "Gemma 2 9B", "input": ["text"], "contextWindow": 8192, "maxTokens": 8192}
            ]
        },
        "cohere": {
            "baseUrl": "https://api.cohere.ai/v1/",
            "api": "openai-completions",
            "models": [
                {"id": "command-r-plus", "name": "Command R+", "input": ["text"], "contextWindow": 128000, "maxTokens": 4096},
                {"id": "command-r", "name": "Command R", "input": ["text"], "contextWindow": 128000, "maxTokens": 4096},
                {"id": "command", "name": "Command", "input": ["text"], "contextWindow": 4096, "maxTokens": 4096}
            ]
        },
        "deepseek": {
            "baseUrl": "https://api.deepseek.com/v1/",
            "api": "openai-completions",
            "models": [
                {"id": "deepseek-chat", "name": "DeepSeek Chat", "input": ["text"], "contextWindow": 64000, "maxTokens": 4096},
                {"id": "deepseek-coder", "name": "DeepSeek Coder", "input": ["text"], "contextWindow": 64000, "maxTokens": 4096}
            ]
        },
        "ollama": {
            "baseUrl": body.base_url or "http://localhost:11434/v1/",
            "api": "openai-completions",
            "models": [
                {"id": "llama3.2", "name": "Llama 3.2 (Local)", "input": ["text"], "contextWindow": 128000, "maxTokens": 4096},
                {"id": "mistral", "name": "Mistral (Local)", "input": ["text"], "contextWindow": 32768, "maxTokens": 4096},
                {"id": "qwen2.5", "name": "Qwen 2.5 (Local)", "input": ["text"], "contextWindow": 128000, "maxTokens": 4096}
            ]
        }
    }
    
    if provider not in provider_configs:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    
    # Validate API key for non-Ollama providers
    if provider != "ollama":
        if not body.api_key or len(body.api_key.strip()) < 10:
            raise HTTPException(status_code=400, detail=f"{provider.title()} requires an API key")
    
    try:
        # Load existing config
        existing_config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                existing_config = json.load(f)
        
        if "models" not in existing_config:
            existing_config["models"] = {"mode": "merge", "providers": {}}
        if "providers" not in existing_config["models"]:
            existing_config["models"]["providers"] = {}
        
        # Add the provider
        config = provider_configs[provider].copy()
        if provider != "ollama":
            config["apiKey"] = body.api_key.strip()
        
        existing_config["models"]["providers"][provider] = config
        
        # Write config
        with open(CONFIG_FILE, "w") as f:
            json.dump(existing_config, f, indent=2)
        
        # Restart gateway if running
        if check_gateway_running():
            import subprocess as _sp
            _sp.run(["supervisorctl", "restart", "clawdbot-gateway"], capture_output=True)
        
        model_list = ", ".join([m["id"] for m in config["models"]])
        logger.info(f"{provider.title()} provider configured by {user.email}")
        return {
            "ok": True,
            "provider": provider,
            "message": f"{provider.title()} provider configured successfully.",
            "models": [m["id"] for m in config["models"]]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to configure {provider}: {str(e)}")


@api_router.get("/hub/providers")
async def get_providers(request: Request):
    """Get list of configured providers"""
    user = await require_auth(request)
    
    try:
        if not os.path.exists(CONFIG_FILE):
            return {"providers": {}}
        
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        
        providers = config.get("models", {}).get("providers", {})
        
        # Return provider info without exposing API keys
        result = {}
        for name, prov in providers.items():
            result[name] = {
                "name": name,
                "configured": True,
                "models": [m["id"] for m in prov.get("models", [])]
            }
        
        return {"providers": result}
    except Exception as e:
        logger.error(f"Failed to get providers: {e}")
        return {"providers": {}}


@api_router.get("/hub/analytics")
async def get_analytics(request: Request, range: str = "7d"):
    """Get usage analytics (mock data for now - integrate with OpenClaw logs later)"""
    user = await require_auth(request)
    
    # TODO: Integrate with actual OpenClaw usage logs
    # For now, return realistic mock data
    return {
        "totalTokens": 1250000,
        "totalCost": 12.45,
        "totalRequests": 342,
        "avgResponseTime": 1.8,
        "topModels": [
            {"model": "claude-sonnet-4-5", "requests": 156, "tokens": 620000, "cost": 6.20, "avgTime": 1.5},
            {"model": "gpt-5.2", "requests": 98, "tokens": 380000, "cost": 5.70, "avgTime": 2.1},
            {"model": "llama-3.3-70b", "requests": 54, "tokens": 180000, "cost": 0.11, "avgTime": 0.9},
            {"model": "deepseek-chat", "requests": 34, "tokens": 70000, "cost": 0.02, "avgTime": 2.4}
        ],
        "dailyUsage": [
            {"day": "Mon", "tokens": 145000, "cost": 1.45},
            {"day": "Tue", "tokens": 198000, "cost": 1.98},
            {"day": "Wed", "tokens": 210000, "cost": 2.10},
            {"day": "Thu", "tokens": 185000, "cost": 1.85},
            {"day": "Fri", "tokens": 232000, "cost": 2.32},
            {"day": "Sat", "tokens": 156000, "cost": 1.56},
            {"day": "Sun", "tokens": 124000, "cost": 1.24}
        ]
    }


class QuickChatRequest(BaseModel):
    model: str
    message: str


class PlaygroundRequest(BaseModel):
    model: str
    prompt: str
    temperature: float = 0.7
    max_tokens: int = 1000


@api_router.post("/chat/quick")
async def quick_chat(request: Request, body: QuickChatRequest):
    """Quick chat endpoint for testing models from Hub"""
    user = await require_auth(request)
    
    try:
        # Create LlmChat instance with selected model
        chat = LlmChat(model=body.model)
        
        # Send message and get response
        response = chat.chat([UserMessage(content=body.message)])
        
        return {
            "ok": True,
            "model": body.model,
            "response": response.content if hasattr(response, 'content') else str(response)
        }
    except Exception as e:
        logger.error(f"Quick chat error: {e}")
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


@api_router.post("/chat/playground")
async def playground_chat(request: Request, body: PlaygroundRequest):
    """Playground endpoint for testing prompts with custom parameters"""
    user = await require_auth(request)
    
    try:
        import time
        start_time = time.time()
        
        # Create LlmChat with custom parameters
        chat = LlmChat(
            model=body.model,
            temperature=body.temperature,
            max_tokens=body.max_tokens
        )
        
        # Send message and get response
        response = chat.chat([UserMessage(content=body.prompt)])
        
        end_time = time.time()
        
        return {
            "ok": True,
            "model": body.model,
            "response": response.content if hasattr(response, 'content') else str(response),
            "time": round(end_time - start_time, 2),
            "tokens": body.max_tokens  # TODO: Get actual token count from response
        }
    except Exception as e:
        logger.error(f"Playground chat error: {e}")
        raise HTTPException(status_code=500, detail=f"Playground failed: {str(e)}")


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


# Include the router in the main app — MUST be after all route definitions
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


# Background task for auto-fixing WhatsApp
whatsapp_watcher_task = None
digest_scheduler_task = None


# ============== Daily Digest ==============

async def send_telegram_message(chat_id: str, text: str) -> bool:
    """Send a message to a Telegram user via the bot."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token or not chat_id:
        return False
    try:
        async with httpx.AsyncClient() as hc:
            resp = await hc.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10.0
            )
            return resp.status_code == 200
    except Exception as e:
        logger.error(f"[digest] Telegram send failed: {e}")
        return False


async def get_paired_telegram_id() -> Optional[str]:
    """Get the first paired Telegram user ID from credentials file."""
    allow_file = os.path.expanduser("~/.clawdbot/credentials/telegram-allowFrom.json")
    try:
        if os.path.exists(allow_file):
            with open(allow_file) as f:
                data = json.load(f)
            # Handle both list and dict formats
            if isinstance(data, list) and data:
                return str(data[0])
            elif isinstance(data, dict):
                ids = list(data.keys())
                if ids:
                    return str(ids[0])
    except Exception as e:
        logger.warning(f"[digest] Could not read paired Telegram ID: {e}")
    return None


async def generate_digest_summary(user_email: str) -> Optional[str]:
    """Generate a digest summary of recent activity using Claude."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    since_iso = since.isoformat()

    messages = await db.chat_messages.find(
        {"user_email": user_email, "created_at": {"$gte": since_iso}},
        {"_id": 0}
    ).sort("created_at", 1).to_list(200)

    if not messages:
        return None

    # Build conversation summary
    convo_text = "\n".join(
        f"[{m['role'].upper()}]: {m['content'][:300]}"
        for m in messages[:80]
    )
    user_msgs = [m for m in messages if m["role"] == "user"]
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]

    prompt = (
        f"You are Neo, a personal AI assistant. Here is a summary of the last 24 hours of conversations "
        f"({len(user_msgs)} user messages, {len(assistant_msgs)} responses):\n\n"
        f"{convo_text}\n\n"
        f"Write a concise morning digest (3-5 bullet points) covering:\n"
        f"- Key topics discussed\n"
        f"- Important decisions or information from the conversation\n"
        f"- Any action items or follow-ups mentioned\n"
        f"Keep it brief, friendly, and useful. Use Telegram-friendly markdown (bold with *, not **)."
    )

    try:
        chat = LlmChat(
            api_key=os.environ.get("EMERGENT_API_KEY", ""),
            session_id=f"digest-{user_email}-{datetime.now(timezone.utc).date()}",
            system_message="You are Neo, a helpful AI assistant generating a daily digest."
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        summary = await chat.send_message(UserMessage(text=prompt))
        return summary
    except Exception as e:
        logger.error(f"[digest] LLM summary failed: {e}")
        return None


async def run_digest_for_user(user_email: str):
    """Run the full digest pipeline for a user and deliver via Telegram."""
    logger.info(f"[digest] Running digest for {user_email}")
    summary = await generate_digest_summary(user_email)
    if not summary:
        logger.info(f"[digest] No messages in last 24h for {user_email}, skipping")
        return False

    telegram_id = await get_paired_telegram_id()
    header = f"*Good morning! Here's your Neo digest for {datetime.now(timezone.utc).strftime('%B %d, %Y')}:*\n\n"
    full_message = header + summary

    sent = False
    if telegram_id:
        sent = await send_telegram_message(telegram_id, full_message)
        logger.info(f"[digest] Telegram delivery: {'ok' if sent else 'failed'}")

    # Store in history
    await db.digest_history.insert_one({
        "user_email": user_email,
        "content": full_message,
        "message_count": await db.chat_messages.count_documents(
            {"user_email": user_email,
             "created_at": {"$gte": (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()}}
        ),
        "telegram_sent": sent,
        "sent_at": datetime.now(timezone.utc).isoformat()
    })
    return True


async def digest_scheduler():
    """Background task: runs daily digest at the configured time."""
    logger.info("[digest-scheduler] Started")
    last_sent_date = None
    while True:
        await asyncio.sleep(60)  # check every minute
        try:
            config = await db.digest_config.find_one({}, {"_id": 0})
            if not config or not config.get("enabled"):
                continue

            now_utc = datetime.now(timezone.utc)
            send_time = config.get("send_time", "08:00")
            h, m = map(int, send_time.split(":"))
            today = now_utc.date()

            if now_utc.hour == h and now_utc.minute == m and last_sent_date != today:
                last_sent_date = today
                user_email = config.get("user_email")
                if user_email:
                    await run_digest_for_user(user_email)
        except Exception as e:
            logger.warning(f"[digest-scheduler] Error: {e}")


class DigestConfigRequest(BaseModel):
    enabled: bool
    send_time: str = "08:00"  # HH:MM UTC


@api_router.get("/digest/config")
async def get_digest_config(request: Request):
    user = await require_auth(request)
    config = await db.digest_config.find_one({"user_email": user.email}, {"_id": 0})
    if not config:
        return {"enabled": False, "send_time": "08:00", "user_email": user.email}
    return config


@api_router.post("/digest/config")
async def save_digest_config(request: Request, body: DigestConfigRequest):
    user = await require_auth(request)
    # Validate time format
    try:
        h, m = map(int, body.send_time.split(":"))
        assert 0 <= h <= 23 and 0 <= m <= 59
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM (UTC).")
    await db.digest_config.update_one(
        {"user_email": user.email},
        {"$set": {"enabled": body.enabled, "send_time": body.send_time,
                  "user_email": user.email, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )
    return {"ok": True, "enabled": body.enabled, "send_time": body.send_time}


@api_router.post("/digest/trigger")
async def trigger_digest_now(request: Request):
    user = await require_auth(request)
    sent = await run_digest_for_user(user.email)
    if sent:
        return {"ok": True, "message": "Digest sent to your Telegram!"}
    return {"ok": False, "message": "No messages in the last 24h to summarise — chat with Neo first!"}


@api_router.get("/digest/history")
async def get_digest_history(request: Request):
    user = await require_auth(request)
    history = await db.digest_history.find(
        {"user_email": user.email}, {"_id": 0}
    ).sort("sent_at", -1).limit(10).to_list(10)
    return {"history": history}


# Background task for auto-fixing WhatsApp

async def whatsapp_auto_fix_watcher():
    """Auto-fix Baileys registered=false bug every 5 seconds."""
    logger.info("[whatsapp-watcher] Background watcher started")
    while True:
        await asyncio.sleep(5)
        try:
            status = get_whatsapp_status()
            logger.info(f"[whatsapp-watcher] Check: linked={status['linked']}, registered={status['registered']}, phone={status['phone']}")
            if status["linked"] and not status["registered"]:
                logger.info("[whatsapp-watcher] DETECTED registered=false, applying fix...")
                if fix_registered_flag():
                    logger.info("[whatsapp-watcher] Fix applied, restarting gateway via supervisor...")
                    result = subprocess.run(["supervisorctl", "restart", "clawdbot-gateway"], capture_output=True, text=True)
                    logger.info(f"[whatsapp-watcher] Supervisor restart result: {result.stdout} {result.stderr}")
        except Exception as e:
            logger.warning(f"[whatsapp-watcher] Error: {e}")


@app.on_event("startup")
async def startup_event():
    """Run on server startup - ensure Moltbot dependencies are installed and auto-start gateway if needed"""
    global whatsapp_watcher_task, gateway_state

    logger.info("Server starting up...")

    # Reload supervisor config to pick up any changes
    SupervisorClient.reload_config()

    # Check and install Moltbot dependencies if needed
    clawdbot_cmd = get_clawdbot_command()
    if clawdbot_cmd:
        logger.info(f"Moltbot dependencies ready: {clawdbot_cmd}")
    else:
        logger.info("Moltbot dependencies not found, will install on first use")

    # Check database for persistent gateway config
    config_doc = None
    try:
        config_doc = await db.moltbot_configs.find_one({"_id": "gateway_config"})
    except Exception as e:
        logger.warning(f"Could not read gateway config from database: {e}")

    should_run = config_doc.get("should_run", False) if config_doc else False
    logger.info(f"Gateway should_run flag: {should_run}")

    # Check if gateway is already running via supervisor
    if SupervisorClient.status():
        pid = SupervisorClient.get_pid()
        logger.info(f"Gateway already running via supervisor (PID: {pid})")

        gateway_state["provider"] = config_doc.get("provider", "emergent") if config_doc else "emergent"

        # Recover token from config file
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            gateway_state["token"] = config.get("gateway", {}).get("auth", {}).get("token")
            logger.info("Recovered gateway token from config file")
        except Exception as e:
            logger.warning(f"Could not recover gateway token: {e}")

        # Recover owner info from database
        if config_doc:
            gateway_state["owner_user_id"] = config_doc.get("owner_user_id")
            gateway_state["started_at"] = config_doc.get("started_at")
            logger.info(f"Recovered gateway owner from database: {gateway_state['owner_user_id']}")

    elif should_run and config_doc:
        # Gateway should be running but isn't - auto-start it!
        logger.info("Gateway should_run=True but not running - auto-starting via supervisor...")

        # Recover token from config file or database
        token = config_doc.get("token")
        if not token:
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                token = config.get("gateway", {}).get("auth", {}).get("token")
            except:
                token = generate_token()

        # Write env file for supervisor wrapper
        write_gateway_env(token=token, provider=config_doc.get("provider", "emergent"))

        # Start via supervisor
        if SupervisorClient.start():
            logger.info("Gateway auto-started successfully via supervisor")

            # Wait briefly for it to be ready
            await asyncio.sleep(3)

            gateway_state["token"] = token
            gateway_state["provider"] = config_doc.get("provider", "emergent")
            gateway_state["owner_user_id"] = config_doc.get("owner_user_id")
            gateway_state["started_at"] = config_doc.get("started_at")
        else:
            logger.error("Failed to auto-start gateway via supervisor")

    # Start WhatsApp auto-fix background watcher
    whatsapp_watcher_task = asyncio.create_task(whatsapp_auto_fix_watcher())
    logger.info("[whatsapp-watcher] Background watcher task created (checks every 5s)")

    # Start daily digest scheduler
    digest_scheduler_task = asyncio.create_task(digest_scheduler())
    logger.info("[digest-scheduler] Background task created (checks every 60s)")


@app.on_event("shutdown")
async def shutdown_db_client():
    global whatsapp_watcher_task, digest_scheduler_task

    # Stop WhatsApp watcher task
    if whatsapp_watcher_task:
        whatsapp_watcher_task.cancel()
        try:
            await whatsapp_watcher_task
        except asyncio.CancelledError:
            pass

    # Stop digest scheduler
    if digest_scheduler_task:
        digest_scheduler_task.cancel()
        try:
            await digest_scheduler_task
        except asyncio.CancelledError:
            pass

    # NOTE: We do NOT stop the gateway on backend shutdown!
    # The gateway is managed by supervisor and should continue running
    # independently of the backend. It will auto-restart on crash and
    # survive backend restarts.
    logger.info("Backend shutting down - gateway will continue running via supervisor")

    client.close()
