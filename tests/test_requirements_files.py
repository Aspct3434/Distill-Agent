"""Every requirements*.txt line must be something pip can parse.

Stray tool-output tags have been committed into requirements files twice,
and pip rejects the whole file on the first bad line -- which silently broke
the hybrid-memory install in the Dockerfile and every installer. Nothing
else in CI installs requirements-ml.txt, so this check is the only guard.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from packaging.requirements import InvalidRequirement, Requirement

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "requirements_file",
    sorted(PROJECT_ROOT.glob("requirements*.txt")),
    ids=lambda p: p.name,
)
def test_requirements_file_lines_are_valid(requirements_file: Path) -> None:
    for lineno, raw in enumerate(requirements_file.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split(" #", 1)[0].strip()
        # Blank lines, comments, and pip options (--extra-index-url, -r, ...).
        if not line or line.startswith(("#", "-")):
            continue
        try:
            Requirement(line)
        except InvalidRequirement as exc:
            pytest.fail(f"{requirements_file.name}:{lineno}: {raw!r} is not a requirement: {exc}")
