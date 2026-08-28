import logging

from agno.agent import Agent
from agno.team import Team, TeamMode

from app.agents.finance_agent import create_finance_agent
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
from app.models.gemini_model import get_gemini_flash
from app.providers.gmail_provider import GmailProvider
from app.providers.memory_provider import MemoryProvider
from app.providers.telegram_provider import TelegramProvider
from app.providers.twilio_provider import TwilioProvider
from app.providers.web_provider import WebProvider
from app.workflows.lead_conversion_workflow import LeadConversionWorkflow
from app.workflows.pricing_request_workflow import PricingRequestWorkflow
from app.workflows.daily_briefing_workflow import DailyBriefingWorkflow
from app.telemetry.agent_events import (
    instrument_agno_classes,
    instrument_coroutine,
    slugify,
)
from app.telemetry.floor_config import AGENT_FLOOR_MAP

logger = logging.getLogger("company-brain")


def create_context_providers(memory: SuperMemory) -> dict:
    """Build the Company Brain provider registry.

    One instance per provider, deduped by ``ContextProvider.id``, with
    startup status logged. Kept deliberately simple — 4 fixed providers,
    not Scout's dynamic registry.
    """
    providers = [
        TwilioProvider(),
        WebProvider(),
        GmailProvider(),
        MemoryProvider(memory=memory),
        TelegramProvider(),
    ]
    registry: dict = {}
    for provider in providers:
        if provider.id in registry:
            logger.warning("Duplicate provider id '%s' — keeping first instance", provider.id)
            continue
        registry[provider.id] = provider
        status = provider.status()
        if status.ok:
            logger.info("Provider ready: %s (id=%s) — %s", provider.name, provider.id, status.detail)
        else:
            logger.info("Provider unavailable: %s (id=%s) — %s", provider.name, provider.id, status.detail)
    return registry


def build_company_brain_team(memory: SuperMemory) -> Team:
    """Build the top-level Company Brain team.

    Week 1: Top Agent + Sales Agent
    Week 2: + Onboarding Agent + Gmail + Lead Conversion workflow
    Week 3: + Negotiation Agent + Finance Agent + Legal Agent + Pricing workflow + Playbook Memory
    Week 4: + Refinement Agent + Market Research Agent + Strategy Agent
    Week 5: + Briefing Agent + Daily Briefing Workflow + Semantic Memory
    """
    # Create agents
    top_agent = create_top_agent()
    sales_agent = create_sales_agent()
    onboarding_agent = create_onboarding_agent()
    negotiation_agent = create_negotiation_agent()
    finance_agent = create_finance_agent()
    legal_agent = create_legal_agent()
    refinement_agent = create_refinement_agent()
    market_research_agent = create_market_research_agent()
    strategy_agent = create_strategy_agent()
    briefing_agent = create_briefing_agent()

    # Create providers via the registry (deduped by ContextProvider.id,
    # statuses logged once at startup)
    providers = create_context_providers(memory)

    # Wire tools/instructions: (agent, ordered provider ids).
    # Providers whose status is not ok are skipped with a log line
    # (e.g. Gmail when OAuth env vars are missing).
    # NOTE: list of pairs — agno Agents don't hash as dict keys.
    provider_wiring = [
        (top_agent, ["twilio", "memory", "gmail"]),
        (sales_agent, ["web", "memory"]),
        (onboarding_agent, ["memory"]),
        (negotiation_agent, ["memory", "web"]),
        (finance_agent, ["memory"]),
        (legal_agent, ["memory"]),
        (refinement_agent, ["memory"]),
        (market_research_agent, ["web", "memory"]),
        (strategy_agent, ["memory", "web"]),
        (briefing_agent, ["memory"]),
    ]
    for agent, provider_ids in provider_wiring:
        for pid in provider_ids:
            provider = providers[pid]
            status = provider.status()
            if not status.ok:
                logger.info(
                    "Skipping %s for %s — %s",
                    provider.name,
                    agent.name,
                    status.detail,
                )
                continue
            agent.tools.extend(provider.get_tools())
            agent.instructions.append(provider.get_instructions())

    # Build the team
    team = Team(
        name="Company Brain",
        id="company-brain",
        model=get_gemini_flash(),
        mode=TeamMode.coordinate,
        members=[
            top_agent,
            sales_agent,
            onboarding_agent,
            negotiation_agent,
            finance_agent,
            legal_agent,
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
            "Market research requests: Market Research Agent handles them with web search.",
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

    # ---- Office-floor telemetry: instrument every real invocation point ----
    # Class-level patch covers all Agent/Team runs, including the per-request
    # deep copies AgentOS makes of the registered team (instance wrappers
    # would be stripped by deep_copy).
    instrument_agno_classes()
    expected = {entry["agent_id"] for entry in AGENT_FLOOR_MAP}
    for member in team.members:
        aid = slugify(member.name)
        if aid not in expected:
            logger.warning("Agent id '%s' has no desk in floor_config", aid)

    # Workflow triggers, tagged to the agents involved.
    instrument_coroutine(
        team._lead_conversion,
        "run",
        agent_id="top_agent",
        agent_name="Top Agent",
        summary_from_args=lambda *a, **k: f"converting lead {k.get('client_name') or (a[1] if len(a) > 1 else '')}",
    )
    instrument_coroutine(
        team._pricing_request,
        "prepare_pricing_context",
        agent_id="negotiation_agent",
        agent_name="Negotiation Agent",
        summary_from_args=lambda *a, **k: f"pricing options for {k.get('client_name') or (a[1] if len(a) > 1 else '')}",
    )
    instrument_coroutine(
        team._pricing_request,
        "record_pricing_decision",
        agent_id="negotiation_agent",
        agent_name="Negotiation Agent",
        summary_from_args=lambda *a, **k: f"pricing approved for {k.get('client_name') or (a[1] if len(a) > 1 else '')}",
    )
    instrument_coroutine(
        team._daily_briefing,
        "run_daily_briefing",
        agent_id="briefing_agent",
        agent_name="Briefing Agent",
        summary_from_args=lambda: "generating daily briefing",
    )
    instrument_coroutine(
        team._daily_briefing,
        "run_weekly_briefing",
        agent_id="briefing_agent",
        agent_name="Briefing Agent",
        summary_from_args=lambda: "generating weekly briefing",
    )

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
