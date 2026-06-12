# DEEP FORENSIC — keystone map-reduce distiller collapses every section to 0 verified

The map-reduce evidence distiller (the #1209/#1217 keystone) makes the report EMPTY on the real model. This is a structural bug hunt. Find the SINGLE root cause + the ONE right fix. Be specific (file:line). Do NOT just confirm a hypothesis — investigate independently and challenge.

## THE FACTS (3 live runs on drb_76 Safety section, deepseek-v4-pro)
- LEGACY path (PG_SECTION_DISTILL OFF): 6-9 strict_verify-VERIFIED sentences, 137-160 words, rich cited prose. drop_rate ~0.33-0.50.
- DISTILL path (keystone ON): ALWAYS 0 verified, 29 words = the abort placeholder "No claim in this section survived strict verification ... curator-actionable gap." drop_rate = 1.00 (strict_verify drops 100% of the REDUCE prose).
- 38-41 of ~40 MAP calls DO produce findings (median ~400 output tokens). So extraction works.
- The REDUCE generate() received only ~750-1700 input tokens in runs 1-2 (small validated ledger).

## FIXES ALREADY TRIED THAT DID NOT HELP (rule them out, look deeper)
1. Span-recovery in _validate_finding step-1 (whitespace-flexible quote match) — distill still 0.
2. Relaxed filter_and_strip_reduce_markers (any [#ev] token, not exact evidence_id binding) — still 0.
3. Made the per-finding step-6 entailment NON-BLOCKING (so more findings flow) — still 0, drop_rate still 1.00.

## THE CENTRAL QUESTION
Why does strict_verify drop 100% of the REDUCE (distill) prose but only ~50% of the LEGACY prose, on the same evidence + same model? What is STRUCTURALLY different between how legacy _call_section produces verifiable [#ev]-cited prose vs how the REDUCE branch produces it?

## INVESTIGATE THE FULL PATH (read every function, compare legacy vs distill)
- src/polaris_graph/generator/evidence_distiller.py: distill_section_evidence, _validate_finding, render_reduce_user, _REDUCE_SYSTEM (the REDUCE prompt — what does it INSTRUCT the model to emit?), filter_and_strip_reduce_markers.
- src/polaris_graph/generator/multi_section_generator.py: _call_section (BOTH the legacy raw-evidence branch AND the new distillate REDUCE branch ~line 1697-2050), _run_section (the marker-strip call + _rewrite_draft_with_spans + the strict_verify call), the LEGACY section system prompt vs _REDUCE_SYSTEM.
- src/polaris_graph/clinical_generator/strict_verify.py: how is a sentence's [#ev:evidence_id:start-end] token validated? (numeric-in-span + content-overlap >=2 words + entailment). What EXACTLY makes a sentence VERIFIED vs dropped?
- How does _rewrite_draft_with_spans transform the draft for legacy vs for the distill REDUCE output? Does the REDUCE's pre-formed [#ev:...] token survive _rewrite_draft_with_spans, or does that function only work on the legacy [ev_XXX] short-form and MANGLE/IGNORE the REDUCE's full tokens?

## SPECIFIC SUSPECTS (confirm or refute each with file:line)
(a) The REDUCE emits full [#ev:evidence_id:start-end] tokens, but _rewrite_draft_with_spans (which the LEGACY path relies on to CONVERT [ev_XXX] -> [#ev:...]) treats the REDUCE output differently and the REDUCE's tokens don't end up in the form strict_verify expects.
(b) The REDUCE paraphrases the finding claim, so the content-overlap / numeric / entailment check in strict_verify fails (legacy prose stays closer to spans).
(c) The marker-strip drops everything BEFORE strict_verify (the REDUCE doesn't emit the [[finding:fXXX]] markers the filter requires, so 100% dropped pre-verify).
(d) The distillate span offsets (start-end) are offsets into the SOURCE direct_quote, but strict_verify resolves [#ev:evidence_id:start-end] offsets against a DIFFERENT text (e.g. the evidence_pool row's full text vs the direct_quote), so every span is wrong.
(e) The REDUCE section-writer model returns reasoning-only / tiny content (reasoning-first starvation) so there is almost no prose to verify.

## DELIVER
The single structural root cause (which suspect, with file:line proof), why the 3 fixes missed it, and the ONE specific change to make distill >= legacy without weakening strict_verify. If the map-reduce architecture is fundamentally incompatible with strict_verify's span-matching, SAY SO and propose the alternative.
