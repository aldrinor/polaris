# Slice 004 — Audit Bundle Export, GPG-Signed
# Architecture Proposal v1

**Slice:** slice_004_audit_bundle_export
**Author:** Claude (architect-reviewer)
**Status:** DRAFT
**Slice spec authority:** polaris-controls/slices/slice_004_*.md (pending user signed-commit)
**Date:** 2026-05-04
**Window per PLAN.md §3:** weeks 12-14 (2026-07-27 to 2026-08-16)

---

## What this slice ships

A user who has produced a verified clinical research report (slice 003)
gets a downloadable, GPG-signed audit bundle containing:

1. The original ScopeDecision (slice 001)
2. The EvidencePool (slice 002)
3. The VerifiedReport (slice 003)
4. Every cited source's full text (snapshotted at retrieval time)
5. A manifest with SHA256 of every content file
6. A GPG signature over the manifest

The bundle is a `.tar.gz` archive that any third party can:
- Verify the GPG signature against the publisher's public key
- Re-hash every content file to confirm it matches the manifest
- Independently re-run strict-verify against the included sources

This is the audit trail that makes POLARIS output legally defensible.
It's the artifact the Carney's office will use to audit the system.

**This slice does NOT ship:**
- BEAT-BOTH benchmark vs ChatGPT/Gemini DR (slice 005)
- Re-verification CLI (post-MVP; bundle format is sufficient for manual audit)
- Multi-key signing / key rotation (post-MVP; single keypair is fine)

---

## Pipeline overview

```
Slice 003 output                Slice 004 (THIS)              User-visible output
┌─────────────────────┐    ┌──────────────────────────┐   ┌──────────────────────┐
│ VerifiedReport      │    │ build_audit_bundle()     │   │ audit_<id>.tar.gz    │
│ verdict: success    │ →  │   collect → snapshot →   │ → │ manifest.yaml        │
│ pool_id, decision_id│    │   manifest → sign        │   │ manifest.yaml.asc    │
└─────────────────────┘    └──────────────────────────┘   │ + content files      │
                                                          └──────────────────────┘
```

---

## Module boundaries

### `polaris_graph.audit_bundle` (NEW package)

#### `bundle_schema.py` — manifest types

```python
class FileEntry(BaseModel):
    path: str               # relative path inside bundle
    sha256: str             # hex digest
    size_bytes: int
    content_type: str       # "scope_decision" | "evidence_pool" |
                            # "verified_report" | "source_snapshot" |
                            # "metadata"

class BundleManifest(BaseModel):
    bundle_id: str          # uuid
    bundle_version: str     # "1.0"
    decision_id: str        # FK chain
    pool_id: str
    report_id: str
    generator_model: str
    files: list[FileEntry]
    bundle_created_at_utc: datetime
    polaris_version: str
```

#### `snapshot_sources.py` — capture every cited source's full text

```python
def snapshot_sources(report: VerifiedReport, pool: EvidencePool) -> dict[str, str]:
    """Return {source_id: full_text_or_snippet}.

    Iterates every provenance_token in every kept VerifiedSentence,
    collects the unique source_ids, pulls full_text (or snippet
    fallback) from the EvidencePool. The bundle includes the snapshot
    so re-verification works offline.
    """
```

#### `manifest_builder.py` — assemble manifest from collected files

```python
def build_manifest(
    decision: ScopeDecision,
    pool: EvidencePool,
    report: VerifiedReport,
    source_texts: dict[str, str],
) -> tuple[BundleManifest, dict[str, bytes]]:
    """Returns (manifest, {filename: content_bytes}).

    Files included:
    - scope_decision.json   — slice 001 output
    - evidence_pool.json    — slice 002 output
    - verified_report.json  — slice 003 output
    - sources/<source_id>.txt — snapshotted full_text
    - metadata.json         — bundle-level metadata
    """
```

#### `gpg_signer.py` — sign the manifest

```python
def sign_manifest(
    manifest_yaml_bytes: bytes,
    gpg_key_id: str,
    gpg_passphrase: str | None = None,
) -> bytes:
    """Detached ASCII-armored signature.

    Uses python-gnupg. Returns the .asc bytes. Raises if no matching
    private key in the GPG keyring.
    """
```

#### `bundle_builder.py` — orchestrator

```python
def build_audit_bundle(
    decision: ScopeDecision,
    pool: EvidencePool,
    report: VerifiedReport,
    gpg_key_id: str,
    output_dir: Path,
) -> Path:
    """End-to-end: collect, snapshot, manifest, sign, tar.gz.

    Returns the path to the .tar.gz file.
    Failure modes:
    - GPG key missing -> RuntimeError
    - Report verdict != 'success' -> ValueError
    """
```

### `polaris_graph.api.audit_bundle_route` (NEW)

```python
@router.post("/audit-bundle")
def post_audit_bundle(req: AuditBundleRequest) -> StreamingResponse:
    """Build + stream the audit bundle as application/gzip."""
```

### `web/app/audit-bundle/` (NEW)

- `page.tsx` — accepts ?report_id=…; shows bundle metadata + download button
- `components/bundle_download.tsx` — clicks fetch the .tar.gz and downloads

---

## Data contracts

| From → To | Contract |
|---|---|
| Slice 003 → Slice 004 | `VerifiedReport { pipeline_verdict='success', sections, decision_id, pool_id }` |
| Slice 004 → User | `audit_<bundle_id>.tar.gz` containing manifest + signature + content |
| Slice 004 abort | `ValueError` (report not success) or `RuntimeError` (GPG unavailable) |

---

## Test strategy

### Unit tests (≥85% coverage)

- `test_bundle_schema.py` — Pydantic validation, JSON round-trip
- `test_snapshot_sources.py` — given report+pool, asserts collected source_ids
- `test_manifest_builder.py` — file-list contents, SHA256 stability
- `test_gpg_signer.py` — uses test keypair fixture; validates signature
- `test_bundle_builder.py` — end-to-end with stubbed GPG; tarball integrity

### HTTP tests

- `test_audit_bundle_route.py` — TestClient; happy + error paths; mocked GPG

### Golden tests (in `.codex/slices/slice_004/golden_drafts/`)

3 scenarios:
1. Successful bundle from canonical aspirin report (verifies tarball + manifest + signature)
2. Bundle from report with mixed dropped/kept sections (snapshot only kept)
3. Reject when verdict=abort_no_verified_sections (ValueError)

### Playwright e2e

- /audit-bundle?report_id=… renders + download click produces .tar.gz

---

## Implementation order (~10 PRs, all ≤200 LOC)

| PR | Scope | LOC est. |
|---|---|---|
| 1 | architecture proposal (this doc) | docs only |
| 2 | `bundle_schema.py` + tests | 130-180 |
| 3 | `snapshot_sources.py` + tests | 100-150 |
| 4 | `manifest_builder.py` + tests | 150-200 |
| 5 | `gpg_signer.py` (with python-gnupg) + tests | 130-180 |
| 6 | `bundle_builder.py` orchestrator + tests | 150-200 |
| 7 | `api/audit_bundle_route.py` + tests | 120-160 |
| 8 | Mount in polaris_v6 app + tests | 60-100 |
| 9 | `web/app/audit-bundle/` + Playwright | 150-200 |
| 10 | Golden fixtures + integration runner | 150-200 |

If any PR exceeds 200 LOC, split.

---

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| python-gnupg requires gpg binary on system | Document install requirement in runbook; CI has gpg; test fixture uses temporary keyring |
| GPG passphrase handling in env | GPG_PASSPHRASE env var; never log; rotate via signed key change |
| Bundle gets too large with full source texts | Cap source_text snapshot at MAX_SOURCE_TEXT_BYTES (default 200KB); truncate with provenance note |
| Re-verification at user side requires running POLARIS code | Bundle includes a small self-contained verify.py + minimal deps; one-shot script |
| Source text changes upstream after bundle | The bundle's snapshot IS the audit truth; manifest SHA256 anchors content |

---

## Definition of "demo-able"

Non-developer:
1. Visits /generation, runs the chain, gets a verified report
2. Clicks "Download audit bundle" on the resulting page
3. Receives `audit_<id>.tar.gz`
4. Extracts → sees manifest.yaml, manifest.yaml.asc, content files
5. Runs `gpg --verify manifest.yaml.asc manifest.yaml` → SUCCESS

If any step breaks, the slice fails. The audit bundle is the gift's
legal scaffolding — Carney's office MUST be able to independently
verify any claim made in any report POLARIS produces.

---

**End of architecture proposal v1.**
