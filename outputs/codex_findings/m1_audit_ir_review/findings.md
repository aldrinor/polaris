# Codex review of M-1 Audit Graph IR loader

## Verdict
PARTIAL

## Schema completeness check
View 1 (Report click-to-inspect): No. `AuditIR` has `report_md` + bibliography, but no verified claim objects, no claim IDs, and no `evidence_id:start-end` span tokens. Those only exist in `verification_details.json`, which the loader claims to join but does not load (`src/polaris_graph/audit_ir/loader.py:1-16, 326-360`). M-3 is blocked on this.

View 2 (Contradiction Matrix): Mostly, but not fully. Claim-level fields needed for a basic matrix are present. Cluster-level `severity`, `relative_difference`, `subject`, and `recommended_action` from `contradictions.json` are dropped (`loader.py:217-245`), so prioritization / UX richness is lost.

View 3 (Frame Coverage): Partially. Per-entity status, failure reason, required fields, and retrieval logs are present. But `section`, `slot_id`, `subsection_title`, `min_fields_for_completion`, and `human_curated_provenance` are dropped (`loader.py:249-278`) even though they exist in the manifest. Also, run-14 explicitly warns this is retrieval coverage only, not verified report coverage; that warning is not preserved.

View 4 (Methods + Provenance Bundle): No. `RunManifest` keeps only a thin subset. Missing now: model versions, evaluator reasons / rule blockers, retrieval counts, protocol criteria, and any structured retrieval query payload. Some of that exists in `evaluator_rule_checks.json`, `protocol.json`, and `run_log.txt`; query strings do not appear to be persisted structurally.

View 5 (Source Tier Mix): Yes for basic corpus-level actual fractions only. No for expected-vs-actual, selected-vs-cited, or per-section breakdown. If the view needs Methods parity, it also needs expected tier bands from `protocol.json` and likely `material_deviation`.

## Specific issues
1. `verification_details.json` is the only surviving source of report claim -> evidence span bindings, and it is not loaded. The loader docstring says it is joined, but `load_audit_ir()` only reads four files (`src/polaris_graph/audit_ir/loader.py:1-16, 329-344`). This means the current IR cannot satisfy the View 1 contract.

2. `RunManifest.completeness_percent` is parsed incorrectly. The code looks for `covered_topics` / `total_topics` or `covered` / `total` (`loader.py:300-305`), but run-14 uses `total_covered` / `total_applicable` and `covered_fraction`. The loaded value is `0.0` for a manifest that says `7/7` and `1.0`. This is a real bug, not just a future-proofing concern.

3. The IR is only shallowly immutable. `TierMix.fractions` is a mutable `dict`, and `FrameCoverageEntry.retrieval_attempt_log` is a tuple of mutable `dict`s (`loader.py:80, 102`). A renderer can mutate canonical state through nested objects even though the dataclasses are frozen.

4. The loader silently degrades on schema mismatch in places where the canonical IR should fail loudly. Examples: `frame_coverage_report` missing -> empty coverage object; missing contradiction claim fields -> coerced to empty strings / `0.0`; missing corpus tier fractions -> empty dict (`loader.py:223-285, 349-350`). For foundation IR, silent coercion is the wrong default.

5. Frame coverage slot metadata is discarded. The manifest entries include `section`, `slot_id`, `subsection_title`, `min_fields_for_completion`, and `human_curated_provenance`, but `FrameCoverageEntry` drops them (`loader.py:65-80, 249-264`). That weakens View 3 grouping and back-links into report structure.

6. Contradiction cluster metadata is discarded. `severity`, `relative_difference`, `subject`, and `recommended_action` exist in `contradictions.json` but are not represented in `ContradictionCluster` (`loader.py:55-62, 217-245`). Basic rendering still works, but ranking and disclosure UX are constrained.

7. View 4 provenance is materially incomplete in the current IR surface. `RunManifest` drops `evaluator_gate.reasons`, `rule_blockers`, retrieval counts, `v30_warnings`, and all model/version information (`loader.py:107-125, 289-323`). That is enough for a header card, not a methods/provenance bundle.

8. The top-level canonical-graph claim is ahead of the implementation. `AuditIR` has no first-class report claim nodes at all (`loader.py:128-144`). Until claims have IDs and evidence bindings, derivative renderers cannot reliably “retain back-links to claim IDs.”

## Recommended changes
1. `src/polaris_graph/audit_ir/loader.py:128-144, 326-360`
Add first-class verified report claim structures from `verification_details.json`.
Minimum shape: `VerifiedSection`, `VerifiedSentence` or `ReportClaim`, `EvidenceSpanToken`, plus stable claim IDs and report location data.

2. `src/polaris_graph/audit_ir/loader.py:289-305`
Fix completeness parsing to honor `covered_fraction` and `total_covered` / `total_applicable`. Add a hard assertion in tests for run-14 `completeness_percent == 100.0`.

3. `src/polaris_graph/audit_ir/loader.py:65-80, 98-104, 249-285`
Make nested state actually immutable. Replace mutable dict members with typed frozen dataclasses or immutable mappings. Frozen dataclasses are fine as the core IR once this is fixed; switching the canonical core to Pydantic is not necessary for M-1.

4. `src/polaris_graph/audit_ir/loader.py:217-278, 289-323`
Preserve metadata already present in the artifact:
- contradiction `severity`, `relative_difference`, `subject`, `recommended_action`
- frame coverage `section`, `slot_id`, `subsection_title`, `min_fields_for_completion`, `human_curated_provenance`
- manifest/provenance `v30_warnings`, evaluator reasons/blockers, retrieval stats

5. `src/polaris_graph/audit_ir/loader.py:341-350`
Treat missing required schema blocks as errors, not zero-filled defaults. At minimum fail on missing `frame_coverage_report`, `corpus.tier_fractions`, and required contradiction claim fields.

6. `src/polaris_graph/audit_ir/loader.py`
Add top-level IR versioning now: `ir_schema_version` plus preserved source schema/version fields. V31/V32/V34 evolution will otherwise force implicit branching on ad hoc key presence.

7. `tests/polaris_graph/test_audit_ir_loader.py:44-170`
Add tests for:
- `verification_details.json` loading and claim lookup
- deep immutability of nested structures
- correct completeness parsing
- fail-loud behavior on missing `frame_coverage_report`
- preservation of dropped contradiction / frame metadata
- version-tag presence

## What's ready to build on
M-2 can safely depend on:
- loading `report_md`
- bibliography `[N] <-> evidence_id`
- basic contradiction clusters and per-evidence lookup
- frame coverage counts / rows at a retrieval-coverage level
- corpus tier fractions

That is enough for app mounting, read-only artifact loading, and scaffolding the non-interactive parts of Views 2, 3, and 5.

## Next module dependency check
M-2: safe to proceed, but avoid freezing the public API shape until claim bindings and IR versioning land.

M-3: not safe to build on current M-1. View 1 needs claim/span lookup, and the current IR does not carry it. `verification_details.json` loading plus first-class claim nodes should land before M-3.

View 4 prerequisites do not need to block M-2/M-3, but they should land before the Methods/Provenance view: model/version capture, evaluator reasons, warnings, protocol payload, and a real source for retrieval queries if that UI is expected.
