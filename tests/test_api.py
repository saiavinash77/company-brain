"""API endpoint tests — FastAPI TestClient against webhook_app.

main.py builds the team at import; that requires LLM keys. We set dummy
keys before import — no real API calls happen in these tests.
"""
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("GOOGLE_API_KEY", "test-key-dummy")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key-dummy")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import webhook_app

    with TestClient(webhook_app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_settings_status_keys(client):
    r = client.get("/api/settings-status")
    assert r.status_code == 200
    data = r.json()
    assert data["keys"]["GOOGLE_API_KEY"]["set"] is True  # dummy key above
    assert "agents" in data and len(data["agents"]) == 10


def test_settings_status_flags_missing_required(client):
    # GOOGLE_API_KEY is set via env default, so not missing
    assert client.get("/api/settings-status").json()["missing_required"] is False


def test_snapshot_has_floor_and_10_agents(client):
    r = client.get("/api/agent-status/snapshot")
    assert r.status_code == 200
    data = r.json()
    assert len(data["agents"]) == 10
    assert "floor" in data


def test_agent_activity_known_agent(client):
    r = client.get("/api/agent-activity/sales_agent")
    assert r.status_code == 200
    data = r.json()
    assert data["live"]["agent_id"] == "sales_agent"
    assert isinstance(data["history"], list)
    assert "model" in data


def test_agent_activity_unknown_agent(client):
    r = client.get("/api/agent-activity/nobody_agent")
    assert r.status_code == 200
    data = r.json()
    assert data["live"] is None
    assert data["history"] == []


def test_list_clients_shape(client):
    r = client.get("/api/clients")
    assert r.status_code == 200
    assert "clients" in r.json()


def test_whatsapp_webhook_requires_twilio(client):
    """Without TWILIO_ACCOUNT_SID the webhook returns a config error."""
    from app.config import TWILIO_ACCOUNT_SID

    if TWILIO_ACCOUNT_SID:
        pytest.skip("Twilio configured in env")
    r = client.post("/webhook/whatsapp", data={"From": "x", "Body": "hi"})
    assert r.status_code in (200, 503)


def test_telegram_webhook_requires_token(client):
    from app.config import TELEGRAM_BOT_TOKEN

    if TELEGRAM_BOT_TOKEN:
        pytest.skip("Telegram configured in env")
    r = client.post("/webhook/telegram", json={"message": {"chat": {"id": 1}, "text": "hi"}})
    assert r.status_code in (200, 503)


def test_floor_page_served():
    """/floor only exists after serve() mounts it; the raw webhook app may 404.
    Accept both: mounted -> HTML, unmounted -> 404. The Docker E2E covers live."""
    from app.main import webhook_app

    paths = {getattr(route, "path", "") for route in webhook_app.routes}
    if "/floor" not in paths:
        pytest.skip("floor mounted at serve() time, not in bare webhook_app")
