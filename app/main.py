import asyncio
import json
import logging
import os

import uvicorn
from fastapi import FastAPI, Request

from app.config import (
    AGENTOS_HOST,
    AGENTOS_PORT,
    TELYNX_API_KEY,
    TELNYX_NUMBER,
    OWNER_NUMBER,
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


# FastAPI app for webhook endpoints
webhook_app = FastAPI(title="Company Brain Webhooks")

# Build the team (stores references for webhook access)
memory = SuperMemory()
team = build_company_brain_team(memory)
top_agent = get_top_agent(team)


@webhook_app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "company-brain"}


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
    """Receive incoming WhatsApp messages from Telnyx and route to Top Agent."""
    if not TELYNX_API_KEY:
        return {"error": "Telnyx not configured"}, 503

    try:
        payload = await request.json()
        logger.info(f"Received WhatsApp webhook: {json.dumps(payload, default=str)[:500]}")

        # Extract message text from Telnyx payload
        data = payload.get("data", {})
        payload_inner = data.get("payload", {})
        text = payload_inner.get("text", "")

        # Also check for media content
        media = payload_inner.get("media", [])

        if not text and not media:
            logger.warning("No text or media in WhatsApp message")
            return {"status": "ignored", "reason": "empty message"}

        # Build the message for the Top Agent
        message_parts = ["[WhatsApp Message from Owner]"]
        if text:
            message_parts.append(text)
        if media:
            for m in media:
                message_parts.append(f"[Media: {m.get('content_type', 'unknown')}]")

        full_message = "\n".join(message_parts)

        # Run the Top Agent asynchronously
        asyncio.create_task(_process_whatsapp_message(full_message))

        # Telnyx expects a quick response
        return {"status": "received", "message": "Processing..."}

    except Exception as e:
        logger.error(f"WhatsApp webhook error: {e}")
        return {"status": "error", "message": str(e)}, 500


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
    from app.teams.company_brain_team import get_lead_conversion

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

    # Start AgentOS (this blocks and serves the API + web UI)
    os = AgentOS(
        name="company-brain",
        agents=[team],
        db=db,
    )

    logger.info(f"Company Brain starting on {AGENTOS_HOST}:{AGENTOS_PORT}")
    logger.info("AgentOS Web UI will be available at http://localhost:8000")
    logger.info(f"Active agents: {[m.name for m in team.members]}")

    os.serve()

    # NOTE: AgentOS serves its own FastAPI app internally.
    # For the WhatsApp webhook, run the webhook_app separately:
    #   uvicorn app.main:webhook_app --host 0.0.0.0 --port 8001
    # Or integrate the webhook routes into AgentOS's FastAPI app (advanced).


def serve_webhook_only():
    """Start only the webhook server (for development/testing)."""
    logger.info(f"Starting webhook server on {AGENTOS_HOST}:{AGENTOS_PORT}")
    uvicorn.run(webhook_app, host=AGENTOS_HOST, port=AGENTOS_PORT)


if __name__ == "__main__":
    serve()
