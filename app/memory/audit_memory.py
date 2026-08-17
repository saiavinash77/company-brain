import uuid
from datetime import datetime, timezone
from typing import Optional

from app.memory.backend import MemoryBackend, MemoryEntry


class AuditMemory:
    """SuperMemory Layer 5: Full action log and analytics.

    Every agent action is logged here. Immutable — entries are never updated,
    only appended. This provides a complete audit trail.
    """

    LAYER = "audit"

    def __init__(self, backend: MemoryBackend):
        self.backend = backend

    async def log_action(
        self,
        agent_id: str,
        action: str,
        details: Optional[dict] = None,
        client_id: Optional[str] = None,
    ) -> str:
        """Log an agent action to the audit trail.

        Args:
            agent_id: The agent that performed the action.
            action: Description of the action performed.
            details: Additional details about the action.
            client_id: Associated client ID if applicable.

        Returns:
            The audit entry ID.
        """
        entry_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        value = {
            "agent_id": agent_id,
            "action": action,
            "details": details or {},
            "client_id": client_id,
            "timestamp": now,
        }
        entry = MemoryEntry(
            id=entry_id,
            agent_id=agent_id,
            client_id=client_id,
            layer=self.LAYER,
            key=f"action:{agent_id}:{entry_id}",
            value=value,
            metadata={"action_type": action},
        )
        await self.backend.put(entry)
        return entry_id

    async def get_agent_history(
        self,
        agent_id: str,
        limit: int = 50,
    ) -> list[dict]:
        """Get recent action history for a specific agent."""
        entries = await self.backend.query(
            self.LAYER,
            filters={"agent_id": agent_id},
            limit=limit,
        )
        return [e.value for e in entries]

    async def get_client_history(
        self,
        client_id: str,
        limit: int = 50,
    ) -> list[dict]:
        """Get recent action history for a specific client."""
        entries = await self.backend.query(
            self.LAYER,
            client_id=client_id,
            limit=limit,
        )
        return [e.value for e in entries]

    async def get_summary(self) -> dict:
        """Get a summary of all actions across all agents."""
        all_entries = await self.backend.query(self.LAYER, limit=1000)
        agent_actions = {}
        for entry in all_entries:
            agent_id = entry.value.get("agent_id", "unknown")
            if agent_id not in agent_actions:
                agent_actions[agent_id] = 0
            agent_actions[agent_id] += 1
        return {
            "total_actions": len(all_entries),
            "agents": agent_actions,
        }
