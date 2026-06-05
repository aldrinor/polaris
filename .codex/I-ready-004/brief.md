# Brief — I-ready-004 (#1078): CAPPED finding-dedup for Gate-B + float-safe floor — ITER 2

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## iter-1 verdict was REQUEST_CHANGES (2 P1, 1 P2). Both P1s + the P2 incorporated. You decided dedup_mode=capped_dedup, defer_model_rerank=yes — locked into the scope below.

## Context (unchanged, condensed)
The P1 silent-throttle (1000→~20 unfloored) is ALREADY closed+tested by #1070 (slate
`PG_LIVE_MAX_EV_TO_GEN=150`, preflight floor 100, test catches the =20 bug value). This issue's
residual = the ranking-quality gap. Model-based cross-encoder rerank + embedding semantic dedup are
DEFERRED to an operator-gated follow-up (§8.4 — heavy ML only on direct operator instruction). This
issue ships the §8.4-safe, pure-logic capped finding-dedup.

## The build (capped dedup — your iter-1 P1-1 + P1-2 baked in)

**1. Capped finding-dedup selection (NOT the existing no-cap relevance-floor mode).**
The existing `PG_USE_FINDING_DEDUP` flag routes `select_evidence_for_generation` to
`_relevance_floor_selection` (L1065), which REPLACES `PG_LIVE_MAX_EV_TO_GEN` with a no-cap floor pool
— that would regress #1070's cap guarantee (unbounded generator pool at 1000 URLs). So Gate-B must
NOT use that path as-is. Instead:
- Add a CAPPED dedup path: (a) compute lexical relevance + apply `PG_RELEVANCE_FLOOR` as a pure-logic
  filter (drop rows below floor); (b) collapse near-duplicate FINDINGS to one representative on the
  IDENTICAL score (reuse the existing finding-dedup grouping — `FindingDedupResult` /
  `_relevance_floor_selection`'s dedup grouping helper, NO recompute); (c) THEN enforce the existing
  tier-balanced top-`PG_LIVE_MAX_EV_TO_GEN` selection on the deduped pool. Net: ≤ PG_LIVE_MAX_EV_TO_GEN
  rows, near-dups removed, floor applied — #1070's cap + floor both still hold.
- Gate this on a NEW explicit flag (e.g. `PG_BENCHMARK_CAPPED_DEDUP=1`) OR make the existing
  `PG_USE_FINDING_DEDUP` capped-by-default when `PG_LIVE_MAX_EV_TO_GEN` is set — your call on the
  cleanest shape; either way the selected count MUST be ≤ PG_LIVE_MAX_EV_TO_GEN. Default OFF outside
  Gate-B (legacy honest-sweep selection byte-unchanged).

**2. Float-safe `PG_RELEVANCE_FLOOR` (your iter-1 P1-2).**
`_BENCHMARK_PREFLIGHT_FLOORS` is `dict[str, int]` — a float like `0.30` would be coerced to int 0 and
then fail `parse_relevance_floor` (valid range (0.0, 1.0]). So `PG_RELEVANCE_FLOOR` must NOT use the
integer slate-floor path. Add explicit float handling: put it in the string slate
(`_FULL_CAPABILITY_BENCHMARK_SLATE`) as e.g. `"0.30"`, and validate it in `preflight_full_capability`
via `parse_relevance_floor` (float, (0.0,1.0]) — a separate required-float check, NOT in the int
floors dict. Require `PG_USE_FINDING_DEDUP`/the capped-dedup flag for Gate-B in the preflight
required-flags set.

**3. Offline tests (your iter-1 P2):**
- `select_evidence_for_generation` (capped-dedup ON) with N≫cap rows incl. duplicate findings →
  assert selected count ≤ `PG_LIVE_MAX_EV_TO_GEN` AND duplicate findings collapsed to one rep.
- Assert `PG_USE_FINDING_DEDUP`/capped flag + a float `PG_RELEVANCE_FLOOR` are in the Gate-B slate and
  PASS preflight; a bad float (e.g. "1.5" or "0") FAILS preflight (fail-closed).
- Assert fail-closed if the generation cap is BELOW the floor-eligible minimum (no silent empty pool).
- Re-run existing `test_evidence_to_generation_cap_iready001.py` + `test_m201_evidence_selection.py`
  to prove #1070's cap/floor still hold under the new path.

**4. Defer the model-based rerank** (cross-encoder + SemHash/MinHash embedding dedup) to a NEW
operator-gated follow-up issue (§8.4). File it; do not build here.

## Files I have ALSO checked
- `evidence_selector.py` import-pure (no model2vec/sentence_transformers/embed) — capped dedup is
  pure-logic, §8.4-safe.
- `live_retriever.py` has no semhash/MinHash (semantic dedup genuinely unwired — that's the deferred
  follow-up).
- Faithfulness (provenance + strict_verify + 4-role D8) is downstream of selection — untouched.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
