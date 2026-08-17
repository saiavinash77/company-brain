from typing import Optional

from app.config import MEMORY_BACKEND
from app.memory.backend import MemoryBackend
from app.memory.local_backend import LocalBackend
from app.memory.working_memory import WorkingMemory
from app.memory.client_vault import ClientVault
from app.memory.audit_memory import AuditMemory
from app.memory.playbook_memory import PlaybookMemory


class SuperMemory:
    """Coordinates all 5 SuperMemory layers.

    Provides a single entry point for agents to interact with the memory system.
    Routes to the appropriate layer based on the request type.

    Layers:
    1. Working Memory — Active tasks & conversations
    2. Client Vaults — Per-client isolated history
    3. Semantic Memory — Vector search (uses PgVector, upgraded to Vertex AI on GCP)
    4. Playbook Memory — Rate cards, SOPs, winning patterns
    5. Audit & Learning — Full action log + analytics
    """

    def __init__(self, backend: Optional[MemoryBackend] = None):
        if backend is None:
            if MEMORY_BACKEND == "gcp":
                from app.memory.gcp_backend import GCPBackend
                backend = GCPBackend()
            else:
                backend = LocalBackend()

        self.backend = backend
        self.working = WorkingMemory(backend)
        self.audit = AuditMemory(backend)
        self.playbook = PlaybookMemory(backend)

    async def load_playbooks(self):
        """Load all playbook files into memory. Call once at startup."""
        return await self.playbook.load_playbooks()

    def get_client_vault(self, client_id: str) -> ClientVault:
        """Get an isolated vault for a specific client."""
        return ClientVault(client_id=client_id, backend=self.backend)
