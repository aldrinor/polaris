# I-ready-017 FX-07b leg-2 (#1111) — ROOT-CAUSE DESIGN consult (iter 1 of 5)

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
# ALSO answer these design questions explicitly (free text under each key):
q1_scope: <keep in #1111 leg-2 OR split to a new issue — your ruling>
q2_classification: <your ruling on the two-outcome split>
q3_substantive_kept: <fold in now OR follow-up>
q4_phase1_root: <fix Phase-1 verdict OR keep override-layer correction>
q5_status_name: <name + registration needs for any new curator-gap status>
q6_drafted_signal: <token-independent drafted-count: payload/raw-prose vs slot_drop_log disposition>
```

## This is a DESIGN consult, not a diff review
I already shipped the iter-3-APPROVED override (the "drafted-real-cited-content-then-fully-dropped → generation_failed" honesty flip). Before re-gating the diff, I ran a 4-agent root-cause investigation. It PROVED — on the REAL held drb_72 artifact — that the override is INCOMPLETE: it misses the worst sub-class. I need your ruling on the CLASSIFICATION before I code, because mis-classifying it would itself be a faithfulness regression.

## The bug #1111 exists to kill
`frame_coverage_report` (manifest summary) labels a contract rendering-slot/entity `status="pass"` when ZERO substantive verified prose exists for it in the report body. Clinical-lethal: a coverage report reads "covered" while the body has nothing verified.

## What the committed override does (correct but PARTIAL)
`src/polaris_graph/generator/frame_manifest.py:250-259` (verbatim):
```python
_sv_meta = (strict_verify_by_key or {}).get((slot.slot_id, entity_id))
_is_gen_failed = bool(
    (not is_gap_row)
    and status == ValidationVerdict.PASS.value
    and isinstance(_sv_meta, dict)
    and (_sv_meta.get("sentences_generated_content") or 0) > 0
    and (_sv_meta.get("sentences_kept") or 0) == 0
)
```
`sentences_generated_content` and `sentences_kept` are counted in
`contract_section_runner.py` by matching the span-token regex
`_prov_re = \[#ev:([^:\]]+):(\d+)-(\d+)\]` over kept/dropped sentence text, per entity.

## THE ESCAPE (PROVEN on outputs/audits/I-ready-017/run_artifacts/, 4 independent auditors converged)

### Class A — token-blind not_extractable (the lethal one). Entity `frey_osborne_computerisation`:
- `evidence_pool.json`: `provenance_class=metadata_only`, `direct_quote=""` (empty).
- `manifest.json frame_coverage_report`: **status="pass", is_pipeline_fault=false, failure_reason=null, human_completion_eligible=false.**
- `report.md:38` (the actual body for this slot): *"Contract-bound content for frey_osborne_computerisation did not survive strict verification against retrieved primary source text; this slot is a curator-actionable gap."*
- `verification_details.json`: ZERO occurrences of `ev:frey`; the section's dropped list contains frey's 5 required-field not_extractable sentences, ALL with `tokens:[]` and `failure_reasons:['no_provenance_token']`.
- Mechanism: frey is below the verifiable-span floor (`_MIN_VERIFIABLE_SPAN_CHARS=50`, empty quote) → routed to `_build_not_extractable_payload` → drafts 5 "X: not extractable from available primary content" sentences carrying a BARE `[frey_osborne_computerisation]` marker → `_rewrite_draft_with_spans` (live_deepseek_generator.py:374-379) STRIPS the marker (no span to point into, `_find_best_span_for_sentence` returns None) → the dropped sentences have NO `[#ev:..]` token → my counters see kept=0 AND dropped=0 → `sentences_generated_content=0` → the `>0` gate is FALSE → **override never fires → frey stays "pass".**
- So the override is blind to exactly the highest-risk drop reason (`no_provenance_token`), for the whole metadata_only / empty-or-sub-floor-quote class.

### Class B — placeholder-kept. Entity `eloundou_gpts_are_gpts` (+ similar shape in fourth_industrial_revolution_framing):
- status="pass" with kept=5, but ALL 5 kept sentences are field-level placeholders "X: not extractable from available primary content" (they DO carry a valid `[#ev:..]` token because the direct_quote was non-empty), so `sentences_kept != 0` → override correctly does NOT fire → stays "pass" — yet zero SUBSTANTIVE verified prose exists. The body honestly says "not extractable" (so no manifest-vs-body CONTRADICTION as in Class A), but the manifest still reads "pass".

### Root cause (upstream): `honest_sweep_integration.py:_synthesize_phase1_validation` (~605-650)
Assigns `ValidationVerdict.PASS` to every non-gap row that has ANY retrieval evidence (non-empty `direct_quote` OR `oa_pdf_url`), regardless of whether verified prose was produced. frey was marked PASS purely because `oa_pdf_url` was present despite an empty `direct_quote`. The override is a backstop on top of this over-permissive Phase-1 verdict.

## The classification nuance the audit flagged (do NOT get this wrong)
Auditor 4: do NOT blindly flip frey to `is_pipeline_fault=True`. frey is metadata_only with no usable quote — an EVIDENCE / curator gap (a curator can supply licensed full-text), NOT an engineering pipeline fault. A blind pipeline-fault flip would mis-route a curator-fixable gap to engineers — a DIFFERENT dishonesty. The existing `_is_curator_actionable` + `human_completion_eligible` machinery exists precisely for this distinction.

## My PROPOSED extended design (rule on it)
Make the per-(slot,entity) telemetry TOKEN-INDEPENDENT and add a substantive-prose signal:
- `sentences_drafted` — total sentences the generator produced for the entity (extracted + not_extractable), counted from the per-entity payload / raw prose BEFORE rewrite-strip — NOT from `[#ev:]` tokens. (Closes Class A.)
- `sentences_kept_substantive` — kept sentences EXCLUDING `_GAP_DISCLOSURE_MARKER` ("not extractable from available primary content") placeholders. (Closes Class B.)
- `has_usable_quote` — `len(direct_quote.strip()) >= _MIN_VERIFIABLE_SPAN_CHARS` (the generator COULD have produced verifiable prose).
- keep `provenance_class`.

Override (non-gap, verdict==pass, not FRAME_GAP_UNRECOVERABLE):
- IF `sentences_drafted>0` AND `sentences_kept_substantive==0` → entity reads pass but has zero substantive verified prose → MUST NOT stay pass:
  - IF `has_usable_quote` → `generation_failed` (is_pipeline_fault=True, human_completion_eligible=False) — engineer-owned: real source existed, pipeline produced nothing verified.
  - ELSE → a CURATOR-GAP status (is_pipeline_fault=False, human_completion_eligible=True) — curator can supply licensed full-text.
- Aggregate: decrement original bucket; generation_failed → pipeline_fault_count++; curator-gap → count as gap/partial (not pass, not pipeline_fault).
- Default-None / missing telemetry → non-overriding (byte-identical), preserved.

## Faithfulness
No change to strict_verify / provenance tokens / 4-role / two-family. This only corrects the manifest coverage CLASSIFICATION so it can never read "pass/covered" when zero substantive verified prose exists, while routing engineer-faults vs curator-gaps correctly. Additive + default-None inert.

## Questions (answer each in the schema)
1. SCOPE: keep this in #1111 leg-2, or split Class A/B into a new sibling issue? (My lean: same issue — same honesty goal; committed diff is correct-but-partial.)
2. CLASSIFICATION (the key call): is the two-outcome split correct — usable-quote+drafted+zero-substantive-kept → generation_failed/pipeline_fault; no-usable-quote → curator_gap (human_completion_eligible=True)? Or should the no-usable-quote case ALSO be pipeline_fault? Or both collapse to ONE honest "uncovered" status?
3. SUBSTANTIVE-KEPT (Class B): is excluding `_GAP_DISCLOSURE_MARKER` sentences from "kept" the right substantive discriminator, and fold it in NOW or follow-up?
4. PHASE-1 ROOT: fix `_synthesize_phase1_validation` (PASS-on-retrieval-presence) at the verdict layer (higher blast radius across ALL coverage), or keep the override-layer correction (less invasive backstop)?
5. STATUS NAME: name for the curator-gap status, and confirm registration (graph_route `_normalize_frame_status` mapping, loader free-str tolerance, no run-level PipelineStatus / KNOWN_STATUS_VALUES collision).
6. DRAFTED SIGNAL: token-independent drafted-count from per-entity payload/raw-prose (pre-rewrite) vs the existing `slot_drop_log` disposition (`rendered_as_gap_disclosure`). Note multi-entity slots: disposition is per-slot, so a per-entity drafted count is needed.
