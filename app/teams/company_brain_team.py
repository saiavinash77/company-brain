from agno.agent import Agent
from agno.team import Team, TeamMode

from app.agents.sales_agent import create_sales_agent
from app.agents.top_agent import create_top_agent
from app.memory.super_memory import SuperMemory
from app.providers.memory_provider import MemoryProvider
from app.providers.telnyx_provider import TelnyxProvider
from app.providers.web_provider import WebProvider


def build_company_brain_team(memory: SuperMemory) -> Team:
    """Build the top-level Company Brain team.

    Week 1: Top Agent + Sales Agent
    The team uses coordinate mode — the Top Agent evaluates requests
    and delegates to the appropriate specialist.
    """
    # Create agents
    top_agent = create_top_agent()
    sales_agent = create_sales_agent()

    # Create providers and wire them into agents
    telnyx_provider = TelnyxProvider()
    web_provider = WebProvider()
    memory_provider = MemoryProvider(memory=memory)

    # Wire tools into Top Agent
    top_agent.tools.extend(telnyx_provider.get_tools())
    top_agent.tools.extend(memory_provider.get_tools())
    top_agent.instructions.extend([telnyx_provider.get_instructions(), memory_provider.get_instructions()])

    # Wire tools into Sales Agent
    sales_agent.tools.extend(web_provider.get_tools())
    sales_agent.tools.extend(memory_provider.get_tools())
    sales_agent.instructions.extend([web_provider.get_instructions(), memory_provider.get_instructions()])

    # Build the team
    team = Team(
        name="Company Brain",
        mode=TeamMode.coordinate,
        members=[top_agent, sales_agent],
        instructions=[
            "This is the Company Brain team. The Top Agent (Chief of Staff) coordinates all work.",
            "When a request comes in, the Top Agent decides whether to handle it directly or delegate.",
        ],
        markdown=True,
    )

    # Store references for webhook access
    team._top_agent = top_agent
    team._sales_agent = sales_agent

    return team


def get_top_agent(team: Team) -> Agent:
    """Get the Top Agent from the team for webhook routing."""
    return team._top_agent
