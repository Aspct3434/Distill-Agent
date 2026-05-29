from __future__ import annotations

_STOP_WORDS = frozenset({"stop", "cancel", "interrupt", "abort"})
PASSIVE_GREETING_RESPONSE = "Hello! Send me a task and I'll get it done. Type /help for commands."

_PASSIVE_GREETINGS = frozenset(
    {
        "hello",
        "hello there",
        "hey",
        "hey there",
        "hi",
        "hi there",
        "good morning",
        "good afternoon",
        "good evening",
        "sup",
        "what's up",
        "whats up",
        "yo",
    }
)


def _normalise_control_text(text: str) -> str:
    """Return a compact, punctuation-trimmed control-message shape."""
    return " ".join(text.strip().lower().strip(".!? \t\r\n").split())


def is_stop_command(text: str) -> bool:
    """True for short user control messages that should cancel the active turn."""
    normalized = _normalise_control_text(text)
    return normalized in _STOP_WORDS or normalized.startswith("/stop")


def is_passive_greeting(text: str) -> bool:
    """True for greeting-only messages that should not start an agent task."""
    return _normalise_control_text(text) in _PASSIVE_GREETINGS
