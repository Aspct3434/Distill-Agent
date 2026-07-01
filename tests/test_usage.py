"""Tests for LLM usage accounting (src/usage.py) and the session token budget.

Covers the tracker itself, the instrumentation inside the llm_utils completion
wrappers, the AGENT_SESSION_TOKEN_BUDGET gate in the ReAct loop, and the
/api/usage gateway endpoint.
"""
from __future__ import annotations

import json
import sys
import unittest.mock
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import agent as agent_module
import usage as usage_module
from agent import AgentEngine, NormalizedMessage
from llm_utils import (
    _acompletion_stream_with_retry,
    _acompletion_with_retry,
)
from usage import (
    UNATTRIBUTED_SESSION,
    UsageTracker,
    current_session_id,
    usage_tracker,
)


@pytest.fixture(autouse=True)
def _clean_tracker():
    usage_tracker.reset()
    yield
    usage_tracker.reset()


# ---------------------------------------------------------------------------
# UsageTracker accounting
# ---------------------------------------------------------------------------

class TestUsageTracker:
    def test_record_accumulates_per_session(self):
        tracker = UsageTracker()
        tracker.record(
            model="unknown-model",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            session_id="s1",
        )
        tracker.record(
            model="unknown-model",
            usage={"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
            session_id="s1",
        )
        snapshot = tracker.snapshot()
        entry = snapshot["sessions"]["s1"]
        assert entry["calls"] == 2
        assert entry["prompt_tokens"] == 30
        assert entry["completion_tokens"] == 15
        assert entry["total_tokens"] == 45

    def test_snapshot_totals_span_sessions(self):
        tracker = UsageTracker()
        tracker.record(model="", usage={"total_tokens": 7}, session_id="a")
        tracker.record(model="", usage={"total_tokens": 3}, session_id="b")
        totals = tracker.snapshot()["totals"]
        assert totals["calls"] == 2
        assert totals["total_tokens"] == 10

    def test_none_usage_still_counts_the_call(self):
        tracker = UsageTracker()
        tracker.record(model="m", usage=None, session_id="s")
        entry = tracker.snapshot()["sessions"]["s"]
        assert entry["calls"] == 1
        assert entry["total_tokens"] == 0

    def test_usage_object_attributes_are_read(self):
        tracker = UsageTracker()
        tracker.record(
            model="m",
            usage=SimpleNamespace(prompt_tokens=4, completion_tokens=6, total_tokens=10),
            session_id="s",
        )
        assert tracker.session_total_tokens("s") == 10

    def test_total_falls_back_to_prompt_plus_completion(self):
        tracker = UsageTracker()
        tracker.record(
            model="m",
            usage={"prompt_tokens": 4, "completion_tokens": 6},
            session_id="s",
        )
        assert tracker.session_total_tokens("s") == 10

    def test_unknown_model_cost_is_zero_and_does_not_raise(self):
        tracker = UsageTracker()
        tracker.record(
            model="definitely-not-a-real-model-xyz",
            usage={"prompt_tokens": 100, "completion_tokens": 100},
            session_id="s",
        )
        assert tracker.snapshot()["sessions"]["s"]["estimated_cost_usd"] == 0.0

    def test_default_attribution_is_unattributed(self):
        tracker = UsageTracker()
        tracker.record(model="m", usage={"total_tokens": 1})
        assert UNATTRIBUTED_SESSION in tracker.snapshot()["sessions"]

    def test_contextvar_attribution(self):
        tracker = UsageTracker()
        token = current_session_id.set("ctx-session")
        try:
            tracker.record(model="m", usage={"total_tokens": 2})
        finally:
            current_session_id.reset(token)
        assert tracker.session_total_tokens("ctx-session") == 2

    def test_session_map_is_bounded(self, monkeypatch):
        monkeypatch.setattr(usage_module, "_MAX_TRACKED_SESSIONS", 2)
        tracker = UsageTracker()
        for sid in ("old", "mid", "new"):
            tracker.record(model="m", usage={"total_tokens": 1}, session_id=sid)
        sessions = tracker.snapshot()["sessions"]
        assert len(sessions) == 2
        assert "old" not in sessions


# ---------------------------------------------------------------------------
# llm_utils wrapper instrumentation
# ---------------------------------------------------------------------------

class TestWrapperInstrumentation:
    @pytest.mark.asyncio
    async def test_non_stream_wrapper_records_usage(self):
        response = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=9, total_tokens=20)
        )
        token = current_session_id.set("plain-call")
        try:
            with unittest.mock.patch("litellm.acompletion", return_value=response):
                result = await _acompletion_with_retry(model="m", messages=[])
        finally:
            current_session_id.reset(token)
        assert result is response
        assert usage_tracker.session_total_tokens("plain-call") == 20

    @pytest.mark.asyncio
    async def test_stream_wrapper_records_usage_from_final_chunk(self):
        chunk1 = SimpleNamespace(choices=[], usage=None)
        chunk2 = SimpleNamespace(
            choices=[],
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2, total_tokens=5),
        )

        async def fake_stream() -> AsyncIterator[Any]:
            yield chunk1
            yield chunk2

        token = current_session_id.set("stream-call")
        try:
            with unittest.mock.patch("litellm.acompletion", return_value=fake_stream()):
                stream = await _acompletion_stream_with_retry(model="m", messages=[])
                seen = [chunk async for chunk in stream]
        finally:
            current_session_id.reset(token)
        assert seen == [chunk1, chunk2]
        assert usage_tracker.session_total_tokens("stream-call") == 5

    @pytest.mark.asyncio
    async def test_stream_wrapper_falls_back_to_chunk_builder(self):
        chunk = SimpleNamespace(choices=[])

        async def fake_stream() -> AsyncIterator[Any]:
            yield chunk

        built = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2)
        )
        token = current_session_id.set("builder-call")
        try:
            with (
                unittest.mock.patch("litellm.acompletion", return_value=fake_stream()),
                unittest.mock.patch("litellm.stream_chunk_builder", return_value=built),
            ):
                stream = await _acompletion_stream_with_retry(model="m", messages=[])
                _ = [c async for c in stream]
        finally:
            current_session_id.reset(token)
        assert usage_tracker.session_total_tokens("builder-call") == 2


# ---------------------------------------------------------------------------
# AGENT_SESSION_TOKEN_BUDGET gate in the ReAct loop
# ---------------------------------------------------------------------------

class _EmptyMemory:
    def retrieve_context(self, query: str, query_type: str) -> dict[str, Any]:
        return {"query_type": query_type, "results": []}

    def store_event(
        self, session_id: str, raw_text: str, entities: dict[str, Any]
    ) -> str:
        return ""


class _NoTools:
    async def list_all_tools(self) -> list[dict[str, Any]]:
        return []


def _completion(content: str) -> Any:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=content, tool_calls=None),
            )
        ]
    )


async def _stream_response(response: Any) -> AsyncIterator[Any]:
    yield SimpleNamespace(
        _response=response,
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=response.choices[0].message.content, tool_calls=None
                )
            )
        ],
    )


def _stream_chunk_builder(chunks: list[Any], messages: Any = None) -> Any:
    return chunks[-1]._response


class TestSessionTokenBudget:
    @pytest.mark.asyncio
    async def test_exhausted_budget_blocks_llm_calls(self, monkeypatch):
        monkeypatch.setattr(agent_module, "_SESSION_TOKEN_BUDGET", 100)
        usage_tracker.record(
            model="m", usage={"total_tokens": 150}, session_id="budget-test"
        )

        async def forbidden(**kwargs: Any) -> Any:
            raise AssertionError("LLM must not be called once the budget is spent")

        monkeypatch.setattr(agent_module.litellm, "acompletion", forbidden)
        engine = AgentEngine(memory=_EmptyMemory(), tools=_NoTools(), model="test-model")
        events = [
            event
            async for event in engine.stream_task(
                NormalizedMessage(
                    session_id="budget-test",
                    role="user",
                    content="make a simple website about the importance of sleep",
                )
            )
        ]
        final = next(e for e in events if e["type"] == "final_answer")
        assert final["reason"] == "budget_exhausted"
        assert "AGENT_SESSION_TOKEN_BUDGET" in final["content"]

    @pytest.mark.asyncio
    async def test_budget_with_headroom_lets_the_task_run(self, monkeypatch):
        monkeypatch.setattr(agent_module, "_SESSION_TOKEN_BUDGET", 10_000)
        usage_tracker.record(
            model="m", usage={"total_tokens": 10}, session_id="budget-ok-test"
        )

        async def scripted(**kwargs: Any) -> Any:
            return _stream_response(_completion("All done."))

        monkeypatch.setattr(agent_module.litellm, "acompletion", scripted)
        monkeypatch.setattr(
            agent_module.litellm, "stream_chunk_builder", _stream_chunk_builder
        )
        engine = AgentEngine(memory=_EmptyMemory(), tools=_NoTools(), model="test-model")
        events = [
            event
            async for event in engine.stream_task(
                NormalizedMessage(
                    session_id="budget-ok-test",
                    role="user",
                    content="make a simple website about the importance of sleep",
                )
            )
        ]
        texts = [e for e in events if e["type"] == "text"]
        assert texts and "All done." in texts[-1]["content"]
        # The call itself was attributed to the session via the ContextVar.
        entry = usage_tracker.snapshot()["sessions"]["budget-ok-test"]
        assert entry["calls"] >= 2  # seed record + at least one real call


# ---------------------------------------------------------------------------
# /api/usage gateway endpoint
# ---------------------------------------------------------------------------

class TestUsageEndpoint:
    @pytest.mark.asyncio
    async def test_endpoint_reports_snapshot_and_budget(self, monkeypatch):
        import gateway

        monkeypatch.setenv("AGENT_SESSION_TOKEN_BUDGET", "1234")
        usage_tracker.record(
            model="m", usage={"total_tokens": 42}, session_id="api-session"
        )
        payload = await gateway.usage()
        assert payload["session_token_budget"] == 1234
        assert payload["totals"]["total_tokens"] == 42
        assert payload["sessions"]["api-session"]["calls"] == 1
        json.dumps(payload)  # must be JSON-serialisable
