"""AgentActivityBus tests — publish/subscribe, reentrancy, handoffs, snapshot."""
import asyncio
import json

import pytest

from app.telemetry.agent_events import (
    STATE_HANDOFF,
    STATE_IDLE,
    STATE_WORKING,
    AgentEvent,
    bus as global_bus,
    instrument_agent,
)
from app.telemetry.floor_config import fixed_agents


@pytest.fixture()
def bus():
    """The real module-level singleton — instrument_agent publishes to it."""
    # drain any leftover events between tests
    for sub in list(global_bus._subscribers):
        while not sub.empty():
            sub.get_nowait()
    return global_bus


@pytest.mark.asyncio
async def test_publish_reaches_subscriber(bus):
    q = bus.subscribe()
    bus.publish(AgentEvent("sales_agent", "Sales Agent", STATE_WORKING, task_summary="qualifying"))
    event = await asyncio.wait_for(q.get(), timeout=2)
    assert event["agent_id"] == "sales_agent"
    assert event["state"] == "working"


@pytest.mark.asyncio
async def test_invalid_state_ignored(bus):
    q = bus.subscribe()
    bus.publish(AgentEvent("sales_agent", "Sales Agent", "dancing"))
    assert q.empty()


@pytest.mark.asyncio
async def test_snapshot_contains_all_fixed_desks(bus):
    snap = bus.snapshot(fixed_agents())
    ids = {a["agent_id"] for a in snap["agents"]}
    assert len(ids) == 11
    assert "top_agent" in ids
    top = next(a for a in snap["agents"] if a["agent_id"] == "top_agent")
    assert top["desk"] == {"x": 480, "y": 60}  # boss cabin


@pytest.mark.asyncio
async def test_instrument_agent_working_and_idle(bus):
    class FakeAgent:
        name = "Test Agent"

        async def arun(self, *a, **k):
            return "ok"

    agent = FakeAgent()
    aid = instrument_agent(agent)
    q = bus.subscribe()

    await agent.arun(input="hello")
    states = []
    while not q.empty():
        states.append(q.get_nowait())
    assert any(e["state"] == "working" and e["agent_id"] == aid for e in states)
    assert any(e["state"] == "idle" for e in states)


@pytest.mark.asyncio
async def test_handoff_event_has_target(bus):
    """Nested run: outer agent delegates to inner -> handoff with target id."""
    class Outer:
        name = "Top Agent"

        async def arun(self, *a, **k):
            await inner.arun(input="subtask")
            return "done"

    class Inner:
        name = "Sales Agent"

        async def arun(self, *a, **k):
            return "ok"

    inner = Inner()
    instrument_agent(inner)
    outer = Outer()
    instrument_agent(outer)

    q = bus.subscribe()
    await outer.arun(input="delegate please")

    events = []
    while not q.empty():
        events.append(q.get_nowait())

    handoffs = [e for e in events if e["state"] == STATE_HANDOFF]
    assert handoffs, f"expected a handoff among: {[e['state'] for e in events]}"
    assert handoffs[0]["target_agent_id"] is not None


@pytest.mark.asyncio
async def test_reentrancy_no_flip_flop(bus):
    """Concurrent runs of the same agent: state stays working until all finish."""

    class Agent:
        name = "Busy Agent"

        async def arun(self, *a, **k):
            await asyncio.sleep(0.05)
            return "ok"

    agent = Agent()
    instrument_agent(agent)
    q = bus.subscribe()

    await asyncio.gather(agent.arun(input="1"), agent.arun(input="2"))

    events = []
    while not q.empty():
        events.append(q.get_nowait())
    working_count = sum(1 for e in events if e["state"] == STATE_WORKING)
    idle_count = sum(1 for e in events if e["state"] == STATE_IDLE)
    assert working_count == 1  # entered once despite 2 concurrent runs
    assert idle_count == 1     # exited once


def test_roster_add_remove_broadcast(bus):
    q = bus.subscribe()
    bus.roster_add({"agent_id": "client_x", "name": "Client X Agent", "desk": {"x": 0, "y": 0}})
    add_ev = q.get_nowait()
    assert add_ev["kind"] == "roster" and add_ev["action"] == "add"

    bus.roster_remove("client_x")
    rm_ev = q.get_nowait()
    assert rm_ev["kind"] == "roster" and rm_ev["action"] == "remove"
