import logging

from agno.agent import Agent
from agno.team import Team, TeamMode

from app.agents.onboarding_agent import create_onboarding_agent
from app.agents.sales_agent import create_sales_agent
from app.agents.top_agent import create_top_agent
from app.memory.super_memory import SuperMemory
from app.providers.gmail_provider import GmailProvider
from app.providers.memory_provider import MemoryProvider
from app.providers.telnyx_provider import TelnyxProvider
from app.providers.web_provider import WebProvider
from app.workflows.lead_conversion_workflow import LeadConversionWorkflow

logger = logging.getLogger("company-brain")


def build_company_brain_team(memory: SuperMemory) -> Team:
    """Build the top-level Company Brain team.

    Week 1: Top Agent + Sales Agent
    Week 2: + Onboarding Agent + Gmail Provider + Lead Conversion workflow
    The team uses coordinate mode — the Top Agent evaluates requests
    and delegates to the appropriate specialist.
    """
    # Create agents
    top_agent = create_top_agent()
    sales_agent = create_sales_agent()
    onboarding_agent = create_onboarding_agent()

    # Create providers and wire them into agents
    telnyx_provider = TelnyxProvider()
    web_provider = WebProvider()
    gmail_provider = GmailProvider()
    memory_provider = MemoryProvider(memory=memory)

    # Wire tools into Top Agent
    top_agent.tools.extend(telnyx_provider.get_tools())
    top_agent.tools.extend(memory_provider.get_tools())
    top_agent.instructions.extend([
        telnyx_provider.get_instructions(),
        memory_provider.get_instructions(),
    ])
    if gmail_provider.is_available():
        top_agent.tools.extend(gmail_provider.get_tools())
        top_agent.instructions.append(gmail_provider.get_instructions())

    # Wire tools into Sales Agent
    sales_agent.tools.extend(web_provider.get_tools())
    sales_agent.tools.extend(memory_provider.get_tools())
    sales_agent.instructions.extend([
        web_provider.get_instructions(),
        memory_provider.get_instructions(),
    ])

    # Wire tools into Onboarding Agent
    onboarding_agent.tools.extend(memory_provider.get_tools())
    onboarding_agent.instructions.append(memory_provider.get_instructions())

    # Build the team
    team = Team(
        name="Company Brain",
        mode=TeamMode.coordinate,
        members=[top_agent, sales_agent, onboarding_agent],
        instructions=[
            "This is the Company Brain team. The Top Agent (Chief of Staff) coordinates all work.",
            "When a request comes in, the Top Agent decides whether to handle it directly or delegate.",
            "Client Agents are spawned dynamically via the Lead Conversion workflow.",
        ],
        markdown=True,
    )

    # Store references for webhook and workflow access
    team._top_agent = top_agent
    team._sales_agent = sales_agent
    team._onboarding_agent = onboarding_agent
    team._lead_conversion = LeadConversionWorkflow(memory=memory)

    return team


def get_top_agent(team: Team) -> Agent:
    """Get the Top Agent from the team for webhook routing."""
    return team._top_agent


def get_lead_conversion(team: Team) -> LeadConversionWorkflow:
    """Get the Lead Conversion workflow from the team."""
    return team._lead_conversion
