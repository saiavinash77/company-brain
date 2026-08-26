"""Shared fixtures: temp SQLite-backed SuperMemory, isolated from real data."""
import asyncio
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture()
def backend(tmp_path):
    from app.memory.local_backend import LocalBackend

    return LocalBackend(db_path=tmp_path / "test_memory.db")


@pytest.fixture()
def supermemory(backend):
    from app.memory.super_memory import SuperMemory

    return SuperMemory(backend=backend)
