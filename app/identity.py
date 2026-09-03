"""Who is talking to Company Brain.

The company has three named people — Sai, Bruhadish and Sravani — and the
agents must know who is asking so answers can be personal and each person's
chats stay in their own space. Identity is chosen in the UI with a slash
command (/Sai, /Bruhadish, /Sravani) and sent to the server on every team run
via the ``user_id`` form field.

Everything still lives in ONE Postgres/AgentOS store (the team can read
across everyone's history when needed) — separation is by session-id prefix,
not by separate databases.

Optional: extend KNOWN_PEOPLE with more owners later; the slash command is
just the registry key, lowercased.
"""

from __future__ import annotations

import re

# Canonical registry: slash key -> display profile.
# Add more people here; the UI picks the list up from /api/people.
KNOWN_PEOPLE: dict[str, dict] = {
    "sai": {
        "display": "Sai",
        "slash": "/Sai",
        "role": "Owner — final decision maker on pricing, contracts and spend",
    },
    "bruhadish": {
        "display": "Bruhadish",
        "slash": "/Bruhadish",
        "role": "Co-owner — operations, delivery and client relationships",
    },
    "sravani": {
        "display": "Sravani",
        "slash": "/Sravani",
        "role": "Co-owner — finance, planning and internal coordination",
    },
}

# Sessions are scoped the NATIVE Agno way: the UI sends user_id="sai" on every
# team run (stored on the TeamSession row) and lists sessions with
# GET /sessions?user_id=sai — each person sees only their chats. All sessions
# still share ONE Postgres database, so the team's tools (retrieve_memory,
# knowledge search) can read across everyone's history when a run needs it.
SLASH_RE = re.compile(r"^\s*/(sai|bruhadish|sravani)\b", re.IGNORECASE)


def normalize_person(raw: str | None) -> str | None:
    """Form value -> registry key ('sai', 'bruhadish', 'sravani') or None."""
    if not raw:
        return None
    key = raw.strip().lower().lstrip("/")
    return key if key in KNOWN_PEOPLE else None


def person_session_prefix(person: str | None) -> str:
    """Legacy helper — session ids for a person carry their prefix (sai-…).
    Kept for pre-user_id sessions; new runs are scoped by user_id instead."""
    key = normalize_person(person)
    return f"{key}-" if key else "web-"


def person_display(person: str | None) -> str:
    key = normalize_person(person)
    return KNOWN_PEOPLE[key]["display"] if key else ""


def speaker_tag(person: str | None) -> str:
    """Prefix injected before the message so the team knows who is asking."""
    key = normalize_person(person)
    if not key:
        return ""
    p = KNOWN_PEOPLE[key]
    return f"[{p['display']} is asking — {p['role']}]\n"


def strip_slash_command(text: str) -> str:
    """Remove a leading /Sai-style command from the message body."""
    return SLASH_RE.sub("", text, count=1).strip() if text else text


def people_payload() -> list[dict]:
    """Registry for the UI: slash command + display name + role blurb."""
    return [
        {
            "id": key,
            "display": p["display"],
            "slash": p["slash"],
            "role": p["role"],
        }
        for key, p in KNOWN_PEOPLE.items()
    ]


# ---------------------------------------------------------------------------
# Clients — work folders.
#
# A client is a lightweight label, not a separate database: its chats are
# ordinary team sessions whose session_id starts with "client/<slug>/", and
# everyone can still chat outside any folder ("general" space). The registry
# below is the folder list shown in the UI; it persists as a small JSON file
# in data/ so it survives restarts without a schema change.
# ---------------------------------------------------------------------------

import json
import threading
from pathlib import Path

from app.config import DATA_DIR

CLIENTS_FILE = DATA_DIR / "clients.json"
_client_lock = threading.Lock()

CLIENT_SESSION_PREFIX = "client/"  # session ids: client/<slug>/<person>-<rand>
CLIENT_SLASH_RE = re.compile(r"^\s*/client\s+([\w .&-]+)\s*$", re.IGNORECASE)


def slugify_client(name: str) -> str:
    """'Cake Magic Bakery!' -> 'cake-magic-bakery' (URL/session safe)."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return slug[:60]


def _load_clients() -> dict:
    try:
        raw = json.loads(CLIENTS_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
    except Exception:
        pass
    return {}


def _save_clients(clients: dict) -> None:
    CLIENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CLIENTS_FILE.write_text(json.dumps(clients, indent=2), encoding="utf-8")


def list_clients() -> list[dict]:
    """All client folders, newest first."""
    with _client_lock:
        clients = _load_clients()
    out = [
        {"id": slug, "name": meta.get("name", slug), "created_at": meta.get("created_at", "")}
        for slug, meta in clients.items()
    ]
    out.sort(key=lambda c: c["created_at"], reverse=True)
    return out


def register_client(name: str) -> dict:
    """Create (or fetch) a client folder. Idempotent by slug."""
    slug = slugify_client(name)
    if not slug:
        raise ValueError("client name is empty")
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    with _client_lock:
        clients = _load_clients()
        if slug not in clients:
            clients[slug] = {"name": name.strip(), "created_at": now}
            _save_clients(clients)
        meta = clients[slug]
    return {"id": slug, "name": meta.get("name", slug), "created_at": meta.get("created_at", now)}


def client_session_prefix(slug: str) -> str:
    """Session-id prefix for one client folder."""
    return f"{CLIENT_SESSION_PREFIX}{slugify_client(slug)}/"


def parse_client_slash(text: str) -> str | None:
    """/client cake magic -> 'cake magic' (name), else None."""
    m = CLIENT_SLASH_RE.match(text or "")
    return m.group(1).strip() if m else None
