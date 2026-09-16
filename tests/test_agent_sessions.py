"""Conversation isolation and checkpoint replay across agent entry points."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import agent as agent_module
from agent import AgentEngine, ExecutionStep, NormalizedMessage
from checkpointer import StateCheckpointer, initialize_checkpoints_db
from session_store import SessionStore


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setattr(agent_module, "_BOOTSTRAP_SESSIONS", False)
    engine = AgentEngine(
        memory=SimpleNamespace(),
        tools=SimpleNamespace(list_all_tools=AsyncMock(return_value=[])),
        model="test",
    )
    monkeypatch.setattr(engine, "_fetch_context", AsyncMock(return_value={"results": []}))
    monkeypatch.setattr(engine, "_build_host_environment_message", lambda: {
        "role": "system", "content": "test host",
    })
    return engine


def message(session="s", text="prompt"):
    return NormalizedMessage(session_id=session, role="user", content=text)


@pytest.mark.asyncio
async def test_same_session_turns_are_serialized(engine, monkeypatch):
    started = asyncio.Event()
    finish = asyncio.Event()
    prompts = []

    async def react(_session_id, prompt, messages, _tools):
        prompts.append(prompt)
        if prompt == "first":
            started.set()
            await finish.wait()
        messages.append({"role": "assistant", "content": prompt + " answer"})
        yield {"type": "final_answer", "content": prompt + " answer"}

    monkeypatch.setattr(engine, "_stream_react_loop", react)
    first = asyncio.create_task(engine.process_task(message(text="first")))
    await asyncio.wait_for(started.wait(), timeout=2)
    second = asyncio.create_task(engine.process_task(message(text="second")))
    try:
        await asyncio.sleep(0)
        assert prompts == ["first"]
        finish.set()
        assert await asyncio.gather(first, second) == ["first answer", "second answer"]
        conversation = [m["content"] for m in engine._histories["s"] if m["role"] != "system"]
        assert conversation == ["first", "first answer", "second", "second answer"]
        assert not engine._session_locks
    finally:
        finish.set()
        await asyncio.gather(first, second, return_exceptions=True)


@pytest.mark.asyncio
async def test_different_sessions_run_concurrently_and_survive_eviction(engine, monkeypatch):
    monkeypatch.setattr(agent_module, "_MAX_SESSIONS", 1)
    started = {session: asyncio.Event() for session in ("one", "two")}
    finish = asyncio.Event()

    async def react(session_id, _prompt, _messages, _tools):
        started[session_id].set()
        await finish.wait()
        yield {"type": "final_answer", "content": session_id}

    monkeypatch.setattr(engine, "_stream_react_loop", react)
    tasks = [asyncio.create_task(engine.process_task(message(session))) for session in started]
    try:
        await asyncio.wait_for(asyncio.gather(*(event.wait() for event in started.values())), 2)
        assert set(engine._histories) == {"one", "two"}
        finish.set()
        assert await asyncio.gather(*tasks) == ["one", "two"]
        assert len(engine._histories) == 1
        assert not engine._session_locks
    finally:
        finish.set()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_turn_releases_session_for_waiting_turn(engine, monkeypatch):
    started = asyncio.Event()

    async def react(_session_id, prompt, _messages, _tools):
        if prompt == "first":
            started.set()
            await asyncio.Event().wait()
        yield {"type": "final_answer", "content": prompt}

    monkeypatch.setattr(engine, "_stream_react_loop", react)
    first = asyncio.create_task(engine.process_task(message(text="first")))
    await asyncio.wait_for(started.wait(), timeout=2)
    second = asyncio.create_task(engine.process_task(message(text="second")))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert await asyncio.wait_for(second, timeout=2) == "second"
    assert not engine._session_locks


@pytest.mark.asyncio
@pytest.mark.parametrize("with_steps", [False, True])
async def test_replay_restores_state_and_followup_uses_resumed_history(engine, monkeypatch, with_steps):
    payload = {"session_id": "s", "messages": [
        {"role": "user", "content": "earlier question"},
        {"role": "assistant", "content": "earlier answer"},
        {"role": "user", "content": "current question"},
    ]}
    saved_step = {
        "kind": "tool_result",
        "content": '{"path":"/saved.txt","written":true,"exists":true}',
        "metadata": {"tool_name": "write_text_file", "arguments": {}, "is_error": False},
    }
    if with_steps:
        payload["steps"] = [saved_step]
    engine._checkpointer = SimpleNamespace(load_checkpoint=AsyncMock(return_value=payload))
    engine._histories["s"] = [{"role": "user", "content": "stale future turn"}]
    engine._session_steps["s"] = [ExecutionStep("tool_result", "unrelated")]
    engine._artifact_ledger("s").record([("File", "/stale.txt")], "write_text_file")
    observed = []

    async def react(session_id, prompt, messages, _tools):
        observed.append(prompt)
        if len(observed) == 1:
            assert engine._histories[session_id] is messages
            assert [step.content for step in engine._session_steps[session_id]] == (
                [saved_step["content"]] if with_steps else []
            )
            artifacts = engine._artifact_ledger(session_id).recent_first()
            assert all(value != "/stale.txt" for _, value in artifacts)
            assert any(value == "/saved.txt" for _, value in artifacts) is with_steps
        messages.append({"role": "assistant", "content": "replayed answer"})
        yield {"type": "final_answer", "content": "replayed answer"}

    monkeypatch.setattr(engine, "_stream_react_loop", react)
    events = [event async for event in engine.replay_from_checkpoint("checkpoint", "correction")]
    assert events[-1]["content"] == "replayed answer"
    assert observed == ["current question"]
    assert engine._histories["s"][-2] == {"role": "system", "content": "correction"}
    await engine.process_task(message(text="followup"))
    assert "replayed answer" in [m["content"] for m in engine._histories["s"]]
    assert observed == ["current question", "followup"]


@pytest.mark.asyncio
async def test_memory_recall_is_scoped_to_active_conversation(engine, tmp_path):
    engine._session_store = SessionStore(tmp_path / "sessions.db")
    engine._session_store.add_turn("s", "user", "shared keyword visible")
    engine._session_store.add_turn("other", "user", "shared keyword private")
    result = json.loads(await engine._recall_memory({"query": "shared keyword"}, "s"))
    assert len(result["results"]) == 1
    assert result["results"][0]["session_id"] == "s"
    assert "private" not in result["results"][0]["content"]


@pytest.mark.asyncio
async def test_replay_waits_for_active_turn_in_same_session(engine, monkeypatch):
    started = asyncio.Event()
    finish = asyncio.Event()
    prompts = []
    engine._checkpointer = SimpleNamespace(load_checkpoint=AsyncMock(return_value={
        "session_id": "s", "messages": [{"role": "user", "content": "replay"}],
    }))

    async def react(_session_id, prompt, _messages, _tools):
        prompts.append(prompt)
        if prompt == "live":
            started.set()
            await finish.wait()
        yield {"type": "final_answer", "content": prompt}

    async def replay():
        return [event async for event in engine.replay_from_checkpoint("checkpoint")]

    monkeypatch.setattr(engine, "_stream_react_loop", react)
    live = asyncio.create_task(engine.process_task(message(text="live")))
    await asyncio.wait_for(started.wait(), 2)
    resumed = asyncio.create_task(replay())
    try:
        await asyncio.sleep(0)
        assert prompts == ["live"]
        finish.set()
        await asyncio.wait_for(asyncio.gather(live, resumed), 2)
        assert prompts == ["live", "replay"]
        assert not engine._session_locks
    finally:
        finish.set()
        await asyncio.gather(live, resumed, return_exceptions=True)


@pytest.mark.asyncio
async def test_closing_stream_releases_session_lock(engine):
    stream = engine.stream_task(message())
    assert (await anext(stream))["type"] == "status"
    assert engine._session_locks["s"].locked()
    await stream.aclose()
    assert not engine._session_locks


@pytest.mark.asyncio
async def test_checkpoint_persists_tool_execution_evidence(engine, tmp_path, monkeypatch):
    path = await initialize_checkpoints_db(tmp_path / "checkpoints.db")
    engine._checkpointer = StateCheckpointer(path)
    engine._tools.list_all_tools.return_value = [{
        "name": "write_text_file", "server": "filesystem", "inputSchema": {"type": "object"},
    }]
    call = SimpleNamespace(id="call", function=SimpleNamespace(
        name="write_text_file", arguments='{"path":"/saved.txt","content":"hello"}',
    ))
    responses = [
        SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="tool_calls", message=SimpleNamespace(content=None, tool_calls=[call]),
        )]),
        SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(content="done", tool_calls=[]),
        )]),
    ]
    monkeypatch.setattr(agent_module, "_acompletion_stream_with_retry", AsyncMock(side_effect=responses))
    monkeypatch.setattr(engine, "_execute_single_tool", AsyncMock(return_value=(
        '{"written":true,"exists":true,"path":"/saved.txt"}', False, "filesystem",
    )))
    assert "done" in await engine.process_task(message(text="write a file"))
    checkpoints = await engine._checkpointer.list_checkpoints("s")
    steps = checkpoints[0]["state_payload"]["steps"]
    assert steps[-1]["metadata"]["tool_name"] == "write_text_file"
    assert steps[-1]["metadata"]["is_error"] is False
    assert json.loads(steps[-1]["content"])["path"] == "/saved.txt"
