# MoltBot + Telegram Integration PRD

## Problem Statement
1. Install MoltBot (OpenClaw/clawdbot) on Emergent platform
2. Configure Telegram bot API (token: 7957705342:AAGEeU3H387mfaWZ7EGBgwfRRi3fimZFSiU)
3. "Do all" — start OpenClaw with Emergent provider, wire up all channels

## Architecture
- **Frontend**: React (served via `serve -s build`) → port 3000
- **Backend**: FastAPI (Python) → port 8001
- **Database**: MongoDB → port 27017
- **Gateway**: clawdbot (OpenClaw) → port 18789 (supervisor-managed)
- **Proxy**: nginx-code-proxy

## What Was Implemented

### 2026-02-23: MoltBot Installation
- LLM key fetched, restic restore of 1.679 GiB (147,221 files)
- Frontend rebuilt with correct preview endpoint URLs
- All services started via supervisor

### 2026-02-23: Telegram Bot Integration
- Configured `channels.telegram.botToken` in `/root/.clawdbot/clawdbot.json`
- `TELEGRAM_BOT_TOKEN` stored in `/app/backend/.env`
- Gateway env (`/root/.clawdbot/gateway.env`) updated with Telegram token
- Backend endpoint: `GET /api/telegram/status` — returns bot info from Telegram API
- Backend endpoint: `POST /api/telegram/configure` — validates & updates bot token (auth required)
- Frontend Telegram panel added to SetupPage: shows connected badge, bot name/username
- Telegram webhook cleared; gateway polling cleanly as **@Clawdsahiixbot**

### 2026-02-23: OpenClaw Gateway Started
- Gateway configured with Emergent LLM (Claude Sonnet 4.5 + GPT-5.2)
- Started via supervisor: `supervisorctl start clawdbot-gateway`
- MongoDB gateway_config document synced (should_run=true)

## Services Running
| Service          | Status  | Details                              |
|-----------------|---------|--------------------------------------|
| backend         | RUNNING | FastAPI on port 8001                 |
| frontend        | RUNNING | React on port 3000                   |
| mongodb         | RUNNING | Port 27017                           |
| nginx-code-proxy| RUNNING | Reverse proxy                        |
| clawdbot-gateway| RUNNING | Port 18789, Telegram @Clawdsahiixbot |

## API Endpoints
- `GET /api/` — health check
- `GET /api/openclaw/status` — gateway status
- `POST /api/openclaw/start` — start gateway (auth required)
- `POST /api/openclaw/stop` — stop gateway (owner only)
- `GET /api/telegram/status` — Telegram bot connection status
- `POST /api/telegram/configure` — update Telegram bot token (auth required)
- `GET /api/auth/me` — current user
- `POST /api/auth/session` — create session from Emergent Auth

## Telegram Bot
- **Bot**: Clawd dbot
- **Username**: @Clawdsahiixbot
- **Bot ID**: 7957705342
- **Status**: Active, polling via getUpdates

## Tutorial Reference
https://emergent.sh/tutorial/moltbot-on-emergent

## Prioritized Backlog
- P1: WhatsApp QR pairing flow (infrastructure ready, no credentials needed)
- P1: Instance ownership assignment on first login
- P2: Telegram pairing approval UI (clawdbot pairing list/approve commands)
- P2: Dashboard showing all connected channels
- P3: Cron job management UI
