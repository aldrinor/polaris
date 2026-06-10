HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

# Codex Diff Gate — I-meta-008 (#1186): Claude Codex Workflow DNA embed

## What this PR is

A **process-doc + per-prompt-hook ONLY** change. It embeds three pieces of "DNA" into the standing `Claude Codex Workflow` so they re-inject every prompt:

1. **ONE name** — the process has exactly one name, "Claude Codex Workflow." It is NOT split into a separate "Ledger-First Workflow" / "Prove-First Workflow" / any variant. Prove-first is the *standard content of every run*, not a different named mode.
2. **HARD RULE: always via the Anthropic Workflow FUNCTION, never inline** (operator reaffirmed 2026-06-09). Running the loop as ad-hoc foreground `codex exec` stitched in the main turn is DRIFT and forbidden.
3. **Prove-first discipline** as new standard content: Claims Ledger BEFORE building, sibling-scan + batch-fix the class, build from the ledger not memory, self-run a 12-point rubric, hand Codex an EVIDENCE PACK to VERIFY not hunt, answer each finding id→line→sibling-grep proof.

The same is condensed into the per-prompt hook REMINDER (two new invariants 7+8 + extended NAMED TRIGGER text).

**Scope is two files only:** `.claude/workflows/polaris_task_cycle.md` (spec) and `.claude/hooks/polaris_task_cycle_reminder.py` (hook). **No pipeline code, no faithfulness/retrieval/generator/evaluator code, no tests touched.**

**CLAUDE.md §3.0.1 is DEFERRED on purpose.** CLAUDE.md is canonical-PINNED (`docs/canonical_pin.txt` L10 = `69306b4a...  CLAUDE.md`; verified live: working-tree `sha256sum CLAUDE.md` == that exact pin). Per CLAUDE.md §3.1 step 0, any CLAUDE.md edit is a HARD STOP requiring a user-signed reconciliation commit — it cannot land as a plain commit in this PR. The spec file documents this deferral explicitly.

## Claims Ledger (every claim → proof file:line → status)

```json
[
  {
    "claim": "The name is ONE phrase, \"Claude Codex Workflow\" (the operator-named invocation phrase already exists; this is not new naming).",
    "proof": ".claude/workflows/polaris_task_cycle.md L1 (title \"# Claude Codex Workflow — canonical spec\") and L3 (\"The invocation phrase **\\\"Claude Codex Workflow\\\"** (or **\\\"with Claude Codex Workflow\\\"**)\"); .claude/hooks/polaris_task_cycle_reminder.py L76-77 (\"NAMED TRIGGER (operator, 2026-05-29): \\\"Claude Codex Workflow\\\" (or \\\"with Claude Codex Workflow\\\")\") and L86 (_TRIGGER_PHRASES = (\"claude codex workflow\", ...)); authoritative source CLAUDE.md §3.0.1 L204/L206.",
    "status": "live"
  },
  {
    "claim": "It MUST run via the Anthropic Workflow function (the background workflow engine is the prescribed engine, not an inline ad-hoc loop).",
    "proof": ".claude/workflows/polaris_task_cycle.md L5 (\"driven by the **Anthropic Workflow function** as the engine\") and L13 (\"Authors a **Workflow-function script** (the Anthropic `Workflow` tool)\"); .claude/hooks/polaris_task_cycle_reminder.py L78-80 (\"RUN this loop via the Anthropic Workflow FUNCTION (the background workflow engine that spawns the BRIEF / BUILD / SMOKE / Codex-gate agents in phases)\"); authoritative CLAUDE.md §3.0.1 L206.",
    "status": "live"
  },
  {
    "claim": "CLAUDE.md is canonical-PINNED, so editing it in this PR is DEFERRED to the signed-reconciliation flow (the DNA edit cannot land as a plain commit).",
    "proof": "docs/canonical_pin.txt L10 = \"69306b4a2b17d26c8ea0a5f84319b223c4c08755b30bbf882fa41520cf1d50aa  CLAUDE.md\"; verified live: working-tree `sha256sum CLAUDE.md` = 69306b4a... (exact match to pinned SHA), so the pin is current and binding. CLAUDE.md §3.1 step 0 mandates HARD STOP on canonical-pin drift, meaning any CLAUDE.md edit requires a user-signed reconciliation commit, not an autonomous edit.",
    "status": "staged"
  },
  {
    "claim": "Prove-first / Claims-Ledger is NEW standard content to ADD (it is not yet a written directive in the spec, hook, or CLAUDE.md).",
    "proof": "Negative-grounded: the prove-first / Claims-Ledger concept appears NOWHERE in the three sources — polaris_task_cycle.md (67 lines pre-edit, phases BOOT→BRIEF→codex-gate→BUILD→SMOKE→codex-gate→CLOSE→NEXT, no prove-first/ledger step), polaris_task_cycle_reminder.py REMINDER block (same loop, no ledger), and CLAUDE.md §3.0.1 L204-215 (no ledger). This very ledger artifact is the first instance of the content. Added this PR.",
    "status": "roadmap->live"
  },
  {
    "claim": "Codex is the ONLY review gate (two gates per issue, brief + diff, each 5-iter capped; Claude does NOT merge).",
    "proof": ".claude/workflows/polaris_task_cycle.md L5 (\"with **Codex as the only review gate**\"), L23-24 (\"Treats **Codex as the ONLY gate**: two gates per issue (brief + diff), each capped at **5 iterations** (§8.3.1)\"), L34 (\"Codex is the only review gate. Claude does NOT merge.\"); .claude/hooks/polaris_task_cycle_reminder.py L64-66 (\"Codex is the ONLY review gate (§3.0). Two gates per issue: brief + diff, each 5-cap (§8.3.1)\") and L69 (\"Claude does NOT merge.\"); authoritative CLAUDE.md L200 + §3.0.1 L206.",
    "status": "live"
  }
]
```

## Summary

- ONE name: "Claude Codex Workflow" — no contradictory separate "Ledger-First"/"Prove-First" name; prove-first is the standard content of the one process.
- HARD rule: ALWAYS run via the Anthropic Workflow FUNCTION, never inline. Made explicit and consistent in BOTH files.
- Prove-first / Claims-Ledger standard content ADDED to the spec (new "Prove-first discipline" section + 12-point self-run rubric + build order).
- The same condensed into the per-prompt hook REMINDER (new invariants 7+8; NAMED TRIGGER text extended).
- CLAUDE.md §3.0.1 edit DEFERRED — canonical-pinned; documented in the spec's "Recorded in" section.
- Process-doc + hook ONLY. No pipeline / faithfulness / retrieval / generator / evaluator / test code.

## Smoke results (run from C:/POLARIS so the cwd guard fired)

```json
{
  "hook_compiles": true,
  "hook_emits_json": true,
  "edits_present": true,
  "summary": "I-meta-008 smoke PASSED — all 3 checks green, run from /c/POLARIS so the cwd guard fired. (1) py_compile clean: `python -m py_compile .claude/hooks/polaris_task_cycle_reminder.py` -> PY_COMPILE_EXIT=0 (no syntax errors). (2) Hook emits VALID JSON: `echo '{\"prompt\":\"use Claude Codex Workflow to do X\"}' | python .claude/hooks/polaris_task_cycle_reminder.py` -> HOOK_EXIT=0; re-parsing stdout with json.load succeeds (VALID_JSON=1); HAS_hookSpecificOutput=True, HAS_additionalContext=True. additionalContext carries ALL THREE required elements (ALL_THREE_PRESENT=True): the always-via-Workflow-function rule (invariant 7); the prove-first/Claims-Ledger lines (invariant 8); and the named-trigger activation line ('>>> NAMED TRIGGER DETECTED in this prompt...'), which only appears because cwd is under C:/POLARIS and the prompt contains 'Claude Codex Workflow'. (3) Workflow markdown edits present: the new 'Prove-first discipline' section at line 55 (backed by a 12-point self-run rubric + Claims-Ledger build order) and the always-via-function HARD RULE at line 15."
}
```

Independent re-verification by the diff author (separate from the build-phase smoke above):
- `python -m py_compile` → exit 0.
- `echo '{"prompt":"use Claude Codex Workflow to do X"}' | python <hook>` → valid JSON; `>>> NAMED TRIGGER DETECTED` present; invariant-7 (`Anthropic Workflow FUNCTION, NEVER inline`) present; invariant-8 (`Claims Ledger`) present; ALL_THREE=True.
- Fail-soft: `echo 'not json at all' | python <hook>` → exit 0 (graceful); `echo '' | python <hook>` → exit 0.
- No-trigger prompt (`{"prompt":"just a normal prompt"}`) → JSON valid AND the `>>> NAMED TRIGGER DETECTED` line is NOT injected (trigger gating intact).
- Diff does NOT touch trigger-detection logic: grepping the hook diff for `_TRIGGER_PHRASES` / `def ` / `startswith` / `.lower()` / `cwd` / `C:/POLARIS` / `sys.exit` / `json.dump` returns EMPTY — only the reminder TEXT (docstring) was extended.

## What you (Codex) must VERIFY (not hunt)

1. **ONE name, no contradictory "Ledger-First"-as-separate-name.** Confirm the spec and hook use exactly one name "Claude Codex Workflow" and explicitly reject splitting it into a separate "Ledger-First"/"Prove-First" named mode. Flag any place the text implies a second named process.
2. **The always-via-Workflow-function rule is explicit + consistent in BOTH files.** Confirm both the spec (HARD RULE block + invariants) and the hook (invariant 7 + NAMED TRIGGER text) say "always via the Anthropic Workflow FUNCTION, never inline" with no contradiction between them.
3. **Hook still exit-0 fail-soft, JSON contract + trigger detection unchanged (only the reminder TEXT extended).** Confirm from the diff that no control-flow / trigger-detection / JSON-emission code changed — only the docstring REMINDER text + two invariant bullets were added. (Smoke evidence above corroborates: fail-soft exit 0, valid JSON, gated trigger line.)
4. **No working invariant deleted.** Confirm invariants 1-6 and the prior NAMED TRIGGER semantics survive unchanged; the edit only ADDS (invariants 7+8, HARD RULE block, Prove-first section) and rewords the NAMED TRIGGER paragraph without dropping its existing content (Codex-only gate, operator-BLIND announce rule).
5. **CLAUDE.md untouched (pinned).** Confirm the diff contains NO change to CLAUDE.md, and that the spec correctly documents the §3.0.1 edit as DEFERRED to the signed-reconciliation flow because CLAUDE.md is canonical-pinned.

## Output schema (REQUIRED — emit this exact YAML, with a final `verdict:` line)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1. End your output with a single final line `verdict: APPROVE` or `verdict: REQUEST_CHANGES`.

---

## THE DIFF UNDER REVIEW

```diff
diff --git a/.claude/hooks/polaris_task_cycle_reminder.py b/.claude/hooks/polaris_task_cycle_reminder.py
index 0ed3912b..7795ecec 100644
--- a/.claude/hooks/polaris_task_cycle_reminder.py
+++ b/.claude/hooks/polaris_task_cycle_reminder.py
@@ -70,16 +70,28 @@ Non-negotiable invariants (these are what the 4-role drift violated):
      merger). Live testing / auto-merge enabled ONLY after everything is fixed.
   6. Between merge and next branch: ZERO prose (Â§8.2). Stop is Codex's call,
      not Claude's (Â§8.3.10).
+  7. ONE name: "Claude Codex Workflow" (no sub-labels). ALWAYS run it via the
+     Anthropic Workflow FUNCTION, NEVER inline (operator reaffirmed 2026-06-09).
+  8. Prove-first (the standard content of every run): write the Claims Ledger
+     (every claim -> file:line -> live/staged/roadmap/removed) BEFORE building;
+     build from the ledger not memory; batch-fix the whole class (sibling-grep);
+     self-run the rubric; hand Codex an EVIDENCE PACK (changes + ledger + smoke
+     command/output/artifact) to VERIFY not hunt; answer each finding
+     id -> fixed line -> sibling-grep proof.
 
 Full spec: CLAUDE.md Â§3.0.1 + .claude/workflows/polaris_task_cycle.md.
 
 NAMED TRIGGER (operator, 2026-05-29): "Claude Codex Workflow" (or "with Claude Codex
-Workflow") is the operator's invocation phrase for THIS loop. When the operator says it
-â€” and equivalently the keywords 'exec:' / 'task:' â€” RUN this loop via the Anthropic
-Workflow FUNCTION (the background workflow engine that spawns the BRIEF / BUILD / SMOKE /
-Codex-gate agents in phases), with Codex as the ONLY gate. Operator is BLIND: ANNOUNCE
-each workflow launch in one plain spoken line as it fires, and read the key result inline
-â€” do NOT rely on the /workflows panel (a screen reader cannot see it)."""
+Workflow") is the operator's ONE invocation phrase for THIS loop (no sub-labels). When the
+operator says it â€” and equivalently the keywords 'exec:' / 'task:' â€” ALWAYS RUN this loop
+via the Anthropic Workflow FUNCTION, NEVER inline (operator reaffirmed 2026-06-09) â€” the
+background workflow engine that spawns the BRIEF / BUILD / SMOKE / Codex-gate agents in
+phases, with Codex as the ONLY gate. Prove-first is the standard content of every run:
+Claims Ledger (every claim -> file:line -> live/staged) BEFORE building; self-run the
+rubric; hand Codex an EVIDENCE PACK to VERIFY not hunt; batch-fix the whole class; answer
+findings id -> line -> sibling-grep. Operator is BLIND: ANNOUNCE each workflow launch in one
+plain spoken line as it fires, and read the key result inline â€” do NOT rely on the
+/workflows panel (a screen reader cannot see it)."""
 
 
 # Case-insensitive trigger phrases that mean "run the loop via the Workflow function".
diff --git a/.claude/workflows/polaris_task_cycle.md b/.claude/workflows/polaris_task_cycle.md
index 2e18dd2d..0e7302c4 100644
--- a/.claude/workflows/polaris_task_cycle.md
+++ b/.claude/workflows/polaris_task_cycle.md
@@ -6,6 +6,22 @@ driven by the **Anthropic Workflow function** as the engine, with **Codex as the
 gate**. The keywords `exec:` / `task:` are equivalent triggers. This file is the spec the
 per-prompt hook (`.claude/hooks/polaris_task_cycle_reminder.py`) points to.
 
+**ONE name (no sub-labels).** There is exactly **one** name for this process: **"Claude Codex
+Workflow."** It is NOT split into a separate "Ledger-First Workflow", "Prove-First Workflow",
+or any other variant. The prove-first / Claims-Ledger discipline (see the section below) is the
+**standard content of every Claude Codex Workflow run** â€” not a different named mode. When you
+hear the one phrase, you run the one loop, and prove-first is built into it.
+
+**HARD RULE â€” always via the Anthropic Workflow FUNCTION, never inline (operator reaffirmed
+2026-06-09).** Every "Claude Codex Workflow" run MUST execute INSIDE the Anthropic **Workflow
+function** (the background workflow engine that spawns the BRIEF / BUILD / SMOKE / Codex-gate
+agents in ordered phases). Running the loop "inline" â€” ad-hoc foreground `codex exec` calls
+stitched together by hand in the main turn â€” is a DRIFT and is forbidden. The operator has
+repeat-flagged the inline drift ("I keep giving this directive, you just drift to inline"). The
+first substantive action when the trigger fires is therefore: **author the Workflow-function
+script**, then run it. The 2026-05-29 "few brief-gates run as direct foreground `codex exec`"
+deviation noted at the bottom of this file is the exact pattern this HARD RULE now closes.
+
 ## What the phrase binds to
 
 When the operator says **"Claude Codex Workflow"**, Claude:
@@ -36,6 +52,60 @@ When the operator says **"Claude Codex Workflow"**, Claude:
 5. Stop is Codex's call / a documented halt / an explicit operator stop â€” not Claude's
    self-initiated cadence (Â§8.3.10).
 
+## Prove-first discipline (the standard content of every Claude Codex Workflow)
+
+This is NOT a separate workflow â€” it is the standard content every Claude Codex Workflow run
+carries. Build in this order, every time:
+
+1. **Pin done + non-goals.** Confirm the canonical pin (CLAUDE.md Â§3.1 step 0) is green and
+   state the non-goals up front: what this change deliberately does NOT touch. A pinned file
+   (e.g. CLAUDE.md) is a non-goal here â€” its edit is DEFERRED to the signed-reconciliation flow.
+2. **Claims Ledger BEFORE building.** Write the ledger first. Every claim maps to a
+   `proof file:line` and a `status` of `live` / `staged` / `roadmap` / `removed`. **Nothing
+   enters the build unless it is ledgered.** The ledger is the spec; the diff implements it.
+3. **Sibling-scan + batch-fix the whole class.** Before writing one fix, grep for siblings of
+   the same shape (all call sites, all consumers, all parallel constants) and fix the entire
+   class in one pass â€” never the single instance the symptom pointed at.
+4. **Build from the ledger, not from memory.** Implement exactly what the ledger asserts. If a
+   line isn't in the ledger, it doesn't go in the diff. Memory is a TL;DR, not the source.
+5. **Self-run a fixed 12-point rubric BEFORE Codex sees it.** Score the change against:
+   (1) claimâ†”proof â€” every claim has a real file:line;
+   (2) staged-vs-live honesty â€” `staged`/`roadmap` never described as already `live`;
+   (3) number honesty â€” counts/sizes/line-refs are real, re-checked, not estimated;
+   (4) internal consistency â€” no two parts of the change contradict;
+   (5) sibling-consistency â€” the whole class is fixed, not one instance;
+   (6) fail-closed safety â€” on error the change fails closed/loud, never silently degrades;
+   (7) runtime-truth â€” claims about runtime behaviour are verified by running, not assumed;
+   (8) acceptance-criteria-verbatim â€” the issue's acceptance criteria are met word-for-word;
+   (9) non-goals â€” nothing outside the declared scope was touched;
+   (10) no-magic-numbers â€” thresholds/paths come from config/const/env, not inline literals;
+   (11) smoke-with-evidence â€” a smoke ran and produced a real artifact, not a "should work";
+   (12) prior-findings-answered â€” every earlier Codex finding has an idâ†’lineâ†’fix answer.
+6. **Hand Codex an EVIDENCE PACK â€” Codex + own deep audit run in PARALLEL.** Give Codex the
+   changes + the Claims Ledger + the smoke command/output/artifact path so Codex **VERIFIES**
+   rather than **hunts**. In parallel, run your own deep Â§-1.1 line-by-line audit. Two
+   independent audits, cross-reviewed (CLAUDE.md Â§-1.1).
+7. **Answer each finding: id â†’ fixed line â†’ sibling-grep proof.** For every Codex finding,
+   record the finding id, the exact line that now fixes it, and a sibling-grep proving no
+   other instance of the same class survives.
+8. **Codex APPROVE (0 P0/P1) â†’ UI gets a SEPARATE live eyes-on gate â†’ commit.** Codex is the
+   only review gate; APPROVE requires zero P0 and zero P1. If the change touches
+   `web/app/**` or `web/components/**`, a SEPARATE live visual eyes-on gate
+   (`scripts/visual_review_gate.py` against `.codex/visual_audit_rubric.md`) must also pass
+   before commit. Claude does NOT merge (Â§3.0).
+
+**Why this is binding (cite):**
+- **Codex names the Claims Ledger the #1 lever** â€” the ledger-before-build step is what turns a
+  Codex review from a hunt into a verification, which is where its review power concentrates.
+- **"LLMs Cannot Self-Correct Reasoning Yet" (Huang et al., ICLR 2024)** + **Anthropic's
+  finding that a model grading its own output skews positive** â€” together these mean a
+  **different-vendor Codex gate has real teeth** that a same-family self-check does not. The
+  Opus `advisor` is the **same family** as the author and is therefore **never a substitute**
+  for the Codex gate (CHARTER Â§1; operator memory `feedback_no_opus_advisor_use_codex_cli`).
+- **GitHub Spec-Kit â€” "gate the brief harder than the diff"** â€” most defects are cheaper to
+  catch at the spec/brief stage than at the diff stage, which is why the brief gate (gate 1)
+  and the ledger (step 2) carry the load.
+
 ## Operator is BLIND â€” visibility rule (binding)
 
 The Workflow function runs in the **background** and its live progress is only in the
@@ -51,7 +121,10 @@ Workflow fires, Claude MUST:
 ## Recorded in
 
 - `.claude/hooks/polaris_task_cycle_reminder.py` (per-prompt re-injection + trigger detection)
-- `CLAUDE.md` Â§3.0.1 (authoritative project directive)
+- `CLAUDE.md` Â§3.0.1 (authoritative project directive) â€” the matching prove-first edit to
+  Â§3.0.1 is **DEFERRED**: CLAUDE.md is canonical-PINNED (`docs/canonical_pin.txt`), so it can
+  only change via the user-signed reconciliation flow (CLAUDE.md Â§3.1 step 0), not a plain
+  commit. This file and the hook carry the prove-first content until that reconciliation lands.
 - this file (`.claude/workflows/polaris_task_cycle.md`)
 - operator memory (`feedback_claude_codex_workflow_named_trigger_2026_05_29.md`)
 - GitHub (issue comment on #935 + this committed file)
```
