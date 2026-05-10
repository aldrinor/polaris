## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 3 of 5. Verdict APPROVE iff zero P0/P1.
```

## §1 — Iter-2 P1 disposition

| Iter-2 finding | Iter-3 fix |
|---|---|
| **P1** Aggregator BEAT-ONE wrongly fires when polaris ahead of one but behind the other; canonical classifies as BEHIND. | **FIXED.** Mirrors canonical scripts/run_m_live_2_beat_both.py:527-543: cmp_one() returns ahead/behind/tie per competitor; verdict from ahead_count/behind_count: 2 ahead → BEAT-BOTH; 1 ahead AND 0 behind → BEAT-ONE; 2 behind → BEHIND-BOTH; ≥1 behind → BEHIND; else TIE. New regression tests `test_ahead_one_behind_one_classifies_as_behind` (Codex's example: 1200 vs 1000/2000 → BEHIND) and `test_behind_both_distinct_from_behind` (50 vs 1000/2000 → BEHIND-BOTH). |

## §2 — Diff scope

scripts/aggregate_beat_both_runs.py +~225 (canonical taxonomy); tests +~310 (13 tests). All 13 pass in 1.64s.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
