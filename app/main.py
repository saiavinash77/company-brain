import asyncio
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path

import aiohttp
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import (
    AGENTOS_HOST,
    AGENTOS_PORT,
    OWNER_NUMBER,
    TWILIO_ACCOUNT_SID,
)
from app.memory.super_memory import SuperMemory
from app.telemetry.agent_events import bus
from app.telemetry.floor_config import FLOOR_META, fixed_agents
from app.teams.company_brain_team import (
    build_company_brain_team,
    get_lead_conversion,
    get_top_agent,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("company-brain")


# FastAPI app for webhook endpoints
webhook_app = FastAPI(title="Company Brain Webhooks")


# ---- Passcode gate (production access control) ---------------------------
# When APP_PASSCODE is set, every browser request needs a valid gate cookie
# (issued after entering the passcode). Machine traffic stays open: /health
# for uptime checks, /webhook/* for Twilio, and anything when no passcode
# is configured (local dev stays open exactly as before).

GATE_COOKIE = "cb_gate"
GATE_COOKIE_MAX_AGE = 30 * 24 * 3600  # 30 days
# Paths machines hit directly — never gated. /gate/ carries the login form
# itself (the endpoint validates the passcode), so it must stay reachable.
GATE_EXEMPT_PREFIXES = ("/health", "/webhook/", "/gate/", "/docs", "/openapi.json", "/redoc")

APP_PASSCODE = os.environ.get("APP_PASSCODE", "")


def _gate_secret() -> bytes:
    """HMAC key for cookie signing: derived from the passcode itself so no
    extra secret is needed; changing the passcode invalidates old cookies."""
    return hashlib.sha256(("cb-gate:" + APP_PASSCODE).encode()).digest()


def _gate_token() -> str:
    return hmac.new(_gate_secret(), b"authorized", hashlib.sha256).hexdigest()


def _cookie_ok(request: Request) -> bool:
    token = request.cookies.get(GATE_COOKIE, "")
    return bool(token) and hmac.compare_digest(token, _gate_token())


_GATE_PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Company Brain</title>
<style>
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #f7f8fc;
         display: flex; align-items: center; justify-content: center;
         min-height: 100vh; margin: 0; color: #1d2130; }}
  .card {{ background: #fff; border: 1px solid #e5e8f0; border-radius: 16px;
          padding: 34px 30px; width: 320px; text-align: center;
          box-shadow: 0 18px 44px rgba(29,33,48,.12); }}
  img {{ width: 56px; height: 56px; border-radius: 14px; }}
  h1 {{ font-size: 19px; margin: 14px 0 4px; }}
  p {{ font-size: 13.5px; color: #6b7280; margin: 0 0 20px; }}
  input {{ width: 100%; box-sizing: border-box; padding: 11px 13px;
          border: 1.5px solid #dfe3ee; border-radius: 10px; font-size: 15px;
          text-align: center; letter-spacing: 2px; outline: none; }}
  input:focus {{ border-color: #647cf8; box-shadow: 0 0 0 3px rgba(100,124,248,.12); }}
  button {{ margin-top: 14px; width: 100%; padding: 11px; border: 0;
           border-radius: 10px; background: #647cf8; color: #fff;
           font-size: 15px; font-weight: 600; cursor: pointer; }}
  .err {{ color: #b3261e; font-size: 12.5px; margin-top: 10px; }}
</style></head><body>
<div class="card">
  <img src="/floor/logo.png" alt="">
  <h1>Company Brain</h1>
  <p>Enter your passcode to open your workspace.</p>
  <form method="post" action="/gate/login">
    <input type="password" name="passcode" placeholder="passcode" autofocus required>
    <button type="submit">Enter</button>
  </form>
  {err}
</div>
</body></html>"""


@webhook_app.get("/gate/login", include_in_schema=False)
async def gate_page():
    return HTMLResponse(_GATE_PAGE.format(err=""))


@webhook_app.post("/gate/login", include_in_schema=False)
async def gate_login(request: Request):
    form = await request.form()
    supplied = str(form.get("passcode", ""))
    if supplied and hmac.compare_digest(supplied, APP_PASSCODE):
        resp = HTMLResponse(
            '<!doctype html><meta http-equiv="refresh" content="0;url=/">'
        )
        resp.set_cookie(
            GATE_COOKIE,
            _gate_token(),
            max_age=GATE_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=os.environ.get("GATE_SECURE_COOKIE", "").lower() in ("1", "true", "yes"),
        )
        return resp
    return HTMLResponse(_GATE_PAGE.format(err='<div class="err">Wrong passcode — try again.</div>'), status_code=401)


@webhook_app.middleware("http")
async def passcode_gate(request: Request, call_next):
    """Gate all browser traffic when APP_PASSCODE is configured; leave the
    app fully open when it isn't (local dev). Websockets are gated inside
    their handlers (starlette's ws middleware call_next is incompatible)."""
    if not APP_PASSCODE:
        return await call_next(request)
    path = request.url.path
    if path.startswith(GATE_EXEMPT_PREFIXES):
        return await call_next(request)
    if _cookie_ok(request):
        return await call_next(request)
    return HTMLResponse(_GATE_PAGE.format(err=""), status_code=401)


def _cookie_ok_ws(websocket: WebSocket) -> bool:
    token = websocket.cookies.get(GATE_COOKIE, "")
    return bool(token) and hmac.compare_digest(token, _gate_token())


# Build the team (stores references for webhook access)
memory = SuperMemory()
team = build_company_brain_team(memory)
top_agent = get_top_agent(team)


@webhook_app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "company-brain"}


# ---- Office-floor live status (Task: Agent Activity Floor) ----

@webhook_app.get("/api/agent-status/snapshot")
async def agent_status_snapshot():
    """Initial floor state for page load: all fixed desks + live states."""
    payload = bus.snapshot(fixed_agents())
    payload["floor"] = FLOOR_META
    return payload


@webhook_app.websocket("/ws/agent-status")
async def ws_agent_status(websocket: WebSocket):
    """Broadcast live agent activity events to connected floor views.
    Passcode-gated when APP_PASSCODE is set (cookies ride the ws
    handshake, so the check is the same as the HTTP gate)."""
    if APP_PASSCODE and not _cookie_ok_ws(websocket):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    queue = bus.subscribe()
    try:
        # Initial state on connect, then live events.
        payload = bus.snapshot(fixed_agents())
        payload["floor"] = FLOOR_META
        payload["kind"] = "snapshot"
        await websocket.send_json(payload)
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"agent-status websocket closed: {e}")
    finally:
        bus.unsubscribe(queue)


@webhook_app.get("/api/agent-activity/{agent_id}")
async def agent_activity(agent_id: str, limit: int = 15):
    """Recent activity for one agent — live state + durable audit history."""
    from app.config import GROQ_API_KEY, GOOGLE_API_KEY, MISTRAL_API_KEY

    payload = bus.snapshot(fixed_agents())
    live = next(
        (a for a in payload.get("agents", []) if a.get("agent_id") == agent_id), None
    )
    # durable audit trail (SuperMemory audit layer)
    try:
        history = await memory.audit.get_agent_history(agent_id, limit=limit)
    except Exception as e:
        logger.warning(f"audit history unavailable: {e}")
        history = []
    return {
        "live": live,
        "history": history,
        "model": _agent_model(agent_id),
    }


def _agent_model(agent_id: str) -> str:
    from app.config import GROQ_API_KEY

    # Every agent rides Groq's gpt-oss-120b now — free-tier Gemini was
    # taking 20-50s per call and Mistral ~70s; Groq answers in ~1s.
    # Gemini remains the coded fallback in get_groq_llama().
    return "groq/gpt-oss-120b" if GROQ_API_KEY else "gemini (fallback)"


@webhook_app.get("/api/settings-status")
async def settings_status():
    """Simple settings/readiness page data — which keys are set, model map."""
    import os as _os

    from app.config import (
        DATABASE_URL, GMAIL_CLIENT_ID, GOOGLE_API_KEY, GROQ_API_KEY,
        MISTRAL_API_KEY, TWILIO_ACCOUNT_SID,
    )

    def _set(v: str) -> bool:
        return bool(v and v.strip())

    keys = {
        "GOOGLE_API_KEY": {"set": _set(GOOGLE_API_KEY), "label": "Google Gemini (required)"},
        "GROQ_API_KEY": {"set": _set(GROQ_API_KEY), "label": "Groq — powers all agents (fast inference)"},
        "MISTRAL_API_KEY": {"set": _set(MISTRAL_API_KEY), "label": "Mistral (currently unused — agents moved to Groq)"},
        "TWILIO_ACCOUNT_SID": {"set": _set(TWILIO_ACCOUNT_SID), "label": "Twilio WhatsApp"},
        "GMAIL_CLIENT_ID": {"set": _set(GMAIL_CLIENT_ID), "label": "Gmail tools"},
    }
    missing_required = not _set(GOOGLE_API_KEY)
    return {
        "keys": keys,
        "missing_required": missing_required,
        "database": "postgres (docker)" if "postgres" in DATABASE_URL else "sqlite (local)",
        "agents": [
            {"agent_id": a["agent_id"], "name": a["name"], "role": a["role"],
             "model": _agent_model(a["agent_id"])}
            for a in fixed_agents()
        ],
    }


@webhook_app.get("/api/clients")
async def list_clients():
    conversion = get_lead_conversion(team)
    clients = conversion.list_client_agents()
    return {
        "clients": [
            {"client_id": cid, "agent_name": agent.name}
            for cid, agent in clients.items()
        ]
    }


@webhook_app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """Receive Telegram updates and route owner messages to the Top Agent.

    Set once via: https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<host>/webhook/telegram
    Only messages from TELEGRAM_CHAT_ID (the owner) are processed.
    """
    from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

    if not TELEGRAM_BOT_TOKEN:
        return {"error": "Telegram not configured"}, 503

    try:
        update = await request.json()
        message = update.get("message") or {}
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = (message.get("text") or "").strip()

        if not chat_id or (TELEGRAM_CHAT_ID and chat_id != str(TELEGRAM_CHAT_ID)):
            logger.warning("Telegram update from unknown chat %s — ignored", chat_id)
            return {"ok": True}
        if not text:
            return {"ok": True}

        logger.info("Telegram message from owner (%s): %s", chat_id, text[:80])

        full_message = f"[Telegram message from Owner]\n{text}"
        asyncio.create_task(_process_telegram_message(full_message, chat_id))
        return {"ok": True}
    except Exception as e:
        logger.error(f"Telegram webhook error: {e}")
        return {"ok": False, "error": str(e)}


async def _process_telegram_message(message: str, chat_id: str):
    """Run the Top Agent on a Telegram message and reply in the same chat."""
    from app.config import TELEGRAM_BOT_TOKEN

    try:
        response = await top_agent.arun(input=message)
        content = getattr(response, "content", None)
        if not content:
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        async with aiohttp.ClientSession() as session:
            await session.post(
                url,
                json={"chat_id": chat_id, "text": str(content)[:4000]},
                timeout=aiohttp.ClientTimeout(total=30),
            )
    except Exception as exc:
        logger.error(f"Telegram processing error: {exc}")


@webhook_app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    """Receive incoming WhatsApp messages from Twilio and route to Top Agent.

    Twilio sends webhook POST with form data:
    - From: whatsapp:+1xxxxxxxxxx (sender)
    - To: whatsapp:+1xxxxxxxxxx (your Twilio number)
    - Body: message text
    - NumMedia: count of media attachments
    - SmsSid: message SID
    """
    if not TWILIO_ACCOUNT_SID:
        return {"error": "Twilio not configured"}, 503

    try:
        form = await request.form()
        logger.info(f"Received Twilio webhook from {form.get('From', 'unknown')}")

        # Validate sender is the owner
        sender = form.get("From", "")
        if OWNER_NUMBER and OWNER_NUMBER not in sender:
            logger.warning(f"Message from unknown sender: {sender}, ignoring")
            # Return empty TwiML to acknowledge without responding
            return _empty_twiml()

        # Extract message text
        text = form.get("Body", "")
        num_media = int(form.get("NumMedia", 0))

        if not text and num_media == 0:
            logger.warning("Empty WhatsApp message received")
            return _empty_twiml()

        # Build the message for the Top Agent
        message_parts = ["[WhatsApp Message from Owner]"]
        if text:
            message_parts.append(text)
        if num_media > 0:
            for i in range(num_media):
                media_url = form.get(f"MediaUrl{i}", "")
                media_type = form.get(f"MediaContentType{i}", "unknown")
                message_parts.append(f"[Media: {media_type}]")

        full_message = "\n".join(message_parts)

        # Run the Top Agent asynchronously (Twilio expects a fast response)
        asyncio.create_task(_process_whatsapp_message(full_message))

        # Return empty TwiML to acknowledge receipt
        return _empty_twiml()

    except Exception as e:
        logger.error(f"WhatsApp webhook error: {e}")
        return {"status": "error", "message": str(e)}, 500


def _empty_twiml() -> str:
    """Return empty TwiML response to acknowledge webhook receipt."""
    return '<Response></Response>'


async def _process_whatsapp_message(message: str):
    """Process a WhatsApp message through the Top Agent and send response back."""
    try:
        response = await top_agent.arun(input=message)
        if response and response.content:
            # The Top Agent may decide to send a WhatsApp reply
            # (it has the send_whatsapp_message tool)
            logger.info(f"Top Agent processed WhatsApp message: {str(response.content)[:200]}")
    except Exception as e:
        logger.error(f"Error processing WhatsApp message: {e}")


def _wire_knowledge_to_client_agents(team):
    """Wire shared knowledge/db into dynamically spawned client agents."""
    conversion = get_lead_conversion(team)
    for client_id, agent in conversion.list_client_agents().items():
        if hasattr(team, "knowledge") and team.knowledge and not agent.knowledge:
            agent.knowledge = team.knowledge
        if hasattr(team, "db") and team.db and not agent.db:
            agent.db = team.db
        logger.info(f"Wired knowledge/db to Client Agent: {agent.name}")


def serve():
    """Start the Company Brain via AgentOS with webhook support."""
    from agno.db.postgres import PostgresDb
    from agno.knowledge import Knowledge
    from agno.knowledge.embedder.google import GeminiEmbedder
    from agno.vectordb.pgvector import PgVector
    from agno.os import AgentOS as AgnoAgentOS  # alias: plain "os" would shadow the os module

    logger.info("Initializing Company Brain...")

    # Build storage
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://scout:scout@localhost:5432/companybrain",
    )
    db = PostgresDb(db_url=db_url)

    # Build knowledge base (uses PgVector for semantic search).
    # PgVector defaults to OpenAIEmbedder, which needs OPENAI_API_KEY we
    # don't have — point it at Gemini's embedding model instead.
    knowledge = Knowledge(
        vector_db=PgVector(
            table_name="company_brain_knowledge",
            db_url=db_url,
            embedder=GeminiEmbedder(),
        ),
    )

    # Wire knowledge into team and all members
    team.knowledge = knowledge
    team.db = db
    for member in team.members:
        member.knowledge = knowledge
        member.db = db

    # Wire knowledge into any pre-spawned client agents
    _wire_knowledge_to_client_agents(team)

    # Start AgentOS (this blocks and serves the API + web UI).
    # The WhatsApp webhook and office-floor routes live on our own FastAPI
    # app, which is handed to AgentOS as base_app: registering them BEFORE
    # AgentOS builds its route table keeps every route first-class. Appending
    # mounts after get_app() breaks fastapi>=0.141 dispatch (the /floor mount
    # was never consulted and its path fell into a self-redirect loop).
    _mount_floor_ui(webhook_app)
    agent_os = AgnoAgentOS(
        name="company-brain",
        teams=[team],
        db=db,
        base_app=webhook_app,
    )
    agent_os_app = agent_os.get_app()

    logger.info("WhatsApp webhook mounted at /webhook/whatsapp on the AgentOS app")
    logger.info(f"Company Brain starting on {AGENTOS_HOST}:{AGENTOS_PORT}")
    logger.info("Chat UI available at http://localhost:8000 (landing), http://localhost:8000/floor and http://localhost:8000/chat")
    logger.info(f"Active agents: {[m.name for m in team.members]}")

    agent_os.serve(agent_os_app, host=AGENTOS_HOST, port=AGENTOS_PORT)

    # NOTE: The WhatsApp webhook is now served by the same process/port —
    # no second uvicorn server needed.


def serve_webhook_only():
    """Start only the webhook server (for development/testing)."""
    _mount_floor_ui(webhook_app)
    logger.info(f"Starting webhook server on {AGENTOS_HOST}:{AGENTOS_PORT}")
    uvicorn.run(webhook_app, host=AGENTOS_HOST, port=AGENTOS_PORT)


def _mount_floor_ui(app) -> None:
    """Serve office-floor-widget/dist at /floor, /chat and as the "/" landing page.

    The widget page is self-sufficient: it provides the local chat panel
    (talking to POST /teams/company-brain/runs) plus the Office Floor overlay
    (talking to /ws/agent-status + /api/agent-status/snapshot). /chat opens the
    same SPA in its clean modern-chat face. AgentOS itself ships no bundled
    UI — its GET / returns a JSON API descriptor and it OVERRIDES same-path
    custom routes (observed with /health), so the landing page at "/" is
    installed via pure-ASGI middleware, which runs before routing and cannot
    be overridden.
    """
    dist = Path(__file__).resolve().parent.parent / "office-floor-widget" / "dist"
    if not (dist / "index.html").exists():
        logger.warning(
            "Office floor UI not built — run: cd office-floor-widget && npm install && npm run build"
        )
        return
    if getattr(app.state, "floor_ui_mounted", False):
        return  # serve() and serve_webhook_only() share webhook_app
    app.state.floor_ui_mounted = True

    app.mount("/floor", StaticFiles(directory=str(dist), html=True), name="floor")

    # Agno's TrailingSlashMiddleware rewrites "/floor/" -> "/floor" before
    # routing, so StaticFiles' add-slash redirect loops forever on the bare
    # mount path. Serve the wrapper page directly on "/floor" instead —
    # no redirect involved; the mount above still serves /floor/assets/*.
    from fastapi.responses import FileResponse

    @app.get("/floor", include_in_schema=False)
    async def _floor_page():
        return FileResponse(str(dist / "index.html"))

    # Clean modern chat — same SPA, opens its "chat" face (the app reads the
    # path). Assets are absolute under /floor/assets/*, so they load fine.
    @app.get("/chat", include_in_schema=False)
    async def _chat_page():
        return FileResponse(str(dist / "index.html"))

    class LandingPageMiddleware:
        """Serve the widget page at "/" ahead of routing.

        AgentOS registers its own GET "/" (JSON descriptor) and overrides
        conflicting custom routes, so a plain @app.get("/") loses. Middleware
        executes before routing and wins regardless.
        """

        def __init__(self, inner, index_html: Path):
            self.inner = inner
            self.index_html = index_html

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http" and scope.get("path") == "/":
                response = FileResponse(str(self.index_html))
                await response(scope, receive, send)
                return
            await self.inner(scope, receive, send)

    app.add_middleware(LandingPageMiddleware, index_html=dist / "index.html")

    logger.info("Office floor UI mounted at /floor and /chat, served as / landing (from %s)", dist)


if __name__ == "__main__":
    serve()
