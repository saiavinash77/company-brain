import asyncio
import json
import logging
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
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
    """Broadcast live agent activity events to connected floor views."""
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


@webhook_app.get("/api/clients")
async def list_clients():
    """List all active client agents and their IDs."""
    conversion = get_lead_conversion(team)
    clients = conversion.list_client_agents()
    return {
        "clients": [
            {"client_id": cid, "agent_name": agent.name}
            for cid, agent in clients.items()
        ]
    }


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
    from agno.vectordb.pgvector import PgVector
    from agno.os import AgentOS as AgnoAgentOS  # alias: plain "os" would shadow the os module

    logger.info("Initializing Company Brain...")

    # Build storage
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://scout:scout@localhost:5432/companybrain",
    )
    db = PostgresDb(db_url=db_url)

    # Build knowledge base (uses PgVector for semantic search)
    knowledge = Knowledge(
        vector_db=PgVector(
            table_name="company_brain_knowledge",
            db_url=db_url,
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

    # Start AgentOS (this blocks and serves the API + web UI)
    agent_os = AgnoAgentOS(
        name="company-brain",
        teams=[team],
        db=db,
    )

    # Mount the WhatsApp webhook routes onto AgentOS's FastAPI app,
    # so a single port serves both the UI/API and the webhook.
    agent_os_app = agent_os.get_app()
    for route in webhook_app.routes:
        if hasattr(route, "methods") and any(
            agent_os_app.routes and getattr(r, "path", None) == route.path
            for r in agent_os_app.routes
        ):
            continue  # avoid duplicate paths (e.g. /health)
        agent_os_app.router.routes.append(route)
    logger.info("WhatsApp webhook mounted at /webhook/whatsapp on the AgentOS app")

    # Serve the office-floor wrapper UI (iframes the AgentOS UI + live floor
    # overlay) from the same port, when the widget has been built.
    _mount_floor_ui(agent_os_app)

    logger.info(f"Company Brain starting on {AGENTOS_HOST}:{AGENTOS_PORT}")
    logger.info("AgentOS Web UI will be available at http://localhost:8000")
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
    """Serve office-floor-widget/dist at /floor (wrapper page + floor overlay).

    The wrapper page iframes the AgentOS UI and adds the Office Floor button;
    the widget itself talks to /ws/agent-status + /api/agent-status/snapshot.
    """
    dist = Path(__file__).resolve().parent.parent / "office-floor-widget" / "dist"
    if (dist / "index.html").exists():
        app.mount("/floor", StaticFiles(directory=str(dist), html=True), name="floor")
        logger.info("Office floor UI mounted at /floor (from %s)", dist)
    else:
        logger.warning(
            "Office floor UI not built — run: cd office-floor-widget && npm install && npm run build"
        )


if __name__ == "__main__":
    serve()
