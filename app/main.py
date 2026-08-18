import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)

from app.config import (
    AGENTOS_HOST,
    AGENTOS_PORT,
    OWNER_NUMBER,
    TWILIO_ACCOUNT_SID,
)
from app.memory.super_memory import SuperMemory
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


# FastAPI app for Company Brain routes. AgentOS mounts its own API and UI
# onto this app during startup.
webhook_app = FastAPI(title="Company Brain")
FLOOR_PAGE = Path(__file__).parent / "static" / "floor.html"
application = None

# Build the team (stores references for webhook access)
memory = SuperMemory()
team = build_company_brain_team(memory)
top_agent = get_top_agent(team)


@webhook_app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "company-brain"}


@webhook_app.get("/floor", response_class=HTMLResponse)
async def agent_floor():
    """Serve the visual Agent Floor presentation layer."""
    return FileResponse(FLOOR_PAGE, media_type="text/html")


def _slug(value: str) -> str:
    return "-".join(value.lower().split())


def _floor_state() -> dict:
    """Return a read-only snapshot for the Agent Floor UI.

    AgentOS remains the execution source of truth. This endpoint only exposes
    presentation metadata and the dynamically spawned client roster.
    """
    agents = []
    for member in team.members:
        name = str(getattr(member, "name", "Agent"))
        agents.append(
            {
                "id": str(getattr(member, "id", None) or _slug(name)),
                "name": name,
                "role": str(getattr(member, "role", "Company Brain specialist")),
                "status": "ready",
            }
        )

    conversion = get_lead_conversion(team)
    clients = [
        {
            "id": client_id,
            "name": str(getattr(agent, "name", client_id)),
            "status": "active",
        }
        for client_id, agent in conversion.list_client_agents().items()
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agents": agents,
        "clients": clients,
        "workflows": [
            "lead-conversion",
            "pricing-request",
            "daily-briefing",
        ],
    }


@webhook_app.get("/api/floor/state")
async def floor_state():
    """Return the current Company Brain roster for external visual clients."""
    return _floor_state()


async def _floor_event_stream(request: Request):
    """Send periodic snapshots until the browser disconnects."""
    while not await request.is_disconnected():
        yield f"event: floor_state\ndata: {json.dumps(_floor_state())}\n\n"
        await asyncio.sleep(5)


@webhook_app.get("/api/floor/events")
async def floor_events(request: Request):
    """Stream floor snapshots to browser clients over Server-Sent Events."""
    return StreamingResponse(
        _floor_event_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
        return JSONResponse({"error": "Twilio not configured"}, status_code=503)

    try:
        form = await request.form()
        logger.info(f"Received Twilio webhook from {form.get('From', 'unknown')}")

        # Validate sender is the owner
        sender = form.get("From", "")
        if OWNER_NUMBER and OWNER_NUMBER not in sender:
            logger.warning(f"Message from unknown sender: {sender}, ignoring")
            # Return empty TwiML to acknowledge without responding
            return Response(content=_empty_twiml(), media_type="application/xml")

        # Extract message text
        text = form.get("Body", "")
        num_media = int(form.get("NumMedia", 0))

        if not text and num_media == 0:
            logger.warning("Empty WhatsApp message received")
            return Response(content=_empty_twiml(), media_type="application/xml")

        # Build the message for the Top Agent
        message_parts = ["[WhatsApp Message from Owner]"]
        if text:
            message_parts.append(text)
        if num_media > 0:
            for i in range(num_media):
                media_type = form.get(f"MediaContentType{i}", "unknown")
                message_parts.append(f"[Media: {media_type}]")

        full_message = "\n".join(message_parts)

        # Run the Top Agent asynchronously (Twilio expects a fast response)
        asyncio.create_task(_process_whatsapp_message(full_message))

        # Return empty TwiML to acknowledge receipt
        return Response(content=_empty_twiml(), media_type="application/xml")

    except Exception as e:
        logger.error(f"WhatsApp webhook error: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


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
    from agno.os import AgentOS

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

    # Mount AgentOS onto the existing FastAPI app so its UI/API and the
    # Company Brain routes share one server and one origin.
    agent_os = AgentOS(
        id="company-brain",
        name="Company Brain",
        description="Business operations team with visual Agent Floor support.",
        agents=list(team.members),
        teams=[team],
        db=db,
        base_app=webhook_app,
        on_route_conflict="preserve_base_app",
        cors_allowed_origins=[
            "http://localhost:3000",
            "http://localhost:3001",
            f"http://localhost:{AGENTOS_PORT}",
        ],
        tracing=True,
    )

    global application
    application = agent_os.get_app()

    logger.info(f"Company Brain starting on {AGENTOS_HOST}:{AGENTOS_PORT}")
    logger.info("AgentOS API will be available at http://localhost:8000")
    logger.info("Agent UI will be available at http://localhost:3000")
    logger.info("Agent Floor will be available at http://localhost:8000/floor")
    logger.info(f"Active agents: {[m.name for m in team.members]}")

    agent_os.serve(application, host=AGENTOS_HOST, port=AGENTOS_PORT)


def serve_webhook_only():
    """Start only the webhook server (for development/testing)."""
    logger.info(f"Starting webhook server on {AGENTOS_HOST}:{AGENTOS_PORT}")
    uvicorn.run(webhook_app, host=AGENTOS_HOST, port=AGENTOS_PORT)


if __name__ == "__main__":
    serve()
