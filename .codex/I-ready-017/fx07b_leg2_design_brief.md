# I-ready-017 FX-07b leg-2 (#1111) — strict_verify→frame_coverage data-path DESIGN consult (iter 3 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Your iter-2 finding — addressed (you endorsed the seam; this tightens the override gate)

**P1-1 (override too broad — gate on M-59 pass + generated-content + kept==0) — FIXED.** The
`generation_failed`/pipeline-fault override now fires ONLY when ALL three hold for the entity:
1. the existing coverage verdict for that (slot_id,entity_id) is **pass** (M-59 validated a real payload —
   so this is NOT a fail_min_fields / not_extractable / fail_missing_payload extraction gap), AND
2. `sentences_generated_content > 0` (the generator actually produced content sentences — NOT a gap-
   template/no-language row), AND
3. `sentences_kept == 0` (every generated content sentence failed strict_verify).
That triple = a true PIPELINE FAULT (valid payload + real generated prose, but nothing survived
verification). A non-gap ABSTRACT_ONLY/METADATA_ONLY row that yielded fail_min_fields/not_extractable
with kept==0 has verdict != pass → NOT overridden → stays curator-actionable partial/extraction
coverage. A FRAME_GAP_UNRECOVERABLE row also has verdict != pass → stays a retrieval gap.

**Data needed (from the endorsed seam):** the contract runner returns, per (slot_id,entity_id):
`sentences_generated_content` (count of non-gap content sentences emitted pre-strict_verify) +
`sentences_kept` + `provenance_class`. Aggregated on MultiSectionResult → threaded (default-None) into
run_v30_post_generation → compose_frame_coverage, which applies the triple-gated override.

**P2s (iter-2) — ADOPTED:**
- Seam: contract runner → MultiSectionResult → run_v30_post_generation → compose_frame_coverage; M-59
  stays payload-validation only; strict_verify applied as a later manifest override. (as you endorsed)
- New status value `generation_failed` with `is_pipeline_fault=True`, `human_completion_eligible=False`,
  and inspector/audit status-classification mapped to pipeline-fault (added across the enum/surfaces, not
  overloading fail_min_fields/fail_missing_payload). Registered in the manifest status taxonomy
  (UNIFIED/KNOWN status values + v6 PipelineStatus if it surfaces there) like the I-ready-017 journal_only
  statuses were.
- Override applied BEFORE aggregate counting: decrement the original pass bucket + by_status, then
  pipeline_fault_count += 1, so counts stay honest.

**Tests (planned):** (a) pass + generated>0 + kept==0 → generation_failed/pipeline_fault;
(b) non-gap fail_min_fields/not_extractable + kept==0 → stays partial/curator-actionable (override does
NOT fire); (c) FRAME_GAP_UNRECOVERABLE + kept==0 → stays gap; (d) mixed section one slot zero-kept;
(e) aggregate counts + by_status corrected; (f) pipeline-fault excluded from human completion.

## Faithfulness
Honesty/observability tightening; additive + default-None (byte-identical when unset). No change to
strict_verify / provenance / 4-role / two-family. Converts a misreported pass→pipeline-fault ONLY for a
validated entity whose generated prose all failed strict_verify; never reclassifies an extraction gap.

## Questions
1. Is the triple gate (verdict==pass AND sentences_generated_content>0 AND sentences_kept==0) correct +
   complete to isolate true pipeline faults from extraction/retrieval gaps?
2. Is `sentences_generated_content` (non-gap content sentences pre-strict_verify, per (slot,entity))
   the right denominator, and obtainable from the contract runner's existing slot_drop_log / kept+dropped
   accounting?
3. Ready to build, or any remaining gap?
