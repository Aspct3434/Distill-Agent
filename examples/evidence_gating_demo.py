"""Demo: evidence-gated verification catches hallucinated completions.

Distill's differentiator is that a task is only "done" when there is *physical
evidence* it was done -- a file on disk, a port open -- not when the model merely
*says* it is done. This script makes that concrete with a deterministic, scripted
model (no API key, no network), reusing the evaluation harness plumbing.

Two runs of the same task ("create a file, then confirm"):

  1. HALLUCINATED -- the model claims success without calling any tool.
  2. HONEST       -- the model actually invokes the write tool, then claims success.

Each run is scored two ways:

  * text-only   -- did the final answer *say* it succeeded?   (a naive ReAct loop)
  * evidence    -- does the file actually exist on disk?       (Distill's gate)

The text-only check passes the hallucination through; the evidence check rejects
it. That gap is the whole point.

Run:

    python examples/evidence_gating_demo.py
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from typing import Any

# Make ``src`` importable whether run from the repo root or elsewhere.
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import agent as agent_module  # noqa: E402
from agent import AgentEngine  # noqa: E402
from eval_harness import (  # noqa: E402
    EvalTask,
    _EmptyMemory,
    _check_contains,
    _check_file,
    _mk_response,
    _ScriptedModel,
    run_task,
)

_TEXT_CLAIM = "I created the file at {path}. Task complete -- done."


class _WritingTools:
    """Minimal tools object whose terminal command actually writes the target file.

    Mirrors the harness self-test's FakeTools, but the side-effecting command
    creates ``target`` on disk so the evidence check has something real to find.
    """

    def __init__(self, target: Path) -> None:
        self._target = target

    async def list_all_tools(self) -> list[dict[str, Any]]:
        return []

    async def execute_terminal_command(self, command: str) -> dict[str, Any]:
        self._target.parent.mkdir(parents=True, exist_ok=True)
        self._target.write_text("DEMO_EVIDENCE", encoding="utf-8")
        return {
            "exit_code": 0,
            "stdout": "wrote file",
            "stderr": "",
            "current_working_directory": str(self._target.parent),
        }


async def _run(script: list[Any], target: Path) -> Any:
    """Run one scripted agent turn and return its EvalResult."""
    original = agent_module.litellm.acompletion
    agent_module.litellm.acompletion = _ScriptedModel(script)
    try:
        engine = AgentEngine(
            memory=_EmptyMemory(), tools=_WritingTools(target), model="gpt-4o-mini"
        )
        task = EvalTask(
            id="evidence_demo",
            prompt=f"Create a file at {target} containing DEMO_EVIDENCE, then confirm it exists.",
            check=_check_contains("done"),  # placeholder; we re-score below
        )
        return await run_task(engine, task)
    finally:
        agent_module.litellm.acompletion = original


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="distill-evidence-demo-"))
    target = tmp / "evidence.txt"

    text_only = _check_contains("done")
    evidence = _check_file(str(target), "DEMO_EVIDENCE")

    # Scenario 1: the model claims success but calls no tool -> no file is written.
    hallucinated = asyncio.run(
        _run([_mk_response(content=_TEXT_CLAIM.format(path=target))], target)
    )
    halluc_text = text_only(hallucinated)
    halluc_evidence = evidence(hallucinated)

    # Reset the target so the honest run starts from a clean slate.
    target.unlink(missing_ok=True)

    # Scenario 2: the model actually writes the file, then claims success.
    honest = asyncio.run(
        _run(
            [
                _mk_response(tool=("execute_terminal_command", {"command": f"echo DEMO_EVIDENCE > {target}"})),
                _mk_response(content=_TEXT_CLAIM.format(path=target)),
            ],
            target,
        )
    )
    honest_text = text_only(honest)
    honest_evidence = evidence(honest)

    def mark(ok: bool) -> str:
        return "PASS" if ok else "FAIL"

    print("\nEvidence-gated verification demo")
    print("=" * 52)
    print(f"{'run':14} {'text-only':>12} {'evidence':>12}")
    print("-" * 52)
    print(f"{'hallucinated':14} {mark(halluc_text):>12} {mark(halluc_evidence):>12}")
    print(f"{'honest':14} {mark(honest_text):>12} {mark(honest_evidence):>12}")
    print("-" * 52)
    print(
        "A naive text-matching ReAct loop accepts the hallucinated 'done'.\n"
        "Distill's evidence gate rejects it: no file, no completion."
    )

    # The demo is only meaningful if the gap shows up exactly here.
    ok = halluc_text and not halluc_evidence and honest_text and honest_evidence
    if not ok:
        print("\nDEMO INVARIANT BROKEN -- the evidence gap did not reproduce.")
        return 1
    print("\nDEMO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
