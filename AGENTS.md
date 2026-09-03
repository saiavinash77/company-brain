# Company Brain — Architecture Guide

## Overview
Company Brain is a multi-agent AI system built on top of Agno Scout and the Agno Framework v2.
It serves as an intelligent business assistant with specialized agents for sales, client management,
negotiation, finance, legal, idea development, and strategic thinking.

## Architecture

### Single Entry Point
The **Top Agent** (Chief of Staff) is the ONLY agent the owner interacts with.
All requests flow: Owner → Top Agent → Specialist Agent → Top Agent → Owner.
Agents never talk to each other directly — they write to SuperMemory.

### Agent Roster (Week 1 — Foundation)
| Agent | Model | Role |
|-------|-------|------|
| Top Agent | Gemini Pro | Orchestrator. Routes everything, collects status, escalates to owner |
| Sales Agent | Groq Llama 3.3 70B | Qualify leads, score, draft first replies, manage pipeline |

### Agent Roster (Week 2 — Client System + Email)
| Agent | Model | Role |
|-------|-------|------|
| Top Agent | Gemini Pro | Orchestrator. Now also delegates to Onboarding Agent, manages Client Agents |
| Sales Agent | Groq Llama 3.3 70B | Lead qualification & scoring |
| Onboarding Agent | Gemini Flash | New client setup checklist, credential gathering, vault population |
| Client Agent | Gemini Flash | Per-client dedicated agent, spawned dynamically on lead conversion |

### Agent Roster (Week 3+ — Planned)
| Agent | Model | Role |
|-------|-------|------|
| Negotiation Agent | Gemini Pro | Pricing & deal structuring |
| Finance Agent | Groq Llama 3.3 70B | Invoices & payments |
| Legal Agent | Mistral Large | Contract review |
| Idea Agent | Gemini Flash | Capture raw ideas |
| Refinement Agent | Mistral Large | Turn ideas into briefs |
| Market Research Agent | Groq Llama 3.3 70B | Competitor & trend research |
| Briefing Agent | Groq Llama 3.3 70B | Daily/weekly summaries |
| Strategy Agent | Gemini Pro | Campaign thinking |

## SuperMemory (5 Layers)
1. **Working Memory** — Active tasks & conversations
2. **Client Vaults** — Per-client isolated history (strict separation)
3. **Semantic Memory** — Vector search (PgVector locally, Vertex AI on GCP)
4. **Playbook Memory** — Rate cards, SOPs, winning patterns
5. **Audit & Learning** — Full action log (every action is tracked)

## Key Patterns

### Provider Pattern (from Agno Scout)
Each data source is wrapped in a Provider class with:
- `get_tools()` → list of tool functions for agents
- `get_instructions()` → system instructions for agents
- `is_available()` → check if required config is present

### Memory Backend Abstraction
- `MemoryBackend` (abstract) → `LocalBackend` (SQLite) or `GCPBackend` (Firestore/BigQuery)
- Swap via `MEMORY_BACKEND=local|gcp` environment variable
- No code changes needed when migrating to GCP

### Workflows
- **Lead Conversion** — Lead → create client vault → spawn Client Agent → trigger Onboarding Agent
- **Daily Briefing** (Week 5) — Scheduled morning summary
- **Pricing Request** (Week 3) — 3 pricing options → owner approval → send

## Project Structure
```
app/
├── main.py              # AgentOS entry point + webhook endpoints
├── config.py            # Environment configuration
├── models/              # LLM helpers (Groq, Gemini, Mistral)
├── agents/              # Individual agent definitions
├── teams/               # Team compositions
├── workflows/           # Deterministic multi-step workflows
├── memory/              # SuperMemory system
├── providers/           # Context providers (Telnyx, Gmail, Web, Memory)
data/playbooks/          # Rate cards, SOPs
```

## Development

### Local Setup
```bash
cp example.env .env
# Fill in your API keys
docker compose up -d --build
# Open http://localhost:8000 for AgentOS Web UI
```

### Key Environment Variables
- `GROQ_API_KEY` — Groq API (Llama 3.3 70B)
- `GOOGLE_API_KEY` — Gemini API (Flash/Pro)
- `MISTRAL_API_KEY` — Mistral API
- `TELYNX_API_KEY` — Telnyx WhatsApp API
- `DATABASE_URL` — PostgreSQL connection

## Non-Negotiables
1. Built on Agno Scout ContextProvider pattern
2. Top Agent is the ONLY user interface
3. Strict client data isolation via Client Vaults
4. All pricing/negotiation requires owner approval
5. Full audit trail of every agent action
6. Models: Groq + Gemini + Mistral ONLY

## Boot Notes (verified 2026-08-24)
- Run from repo root as a module: `.venv\Scripts\python.exe -m app.main` — `python app\main.py` fails with `ModuleNotFoundError: No module named 'app'`.
- serve() blocks silently at "Initializing Company Brain..." if Postgres is down. Start Docker Desktop first (`C:\Program Files\Docker\Docker\Docker Desktop.exe`); compose services `company-brain-db`/`company-brain-app` auto-start with it. Verify DB via port 5432 listening.
- After changing office-floor-widget src, always `npm run build` before serving — dist/ is committed and stale hashes will 404.
- Port 8000 is owned by the docker container (wslrelay). A local `python -m app.main` can still bind 127.0.0.1:8000 alongside it — probes hitting 127.0.0.1 see the local server while browsers on ::1/localhost may hit the stale container. After changing app/widget code, always rebuild: `docker compose up -d --build` (image unpack alone ~55s; give it 600s+).

---

## Current System (v2 — production)

### Who Is Talking (per-person identity)
Three named people use the system. Identity comes from a slash command
(`/Sai`, `/Bruhadish`, `/Sravani`) in any chat, or the header dropdown in the
modern chat. Runs carry `user_id=<person>`:

- `app/identity.py` — the registry (display name, slash, role). Add people here.
- `app/telemetry/agent_events.py` — injects `[X is asking — role]` before the
  team input, so the model knows the speaker (user_id alone is never shown to it).
- Sessions are stored natively per-person (`user_id` on TeamSession rows);
  `GET /api/sessions/{person}` lists one person's space. One Postgres holds
  everyone — memory tools can read across spaces when a run needs it.

### Auth
- `APP_PASSCODE` → browser gate (HMAC cookie, 30 days)
- `AUTH0_DOMAIN` (+ `AUTH0_AUDIENCE`) → RS256 JWT verification against JWKS,
  accepted as `Authorization: Bearer …` or the `cb_auth0` cookie (also on the
  websocket). Both credentials work side by side.

### Web search
`app/providers/web_provider.py` — Serper primary (`SERPER_API_KEY`,
https://serper.dev), DuckDuckGo automatic fallback (its `web_search` is a
SYNC function — do not await it). Answer-box/knowledge-graph results are
appended as an overview.

### Deploy (GCP)
- `deploy/deploy.sh` — first deploy: Cloud SQL Postgres 16 + pgvector,
  Artifact Registry, Secret Manager (all keys incl. Serper/Auth0), VPC
  connector, Cloud Run. ~30–45 min, idempotent.
- `deploy/redeploy.sh` — every change after: widget build → Cloud Build
  (cached Python layers) → Cloud Run update → /health smoke. ~5–8 min.
- Frontend dist/ is built locally and shipped; the Dockerfile does NOT
  install node/npm (`.dockerignore` excludes node_modules + deploy/).

### Chat UIs
- `/chat` — modern chat: SSE streaming, live briefing (HN tech news +
  own-conversation recap), reader settings, per-person spaces, file
  attachments parsed in-browser (pdf.js).
- `/floor` — workbench: draggable Pixi office floor + team chat.
Both accept the slash-identity commands.
