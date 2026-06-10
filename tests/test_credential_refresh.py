"""Tests for llm_utils credential refreshers (OAuth key refresh before LLM calls)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import llm_utils
from llm_utils import (
    _acompletion_stream_with_retry,
    _acompletion_with_retry,
    register_credential_refresher,
)


async def test_refresher_runs_before_completion(monkeypatch) -> None:
    monkeypatch.setattr(llm_utils, "_credential_refreshers", [])
    calls: list[str] = []
    register_credential_refresher(lambda: calls.append("refreshed"))

    mock_llm = AsyncMock(return_value="ok")
    with patch.object(llm_utils.litellm, "acompletion", new=mock_llm):
        result = await _acompletion_with_retry(model="m", messages=[])

    assert result == "ok"
    assert calls == ["refreshed"]
    mock_llm.assert_awaited_once()


async def test_refresher_runs_before_streaming_completion(monkeypatch) -> None:
    monkeypatch.setattr(llm_utils, "_credential_refreshers", [])
    calls: list[str] = []
    register_credential_refresher(lambda: calls.append("refreshed"))

    mock_llm = AsyncMock(return_value="stream")
    with patch.object(llm_utils.litellm, "acompletion", new=mock_llm):
        result = await _acompletion_stream_with_retry(model="m", messages=[])

    assert result == "stream"
    assert calls == ["refreshed"]
    assert mock_llm.await_args.kwargs["stream"] is True


async def test_failing_refresher_does_not_break_the_call(monkeypatch) -> None:
    monkeypatch.setattr(llm_utils, "_credential_refreshers", [])

    def boom() -> None:
        raise RuntimeError("refresh exploded")

    register_credential_refresher(boom)
    with patch.object(llm_utils.litellm, "acompletion", new=AsyncMock(return_value="ok")):
        assert await _acompletion_with_retry(model="m", messages=[]) == "ok"


async def test_duplicate_registration_runs_once(monkeypatch) -> None:
    monkeypatch.setattr(llm_utils, "_credential_refreshers", [])
    calls: list[int] = []

    def refresher() -> None:
        calls.append(1)

    register_credential_refresher(refresher)
    register_credential_refresher(refresher)
    with patch.object(llm_utils.litellm, "acompletion", new=AsyncMock(return_value="ok")):
        await _acompletion_with_retry(model="m", messages=[])

    assert calls == [1]
