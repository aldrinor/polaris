HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-perm-011 (#1205) — Open the binding over-aggressive throttle (0.30 relevance floor denominator pathology) + fix extraction_yield telemetry

## Problem (data-backed diagnosis, already approved)

drb_76 funnel: 597 pre-select evidence rows -> 53 selected. The 544 drop is the `PG_RELEVANCE_FLOOR=0.30` floor, NOT dedup (dedup collapsed 0) and NOT a lane clobber (the agentic +47 / STORM +52 lanes are additive `merge_seed_url_evidence`, append-only).

Root cause: `_row_relevance` (src/polaris_graph/retrieval/evidence_selector.py:406-423) scores `overlap / len(question_tokens | protocol_tokens)`. The denominator scales with question LENGTH. drb_76's research_question is a ~73-content-token multi-part paragraph, so clearing 0.30 requires >=22 exact-word matches. Excellent on-topic top-tier (T1) clinical papers fail on vocabulary mismatch (Fusobacterium/butyrate/tumorigenesis don't lexically overlap "predominant/mitigate/retard/equilibrium/dietary"). Of 114 T1 sources, 100 dropped; title-split shows 74 are genuinely on-topic (Nature/Cell/Science/Gut CRC-microbiota). Over-aggressive bug, not legitimate filtering.

A blind "lower the floor to 0.15" is rejected by the diagnosis: max_ev=1500 makes the floor the only binding gate, and the post-fix pool size cannot be predicted from persisted data, so lowering it blindly risks re-creating #1070's flood.

## Fix (two coupled parts, both flag-gated)

### Part A — max-over-subqueries scoring (real code, evidence_selector.py)
Score each row against the BEST-MATCHING SUB-QUERY, not the whole 73-token paragraph. The run decomposes into q1d + STORM sub-queries (`_research_plan.sub_queries` + `_decomposed`, both locals in `run_one_query` and in scope at the two floor-path call sites 4650, 5240). Each sub-query has a small token denominator, so a row strongly matching ONE facet clears the floor instead of being diluted.

Implementation:
- New flag `PG_SELECT_SUBQUERY_FLOOR` (default OFF). OFF or empty `sub_queries` => byte-identical (`_row_relevance` unchanged).
- New optional param `sub_queries: list[str] | None = None` on `select_evidence_for_generation`, threaded ONLY to the two floor-path sites (4650, 5240). `_capped_finding_dedup_selection` (986) calls with `relevance_floor=None` => tier path, NOT threaded.
- New helper `_row_relevance_subquery_max(row, question_tokens, protocol_tokens, subquery_token_sets)`: returns `max(existing_whole_question_score, max_over_subqueries(overlap/len(subq_toks)))`. Monotonic-UP: a row never scores LOWER than today, so flag-ON keeps strictly MORE rows. Clamped to [0,1].
- Threaded into both `_relevance_floor_selection` and the tier-balanced scoring loop ONLY when the flag is on AND subquery sets are non-empty; otherwise the call is `_row_relevance` exactly as today.

### Part B — slate activation (run_gate_b.py) — cap DELIBERATELY NOT lowered
Add `PG_SELECT_SUBQUERY_FLOOR=1` to the Gate-B slate (force-on, exact "1") so the fix is ON exactly where the run happens. Keep `PG_RELEVANCE_FLOOR=0.30`.

The diagnosis's secondary "lower PG_LIVE_MAX_EV_TO_GEN 1500->200" is NOT applied. Primary-source reason (run_gate_b.py:475-482, OPERATOR DECISION 2026-06-10, same I-perm campaign): the 1500 pool is intentional — each section independently selects its own rows capped by PG_MAX_EV_PER_SECTION=40 (the BINDING per-prompt guard), so the global pool cap only STARVES niche sections. Non-binding-by-construction proof: the post-fix surviving pool <= the pre-select total (597 for drb_76) < 1500, so the cap never binds on this run; lowering it to 200 would re-impose a throttle at 200 and shrink the universe each section draws its 40 from. Declining it ALIGNS with the operator decision (no flood premise holds; #1070 guard is per-section, not pool-global).

### Part C — telemetry (run_honest_sweep_r3.py)
`extraction_yield.finding_rows` is the FROZEN main-lane snapshot (498), misnamed as pipeline extraction yield. `extraction_yield.finding_rows` IS consumed (tests/polaris_graph/retrieval/test_source_funnel_telemetry.py asserts exact dict shape) — so DO NOT rename; ADD keys, gated:
- `total_extracted_rows` = `len(retrieval.evidence_rows)` (post-merge pre-select pool, 597) — added in `_retrieval_manifest_section` ONLY when `PG_SELECT_SUBQUERY_FLOOR` on (slate-absent => no new key => byte-identical manifest + existing tests still pass).
- `selected_to_generator` = `len(evidence_selection.selected_rows)` after the capped-dedup reassignment (53) — surfaced at the manifest site (6825) where `evidence_selection` is in scope, gated by the same flag.

## Safety
- Flag OFF / slate-absent => byte-identical (scores unchanged, no new telemetry keys, no new manifest keys).
- Faithfulness gates (strict_verify / 4-role / D8) UNTOUCHED — this only changes which rows reach the generator, then the same downstream verification runs.
- Monotonic-up scoring => flag-ON keeps a SUPERSET of flag-OFF rows; never drops a row that would survive today.

## Files ALSO checked and clean
- `_capped_finding_dedup_selection` (986): `relevance_floor=None` => tier path, no floor scoring, no thread needed.
- `_reserve_subqueries` (696): uses `query_origin` LABELS not sub-query TEXT; unrelated to scoring.
- test_source_funnel_telemetry.py: asserts `extraction_yield == {"fetched":N,"finding_rows":M}` exact — preserved because new keys are flag-gated (OFF in those tests).

## Test
`tests/polaris_graph/retrieval/test_subquery_floor_relevance.py`: synthetic row matching ONE facet strongly but scoring <0.30 against the whole 73-token question. Assert kept when flag ON + sub_queries provided, dropped when OFF (byte-identical). Plus a monotonic-superset assertion.

## Schema
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
