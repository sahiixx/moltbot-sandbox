# MoltBot Installation PRD

## Problem Statement
Install MoltBot on the Emergent platform by:
1. Fetching the Emergent LLM key via `emergent_integrations_manager`
2. Running the MoltBot install script from https://moltbot.emergent.to/install.sh
3. Confirming successful installation

## Architecture
- **Restore source**: S3 restic repository `s3:s3.amazonaws.com/moltbot-emergent/molt-310126-2`
- **Frontend**: React (served via `serve -s build`)
- **Backend**: FastAPI (Python)
- **Database**: MongoDB
- **Proxy**: nginx-code-proxy

## What Was Implemented
- **2026-02-XX**: MoltBot installation completed
  - LLM key fetched from emergent_integrations_manager
  - Created `/app/frontend/.env` with `REACT_APP_BACKEND_URL` (preview endpoint)
  - Ran install script: restic restored 147,221 files/dirs (1.679 GiB)
  - LLM key injected into `/app/backend/.env` and clawdbot config files
  - Frontend rebuilt with correct URLs
  - All services started: backend, frontend, mongodb, nginx-code-proxy

## Services Running
| Service         | Status  |
|----------------|---------|
| backend        | RUNNING |
| frontend       | RUNNING |
| mongodb        | RUNNING |
| nginx-code-proxy | RUNNING |

## Tutorial Reference
https://emergent.sh/tutorial/moltbot-on-emergent

## Next Steps
- Start clawdbot-gateway service if needed
- Verify MoltBot UI loads at the preview endpoint
- Configure Neo AI assistant preferences
