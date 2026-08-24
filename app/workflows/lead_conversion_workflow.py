import logging

from agno.agent import Agent
from agno.workflow import Workflow

from app.agents.client_agent import create_client_agent
from app.agents.onboarding_agent import create_onboarding_agent
from app.memory.client_vault import ClientVault
from app.memory.super_memory import SuperMemory
from app.providers.memory_provider import MemoryProvider
from app.telemetry.agent_events import STATE_IDLE, STATE_WORKING, AgentEvent, bus

logger = logging.getLogger("company-brain.workflows")


class LeadConversionWorkflow(Workflow):
    """Convert a qualified lead into a full client with dedicated agent.

    Steps:
    1. Confirm lead conversion with owner (approval gate)
    2. Create client vault in memory system
    3. Spawn dedicated Client Agent scoped to the vault
    4. Trigger onboarding checklist
    5. Store conversion record in audit trail

    This workflow is orchestrated by the Top Agent when a lead scores HOT
    or the owner explicitly requests conversion.
    """

    def __init__(self, memory: SuperMemory):
        self.memory = memory
        self._client_agents: dict[str, Agent] = {}  # client_id -> Agent

    def get_client_agent(self, client_id: str) -> Agent | None:
        """Retrieve an already-spawned client agent by client_id."""
        return self._client_agents.get(client_id)

    def list_client_agents(self) -> dict[str, Agent]:
        """Return all active client agents."""
        return dict(self._client_agents)

    async def run(
        self,
        client_id: str,
        client_name: str,
        client_email: str,
        lead_score: int | None = None,
        lead_verdict: str | None = None,
        notes: str = "",
    ) -> dict:
        """Execute the full lead-to-client conversion.

        Args:
            client_id: Unique slug for the client (e.g. 'acme_corp').
            client_name: Human-readable name (e.g. 'Acme Corporation').
            client_email: Primary contact email.
            lead_score: Original lead score (1-40) if from Sales Agent.
            lead_verdict: Original lead verdict (HOT/WARM/COLD).
            notes: Additional notes from the owner or Top Agent.

        Returns:
            Summary dict with client_id, agent name, and status.
        """
        logger.info(f"Starting lead conversion: {client_name} ({client_id})")

        # Step 1: Log the conversion action
        await self.memory.audit.log_action(
            agent_id="top_agent",
            action="lead_conversion_started",
            details={
                "client_id": client_id,
                "client_name": client_name,
                "client_email": client_email,
                "lead_score": lead_score,
                "lead_verdict": lead_verdict,
                "notes": notes,
            },
        )

        # Step 2: Create and populate the client vault
        vault = ClientVault(client_id=client_id, backend=self.memory.backend)

        await vault.store(
            "profile",
            {
                "name": client_name,
                "email": client_email,
                "status": "active",
                "converted_at": __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).isoformat(),
                "lead_score": lead_score,
                "lead_verdict": lead_verdict,
            },
            metadata={"type": "profile"},
        )

        if notes:
            await vault.store("owner_notes", notes, metadata={"type": "notes"})

        logger.info(f"Client vault created for {client_id}")

        # Step 3: Spawn the Client Agent with scoped memory provider
        client_agent = create_client_agent(client_id=client_id, client_name=client_name)
        memory_provider = MemoryProvider(memory=self.memory, client_id=client_id)

        client_agent.tools.extend(memory_provider.get_tools())
        client_agent.instructions.append(memory_provider.get_instructions())

        # Store reference for later access
        self._client_agents[client_id] = client_agent

        logger.info(f"Client Agent spawned: {client_agent.name}")

        # Office floor: give the new Client Agent a temporary desk while active.
        # (Removed later via bus.roster_remove when the client is offboarded.)
        bus.roster_add(
            {
                "agent_id": f"client_{client_id}",
                "name": f"Client Agent — {client_name}",
                "role": f"dedicated to {client_name}",
                "accent": "#FFA07A",
                "accent_alt": "#FFD0B5",
                "desk": _temp_desk(len(self._client_agents)),
            }
        )
        bus.publish(
            AgentEvent(
                agent_id=f"client_{client_id}",
                agent_name=client_agent.name,
                state=STATE_IDLE,
                task_summary="spawned via lead conversion",
            )
        )

        # Step 4: Log onboarding trigger
        await self.memory.audit.log_action(
            agent_id="onboarding_agent",
            action="onboarding_triggered",
            details={"client_id": client_id, "client_name": client_name},
            client_id=client_id,
        )
        # Floor pulse: onboarding picks the new client up from here.
        bus.publish(AgentEvent("onboarding_agent", "Onboarding Agent", STATE_WORKING,
                               target_agent_id=f"client_{client_id}",
                               task_summary=f"onboarding checklist for {client_name}"))
        bus.publish(AgentEvent("onboarding_agent", "Onboarding Agent", STATE_IDLE,
                               target_agent_id=f"client_{client_id}",
                               task_summary=f"onboarding checklist ready for {client_name}"))

        # Step 5: Return summary
        summary = {
            "status": "success",
            "client_id": client_id,
            "client_name": client_name,
            "client_email": client_email,
            "agent_name": client_agent.name,
            "vault_created": True,
            "onboarding_status": "triggered",
            "message": (
                f"Client '{client_name}' has been converted and is ready for onboarding. "
                f"A dedicated Client Agent has been spawned with access to the client vault. "
                f"The Onboarding Agent should now run the onboarding checklist."
            ),
        }

        logger.info(f"Lead conversion complete: {summary['message']}")

        return summary


def _temp_desk(index: int) -> dict:
    """Deterministic temporary desk positions along the bottom edge."""
    return {"x": 80 + index * 100, "y": 530}


def remove_client_desk(client_id: str) -> None:
    """Take a Client Agent's temporary desk off the floor (offboarding)."""
    bus.roster_remove(f"client_{client_id}")
