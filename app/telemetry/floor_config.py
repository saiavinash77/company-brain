"""Fixed floor plan: the 11 Company Brain agents as permanent avatar identities.

One dict — the frontend never hardcodes agents. Desk coordinates are world
pixels on a 960x560 canvas (integers per DESIGN.md pixel-snapping rule).
Top Agent sits centrally; specialists arc around him.

Accent colors come from the munder-difflin design system (DESIGN.md):
brand maroon #6E1423 + gold #F4D35E for the Top Agent, then the agent-accent
palette (coral/mint/sky/lemon/lilac/peach) rotated across specialists.
"""

TOP_ACCENT = "#6E1423"      # brand maroon — the Chief of Staff
TOP_GOLD = "#F4D35E"        # gold — highlights / CTA

# The Boss sits DEAD CENTER — the hub all work flows through.
BOSS_CABIN = {"x": 480, "y": 280}

# The conference table just below center where the Chief gathers specialists.
CONFERENCE_TABLE = {"x": 480, "y": 380}

# Only the 6 agents that actually do work right now. Top Agent is center;
# the other 5 arc around him left-to-right.
AGENT_FLOOR_MAP: list[dict] = [
    {
        "agent_id": "top_agent",
        "name": "Top Agent",
        "role": "Chief of Staff — routes every task",
        "accent": TOP_ACCENT,
        "accent_alt": TOP_GOLD,
        "desk": BOSS_CABIN,
        "center": True,
    },
    # Client-facing wing (left)
    {
        "agent_id": "sales_agent",
        "name": "Sales Agent",
        "role": "lead qualification & scoring",
        "accent": "#6BCF7F",
        "accent_alt": "#B4E5BD",
        "desk": {"x": 180, "y": 200},
    },
    {
        "agent_id": "onboarding_agent",
        "name": "Onboarding Agent",
        "role": "new client setup",
        "accent": "#FF6B6B",
        "accent_alt": "#FFB4B4",
        "desk": {"x": 180, "y": 410},
    },
    # Client agent (dynamic) anchor point
    {
        "agent_id": "client_agent",
        "name": "Client Agent",
        "role": "per-client dedicated agent",
        "accent": "#4ECDC4",
        "accent_alt": "#A8E6E0",
        "desk": {"x": 300, "y": 500},
    },
    # Deals wing (right)
    {
        "agent_id": "negotiation_agent",
        "name": "Negotiation Agent",
        "role": "pricing & deal structuring",
        "accent": "#FFD93D",
        "accent_alt": "#FFEC99",
        "desk": {"x": 780, "y": 200},
    },
    {
        "agent_id": "finance_agent",
        "name": "Finance Agent",
        "role": "invoices & payments",
        "accent": "#B197FC",
        "accent_alt": "#D6C5FF",
        "desk": {"x": 780, "y": 410},
    },
]

FLOOR_META = {
    "name": "Company Brain HQ",
    "width": 960,
    "height": 560,
}


def fixed_agents() -> list[dict]:
    """Snapshot-ready copies of the fixed desk map."""
    return [dict(entry) for entry in AGENT_FLOOR_MAP]
