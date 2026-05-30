HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; classify the rest P2/P3.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd on remaining non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (emit FIRST, then ≤6 sentences)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

# BRIEF gate — #956 (S2): source-diversity / per-sub-query reservation + per-domain soft cap (no-spend)

Reviewing ACCEPTANCE CRITERIA + DESIGN (not a diff). LOWER-PRIORITY S2 refinement; keep it minimal and
conservative. This change adds passes to `evidence_selector.py`, which already has an intricate set of floors
(M-42e named-trial primary, M-51 anchor custody, M-42c mechanism, M-42d HC jurisdiction) AND the just-merged
#955 recency tiebreaker. The bar: diversity passes must be SOFT (never hard-drop a floor-reserved row, never
leave max_rows unfilled, never starve a tier) and must not regress any existing floor or the 177-test selector
suite.

## The finding (issue #956, Codex-area CONFIRMED #950)
The selector enforces a TIER quota but not topical diversity: e.g. 20 T1 RCTs all on ONE of Q76's 5 sub-topics
satisfy the T1 tier quota while starving the other 4 sub-topics → tanks per-sub-topic benchmark coverage.
NOTE the issue text is partly stale: the FETCH stage already reserves ≥1 slot per `query_origin`
(`_rerank_and_reserve`, merged #959), so the LIVE remaining gap is at SELECTION (what reaches generation) +
the absence of any per-domain cap. Scope is therefore the SELECTOR + one additive retriever line.

## Proposed design (no network; conservative; kill-switched)
1. `live_retriever.py` (ONE additive line): the evidence row built at ~L1816 gains
   `"query_origin": getattr(cand, "query_origin", "") or ""`. Candidates already carry `query_origin`
   (set at L1466/1492/1509). Purely additive field; nothing else in the retriever changes (the fetch-stage
   dedup/cap is NOT touched — it already reserves per sub-query and touching it risks dropping authoritative
   sources before tier classification).
2. `evidence_selector.py` — two new SOFT passes, AFTER the existing tier floors, BEFORE/within the relevance
   fill, both bounded by max_rows and kill-switched:
   a. **Round-robin per-sub-query reservation.** Group the pool by `row['query_origin']` (missing → a single
      `_unlabeled` bucket). Reserve up to `k` slots per distinct origin (k default 1), round-robin across
      origins in a deterministic order (by best in-origin relevance, then origin string), so every sub-topic
      present in the pool reaches generation. Reserved rows are chosen by the EXISTING within-tier ranking
      (tier priority, then #955 banded-relevance+recency). NEVER displaces an M-42e/M-51/M-42c/M-42d reserved
      row; NEVER exceeds max_rows; if origins exceed capacity, higher-best-relevance origins reserve first.
   b. **Per-domain soft cap.** No single domain (`_domain_of(source_url)`) exceeds `ceil(cap_frac * max_rows)`
      rows in the final selection (cap_frac default e.g. 0.5), UNLESS relaxing is required to (i) keep a
      floor-reserved row, (ii) keep a sub-query reservation, or (iii) fill max_rows when no other domain has
      candidates. SOFT: the cap only displaces NON-reserved relevance-fill rows of the over-represented
      domain, replacing them with the next-best row from an under-represented domain; if no replacement
      exists, the cap yields (never leaves a slot empty, never drops a reserved row).
3. Telemetry notes (emitted only when the passes fire): `subquery_reservation origins=N reserved=M k=..` and
   `domain_soft_cap capped_domain=.. moved=..`.
4. Kill-switches: `PG_SELECT_SUBQUERY_RESERVE` (default ON) + `PG_SELECT_SUBQUERY_K` (default 1);
   `PG_SELECT_DOMAIN_CAP` (default ON) + `PG_SELECT_DOMAIN_CAP_FRAC` (default per your ruling). BOTH OFF →
   byte-identical prior selection + no new telemetry.

## Open questions for you to rule on
1. Default `k` (slots reserved per sub-query): 1 (minimal, guarantees presence) vs 2.
2. Default `cap_frac` for the per-domain soft cap: 0.5? 0.4? Or express as an absolute (e.g. ≤ max_rows-1)?
3. Ordering: should the sub-query reservation run BEFORE or AFTER the per-domain cap? (Proposed: reservation
   first — guarantee sub-topic presence — then domain cap only trims NON-reserved relevance-fill rows.)
4. Should the diversity passes apply in BOTH the truncating main path AND the short-pool path, or only the
   truncating path (short-pool keeps everything, so reservation is moot but domain cap is also moot — propose
   main path only; short-pool keeps all rows so diversity is already maximal)?

## The real risks to rule on
1. Can a diversity pass hard-drop an M-42e/M-51/M-42c/M-42d floor-reserved row, or a higher-tier row, to make
   room for a lower-tier diverse row? (MUST be no — reservations + floors are protected; diversity only
   reorders/replaces NON-reserved relevance-fill rows, and the per-domain cap is soft.)
2. Can the per-domain cap leave max_rows unfilled or drop a tier below its quota? (MUST be no — soft yields.)
3. Determinism: deterministic origin/domain ordering + original_index final fallback?
4. Kill-switches OFF → byte-identical prior selection (no reservation, no cap, no telemetry)?
5. Does grouping by `query_origin` interact badly with the seed lane / `_unlabeled` rows (primary-trial seeds
   have query_origin="primary_trial_doi_seed")? Seeds should still be selectable; the `_unlabeled`/seed
   bucket is just another origin for round-robin, never penalized.

## Files I have ALSO checked
- src/polaris_graph/retrieval/live_retriever.py — `_rerank_and_reserve` (fetch-stage per-sub-query reserve,
  already present), `_domain_of` (L1164), row build (L1816), SearchCandidate.query_origin (L1466/1492/1509).
- src/polaris_graph/retrieval/query_decomposer.py — produces the sub-queries that become `query_origin`.
- tests/polaris_graph/: test_m201, test_m41, test_m42c/d/e, test_m46, test_m48, test_m51, test_pass2,
  test_recency_tiebreaker (#955, this branch's parent) — ALL must stay green. New test file for #956.

## Acceptance criteria
A. Retriever propagates `query_origin` onto the evidence row (additive only).
B. Selector round-robin reserves up to k slots per distinct sub-query, post-floor, soft, bounded by max_rows,
   never displacing a floor-reserved or higher-tier row.
C. Per-domain soft cap trims only NON-reserved relevance-fill rows of an over-represented domain; yields
   rather than leave a slot empty or drop a reserved row.
D. Applies in the main truncating path (and short-pool only if you rule it should).
E. Kill-switches OFF → byte-identical prior selection + no new telemetry. Defaults per your ruling.
F. New tests: every present sub-query reaches selection; domain cap limits dominance; floors still reserved;
   kill-switch off = prior selection; determinism. All existing selector + recency tests stay green.

Is this design correct + safe (diversity strictly soft, floors + tiers protected, never hard-drops), and what
defaults for k / cap_frac / ordering / path-scope?
