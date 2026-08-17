from typing import Any, Optional

from app.memory.backend import MemoryBackend, MemoryEntry


class ClientVault:
    """SuperMemory Layer 2: Per-client isolated data storage.

    Each client gets their own isolated namespace. Client Agents can only
    access their own vault. The Top Agent can read all vaults but never writes.
    """

    LAYER = "vault"

    def __init__(self, client_id: str, backend: MemoryBackend):
        self.client_id = client_id
        self.backend = backend

    async def store(self, key: str, value: Any, metadata: Optional[dict] = None) -> str:
        """Store data in this client's vault."""
        entry = MemoryEntry(
            client_id=self.client_id,
            layer=self.LAYER,
            key=key,
            value=value,
            metadata=metadata or {},
        )
        return await self.backend.put(entry)

    async def retrieve(self, key: str) -> Optional[Any]:
        """Retrieve data from this client's vault."""
        entry = await self.backend.get(self.LAYER, key, client_id=self.client_id)
        if entry:
            return entry.value
        return None

    async def list_entries(self, key_prefix: Optional[str] = None) -> list[dict]:
        """List all entries in this client's vault, optionally filtered by key prefix."""
        filters = {}
        if key_prefix:
            filters["key_contains"] = key_prefix
        entries = await self.backend.query(self.LAYER, client_id=self.client_id, filters=filters, limit=100)
        return [{"key": e.key, "value": e.value, "metadata": e.metadata, "updated_at": e.updated_at} for e in entries]

    async def delete(self, key: str) -> bool:
        """Delete an entry from this client's vault."""
        return await self.backend.delete(self.LAYER, key, client_id=self.client_id)

    async def store_conversation(self, contact: str, direction: str, content: str, metadata: Optional[dict] = None):
        """Store a conversation entry (email, message, etc.) in the vault."""
        import uuid
        from datetime import datetime, timezone

        entry_key = f"conversation:{contact}:{uuid.uuid4().hex[:8]}"
        value = {
            "contact": contact,
            "direction": direction,  # "inbound" or "outbound"
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return await self.store(entry_key, value, metadata)
