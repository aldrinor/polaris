Diff review iter 5 for GH#423 Phase 3. Output YAML.

HARD ITERATION CAP: 5 per document. This is iter 5 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Iter-4 P1 RESOLVED — conflict guard lifted to top-level precondition

You caught: the iter-3 conflict guard lived inside Path 2 only, so Path 1 (≥2 shared decimals) and Path 3 (≥2 shared dollar buckets) could short-circuit-match before the guard fired. Example: 3.0%/1.6% of $40K/$80K in 2014 vs 3.0%/1.6% of $200K/$300K in 2014 → Path 1 matches because 2 decimals overlap, despite dollar conflict.

Fix: lifted `years_conflict` / `dollars_conflict` check to a top-level precondition that fires BEFORE Path 1, Path 2, and Path 3. Path 0 (exact-signature equality) is unaffected — by definition identical signatures cannot have a populated-axis conflict.

```python
# After Path 0 exact-equality check…
years_conflict = (a.years and b.years) and not (a.years & b.years)
dollars_conflict = (
    (a.dollar_buckets and b.dollar_buckets)
    and not (a.dollar_buckets & b.dollar_buckets)
)
if years_conflict or dollars_conflict:
    return False
# Path 1 / Path 2 / Path 3 now run only after conflict check passes
```

# 3 new regression tests covering all three heuristic paths

- `test_signatures_overlap_path1_two_decimals_disjoint_dollars_blocks`: 3.0%/1.6% with $40K/$80K vs $200K/$300K (years overlap, dollars conflict) → BLOCK via Path 1 → Path 1 path
- `test_signatures_overlap_path3_two_dollars_disjoint_years_blocks`: $40K/$200K in 2014 vs $40K/$200K in 2018 (dollars overlap, years conflict) → BLOCK via Path 3 → Path 3 path
- `test_signatures_overlap_path1_two_decimals_compatible_context_matches`: positive Path 1 case — 9.2% / 13.9% with one side empty year axis (no conflict possible) → MATCH preserved

# Updated decision matrix (heuristic paths after Path 0 + conflict guard)

| sig_a context | sig_b context | Path that matches | Outcome |
|---|---|---|---|
| {3.0,1.6}/{$40K,$80K}/{2014} | {3.0,1.6}/{$200K,$300K}/{2014} | Path 1 → BLOCKED by guard | BLOCK |
| {3.0,1.6}/{$40K,$80K}/{2014} | {3.0,1.6}/{$200K,$300K}/{2014} | (dollars conflict) | BLOCK |
| {$40K,$200K}/{2014} | {$40K,$200K}/{2018} | Path 3 → BLOCKED by guard | BLOCK |
| {3.0}/{$40K}/{2014} | {3.0}/{$200K}/{2014} | Path 2 → BLOCKED | BLOCK |
| {9.2,13.9}/{2014} | {9.2,13.9}/(empty) | Path 1 → no conflict possible | MATCH |
| {3.0}/{$40K}/{2014} | {3.0}/{$40K} | Path 2 supporting overlap | MATCH |
| {$200} | {$200} | Path 0 | MATCH |

# Test results

```
PYTHONPATH=src pytest tests/polaris_graph/test_fact_dedup.py
43 passed (40 iter 4 + 3 iter 5 path1/path3 conflict regression)
```

# Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
