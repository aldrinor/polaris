# Codex DIFF-gate — keystone distiller Bug A + Bug B + cache-invalidation (#1217 / #1209)

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## What changed (diff at `.codex/keystone_forensic/diff_gate_input.patch`; live files in repo)
`src/polaris_graph/generator/evidence_distiller.py` (+426/-? ), `tests/polaris_graph/generator/test_evidence_distiller_iperm016.py` (+278), new `scripts/dr_benchmark/probe_source_map.py`. This is the accumulated fix for the live keystone collapse (distill 0 verified vs legacy 6–11 on the drb_76 Safety section). You APPROVED the plan earlier (`.codex/keystone_forensic/plan_review_verdict.txt`). Faithfulness invariant: `strict_verify` / 4-role / D8 are byte-UNCHANGED and remain the SOLE publication authority; every change is MAP-extraction-side or REDUCE-output-shaping-side.

### Change 1 — Bug A: orphaned-citation collapse (deterministic, was 100% drop)
The REDUCE sometimes emits `[[finding]]`/`[ev]` markers in a SEPARATE sentence after the claim's period. `split_into_sentences` then yields a marker-only fragment; the old `filter_and_strip_reduce_markers` kept that fragment and DROPPED the claim prose → bare marker → strict_verify drops → 0 verified.
- New `_is_marker_only_fragment` + a pre-pass in `filter_and_strip_reduce_markers` REATTACH a marker-only fragment to the preceding sentence; a leading orphan with nothing to attach to is dropped.
- `_REDUCE_SYSTEM` + `render_reduce_user` tightened to require the marker INSIDE the sentence, before the terminal period, with an explicit inline example.
- LIVE-CONFIRMED fixed: this run the REDUCE wrote markers inline and the filter kept the full sentence.

### Change 2 — Bug B: paraphrased support_quote rejected at locate (recall collapse)
The MAP paraphrases the support_quote (drops markdown italics `_S. cerevisiae_`; atomizes one source sentence). The probe on the CDC safety source showed **"3 proposed, 0 validated"** — all 3 contraindications rejected at `step1_locate` because the quote was not a verbatim/whitespace substring. These are the exact claims legacy verified.
- New `_fuzzy_locate_span` (+ `_locate_span_with_method`): when exact/whitespace fail, recover the REAL source window by content-word overlap, threshold-gated (`PG_DISTILL_FUZZY_MIN_OVERLAP` default 0.6), shrunk to the tight span between first/last matched content word. Returns a GENUINE source slice, never the model's paraphrase.
- **FAITHFULNESS GATE (the design point I most need you to scrutinize):** content-word overlap is BLIND to meaning-changing function words ("all"→"some", negation flips). So for `locate_method == "fuzzy"` ONLY, the per-finding entailment (already computed in step 6, otherwise non-blocking) is made BLOCKING: a fuzzy-recovered span must ENTAIL the claim or the finding is rejected (`step6_fuzzy_not_entailed`). Exact/whitespace matches stay non-blocking (verbatim text can't drift). The final strict_verify on the REDUCE prose is still the SOLE publication authority for all paths.
- Offline-proven: 3 paraphrased contraindications recover the real span; 2 fabricated claims reject; a "43% of some" (vs source "of all") with NEUTRAL entailment rejects; an entailed paraphrase is kept.

### Change 3 — cache invalidation
`DISTILLER_VERSION` "section_distiller_v2" → "v3". The per-source cache key includes `DISTILLER_VERSION` but I changed validation logic, so v2 entries had to invalidate (the first post-fix run was contaminated by stale v2 cache → ledger=1, zero traces). Bumping the version auto-invalidates; the VM cache was also cleared.

### Change 4 — diagnostics (logging only, faithfulness-inert)
`PG_DISTILL_DEBUG` per-rejection trace in `_validate_finding` (`raw_index`, `step`, `reason`) + KEPT trace with `method`; reattach counter. Stale `_validate_finding` docstring corrected (numbers-in-span + non-exception entailment are non-blocking).

## LIVE RESULT (clean MAXEV=8 A/B, fresh cache, deepseek-v4-pro, on the OVH VM)
- legacy=6 verified (drop_rate 0.60) → distill=2 verified (drop_rate **0.00** — NO collapse, was 0/placeholder).
- Ledger=4, ALL from the CDC safety source, ALL `method=fuzzy`, ALL entailed, ZERO rejects. The fuzzy-locate + entailment-gate recovered exactly the contraindications.
- §-1.1 on the 2 distill sentences: BOTH verbatim-faithful to the source contraindication passages (FOUND in direct_quote), zero fabrication.
- The 2-vs-6 gap is NOT a faithfulness defect: legacy's extra sentences are ~2-3 on-topic safety numerics the MAP under-extracted (OR 14; contamination/AMR) + ~2-3 OFF-topic carcinogenesis-mechanism sentences (fusobacterium FadA, butyrate→cancer) that the distiller correctly excluded as not safety-of-the-intervention.

## QUESTIONS FOR YOU
1. **Fuzzy-locate + entailment-block (P0-critical, clinical):** is making per-finding entailment BLOCKING for fuzzy-recovered spans (and only fuzzy) a sound faithfulness gate against negation/quantifier meaning-drift? Or can a meaning-changed paraphrase still slip (content overlap high, entailment judge lenient)? Should the fuzzy threshold (0.6) be higher, or the shrink logic tighter?
2. Is bumping `DISTILLER_VERSION` the right cache-invalidation mechanism, and is the "empty cached list is a hit" behavior (line ~901, `cache_hit_empty`) safe given step-1 now recovers more?
3. **PERF:** the per-fuzzy-finding entailment LLM call made the MAXEV=8 distill arm ~12 min (deepseek-v4-pro). At MAXEV=40/full Q1 this could be very slow. Do we need a faster judge model or batched entailment BEFORE scaling, or ship and optimize later?
4. **Mergeability ruling:** the collapse (the actual #1217 bug) is fixed and the output is faithful, but distill (2) < legacy (6) on this section because the MAP under-extracts on-topic safety numerics. Is this diff mergeable now with the MAP-extraction-density gap captured as a FOLLOW-UP issue, OR does the density gap block this commit? (The harness exits nonzero on distill<legacy by design.)
5. The diff is ~602/-102 lines (bundles short-marker fix + Bug A + Bug B + cache + traces + tests) — over the 200-LOC norm. Acceptable for a forensic multi-bug keystone fix, or split?
6. Any correctness bug in `_fuzzy_locate_span`, the reattach pre-pass, `_locate_span_with_method`, or the test changes I haven't named?

## OUTPUT SCHEMA
```yaml
verdict: APPROVE | REQUEST_CHANGES
faithfulness_fuzzy_gate_sound: true | false
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
perf_blocks_scaling: true | false
mergeable_now_with_followup: true | false   # answer to Q4
density_gap_is_blocker: true | false
convergence_call: continue | accept_remaining
```
