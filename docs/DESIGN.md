# Design Rationale

[ARCHITECTURE.md](../ARCHITECTURE.md) describes what the pieces are. This
document records *why* each major decision was made, what the alternatives
were, and what each choice costs. File references point at the code that
implements the decision.

## 1. Task contracts: completion is gated on evidence, not prose

**Problem.** The dominant failure mode of tool-using agents is declaring
success without having done the work. The model's own output cannot be
trusted as a completion signal, because the model is the thing being checked.

**Decision.** Before doing any work, the model must call `set_task_contract`
declaring a mode (`answer` or `execute`), success criteria, and evidence
requirements drawn from a closed vocabulary — `filesystem_artifact`,
`running_http_service`, `running_tcp_service`, `database_mutation`,
`command_output`, `none` (`src/contract.py:38`). The loop refuses to finish
until `contract_completion_status` (`src/contract.py:485`) reports every
requirement satisfied.

The gate only counts physical observations: non-error `tool_result` steps,
parsed by per-tool checkers that require positive evidence — e.g. a
`wait_for_port` result must actually report the port open
(`src/contract.py:554`). Assistant text never satisfies a requirement.

**Why a closed vocabulary instead of free-text criteria?** Free-text criteria
cannot be machine-checked; each fixed requirement maps to a specific,
verifiable observation. Free-text success criteria still exist in the
contract, but they inform the model, not the gate.

**Why an `answer` mode?** Pure Q&A produces no artifacts. Without an explicit
no-evidence mode, the agent would be pushed to fabricate side effects just to
satisfy the gate.

**Self-correcting contracts.** Models routinely mis-declare contracts, so
normalisation recovers instead of rejecting where it safely can
(`src/contract.py:366`): a string where an array was expected is split on
`<item>` tags or newlines; over-broad `running_http_service` evidence on a
task with no HTTP semantics is downgraded to `running_tcp_service`;
artifact-flavored tasks get `filesystem_artifact` added. Wording that would
re-scope sandboxed work onto the host ("on the host system") is rewritten
(`src/contract.py:350`) so a model-authored contract cannot quietly escape the
sandbox. Anything unrecoverable (wrong mode, non-object JSON arguments, empty
summary) returns a structured error that is fed back as a tool result for the
next turn.

**Streaming interacts with the gate.** Text is not streamed to the user
before the contract is satisfied (`can_stream_text_before_final`,
`src/contract.py:528`); otherwise the user would see a confident answer that
the gate then rejects.

## 2. Concurrency: one FIFO lane per session

**Problem.** Many users must run concurrently, but messages within one
session mutate shared state (history, checkpoints, plan) and must stay
ordered.

**Decision.** Each session gets one `asyncio.Queue` and one worker task
(`_SessionLane`, `src/gateway.py:357`); `SessionLaneManager` creates lanes
lazily and routes by session id (`src/gateway.py:409`). Different sessions
run in parallel; same-session messages are serialised by the queue.

**Alternatives rejected.** A global queue with a worker pool gives
head-of-line blocking across users. Spawning a task per message gives
interleaved state writes within a session. Per-session locks around a shared
pool reinvent the lane with more moving parts.

**Cost.** A wedged handler blocks only its own session. Lanes are cheap
(an idle asyncio task), but there is no lane eviction yet — a very large
number of one-message sessions would accumulate idle tasks.

## 3. Defensive tool-call parsing and model escalation

Frontier function-calling APIs rarely emit malformed JSON; locally served and
small models do. Every tool call's arguments are parsed defensively
(`src/agent.py:2265`): a bad parse — including syntactically valid JSON that
is not an object — drops the call from execution and synthesises a matching
error tool-result, because the provider protocol requires a response for
every emitted `tool_call` id. The model re-issues the call next turn.

The engine runs a cheap model by default and escalates to a strong model only
after two consecutive iterations in which every tool call failed
(`_ESCALATE_AFTER_CONSECUTIVE_ERROR_ITERS`, `src/agent.py:751`); malformed
calls count as failures. Why: most iterations are easy, and consecutive
all-error iterations are a reliable signal that this one is not.

## 4. Sandboxing: three backends behind one interface

All shell execution goes through a single `_ScriptSandbox` interface with
three backends (`src/tools.py`):

- **Host** — fastest, no isolation; the default for local development.
- **Docker** (`src/tools.py:668`) — one long-lived container per
  `ToolManager`, kept alive with `sleep infinity`; commands run via
  `docker exec`. A container per command would add seconds of latency to
  every step; the workspace lives inside the container rather than
  bind-mounting the host, so a compromised command cannot write outside it.
- **HTTP exec shim** (`src/tools.py:1095`) — `AGENT_SANDBOX=http` points at
  one POST endpoint. Any serverless provider (Daytona, E2B, Modal, Vercel
  Sandbox) is adapted by a ~20-line shim service.

**Why one shim instead of N provider SDKs?** Provider SDKs churn and each
would be a separate dependency, auth model, and failure mode inside the agent
core. The shim moves provider-specific code out of the repo entirely and
makes the core testable against a plain HTTP mock (`tests/test_http_sandbox.py`).

**Command safety is regex-anchored, not substring-based.** The block list
compiles anchored patterns for destructive commands (`dd`, `mkfs`, `shred`,
`rm -rf /`). Substring matching was tried first and missed digit-suffixed
NVMe device names (`/dev/nvme0n1`) because `[a-z]` does not match digits —
a concrete bug that motivated the rewrite (see CHANGELOG, Security).

## 5. Memory: three tiers because recall has three shapes

- **SQLite** (always on): checkpoints, session history, durable state. Zero
  setup, transactional, good enough full-text search.
- **ChromaDB** (optional): semantic similarity — "have I seen something like
  this before?"
- **Neo4j** (optional): entity relationships — "what is connected to X?"

The optional backends are imported lazily inside `HybridMemory.__init__`
(`src/memory.py`) so the lightweight install never pays the ML dependency
tax, and the system degrades gracefully when they are absent. Cypher cannot
parameterise labels or relationship types, so both are sanitised before
interpolation (`_safe_identifier`, `src/memory.py`).

## 6. Skill distillation: gate first, synthesise second, prove before promote

Successful trajectories are synthesised by an LLM into parameterised,
`@skill`-decorated Python functions that auto-register on the MCP skills
server (`src/evaluator.py`). Two deliberate brakes:

1. **Quality gate before synthesis** — a trajectory qualifies only with at
   least two successful side-effecting tool calls and a non-trivial prompt
   (`_MIN_SIDE_EFFECT_STEPS`, `src/evaluator.py`). Trivial tasks would
   otherwise flood the library with junk skills. The set of side-effecting
   tools is defined once in `evaluator.py` and imported by `planning.py` —
   a single source of truth.
2. **Proof-carrying promotion** — the evolution layer (`src/evolution.py`)
   stages candidates, verifies them, promotes only with a proof bundle, and
   keeps rollback data in a SQLite ledger. A self-modifying agent must not be
   able to silently regress itself; every promotion is reversible and every
   version is tracked.

## 7. Sub-agents: bounded delegation, not a swarm

`delegate_task` fans work out to role-scoped sub-agents (researcher, coder,
auditor, planner) under `SubAgentOrchestrator` (`src/agent.py`): a semaphore
caps concurrency, every task has a timeout that returns a structured result
instead of crashing the parent, recursion depth is capped at 2, and batches
at 8 (all env-configurable, see ARCHITECTURE.md). There is deliberately no
persistent shared-state swarm: unbounded delegation is unbounded cost, and
sub-agents that cease to exist after returning are debuggable in a way that
long-lived inter-communicating agents are not.

## 8. Gateway security: fail closed

Agent endpoints return 503 until `AGENT_API_TOKEN` is set; running without
auth requires the explicit `AGENT_ALLOW_INSECURE_NO_AUTH` override. A
self-hosted agent with shell access must not be reachable unauthenticated by
default — "open until configured" is the wrong polarity for this kind of
software. A sliding-window rate limiter keyed by token (or client IP) guards
`/webhook` and `/ws/stream` (`src/gateway.py`). The Docker image runs as a
non-root user.

## 9. What gets cut first

An honest priority order, most expendable first:

1. **Chat adapters beyond Telegram.** All four share one core
   (`src/adapters/_commands.py`, `_progress.py`); each adapter is a thin
   transport. They are kept because the shared core makes them cheap.
2. **Neo4j graph tier.** The most speculative memory layer — its value is
   bounded by entity-extraction quality.
3. **Skill evolution.** The most experimental subsystem, and explicitly
   marked so. The contract loop is the project; everything else is removable.

## 10. Known gaps

- The core claim — that contract gating reduces false completions — has no
  published benchmark yet. `src/eval_harness.py` exists for exactly this;
  running it across a task suite with gating on/off is the highest-leverage
  missing piece of evidence.
- The HTTP sandbox shim is less exercised than the host and Docker paths
  (tested against mocks, not live providers).
- Session lanes have no eviction policy for long-idle sessions.
