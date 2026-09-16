"""WebSocket lifecycle regressions without live LLM or network dependencies."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import WebSocketDisconnect

import gateway


class FakeWebSocket:
    def __init__(self):
        self.incoming = asyncio.Queue()
        self.outgoing = asyncio.Queue()

    async def accept(self):
        pass

    async def receive_text(self):
        message = await self.incoming.get()
        if isinstance(message, Exception):
            raise message
        return message

    async def send_text(self, text):
        await self.outgoing.put(json.loads(text))

    async def receive(self):
        return await asyncio.wait_for(self.outgoing.get(), timeout=2)


@pytest.fixture
def stream_state(monkeypatch):
    monkeypatch.setattr(gateway, "_websocket_authorized", lambda ws: True)
    monkeypatch.setattr(gateway, "_rate_limit_key_for_websocket", lambda ws: "test")
    monkeypatch.setattr(gateway, "_rate_limiter", gateway._SlidingWindowRateLimiter(0))
    monkeypatch.setattr(gateway.app.state, "active_stream_tasks", {}, raising=False)
    return gateway.app.state


@asynccontextmanager
async def connection():
    ws = FakeWebSocket()
    task = asyncio.create_task(gateway.ws_stream(ws))
    try:
        yield ws
    finally:
        await ws.incoming.put(WebSocketDisconnect())
        try:
            await asyncio.wait_for(task, timeout=2)
        finally:
            if not task.done():
                task.cancel()


@pytest.mark.parametrize("payload", [
    "{", "[]", "null", '{"session_id": []}',
    '{"session_id": null}', '{"text": {}}', '{"text": "   "}',
])
async def test_invalid_message_does_not_break_connection(stream_state, monkeypatch, payload):
    async def stream_task(message):
        yield {"type": "final_answer", "content": message.content}

    monkeypatch.setattr(stream_state, "engine", SimpleNamespace(stream_task=stream_task), raising=False)
    async with connection() as ws:
        await ws.incoming.put(payload)
        assert (await ws.receive())["type"] == "error"
        await ws.incoming.put('{"session_id": "s", "text": "hello"}')
        assert await ws.receive() == {"type": "final_answer", "content": "hello"}


async def test_engine_failure_is_reported_and_connection_can_retry(stream_state, monkeypatch):
    async def stream_task(message):
        if message.content == "fail":
            raise RuntimeError("provider unavailable")
        yield {"type": "final_answer", "content": "recovered"}

    monkeypatch.setattr(stream_state, "engine", SimpleNamespace(stream_task=stream_task), raising=False)
    async with connection() as ws:
        await ws.incoming.put('{"session_id": "s", "text": "fail"}')
        assert (await ws.receive())["type"] == "error"
        await ws.incoming.put('{"session_id": "s", "text": "retry"}')
        assert (await ws.receive())["content"] == "recovered"


async def test_second_connection_cannot_overwrite_active_session(stream_state, monkeypatch):
    stopped = asyncio.Event()

    async def stream_task(message):
        try:
            yield {"type": "status", "message": "working"}
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr(stream_state, "engine", SimpleNamespace(stream_task=stream_task), raising=False)
    async with connection() as first, connection() as second:
        await first.incoming.put('{"session_id": "shared", "text": "first"}')
        assert (await first.receive())["type"] == "status"
        original = stream_state.active_stream_tasks["shared"]
        await second.incoming.put('{"session_id": "shared", "text": "second"}')
        assert (await second.receive())["type"] == "error"
        assert stream_state.active_stream_tasks["shared"] is original
        await first.incoming.put('{"session_id": "shared", "type": "cancel"}')
        assert (await first.receive())["reason"] == "cancelled"
        await asyncio.wait_for(stopped.wait(), timeout=2)
    assert stream_state.active_stream_tasks == {}


async def test_disconnect_cancels_active_turn(stream_state, monkeypatch):
    stopped = asyncio.Event()

    async def stream_task(message):
        try:
            yield {"type": "status", "message": "working"}
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr(stream_state, "engine", SimpleNamespace(stream_task=stream_task), raising=False)
    async with connection() as ws:
        await ws.incoming.put('{"session_id": "s", "text": "hello"}')
        await ws.receive()
    assert stopped.is_set()
    assert stream_state.active_stream_tasks == {}


async def test_replay_returns_final_answer(stream_state, monkeypatch):
    async def replay_from_checkpoint(checkpoint_id, user_correction):
        yield {"type": "final_answer", "content": "replayed result"}

    monkeypatch.setattr(
        stream_state, "engine", SimpleNamespace(replay_from_checkpoint=replay_from_checkpoint),
        raising=False,
    )
    result = await gateway.replay_checkpoint("checkpoint", gateway.ReplayCheckpointRequest())
    assert result["final_output"] == "replayed result"
