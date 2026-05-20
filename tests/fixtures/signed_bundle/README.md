# `tests/fixtures/signed_bundle/` — canonical signed-bundle fixtures

Fixtures used by:
- `tests/polaris_graph/audit_bundle/test_conformance.py` (I-cd-012 conformance check)
- I-B-08 (#630) real-run bundle emitter conformance tests
- Future Inspector route (I-A-03, #609) offline-fallback rendering tests

## `v1_canonical/`

Schema version **v1.0** per `src/polaris_graph/audit_bundle/bundle_schema.py:BUNDLE_VERSION`.

| File | Content type | Purpose |
|---|---|---|
| `manifest.yaml` | (the manifest itself) | Top-level `BundleManifest` referencing every other file with SHA256 anchors |
| `manifest.yaml.asc` | (the signature) | GPG armored signature **placeholder** — presence-only test fixture, not a real key signature. See note below. |
| `scope_decision.json` | `scope_decision` | One `ScopeDecision` (slice 001 output) |
| `evidence_pool.json` | `evidence_pool` | One `EvidencePool` (slice 002 output) with one Source |
| `verified_report.json` | `verified_report` | One `VerifiedReport` (slice 003 output) — minimal sections |
| `metadata.json` | `metadata` | Bundle-level metadata (polaris_version, generator_model, evaluator_model, timestamps) |
| `reasoning_trace.jsonl` | `reasoning_trace` | I-gen-004 raw model reasoning channel; JSONL, one record per generator LLM call |
| `sources/<sha-id>.txt` | `source_snapshot` | One source full-text snapshot |

## How to regenerate (deterministic)

The fixture content + SHA256s are produced by:

```
python scripts/regen_signed_bundle_canonical_fixture.py
```

The script:
1. Constructs `ScopeDecision`, `EvidencePool`, `VerifiedReport` Pydantic objects with deterministic seed values (no clocks, no uuid4 — the IDs are hard-coded).
2. Serializes each to JSON using `model_dump(mode="json")` + `json.dumps(..., sort_keys=True, indent=2)`.
3. Writes each content file.
4. Computes SHA256 + size of each file.
5. Constructs `BundleManifest` referencing the files.
6. Writes `manifest.yaml` using `yaml.safe_dump(..., sort_keys=True)`.

The placeholder `manifest.yaml.asc` is a fixed GPG-armored stub authored
once and reused. Real signatures require an operator key; conformance
checks presence + non-empty only (cryptographic verification belongs to
operator/reviewer-side tooling, NOT the I-B-08 emitter's pre-sign
conformance check).

## When to bump

When `bundle_schema.BUNDLE_VERSION` changes from `"1.0"`, author a fresh
`v{N}_canonical/` directory; preserve `v1_canonical/` verbatim as the
historical anchor. Every bump triggers the full cascade documented in
`src/polaris_graph/audit_bundle/bundle_schema.py` module docstring.
