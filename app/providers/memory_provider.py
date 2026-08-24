from agno.context.provider import Status

from app.memory.super_memory import SuperMemory
from app.providers.base_provider import BaseProvider


class MemoryProvider(BaseProvider):
    """Provides SuperMemory tools to agents.

    Gives agents access to working memory (tasks), client vaults,
    and audit logging. Each agent gets scoped access.

    Holds no connection of its own (the backend is shared via SuperMemory):
    inherits the no-op ``asetup()``/``aclose()`` lifecycle from ContextProvider.
    """

    def __init__(self, memory: SuperMemory, client_id: str | None = None):
        # Per-client instances get a distinct id so registries can dedupe by id
        # without collapsing scoped providers into the general one.
        provider_id = f"memory:{client_id}" if client_id else "memory"
        super().__init__(provider_id=provider_id, name=f"Memory ({client_id})" if client_id else "Memory")
        self.memory = memory
        self.client_id = client_id  # For Client Agents, None for general agents

    def status(self) -> Status:
        if self.memory is not None:
            scope = f"scoped to client '{self.client_id}'" if self.client_id else "general scope"
            return Status(ok=True, detail=f"SuperMemory available ({scope})")
        return Status(ok=False, detail="No SuperMemory instance attached")

    async def astatus(self) -> Status:
        return self.status()

    def get_tools(self) -> list:
        return [
            self.create_task,
            self.get_active_tasks,
            self.complete_task,
            self.store_memory,
            self.retrieve_memory,
            self.log_action,
        ]

    def get_instructions(self) -> str:
        instructions = (
            "You have access to the Company Brain memory system.\n"
            "- Use create_task to track work you need to do.\n"
            "- Use get_active_tasks to see what's pending.\n"
            "- Use complete_task when you finish something.\n"
            "- Use store_memory to save important information.\n"
            "- Use retrieve_memory to look up saved information.\n"
            "- Use log_action to record significant actions for the audit trail.\n"
        )
        if self.client_id:
            instructions += (
                f"\nYou are assigned to client '{self.client_id}'. "
                "Your memory access is scoped to this client's vault."
            )
        return instructions

    async def create_task(self, task_type: str, description: str) -> str:
        """Create a new task to track your work.

        Args:
            task_type: Category of task (e.g., 'lead_scoring', 'email_draft', 'research').
            description: What the task involves.

        Returns:
            The task ID for tracking.
        """
        task_id = await self.memory.working.create_task(
            agent_id=self.client_id or "general",
            task_type=task_type,
            data={"description": description},
        )
        await self.memory.audit.log_action(
            agent_id=self.client_id or "general",
            action="create_task",
            details={"task_id": task_id, "task_type": task_type, "description": description},
        )
        return f"Task created with ID: {task_id}"

    async def get_active_tasks(self) -> str:
        """Get all active (non-completed) tasks.

        Returns:
            List of pending and in-progress tasks.
        """
        tasks = await self.memory.working.get_active_tasks(agent_id=self.client_id or "general")
        if not tasks:
            return "No active tasks found."
        lines = []
        for task in tasks:
            lines.append(f"- [{task['status'].upper()}] {task['task_type']}: {task['data'].get('description', 'No description')}")
        return "Active tasks:\n" + "\n".join(lines)

    async def complete_task(self, task_id: str, result: str = "") -> str:
        """Mark a task as completed.

        Args:
            task_id: The ID of the task to complete.
            result: Optional summary of what was accomplished.

        Returns:
            Confirmation message.
        """
        await self.memory.working.complete_task(task_id, result)
        await self.memory.audit.log_action(
            agent_id=self.client_id or "general",
            action="complete_task",
            details={"task_id": task_id, "result": result},
        )
        return f"Task {task_id} marked as completed."

    async def store_memory(self, key: str, value: str) -> str:
        """Store important information in memory.

        Args:
            key: A descriptive key for the information (e.g., 'client_preference', 'pricing_decision').
            value: The information to store.

        Returns:
            Confirmation of storage.
        """
        from app.memory.backend import MemoryEntry

        entry = MemoryEntry(
            agent_id=self.client_id or "general",
            layer="vault" if self.client_id else "working",
            key=key,
            value={"data": value},
        )
        await self.memory.backend.put(entry)
        return f"Stored memory under key: {key}"

    async def retrieve_memory(self, key: str) -> str:
        """Retrieve stored information by key.

        Args:
            key: The key to look up.

        Returns:
            The stored information or 'not found'.
        """
        entry = await self.memory.backend.get(
            layer="vault" if self.client_id else "working",
            key=key,
            client_id=self.client_id,
        )
        if entry and entry.value:
            return str(entry.value.get("data", entry.value))
        return f"No memory found for key: {key}"

    async def log_action(self, action: str, details: str = "") -> str:
        """Log a significant action to the audit trail.

        Args:
            action: What action was performed.
            details: Additional context about the action.

        Returns:
            Confirmation of logging.
        """
        await self.memory.audit.log_action(
            agent_id=self.client_id or "general",
            action=action,
            details={"details": details},
        )
        return f"Action '{action}' logged to audit trail."
