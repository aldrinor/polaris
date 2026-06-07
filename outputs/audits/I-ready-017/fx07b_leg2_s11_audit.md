# §-1.1 audit — FX-07b leg-2 (#1111): strict_verify → frame_coverage pipeline-fault honesty

**Standard:** §-1.1 on the REAL held drb_72 generation manifest
(`outputs/audits/I-ready-017/run_artifacts/manifest.json`, status=abort_four_role_release_held)
+ its report.md. The fix is flag-free/additive (default-None param → no override), so the override
behaviour is verified by 7 focused unit tests on the real CompiledFrame/outline/validation shapes; this
§-1.1 confirms the fix targets the EXACT real misreport.

## The bug, on the real artifact (claim-by-claim)

CLAIM: a contract slot whose generated prose all failed strict_verify is mis-reported as `pass`.

EVIDENCE (held drb_72 manifest `frame_coverage_report`):
- `pass_count = 7`, `partial_count = 0`, `frame_gap_count = 0`, `pipeline_fault_count = 0`.
- Entry `frey_osborne_computerisation` (slot `empirical_exposure`): **status = "pass",
  is_pipeline_fault = False.**

EVIDENCE (same run's report.md, the Frey & Osborne subsection, verbatim):
> "### Occupational computerisation susceptibility (Frey & Osborne, TFSC 2017)
> Contract-bound content for frey_osborne_computerisation **did not survive strict verification** against
> retrieved primary source text; this slot is a curator-actionable gap. ..."

VERDICT: **UNSUPPORTED → the frame_coverage `pass` for frey_osborne_computerisation is a
misrepresentation.** The body shows the entity has NO verified prose (strict_verify kept 0 sentences),
yet frame_coverage reports it `pass`, `is_pipeline_fault=False` — exactly the honesty gap #1111 fixes.
In a clinical context this is the §-1.1-lethal class: a coverage report that reads "covered" while the
report carries zero verified sentences for the entity.

## The fix corrects exactly this case (verified)

With the new per-(slot,entity) strict_verify telemetry threaded into compose_frame_coverage, an entity
with: verdict==pass AND sentences_generated_content>0 (the generator DID draft content for it) AND
sentences_kept==0 (all dropped by strict_verify) AND provenance_class != FRAME_GAP_UNRECOVERABLE
→ flips to **status="generation_failed", is_pipeline_fault=True, human_completion_eligible=False**, and
pipeline_fault_count is incremented while pass_count + by_status are decremented (honest aggregate).
frey_osborne_computerisation is a real ABSTRACT_ONLY/OA contract entity (not FRAME_GAP_UNRECOVERABLE),
its body shows drafted-then-dropped content, and its M-59 verdict was pass → it flips. The other 6
entries (real verified prose, kept>0) stay pass.

## Fail-closed boundaries (verified by unit tests on real shapes)
- non-gap `fail_min_fields`/`not_extractable` with kept==0 (verdict != pass) → STAYS partial
  (extraction gap, curator-actionable) — NOT reclassified.
- FRAME_GAP_UNRECOVERABLE with kept==0 → STAYS gap.
- pass with kept>0 → unaffected.
- missing/None strict_verify metric → non-overriding.
- mixed section: only the zero-kept slot flips; the kept slot stays pass.

## Offline evidence
`pytest tests/polaris_graph/test_m60_frame_manifest.py` → 33 passed (26 existing + 7 new override
cases: pass→generation_failed, fail_min_fields stays partial, gap stays gap, pass-with-kept unaffected,
None non-overriding, mixed-section, aggregate counts). `test_m63_contract_section_runner.py` +
`test_honest_sweep_integration.py` green (64 combined). py_compile clean across all 5 touched files.

## Faithfulness
Honesty/observability tightening; additive + default-None (byte-identical when the telemetry is absent
or no zero-kept entity exists). No change to strict_verify itself / provenance tokens / 4-role /
two-family. Converts a misreported pass into a pipeline fault ONLY for a validated, generated-then-fully-
dropped non-gap entity; never reclassifies an extraction or retrieval gap.
