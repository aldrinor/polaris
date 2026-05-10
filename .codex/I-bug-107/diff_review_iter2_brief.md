## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 2 of 5. Verdict APPROVE iff zero P0/P1.
```

## §1 — Iter-1 P1+P2 disposition

| Iter-1 finding | Iter-2 fix |
|---|---|
| **P1** Hand-rolled 1% tolerance differs from canonical `tolerance_for(dim)`; example narrative_length 1055 vs 1000/900 wrongly published BEAT-BOTH instead of BEAT-ONE. | **FIXED.** Imports `tolerance_for` from `src.polaris_graph.audit_ir.beat_both_scoring` and uses it for all BEAT-BOTH/TIE/BEHIND classifications. New regression test `test_canonical_tolerance_used_not_hand_rolled` exercises Codex's exact example (1055 vs 1000/900) and asserts BEAT-ONE. |
| **P2** Missing all-zero N/A guard; structurally unmeasurable dimensions became TIE. | **FIXED.** Mirrors `scripts/run_m_live_2_beat_both.py:492-494` — when polaris_mean=chatgpt=gemini=0, verdict is N/A with rationale "All 3 manifests scored 0.0 — dimension not measurable". New regression test `test_all_zero_dimension_returns_na_not_tie`. |

## §2 — Diff scope

scripts/aggregate_beat_both_runs.py: +~225 (with both fixes); tests: +~250 (11 tests). All 11 pass in 1.53s.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
