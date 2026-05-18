# Claude architect audit — I-rdy-547 (#547)

**Issue:** GH #547 (I-rdy-016-followup) — add an optional GPG detached
signature over the v6 orchestrator-state backup archive (#512 added the
sha256 sidecar).
**Branch:** `bot/I-rdy-547` (re-cut from `I-rdy-016-followup` to the
canonical non-colliding `I-rdy-547`).
**Commit 1:** `38eb6022` — 3 files, +379/-1 (production ~97 LOC, mandatory
acceptance test ~283 LOC).
**Brief:** `.codex/I-rdy-547/brief.md` — Codex APPROVE iter 3 (iter 1 + 2
REQUEST_CHANGES, all findings fixed — see §4).

## 1. What shipped

| File | Change |
|---|---|
| `scripts/v6/backup_orchestrator_state.py` | +93 — `_maybe_sign_archive()` (env-gated detached sign on `backup`), `_verify_archive_signature()` (`restore --verify-sig`), the `--verify-sig` argparse flag, docstring usage update. |
| `requirements-v6.txt` | +4 — `python-gnupg==0.5.6` (the `pytest_v6_backend` CI job installs only this file). |
| `tests/v6/test_backup_gpg_sign.py` | +283 — new; 6 subprocess-driven tests against an ephemeral GPG keyring. |

## 2. Per-finding verification

- **VERIFIED — acceptance criterion 1 (`backup` signs / no-ops)**:
  `_maybe_sign_archive` reads `POLARIS_GPG_KEY_ID`; unset → prints a
  sha256-only notice and returns (no `.asc`); set → signs with `python-gnupg`
  and writes `<archive>.asc`. Tests `test_backup_signs_when_key_set` +
  `test_backup_no_asc_when_key_unset`.
- **VERIFIED — acceptance criterion 2 (`restore --verify-sig` fails loud on
  bad/absent)**: `_verify_archive_signature` — absent `.asc` → `_fail`;
  invalid signature → `_fail`; unexpected key (when `POLARIS_GPG_KEY_ID`
  pins a hex id) → `_fail`. Tests `test_restore_verify_sig_fails_on_absent_signature`
  (RAN, passed), `_on_bad_signature`, `_on_wrong_key`.
- **VERIFIED — `output=` not used**: `sign_file` is called WITHOUT `output=`;
  the armored signature is captured from `signed.data` and written by us —
  the iter-1 P1 empty-`.data` false-reject is structurally avoided.
- **VERIFIED — lazy `import gnupg`**: the import is inside the sign + verify
  helpers only; the sha256-only `backup` path and a plain `restore` never
  import gnupg.
- **VERIFIED — no env leak**: the test `_run` builds the child env
  explicitly and the no-key tests pass `drop_env=_GPG_ENV` so a parent /
  `.env` `POLARIS_GPG_KEY_ID` cannot leak in.
- **VERIFIED — sha256 path regression-free**: `tests/v6/test_backup_restore.py`
  → 6/6 pass; the signing step is purely additive, inserted after the
  sha256 sidecar write and before the `print("backup OK")` lines.
- **VERIFIED — expected-key check robustness**: matches `POLARIS_GPG_KEY_ID`
  (when hex) against BOTH `verified.fingerprint` and `verified.pubkey_fingerprint`
  — a subkey signature still passes; a non-hex selector (email/user-id) is
  not fingerprint-matched (no false-reject) — addresses the iter-3 P2.

## 3. Test / smoke

`ast.parse` clean on the edited script + the new test.
`PYTHONPATH='src;.' pytest tests/v6/test_backup_gpg_sign.py
tests/v6/test_backup_restore.py` → **8 passed, 4 skipped**:
- The 2 no-key tests (`no_asc_when_key_unset`, `verify_sig_fails_on_absent_signature`)
  RAN and passed — exercising the no-op + absent-`.asc` fail-loud paths.
- The 4 key-generating tests **skipped on this Windows dev host** — `gpg
  --gen-key` is unavailable here (the gpg-agent path issue documented in
  `tests/polaris_graph/audit_bundle/test_gpg_signer.py`, whose round-trip
  tests skip identically on the same host). They RUN on a working-gpg host
  (the CI `pytest_v6_backend` Linux runner), where the sign / verify /
  wrong-key paths get real coverage.
- `test_backup_restore.py` 6/6 — the sha256 path is unchanged.

This is within the iter-3-APPROVE'd brief §5 ("…or skip cleanly if the host
gpg/gpg-agent is unavailable, per the test_gpg_signer.py precedent").

## 4. Codex iteration trail

- **iter 1 REQUEST_CHANGES** (1 P1 + 3 P2): `sign_file(output=...)` empty-`.data`
  false-reject; lazy import; no-key-test env leak; sign-before-"backup OK".
  All fixed in the iter-2 brief.
- **iter 2 REQUEST_CHANGES** (1 P1 + 1 P2): `tests/v6/` CI lacks
  `python-gnupg`; verify should check the expected key. Both fixed in the
  iter-3 brief (`requirements-v6.txt` add + the expected-key check).
- **iter 3 APPROVE** (1 non-blocking P2): the expected-key check should also
  consider `pubkey_fingerprint` — folded into the implementation.

## 5. Scope + residuals

- Diff is +379/-1. Production change is ~97 LOC (script +93,
  requirements-v6 +4); the remaining ~283 is the new acceptance test, which
  the issue explicitly requires ("a test exercises the GPG path"). A feature
  and its mandatory test are one coherent unit — splitting them across PRs
  would leave a feature PR with no test. Codex APPROVE'd this exact shape at
  the brief stage.
- `gpg_signer.py` (slice-004) is deliberately NOT reused — the ops script
  stays self-contained; `python-gnupg` directly gives identical semantics
  (Codex iter-2 P2 confirmed this design call).

## 6. Risk assessment

The sha256 integrity path is untouched and regression-verified (6/6). The
GPG path is additive and env-gated — a box without `POLARIS_GPG_KEY_ID`
behaves exactly as before. Signing failure fails loud (no silently-unsigned
backup). The one offline-verification gap — the key-requiring tests skip on
this Windows host — is the documented `test_gpg_signer.py` environment
limitation, not a code defect; the CI Linux job exercises those paths.

## 7. Verdict

Feature complete, faithful to the iter-3 APPROVE'd brief; both acceptance
criteria covered by tests; sha256 path regression-free. Ready for Codex diff
review.
