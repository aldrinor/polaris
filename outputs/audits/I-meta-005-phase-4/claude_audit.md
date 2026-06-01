# Claude architect audit — I-meta-005 Phase 4 (#988) multi-round saturation

**Verdict: APPROVE (post-fix).** Build matches the Codex-APPROVED brief
`.codex/I-meta-005-phase-4/brief.md` and `build_spec.md`. Two issues found in
review, both resolved before this audit; re-smoke green.

## Scope reviewed
Full diff vs base `8ebfe1cb`, 7 code files:
`saturation.py` (new, pure decision logic), `run_honest_sweep_r3.py` (loop
wiring + `_run_gap_round`), `live_retriever.py` + `domain_backends.py`
(`anchor_seed` seam), `multi_section_generator.py` (`partial_mode`),
`regression_lab.py` (taxonomy mirror), `test_saturation_phase4.py` (26 cases).

## Axes (all CLEAN post-fix)
- `off_byte_identity_ok` — `anchor_seed` defaults True on both seams;
  `partial_mode` defaults False; loop only runs under `PG_USE_RESEARCH_PLANNER`.
  Retrieval/adequacy/planning + md9/generator regression green (131 tests).
- `budget_never_exceeded_ok` — pre-spend truncation `floor(remaining/cost)`,
  worst-case `per_query_discovery_cost = 2 + adapter_count`; P4-14 pins it.
- `gap_only_both_seams_ok` — gap round fires gap sub-queries on BOTH the core
  Serper/S2 seam and the need-type adapters with no anchor re-fire; P4-10 pins.
- `partial_out_of_plan_disabled_ok` — all FIVE out-of-plan appenders hard-gated
  off in `partial_mode`; P4-7/7b/7c pin pruned plan + index remap.
- `zero_generator_bill_until_proceed_ok` — generator billed exactly once on
  STOP_SUFFICIENT (P4-6); partial path on STOP_NOVELTY/STOP_BUDGET.

## P1 found and FIXED — degenerate novelty stop (the live signal was dead)
`_run_gap_round` returned the DEDUPED additions (`_new_rows`) as
`new_round_rows`, the exact key `marginal_novelty` consumes. Because every
element was novel-by-construction, novelty read 1.0 whenever a round added ≥1
row and 0.0 only when it added exactly zero — so `eps` was never exercised and
STOP_NOVELTY fired ONLY at exactly-zero-new, not on diminishing returns.

**Test-masking:** P4-5 fed `new_round_rows` containing duplicates — a shape
`_run_gap_round` never produced — so the green test validated a path the
production code couldn't reach.

**Fix:** hand the RAW retrieved rows (`_gap_ret.evidence_rows`, dups included)
as the novelty DENOMINATOR; snapshot the corpus BEFORE the merge as a new
explicit `RoundOutcome.prev_corpus_rows` baseline; loop scores
`marginal_novelty(prev_corpus_rows, new_round_rows)` directly (no fragile
object-identity subtraction). Only deduped `_new_rows` still append to the
cumulative corpus. Stub `_StubLoopDriver` made shape-faithful (snapshot-before-
merge + raw rows). New **P4-5b** regression pin: a round retrieving 20 rows
where 19 are dups → novelty 0.05 (< eps, > 0) → STOP_NOVELTY; RED on old shape,
GREEN on fix.

## Process issue found and FIXED — incomplete build in git
At the build checkpoint, 4 of the build's files (`live_retriever.py`,
`domain_backends.py`, `multi_section_generator.py`, `regression_lab.py`) were
in the working tree but UNCOMMITTED — smoke passed against them but
`git diff base..HEAD` would have shown an incomplete, broken diff (the loop
calls `anchor_seed=False`/`run_need_type_backends(anchor_seed=...)` which don't
exist without them; `partial_saturation` taxonomy unregistered). Caught during
patch regeneration; committed as `2ac0a678`. The diff Codex now reviews is
complete.

## Codex diff-gate iter 1 — REQUEST_CHANGES (1 P1 + 2 P2), all resolved
The diff-gate caught a real P1 the green smoke missed:
- **P1 — gap rounds drop V30 contract evidence.** `_run_gap_round` re-injected
  only upload rows after re-selection; the V30 contract rows prepended before the
  round-0 gate were dropped, so after any expansion the gate + generator no longer
  saw the V30-augmented billed set. Fixed by capturing the round-0 selection
  baseline and re-injecting the exact same prepend (upload + V30 contract,
  suffix-diff) every gap round.
- **P2a — partial_saturation not observable.** Now persists `summary["saturation"]`
  (decision, rounds, novelty trajectory, kept/dropped sections, per-section
  shortfall) into the manifest.
- **P2b — gap-round early-break starvation.** The legacy result-count break is now
  gated on `anchor_seed`; gap rounds fire all budget-truncated facets. NEW test
  P4-10b pins both modes.
All three deterministically resolved; 27 saturation + 153 regression green;
re-gated iter 2 to confirm the P1 is closed.

## Money
Zero spend. Build + smoke are spend-free (decision logic pure; live round
injected; `_NoLiveClientSentinel` asserts no live client constructed). Generator
billed only on PROCEED/partial.
