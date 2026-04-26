# Codex re-review of M-1 v2

## Verdict
STILL-PARTIAL

## Pass-1 findings integration check
- [x] `verification_details.json` claim/span bindings: integrated correctly via `VerifiedReport`, `ReportSection`, `ReportSentence`, `EvidenceSpanToken`, plus `get_sentence_by_claim_id` and `get_evidence_spans_for_claim`.
- [x] completeness parsing bug: integrated correctly. `covered_fraction` is now canonical, with the expected V30 and legacy fallbacks.
- [x] deep immutability: integrated correctly. The previously mutable nested dict surfaces are now read-only, and retrieval attempts are typed frozen objects.
- [x] fail-loud canonical schema behavior: integrated correctly for the pass-1 required cases. Missing `frame_coverage_report`, missing `corpus`, missing contradiction `evidence_id`, and contradiction clusters with `<2` claims now raise `AuditIRSchemaError`.
- [x] frame coverage metadata preservation: integrated correctly. `section`, `slot_id`, `subsection_title`, `min_fields_for_completion`, `human_curated_provenance`, and the retrieval-coverage semantics warning are present.
- [x] contradiction cluster metadata preservation: integrated correctly. `subject`, `severity`, `relative_difference`, and `recommended_action` are preserved.
- [partial] methods/provenance bundle completeness: materially better, but not fully integrated. `evaluator_gate.reasons`, `rule_blockers`, `v30_warnings`, and retrieval counts are now in IR; model/version provenance still is not, despite being present in artifact-side provenance files.
- [x] first-class report claim nodes / back-links: integrated correctly. The IR now has claim-level objects and stable synthetic claim IDs, so the prior “canonical graph claim is ahead of implementation” issue is closed.

## New issues introduced
none

## M-3 readiness
Yes. For View 1 / click-to-inspect, M-3 can now depend on the IR for `claim_id -> sentence` and `claim_id -> evidence span tokens` lookup.

## Final word
STILL-PARTIAL with edits. M-3 is unblocked, schema versioning is acceptable, but M-1 is not yet the full Methods/Provenance IR because model/version provenance remains outside the canonical loader surface.
