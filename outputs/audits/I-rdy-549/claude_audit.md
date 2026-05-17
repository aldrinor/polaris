# Claude architect audit — I-rdy-549 (#549)

**Issue:** GH #549 (I-rdy-017-followup) — add an automated test for the
audit-bundle per-file hash-chain (carved from #513).
**Branch:** `bot/I-rdy-549` (re-cut from the colliding `I-rdy-017-followup`
to the canonical non-colliding `I-rdy-549`).
**Commit 1:** `f6a03ddf` — 1 new test file, +222, zero production-code change.
**Brief:** `.codex/I-rdy-549/brief.md` — Codex APPROVE iter 1 (clean — 0
P0/P1/P2).

## 1. What shipped

New file `tests/polaris_graph/audit_bundle/test_bundle_hash_chain.py` —
test-only. Three tests covering the per-file sha256 hash-chain that the
clean-machine reviewer verification procedure relies on (the GPG signature
is already covered by `test_gpg_signer.py`; the hash-chain was not):

| Test | Asserts |
|---|---|
| `test_hash_chain_every_manifest_file_matches_extracted` | builds a signed bundle, extracts the `.tar.gz`, re-hashes every extracted `audit_<id>/<path>` file and asserts it equals `manifest.files[i].sha256`; also asserts the 5 core content files are on-chain. |
| `test_hash_chain_size_bytes_matches_extracted` | `manifest.files[i].size_bytes` equals the extracted file's byte length. |
| `test_hash_chain_detects_tampered_content_file` | a 1-byte mutation of an extracted content file makes the re-hash NO LONGER match the recorded digest — the acceptance "tamper case". |

## 2. Per-finding verification

- **VERIFIED — acceptance criteria met**: criterion 1 ("a test builds a
  signed bundle, extracts the tarball, asserts every
  `manifest.files[i].sha256` matches the re-hashed extracted file") →
  `test_hash_chain_every_manifest_file_matches_extracted`. Criterion 2 ("a
  tamper case: mutating one content file is caught by the hash compare") →
  `test_hash_chain_detects_tampered_content_file`. The `size_bytes` test is
  a cheap strengthening extra.
- **VERIFIED — test-only, no production change**: `git diff --cached --stat`
  → 1 file, `tests/polaris_graph/audit_bundle/test_bundle_hash_chain.py`,
  +222, new. No `src/` file touched.
- **VERIFIED — API surface used correctly**: `build_audit_bundle(...)` →
  `.tar.gz`; `extract_manifest_from_bundle(...)` → `(BundleManifest, yaml,
  sig)`; `BundleManifest.bundle_id` + `.files`; `FileEntry.path` / `.sha256`
  / `.size_bytes`. Tarball top dir `audit_<bundle_id>/`. All read from
  `src/polaris_graph/audit_bundle/{bundle_builder,manifest_builder,bundle_schema}.py`.
- **VERIFIED — hermetic**: `_stub_sign` is a fake-`.asc` producer; no real
  `gpg` binary needed (the hash-chain assertions are independent of GPG
  signature validity — the bundle is still a sign_fn-signed bundle). The 5
  fixture helpers are replicated verbatim from the sibling passing test
  `test_bundle_builder.py` — the module is self-contained (no inter-test-module
  import).
- **VERIFIED — forward-compatible**: `tar.extractall(..., filter="data")` —
  the safe extraction filter (Python 3.12+), which also silences the 3.14
  default-filter `DeprecationWarning`.

## 3. Test / smoke

`ast.parse` OK. `PYTHONPATH='src;.' pytest test_bundle_hash_chain.py` → 3/3
pass; run together with the sibling `test_bundle_builder.py` → **15 passed**
(no cross-pollution). No production behaviour exercised beyond the public
`build_audit_bundle` / `extract_manifest_from_bundle` API.

## 4. Scope + residuals

- Commit-1 diff is +222, one new test file — well under the 200-LOC *code*
  cap concern (it is test code, not production logic; a single focused test
  module).
- No new dependency (`hashlib`/`tarfile`/`pathlib` stdlib; `pytest` +
  audit_bundle modules already used by sibling tests).
- The GPG-signature path is intentionally NOT re-tested — `test_gpg_signer.py`
  owns it; #549 is strictly the per-file sha256 chain.

## 5. Risk assessment

Pure test addition — no production code changed, so no behaviour/regression
risk. The new tests genuinely exercise the integrity property (a real
tarball is built, extracted, re-hashed) rather than a mock. The tamper test
proves the chain is load-bearing.

## 6. Verdict

Test complete, faithful to the iter-1 APPROVE'd brief; both acceptance
criteria met + a `size_bytes` extra; 15/15 audit_bundle tests green. Ready
for Codex diff review.
