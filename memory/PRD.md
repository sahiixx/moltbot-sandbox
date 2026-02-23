# MoltBot / Clawdbot — Project Requirements Document

## Original Problem Statement
Install MoltBot (Clawdbot), configure Telegram bot integration, set up the AI agent "Neo" end-to-end, and integrate 3 GitHub repositories "All in one":
1. `https://github.com/sahiixx/500-AI-Agents-Projects`
2. `https://github.com/sahiixx/system-prompts-and-models-of-ai-tools`
3. `https://github.com/MoonshotAI/kimi-agent-sdk`

Critical original requirement: slug generation must include high-entropy random suffix (≥32 bits).

## Architecture

```
/app/
├── backend/
│   ├── server.py       # FastAPI backend — auth, openclaw, telegram, hub endpoints
│   └── .env            # MONGO_URL, DB_NAME, EMERGENT_API_KEY, TELEGRAM_BOT_TOKEN
├── frontend/
│   └── src/
│       ├── App.js               # Routes: /, /hub, /login
│       └── pages/
│           ├── SetupPage.js     # OpenClaw setup + Telegram config + AI Hub nav
│           ├── HubPage.js       # AI Hub (Personas, Agent Directory, Kimi provider)
│           ├── LoginPage.js
│           └── AuthCallback.js
└── memory/PRD.md

/root/
├── .clawdbot/
│   ├── clawdbot.json            # Telegram token, gateway config, LLM providers
│   └── credentials/
│       └── telegram-allowFrom.json  # Paired user IDs
└── clawd/
    ├── IDENTITY.md   # Active bot persona (switchable via AI Hub)
    ├── SOUL.md
    ├── USER.md
    └── HEARTBEAT.md
```

## Tech Stack
- **Frontend**: React + Craco, TailwindCSS, Shadcn/UI, Framer Motion
- **Backend**: FastAPI (Python), Motor (MongoDB async)
- **Database**: MongoDB
- **AI Gateway**: Clawdbot (MoltBot) — supervisor-managed
- **LLM**: Emergent Universal Key → Claude Sonnet 4.5 + GPT-5.2
- **Telegram**: Bot token `7957705342:AAGEeU3H387mfaWZ7EGBgwfRRi3fimZFSiU` (@Clawdsahiixbot)
- **Paired User**: Telegram ID 8252725134 (@Zeus920)

## What's Been Implemented

### Phase 1 — Core Installation (Session 1)
- MoltBot/Clawdbot installed and configured
- Emergent LLM Key wired up
- Services managed by Supervisor

### Phase 2 — Telegram Integration
- Telegram bot token configured in clawdbot.json + backend .env
- `/api/telegram/status` and `/api/telegram/configure` endpoints
- SetupPage shows Telegram connection status + config UI
- User 8252725134 paired via `clawdbot pairing approve`
- Agent persona configured (IDENTITY.md, USER.md, HEARTBEAT.md, SOUL.md)

### Phase 3 — AI Hub (3 GitHub Repos Integration) [2026-02-23]
- **Persona Library** (from system-prompts-and-models-of-ai-tools)
  - 8 personas: Neo (Default), Cursor, Devin, Manus, Lovable, Perplexity, Claude Code, Notion AI
  - `POST /api/hub/personas/apply` — writes new IDENTITY.md to /root/clawd/
  - `GET /api/hub/personas` — returns personas with active flag
- **Agent Directory** (from 500-AI-Agents-Projects)
  - 35 curated AI agent use cases across 25 industries and 4 frameworks
  - `GET /api/hub/agents` — with search, industry, framework filtering
- **Kimi Provider** (from kimi-agent-sdk)
  - `POST /api/hub/kimi/configure` — adds Moonshot as OpenAI-compatible provider
  - Models: moonshot-v1-8k, 32k, 128k
- New frontend route `/hub` → HubPage with 3 tabs
- AI Hub navigation button added to SetupPage header

### Phase 4 — Web Chat Interface [2026-02-23]
- **ChatPage** at `/chat` — full chat UI to talk to Neo directly from browser
- Backend endpoints: `POST /api/chat/message`, `GET /api/chat/sessions`, `GET /api/chat/history/{id}`, `DELETE /api/chat/session/{id}`
- LLM: Claude Sonnet 4.5 via emergentintegrations, persona-aware system prompt from IDENTITY.md
- MongoDB persistence for messages and sessions
- Features: session history sidebar, suggested prompts, typing indicator, auto-scroll, delete sessions
- Navigation: Chat button added to SetupPage and HubPage headers
- LLM verified working: direct test returned "Hello! I'm Neo. How can I help you today?"

### Phase 6 — "All" Feature Batch [2026-02-23]
- **Voice Input**: Mic button in chat → browser MediaRecorder → Whisper-1 transcription → fills input field
- **Smart Persona Auto-Routing**: Detects message intent (coding/writing/research/UI/autonomous) and suggests persona switch inline. Rule-based classifier, 8 intent categories. `POST /api/hub/personas/detect`
- **WhatsApp Setup UI**: WhatsApp card added to SetupPage showing connection status and `clawdbot whatsapp link` instructions
- **50 Agents**: Expanded agent directory from 35 to 50 use cases (Healthcare, Finance, Marketing, Software Dev, etc.)
- **Slug Entropy Verified**: `secrets.token_hex(32)` = 256 bits ✅ (requirement was ≥32 bits)


- Typewriter animation for Neo's responses — adaptive speed, reveals character-by-character
- Full markdown rendering: code blocks with copy button, tables, lists, blockquotes, inline code
- Blinking cursor shown while text is being revealed
- react-markdown + remark-gfm installed
- `GET /api/hub/personas` — list personas (public)
- `POST /api/hub/personas/apply` — apply persona (auth required)
- `GET /api/hub/agents?q=&industry=&framework=` — agent directory (public)
- `POST /api/hub/kimi/configure` — add Kimi LLM (auth required)
- `GET /api/openclaw/status` — gateway status
- `GET /api/telegram/status` — Telegram bot status
- `POST /api/telegram/configure` — configure Telegram

## Prioritized Backlog

### P0 (Blockers)
- LLM Key balance — user needs to top up Emergent Universal Key (Profile → Universal Key → Add Balance)

### P1 (Next Up)
- Verify slug generation entropy (≥32 bits) in Clawdbot source — original requirement never verified
- Test applying different personas via Telegram and confirm bot behavior changes
- Add more agent use cases (currently 35 of 500)

### P2 (Future)
- Add more system prompt tools (Windsurf, Replit, v0, GitHub Copilot personas)
- WhatsApp integration (monitor is already wired, just needs setup)
- Session history / conversation logs in the Hub UI
- Export/import persona configurations
