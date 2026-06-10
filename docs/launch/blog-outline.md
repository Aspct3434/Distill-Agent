# Blog post outline

**Working title:** "I built an AI agent that has to prove it finished"

**Alt titles:**
- "No evidence, no 'done': evidence-gated task contracts for AI agents"
- "Your agent says it's done. Your filesystem disagrees."

**Audience:** developers who have used an agent (Claude Code, OpenClaw,
Cursor, etc.) and been burned by a false "done". Publish on a personal blog or
the repo's `docs/`, syndicate to r/LocalLLaMA, r/AI_Agents, r/selfhosted, X,
and use it as the link target for the Show HN comment.

---

## 1. The failure mode (hook — 3 paragraphs max)

- Open with a real transcript: agent says "I've created the config and the
  server is running ✅" — then `ls` shows nothing, port is closed.
- Name the problem: LLMs are trained to produce plausible completions, and "I
  finished successfully" is the most plausible completion of a task prompt.
  Self-report is the wrong trust anchor.
- One sentence: every popular agent framework today accepts the model's word.

## 2. Why the obvious fixes don't work

- "Just prompt it to be honest" — prompting reduces frequency, can't gate.
- "Have a second LLM judge the transcript" — the judge reads the same
  fiction; hallucinations are internally consistent.
- "Human reviews everything" — doesn't scale, defeats the point of an agent.
- The insight: stop verifying *text*, start verifying *the world*.

## 3. Task contracts: the mechanism

- Before substantive work, the agent must call `set_task_contract` declaring
  required evidence: files at paths, processes on ports, commands exiting 0,
  tests passing.
- The ReAct loop's finalization is gated: a final answer is rejected unless
  every contract item is verified against the actual system (filesystem
  stat, port probe, exit code) — not against the transcript.
- Show the actual loop: agent tries to finish early → gate rejects → agent is
  forced back to work → evidence appears → finish allowed.
- Include the code-level shape (tool schema + gate check), keep it short.

## 4. What happened when it couldn't lie anymore

- Concrete before/after anecdotes: tasks that previously "succeeded" in one
  fake turn now either actually complete or honestly fail.
- New honest failure modes that appeared (e.g., agent declares weaker
  contracts) and the countermeasures.
- **Numbers section** — run `src/eval_harness.py` task suite with contracts
  on vs. off, report false-completion rate. This is the screenshot people
  will share; prioritize getting it.

## 5. The same idea, applied to learning

- Skill distillation: successful trajectory → parameterized Python skill.
- Skills are versioned; success rate is measured; regression → automatic
  rollback. Self-improvement gated on evidence, like everything else.
- One example of a real distilled skill from the repo.

## 6. Limits (credibility section — do not skip)

- A determined adversarial model can satisfy a weak contract (`touch` the
  file). Contracts kill hallucinated completion, not malice; richer evidence
  types raise the bar.
- Contract declaration itself is LLM-generated — quality varies by model.
- What's stable vs. experimental (mirror the README maturity matrix).

## 7. Try it

- One-click deploy buttons, `npx @aspct/distill-agent install`, Telegram in
  5 minutes.
- Link the repo, invite contract-evasion bug reports as issues — "try to make
  it lie" is a great call to action.

---

**Length target:** 1,500–2,200 words. Mechanism over marketing; every claim
in the post should itself come with evidence (transcripts, code, numbers).
