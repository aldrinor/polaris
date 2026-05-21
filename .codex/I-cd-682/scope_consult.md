# Codex scope consult — I-cd-682 metadata.json schema reconciliation

Operator directive: route design decisions to Codex on highest-quality-impact grounds.

## The mismatch (verified by grep, not assumed)

Producer `src/polaris_graph/audit_bundle/manifest_builder.py:196-213` emits metadata.json:
`bundle_version, polaris_version, created_at_utc, generator_model, decision_id, pool_id, report_id, source_snapshot_count`

Frozen fixture `tests/fixtures/signed_bundle/v1_canonical/metadata.json` + frontend `web/lib/signed_bundle.ts` BundleMetadata interface:
`bundle_created_at_utc, evaluator_model, generator_model, polaris_version, schema_version`

Field-level deltas:
1. `created_at_utc` (producer) vs `bundle_created_at_utc` (fixture) — NAME mismatch
2. `bundle_version` (producer) vs `schema_version` (fixture) — NAME mismatch (both = "1.0")
3. producer has `decision_id/pool_id/report_id/source_snapshot_count` (provenance IDs) — fixture lacks them
4. fixture has `evaluator_model` — producer LACKS it (`bundle_schema.py:160` only has generator_model; this is the #675 model='unknown' bug too)

Note: `manifest.yaml` separately carries `bundle_version` (frontend signed_bundle.ts:61). So metadata.json using `schema_version` doesn't collide.

Consumers of these fields (grep): web/lib/signed_bundle.ts, web/components/inspector/{metadata_panel,bundle_header,family_segregation_badge}.tsx, src/polaris_v6/api/{artifact_to_slice_chain,transparency}.py, tests/crown_jewels/test_cj_001/004.

## My recommendation: Option A as an additive superset

Update the PRODUCER to emit the 5 frozen-fixture fields (rename created_at_utc→bundle_created_at_utc, bundle_version→schema_version, ADD evaluator_model) AND keep decision_id/pool_id/report_id/source_snapshot_count as ADDITIVE OPTIONAL fields. Extend the frontend BundleMetadata interface with the 4 provenance IDs as optional. Rationale:
- Keeps the frozen v1.0 fixture valid (all 5 required fields present) — no schema re-freeze.
- Additive optional fields are backward-compatible — NO major BUNDLE_VERSION bump needed (the I-cd-012 freeze discipline forbids breaking changes, not additive ones).
- Preserves the producer's richer provenance (decision/pool/report IDs) instead of discarding it.
- evaluator_model threading is shared work with #675 (PHASE 3) — for #682 wire it from the report/run model-pin; #675 hardens the fallback.

## Questions for Codex (highest-quality-impact lens)

1. Is Option A (additive superset) correct, or does adding evaluator_model + 4 provenance IDs to metadata.json constitute a SCHEMA CHANGE that requires a BUNDLE_VERSION major bump under the I-cd-012 freeze discipline? Quote the freeze rule if it forbids additive fields.
2. Should the 4 provenance IDs live in metadata.json at all, or do they belong in manifest.yaml (which already carries provenance)? i.e. is metadata.json meant to be the small human-facing card (5 fields) and the provenance belongs elsewhere?
3. evaluator_model: source it from where? The run's model_pin.json? report object? A new param threaded from the v6 worker? Which is the least-fragile for a real run.
4. Any consumer in the grep list that would BREAK if metadata.json gains fields (strict schema validators with extra="forbid")?

## Output
A recommendation (A/B/C or a variant) with the quality-impact reasoning + answers to Q1-Q4.
