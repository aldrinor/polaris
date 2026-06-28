HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW MODE: STATIC only. Do NOT run pytest / the pipeline / broad exploration. Read the diff file `.codex/I-retr-001/iretr001_diff.patch` and the changed source `src/polaris_graph/retrieval/scope_query_validator.py` + test `tests/polaris_graph/test_scope_query_validator.py`. Emit the verdict schema at the end.

# I-retr-001 (#1340) — scope_query_validator default measure flip (jaccard → containment) to fix breadth collapse

## Problem (confirmed on a real paid run)
A fresh drb_72 run cited only 2 sources because `scope_query_validator` dropped 33 of 35 generated queries:
`[scope_validator] measure=jaccard floor=0.15 kept=2 dropped=33 (anchor_tokens=136)`.
Symmetric Jaccard(query, anchor) is structurally near-impossible against a LONG anchor: the anchor is the full
research question (drb_72 = 136 tokens), so a perfectly on-topic 8-token query caps at |q∩a|/|q∪a| ≈ 8/136 ≈ 0.06,
far below the 0.15 floor → dropped before it issues a search. This is the §-1.3 FILTER-strangles-breadth anti-pattern.

## Root cause
The CORRECT measure already exists in code — `_containment` = |q∩a| / min(|q|,|a|) (overlap-coefficient, normalizes
by the smaller set, so a short on-topic query scores ~1.0 while genuine off-anchor drift still scores low). The
Gate-B benchmark slate already pins `PG_SCOPE_SIM_MEASURE=containment` + `PG_AMPLIFIER_SCOPE_FLOOR=0.08`. But the
CODE DEFAULTS were `jaccard` / 0.15 (a deliberate BB-001 "byte-identical OFF" choice), and `run_honest_sweep_r3.py`
does NOT apply the Gate-B slate — so every non-Gate-B run path inherited the broken default.

## The change (the ONLY diff — `.codex/I-retr-001/iretr001_diff.patch`)
1. Flip the CODE DEFAULTS to the right measure for ALL run paths: `_DEFAULT_SIM_MEASURE = "containment"`,
   `_DEFAULT_SCOPE_FLOOR = 0.08` (named module constants, LAW VI). `_select_sim_measure()` default → containment;
   floor fallback → 0.08. `jaccard` remains selectable via `PG_SCOPE_SIM_MEASURE` (back-compat).
2. Update docstrings/comments that described `jaccard`-default "byte-identical OFF" (now misleading).
3. Tests: updated `test_floor_environment_variable_is_respected` (its premise — a short on-topic query scoring low —
   was jaccard-specific; under containment a fully-on-topic query scores 1.0, so it now uses a PARTIAL-overlap query
   that still drops at floor 0.80). Added `test_default_similarity_measure_is_containment` and the drb_72 regression
   `test_long_anchor_short_query_kept_under_default` (short on-topic queries vs a long anchor are KEPT under defaults).

## Validation (offline; I ran it, you do NOT need to)
- 9/9 tests in test_scope_query_validator.py pass. 49/49 adjacent planner+saturation tests pass.
- The de-drift GATE is preserved: the off-scope tests (Japan elderly care, blockchain) still DROP under containment.

## Things to verify (be adversarial)
1. Is the default flip correct and safe? Does containment still DROP genuine off-anchor drift (gate preserved), not
   just keep everything? Walk `_containment` vs `_jaccard`.
2. Any run path that legitimately depended on the jaccard/0.15 default and would now behave wrong? (Gate-B sets its
   own values explicitly, so it's unaffected.)
3. LAW VI: are the new defaults named constants, env-overridable? Any magic numbers introduced?
4. Faithfulness: confirm this is a pre-fetch query/scope gate only — no strict_verify / NLI / 4-role / span / provenance touched.
5. Did the test edits weaken coverage (e.g. the floor-env test still meaningfully asserts the floor bites)?

## Output schema (REQUIRED, last lines)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
