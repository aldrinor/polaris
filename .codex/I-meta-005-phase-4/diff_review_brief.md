REVIEW DISCIPLINE (read first): FOCUSED DIFF REVIEW. Review ONLY the diff in
`.codex/I-meta-005-phase-4/codex_diff.patch` against the brief
`.codex/I-meta-005-phase-4/brief.md`. Do NOT run a repo-wide audit. Open at most
the 7 changed files + the brief. This is iter 3: your iter-1 P1 + iter-1 P2b are
already APPROVE-confirmed; your job now is to confirm the iter-2 residual P2a is
fully closed, and surface any NEW real blocker.

HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Status: iter-2 APPROVE'd. This iter only confirms the residual P2a fix.

Iter 2 verdict: APPROVE (0 P0, 0 P1), one accept_remaining P2a:
"`summary["saturation"]` is populated but the final success/partial manifest does
not copy it to `manifest["saturation"]`, and the patch records dropped section
titles/shortfall but not the uncovered sub-query TEXT."

### P2a — now COMPLETED (verify), run_honest_sweep_r3.py:
1. The partial branch's `_dropped_detail` now includes
   `"uncovered_sub_queries"` for each dropped section = the TEXT of the uncovered
   planned sub-questions (the unit's `empty_facets` if any, else the unit's full
   `sub_query_indices`), resolved against `_research_plan.sub_queries` with a
   bounds guard.
2. After the `research_plan` manifest block, the success/partial manifest now does
   `if summary.get("saturation"): manifest["saturation"] = summary["saturation"]`
   — ON-mode only, so the OFF manifest shape is byte-preserved.

VERIFY: (a) `manifest["saturation"]` is present on BOTH success and
partial_saturation runs and absent in OFF; (b) `uncovered_sub_queries` resolves the
correct plan sub-query text with no index error; (c) no double-write / shape drift;
(d) nothing else changed since the iter-2 APPROVE (P1 V30 re-inject, P2b early-break
gate, degenerate-novelty fix all unchanged).

## Unchanged (already APPROVE-confirmed at iter 2 — do NOT re-litigate unless a NEW defect)
- P1: gap-round re-injects the round-0 prepend (upload + V30 contract) via suffix-diff.
- P2b: need-type early-break gated on anchor_seed; legacy domain-runner :555 untouched.
- Degenerate-novelty fix: RoundOutcome.prev_corpus_rows + raw new_round_rows.
- OFF byte-identity: anchor_seed/partial_mode default legacy; loop only under
  PG_USE_RESEARCH_PLANNER. Money: zero generator tokens until PROCEED/partial.

## Smoke (committed tree, HEAD 2e3ede33)
- test_saturation_phase4.py: 27 passed. Regression (adequacy+planning+discovery+md9
  + retrieval): 153 passed.

## Output schema (REQUIRED — loose prose rejected)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
