from dataclasses import dataclass
from typing import Any, Optional

from app.memory.backend import MemoryBackend


@dataclass
class Task:
    id: str
    agent_id: str
    task_type: str
    status: str = "pending"  # pending, in_progress, completed, failed
    data: dict = None
    result: Any = None
    created_at: str = ""

    def __post_init__(self):
        if self.data is None:
            self.data = {}


class WorkingMemory:
    """SuperMemory Layer 1: Active tasks and conversations.

    Tracks what each agent is currently working on.
    Uses the MemoryBackend abstraction (SQLite locally, Firestore on GCP).
    """

    LAYER = "working"

    def __init__(self, backend: MemoryBackend):
        self.backend = backend

    async def create_task(self, agent_id: str, task_type: str, data: dict) -> str:
        """Create a new active task for an agent."""
        from app.memory.backend import MemoryEntry

        import uuid
        from datetime import datetime, timezone

        task_id = str(uuid.uuid4())
        task = {
            "id": task_id,
            "agent_id": agent_id,
            "task_type": task_type,
            "status": "pending",
            "data": data,
            "result": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        entry = MemoryEntry(
            id=task_id,
            agent_id=agent_id,
            layer=self.LAYER,
            key=f"task:{task_type}:{task_id}",
            value=task,
            metadata={"task_type": task_type},
        )
        await self.backend.put(entry)
        return task_id

    async def get_active_tasks(self, agent_id: Optional[str] = None) -> list[dict]:
        """Get all active (non-completed) tasks, optionally filtered by agent."""
        filters = {}
        if agent_id:
            filters["agent_id"] = agent_id
        entries = await self.backend.query(self.LAYER, filters=filters, limit=50)
        tasks = []
        for entry in entries:
            task = entry.value
            if task.get("status") not in ("completed", "failed"):
                tasks.append(task)
        return tasks

    async def complete_task(self, task_id: str, result: Any = None) -> None:
        """Mark a task as completed with an optional result."""
        from datetime import datetime, timezone

        entries = await self.backend.query(self.LAYER, filters={"key_contains": task_id}, limit=5)
        for entry in entries:
            task = entry.value
            if task.get("id") == task_id:
                task["status"] = "completed"
                task["result"] = result
                entry.value = task
                await self.backend.put(entry)
                return
        raise ValueError(f"Task {task_id} not found")

    async def fail_task(self, task_id: str, error: str) -> None:
        """Mark a task as failed with an error message."""
        entries = await self.backend.query(self.LAYER, filters={"key_contains": task_id}, limit=5)
        for entry in entries:
            task = entry.value
            if task.get("id") == task_id:
                task["status"] = "failed"
                task["result"] = {"error": error}
                entry.value = task
                await self.backend.put(entry)
                return
        raise ValueError(f"Task {task_id} not found")
