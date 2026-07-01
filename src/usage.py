"""Process-wide LLM usage accounting: tokens, calls, and estimated cost.

Like ``llm_utils``, this module has **no** imports from the rest of the agent
stack so any layer can use it without creating circular dependencies.

Attribution works through a :class:`~contextvars.ContextVar`: the agent sets
``current_session_id`` when it starts handling a message, and the completion
wrappers in ``llm_utils`` record every call against whatever session is
current. Calls made outside any session (e.g. background skill distillation)
land under :data:`UNATTRIBUTED_SESSION`.
"""
from __future__ import annotations

import threading
import time
from contextvars import ContextVar
from typing import Any

import litellm

UNATTRIBUTED_SESSION = "_unattributed"

# Set per handled message by AgentEngine; inherited by tasks it spawns.
current_session_id: ContextVar[str] = ContextVar(
    "distill_usage_session", default=UNATTRIBUTED_SESSION
)

# Same spirit as AGENT_MAX_SESSIONS in agent.py: bound the per-session map so
# a long-lived gateway process cannot grow it without limit.
_MAX_TRACKED_SESSIONS = 512


def _usage_int(usage: Any, key: str) -> int:
    """Read a token count from a litellm ``Usage`` object or a plain dict."""
    value = getattr(usage, key, None)
    if value is None and isinstance(usage, dict):
        value = usage.get(key)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Best-effort USD cost from litellm's price table; 0.0 when unknown."""
    if not model or not (prompt_tokens or completion_tokens):
        return 0.0
    try:
        prompt_cost, completion_cost = litellm.cost_per_token(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        return float(prompt_cost or 0.0) + float(completion_cost or 0.0)
    except Exception:
        return 0.0


def _empty_entry() -> dict[str, Any]:
    return {
        "calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
        "last_call_at": 0.0,
    }


class UsageTracker:
    """Accumulates LLM call counts, token totals, and estimated cost per session."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, dict[str, Any]] = {}

    def record(
        self,
        *,
        model: str,
        usage: Any,
        session_id: str | None = None,
    ) -> None:
        """Record one completed LLM call.

        *usage* may be a litellm ``Usage`` object, a dict, or ``None`` (the
        call is still counted so the call counter stays truthful).
        """
        sid = session_id or current_session_id.get()
        prompt = _usage_int(usage, "prompt_tokens")
        completion = _usage_int(usage, "completion_tokens")
        total = _usage_int(usage, "total_tokens") or (prompt + completion)
        cost = _estimate_cost_usd(model, prompt, completion)
        with self._lock:
            entry = self._sessions.setdefault(sid, _empty_entry())
            entry["calls"] += 1
            entry["prompt_tokens"] += prompt
            entry["completion_tokens"] += completion
            entry["total_tokens"] += total
            entry["estimated_cost_usd"] += cost
            entry["last_call_at"] = time.time()
            self._evict_locked()

    def record_response(self, response: Any, *, model: str = "") -> None:
        """Record a non-streaming completion response object."""
        usage = getattr(response, "usage", None)
        if usage is None and isinstance(response, dict):
            usage = response.get("usage")
        self.record(model=model or str(getattr(response, "model", "") or ""), usage=usage)

    def session_total_tokens(self, session_id: str) -> int:
        with self._lock:
            entry = self._sessions.get(session_id)
            return int(entry["total_tokens"]) if entry else 0

    def snapshot(self) -> dict[str, Any]:
        """Totals plus a per-session breakdown, safe to serialise as JSON."""
        with self._lock:
            sessions = {sid: dict(entry) for sid, entry in self._sessions.items()}
        totals = _empty_entry()
        for entry in sessions.values():
            for key in ("calls", "prompt_tokens", "completion_tokens", "total_tokens"):
                totals[key] += entry[key]
            totals["estimated_cost_usd"] += entry["estimated_cost_usd"]
            totals["last_call_at"] = max(totals["last_call_at"], entry["last_call_at"])
        return {"totals": totals, "sessions": sessions}

    def reset(self) -> None:
        with self._lock:
            self._sessions.clear()

    def _evict_locked(self) -> None:
        while len(self._sessions) > _MAX_TRACKED_SESSIONS:
            oldest = min(self._sessions, key=lambda sid: self._sessions[sid]["last_call_at"])
            del self._sessions[oldest]


# Process-wide singleton used by llm_utils, agent, and gateway.
usage_tracker = UsageTracker()
