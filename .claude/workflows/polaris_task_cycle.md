# Claude Codex Workflow — canonical spec (a.k.a. polaris_task_cycle)

**Operator-named 2026-05-29.** The invocation phrase **"Claude Codex Workflow"** (or
**"with Claude Codex Workflow"**) means: run the standing POLARIS task-execution loop below,
driven by the **Anthropic Workflow function** as the engine, with **Codex as the only review
gate**. The keywords `exec:` / `task:` are equivalent triggers. This file is the spec the
per-prompt hook (`.claude/hooks/polaris_task_cycle_reminder.py`) points to.

**ONE name (no sub-labels).** There is exactly **one** name for this process: **"Claude Codex
Workflow."** It is NOT split into a separate "Ledger-First Workflow", "Prove-First Workflow",
or any other variant. The prove-first / Claims-Ledger discipline (see the section below) is the
**standard content of every Claude Codex Workflow run** — not a different named mode. When you
hear the one phrase, you run the one loop, and prove-first is built into it.

**HARD RULE — always via the Anthropic Workflow FUNCTION, never inline (operator reaffirmed
2026-06-09).** Every "Claude Codex Workflow" run MUST execute INSIDE the Anthropic **Workflow
function** (the background workflow engine that spawns the BRIEF / BUILD / SMOKE / Codex-gate
agents in ordered phases). Running the loop "inline" — ad-hoc foreground `codex exec` calls
stitched together by hand in the main turn — is a DRIFT and is forbidden. The operator has
repeat-flagged the inline drift ("I keep giving this directive, you just drift to inline"). The
first substantive action when the trigger fires is therefore: **author the Workflow-function
script**, then run it. The 2026-05-29 "few brief-gates run as direct foreground `codex exec`"
deviation noted at the bottom of this file is the exact pattern this HARD RULE now closes.

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

## Prove-first discipline (the standard content of every Claude Codex Workflow)

This is NOT a separate workflow — it is the standard content every Claude Codex Workflow run
carries. Build in this order, every time:

1. **Pin done + non-goals.** Confirm the canonical pin (CLAUDE.md §3.1 step 0) is green and
   state the non-goals up front: what this change deliberately does NOT touch. A pinned file
   (e.g. CLAUDE.md) is a non-goal here — its edit is DEFERRED to the signed-reconciliation flow.
2. **Claims Ledger BEFORE building.** Write the ledger first. Every claim maps to a
   `proof file:line` and a `status` of `live` / `staged` / `roadmap` / `removed`. **Nothing
   enters the build unless it is ledgered.** The ledger is the spec; the diff implements it.
3. **Sibling-scan + batch-fix the whole class.** Before writing one fix, grep for siblings of
   the same shape (all call sites, all consumers, all parallel constants) and fix the entire
   class in one pass — never the single instance the symptom pointed at.
4. **Build from the ledger, not from memory.** Implement exactly what the ledger asserts. If a
   line isn't in the ledger, it doesn't go in the diff. Memory is a TL;DR, not the source.
5. **Self-run a fixed 12-point rubric BEFORE Codex sees it.** Score the change against:
   (1) claim↔proof — every claim has a real file:line;
   (2) staged-vs-live honesty — `staged`/`roadmap` never described as already `live`;
   (3) number honesty — counts/sizes/line-refs are real, re-checked, not estimated;
   (4) internal consistency — no two parts of the change contradict;
   (5) sibling-consistency — the whole class is fixed, not one instance;
   (6) fail-closed safety — on error the change fails closed/loud, never silently degrades;
   (7) runtime-truth — claims about runtime behaviour are verified by running, not assumed;
   (8) acceptance-criteria-verbatim — the issue's acceptance criteria are met word-for-word;
   (9) non-goals — nothing outside the declared scope was touched;
   (10) no-magic-numbers — thresholds/paths come from config/const/env, not inline literals;
   (11) smoke-with-evidence — a smoke ran and produced a real artifact, not a "should work";
   (12) prior-findings-answered — every earlier Codex finding has an id→line→fix answer.
6. **Hand Codex an EVIDENCE PACK — Codex + own deep audit run in PARALLEL.** Give Codex the
   changes + the Claims Ledger + the smoke command/output/artifact path so Codex **VERIFIES**
   rather than **hunts**. In parallel, run your own deep §-1.1 line-by-line audit. Two
   independent audits, cross-reviewed (CLAUDE.md §-1.1).
7. **Answer each finding: id → fixed line → sibling-grep proof.** For every Codex finding,
   record the finding id, the exact line that now fixes it, and a sibling-grep proving no
   other instance of the same class survives.
8. **Codex APPROVE (0 P0/P1) → UI gets a SEPARATE live eyes-on gate → commit.** Codex is the
   only review gate; APPROVE requires zero P0 and zero P1. If the change touches
   `web/app/**` or `web/components/**`, a SEPARATE live visual eyes-on gate
   (`scripts/visual_review_gate.py` against `.codex/visual_audit_rubric.md`) must also pass
   before commit. Claude does NOT merge (§3.0).

**Why this is binding (cite):**
- **Codex names the Claims Ledger the #1 lever** — the ledger-before-build step is what turns a
  Codex review from a hunt into a verification, which is where its review power concentrates.
- **"LLMs Cannot Self-Correct Reasoning Yet" (Huang et al., ICLR 2024)** + **Anthropic's
  finding that a model grading its own output skews positive** — together these mean a
  **different-vendor Codex gate has real teeth** that a same-family self-check does not. The
  Opus `advisor` is the **same family** as the author and is therefore **never a substitute**
  for the Codex gate (CHARTER §1; operator memory `feedback_no_opus_advisor_use_codex_cli`).
- **GitHub Spec-Kit — "gate the brief harder than the diff"** — most defects are cheaper to
  catch at the spec/brief stage than at the diff stage, which is why the brief gate (gate 1)
  and the ledger (step 2) carry the load.

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
- `CLAUDE.md` §3.0.1 (authoritative project directive) — the matching prove-first edit to
  §3.0.1 is **DEFERRED**: CLAUDE.md is canonical-PINNED (`docs/canonical_pin.txt`), so it can
  only change via the user-signed reconciliation flow (CLAUDE.md §3.1 step 0), not a plain
  commit. This file and the hook carry the prove-first content until that reconciliation lands.
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
