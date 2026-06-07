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
| `manifest.yaml.asc` | (the signature) | **Real** GPG detached armored signature over `manifest.yaml`, made by the POLARIS bundle key (`POLARIS_GPG_KEY_ID`, `signing@polaris.local`). `gpg --verify` => Good signature. See note below. |
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
7. **Signs `manifest.yaml` -> `manifest.yaml.asc` with the real POLARIS bundle
   key** via `_sign_manifest()` (gpg detached armored sig; key/homedir/passphrase
   from `POLARIS_GPG_KEY_ID` / `POLARIS_GPG_HOMEDIR` / `POLARIS_GPG_PASSPHRASE`,
   the same env contract as `audit_bundle/gpg_signer`). **Fail-loud:** if the key
   is unset or signing/verify fails the script raises — it will NOT write a
   placeholder stub (a stub silently downgrades the real signature; that was the
   I-ready-018 #1139 born-inconsistent-fixture root cause).

The `check_bundle_conformance` step asserts the `.asc` is present + non-empty
(cryptographic `gpg --verify` is operator/reviewer-side), but the fixture ships
a genuine signature so an external `gpg --verify` also succeeds.

> **Line endings:** the whole `tests/fixtures/signed_bundle/` tree is pinned to
> LF via `.gitattributes` (`... -text`). These bytes are SHA256-anchored + signed;
> any CRLF conversion (e.g. Windows `core.autocrlf=true`) flips every hash and
> breaks conformance. Do not "fix" line endings here.

## When to bump

When `bundle_schema.BUNDLE_VERSION` changes from `"1.0"`, author a fresh
`v{N}_canonical/` directory; preserve `v1_canonical/` verbatim as the
historical anchor. Every bump triggers the full cascade documented in
`src/polaris_graph/audit_bundle/bundle_schema.py` module docstring.
