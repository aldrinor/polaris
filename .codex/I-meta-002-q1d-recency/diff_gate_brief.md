HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- Read ONLY `.codex/I-meta-002-q1d-recency/codex_diff.patch`. Emit the YAML verdict block FIRST, then ≤6 sentences.

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

# DIFF gate — #955 (S2): within-tier recency tiebreaker. Patch: 2 files, +288/-5.

You APPROVED the design at brief iter 1, with two P2 conditions: (P2a) document that same-tier/same-band
recency can change which row fills a quota slot; (P2b) keep floor priority classes + tier AHEAD of recency.
Epsilon default ruled = 0.05. Verify the patch honors these EXACTLY.

## What the patch does (evidence_selector.py)
1. Helpers: `_row_year` (row['year'] or row['metadata']['year']; int; None if absent/invalid/outside
   [1900,2100]; no network). `_relevance_band(score, eps)` = `floor(score/eps)`, or raw score if eps<=0.
   `_year_sort_value` = `-(year or 1899)` so newer sorts first, undated last. `_relevance_recency_key`:
   disabled → `(-score,)` (byte-identical prior key); enabled → `(-band, year_sort, -score)`.
   **Note the trailing `-score`**: within a band, after recency, EXACT score still breaks ties — so an
   ALL-UNDATED corpus reproduces the prior pure-(-score) order EXACTLY (band is monotonic in score; the
   `-score` sub-key restores exact order within a band). Recency ONLY reorders DATED same-band rows.
2. Kill-switch `PG_SELECT_RECENCY_TIEBREAK` (default ON) + `PG_SELECT_RECENCY_EPSILON` (default 0.05).
   OFF → `_relevance_recency_key` returns `(-score,)` and no telemetry note → byte-identical prior behavior.
3. Applied at THREE sort sites, each keeping prior leading keys ahead (P2b):
   - main within-tier sort: `(-score, idx)` → `(*key, idx)`.
   - final sort: `(tier, -score, idx)` → `(tier, *key, idx)`.
   - short-pool ordered: `(class, tier, -score, idx)` → `(class, tier, *key, idx)`.
   The M-42e/M-51/M-42c/M-42d floor reservation passes are UNCHANGED — they still select their matched rows;
   recency only reorders candidates WITHIN a tier/band (P2b satisfied).
4. P2a documented in a code comment at the helper block (recency may change which same-band row fills a slot;
   never costs a higher-band/more-relevant row its slot).
5. Telemetry `recency_tiebreak enabled epsilon=.. dated=N/total` note emitted ONLY when enabled.

## Tests (12 new, all pass; NO SPEND)
Helpers (year sources/bounds, band monotonic + exact mode, year_sort newer-first/undated-last, disabled key =
pure score, default eps 0.05); integration (same-band newer first; relevance gap beats recency; missing-year
not dropped; truncation slot → newer same-band row [the P2a case]; kill-switch off = index order + no
telemetry; kill-switch on emits telemetry; M-42e/M-51 primary floor still reserves a SURPASS-2 primary with
recency on).

## No-regression evidence (verified by Claude main-thread)
- 12 new + 165 of the selector suite PASS (test_m201, test_m41, test_m42c/d/e, test_m46, test_m48, test_m51,
  test_pass2_remediation).
- 1 selector-suite test FAILS but it is PRE-EXISTING and NOT caused by this diff:
  `test_m42_preservation.py::test_nice_count_at_or_above_v25_baseline` reads a STATIC working-tree artifact
  (`outputs/full_scale_v26/.../bibliography`) — it does NOT call `select_evidence_for_generation`. PROVEN
  independent: with this diff stashed (clean HEAD), the test fails identically (nice=0 < 4). The artifact has
  drifted; out of scope for #955. (Filing it as a separate data-artifact issue is the correct follow-up, not
  a change in this PR.)

## The real risks to rule on
1. Can recency cross a tier, floor priority class, or higher relevance band? (Claim: no — leading keys
   unchanged; band monotonic in score.)
2. Does the trailing `-score` truly make all-undated corpora byte-identical to the prior order? (Reason about
   the key tuple.)
3. Can recency hard-drop a row (remove from selected set) rather than just reorder? In the truncating path a
   same-band newer row CAN take a same-band older row's quota slot — is that within the approved P2a "soft"
   semantics (never drops a MORE-relevant row)?
4. Kill-switch OFF = byte-identical (key `(-score,)`, telemetry suppressed)?
5. Anything beyond the 2 files / beyond the approved design?

APPROVE iff the diff implements the brief-approved soft tiebreaker (relevance-banded, recency only within
band, floors + tiers ahead, never hard-drops a more-relevant row), kill-switch restores prior behavior, and
the only failing suite test is the proven-pre-existing artifact test.
