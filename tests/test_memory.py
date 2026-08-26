"""SuperMemory layer tests — audit, vaults, working memory, playbooks."""
import pytest

from app.memory.client_vault import ClientVault


@pytest.mark.asyncio
async def test_audit_log_and_history(supermemory):
    await supermemory.audit.log_action(
        agent_id="sales_agent", action="qualified_lead", details={"score": 32}
    )
    history = await supermemory.audit.get_agent_history("sales_agent")
    assert len(history) == 1
    assert history[0]["action"] == "qualified_lead"
    assert history[0]["details"]["score"] == 32


@pytest.mark.asyncio
async def test_audit_summary_counts(supermemory):
    await supermemory.audit.log_action(agent_id="a", action="x")
    await supermemory.audit.log_action(agent_id="a", action="y")
    await supermemory.audit.log_action(agent_id="b", action="z")
    summary = await supermemory.audit.get_summary()
    assert summary["total_actions"] == 3
    assert summary["agents"]["a"] == 2


@pytest.mark.asyncio
async def test_client_vault_roundtrip(supermemory):
    vault = ClientVault(client_id="acme", backend=supermemory.backend)
    await vault.store("profile", {"name": "Acme", "status": "active"})
    got = await vault.retrieve("profile")
    assert got == {"name": "Acme", "status": "active"}


@pytest.mark.asyncio
async def test_client_vault_isolation(supermemory):
    """Strict separation: one client's vault must never leak to another."""
    v1 = ClientVault(client_id="acme", backend=supermemory.backend)
    v2 = ClientVault(client_id="globex", backend=supermemory.backend)
    await v1.store("profile", {"name": "Acme", "secret": "A"})
    await v2.store("profile", {"name": "Globex"})

    acme_view = await v2.retrieve("profile")
    assert acme_view != {"name": "Acme", "secret": "A"}
    # and from the raw backend, entries are namespaced by client
    leaked = await supermemory.backend.query(
        "client", filters={"client_id": "globex"}, limit=50
    )
    for entry in leaked:
        assert entry.value.get("secret") != "A"


@pytest.mark.asyncio
async def test_working_memory_task_lifecycle(supermemory):
    task_id = await supermemory.working.create_task(
        "top_agent", "research", {"topic": "competitors"}
    )
    active = await supermemory.working.get_active_tasks()
    assert len(active) == 1

    await supermemory.working.complete_task(task_id, result={"done": True})
    active_after = await supermemory.working.get_active_tasks()
    assert len(active_after) == 0


@pytest.mark.asyncio
async def test_playbooks_load_from_disk(supermemory):
    loaded = await supermemory.load_playbooks()
    assert isinstance(loaded, dict)
    # repo ships rate_card.json + sop.json
    assert "rate_card" in loaded or "sop" in loaded
