# Claude architect audit — #955 (S2): within-tier recency tiebreaker

**Branch:** `bot/I-meta-002-q1d-recency-tiebreaker` (on the depth tip). **Brief gate:** APPROVE iter 1 (2 P2
conditions adopted). **Diff gate:** pending. **NO SPEND** — pure stdlib + offline pytest.

## Why
S2 `year` is fetched (live_retriever) and lands on the row but the selector ranked within a tier purely by
relevance, so a 2014 review and a 2025 RCT in the same tier competed only on tier + lexical. The
FreshnessDetector is a separate Phase-F network probe (out of scope).

## Fix
Recency as a SOFT within-tier-band tiebreaker. `_relevance_recency_key` (enabled) = `(-band, year_sort, -score)`
where `band = floor(score/0.05)`. The trailing `-score` is the key design point: band is monotonic in score
and the exact `-score` sub-key restores exact ordering within a band, so an **all-undated corpus reproduces
the prior pure-(-score) order exactly** — recency only reorders DATED same-band rows. Applied to the main
within-tier sort, the final sort, and the short-pool ordered sort, always keeping priority-class + tier ahead
(Codex P2b). Kill-switch `PG_SELECT_RECENCY_TIEBREAK` (default ON) → OFF restores `(-score,)` + suppresses
telemetry. Floors (M-42e/M-51/M-42c/M-42d) unchanged.

## Safety (Codex P2 conditions, both honored)
- P2a: documented in the helper comment — recency CAN change which same-band row fills a quota slot, but
  never costs a higher-band (more-relevant) row its slot. Test `test_truncation_slot_goes_to_newer_in_same_band`
  pins exactly this.
- P2b: priority-class + tier remain the leading sort keys at all three sites; recency only orders within.
- Never hard-drops: undated rows stay eligible (`test_missing_year_not_dropped`); a relevance gap always wins
  (`test_relevance_gap_beats_recency`).

## Tests (12 new, pass) + no-regression
12 new + 165 selector-suite tests PASS. ONE suite test fails — `test_m42_preservation::test_nice_count...` —
but it is PRE-EXISTING and independent: it reads a static drifted working-tree artifact
(`outputs/full_scale_v26/...`), not the live selector; with this diff stashed it fails identically (nice=0).
Out of scope for #955; correct follow-up is a separate data-artifact issue.

## Verdict
Recency is strictly soft (banded, within-tier, floors + tiers ahead, exact-score sub-tiebreaker makes undated
corpora byte-identical to prior), never hard-drops a more-relevant row, kill-switchable, offline-tested NO
SPEND. Brief APPROVE iter 1; diff gate next.
