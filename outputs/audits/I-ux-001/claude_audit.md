# Claude architect audit — I-ux-001 (GH#872, operating model + plan)

**Branch:** `bot/I-ux-001-operating-model` (off `polaris`).
**Plan source:** the operator's 2026-05-24 S-tier experience directive.
**Codex review trajectory:** plan iter 1→4 (APPROVE iter 4, `convergence_call: accept_remaining`, zero P0/P1 — under the operator's UNCAPPED iteration override for the plan).

## What's in this PR

1. **`docs/stier_experience_directive_2026_05_24.md`** — the operator's directive + full operating model + frontier-product research synthesis (proof-as-hero whitespace).
2. **Anti-drift hooks** — `.claude/hooks/stier_directive.txt`, `stier_session_start.py` (re-injects directive on startup/resume/compact via SessionStart `additionalContext`), `stier_stop_hook.py` (blocks premature stop while #872 OPEN, gates on objective GitHub state). Wired in `.claude/settings.json`.
3. **`state/restart_instructions.md`** — rewritten to the I-ux-001 current step.
4. **`docs/stier_experience_plan.md`** — Codex iter-4 APPROVE'd plan (v4): two-judgment moat (faithfulness + evidence-strength + signed two-family receipt + offline-verifiable), one verified-brief workspace (artifact-centric, not route-centric), 6-beat "challenge any sentence" hero, clinical evidence-strength layer (outcome-level GRADE Summary of Findings), intended-use/regulatory posture, verifier-trust honesty, anti-cherry-picking source controls, execution-safe offline-verify, concrete 90s PM demo script.

## Codex review trajectory (uncapped per operator override)

| iter | verdict | findings |
|---|---|---|
| 1 | REQUEST_CHANGES | overclaim of uniqueness; route-centric not artifact-centric; hero too weak |
| 2 | REQUEST_CHANGES | clinical-safety method (GRADE per-sentence wrong); regulatory/intended-use missing; verifier over-trust |
| 3 | REQUEST_CHANGES | one honest P0 — "signed bundle" wasn't actually signed (CI-guard'd in I-ux-001a) |
| 4 | **APPROVE** | zero P0/P1; convergence_call=accept_remaining |

Plan APPROVED summary: `.codex/I-ux-001/PLAN_APPROVED.md`. Verdicts under `.codex/I-ux-001/codex_plan_verdict_iter*.txt`.

## Closes / unblocks
- Sets up the operating model + plan that all subsequent I-ux-001a/b/c sub-issues consume.
- #874 (Prereq 0 — real signed bundle) is the first execution unit; PR #875.
- #876 (foundation — design tokens v2 + components catalogue + storyboard) is the second; PR #877.
