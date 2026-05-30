# Claude architect audit — #956 (S2): source-diversity / per-sub-query reservation + per-domain soft cap

**Branch:** `bot/I-meta-002-q1d-source-diversity` (stacked on the #955 recency branch to avoid an
evidence_selector conflict). **Brief gate:** APPROVE iter 1 (P2 invariant adopted). **Diff gate:** pending.
**NO SPEND.**

## Why
Tier quota != topical diversity: 20 T1 RCTs all on one of a question's sub-topics satisfy the T1 quota while
starving the others, tanking per-sub-topic benchmark coverage. The fetch stage already reserves 1 slot per
sub-query (#959); the live gap is the SELECTOR (+ no per-domain cap).

## Fix
One additive retriever line propagates `query_origin` onto the evidence row. Two SOFT selector passes run
just before the final sort on the main truncating path: (1) round-robin per-sub-query reservation (k=1),
(2) per-domain soft cap (cap = ceil(0.5*max_rows)). Both are SAME-TIER swaps — an evicted row and its
replacement share a tier — so per-tier counts (the tier quota minimums) are invariant (Codex P2). Reservation
evicts only NON-protected slack rows whose origin is over-represented; the domain cap evicts only NON-protected
slack rows of an over-cap domain and YIELDS when no same-tier under-cap replacement exists. `protected_ids`
covers all four floors (M-42e primary, M-42c mechanism, M-51 anchor custody, T3 jurisdiction/HC via a
snapshot taken before the T3 relevance-fill) plus sub-query-reserved rows (so the cap can't undo a
reservation). Kill-switches `PG_SELECT_SUBQUERY_RESERVE` / `PG_SELECT_DOMAIN_CAP` (default ON) → OFF = no
swaps, no telemetry, byte-identical prior selection.

## Safety
- Tier minimums preserved (same-tier swaps; `test_tier_minimums_preserved`).
- Floors + reservations never evicted (`test_floor_primary_not_evicted_by_diversity`).
- Never unfills max_rows; cap yields gracefully (`test_domain_cap_yields_when_no_same_tier_replacement`).
- Short-pool path untouched (`test_short_pool_path_unaffected`).
- Kill-switch off = prior non-diverse behavior + no telemetry (two tests).

## Tests + no-regression
9 new + 175 across selector + #955 recency + #956 suites PASS. One pre-existing failure
(test_m42_preservation, drifted outputs/full_scale_v26 artifact, #975) is independent — fails identically with
this diff stashed.

## Open item for Codex
Non-test additions ~228 LOC > the 200-LOC soft cap (excess is largely clinical-safety docstring/comment +
config readers). Ruling requested in the diff brief: APPROVE-with-exemption or split into reservation + cap PRs.

## Verdict
Diversity is strictly soft (post-floor slack, same-tier, tier minimums + floors + reservations protected, cap
yields, never unfills), kill-switchable, offline-tested NO SPEND. Brief APPROVE iter 1; diff gate (+ LOC
ruling) next.
