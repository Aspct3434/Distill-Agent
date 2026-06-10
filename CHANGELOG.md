# Changelog

All notable changes to **Distill** are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added
- **Gating benchmark** (`eval_harness.py`): `--benchmark-gating` runs the live
  suite twice — contract gating on, then off — on fresh engine/tool instances
  and reports the false-completion rate per arm (confident final answers whose
  deterministic check failed). First direct measurement path for the project's
  core claim. `EvalTask.artifacts` declares each task's expected outputs,
  removed before every arm so a stale artifact can never satisfy a check.
- **Encoding regression test** (`tests/test_source_encoding.py`): scans
  `src/`, `skills/`, `scripts/`, and `tests/` for mojibake marker characters
  (U+00E2, U+00C3, U+FFFD). The CI "files parse" check cannot catch this —
  mojibake is valid Python.
- **`requirements-dev.txt`**: pinned test/lint/typecheck toolchain (pytest,
  pytest-asyncio, pytest-cov, hypothesis, ruff, mypy), installed on top of
  `requirements.txt` by CI and local dev environments.
- **Rate limiting** (`gateway.py`): `_SlidingWindowRateLimiter` — per-session
  sliding-window limiter (default 60 req/min, configurable via
  `GATEWAY_RATE_LIMIT_RPM`). Applied to `/webhook` and `/ws/stream` with HTTP
  429 responses and WebSocket error frames.
- **`AgentEngine._dispatch_tool_calls()`**: extracted parallel/serial tool
  dispatch and step recording from the main ReAct loop into a dedicated method,
  reducing `_run_agent_loop` by ~60 lines.
- **`_llm_first_choice()` helper** (`agent.py`): isolates the litellm
  `ModelResponse | TextCompletionResponse | None` union-attr access into a
  single typed adapter, eliminating scattered `# type: ignore[union-attr]`
  comments.
- **Property-based tests** (`tests/test_property.py`): Hypothesis tests for
  `_normalize_command` (idempotency, never-raises, None→empty) and
  `_normalise_task_contract` (valid inputs always succeed, invalid mode always
  errors, deduplication). Security-gate regex stress-tested with 500 arbitrary
  strings.
- **`tests/conftest.py`**: `sys.modules` stubs for `chromadb`, `neo4j`, and
  `sentence_transformers` so the full test suite runs without live backends.
- **`tests/test_gateway_unit.py`** (17 tests): `_SessionLane` FIFO ordering,
  `SessionLaneManager` session isolation, `Gateway` load test (500 messages).
- **`tests/test_coverage_boost.py`** (77 tests): evidence parsers, retry logic,
  `StateCheckpointer` async I/O, plan rendering.
- **`tests/test_contract_planning.py`** (49 tests): contract validation,
  continuation signals, plan lookups, classify_tool_result, instruction builders.
- **Multi-stage `Dockerfile`**: Python 3.12-slim builder → lean runtime image,
  non-root `agent` user (uid 1001), `HEALTHCHECK`, `VOLUME` declarations, all
  runtime paths wired via environment variables.
- **GitHub Actions CI** (`.github/workflows/ci.yml`): matrix over
  ubuntu/windows × Python 3.11/3.12; separate `lint` (ruff) and `typecheck`
  (mypy) jobs.

### Removed
- **Fast-path keyword heuristics** (`agent.py`): the pre-LLM intent matchers
  (environment report, public IPv4, cwd, port status, last-URL) answered
  requests via brittle English-only token matching and bypassed the task
  contract entirely — at odds with the project's evidence-gating thesis. All
  user requests now flow through the contract-gated ReAct loop.

### Changed
- **CI dependency install**: all three jobs (test, lint, typecheck) now install
  the pinned `requirements.txt` + `requirements-dev.txt` instead of an ad-hoc
  unpinned package list, so a green build proves the shipped pins work and an
  upstream release cannot break CI without a pin change in the diff.
- **Architecture**: split `agent.py` (2,648 lines) into four focused modules —
  `llm_utils.py`, `contract.py`, `planning.py`, `agent.py` (1,595 lines, −40%).
  Dependency chain is acyclic: `evaluator` ← `contract` ← `planning` ← `agent`.
- **`_SIDE_EFFECT_TOOLS`** consolidated: single canonical definition in
  `evaluator.py`; `planning.py` imports it instead of redeclaring.
- **Dockerfile**: upgraded from Python 3.11 single-stage to Python 3.12
  multi-stage build; removed UTF-16 decode hack (requirements.txt is now UTF-8).
- **Coverage threshold** (`pyproject.toml`): lowered to 60% — honest baseline
  for a project with LLM-dependent agent loop, HTTP server, and tool
  implementations that require external services.
- **mypy** expanded to 7 modules: `checkpointer`, `evaluator`, `memory`,
  `gateway`, `llm_utils`, `contract`, `planning`. All pass with 0 errors.
- **ruff**: zero violations across `src/` and `tests/`. All `E402` noqa
  annotations added to post-`sys.path` test imports; `RUF006` annotated for
  intentional fire-and-forget distillation task.

### Fixed
- **Packaging** (`pyproject.toml`): the declared build backend
  (`setuptools.backends.legacy:build`) does not exist, so `pip install .`
  failed at build time. Now uses `setuptools.build_meta`, declares the direct
  runtime dependencies plus an `ml` extra, lists the flat `src/` modules
  explicitly so the wheel is deterministic, and syncs the version with the
  npm installer package (0.2.6).
- **Mojibake, comprehensively** (`agent.py`, `tools.py`,
  `tests/test_plan_contract_robustness.py`): 459 double-encoded UTF-8
  sequences (box-drawing dividers, em dashes, ellipses, a minus sign)
  repaired. Several sat inside `SYSTEM_DIRECTIVE` string literals, shipping
  corrupted bytes to the LLM in every system prompt. Guarded by the new
  encoding regression test.
- **NVMe block-device regex** (`tools.py`): `dd/mkfs/shred of=/dev/nvme0n1`
  was not blocked because `[a-z]` doesn't match digit-suffixed NVMe names.
  Fixed by splitting into `(sd|hd|xvd|vd)[a-z]` and `nvme\d` patterns.
- **Mojibake** (`agent.py`): `â€¦` in escalation status message corrected to
  `…` (U+2026 HORIZONTAL ELLIPSIS).
- **Windows shell** (`tools.py`): `execute_terminal_command` now passes
  `shell=True` with `cmd.exe` on Windows and `bash -c` on POSIX, so the
  same tool works correctly on both CI platforms.
- **`StateCheckpointer.load_checkpoint`** raises `KeyError` on missing IDs
  (previously returned `None` in some paths); test updated accordingly.
- **`bool` return** (`contract.py`): `_can_stream_text_before_final` wrapped
  result in `bool()` to fix mypy `no-any-return`.
- **`list()` wraps** (`checkpointer.py`, `gateway.py`, `memory.py`): coerce
  `Any`-typed JSON/neo4j return values to `list` for mypy `no-any-return`.

### Security
- **Regex block list** (`tools.py`): replaced substring-match allow/block lists
  with compiled regex patterns anchored to dangerous command patterns (`dd`,
  `mkfs`, `shred`, `rm -rf /`, `chmod 777 /`).
- **Per-session rate limiter** (`gateway.py`): HTTP 429 / WebSocket error frame
  when a session exceeds `GATEWAY_RATE_LIMIT_RPM` requests per minute.

---

## [0.1.0] — 2025-05-22 (initial release)

### Added
- ReAct agent loop with task-contract gating and plan management.
- MCP tool integration (sqlite, filesystem, custom tools).
- Skill distillation: successful trajectories are synthesised into reusable
  `@skill`-decorated Python functions.
- Session checkpointing with SQLite backend.
- FastAPI gateway with WebSocket streaming, proxy, and webhook endpoints.
- Hybrid memory backend (ChromaDB vector store + Neo4j knowledge graph).
