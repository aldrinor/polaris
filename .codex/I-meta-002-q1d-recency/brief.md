HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
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

# BRIEF gate — #955 (S2): within-tier recency tiebreaker in evidence_selector (no-spend)

Reviewing ACCEPTANCE CRITERIA + DESIGN (not a diff). This is a LOWER-PRIORITY S2 refinement; keep the fix
minimal and conservative. The bar: recency must be a SOFT tiebreaker that NEVER hard-drops a row and NEVER
displaces a clearly-more-relevant row. Be adversarial about any way recency could demote a more-relevant or
higher-tier source.

## The finding (issue #955, Codex-area CONFIRMED #950)
`src/polaris_graph/retrieval/live_retriever.py` fetches Semantic Scholar `year` (L170 fields, L215 hit dict,
L1508 `metadata={"year": ...}`) but the selector never uses it. `evidence_selector.select_evidence_for_generation`
ranks within a tier purely by `(-relevance_score, original_index)` (L756 main path; L566-574 short-pool path;
L1091 final deterministic sort). So a 2014 review and a 2025 pivotal RCT in the same tier compete only on
tier + lexical relevance. The sweep's FreshnessDetector (run_honest_sweep_r3.py:842-856) is a v1 stub
returning UNCHANGED and is a SEPARATE Phase-F Crossref *network* probe — OUT OF SCOPE here (the fix is a
no-network selector tiebreaker, not a freshness probe).

## Proposed design (no network; reads year already on the row)
1. `_row_year(row) -> int | None`: reads `row.get("year")`, else `row.get("metadata", {}).get("year")`;
   coerces to int; returns None if absent / non-numeric / outside a sane range (e.g. 1900..2100). No network.
2. Recency as a within-tier-band SOFT tiebreaker. Relevance stays the PRIMARY key. To make recency actually
   bite for near-ties (the 2014-vs-2025 case) without overriding real relevance gaps, bucket the relevance
   score into bands of width `epsilon`: rows in the SAME tier AND SAME relevance band order by higher year
   first; ties below that fall back to original_index (unchanged determinism).
   - Sort key becomes `(tier_priority, relevance_band_desc, year_desc, original_index)` where
     `relevance_band = floor(score / epsilon)` (epsilon>0) or exact score (epsilon==0 → pure exact-tie only).
   - Missing year (`None`) sorts AFTER any dated row within the same band (treated as year = -inf), so a
     dated row wins a same-band tie but recency NEVER hard-drops the undated row (it stays selectable, just
     ordered lower within its band).
3. Applied consistently to BOTH selection paths: main within-tier sort (L756), the short-pool ordered
   selection (L566-574), and the final deterministic sort (L1091). The M-42e/M-51/M-42c/M-42d floors are
   UNCHANGED — recency only orders WITHIN what a tier/floor already admits; it never evicts a reserved
   primary/mechanism/HC row.
4. Kill-switch `PG_SELECT_RECENCY_TIEBREAK` (default ON; OFF → byte-identical prior ordering) +
   `PG_SELECT_RECENCY_EPSILON` (relevance band width). **Open question for you to rule on: the default
   epsilon.** Options: (a) 0.0 = pure exact-score-tie tiebreaker (safest, rarely fires, may not fix the
   2014-vs-2025 case); (b) a small band e.g. 0.05 (recency breaks near-ties, still can't override a real
   relevance gap). I lean (b) with a conservative value; rule on the exact default + whether banding is
   acceptable given "soft floor, never hard-drop."
5. Telemetry: a `notes` entry when recency reordered ≥1 row, for sweep audits.

## The real risks to rule on
1. Can recency EVER hard-drop a row or push a row out of the selected set? (Claim: no — it only reorders
   within a tier/band; truncation still happens by tier quota which is unchanged. But verify the final-sort
   reorder can't change WHICH rows survive a `[:quota]` slice. NOTE: in the main path, within-tier picks
   happen via quota slices BEFORE the final sort — so a within-tier sort change CAN change which rows fill a
   quota. Is that acceptable as "soft floor"? It reorders by recency only within the same relevance band, so
   a more-relevant row is never dropped for an older one — but a same-band older row could lose its slot to a
   same-band newer row. Rule on whether that is within "soft tiebreaker, never hard-drop the MORE-relevant".)
2. Does banding risk demoting a higher-relevance row that happens to land one band below a newer lower-relevance
   row? (Claim: no — banding is monotonic in score; a higher band always sorts ahead regardless of year.)
3. Missing-year handling: does treating None as -inf ever harm an undated authoritative source? (It orders
   lower within its band but is never dropped if it's in the quota by relevance.)
4. Determinism preserved (original_index final fallback) and kill-switch gives byte-identical prior order?
5. Floors (M-42e primary / M-51 / M-42c mechanism / M-42d HC) still reserve their rows unaffected?

## Files I have ALSO checked
- src/polaris_graph/retrieval/live_retriever.py — year source (L170/215/1508 metadata). No change needed.
- scripts/run_honest_sweep_r3.py:842-856 — FreshnessDetector stub = separate Phase-F network probe, OUT OF SCOPE.
- tests/polaris_graph/: test_m201_evidence_selection, test_m42c/d/e, test_m46_selector_no_bypass,
  test_m51_selector_primary_custody, test_m41_v24_regression, test_m42_preservation, test_pass2_remediation,
  test_m48_anchor_variants — ALL must stay green (no-regression). New test file for the recency tiebreaker.

## Acceptance criteria
A. `_row_year` reads year from row or row.metadata, coerces to int, None on absent/invalid/out-of-range; no network.
B. Recency is a within-tier-band SOFT tiebreaker after relevance; never hard-drops; never demotes a
   higher-relevance-band row; floors unaffected.
C. Applied consistently to main within-tier sort, short-pool path, and final sort.
D. Kill-switch OFF → byte-identical prior ordering. Epsilon configurable; default per your ruling.
E. Telemetry note when recency reorders. New tests: same-tier same-band newer-wins; relevance gap still wins
   over recency; missing-year not dropped; kill-switch off = prior order; floors still reserve. All 11
   existing selector tests stay green.

Is this design correct + safe (recency strictly soft, no hard-drop, floors intact), and what default epsilon?
