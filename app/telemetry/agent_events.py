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
import threading
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


def _safe_put(q: asyncio.Queue, payload: dict) -> None:
    """put_nowait on the subscriber's own loop; drop on overflow."""
    try:
        q.put_nowait(payload)
    except asyncio.QueueFull:
        logger.warning("Floor event queue full — dropping event %s", payload.get("state"))


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
    """In-process pub/sub for live agent status + the current snapshot.

    Thread-safe: AgentOS executes team runs on a background ThreadPoolExecutor
    (``team.arun(background=True)``), so member instrumentation publishes from
    worker threads. Subscribers record the loop they were created on and
    payloads are handed to that loop via ``call_soon_threadsafe``.
    """

    def __init__(self, max_queue: int = 256):
        self._states: dict[str, dict] = {}          # latest event per agent
        self._roster: dict[str, dict] = {}          # dynamic client desks
        self._run_depth: dict[str, int] = {}        # reentrancy per agent
        self._active_stack: list[tuple[str, str]] = []  # [(agent_id, name)]
        self._subscribers: dict[asyncio.Queue, asyncio.AbstractEventLoop | None] = {}
        self._max_queue = max_queue
        self._lock = threading.Lock()

    # -- publishing ----------------------------------------------------

    def publish(self, event: AgentEvent) -> None:
        if event.state not in VALID_STATES:
            logger.warning("Ignoring invalid agent state '%s'", event.state)
            return
        payload = event.to_dict()
        with self._lock:
            self._states[event.agent_id] = payload
        self._broadcast(payload)

    def _broadcast(self, payload: dict) -> None:
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        dead = []
        with self._lock:
            subscribers = list(self._subscribers.items())
        for q, loop in subscribers:
            target = loop if loop is not None else running
            try:
                if target is None or target is running:
                    q.put_nowait(payload)
                else:
                    target.call_soon_threadsafe(_safe_put, q, payload)
            except asyncio.QueueFull:
                dead.append(q)  # slow consumer — drop it rather than block agents
            except Exception:
                dead.append(q)  # closed loop or dead queue
        for q in dead:
            self.unsubscribe(q)

    # -- subscriptions ---------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        with self._lock:
            self._subscribers[q] = loop
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.pop(q, None)

    # -- dynamic client desks ---------------------------------------------

    def roster_add(self, agent: dict) -> None:
        entry = {**agent, "temporary": True}
        with self._lock:
            self._roster[agent["agent_id"]] = entry
        self._broadcast({"kind": "roster", "action": "add", "agent": entry, "timestamp": _now_iso()})
        logger.info("Floor roster add: %s (%s)", agent.get("name"), agent["agent_id"])

    def roster_remove(self, agent_id: str) -> None:
        with self._lock:
            if agent_id not in self._roster:
                return
            entry = self._roster.pop(agent_id)
            self._states.pop(agent_id, None)
        self._broadcast({"kind": "roster", "action": "remove", "agent": entry, "timestamp": _now_iso()})
        logger.info("Floor roster remove: %s (%s)", entry.get("name"), agent_id)

    # -- snapshot ----------------------------------------------------------

    def snapshot(self, fixed_agents: list[dict]) -> dict:
        """Full floor state: fixed desks + live states + temporary client desks."""
        agents = []
        with self._lock:
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

def _enter_run(aid: str, aname: str, summary: str) -> None:
    with bus._lock:
        depth = bus._run_depth.get(aid, 0)
        bus._run_depth[aid] = depth + 1
        src = bus._active_stack[-1] if bus._active_stack else None
        bus._active_stack.append((aid, aname))
    if depth == 0:
        if src is not None and src[0] != aid:
            bus.publish(AgentEvent(src[0], src[1], STATE_HANDOFF, target_agent_id=aid,
                                   task_summary=summary))
        bus.publish(AgentEvent(aid, aname, STATE_WORKING, task_summary=summary))


def _exit_run(aid: str, aname: str, summary: str) -> None:
    with bus._lock:
        bus._run_depth[aid] = max(0, bus._run_depth.get(aid, 1) - 1)
        for item in reversed(bus._active_stack):
            if item == (aid, aname):
                bus._active_stack.remove(item)
                break
        done = bus._run_depth[aid] == 0
    if done:
        bus.publish(AgentEvent(aid, aname, STATE_IDLE, task_summary=summary))


def instrument_agent(agent, agent_id: str | None = None) -> str:
    """Wrap an agent-like object's run/arun to emit working/idle + handoff
    events (used for objects that are not real Agno Agent/Team instances;
    real ones are covered by instrument_agno_classes). Handles both plain
    awaits and streaming calls (arun(stream=True)), and is reentrancy-safe.
    """
    aid = agent_id or slugify(getattr(agent, "name", "agent"))
    aname = getattr(agent, "name", aid)
    orig_run = getattr(agent, "run", None)
    orig_arun = getattr(agent, "arun", None)

    def run_wrapper(*args, **kwargs):
        summary = summarize(kwargs.get("input") or (args[0] if args else ""))
        _enter_run(aid, aname, summary)
        try:
            result = orig_run(*args, **kwargs)
        except Exception:
            _exit_run(aid, aname, f"error: {summary}")
            raise
        _exit_run(aid, aname, summary)
        return result

    # Same duality as the class-level patch below: arun(stream=True) must
    # return an async generator, arun otherwise a coroutine — never one
    # wrapper type for both.
    def arun_wrapper(*args, **kwargs):
        if not kwargs.get("stream"):
            async def run_coro():
                summary = summarize(kwargs.get("input") or (args[0] if args else ""))
                _enter_run(aid, aname, summary)
                try:
                    result = await orig_arun(*args, **kwargs)
                except Exception:
                    _exit_run(aid, aname, f"error: {summary}")
                    raise
                _exit_run(aid, aname, summary)
                return result

            return run_coro()

        async def stream_gen():
            summary = summarize(kwargs.get("input") or (args[0] if args else ""))
            _enter_run(aid, aname, summary)
            try:
                async for chunk in orig_arun(*args, **kwargs):
                    yield chunk
            finally:
                _exit_run(aid, aname, summary)

        return stream_gen()

    if orig_run is not None:
        agent.run = run_wrapper
    if orig_arun is not None:
        agent.arun = arun_wrapper
    return aid


_AGNO_CLASSES_INSTRUMENTED = False


def instrument_agno_classes() -> None:
    """Patch Agno Agent/Team run methods at the class level (idempotent).

    AgentOS resolves the registered team per request via
    ``get_team_by_id(create_fresh=True)``; ``team.deep_copy()`` rebuilds the
    team and its members, stripping any instance-level wrappers. Class
    methods survive the copy, so every deep-copied team/member — and any
    dynamically spawned client agent — stays instrumented. The team run
    itself is reported as top_agent: in coordinate mode the team model is
    the boss's brain, and it anchors the handoff source for member runs.
    """
    global _AGNO_CLASSES_INSTRUMENTED
    if _AGNO_CLASSES_INSTRUMENTED:
        return
    _AGNO_CLASSES_INSTRUMENTED = True

    from agno.agent import Agent
    from agno.team import Team

    def _ids(instance) -> tuple[str, str]:
        if isinstance(instance, Team):
            return "top_agent", "Top Agent"
        name = getattr(instance, "name", None) or "agent"
        return slugify(name), name

    def _wrap_arun(orig_arun):
        # Agno v2's Agent/Team.arun is a PLAIN function that returns either a
        # coroutine (stream=False) or an async generator (stream=True), and
        # AgentOS consumes it accordingly (`await` vs `async for`). The
        # wrapper must preserve that duality: an `async def` wrapper always
        # returns a coroutine, which breaks `async for ... in arun(...)` with
        # TeamRunError "'async for' requires an object with __aiter__".
        def arun_wrapper(self, *args, **kwargs):
            aid, aname = _ids(self)
            if not kwargs.get("stream"):
                async def run_coro():
                    summary = summarize(kwargs.get("input") or (args[0] if args else ""))
                    _enter_run(aid, aname, summary)
                    try:
                        result = await orig_arun(self, *args, **kwargs)
                    except Exception:
                        _exit_run(aid, aname, f"error: {summary}")
                        raise
                    _exit_run(aid, aname, summary)
                    return result

                return run_coro()

            async def stream_gen():
                summary = summarize(kwargs.get("input") or (args[0] if args else ""))
                _enter_run(aid, aname, summary)
                try:
                    async for chunk in orig_arun(self, *args, **kwargs):
                        yield chunk
                finally:
                    _exit_run(aid, aname, summary)

            return stream_gen()

        return arun_wrapper

    def _wrap_run(orig_run):
        def run_wrapper(self, *args, **kwargs):
            aid, aname = _ids(self)
            summary = summarize(kwargs.get("input") or (args[0] if args else ""))
            _enter_run(aid, aname, summary)
            try:
                result = orig_run(self, *args, **kwargs)
            except Exception:
                _exit_run(aid, aname, f"error: {summary}")
                raise
            _exit_run(aid, aname, summary)
            return result

        return run_wrapper

    Agent.arun = _wrap_arun(Agent.arun)
    Agent.run = _wrap_run(Agent.run)
    Team.arun = _wrap_arun(Team.arun)
    Team.run = _wrap_run(Team.run)
    logger.info("Agno Agent/Team run methods instrumented for floor events")


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
        with bus._lock:
            depth = bus._run_depth.get(agent_id, 0)
            bus._run_depth[agent_id] = depth + 1
        if depth == 0:
            bus.publish(AgentEvent(agent_id, agent_name, STATE_WORKING, task_summary=summary))
        try:
            result = await original(*args, **kwargs)
        except Exception:
            with bus._lock:
                bus._run_depth[agent_id] = max(0, bus._run_depth.get(agent_id, 1) - 1)
                done = bus._run_depth[agent_id] == 0
            if done:
                bus.publish(AgentEvent(agent_id, agent_name, STATE_IDLE, task_summary=f"error: {summary}"))
            raise
        with bus._lock:
            bus._run_depth[agent_id] = max(0, bus._run_depth.get(agent_id, 1) - 1)
            done = bus._run_depth[agent_id] == 0
        if done:
            bus.publish(AgentEvent(agent_id, agent_name, STATE_IDLE, task_summary=summary))
            if on_done:
                on_done()
        return result

    setattr(obj, method_name, wrapper)
