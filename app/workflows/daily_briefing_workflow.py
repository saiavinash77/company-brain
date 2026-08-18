import logging
from datetime import datetime, timezone
from typing import Optional

from app.memory.audit_memory import AuditMemory
from app.memory.client_vault import ClientVault
from app.memory.super_memory import SuperMemory
from app.memory.working_memory import WorkingMemory

logger = logging.getLogger("company-brain")


class DailyBriefingWorkflow:
    """Orchestrates the daily briefing generation process.

    Collects data from all memory layers, runs through the Briefing Agent,
    and delivers the briefing via available channels (AgentOS, WhatsApp).
    """

    def __init__(self, memory: SuperMemory):
        self.memory = memory
        self.working = memory.working
        self.audit = memory.audit
        self.playbook = memory.playbook

    async def collect_briefing_data(self) -> dict:
        """Gather data from all memory layers for the briefing.

        Returns:
            A dictionary with all briefing-relevant data organized by section.
        """
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")

        # Active tasks from Working Memory
        active_tasks = await self.working.get_active_tasks()

        # Client status from Working Memory (clients are tracked as active tasks/metadata)
        client_summaries = {}
        try:
            # Query working memory for client-related entries
            client_entries = await self.working.backend.query(
                "working",
                filters={"key_contains": "client"},
                limit=50,
            )
            for entry in client_entries:
                val = entry.value
                if isinstance(val, dict) and "client_id" in val:
                    cid = val["client_id"]
                    if cid not in client_summaries:
                        client_summaries[cid] = val
        except Exception as e:
            logger.warning(f"Error collecting client data for briefing: {e}")

        # Recent audit trail (last 24h actions)
        recent_actions = []
        try:
            all_actions = await self.audit.get_summary()
            recent_actions = all_actions
        except Exception as e:
            logger.warning(f"Error collecting audit data for briefing: {e}")

        # Overdue flags (from working memory tasks)
        overdue_tasks = [
            t for t in active_tasks
            if t.get("status") == "in_progress" and t.get("due_date")
            and t.get("due_date", "") < today
        ]

        # Rate card for pricing context
        rate_card = None
        try:
            rate_card = await self.playbook.get_rate_card()
        except Exception:
            pass

        return {
            "date": today,
            "active_tasks": active_tasks,
            "overdue_tasks": overdue_tasks,
            "clients": client_summaries,
            "audit_summary": recent_actions,
            "rate_card": rate_card,
            "total_active_tasks": len(active_tasks),
            "total_overdue": len(overdue_tasks),
            "total_clients": len(client_summaries),
        }

    async def generate_briefing_prompt(self, data: dict, briefing_type: str = "daily") -> str:
        """Convert collected data into a prompt for the Briefing Agent.

        Args:
            data: Collected briefing data.
            briefing_type: 'daily' or 'weekly'.

        Returns:
            A formatted prompt string for the Briefing Agent.
        """
        sections = []

        if briefing_type == "daily":
            sections.append(f"Generate a morning briefing for {data['date']}.\n")

        # Priority flags
        flags = []
        if data["overdue_tasks"]:
            for task in data["overdue_tasks"]:
                flags.append(f"- OVERDUE: {task.get('description', 'Unknown task')} (due {task.get('due_date', '?')})")
        if flags:
            sections.append("### Priority Flags\n" + "\n".join(flags))
        else:
            sections.append("### Priority Flags\n- No overdue items or urgent flags.")

        # Pipeline / Tasks
        sections.append(
            f"\n### Active Tasks\n"
            f"Total active: {data['total_active_tasks']}"
        )
        for task in data["active_tasks"][:10]:
            status = task.get("status", "?")
            desc = task.get("description", "Unknown")
            task_type = task.get("type", "")
            sections.append(f"- [{status.upper()}] {desc} (type: {task_type})")

        # Clients
        sections.append(
            f"\n### Clients\n"
            f"Total active: {data['total_clients']}"
        )
        for client_id, profile in data["clients"].items():
            name = profile.get("name", client_id)
            status = profile.get("status", "unknown")
            sections.append(f"- {name} ({client_id}): {status}")

        # Audit summary
        if data["audit_summary"]:
            sections.append(f"\n### Agent Activity\nTotal actions logged: {data['audit_summary'].get('total_actions', 0)}")
            for agent_id, count in data["audit_summary"].get("agents", {}).items():
                sections.append(f"- {agent_id}: {count} actions")

        return "\n".join(sections)

    async def run_daily_briefing(self) -> str:
        """Run the full daily briefing workflow.

        Returns:
            The generated briefing text.
        """
        logger.info("Starting daily briefing workflow")
        data = await self.collect_briefing_data()
        prompt = await self.generate_briefing_prompt(data, briefing_type="daily")

        # Log the briefing generation
        await self.audit.log_action(
            agent_id="briefing_workflow",
            action="daily_briefing_generated",
            details={
                "date": data["date"],
                "active_tasks": data["total_active_tasks"],
                "overdue": data["total_overdue"],
                "clients": data["total_clients"],
            },
        )

        return prompt

    async def run_weekly_briefing(self) -> str:
        """Run the full weekly briefing workflow.

        Returns:
            The generated briefing text.
        """
        logger.info("Starting weekly briefing workflow")
        data = await self.collect_briefing_data()
        prompt = await self.generate_briefing_prompt(data, briefing_type="weekly")

        await self.audit.log_action(
            agent_id="briefing_workflow",
            action="weekly_briefing_generated",
            details={
                "date": data["date"],
                "active_tasks": data["total_active_tasks"],
                "clients": data["total_clients"],
            },
        )

        return prompt
