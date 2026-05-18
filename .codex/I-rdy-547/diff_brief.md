# Codex DIFF review — I-rdy-016-followup / GH #547: GPG-sign orchestrator backup archives

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #547 — `git diff origin/polaris...HEAD` excluding
`.codex/I-rdy-547/` and `outputs/audits/I-rdy-547/` (the canonical diff in
`.codex/I-rdy-547/codex_diff.patch`, sha256 trailer). It implements the
Codex-APPROVE'd brief `.codex/I-rdy-547/brief.md` (brief APPROVE iter 3 —
iter 1+2 REQUEST_CHANGES findings all fixed). 3 files, +379/-1.

## 2. The diff

- `scripts/v6/backup_orchestrator_state.py` (+93): `_maybe_sign_archive()`
  + `_verify_archive_signature()` helpers; `_maybe_sign_archive(archive)`
  call inserted in `cmd_backup` after the `.sha256` sidecar and before
  `print("backup OK")`; `if args.verify_sig: _verify_archive_signature(archive)`
  in `cmd_restore` after the sha256 check; the `--verify-sig` argparse arg;
  docstring usage update.
- `requirements-v6.txt` (+4): `python-gnupg==0.5.6`.
- `tests/v6/test_backup_gpg_sign.py` (+283, new): 6 subprocess-driven tests
  against an ephemeral GPG keyring.

## 3. Verify against the brief — the iter-1/2 P1 fixes especially

1. **`sign_file` has NO `output=`** — confirm the armored sig is captured
   from `signed.data` and written via `asc_path.write_bytes(...)`; success
   is judged by `bool(signed)` + `signed.data`, NOT by an empty-`.data`
   gate (the iter-1 P1).
2. **lazy `import gnupg`** — the import is INSIDE `_maybe_sign_archive` and
   `_verify_archive_signature` only; the module top-level import block is
   unchanged (stdlib-only). The sha256-only `backup` and a plain `restore`
   never import gnupg.
3. **`requirements-v6.txt`** carries `python-gnupg==0.5.6` (iter-2 P1 — the
   `pytest_v6_backend` job installs only this file).
4. **expected-key check** — when `POLARIS_GPG_KEY_ID` is a hex id, the
   restore verify matches it (case-insensitive suffix) against BOTH
   `verified.fingerprint` and `verified.pubkey_fingerprint` (iter-3 P2 —
   subkey signatures still pass); a non-hex selector is not fingerprint-
   matched (no false-reject).
5. **fail-loud** — signing failure and verification failure both go through
   `_fail` (exit non-zero); signing runs before `print("backup OK")`.
6. **sha256 path untouched** — the existing `cmd_backup` / `cmd_restore`
   sha256 logic is unmodified; `test_backup_restore.py` still 6/6.
7. **no env leak** — the test `_run` builds the child env explicitly;
   no-key tests pass `drop_env=_GPG_ENV`.

## 4. Files I have ALSO checked and they're clean

- `tests/v6/test_backup_restore.py` — the `_run` / `_build_db` pattern the
  new test replicates; NOT modified; still 6/6.
- `tests/polaris_graph/audit_bundle/test_gpg_signer.py` — the ephemeral-keyring
  fixture pattern + the documented gpg-agent skip; NOT modified.
- `src/polaris_graph/audit_bundle/gpg_signer.py` — read for the env-var
  names; deliberately NOT imported (the ops script stays self-contained —
  Codex iter-2 P2 confirmed this design call) and NOT modified.
- `.github/workflows/web_ci.yml` — the `pytest_v6_backend` job installs
  `requirements-v6.txt` then runs `pytest tests/v6/`; the new
  `python-gnupg` line makes the test importable there.

## 5. Test state

`ast.parse` 2/2. `PYTHONPATH='src;.' pytest tests/v6/test_backup_gpg_sign.py
tests/v6/test_backup_restore.py` → **8 passed, 4 skipped**. The 2 no-key
tests RAN+passed; the 4 key-generating tests skipped on this Windows dev
host (`gpg --gen-key` gpg-agent limitation — the identical documented skip
of `test_gpg_signer.py`'s round-trip tests on the same host) and run on the
CI `pytest_v6_backend` Linux runner. `test_backup_restore.py` 6/6 — sha256
path regression-free.

## 6. LOC note

The canonical diff is +379/-1. Production code is ~97 LOC (script +93,
requirements-v6 +4) — well under the 200-LOC cap. The remaining ~283 is the
new acceptance test, which #547 explicitly mandates ("a test exercises the
GPG path"). A feature and its required test are one coherent unit;
splitting them would leave a feature PR with no test. The brief (APPROVE
iter 3) described exactly this shape — confirm the LOC is acceptable for a
feature+mandatory-test PR, or flag if you judge otherwise.

## 7. Required output schema (§8.3.9)

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
