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

# The Boss's cabin: Top Agent sits here, apart from the crew.
BOSS_CABIN = {"x": 480, "y": 60}

# The conference table where the Chief gathers specialists for delegation.
CONFERENCE_TABLE = {"x": 480, "y": 330}

AGENT_FLOOR_MAP: list[dict] = [
    {
        "agent_id": "top_agent",
        "name": "Top Agent",
        "role": "Chief of Staff",
        "accent": TOP_ACCENT,
        "accent_alt": TOP_GOLD,
        "desk": BOSS_CABIN,
    },
    # Upper arc (research & thinking wing)
    {
        "agent_id": "idea_agent",
        "name": "Idea Agent",
        "role": "captures raw ideas",
        "accent": "#FF6B6B",
        "accent_alt": "#FFB4B4",
        "desk": {"x": 210, "y": 170},
    },
    {
        "agent_id": "market_research_agent",
        "name": "Market Research Agent",
        "role": "competitor & trend research",
        "accent": "#4ECDC4",
        "accent_alt": "#A8E6E0",
        "desk": {"x": 345, "y": 105},
    },
    {
        "agent_id": "briefing_agent",
        "name": "Briefing Agent",
        "role": "daily & weekly briefings",
        "accent": "#B197FC",
        "accent_alt": "#D6C5FF",
        "desk": {"x": 480, "y": 80},
    },
    {
        "agent_id": "strategy_agent",
        "name": "Strategy Agent",
        "role": "campaigns & roadmaps",
        "accent": "#FFA07A",
        "accent_alt": "#FFD0B5",
        "desk": {"x": 615, "y": 105},
    },
    {
        "agent_id": "refinement_agent",
        "name": "Refinement Agent",
        "role": "polishes ideas into briefs",
        "accent": "#FFD93D",
        "accent_alt": "#FFEC99",
        "desk": {"x": 750, "y": 170},
    },
    # Lower arc (client-facing wing)
    {
        "agent_id": "sales_agent",
        "name": "Sales Agent",
        "role": "lead qualification",
        "accent": "#6BCF7F",
        "accent_alt": "#B4E5BD",
        "desk": {"x": 240, "y": 390},
    },
    {
        "agent_id": "onboarding_agent",
        "name": "Onboarding Agent",
        "role": "new client setup",
        "accent": "#FF6B6B",
        "accent_alt": "#FFB4B4",
        "desk": {"x": 365, "y": 455},
    },
    {
        "agent_id": "negotiation_agent",
        "name": "Negotiation Agent",
        "role": "pricing & deal structuring",
        "accent": "#4ECDC4",
        "accent_alt": "#A8E6E0",
        "desk": {"x": 480, "y": 485},
    },
    {
        "agent_id": "finance_agent",
        "name": "Finance Agent",
        "role": "invoices & payments",
        "accent": "#FFD93D",
        "accent_alt": "#FFEC99",
        "desk": {"x": 595, "y": 455},
    },
    {
        "agent_id": "legal_agent",
        "name": "Legal Agent",
        "role": "contract review & risk",
        "accent": "#B197FC",
        "accent_alt": "#D6C5FF",
        "desk": {"x": 720, "y": 390},
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
