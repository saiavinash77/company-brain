"""Live agent activity events powering the office-floor view.

A tiny in-process pub/sub bus. Agent invocation points (team member runs,
workflow triggers, webhook-driven Top Agent runs) publish state events;
the ``/ws/agent-status`` WebSocket fans them out to connected floor views.

Event schema — exactly what the frontend consumes:

    state events:  {"kind": "state", agent_id, agent_name,
                    state: "idle" | "working" | "handoff",
                    target_agent_id: str | null,     # set on handoff
                    task_summary: str, timestamp: iso8601}

    roster events: {"kind": "roster", action: "add" | "remove",
                    agent: {agent_id, name, role, accent, desk, temporary},
                    timestamp}

No persistence here by design — audit_memory already covers the durable
trail; this is live status only.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable

logger = logging.getLogger("company-brain.telemetry")

STATE_IDLE = "idle"
STATE_WORKING = "working"
STATE_HANDOFF = "handoff"
VALID_STATES = {STATE_IDLE, STATE_WORKING, STATE_HANDOFF}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentEvent:
    """One agent activity event (matches the floor's event schema)."""

    agent_id: str
    agent_name: str
    state: str  # idle | working | handoff
    target_agent_id: str | None = None
    task_summary: str = ""
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "kind": "state",
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "state": self.state,
            "target_agent_id": self.target_agent_id,
            "task_summary": self.task_summary,
            "timestamp": self.timestamp,
        }


class AgentActivityBus:
    """In-process pub/sub for live agent status + the current snapshot."""

    def __init__(self, max_queue: int = 256):
        self._states: dict[str, dict] = {}          # latest event per agent
        self._roster: dict[str, dict] = {}          # dynamic client desks
        self._run_depth: dict[str, int] = {}        # reentrancy per agent
        self._active_stack: list[tuple[str, str]] = []  # [(agent_id, name)]
        self._subscribers: set[asyncio.Queue] = set()
        self._max_queue = max_queue

    # -- publishing ----------------------------------------------------

    def publish(self, event: AgentEvent) -> None:
        if event.state not in VALID_STATES:
            logger.warning("Ignoring invalid agent state '%s'", event.state)
            return
        self._states[event.agent_id] = event.to_dict()
        self._broadcast(event.to_dict())

    def _broadcast(self, payload: dict) -> None:
        dead = []
        for q in self._subscribers:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)  # slow consumer — drop it rather than block agents
            except Exception:
                dead.append(q)
        for q in dead:
            self.unsubscribe(q)

    # -- subscriptions ---------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    # -- dynamic client desks ---------------------------------------------

    def roster_add(self, agent: dict) -> None:
        entry = {**agent, "temporary": True}
        self._roster[agent["agent_id"]] = entry
        self._broadcast({"kind": "roster", "action": "add", "agent": entry, "timestamp": _now_iso()})
        logger.info("Floor roster add: %s (%s)", agent.get("name"), agent["agent_id"])

    def roster_remove(self, agent_id: str) -> None:
        if agent_id not in self._roster:
            return
        entry = self._roster.pop(agent_id)
        self._states.pop(agent_id, None)
        self._broadcast({"kind": "roster", "action": "remove", "agent": entry, "timestamp": _now_iso()})
        logger.info("Floor roster remove: %s", agent_id)

    # -- snapshot ----------------------------------------------------------

    def snapshot(self, fixed_agents: list[dict]) -> dict:
        """Full floor state: fixed desks + live states + temporary client desks."""
        agents = []
        for meta in fixed_agents:
            snap = dict(meta)
            snap.update(self._states.get(meta["agent_id"], {}))
            snap["temporary"] = False
            agents.append(snap)
        clients = []
        for agent_id, meta in self._roster.items():
            snap = dict(meta)
            snap.update(self._states.get(agent_id, {}))
            clients.append(snap)
        return {"agents": agents, "clients": clients, "server_time": _now_iso()}


# Process-wide singleton so every invocation point shares one bus.
bus = AgentActivityBus()


def slugify(name: str) -> str:
    return name.lower().replace(" ", "_").replace("-", "_")


def summarize(message) -> str:
    """Best-effort short summary from a run() call's message argument."""
    text = message if isinstance(message, str) else str(message or "")
    text = " ".join(text.split())
    return text[:120]


# ---------------------------------------------------------------------------
# Instrumentation helpers — wrap real invocation points, no framework forks.
# ---------------------------------------------------------------------------

def instrument_agent(agent, agent_id: str | None = None) -> str:
    """Wrap an Agno Agent's run/arun to emit working/idle + handoff events.

    Handles both plain awaits and streaming calls (arun(stream=True)), and is
    reentrancy-safe (nested/concurrent runs don't flip-flop states). Returns
    the resolved agent_id.
    """
    aid = agent_id or slugify(getattr(agent, "name", "agent"))
    aname = getattr(agent, "name", aid)
    orig_run = getattr(agent, "run", None)
    orig_arun = getattr(agent, "arun", None)

    def _enter(summary: str) -> None:
        depth = bus._run_depth.get(aid, 0)
        bus._run_depth[aid] = depth + 1
        if depth == 0:
            if bus._active_stack:
                src_id, src_name = bus._active_stack[-1]
                if src_id != aid:
                    bus.publish(AgentEvent(src_id, src_name, STATE_HANDOFF, target_agent_id=aid,
                                           task_summary=summary))
            bus.publish(AgentEvent(aid, aname, STATE_WORKING, task_summary=summary))
        bus._active_stack.append((aid, aname))

    def _exit_ok(summary: str) -> None:
        bus._run_depth[aid] = max(0, bus._run_depth.get(aid, 1) - 1)
        for item in reversed(bus._active_stack):
            if item == (aid, aname):
                bus._active_stack.remove(item)
                break
        if bus._run_depth[aid] == 0:
            bus.publish(AgentEvent(aid, aname, STATE_IDLE, task_summary=summary))

    def run_wrapper(*args, **kwargs):
        summary = summarize(kwargs.get("input") or (args[0] if args else ""))
        _enter(summary)
        try:
            result = orig_run(*args, **kwargs)
        except Exception:
            _exit_ok(f"error: {summary}")
            raise
        _exit_ok(summary)
        return result

    async def arun_wrapper(*args, **kwargs):
        streaming = bool(kwargs.get("stream"))
        if not streaming:
            summary = summarize(kwargs.get("input") or (args[0] if args else ""))
            _enter(summary)
            try:
                result = await orig_arun(*args, **kwargs)
            except Exception:
                _exit_ok(f"error: {summary}")
                raise
            _exit_ok(summary)
            return result

        async def stream_gen():
            summary = summarize(kwargs.get("input") or (args[0] if args else ""))
            _enter(summary)
            try:
                async for chunk in orig_arun(*args, **kwargs):
                    yield chunk
            finally:
                _exit_ok(summary)

        return stream_gen()

    if orig_run is not None:
        agent.run = run_wrapper
    if orig_arun is not None:
        agent.arun = arun_wrapper
    return aid


def instrument_coroutine(
    obj,
    method_name: str,
    *,
    agent_id: str,
    agent_name: str,
    summary_from_args: Callable[..., str] | None = None,
    on_done: Callable[[], None] | None = None,
) -> None:
    """Wrap an async method to emit working/idle pulses tagged to one agent.

    Used for deterministic workflow triggers (pricing, briefing, lead
    conversion) whose work should light up the involved agents' desks.
    """
    original = getattr(obj, method_name)

    async def wrapper(*args, **kwargs):
        summary = summary_from_args(*args, **kwargs) if summary_from_args else method_name
        depth = bus._run_depth.get(agent_id, 0)
        bus._run_depth[agent_id] = depth + 1
        if depth == 0:
            bus.publish(AgentEvent(agent_id, agent_name, STATE_WORKING, task_summary=summary))
        try:
            result = await original(*args, **kwargs)
        except Exception:
            bus._run_depth[agent_id] = max(0, bus._run_depth.get(agent_id, 1) - 1)
            if bus._run_depth[agent_id] == 0:
                bus.publish(AgentEvent(agent_id, agent_name, STATE_IDLE, task_summary=f"error: {summary}"))
            raise
        bus._run_depth[agent_id] = max(0, bus._run_depth.get(agent_id, 1) - 1)
        if bus._run_depth[agent_id] == 0:
            bus.publish(AgentEvent(agent_id, agent_name, STATE_IDLE, task_summary=summary))
            if on_done:
                on_done()
        return result

    setattr(obj, method_name, wrapper)
