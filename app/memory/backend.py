from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class MemoryEntry:
    id: Optional[str] = None
    agent_id: Optional[str] = None
    client_id: Optional[str] = None
    layer: str = ""  # working, vault, semantic, playbook, audit
    key: str = ""
    value: Any = None
    metadata: dict = field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class MemoryBackend(ABC):
    """Abstract interface for memory storage backends.

    Local backend uses SQLite + JSON files.
    GCP backend (future) uses Firestore + BigQuery + Cloud Storage.
    """

    @abstractmethod
    async def put(self, entry: MemoryEntry) -> str:
        """Store a memory entry. Returns the entry ID."""
        ...

    @abstractmethod
    async def get(self, layer: str, key: str, client_id: Optional[str] = None) -> Optional[MemoryEntry]:
        """Retrieve a memory entry by layer, key, and optional client_id."""
        ...

    @abstractmethod
    async def query(
        self,
        layer: str,
        filters: Optional[dict] = None,
        client_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[MemoryEntry]:
        """Query memory entries within a layer with optional filters."""
        ...

    @abstractmethod
    async def delete(self, layer: str, key: str, client_id: Optional[str] = None) -> bool:
        """Delete a memory entry. Returns True if deleted."""
        ...

    @abstractmethod
    async def list_layers(self) -> list[str]:
        """List all available memory layers."""
        ...
