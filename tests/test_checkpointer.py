"""Regression tests for checkpoint retention across conversation turns."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import checkpointer


@pytest.mark.asyncio
async def test_retention_keeps_latest_when_step_numbers_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(checkpointer, "_RETAIN_PER_SESSION", 2)
    path = await checkpointer.initialize_checkpoints_db(tmp_path / "checkpoints.db")
    store = checkpointer.StateCheckpointer(path)
    oldest = await store.save_checkpoint("s", 10, {"turn": 1})
    previous = await store.save_checkpoint("s", 11, {"turn": 1})
    newest = await store.save_checkpoint("s", 1, {"turn": 2})

    assert await store.load_checkpoint(newest) == {"turn": 2}
    assert await store.load_checkpoint(previous) == {"turn": 1}
    with pytest.raises(KeyError):
        await store.load_checkpoint(oldest)


@pytest.mark.asyncio
async def test_retention_with_equal_steps_is_deterministic_and_session_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(checkpointer, "_RETAIN_PER_SESSION", 1)
    path = await checkpointer.initialize_checkpoints_db(tmp_path / "checkpoints.db")
    store = checkpointer.StateCheckpointer(path)
    other = await store.save_checkpoint("other", 1, {"turn": "other"})
    oldest = await store.save_checkpoint("s", 1, {"turn": 1})
    newest = await store.save_checkpoint("s", 1, {"turn": 2})

    assert await store.load_checkpoint(newest) == {"turn": 2}
    assert await store.load_checkpoint(other) == {"turn": "other"}
    with pytest.raises(KeyError):
        await store.load_checkpoint(oldest)
