HARD ITERATION CAP: 5 per document. This is iter 2 of 5.

## iter-1 → iter-2 changelog (Codex diff-gate P1 ADOPTED)
iter-1 P1: the detector checked `len(contribs) >= 2` + distinct bound_ev_id but NOT distinct entity identity,
so two payloads for the SAME non-trial entity (distinct ev) could emit a "comparison" of one entity against
itself. FIXED in `_detect_shared_attribute_patterns`: contribs now carry entity_id; the pool is deduped to
ONE contrib per distinct entity_id (deterministic by display_name,value); the gate now requires ≥2 DISTINCT
ENTITIES (`len(contribs) < 2` after dedup → skip) AND ≥2 distinct bound_ev_id. The early pre-filter is also
`len({f.entity_id for f in generic}) < 2`. New regression test `test_same_entity_two_sources_does_not_emit`
(same entity_id, 2 sources → no pattern). 10 #957 tests + 14 M-72 tests pass. Re-verify the regenerated patch.


- Front-load ALL findings. Reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- Read ONLY `.codex/I-meta-002-q1d-comparative/codex_diff.patch`. Emit the YAML verdict block FIRST, then ≤6 sentences.

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

# DIFF gate — #957 (S2): generalize comparative synthesis. Patch: 1 src + 1 test, +283/-10 (src +154).

You APPROVED the brief at iter 2 with the 3-part guard (comparability + atomic-value + distinct-bound_ev_id),
non-trial-frames-only containment, neutral wording (no "across sources"), and kill-switch
`PG_SYNTH_GENERIC_COMPARATIVE` default ON → OFF byte-identical. Verify the patch implements EXACTLY that.

## What the patch does (cross_trial_synthesis.py)
1. `_EntityFrame` (entity_id, display_name, is_trial, fields: name→(value, bound_ev_id)).
2. Guards: `_is_comparable_field_name` (denylist: rationale/interpretation/limitation/narrative/summary/
   conclusion/discussion/context/note/comment/caveat/assessment/background/overview);
   `_is_atomic_value` (len ≤160, no newline, ≤1 sentence-ending `[.?!](?:\s|$)` — a decimal "2.1" is NOT a
   sentence end so atomic numbers pass).
3. `_aggregate_entity_frames`: keeps EVERY entity with ≥1 extracted field; is_trial via the existing
   `^([a-z0-9_]+?)_(primary|secondary|cvot)$` regex; stores each field's (value, bound_ev_id).
4. `_detect_shared_attribute_patterns`: NON-trial entities only; for a field that passes the comparability
   guard and is shared by ≥2 entities with ≥2 DISTINCT bound_ev_id, emits a `_CrossTrialPattern`
   (pattern_type "generic_attribute_comparison", section "Comparative") whose summary is
   "Extracted {field} values — {A}: {vA}; {B}: {vB}." (deterministic sort; ev markers = the distinct ids).
5. `build_cross_trial_synthesis` restructured: trial detectors run when ≥2 trial frames (UNCHANGED path);
   the generic detector runs regardless behind the kill-switch. In a pure-trial run there are no non-trial
   entities → generic is a no-op → trial output byte-identical. OFF → generic skipped entirely.
   `render_cross_trial_synthesis_block` is UNCHANGED.

## Evidence (verified by Claude main-thread, NO SPEND)
- 9 new tests pass: comparable-field-name guard; atomic-value guard (incl. "2.1%" atomic, multi-sentence /
  long / multi-line rejected); generic emitted for a comparable field across 2 non-trial entities with
  distinct ev (neutral wording, both values, no "across sources", ev markers = both ids); NARRATIVE field →
  none; non-atomic value → none; SAME bound_ev_id pair → none; single entity → none; TRIAL entities excluded
  from generic; kill-switch OFF → none.
- 14 existing M-72 cross-trial tests PASS (trial path unchanged). `py_compile` OK.

## The real risks to rule on
1. Can the generic detector emit a comparison without distinct provenance? (Claim: no — `len(distinct_evs) < 2`
   → skip.)
2. Can a narrative/free-text slot reach the synthesis prompt? (Claim: no — comparability guard rejects
   narrative field-names AND non-atomic values; both checked.)
3. Is the trial path byte-identical (≥2 trial frames → same detectors; non-trial entities absent → generic
   no-op)? Verify the restructured build() didn't change trial behavior.
4. Kill-switch OFF → no aggregation, no patterns, no behavior change?
5. Does it synthesize any comparative CONCLUSION, or only restate extracted values? (Must be restatement only;
   downstream strict_verify guards the LLM's integrated sentence as today.)
6. Anything beyond the 1 src + 1 test file / beyond the approved design?

APPROVE iff the diff implements the iter-2-approved guarded restatement (comparability + atomic + distinct
provenance, non-trial only, neutral wording), keeps the trial path byte-identical, kill-switch restores prior
behavior, and introduces no comparative-inference fabrication surface.
