import logging

from agno.agent import Agent
from agno.team import Team, TeamMode

from app.agents.finance_agent import create_finance_agent
from app.agents.idea_agent import create_idea_agent
from app.agents.legal_agent import create_legal_agent
from app.agents.market_research_agent import create_market_research_agent
from app.agents.negotiation_agent import create_negotiation_agent
from app.agents.onboarding_agent import create_onboarding_agent
from app.agents.refinement_agent import create_refinement_agent
from app.agents.sales_agent import create_sales_agent
from app.agents.strategy_agent import create_strategy_agent
from app.agents.top_agent import create_top_agent
from app.agents.briefing_agent import create_briefing_agent
from app.memory.super_memory import SuperMemory
from app.providers.gmail_provider import GmailProvider
from app.providers.memory_provider import MemoryProvider
from app.providers.twilio_provider import TwilioProvider
from app.providers.web_provider import WebProvider
from app.workflows.lead_conversion_workflow import LeadConversionWorkflow
from app.workflows.pricing_request_workflow import PricingRequestWorkflow
from app.workflows.daily_briefing_workflow import DailyBriefingWorkflow

logger = logging.getLogger("company-brain")


def build_company_brain_team(memory: SuperMemory) -> Team:
    """Build the top-level Company Brain team.

    Week 1: Top Agent + Sales Agent
    Week 2: + Onboarding Agent + Gmail + Lead Conversion workflow
    Week 3: + Negotiation Agent + Finance Agent + Legal Agent + Pricing workflow + Playbook Memory
    Week 4: + Idea Agent + Refinement Agent + Market Research Agent + Strategy Agent
    Week 5: + Briefing Agent + Daily Briefing Workflow + Semantic Memory
    """
    # Create agents
    top_agent = create_top_agent()
    sales_agent = create_sales_agent()
    onboarding_agent = create_onboarding_agent()
    negotiation_agent = create_negotiation_agent()
    finance_agent = create_finance_agent()
    legal_agent = create_legal_agent()
    idea_agent = create_idea_agent()
    refinement_agent = create_refinement_agent()
    market_research_agent = create_market_research_agent()
    strategy_agent = create_strategy_agent()
    briefing_agent = create_briefing_agent()

    # Create providers
    twilio_provider = TwilioProvider()
    web_provider = WebProvider()
    gmail_provider = GmailProvider()
    memory_provider = MemoryProvider(memory=memory)

    # Wire tools into Top Agent (gets Twilio + Gmail + Memory)
    top_agent.tools.extend(twilio_provider.get_tools())
    top_agent.tools.extend(memory_provider.get_tools())
    top_agent.instructions.extend([
        twilio_provider.get_instructions(),
        memory_provider.get_instructions(),
    ])
    if gmail_provider.is_available():
        top_agent.tools.extend(gmail_provider.get_tools())
        top_agent.instructions.append(gmail_provider.get_instructions())

    # Wire tools into Sales Agent (Web + Memory)
    sales_agent.tools.extend(web_provider.get_tools())
    sales_agent.tools.extend(memory_provider.get_tools())
    sales_agent.instructions.extend([
        web_provider.get_instructions(),
        memory_provider.get_instructions(),
    ])

    # Wire tools into Onboarding Agent (Memory)
    onboarding_agent.tools.extend(memory_provider.get_tools())
    onboarding_agent.instructions.append(memory_provider.get_instructions())

    # Wire tools into Negotiation Agent (Memory + Web for market research)
    negotiation_agent.tools.extend(memory_provider.get_tools())
    negotiation_agent.tools.extend(web_provider.get_tools())
    negotiation_agent.instructions.extend([
        memory_provider.get_instructions(),
        web_provider.get_instructions(),
    ])

    # Wire tools into Finance Agent (Memory)
    finance_agent.tools.extend(memory_provider.get_tools())
    finance_agent.instructions.append(memory_provider.get_instructions())

    # Wire tools into Legal Agent (Memory)
    legal_agent.tools.extend(memory_provider.get_tools())
    legal_agent.instructions.append(memory_provider.get_instructions())

    # Wire tools into Idea Agent (Memory)
    idea_agent.tools.extend(memory_provider.get_tools())
    idea_agent.instructions.append(memory_provider.get_instructions())

    # Wire tools into Refinement Agent (Memory)
    refinement_agent.tools.extend(memory_provider.get_tools())
    refinement_agent.instructions.append(memory_provider.get_instructions())

    # Wire tools into Market Research Agent (Web + Memory)
    market_research_agent.tools.extend(web_provider.get_tools())
    market_research_agent.tools.extend(memory_provider.get_tools())
    market_research_agent.instructions.extend([
        web_provider.get_instructions(),
        memory_provider.get_instructions(),
    ])

    # Wire tools into Strategy Agent (Memory + Web)
    strategy_agent.tools.extend(memory_provider.get_tools())
    strategy_agent.tools.extend(web_provider.get_tools())
    strategy_agent.instructions.extend([
        memory_provider.get_instructions(),
        web_provider.get_instructions(),
    ])

    # Wire tools into Briefing Agent (Memory)
    briefing_agent.tools.extend(memory_provider.get_tools())
    briefing_agent.instructions.append(memory_provider.get_instructions())

    # Build the team
    team = Team(
        name="Company Brain",
        mode=TeamMode.coordinate,
        members=[
            top_agent,
            sales_agent,
            onboarding_agent,
            negotiation_agent,
            finance_agent,
            legal_agent,
            idea_agent,
            refinement_agent,
            market_research_agent,
            strategy_agent,
            briefing_agent,
        ],
        instructions=[
            "This is the Company Brain team. The Top Agent (Chief of Staff) coordinates all work.",
            "When a request comes in, the Top Agent decides whether to handle it directly or delegate.",
            "Client Agents are spawned dynamically via the Lead Conversion workflow.",
            "Pricing requests must go through the Negotiation Agent and require owner approval.",
            "Ideas go through: Idea Agent → (optional) Market Research → Refinement Agent.",
            "Strategy requests: Market Research Agent + Strategy Agent work together.",
            "Daily briefings are generated by the Briefing Agent using the Daily Briefing Workflow.",
        ],
        markdown=True,
    )

    # Store references for webhook and workflow access
    team._top_agent = top_agent
    team._sales_agent = sales_agent
    team._onboarding_agent = onboarding_agent
    team._negotiation_agent = negotiation_agent
    team._finance_agent = finance_agent
    team._legal_agent = legal_agent
    team._idea_agent = idea_agent
    team._refinement_agent = refinement_agent
    team._market_research_agent = market_research_agent
    team._strategy_agent = strategy_agent
    team._briefing_agent = briefing_agent
    team._lead_conversion = LeadConversionWorkflow(memory=memory)
    team._pricing_request = PricingRequestWorkflow(
        playbook_memory=memory.playbook,
        audit_memory=memory.audit,
    )
    team._daily_briefing = DailyBriefingWorkflow(memory=memory)

    return team


def get_top_agent(team: Team) -> Agent:
    """Get the Top Agent from the team for webhook routing."""
    return team._top_agent


def get_lead_conversion(team: Team) -> LeadConversionWorkflow:
    """Get the Lead Conversion workflow from the team."""
    return team._lead_conversion


def get_pricing_request(team: Team) -> PricingRequestWorkflow:
    """Get the Pricing Request workflow from the team."""
    return team._pricing_request


def get_daily_briefing(team: Team) -> DailyBriefingWorkflow:
    """Get the Daily Briefing workflow from the team."""
    return team._daily_briefing
