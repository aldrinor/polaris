# Codex DIFF review — I-perm-004 (#1198) SLICE 4 #1180 widening bakeoff — ITER 2 (confirm P1+P2 fix)

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Reserve P0/P1 for real execution risks. If iter 5 REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Your iter-1 verdict was REQUEST_CHANGES with ONE P1 + ONE P2. Both fixed. Verify against the code.

### P1 (RESOLVED): pick_winner ignored the CONTRADICTED anchor (a variant could win while accepting a contradiction)
Fix (`widening_prompt_candidates.py`): `score_predictions` now counts `contradiction_accepted` (gold=CONTRADICTED predicted ENTAILED). `pick_winner` adds `and int(s.get("contradiction_accepted", 0)) == 0` to the eligibility filter — ANY variant that ever grades a contradiction as ENTAILED is INELIGIBLE regardless of its widening recall / entailed precision; fail-safe to "baseline" if none clears. New regression tests `test_pick_winner_rejects_contradiction_acceptance` + `test_score_tracks_contradiction_accepted`. Confirm a variant with perfect recall+precision but `contradiction_accepted>0` now loses to a clean variant (and to baseline if it is the only candidate).

### P2 (RESOLVED): validate_variants did not enforce both {span} and {sentence}
Fix (`widening_prompt_bakeoff.py`): the probe now substitutes distinct sentinel tokens and asserts BOTH `PROBE_SPAN_TOKEN` and `PROBE_SENTENCE_TOKEN` appear in the formatted output — a template omitting `{sentence}` now fails validation.

## Unchanged (you confirmed iter-1): default byte-identical (C1), entailed-precision floor (C2), no §-1.1 gold label to change. The only change since iter-1 is the two fixes above.

## Files (full cumulative diff: `.codex/I-perm-004/slice4_codex_diff.patch`)
- `widening_prompt_candidates.py`: contradiction_accepted in scorer + pick_winner eligibility.
- `widening_prompt_bakeoff.py`: validator both-placeholder check.
- `test_widening_prompt_bakeoff_iperm004.py`: +2 contradiction-safety tests.
- (entailment_judge.py / labeled_set.json unchanged since iter-1.)

## Test evidence: 10 bakeoff-substrate green (incl. the 2 new contradiction-safety tests); 49 entailment-judge (byte-identical default) green.

Confirm the contradiction-safety gate makes a contradiction-accepting variant ineligible. Hunt any remaining §-1.1 hole in the winner selection.
