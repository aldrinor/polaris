HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- Read ONLY `.codex/I-meta-002-q1d-diversity/codex_diff.patch`. Emit the YAML verdict block FIRST, then ≤6 sentences.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

# DIFF gate — #956 (S2): source-diversity passes. Patch: 3 files, +370 (selector +224, retriever +4, tests +142).

You APPROVED the design at brief iter 1 with rulings: k=1, cap_frac=0.5, reservation BEFORE domain cap, main
truncating path only, kill-switch OFF = byte-identical, and the P2 invariant: diversity touches ONLY post-floor
slack and MUST preserve tier minimums. Verify the patch honors that EXACTLY.

## EXPLICIT RULING REQUESTED — 200-LOC soft cap
The non-test additions are ~228 LOC (> the 200-LOC soft cap). The excess is largely docstring/comment for
clinical-safety review (the two helper functions + the integration block carry ~100 lines of explanatory
comments) plus the helper config readers. Please RULE: APPROVE-with-exemption (excess is comment/test, logic
is contained + fully tested) OR REQUEST_CHANGES to split into two PRs (reservation; then per-domain cap). I
will do whichever you direct.

## What the patch does
1. `live_retriever.py` (+4): the evidence row gains `"query_origin": getattr(cand, "query_origin", "") or ""`
   (additive; absent/empty for seed-lane/legacy rows). Nothing else in the retriever changes.
2. `evidence_selector.py` (+224): helpers `_row_query_origin`, `_row_domain`, `_subquery_reserve_config`
   (PG_SELECT_SUBQUERY_RESERVE default ON / PG_SELECT_SUBQUERY_K default 1), `_domain_cap_config`
   (PG_SELECT_DOMAIN_CAP default ON / PG_SELECT_DOMAIN_CAP_FRAC default 0.5), `_priority_sort_key`,
   `_reserve_subqueries`, `_apply_domain_cap`. Wiring: a `_t3_floor_protected_ids` accumulator captures the
   T3 jurisdiction/HC reserved ids (snapshotted BEFORE the T3 relevance-fill); a diversity block runs JUST
   BEFORE the final sort — reservation first, then domain cap — with
   `protected_ids = m42e_primary_ids | m42c_mech_ids | m51_inserted_ids | _t3_floor_protected_ids`
   (and the cap also treats sub-query-reserved rows as protected). Telemetry appended only when a pass fires.
3. Both passes are SAME-TIER swaps: an evicted row and its replacement are always the same tier, so per-tier
   counts (the tier quota minimums) are invariant. Reservation evicts only NON-protected slack rows whose
   origin is OVER-represented (count > k). Domain cap evicts only NON-protected slack rows of an over-cap
   domain and YIELDS (stops) when no same-tier under-cap replacement exists.

## Evidence (verified by Claude main-thread, NO SPEND)
- 9 new #956 tests + 175 total across the selector + #955 recency + #956 suites PASS:
  under-represented sub-query reaches selection; kill-switch off lets one origin dominate (prior behavior) +
  no telemetry; domain cap limits dominance to <= ceil(0.5*max_rows) and pulls in the other domain; kill-switch
  off lets one domain dominate; tier minimums preserved (per-tier counts identical on/off); named-trial primary
  floor NOT evicted by diversity; domain cap YIELDS (no crash, full selection) when no same-tier replacement;
  short-pool path unaffected.
- 1 selector-suite test fails — PRE-EXISTING + independent (test_m42_preservation reads a drifted
  outputs/full_scale_v26 artifact; fails identically with this diff stashed; filed #975). NOT this diff.
- `py_compile` OK on both source files.

## The real risks to rule on
1. Can a diversity swap drop a tier below its quota? (Claim: no — swaps are strictly same-tier; per-tier
   counts invariant. Test `test_tier_minimums_preserved` pins this.)
2. Can a diversity swap evict a floor-reserved (M-42e/M-51/M-42c/M-42d-T3) or a sub-query-reserved row?
   (Claim: no — protected_ids covers all four floors; the cap pass also protects reservation rows.)
3. Does the per-domain cap ever leave max_rows unfilled? (Claim: no — it only SWAPS, and yields rather than
   evict-without-replace.)
4. Is the `_t3_floor_protected_ids` snapshot taken BEFORE the T3 relevance-fill (so only juris/HC floor rows,
   not T3 fill, are protected)? Verify the insertion point.
5. Kill-switches OFF → no swaps, no telemetry, byte-identical selection? (Tests pin both.)
6. Determinism (deterministic origin/domain ordering + priority key + original index)?

APPROVE iff the diff implements the brief-approved soft same-tier diversity (post-floor slack only, tier
minimums preserved, floors + reservations protected, cap yields, never unfills), kill-switch restores prior
behavior, and you grant the 200-LOC exemption (else REQUEST_CHANGES to split).
