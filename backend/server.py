from fastapi import FastAPI, APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Request, Response
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


# Background task for auto-fixing WhatsApp
whatsapp_watcher_task = None

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


@app.on_event("shutdown")
async def shutdown_db_client():
    global whatsapp_watcher_task

    # Stop WhatsApp watcher task
    if whatsapp_watcher_task:
        whatsapp_watcher_task.cancel()
        try:
            await whatsapp_watcher_task
        except asyncio.CancelledError:
            pass

    # NOTE: We do NOT stop the gateway on backend shutdown!
    # The gateway is managed by supervisor and should continue running
    # independently of the backend. It will auto-restart on crash and
    # survive backend restarts.
    logger.info("Backend shutting down - gateway will continue running via supervisor")

    client.close()
