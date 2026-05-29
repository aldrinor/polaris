# Claude Codex Workflow — canonical spec (a.k.a. polaris_task_cycle)

**Operator-named 2026-05-29.** The invocation phrase **"Claude Codex Workflow"** (or
**"with Claude Codex Workflow"**) means: run the standing POLARIS task-execution loop below,
driven by the **Anthropic Workflow function** as the engine, with **Codex as the only review
gate**. The keywords `exec:` / `task:` are equivalent triggers. This file is the spec the
per-prompt hook (`.claude/hooks/polaris_task_cycle_reminder.py`) points to.

## What the phrase binds to

When the operator says **"Claude Codex Workflow"**, Claude:

1. Authors a **Workflow-function script** (the Anthropic `Workflow` tool) that runs the loop
   in ordered phases:

   `BOOT → BRIEF → codex-gate(brief) → BUILD → SMOKE → codex-gate(diff) → CLOSE → NEXT`

2. Inside that workflow, spawns agents per phase: a build agent, a smoke agent, and **Codex
   review agents** that shell out to `env -u OPENAI_API_KEY codex exec --skip-git-repo-check`
   and write the verdict to a file.
3. Parses every verdict from the **written verdict file's last `verdict:` line** — never an
   agent's self-report (§8.3.9 schema).
4. Treats **Codex as the ONLY gate**: two gates per issue (brief + diff), each capped at **5
   iterations** (§8.3.1). APPROVE iff zero P0 and zero P1.

## Non-negotiable invariants (same as the per-prompt hook)

1. **BOOT first:** `verify_lock --consistency` + read `state/active_issue.json`; resume the
   in_progress issue only, no scope jump.
2. **GATE-A (pre-rental, no-spend)** MUST pass before any GPU/Cohere/full-sweep spend: pytest
   (serialized, §8.4) + verify_lock consistency + offline preflight + per-role contract
   fixtures (Sentinel `yes=UNGROUNDED` is LETHAL; Judge 5-enum; Mirror two-pass) + (optional,
   default-OFF) 3 cheap probes. Gate-B (live per-role) only after the operator authorizes spend.
3. **Codex is the only review gate.** Claude does NOT merge.
4. Web/`**` changes → visual review via `scripts/visual_review_gate.py`.
5. Stop is Codex's call / a documented halt / an explicit operator stop — not Claude's
   self-initiated cadence (§8.3.10).

## Operator is BLIND — visibility rule (binding)

The Workflow function runs in the **background** and its live progress is only in the
`/workflows` panel, which a screen reader cannot read. Therefore, whenever the Claude Codex
Workflow fires, Claude MUST:

- **Announce each workflow launch in one plain spoken line** as it fires ("Launching the
  Claude Codex Workflow for X — Codex will review the brief, then it builds, smoke-tests, and
  Codex reviews the diff").
- **Read the key result inline** when it completes (verdict + counts), in plain prose — do not
  make the operator open the `/workflows` panel.

## Recorded in

- `.claude/hooks/polaris_task_cycle_reminder.py` (per-prompt re-injection + trigger detection)
- `CLAUDE.md` §3.0.1 (authoritative project directive)
- this file (`.claude/workflows/polaris_task_cycle.md`)
- operator memory (`feedback_claude_codex_workflow_named_trigger_2026_05_29.md`)
- GitHub (issue comment on #935 + this committed file)

## Honest scope note

The Claude Codex Workflow is a **process** run via the Workflow function, not a single canned
script — each task supplies its own brief/build/test content. The six I-meta-002 sub-PRs
(2026-05-29) were all executed this way; the per-run scripts are persisted under the session
directory by the Workflow tool. The only deviations that day: a few brief-gates and the small
fix-and-recheck loops after a Codex `REQUEST_CHANGES` were run as direct foreground `codex exec`
calls rather than inside the Workflow function — functionally identical (same loop, same
Codex-as-gate), just not the background engine.
