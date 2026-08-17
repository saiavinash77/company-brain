import json
from pathlib import Path
from typing import Any, Optional

from app.config import PLAYBOOKS_DIR
from app.memory.backend import MemoryBackend, MemoryEntry


class PlaybookMemory:
    """SuperMemory Layer 4: Rate cards, SOPs, and operational playbooks.

    Loads playbook data from JSON files and provides read access to agents.
    Uses the MemoryBackend abstraction for future GCP migration (Firestore/BigQuery).

    Data sources:
    - rate_card.json: Service pricing tiers and discount policy
    - sop.json: Standard operating procedures
    """

    LAYER = "playbook"

    def __init__(self, backend: MemoryBackend, playbooks_dir: Optional[Path] = None):
        self.backend = backend
        self.playbooks_dir = playbooks_dir or PLAYBOOKS_DIR
        self._cache: dict[str, Any] = {}

    async def load_playbooks(self) -> dict[str, bool]:
        """Load all playbook JSON files into memory. Returns dict of filename -> success."""
        results = {}
        for json_file in self.playbooks_dir.glob("*.json"):
            key = json_file.stem  # e.g. 'rate_card', 'sop'
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                self._cache[key] = data
                # Also store in backend for persistence and searchability
                await self._store_in_backend(key, data)
                results[key] = True
            except Exception as e:
                results[key] = False
                # Log the error but don't raise — other playbooks may still load
                import logging
                logging.getLogger("company-brain").warning(f"Failed to load playbook {key}: {e}")
        return results

    async def _store_in_backend(self, key: str, data: Any):
        """Store playbook data in the memory backend."""
        entry = MemoryEntry(
            agent_id="system",
            layer=self.LAYER,
            key=f"playbook:{key}",
            value=data,
            metadata={"type": "playbook", "playbook_key": key},
        )
        await self.backend.put(entry)

    async def get_playbook(self, key: str) -> Optional[Any]:
        """Get a playbook by key (e.g. 'rate_card', 'sop')."""
        # Check cache first
        if key in self._cache:
            return self._cache[key]
        # Fall back to backend
        entry = await self.backend.get(self.LAYER, f"playbook:{key}")
        if entry:
            self._cache[key] = entry.value
            return entry.value
        return None

    async def get_rate_card(self) -> Optional[dict]:
        """Convenience method to get the rate card."""
        return await self.get_playbook("rate_card")

    async def get_sops(self) -> Optional[dict]:
        """Convenience method to get the SOPs."""
        return await self.get_playbook("sop")

    async def get_sop(self, sop_key: str) -> Optional[dict]:
        """Get a specific SOP by key (e.g. 'lead_intake', 'pricing_request')."""
        sops = await self.get_sops()
        if sops:
            return sops.get("sops", {}).get(sop_key)
        return None

    async def get_service_pricing(self, service_id: str) -> Optional[dict]:
        """Get pricing tiers for a specific service."""
        rate_card = await self.get_rate_card()
        if rate_card:
            for service in rate_card.get("services", []):
                if service.get("id") == service_id:
                    return service
        return None

    async def list_playbooks(self) -> list[str]:
        """List all available playbook keys."""
        if self._cache:
            return list(self._cache.keys())
        # Fall back to backend query
        entries = await self.backend.query(self.LAYER, filters={"key_contains": "playbook:"}, limit=50)
        return [e.key.replace("playbook:", "") for e in entries]
