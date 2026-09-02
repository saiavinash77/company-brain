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
