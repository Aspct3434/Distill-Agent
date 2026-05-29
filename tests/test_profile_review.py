from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent import _profile_update_signal
from memory import UserProfileStore


def test_profile_signal_ignores_ordinary_tasks() -> None:
    assert not _profile_update_signal("create a dashboard from the sample data")
    assert not _profile_update_signal("what public IPv4 does this runtime use")


def test_profile_signal_accepts_explicit_preferences() -> None:
    assert _profile_update_signal("remember I prefer brief responses")
    assert _profile_update_signal("call me Alex")


def test_pending_profile_updates_are_not_injected_until_approved(tmp_path: Path) -> None:
    store = UserProfileStore(profile_dir=tmp_path)

    update_id = store.propose_update({"preferences": ["prefers brief responses"]})

    assert update_id
    assert "brief responses" not in store.as_context_string()
    assert store.get()["pending_updates"]

    assert store.approve_pending(update_id) == 1

    assert "brief responses" in store.as_context_string()
    assert store.get()["pending_updates"] == []


def test_pending_profile_updates_can_be_rejected(tmp_path: Path) -> None:
    store = UserProfileStore(profile_dir=tmp_path)

    update_id = store.propose_update({"preferences": ["prefers unverified claims"]})

    assert update_id
    assert store.reject_pending(update_id) == 1
    assert "unverified claims" not in store.as_context_string()
    assert store.get()["pending_updates"] == []
