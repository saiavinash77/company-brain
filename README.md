# Company Brain

Your company's AI Chief of Staff. One Top Agent you talk to; 10 specialist agents it delegates to — sales, onboarding, negotiation, finance, legal, ideas, research, strategy, briefings — plus a dedicated agent per client, spawned on conversion.

Built on [Agno Framework v2](https://github.com/agno-agi/agno). Models: Groq (Llama 3.3 70B) + Google Gemini (+ optional Mistral).

## Quick start (local chat — no Docker needed)

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# .venv/bin/pip install -r requirements.txt               # macOS/Linux

cp example.env .env        # add at least GOOGLE_API_KEY (free: aistudio.google.com)

.venv/Scripts/python -m app.chat
```

Type to the Top Agent. `exit` quits. Everything is stored locally in `data/companybrain_memory.db`.

## Full stack (AgentOS UI + WhatsApp webhook)

```bash
docker compose up -d --build
# UI: http://localhost:8000  |  webhook: POST /webhook/whatsapp
```

Requires Docker Desktop. The WhatsApp webhook (Twilio) is mounted on the same port — point your Twilio number's webhook at `https://<host>:8000/webhook/whatsapp`.

## Architecture

- **Top Agent** (Gemini) — the only agent you talk to; routes everything
- **Specialists** — Sales, Onboarding, Negotiation, Finance, Legal, Idea, Refinement, Market Research, Strategy, Briefing
- **Client Agents** — one per client, spawned by the Lead Conversion workflow, isolated to their vault
- **SuperMemory (5 layers)** — working tasks, client vaults (strict isolation), semantic search, playbooks (`data/playbooks/`), full audit log
- **Guardrails** — all pricing/deal terms require owner approval; every agent action is audited

## Environment

See `example.env`. Minimum for local chat: `GOOGLE_API_KEY`. Add `GROQ_API_KEY` for the Groq-powered agents. WhatsApp/Gmail keys are optional.

## Status / known fixes over upstream

- `requirements.txt` was missing `openai` + `google-genai` — fixed
- Deprecated `gemini-1.5-pro`/`2.0-flash` model IDs → `gemini-2.5-flash` — fixed
- WhatsApp webhook now mounts on the AgentOS app (single port) instead of needing a second server — fixed
- Added `app/chat.py` — local terminal chat with the Top Agent, no Docker/Postgres required
- `/floor` rendered blank: vite `base: './'` emitted relative asset URLs, and agno's TrailingSlashMiddleware strips the trailing slash so the browser resolved them to `/assets/*` (404). Fixed with `base: '/floor/'`
- `http://localhost:8000/` showed only AgentOS's JSON descriptor, and agno overrides conflicting custom routes (observed with `/health`) — the landing page at `/` is now served via a pure-ASGI middleware and includes a built-in chat panel wired to `POST /teams/company-brain/runs`
