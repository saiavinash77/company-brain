import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.memory.backend import MemoryBackend, MemoryEntry

logger = logging.getLogger("company-brain")


class SemanticMemory:
    """SuperMemory Layer 3: Semantic vector search over content.

    Provides similarity-based retrieval of memories, ideas, research,
    and other content. Uses PgVector in production; falls back to
    keyword search on LocalBackend during development.

    The semantic layer stores embeddings alongside the memory entries
    and enables "find me similar things" queries across all content.
    """

    LAYER = "semantic"

    def __init__(self, backend: MemoryBackend):
        self.backend = backend

    async def store(
        self,
        content: str,
        agent_id: str,
        content_type: str = "note",
        title: Optional[str] = None,
        client_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Store content in the semantic memory layer.

        Args:
            content: The text content to store.
            agent_id: The agent that created this content.
            content_type: Type of content (note, idea, research, strategy, summary).
            title: Optional title for the content.
            client_id: Optional client ID for scoping.
            metadata: Optional additional metadata.

        Returns:
            The entry ID.
        """
        entry_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        value = {
            "content": content,
            "title": title or "",
            "content_type": content_type,
            "timestamp": now,
            "metadata": metadata or {},
        }
        entry = MemoryEntry(
            id=entry_id,
            agent_id=agent_id,
            client_id=client_id,
            layer=self.LAYER,
            key=f"{content_type}:{entry_id}",
            value=value,
            metadata={"content_type": content_type, "title": title or ""},
        )
        await self.backend.put(entry)
        logger.debug(f"Stored semantic entry {entry_id}: {content_type} from {agent_id}")
        return entry_id

    async def search(
        self,
        query: str,
        content_type: Optional[str] = None,
        client_id: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict]:
        """Search semantic memory by keyword (local) or vector similarity (PgVector).

        Args:
            query: Search query string.
            content_type: Optional filter by content type.
            client_id: Optional filter by client ID.
            limit: Maximum results to return.

        Returns:
            List of matching entries as dicts.
        """
        filters = {}
        if content_type:
            filters["content_type"] = content_type

        entries = await self.backend.query(
            self.LAYER,
            client_id=client_id,
            filters=filters,
            limit=limit,
        )

        # Keyword-based relevance scoring (simple substring match)
        # In production with PgVector, this would be cosine similarity on embeddings
        query_lower = query.lower()
        query_terms = query_lower.split()

        scored = []
        for entry in entries:
            content = entry.value.get("content", "").lower()
            title = entry.value.get("title", "").lower()
            searchable = f"{title} {content}"

            # Score based on term matches
            score = sum(1 for term in query_terms if term in searchable)
            if score > 0:
                scored.append((score, entry))

        # Sort by relevance score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        return [entry.value for _, entry in scored[:limit]]

    async def get_by_type(
        self,
        content_type: str,
        client_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        """Get all entries of a specific content type.

        Args:
            content_type: The type to filter by.
            client_id: Optional client ID filter.
            limit: Maximum results.

        Returns:
            List of entries sorted by timestamp descending.
        """
        entries = await self.backend.query(
            self.LAYER,
            client_id=client_id,
            filters={"content_type": content_type},
            limit=limit,
        )
        # Sort by timestamp descending
        entries.sort(
            key=lambda e: e.value.get("timestamp", ""),
            reverse=True,
        )
        return [e.value for e in entries]

    async def get_entry(self, entry_id: str) -> Optional[dict]:
        """Get a specific entry by ID.

        Args:
            entry_id: The entry ID to retrieve.

        Returns:
            The entry value, or None if not found.
        """
        entries = await self.backend.query(
            self.LAYER,
            filters={"id": entry_id},
            limit=1,
        )
        if entries:
            return entries[0].value
        return None

    async def delete_entry(self, entry_id: str) -> bool:
        """Delete a semantic memory entry.

        Args:
            entry_id: The entry ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        try:
            await self.backend.delete(self.LAYER, entry_id)
            logger.debug(f"Deleted semantic entry {entry_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete semantic entry {entry_id}: {e}")
            return False

    async def get_summary(self) -> dict:
        """Get a summary of semantic memory contents."""
        all_entries = await self.backend.query(self.LAYER, limit=1000)
        type_counts = {}
        for entry in all_entries:
            ct = entry.value.get("content_type", "unknown")
            type_counts[ct] = type_counts.get(ct, 0) + 1
        return {
            "total_entries": len(all_entries),
            "by_type": type_counts,
        }
