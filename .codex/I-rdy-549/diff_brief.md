# Codex DIFF review — I-rdy-017-followup / GH #549: test the audit-bundle per-file hash-chain

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #549 — `git diff origin/polaris...HEAD` excluding
`.codex/I-rdy-549/` and `outputs/audits/I-rdy-549/` (the canonical diff in
`.codex/I-rdy-549/codex_diff.patch`, sha256 trailer). It implements the
Codex-APPROVE'd brief `.codex/I-rdy-549/brief.md` (brief APPROVE iter 1,
clean). ONE new test file, +222, zero production-code change.

## 2. The diff

New file `tests/polaris_graph/audit_bundle/test_bundle_hash_chain.py`:
- `test_hash_chain_every_manifest_file_matches_extracted` — builds a signed
  bundle (`build_audit_bundle` + `_stub_sign`), extracts the `.tar.gz`,
  re-hashes every extracted `audit_<id>/<path>` file, asserts equality with
  `manifest.files[i].sha256`; asserts the 5 core content files are present.
- `test_hash_chain_size_bytes_matches_extracted` — `size_bytes` equals the
  extracted file's byte length.
- `test_hash_chain_detects_tampered_content_file` — a 1-byte mutation breaks
  the re-hash vs the recorded digest.
- 5 fixture helpers (`_src`/`_pool`/`_decision`/`_report`/`_stub_sign`)
  replicated verbatim from the sibling `test_bundle_builder.py`.

## 3. Verify against the brief

1. Test-only — confirm no `src/` file is in the diff (1 file,
   `tests/polaris_graph/audit_bundle/test_bundle_hash_chain.py`).
2. Both acceptance criteria are covered: (a) every `manifest.files[i].sha256`
   matches the re-hashed extracted file; (b) the tamper case is caught.
3. The bundle is genuinely signed (`sign_fn=_stub_sign` passed) and the
   tarball is genuinely built + extracted — not mocked.
4. `extract_manifest_from_bundle` / `build_audit_bundle` / `FileEntry`
   fields used correctly; the top-level dir is `audit_<bundle_id>/`.
5. No new dependency; `tar.extractall(filter="data")` is the safe filter.

## 4. Files I have ALSO checked and they're clean

- `tests/polaris_graph/audit_bundle/test_bundle_builder.py` — the sibling
  passing test the fixtures are replicated from; NOT modified.
- `src/polaris_graph/audit_bundle/{bundle_builder,manifest_builder,bundle_schema}.py`
  — read for the API surface; NOT modified (test-only issue).
- No `conftest.py` change.

## 5. Test state

`ast.parse` OK. `PYTHONPATH='src;.' pytest test_bundle_hash_chain.py` → 3/3;
together with `test_bundle_builder.py` → 15 passed, no cross-pollution.

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
