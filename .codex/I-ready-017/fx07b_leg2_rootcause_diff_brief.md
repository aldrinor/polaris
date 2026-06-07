# I-ready-017 FX-07b leg-2 (#1111) — ROOT-CAUSE DIFF gate (iter 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
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

## What this implements (YOUR design-consult ruling, fx07b_leg2_rootcause_design_verdict.txt)
You returned REQUEST_CHANGES on my first design with the corrected three-way classification.
This diff implements your correction EXACTLY. Diff:
`.codex/I-ready-017/fx07b_leg2_codex_diff.patch` (base 49d060f3^..HEAD, 9 files, +295/-10 src).

Your ruling (verbatim intent), now implemented:
- q2: `has_usable_quote && sentences_drafted_substantive>0 && sentences_kept_substantive==0`
  -> generation_failed (is_pipeline_fault=True, human_completion_eligible=False);
  `sentences_drafted>0` but only placeholders, OR no usable quote ->
  curator_gap_no_substantive_content (curator gap, NOT pipeline fault). Owner routing matters.
- q3: fold in substantive-kept now (exclude `_GAP_DISCLOSURE_MARKER`), paired with a
  substantive-DRAFTED signal so placeholder-only rows don't become pipeline faults.
- q4: keep the override-layer correction; Phase-1 verdict tightening deferred (follow-up).
- q5: status `curator_gap_no_substantive_content`; graph_route -> "fail"; loader stays
  string-tolerant; NOT added to PipelineStatus / KNOWN_STATUS_VALUES; ADDED to
  `_is_curator_actionable` + `_compose_task_needs` (SUBSTANTIVE-CONTENT guidance).
- q6: token-INDEPENDENT per-entity payload signal (status=="extracted" count, pre-rewrite),
  NOT the per-slot `rendered_as_gap_disclosure` disposition.
- P2: one shared `_is_gap_disclosure_sentence` predicate; `has_usable_quote` from the same
  `_MIN_VERIFIABLE_SPAN_CHARS` floor as rendering, with quote_len/min_quote_chars emitted.

## The bug this closes (PROVEN on the REAL held drb_72 artifact)
The committed token-counted override (sentences_generated_content>0 AND sentences_kept==0)
was blind to two classes that read coverage "pass" with ZERO substantive verified prose:
- Class A — `frey_osborne_computerisation`: metadata_only, `direct_quote=""`; drafts 5
  not_extractable disclosures whose `[entity]` marker is stripped at rewrite (no span) ->
  dropped sentences have no `[#ev:]` token -> token-counted generated==0 -> override never
  fired -> stayed `pass` while report.md:38 says "did not survive strict verification".
- Class B — `eloundou`: kept=5 but all placeholders -> kept!=0 -> stayed pass.

## Per-file
- contract_section_runner.py: shared `_is_gap_disclosure_sentence`; per-entity
  `_substantive_drafted_by_entity` (extracted payload fields, captured pre-rewrite);
  `_kept_substantive_by_entity` (kept minus placeholders, PRIMARY-token attributed — also
  removes the secondary-token mis-attribution latent risk); slot_strict_verify rows gain
  sentences_drafted_substantive / sentences_kept_substantive / has_usable_quote / quote_len /
  min_quote_chars. Old sentences_kept / sentences_generated_content retained (honest, unused
  by the new override).
- multi_section_generator.py: aggregate the new fields into slot_strict_verify_by_key.
- frame_manifest.py: three-way override (generation_failed vs curator_gap_no_substantive_content
  vs unchanged); honest aggregate (decrement pass bucket; gen_failed -> pipeline_fault_count++ +
  by_status; curator_gap -> frame_gap_count++ + by_status); `_is_curator_actionable` allowlist +
  `_compose_task_needs` branch; human_completion_eligible uses the EFFECTIVE status.
- graph_route.py: curator_gap_no_substantive_content -> "fail".
- honest_sweep_integration.py / run_honest_sweep_r3.py: unchanged in this commit (threading
  already in place from prior leg-2 commits; included in the cumulative diff base).

## §-1.1 on the REAL held manifest (outputs/audits/I-ready-017/fx07b_leg2_rootcause_s11_audit.md)
Entry-by-entry against manifest.json + report.md + verification_details.json: 3 false passes
(frey_osborne, eloundou, fourth_industrial) flip to curator_gap_no_substantive_content
(is_pipeline_fault=False, human_completion_eligible=True); 4 genuine passes (kept_substantive>0:
acemoglu×2, brynjolfsson, autor) unchanged; 0 false flips. (autor's CoT-leak is a SEPARATE
drb_72 bug #1100, out of scope.)

## Offline evidence
- `pytest test_m60_frame_manifest.py test_m63_contract_section_runner.py test_honest_sweep_integration.py`
  -> 74 passed (m60 incl 11 routing tests: pipeline-fault / curator-gap (frey shape) /
  placeholder-kept / human-task guidance / three-entity mixed / fail-closed / inert).
- graph_route normalization test (incl curator_gap -> fail) passes.
- py_compile clean across all 4 touched source files.
- Pre-existing-failure check: `not_applicable_planner_lane` (test_manifest_contract, #1135
  follow-up) and `reasoning_trace` (test_manifest_augment) FAIL identically with my changes
  STASHED — confirmed not introduced here.

## Faithfulness
No change to strict_verify / provenance tokens / 4-role / two-family. Additive + default-None
(byte-identical when telemetry absent). Converts a misreported coverage "pass" with zero
substantive verified prose into the honest owner-routed status; curator gaps go to curators,
pipeline faults to engineers; never reclassifies a genuine pass / extraction gap / retrieval gap.

## LOC note
Cumulative leg-2 diff is +295 src (additive telemetry + override rewrite + two helper
registrations) — above the 200-LOC soft cap. This is an in-campaign follow-up the operator
explicitly directed to fix at the root; splitting the override from its telemetry would be
artificial. Flag if you believe it must be split.

## Questions
1. Does the three-way classification match your design ruling, and is the curator-gap vs
   pipeline-fault owner routing faithfully implemented (no curator gap mis-routed to engineers,
   no pipeline fault mis-routed to curators)?
2. Is the aggregate accounting honest (pass decremented; frame_gap_count for curator_gap;
   pipeline_fault_count for generation_failed; by_status precise; loader recompute consistent)?
3. Any faithfulness / leak / correctness gap before APPROVE?
