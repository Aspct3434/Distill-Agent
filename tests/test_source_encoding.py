"""Guard against mojibake (double-encoded UTF-8) re-entering the source tree.

Corrupted sequences such as U+00E2-led runs previously shipped inside
SYSTEM_DIRECTIVE, sending garbage bytes to the LLM in every system prompt.
The CI "files parse" check cannot catch this -- mojibake is valid Python --
so this test scans for the marker characters that every such sequence
contains. The markers are built with chr() so this file stays pure ASCII.
"""
from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# U+00E2 / U+00C3: first byte of a UTF-8 multibyte sequence mis-decoded as
# cp1252/latin-1. U+FFFD: the replacement character emitted by lossy decodes.
# None of these appear in legitimate source; box drawing (U+2500) and em
# dashes used in comments are unaffected.
_MOJIBAKE_MARKERS = (chr(0xE2), chr(0xC3), chr(0xFFFD))

_SCANNED_DIRS = ("src", "skills", "scripts", "tests")


def _python_sources() -> list[Path]:
    files: list[Path] = []
    for directory in _SCANNED_DIRS:
        files.extend((PROJECT_ROOT / directory).rglob("*.py"))
    return [f for f in files if "__pycache__" not in f.parts]


@pytest.mark.parametrize("source", _python_sources(), ids=lambda p: p.name)
def test_source_file_has_no_mojibake(source: Path) -> None:
    text = source.read_text(encoding="utf-8")
    for marker in _MOJIBAKE_MARKERS:
        offset = text.find(marker)
        assert offset == -1, (
            f"{source}: mojibake marker U+{ord(marker):04X} at offset {offset}: "
            f"{text[max(0, offset - 30):offset + 10]!r}"
        )
