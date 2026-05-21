# Codex diff review — I-cd-682 metadata.json schema reconciliation

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Canonical-diff-sha256: `4daa377995dd1dcbdb1e9d136635b48da92e32d850600f770d9fa378d9d965b8`. 2 files.

## What this implements (your own scope-consult verdict 2026-05-20)

metadata.json producer now emits the EXACT 5-field v1.0 card matching the frozen v1_canonical fixture + frontend BundleMetadata:
`bundle_created_at_utc, evaluator_model, generator_model, polaris_version, schema_version`.

Changes in `src/polaris_graph/audit_bundle/manifest_builder.py` metadata dict:
- `created_at_utc` → `bundle_created_at_utc`
- `bundle_version` → `schema_version`
- ADD `evaluator_model` (from `report.evaluator_model`; clinical VerifiedReport already carries it at verified_report.py:423)
- REMOVE `decision_id`, `pool_id`, `report_id` (first-class in manifest.yaml per your Q2)
- REMOVE `source_snapshot_count` (derivable from manifest.files)

`tests/polaris_graph/audit_bundle/test_manifest_builder.py`: asserts exact 5-field key set, provenance IDs absent, evaluator_model surfaced verbatim from report.

## Verification

- manifest_builder + bundle_schema suites: 34 pass.
- 2 PRE-EXISTING conformance failures (SHA mismatch on scope_decision.json/sources fixtures) — verified by stashing this diff + re-running on clean polaris HEAD; identical failures. Filed as I-cd-bug-003 (#708). Out of scope for #682.

## Review focus

1. Does dropping the 4 provenance fields from metadata.json break any consumer? (transparency.py, artifact_to_slice_chain.py, inspector loaders read manifest.yaml for provenance, not metadata.json — verify.)
2. Timestamp format: I used `datetime.now(timezone.utc).isoformat()` (gives +00:00) to match the fixture's `+00:00` style; the old code used `.replace("+00:00","Z")`. Any consumer that parses the Z form specifically?
3. evaluator_model from report.evaluator_model — correct per your Q3, or should #682 also touch artifact_to_slice_chain.py? (I scoped real-run population to #675.)
4. Any NOVEL P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
