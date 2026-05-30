# Claude architect audit — #957 (S2): generalize cross-source comparative synthesis

**Branch:** `bot/I-meta-002-q1d-comparative` (off the depth tip; touches generator only, no selector/retriever
conflict). **Brief gate:** APPROVE iter 2 (P1 comparability+provenance guard adopted). **Diff gate:** pending.
**NO SPEND.**

## Why
`cross_trial_synthesis.py` was SURPASS/tirzepatide-bound: `_aggregate_trial_frames` only kept
`<anchor>_(primary|secondary|cvot)` entities and the 3 detectors hardcode T2D prose. For golden Qs with no
trial contract the cross-source layer was simply absent.

## Fix
A domain-agnostic generic detector runs on NON-trial contract entities only (trial runs byte-identical),
emitting a NEUTRAL RESTATEMENT of already-extracted slot values — never a synthesized comparison. Three
guards keep it from opening a fabrication surface (Codex iter-2 P1): comparability (field-name not narrative;
value atomic ≤160 chars + single-clause), distinct provenance (≥2 contributing entities with distinct
`bound_ev_id`), and plain wording ("Extracted {field} values — …", no "across sources"). `build_cross_trial_synthesis`
restructured to run the generic path regardless of trial-frame count, behind kill-switch
`PG_SYNTH_GENERIC_COMPARATIVE` (default ON) → OFF byte-identical. Downstream strict_verify still guards the
LLM's integrated sentence.

## Safety
- No comparative conclusion is synthesized — only verbatim slot values are restated.
- Narrative/free-text slots and same-source pairs cannot emit (tests pin both).
- Trial path unchanged (generic detector ignores trial entities; 14 M-72 tests green).
- Kill-switch OFF = exact prior behavior.

## Tests
9 new + 14 existing M-72 pass. `py_compile` OK. NO SPEND.

## Verdict
Generalizes the comparison layer to any domain WHERE structured entity payloads exist, strictly as a guarded
neutral restatement (comparability + atomic + distinct provenance), trial path byte-identical,
kill-switchable, offline-tested. Brief APPROVE iter 2; diff gate next.
