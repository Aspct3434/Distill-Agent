# Project review and improvement pass — 2026-09-16

This pass reviewed the Python agent and gateway, persistence and scheduling,
React control panel, installers, packaging, deployment configuration, and CI.
Changes focus on reproducible functional problems and regression coverage.
Existing uncommitted adapter, memory-recall, proxy, and dependency changes
were preserved. Nothing was committed, published, or deployed.

## Runtime and conversation reliability

- Agent turns and checkpoint replay now share a per-session execution lock.
  Concurrent work in different sessions remains possible, while browser,
  adapter, and scheduled entry points cannot mutate the same history at once.
  Locks do not accumulate permanently, and active histories are protected
  from eviction.
- Replay selects the latest user prompt, replaces the session's stored
  history, restores execution steps, and reconstructs artifact evidence.
  The replay API also returns `final_answer` events as its final output.
- New checkpoints persist structured execution steps. Legacy checkpoints
  remain readable but clear unrelated current evidence because their own
  execution steps were never saved.
- Checkpoint retention uses insertion order instead of iteration numbers,
  which restart on every turn and previously caused new checkpoints to be
  discarded.
- WebSocket input validation rejects malformed or empty messages without
  losing the connection. Backend failures produce a visible error. Duplicate
  active sessions cannot overwrite the task used for cancellation, and
  disconnection cleans up the current task.

Primary files: [agent.py](../src/agent.py), [gateway.py](../src/gateway.py),
[checkpointer.py](../src/checkpointer.py).

## Persistence, scheduling, and approvals

- SQLite session connections close on success and failure. Quoted full-text
  search terms now return matching results instead of silently failing.
- Schema migration DDL and migration bookkeeping share an explicit
  transaction, including concurrent initialization.
- In-flight scheduled runs and toggles cannot recreate deleted jobs.
  Failed job creation does not leave a runnable job in memory. Nonfinite
  and overflowing schedule intervals are rejected.
- Invalid approval modes and timeouts fail during configuration instead of
  silently weakening approval behavior. Approval requests preserve the full
  command, including trailing operations.
- Regression coverage verifies that the pre-existing memory-recall change
  searches only the active conversation.

Primary files: [session_store.py](../src/session_store.py),
[sqlite_migrations.py](../src/sqlite_migrations.py),
[scheduler.py](../src/scheduler.py), [approvals.py](../src/approvals.py).

## Control panel and authentication

- Settings now provides a **Gateway API token** field. Saving it reloads
  the panel so HTTP and WebSocket connections use the new token; unavailable
  browser storage produces an actionable error.
- Chat recovers from gateway errors and disconnects, preserves partial
  responses, and continues while another panel is open. Stale socket
  callbacks under React StrictMode cannot create extra live connections.
- History storage failures no longer crash chat. IME confirmation does not
  submit an unfinished message.
- Skill exports use authenticated requests. Failed approvals remain visible
  for retry, and long commands can be read in full.
- Existing proxy credential and response-header filtering gained regression
  coverage. A valid proxy cookie cannot mint a replacement cookie using an
  unverified query expiry. Signed-URL redemption preserves encoded reserved
  characters in paths and handles the query separately.
- CORS preflight behavior is checked through the ASGI middleware stack;
  ordinary unauthenticated OPTIONS requests remain protected.

Primary files: [frontend components](../control-panel/src/components),
[API client](../control-panel/src/lib/api.ts), [gateway.py](../src/gateway.py).

## Installation, packaging, and CI

- Fresh installers create the required gateway token while preserving
  configured tokens on reinstall. Docker setup creates missing database
  credentials. Empty template assignments no longer prevent secret setup.
- Bash interactive menus no longer contaminate their returned selections.
  Custom environment files are forwarded to Compose and local startup;
  Bash no longer executes dotenv contents as shell code.
- The npm installer consumes child-process output to prevent full-pipe
  deadlocks, retains bounded failure diagnostics, and replaces managed
  environment values without duplicate token-limit settings.
- Messaging setup prompts match the existing deny-by-default allowlists.
- Python and npm package versions both read `0.2.7`. Docker no longer installs
  an unpinned second copy of the already-pinned SQLite MCP dependency.
- CI now runs npm installer tests plus frontend lint/build on Linux and
  Windows. The frontend's template README was replaced with actual setup,
  authentication, and verification instructions.

Primary files: [installer](../lib/distill-cli.js), [scripts](../scripts),
[CI workflow](../.github/workflows/ci.yml),
[frontend instructions](../control-panel/README.md).

## Verification

The Python checks used an isolated `.venv` with the repository's pinned
runtime and development requirements, on Windows with Python 3.12.13.

| Check | Result |
|---|---|
| Combined Python suite, using the existing CI live-service exclusions | **913 passed, 1 skipped**, 94.06 seconds |
| Python line coverage | **67.14%**, above the configured **61%** minimum |
| Ruff, `src/` and `tests/` | Passed |
| Mypy, complete `src/` tree | Passed, 34 source files |
| Installed dependency consistency | Passed, 94 packages |
| Eval harness self-test | Passed |
| Real SQLite MCP server tool discovery | Passed in combined suite |
| npm installer tests | Passed |
| Frontend ESLint and TypeScript/Vite production build | Passed |
| Browser regression runner | Passed |
| npm package dry run | Passed |
| Python source distribution and wheel build | Passed, version 0.2.7 |
| Diff whitespace check | Passed |

The one skip is the Bash host-local process test on Windows. Bash interactive
and mocked Docker startup checks passed through Git Bash; the POSIX-only test
is collected by the existing Ubuntu Python CI job. Test scratch files were
placed inside the workspace because this machine's sandbox rejects Git Bash
directory creation through parent-relative paths to external temporary folders.

To reproduce the main suite from an activated project environment, set
`PYTHONPATH=src` and run:

```sh
python -m pytest tests/ --ignore=tests/test_end_to_end.py --ignore=tests/test_memory.py --ignore=tests/test_swarm.py --cov=src
python -m ruff check src/ tests/
python -m mypy src/
python src/eval_harness.py --self-test
npm test
npm --prefix control-panel run lint
npm --prefix control-panel run build
```

The retained [browser regression runner](../tests/control-panel-browser-checks.js)
checks socket ownership, error recovery, reconnection, partial responses,
navigation, history, IME input, authenticated downloads, token setup and retry,
approval failures, and blocked storage. It uses mocked gateway responses and
does not require provider credentials. Its invocation is documented in the
script and [frontend README](../control-panel/README.md).

## Validation limits and remaining operational considerations

- Live LLM, multi-agent provider, and ChromaDB/Neo4j integration suites require
  external services and credentials. They were excluded consistently with
  the existing CI workflow. Real messaging delivery and OAuth sign-in were
  not exercised against external accounts.
- No full Docker image build or cloud deployment was performed. Installer
  startup regressions use controlled subprocess mocks and Compose config
  validation.
- The frontend still targets a gateway on `127.0.0.1:8000`. Remote frontend
  hosting needs an endpoint/proxy decision; this pass does not introduce a
  new deployment architecture.
- Browser regression checks are retained but run separately from the new
  npm lint/build CI job.
- Session ordering is enforced inside one agent process. The shipped Docker
  command uses one worker; shared session state across multiple processes
  would require additional coordination.
- Passing checks establish the tested behavior, not complete production or
  security certification. Tool execution, startup, and external integrations
  retain substantial paths that need live environment validation.
