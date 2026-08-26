# Company Brain — Remaining Work, Testing & Deployment Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Finish the remaining polish (live floor verification, tests), then deploy Company Brain to the cloud with Cloudflare in front, so Sai can iterate on UI/design while it runs 24/7.

**Architecture:** FastAPI + Agno team (11 agents) already runs locally in Docker (app container :8000 + Postgres/pgvector). Deployment moves this stack to a free/cheap cloud host; Cloudflare sits in front as DNS + proxy (TLS, domain, caching, bot protection, and WebSocket passthrough which the floor requires).

**Tech Stack:** FastAPI · Agno v2 · Docker Compose · Postgres+pgvector · React/Vite (floor widget) · Google Gemini/Groq · Cloudflare (DNS/proxy) · Cloud Run or Railway/Fly.io (host)

---

## Phase 0 — Verify current state locally (blockers first)

### Task 0.1: Confirm Gemini quota restored & live delegation test
**Objective:** Prove the full chain works: prompt → delegation → events → floor animation.

- Step: Wait for quota reset (or add new key from a *fresh* Google project into `.env`).
- Step: `docker compose up -d --build`, wait for `GET /health` → 200.
- Step: Open WS listener (`ws://localhost:8000/ws/agent-status`) in one shell; POST a delegation-forcing message ("Delegate to Sales Agent: qualify lead…") to `/teams/company-brain/runs`.
- Expected: ≥3 events (`working` top_agent → `handoff` → `working` sales_agent → `idle` ×2).
- Step: Open `/floor` in browser, repeat prompt, visually confirm Boss walks to conference table, envelope flies, Sales Agent walks to web portal station.
- **This is the acceptance gate for everything else. If it fails, debug before proceeding.**

### Task 0.2: Fix anything Task 0.1 reveals
- Known suspects: event emission inside Agno coordinate-mode member runs; WS broadcast ordering; envelope timing.

---

## Phase 1 — Test suite (fill the gap: zero automated tests today)

### Task 1.1: Test scaffolding
- Files: Create `tests/__init__.py`, `tests/conftest.py`, add `pytest`, `pytest-asyncio`, `httpx` to `requirements-dev.txt`.
- conftest: fixture building SuperMemory on temp SQLite backend; fixture building team with fake model keys via monkeypatched env.

### Task 1.2: Memory layer tests
- File: `tests/test_memory.py`
- Tests: audit log_action→get_agent_history roundtrip; client vault isolation (vault A cannot read vault B); working memory create→complete task; playbook load from `data/playbooks/*.json`.

### Task 1.3: Telemetry/event-bus tests
- File: `tests/test_agent_events.py`
- Tests: publish emits to subscriber queue; reentrancy depth (nested runs don't double-flip state); handoff event carries `target_agent_id`; snapshot returns all 11 fixed desks; roster_add/remove broadcasts `kind:"roster"`.

### Task 1.4: API endpoint tests
- File: `tests/test_api.py` (FastAPI TestClient against `webhook_app`)
- Tests: `/health` 200; `/api/settings-status` key flags reflect env; `/api/agent-activity/{id}` returns live+history+model; unknown agent id → live=None, empty history; `/api/agent-status/snapshot` has `floor` meta.
- Run: `.venv/Scripts/python -m pytest tests/ -v` — expected all pass.

### Task 1.5: Floor widget smoke check
- Manual/scripted: build widget (`npm run build` exits 0), serve dist, confirm no console errors and snapshot fetch succeeds.

### Task 1.6: Commit
```bash
git commit -m "test: memory, telemetry, API test suites"
```

---

## Phase 2 — Deployment preparation

### Task 2.1: Choose host (decision recorded)
- Recommendation: **Cloud Run** (container-native, scale-to-zero, cheap) — matches original PRD. Fallback if GCP setup drags: Railway/Fly.io (one-click compose-ish deploys).
- Postgres options: Neon (free tier, supports pgvector) or Cloud SQL.

### Task 2.2: Production config hygiene
- Modify: `app/config.py` — read `PORT` from env (Cloud Run injects it); default keep 8000.
- Modify: `compose.yaml` — split out `compose.prod.yaml` referencing managed DATABASE_URL instead of local pgvector container.
- Security: ensure `.env` never ships; secrets via host's env/secret manager.

### Task 2.3: Container tweaks
- Modify: `Dockerfile` — copy prebuilt `office-floor-widget/dist` (build stage: node:20-alpine runs `npm ci && npm run build`; runtime stage copies dist into app image). Removes Node requirement at deploy time.
- Verify locally: `docker compose -f compose.yaml -f compose.prod.yaml up --build` still serves `/floor` with fresh dist.

### Task 2.4: Deploy to Cloud Run
- Steps: `gcloud auth login` → enable Run + Secret Manager APIs → `gcloud run deploy company-brain --source . --region asia-south1 --allow-unauthenticated --set-env-vars GOOGLE_API_KEY=…(via secrets)` → note the `*.run.app` URL.
- Verify: `curl https://<run-url>/health` → 200; open `/floor`; run one delegation; watch WS events over public URL.

---

## Phase 3 — Cloudflare integration (why it helps us)

| Capability | Why Company Brain needs it |
|---|---|
| 🌐 Custom domain + DNS | `brain.<sai-domain>.com` instead of `*.run.app` |
| 🔒 Free TLS/SSL | HTTPS for the floor UI + WhatsApp webhook (Twilio requires https) |
| 🛡️ Proxy/hiding origin | Hides Cloud Run URL, DDoS protection, bot filtering |
| ⚡ Caching | Static floor assets (`/assets/*`) cached at edge = instant loads in India |
| 🔁 WebSocket support | Enabled by default on proxy — required for `/ws/agent-status` live floor |

### Tasks:
- 2.4a: Add site to Cloudflare (free plan), point nameservers (if registering domain) or add CNAME `brain → <run-url>`.
- 2.4b: Enable proxy (orange cloud), SSL mode "Full", verify WebSockets work through proxy (`wss://brain.…/ws/agent-status` connects).
- 2.4c: Cache rule: cache `/assets/*` 1 day; bypass cache for `/api/*`, `/teams/*`, `/ws/*`.
- 2.4d: Point Twilio WhatsApp webhook at `https://brain.<domain>/webhook/whatsapp`.

---

## Phase 4 — UI/design iteration loop (post-deploy)

Once running publicly, iterate on design without redeploying logic:
- Floor visuals: richer walk cycles, desk art, theme variants (tokens all live in `office-floor-widget/src/floor/tokens.js`)
- Layout experiments: `stations.js` positions are data-driven — safe to tweak per feedback
- Each change: edit → `npm run build` → rebuild image → `gcloud run deploy` (or set up GitHub Actions auto-deploy on push to `semi-final` — optional Task 4.x)

---

## Risks / tradeoffs / open questions

1. **Gemini free-tier quota (20/day)** is the dev-loop killer → strongly recommend Groq key +/or second project key before Phase 0.
2. **Cloud Run + Postgres**: pgvector must come from managed DB (Neon free tier recommended); local compose keeps its own container.
3. **WebSockets behind Cloudflare**: supported, but verify `wss://` early (Task 2.4b) — fallback is polling `/snapshot` every 2s (degrades UX slightly).
4. **Secrets in repo**: none ever; use Cloud Run env/secrets.
5. **Open question for Sai**: do you have a domain name yet? (Needed for Cloudflare custom-domain step; can proceed with `*.run.app` until then.)

## Suggested order now
Phase 1 tests (no quota needed) → Task 2.1–2.3 deploy prep → Phase 0 live verify when key available → deploy → Cloudflare.
