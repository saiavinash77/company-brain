import logging

from app.memory.audit_memory import AuditMemory
from app.memory.playbook_memory import PlaybookMemory

logger = logging.getLogger("company-brain.workflows")


class PricingRequestWorkflow:
    """Pricing request flow: rate card lookup → 3 options → owner approval → send.

    This workflow coordinates the Negotiation Agent and Top Agent to ensure:
    1. All pricing is based on the rate card
    2. Margin minimums are respected
    3. Owner approves before anything is sent to the client

    Steps:
    1. Receive pricing request with client context
    2. Negotiation Agent generates 3 pricing options
    3. Present options to owner for approval
    4. On approval, store final pricing in client vault
    5. Log entire flow in audit trail
    """

    def __init__(self, playbook_memory: PlaybookMemory, audit_memory: AuditMemory):
        self.playbook = playbook_memory
        self.audit = audit_memory

    async def prepare_pricing_context(
        self,
        client_id: str,
        client_name: str,
        service_ids: list[str],
        additional_notes: str = "",
    ) -> dict:
        """Gather all context needed for the Negotiation Agent.

        Args:
            client_id: Client identifier.
            client_name: Human-readable client name.
            service_ids: List of service IDs from the rate card (e.g. ['social_media_management']).
            additional_notes: Any extra context from the Client Agent or Top Agent.

        Returns:
            Pricing context dict with rate card data and client info.
        """
        # Load rate card
        rate_card = await self.playbook.get_rate_card()

        # Extract requested services
        services = []
        missing_services = []
        for sid in service_ids:
            service = await self.playbook.get_service_pricing(sid)
            if service:
                services.append(service)
            else:
                missing_services.append(sid)

        # Load discount policy
        discount_policy = rate_card.get("discount_policy", {}) if rate_card else {}

        context = {
            "client_id": client_id,
            "client_name": client_name,
            "requested_services": services,
            "missing_services": missing_services,
            "discount_policy": discount_policy,
            "currency": rate_card.get("currency", "USD") if rate_card else "USD",
            "additional_notes": additional_notes,
            "status": "ready_for_pricing",
        }

        # Log the request
        await self.audit.log_action(
            agent_id="negotiation_agent",
            action="pricing_request_prepared",
            details={
                "client_id": client_id,
                "client_name": client_name,
                "services_requested": service_ids,
                "missing_services": missing_services,
            },
            client_id=client_id,
        )

        return context

    async def record_pricing_decision(
        self,
        client_id: str,
        client_name: str,
        option_selected: str,
        final_pricing: dict,
        approved_by: str = "owner",
    ) -> dict:
        """Record the owner's pricing decision.

        Args:
            client_id: Client identifier.
            client_name: Client name.
            option_selected: Which option was chosen (e.g. 'Option B — Recommended').
            final_pricing: The final pricing details.
            approved_by: Who approved (default 'owner').

        Returns:
            Confirmation dict.
        """
        # Store in client vault
        from app.memory.client_vault import ClientVault
        from app.memory.backend import MemoryBackend

        # We need the backend — store the pricing decision in audit for now
        # The Client Agent's memory provider will handle vault storage
        await self.audit.log_action(
            agent_id="negotiation_agent",
            action="pricing_approved",
            details={
                "client_id": client_id,
                "client_name": client_name,
                "option_selected": option_selected,
                "final_pricing": final_pricing,
                "approved_by": approved_by,
            },
            client_id=client_id,
        )

        return {
            "status": "approved",
            "client_id": client_id,
            "option_selected": option_selected,
            "message": f"Pricing approved by {approved_by}. Option '{option_selected}' finalized for {client_name}.",
        }

    async def flag_pricing_risk(
        self,
        client_id: str,
        client_name: str,
        risk_description: str,
        below_margin: bool = False,
    ) -> dict:
        """Flag a pricing risk for owner review.

        Args:
            client_id: Client identifier.
            client_name: Client name.
            risk_description: What the risk is.
            below_margin: Whether the request is below minimum margin.

        Returns:
            Risk flag dict.
        """
        await self.audit.log_action(
            agent_id="negotiation_agent",
            action="pricing_risk_flagged",
            details={
                "client_id": client_id,
                "client_name": client_name,
                "risk": risk_description,
                "below_margin": below_margin,
            },
            client_id=client_id,
        )

        return {
            "status": "risk_flagged",
            "client_id": client_id,
            "risk": risk_description,
            "below_margin": below_margin,
            "message": f"PRICING RISK: {risk_description}",
        }
