# Claude line-by-line forensic — #1218 thinness (distill 2 < legacy 6 on drb_76 Safety)

## Land mine 1 — MAP does not demand EXHAUSTIVE extraction
`_MAP_SYSTEM` (evidence_distiller.py:180-187): "You extract atomic, provenance-preserving findings ... Each finding must be one atomic claim ... If no section-relevant finding exists, return no_relevant_findings=true." It NEVER says "extract EVERY distinct finding" or "include all numeric outcomes." A model told to "extract findings" returns a few salient ones (the qualitative contraindications) and stops, leaving the numeric safety facts (odds ratios, fatality rates, contamination/AMR risk) that legacy mines.
- faithful_content_lost: the OR-14/CI 4-44 stat, contamination/AMR-transfer risk — all in the source, all on-topic, never extracted.
- FIX (extraction-side): `_MAP_SYSTEM` + `_render_map_user` — instruct EXHAUSTIVE extraction: "Extract EVERY distinct section-relevant finding — each numeric outcome (incidence/rate/fatality/odds-ratio/hazard-ratio/CI), each contraindication, each adverse-event signal — as its OWN atomic finding. Do not stop at the most salient few." faithfulness_safe: TRUE (more candidates -> strict_verify still the sole gate).

## Land mine 2 — MAP bundles SCATTERED numbers into one "finding"; final span binder can't co-locate them
The dropped sentence cited ONE finding (f004_000) carrying numbers 24, 19, 10, 3, 32. The source has "24 patients (19%)" in one place and "odds ratio 10, 95% CI 3-32" in another (>800 chars apart likely). `_find_best_span_for_sentence` (live_deepseek_generator.py:244) HARD-REQUIRES every sentence decimal in ONE ~800-char window; if the numbers are scattered it returns the fallback span -> strict_verify's numbers-in-span fails -> the FAITHFUL sentence is DROPPED.
- faithful_content_lost: "odds ratio of 10 (95% CI 3-32) ... 24 patients (19%)" — real source stats, dropped on binding.
- FIX (extraction-side): MAP "each finding's support_quote MUST be a CONTIGUOUS source slice that contains EVERY number in the claim; if the relevant numbers are not contiguous in the source, SPLIT into separate findings, each with its own contiguous support_quote." faithfulness_safe: TRUE.

## Land mine 3 — REDUCE allows multi-number "conjunction" sentences
`_REDUCE_SYSTEM` (:189-205): "A sentence must be exactly one type: single-source claim, multi-source conjunction, or conflict-limitation." The "conjunction" path lets the model merge distinct numeric findings into one sentence whose numbers span multiple source locations -> same binding failure as land mine 2.
- FIX (shaping-side): REDUCE "Write ONE numeric result per sentence; never merge two distinct statistics into one sentence. A sentence's numbers must all come from ONE finding's support_quote." faithfulness_safe: TRUE (strict_verify still the gate; this only changes sentence SHAPE so numbers bind).

## Faithfulness invariant
All three fixes are MAP-extraction-side or REDUCE-output-shaping-side. strict_verify / _find_best_span_for_sentence / 4-role / D8 are byte-UNTOUCHED. More/atomic findings -> the final strict_verify still re-checks every published sentence; nothing unfaithful can pass.

## Honesty caveats
- "numbers >800 chars apart" is inferred (the OR-10 sentence dropped on binding); not yet measured exactly. The fix (contiguous support_quote per finding) is correct regardless.
- MAP under-extraction is run-to-run variable (one run got the OR-10 finding, another didn't) — the exhaustive-extraction instruction reduces the variance.
