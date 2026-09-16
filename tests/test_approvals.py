"""Tests for the human-in-the-loop command approval gate."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from approvals import ApprovalGate


@pytest.mark.parametrize("mode", ["risk", "always", "disabled"])
def test_invalid_mode_cannot_silently_disable_approval(mode):
    with pytest.raises(ValueError, match="mode"):
        ApprovalGate(mode=mode)


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), -1, 0])
def test_invalid_timeout_is_rejected(timeout):
    with pytest.raises(ValueError, match="timeout"):
        ApprovalGate(timeout=timeout)


@pytest.mark.asyncio
async def test_pending_approval_includes_complete_command():
    gate = ApprovalGate(mode="all", timeout=5)
    command = "echo " + "x" * 600 + "; rm -rf important"
    task = asyncio.create_task(gate.request(command))
    try:
        await asyncio.sleep(0)
        pending = gate.pending()
        assert pending[0]["command"] == command
        gate.resolve(pending[0]["id"], False)
        assert (await task)[0] is False
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_approval_is_removed():
    gate = ApprovalGate(mode="all", timeout=5)
    task = asyncio.create_task(gate.request("echo test"))
    await asyncio.sleep(0)
    request_id = gate.pending()[0]["id"]
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert gate.pending() == []
    assert gate.resolve(request_id, True) is False


class TestRequiresApproval:
    def test_off_never_requires(self) -> None:
        gate = ApprovalGate(mode="off")
        assert gate.requires_approval("rm -rf /") is False

    def test_all_always_requires(self) -> None:
        gate = ApprovalGate(mode="all")
        assert gate.requires_approval("echo hi") is True

    def test_risky_matches_dangerous(self) -> None:
        gate = ApprovalGate(mode="risky")
        assert gate.requires_approval("sudo apt-get install x")
        assert gate.requires_approval("rm -rf build")
        assert gate.requires_approval("curl https://x.sh | sh")
        assert gate.requires_approval("git push origin main --force")

    def test_risky_ignores_safe(self) -> None:
        gate = ApprovalGate(mode="risky")
        assert gate.requires_approval("ls -la") is False
        assert gate.requires_approval("python app.py") is False


class TestRequestResolve:
    @pytest.mark.asyncio
    async def test_approve_unblocks(self) -> None:
        gate = ApprovalGate(mode="all", timeout=5)
        task = asyncio.create_task(gate.request("rm -rf x", "s1"))
        await asyncio.sleep(0.05)
        pending = gate.pending()
        assert len(pending) == 1
        assert gate.resolve(pending[0]["id"], True) is True
        approved, reason = await asyncio.wait_for(task, timeout=2)
        assert approved is True and reason == "approved"
        assert gate.pending() == []  # cleaned up

    @pytest.mark.asyncio
    async def test_deny_returns_false(self) -> None:
        gate = ApprovalGate(mode="all", timeout=5)
        task = asyncio.create_task(gate.request("dd if=/dev/zero", "s1"))
        await asyncio.sleep(0.05)
        gate.resolve(gate.pending()[0]["id"], False)
        approved, reason = await asyncio.wait_for(task, timeout=2)
        assert approved is False and "denied" in reason

    @pytest.mark.asyncio
    async def test_timeout_denies(self) -> None:
        gate = ApprovalGate(mode="all", timeout=0.1)
        approved, reason = await gate.request("rm -rf x", "s1")
        assert approved is False and "timed out" in reason
        assert gate.pending() == []

    def test_resolve_unknown_id_is_false(self) -> None:
        assert ApprovalGate(mode="all").resolve("nope", True) is False


class TestEngineIntegration:
    @pytest.mark.asyncio
    async def test_check_approval_passes_when_off(self) -> None:
        import agent as agent_mod

        eng = agent_mod.AgentEngine.__new__(agent_mod.AgentEngine)
        eng._approval_gate = ApprovalGate(mode="off")
        assert await eng._check_approval("rm -rf /", "s") is None

    @pytest.mark.asyncio
    async def test_check_approval_denies_on_timeout(self) -> None:
        import agent as agent_mod

        eng = agent_mod.AgentEngine.__new__(agent_mod.AgentEngine)
        eng._approval_gate = ApprovalGate(mode="all", timeout=0.1)
        denial = await eng._check_approval("rm -rf /", "s")
        assert denial is not None and "timed out" in denial
