from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adapters._commands import is_passive_greeting, is_stop_command


def test_passive_greeting_matches_only_greeting_text() -> None:
    assert is_passive_greeting("hello")
    assert is_passive_greeting("Hi!")
    assert is_passive_greeting("good morning")
    assert not is_passive_greeting("hello build me a website")
    assert not is_passive_greeting("hi, install this")


def test_stop_command_still_matches_control_text() -> None:
    assert is_stop_command("Stop")
    assert is_stop_command("cancel!")
    assert is_stop_command("/stop now")
    assert not is_stop_command("hello")
    assert not is_stop_command("stop adding so many animations")
    assert not is_stop_command("how do I stop a server?")
