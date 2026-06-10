from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from eval_harness import (  # noqa: E402
    LIVE_TASKS,
    EvalResult,
    false_completion,
    format_gating_comparison,
    run_self_test,
)


def test_eval_harness_self_test() -> None:
    assert run_self_test() == 0


def test_false_completion_requires_confident_wrong_answer() -> None:
    confident_wrong = EvalResult(
        task_id="t", passed=False, outcome="completed", final_text="All done!"
    )
    honest_failure = EvalResult(
        task_id="t", passed=False, outcome="iteration_limit", final_text="Could not finish."
    )
    verified_pass = EvalResult(
        task_id="t", passed=True, outcome="completed", final_text="Done and checked."
    )
    assert false_completion(confident_wrong)
    assert not false_completion(honest_failure)
    assert not false_completion(verified_pass)


def test_format_gating_comparison_reports_both_arms() -> None:
    gating_on = [
        EvalResult(task_id="a", passed=True, outcome="completed", final_text="ok"),
        EvalResult(task_id="b", passed=False, outcome="iteration_limit", final_text="x"),
    ]
    gating_off = [
        EvalResult(task_id="a", passed=True, outcome="completed", final_text="ok"),
        EvalResult(task_id="b", passed=False, outcome="completed", final_text="done!"),
    ]
    report = format_gating_comparison(gating_on, gating_off)
    assert "gating ON " in report and "gating OFF" in report
    assert "false completions 0/2 (0%)" in report
    assert "false completions 1/2 (50%)" in report


def test_live_action_tasks_declare_artifacts_for_clean_arms() -> None:
    # Every side-effecting task must declare its artifacts, otherwise a stale
    # file from a previous benchmark arm could satisfy the check.
    for task in LIVE_TASKS:
        if "action" in task.tags:
            assert task.artifacts, f"{task.id} has no artifacts declared"


if __name__ == "__main__":
    raise SystemExit(run_self_test())
