import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import DATA_DIR
from app.memory.backend import MemoryBackend, MemoryEntry


class LocalBackend(MemoryBackend):
    """SQLite + JSON file based memory backend for local development.

    Uses a single SQLite database for structured memory (working, vault, audit)
    and JSON files for playbook memory (rate cards, SOPs).
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DATA_DIR / "companybrain_memory.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS memory (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT,
                    client_id TEXT,
                    layer TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(layer, key, client_id)
                );

                CREATE INDEX IF NOT EXISTS idx_memory_layer ON memory(layer);
                CREATE INDEX IF NOT EXISTS idx_memory_client ON memory(client_id);
                CREATE INDEX IF NOT EXISTS idx_memory_agent ON memory(agent_id);
                CREATE INDEX IF NOT EXISTS idx_memory_layer_client ON memory(layer, client_id);
            """)
            conn.commit()
        finally:
            conn.close()

    def _serialize(self, value: Any) -> str:
        return json.dumps(value, default=str, ensure_ascii=False)

    def _deserialize(self, value: str) -> Any:
        return json.loads(value)

    def _entry_from_row(self, row: sqlite3.Row) -> MemoryEntry:
        return MemoryEntry(
            id=row["id"],
            agent_id=row["agent_id"],
            client_id=row["client_id"],
            layer=row["layer"],
            key=row["key"],
            value=self._deserialize(row["value"]),
            metadata=self._deserialize(row["metadata"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def put(self, entry: MemoryEntry) -> str:
        entry_id = entry.id or str(uuid.uuid4())
        entry.id = entry_id  # Assign back so subsequent puts update the same row
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO memory (id, agent_id, client_id, layer, key, value, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id)
                DO UPDATE SET agent_id=excluded.agent_id, client_id=excluded.client_id,
                    layer=excluded.layer, key=excluded.key, value=excluded.value,
                    metadata=excluded.metadata, updated_at=excluded.updated_at
                """,
                (
                    entry_id,
                    entry.agent_id,
                    entry.client_id,
                    entry.layer,
                    entry.key,
                    self._serialize(entry.value),
                    self._serialize(entry.metadata),
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return entry_id

    async def get(
        self,
        layer: str,
        key: str,
        client_id: Optional[str] = None,
    ) -> Optional[MemoryEntry]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM memory WHERE layer = ? AND key = ? AND COALESCE(client_id, '') = COALESCE(?, '')",
                (layer, key, client_id or ""),
            ).fetchone()
            if row:
                return self._entry_from_row(row)
            return None
        finally:
            conn.close()

    async def query(
        self,
        layer: str,
        filters: Optional[dict] = None,
        client_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[MemoryEntry]:
        filters = filters or {}
        conn = self._get_conn()
        try:
            query = "SELECT * FROM memory WHERE layer = ?"
            params: list[Any] = [layer]

            if client_id is not None:
                query += " AND COALESCE(client_id, '') = ?"
                params.append(client_id)

            for filter_key, filter_value in filters.items():
                if filter_key == "agent_id":
                    query += " AND agent_id = ?"
                    params.append(filter_value)
                elif filter_key == "key_contains":
                    query += " AND key LIKE ?"
                    params.append(f"%{filter_value}%")

            query += " ORDER BY updated_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [self._entry_from_row(row) for row in rows]
        finally:
            conn.close()

    async def delete(self, layer: str, key: str, client_id: Optional[str] = None) -> bool:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "DELETE FROM memory WHERE layer = ? AND key = ? AND COALESCE(client_id, '') = COALESCE(?, '')",
                (layer, key, client_id or ""),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    async def list_layers(self) -> list[str]:
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT DISTINCT layer FROM memory ORDER BY layer").fetchall()
            return [row["layer"] for row in rows]
        finally:
            conn.close()
