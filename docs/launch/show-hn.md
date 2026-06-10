# Show HN draft

## Title (pick one, ≤80 chars)

1. `Show HN: An AI agent that must produce evidence before it can say "done"`
2. `Show HN: Distill – self-hosted AI agent gated on evidence, not self-report`
3. `Show HN: I made my AI agent prove it finished the task (files, tests, ports)`

Option 1 is recommended: it leads with the mechanism, not the name, and reads
as a claim HN will want to test.

## Submission

- **URL**: https://github.com/Aspct3434/Distill-Agent
- For Show HN, submit the URL and put the explanation in a first comment
  (HN convention when you submit a link rather than a text post).

## First comment (post immediately after submitting)

---

Hi HN — author here.

Every agent framework I tried had the same failure mode: the model announces
"Done! I've created the file and the tests pass" — and nothing of the sort
happened. The transcript looks perfect; the filesystem disagrees.

Distill's answer is a task contract. Before doing real work, the agent must
declare what physical evidence will exist when the task is complete: a file at
a path, a process on a port, a command exiting 0, a test passing. The ReAct
loop then refuses to accept a final answer until that evidence is verified
against the actual system — not against the model's claims. No evidence, no
"done". The model literally cannot finish by asserting success.

The same philosophy applies to its self-improvement loop. After a successful
complex task, Distill distills the trajectory into a reusable, parameterized
Python skill. Skills are versioned, and if a newer version's measured success
rate regresses, it is automatically rolled back. Learning is gated on
evidence too.

The rest is what you'd expect from a self-hosted personal agent: FastAPI
gateway (token-gated by default — it returns 503 until you set an API token),
session-per-FIFO-lane concurrency, hybrid memory (SQLite FTS + ChromaDB +
optional Neo4j graph), sandboxed execution (host / Docker / Daytona / E2B /
Modal), human-in-the-loop approval modes, and adapters for Telegram, Discord,
Slack, and email. Python + LiteLLM, so it works with any provider, including
local models via Ollama.

Honest caveats: the contract loop, gateway, and checkpointer are stable; skill
distillation, serverless sandboxes, and sub-agent delegation are experimental.
There's a maturity matrix in the README — I'd rather under-claim than have the
project do to you what LLMs do to me.

I'd love feedback on the contract mechanism in particular: what evidence types
are missing, and where would you expect it to be gameable?

---

## Prep notes (don't post these — be ready for them)

Likely questions and the honest answers:

- **"Can't the model fake the evidence (e.g., `touch` the file)?"** — Yes, an
  adversarial model could satisfy a weak contract. The contract raises the bar
  from "claimed it" to "did *something* real"; it eliminates the dominant
  failure mode (hallucinated completion), not a malicious model. Stronger
  evidence (tests passing, service responding) is proportionally harder to fake.
- **"How is this different from OpenClaw?"** — OpenClaw optimizes for channel
  breadth and ecosystem; it has no completion verification, and its default
  main session has full host access. Distill optimizes for verified execution
  and is locked down by default.
- **"How is this different from Hermes?"** — Hermes validates skills by reuse
  and has excellent session infrastructure; Distill gates both task completion
  and skill evolution on measured evidence, with auto-rollback.
- **"Why Neo4j/Chroma? Heavy."** — Both optional; the system degrades
  gracefully to SQLite-only. The one-click deploys run lean with no databases
  to provision.
- **"Benchmarks?"** — If eval numbers exist by launch day, lead with them in
  the comment. If not, say "eval harness is in the repo
  (`src/eval_harness.py`), numbers are the next milestone" — do not improvise
  figures.

Logistics: post Tuesday–Thursday, 8–10am US Eastern. Stay in the thread all
day. Answer every technical question, concede valid criticism quickly, never
argue tone.
