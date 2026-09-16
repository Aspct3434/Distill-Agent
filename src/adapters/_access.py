"""Shared access-control helpers for inbound messaging channels."""
from __future__ import annotations

import os


def allow_public_channels() -> bool:
    """Return whether the operator explicitly opted into public channel access."""
    return os.getenv("AGENT_ALLOW_PUBLIC_CHANNELS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
