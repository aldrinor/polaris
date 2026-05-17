# Codex BRIEF review — I-rdy-017-followup / GH #549: test the audit-bundle per-file hash-chain

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0.1 Review stage — PRE-IMPLEMENTATION brief review

This is the **brief** review (the plan). The working tree is intentionally
unmodified; the later diff review verifies the applied test file. Evaluate
§2-§4 as a plan.

## 1. Issue

GH #549 (I-rdy-017-followup) — add an automated test for the audit-bundle
**per-file hash-chain**: `build_manifest_and_files` records a correct sha256
for every content file, and re-hashing an extracted tarball's files
reproduces those digests. `test_gpg_signer.py` already covers the GPG
signature; the per-file hash chain (which the clean-machine reviewer
procedure relies on) is NOT automatically covered. "Depends on: none."

Branch `bot/I-rdy-549` — the raw id `I-rdy-017-followup` would collapse under
the CI ISSUE_ID regex `^bot/(I-[a-z0-9]{2,8}-[0-9]{3})(-…)?$` onto
`I-rdy-017` (#513's merged `.codex/` dir), so it is re-cut to the canonical
non-colliding `I-rdy-549` (GH issue number as NNN). CI ISSUE_ID =
`I-rdy-549`; artifacts under `.codex/I-rdy-549/` + `outputs/audits/I-rdy-549/`.

## 2. The change — ONE new test file, no production code touched

New file: `tests/polaris_graph/audit_bundle/test_bundle_hash_chain.py`.
Pure test addition — **zero production-code change**.

### Verified API surface (grep of `src/polaris_graph/audit_bundle/`)

- `build_audit_bundle(decision, pool, report, output_dir, sign_fn, *,
  extra_files=None) -> Path` — builds manifest, signs, packs
  `audit_<bundle_id>.tar.gz` with top-level dir `audit_<bundle_id>/`
  containing `manifest.yaml`, `manifest.yaml.asc`, and each content file at
  `audit_<id>/<path>`.
- `extract_manifest_from_bundle(bundle_path) -> (BundleManifest,
  manifest_yaml_bytes, manifest_sig_bytes)`.
- `BundleManifest.bundle_id: str`, `.files: list[FileEntry]`.
- `FileEntry.path: str` (relative to the top dir), `.sha256: str`
  (lowercase hex), `.size_bytes: int`, `.content_type`.
- `build_manifest_and_files` records `sha256 = hashlib.sha256(content)
  .hexdigest()` per content file; `manifest.yaml` + `manifest.yaml.asc` are
  NOT in `manifest.files` (they are the manifest + signature themselves).

### Test fixtures

The 5 fixture builders `_src` / `_pool` / `_decision` / `_report` /
`_stub_sign` are replicated verbatim from the sibling
`tests/polaris_graph/audit_bundle/test_bundle_builder.py` (a known-good,
passing test that already uses exactly this pattern). `_stub_sign` is a
hermetic fake `.asc` producer — the bundle is sign_fn-signed (so it is a
"signed bundle" per the issue), and the hash-chain assertions are
independent of GPG signature validity, so no real `gpg` binary is needed.
Replicating the fixtures (rather than importing from `test_bundle_builder`)
keeps the new test self-contained — test modules importing each other is
fragile.

### The 3 tests

1. `test_hash_chain_every_manifest_file_matches_extracted` — build a signed
   bundle via `build_audit_bundle`, extract the `.tar.gz` to a tmp dir, and
   for EVERY `manifest.files[i]`: re-hash the extracted
   `audit_<bundle_id>/<path>` file with `hashlib.sha256(...).hexdigest()`
   and assert it equals `manifest.files[i].sha256`. Also assert
   `manifest.files` is non-empty (the core content files —
   scope_decision.json / evidence_pool.json / verified_report.json /
   metadata.json / REVIEWER_README.md — are present).
2. `test_hash_chain_size_bytes_matches_extracted` — for each entry, assert
   `manifest.files[i].size_bytes` equals the extracted file's byte length
   (the chain records size too; cheap, strengthens the integrity claim).
3. `test_hash_chain_detects_tampered_content_file` — build + extract, mutate
   one content file's bytes on disk (append a byte), re-hash, and assert the
   re-hash NO LONGER equals the recorded `manifest.files[i].sha256` — i.e.
   the hash compare catches the tamper (the acceptance "tamper case").

## 3. Scope boundary

- Test-only. No `src/` change. No new dependency (`hashlib`, `tarfile`,
  `pathlib` are stdlib; `pytest` + the audit_bundle modules already imported
  by sibling tests).
- The GPG-signature verification path is explicitly NOT re-tested here —
  `test_gpg_signer.py` owns that. #549 is strictly the per-file sha256
  chain.

## 4. Files I have ALSO checked and they're clean

- `tests/polaris_graph/audit_bundle/test_bundle_builder.py` — already
  exercises `build_audit_bundle` + tarball extraction with the same
  fixtures; the new file does not modify it.
- `manifest_builder.py` / `bundle_builder.py` / `bundle_schema.py` — read
  for the API surface above; unchanged by this issue.
- No `conftest.py` change needed — the audit_bundle tests run under the
  existing `tests/polaris_graph/audit_bundle/` package.

## 5. Test / smoke (planned)

`python -m ast` parse the new file; `PYTHONPATH='src;.' python -m pytest
tests/polaris_graph/audit_bundle/test_bundle_hash_chain.py -q` → all new
tests pass; plus a run of the existing
`tests/polaris_graph/audit_bundle/test_bundle_builder.py` to confirm no
cross-pollution. Any pre-existing failure elsewhere verified identical on
clean `polaris` HEAD before commit.

## 6. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — emit the schema.
