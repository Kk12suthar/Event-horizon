# EventHorizon

EventHorizon is a full-stack data workspace: a FastAPI backend, a LangGraph-based
AI agent server, and a React/Vite frontend, orchestrated together for project,
folder, and session-based data analysis and reporting.

## Architecture

- `backend/` - FastAPI REST API (auth, projects, folders, files, sessions, dashboards, data access)
- `agent-server/` - LangGraph-based AI agent server exposing chat/report/dashboard streaming endpoints
- `new-frontend/app/` - React + Vite + TypeScript frontend (primary UI)
- `homepage/` - Marketing/landing page (separate Vite app)

## Run The Whole App

Use the root launcher from PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\run-app.ps1
```

If the ports are already occupied and you want to replace the running processes:

```powershell
powershell -ExecutionPolicy Bypass -File .\run-app.ps1 -Restart
```

Services:

- Frontend: `http://127.0.0.1:5174`
- Backend API: `http://127.0.0.1:8001`
- LangGraph agent server: `http://127.0.0.1:8010`

Logs are written to `logs/`.

## Environment

- Real local env: `.env` (never committed, see `.gitignore`)
- Safe template: `.env.example`
- Reference: `ENVIRONMENT.md`

Copy `.env.example` to `.env` and fill in your own credentials (database, JWT
secret, Firebase, LLM provider API keys, etc.) before running the app. Never
commit `.env` or `backend/firebase-credentials.json` - both are gitignored by
default.

## License

This repository is proprietary. All rights reserved. See [LICENSE](./LICENSE)
for details. No part of this codebase may be copied, used, modified, or
distributed without prior written permission from the copyright holder.
