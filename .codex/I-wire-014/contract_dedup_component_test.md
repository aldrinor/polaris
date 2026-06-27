# I-wire-014 (#1336) — contract-section dedup: component-test record

## What changed (surgical, 1 file)
`src/polaris_graph/generator/contract_section_runner.py` (+180/-2):
- `_contract_dedup_enabled()` — outer gate on PG_FACT_DEDUP_PROSE OR PG_CONSOLIDATION_NLI_PROSE (default-OFF byte-identical; no LLM callable constructed when off).
- `_consolidate_contract_section_sentences()` — runs the SAME `fact_dedup.dedup_pass` (B11 same-span + Jaccard/NLI prose seams) on ONE contract section's verified SVs, then re-verifies rewrites via the injected strict_verify and rebuilds the SV list EXACTLY as multi_section_generator.py:7680-7758 (keep original SV on any absent/failed rewrite). No new dedup written.
- Call site inserted after `dropped = total_in - kept` (line ~1427), BEFORE `resolve_provenance_to_citations`, so the slot-regroup runs on deduped SVs. Recomputes kept/dropped; safe-fail keeps originals on any error. Telemetry comment at the SectionResult updated (was "No dedup pass runs on contract sections").

## Routing (decided from real data, not assumed)
The drb_72 "probability of computerisation … Gaussian process classifier" restatements are EMPTY-numeric-signature (no %/$/19xx-20xx; "702" and the span offsets do not register), so they route to the PROSE path. The numeric `build_groups` path no-ops on a single section (distinct_sections<2). Jaccard pairwise = 0.33-0.49 << 0.82 floor, so PG_FACT_DEDUP_PROSE will NOT collapse these heavy paraphrases — the discriminating path is PG_CONSOLIDATION_NLI_PROSE (mutual-entailment, #1335 FIX-D). Both flags are wired; both require their masters (NLI needs PG_CONSOLIDATION_NLI too).

## Component tests
1. OFFLINE glue (deterministic, Jaccard, fake LLM/verify): 3 near-identical restatements -> 1 full restatement; citation union byte-identical; distinct claim untouched. PASS.
2. VM real-token NLI (cross-encoder, REAL banked SVs from p6_postfix_resume verification_details.json sections[1]=Empirical_Displacement): the cluster is 16 sentences across 3 DISTINCT span tokens of the same source — `:400-1200`×9, `:1000-1800`×6, `:300-1100`×1.
   - RESULT: 16 -> 9 full restatements; 7 consolidated; 0 dropped; **citation union byte-identical (consolidate-keep-all, §-1.3 held)**.
   - The wiring FIRES and is FAITHFUL. The task-acceptance "collapse to ~1" is NOT met on real tokens.

## Why 16->9, not 16->~1 (diagnosed, not asserted)
Two structural causes in the SHARED, certified NLI engine (NOT the new wiring):
1. **3-span structural cap.** FIX-D's `_nli_cite_set` includes the full `[#ev:id:start-end]` token, so the same source's `:400-1200` / `:1000-1800` / `:300-1100` are 3 non-mergeable buckets. Collapse is capped at >=3 survivors before any model runs.
2. **Sparse bidirectional cross-encoder edges within a bucket.** In the 9-member `:400-1200` bucket, `score_pairs` produced only 9 of 36 pairs, forming two disjoint cliques {0,2,3,4} and {6,7,8} -> 4 survivors. Member [1] ("contributes to the literature…", near-verbatim to [0]) formed NO bidirectional edge; member [5] carries no "702" (a genuinely lesser claim). Keeping these is faithfulness-correct, not a wiring bug.

## NOT forced (banned anti-pattern §-1.3)
A stronger collapse would require keying the guard on ev-id-not-span, or weakening bidirectional->unidirectional, or relaxing the num-subset guard — all loosen a multi_section-CERTIFIED faithfulness guard. Deliberately NOT done here. The residual ~1-vs-9 gap is surfaced as a separate engine-level finding (cross-span-aware grouping / stronger same-claim model), with its own faithfulness review.

## Status
fixed_untested — wiring present + fires + faithful (proven on real tokens); task "~1" acceptance not met (real 16->9), gap diagnosed and surfaced.
