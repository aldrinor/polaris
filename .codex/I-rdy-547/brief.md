# Codex BRIEF review — I-rdy-016-followup / GH #547: GPG-sign orchestrator backup archives

HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0.1 Review stage — PRE-IMPLEMENTATION brief review

This is the **brief** review (the plan). The working tree is intentionally
unmodified; the later diff review verifies the applied feature. Evaluate
§2-§4 as a plan — especially the §3 design decision (gnupg-direct vs reusing
the audit-bundle `gpg_signer` module).

## 0.2 iter-1 → iter-2 changelog (REQUEST_CHANGES addressed)

Codex iter-1 returned REQUEST_CHANGES — 1 P1 + 3 P2, all real, all fixed in
this revision:
- **P1 — `sign_file(..., output=...)` empty-`.data` false-reject.** Correct.
  The §2a plan no longer passes `output=` to `sign_file`. It captures the
  armored signature from the result's `.data` (stdout) and writes the
  `.asc` itself — the exact proven pattern of `gpg_signer.py`'s `.sign()`.
  Success is judged by `bool(signed)` (python-gnupg `Sign.__bool__` →
  truthy iff the signature was created) — NOT by `.data` emptiness as a
  primary gate.
- **P2 (lazy import).** `import gnupg` is now lazy — done *inside* the sign
  and verify helpers only, so the sha256-only `backup` path and a plain
  `restore` never import gnupg.
- **P2 (env leak in the no-key test).** The new test's `_run` builds the
  child env explicitly and the no-key test does `env.pop("POLARIS_GPG_KEY_ID",
  None)` so a parent-env / `.env` value cannot leak in.
- **P2 (sign before "backup OK").** The sign step runs *before* the
  `print("backup OK …")` lines, so a signing failure (`_fail`, exit
  non-zero) prevents a misleading success message. With no `output=`, gpg
  never writes a partial `.asc` — the `.asc` is written by us only on
  success — so there is no partial file to clean up.

iter-2 → iter-3 changelog (REQUEST_CHANGES — 1 P1 + 1 P2, both fixed):
- **P1 — `tests/v6/` CI lacks `python-gnupg`.** Correct: the
  `pytest_v6_backend` CI job (`.github/workflows/web_ci.yml`) installs only
  `requirements-v6.txt` then runs `pytest tests/v6/`, and `requirements-v6.txt`
  has no `python-gnupg` — the new `tests/v6/test_backup_gpg_sign.py` (and the
  script's lazy `import gnupg`) would `ImportError` at collection. New §2d:
  add `python-gnupg==0.5.6` to `requirements-v6.txt` (the v6 backup tooling's
  GPG path is a genuine v6 runtime dep; `0.5.6` matches the installed/verified
  version and `requirements.txt:71`'s `python-gnupg>=0.5.0`).
- **P2 — verify accepts any keyring key.** `gpg --verify` passing only means
  "signed by some key in the active keyring." §2b now adds: when
  `POLARIS_GPG_KEY_ID` is set during `restore --verify-sig`, also assert
  `verified.fingerprint` matches it (case-insensitive `endswith`, since the
  env var may be a short id or full fingerprint) — fail loud on mismatch.
  When unset, any valid signature from the operator's imported public keys
  is accepted (the keyring is the trust boundary). §2c adds a wrong-key
  test (test 6).

## 1. Issue

GH #547 (I-rdy-016-followup) — `scripts/v6/backup_orchestrator_state.py`
(#512, merged) backs up v6 orchestrator state to a `.tar.gz` with a
**sha256** integrity sidecar. This follow-up adds an **optional GPG detached
signature** over the archive, gated on `POLARIS_GPG_KEY_ID`, plus a `restore
--verify-sig` flag. Branch `bot/I-rdy-547` — the raw id
`I-rdy-016-followup` collapses under the CI ISSUE_ID regex onto `I-rdy-016`
(#512's `.codex/` dir), so re-cut to the canonical non-colliding
`I-rdy-547`. CI ISSUE_ID = `I-rdy-547`. "Depends on: #512 merged" — verified
merged (`scripts/v6/backup_orchestrator_state.py` is on `polaris`).

### Acceptance (from the issue)
- `backup` produces `<archive>.asc` when `POLARIS_GPG_KEY_ID` is set; no-ops
  gracefully (sha256-only) when unset.
- `restore --verify-sig` fails loud on a bad/absent signature.
- A test exercises the GPG path against an ephemeral test keyring.
- Codex APPROVE.

## 2. The change — `scripts/v6/backup_orchestrator_state.py` + a new test

### 2a. backup — env-gated detached signature

Insert a `_maybe_sign_archive(archive)` step in `cmd_backup` AFTER the
`.sha256` sidecar write and BEFORE the `print("backup OK …")` lines (so a
signing failure prevents a misleading success message):
- `key_id = os.environ.get("POLARIS_GPG_KEY_ID", "").strip() or None`.
- If `key_id is None`: print `gpg: POLARIS_GPG_KEY_ID unset — sha256-only,
  no .asc signature` and return (graceful no-op — acceptance criterion 1).
- Else: lazy `import gnupg` (inside the helper); `gpg =
  gnupg.GPG(gnupghome=os.environ.get("GNUPGHOME") or None)`; `passphrase =
  os.environ.get("POLARIS_GPG_PASSPHRASE") or None`. Sign WITHOUT `output=`
  — `with open(archive, "rb") as fh: signed = gpg.sign_file(fh,
  keyid=key_id, detach=True, passphrase=passphrase)`. **`output=` is
  deliberately NOT used** (per iter-1 P1: with `output=`, a *successful*
  detached signature writes to the file and leaves `signed.data` empty —
  an empty-`.data` check would false-reject good signatures). Instead:
  - If `not signed` (python-gnupg `Sign.__bool__` is falsy → signing
    failed) OR `not signed.data` → `_fail("gpg signing failed: <signed.status>
    / <signed.stderr>")` (fail loud, CLAUDE.md LAW II). Because `output=`
    was not passed, gpg writes no file on failure — there is no partial
    `.asc` to clean up.
  - Else write the armored detached signature ourselves:
    `(archive.parent / f"{archive.name}.asc").write_bytes(signed.data
    if isinstance(signed.data, bytes) else str(signed).encode("utf-8"))`.
    (`signed.data` is the ASCII-armored detached sig — the same value
    `gpg_signer.py`'s `.sign()` returns.) Print `gpg: signed ->
    <archive>.asc`.

### 2b. restore — `--verify-sig` flag

Add `restore.add_argument("--verify-sig", action="store_true", ...)`. In
`cmd_restore`, when `args.verify_sig` (placed right after the existing
sha256 check, before extraction):
- `asc = archive.parent / f"{archive.name}.asc"`; if not `asc.is_file()` →
  `_fail("--verify-sig given but no signature <asc> — refusing restore")`
  (absent-signature fail-loud — acceptance criterion 2).
- lazy `import gnupg`; `gpg = gnupg.GPG(gnupghome=os.environ.get("GNUPGHOME")
  or None)`; `with open(asc, "rb") as sf: verified = gpg.verify_file(sf,
  str(archive))`.
- If not `verified` / not `verified.valid` → `_fail("GPG signature
  verification FAILED for <archive> — status=<verified.status>")`
  (bad-signature fail-loud).
- **Expected-key check (iter-2 P2):** `key_id =
  os.environ.get("POLARIS_GPG_KEY_ID", "").strip()`. If `key_id` is set and
  `not (verified.fingerprint or "").upper().endswith(key_id.upper())` →
  `_fail("GPG signature is valid but from an unexpected key: got
  <verified.fingerprint>, expected POLARIS_GPG_KEY_ID=<key_id>")`. When
  `key_id` is unset, any valid signature from a public key in the active
  keyring is accepted (the operator-controlled keyring is the trust set).
- Else print `gpg: signature verified (fingerprint <verified.fingerprint>)`.

### 2d. requirements-v6.txt — add `python-gnupg`

Add `python-gnupg==0.5.6` to `requirements-v6.txt` (the `pytest_v6_backend`
CI job installs only that file before `pytest tests/v6/`; the new test +
the script's GPG path both need it). Placed with a one-line comment
explaining it is the v6 backup-tooling GPG dependency. Exact pin matches the
v6 file's `==` style and the installed/verified `0.5.6`
(`requirements.txt:71` carries the loose `python-gnupg>=0.5.0`).

### 2c. New test `tests/v6/test_backup_gpg_sign.py`

Subprocess-drives the script exactly like the sibling
`tests/v6/test_backup_restore.py` (`_run(*args)` →
`subprocess.run([sys.executable, SCRIPT, ...], env=…)`), reusing its
`_build_db` DB-fixture pattern. Adds an **ephemeral GPG keyring** fixture
replicated from `tests/polaris_graph/audit_bundle/test_gpg_signer.py`
(`gnupg.GPG(gnupghome=tmp).gen_key(gen_key_input(...))`; `pytest.skip` if
`key.fingerprint` is empty — gpg-agent env issue) and a module-level
`pytest.mark.skipif(not _gpg_callable())`. Tests:
1. `test_backup_signs_when_key_set` — `backup` with env
   `POLARIS_GPG_KEY_ID=<fp>` + `GNUPGHOME=<keyring>` + `POLARIS_GPG_PASSPHRASE`
   → `<archive>.asc` exists.
2. `test_backup_no_asc_when_key_unset` — `backup` with `POLARIS_GPG_KEY_ID`
   unset → no `.asc`, sha256 sidecar still present, exit 0.
3. `test_restore_verify_sig_passes_on_good_signature` — signed `backup` then
   `restore --verify-sig` → exit 0.
4. `test_restore_verify_sig_fails_on_absent_signature` — unsigned `backup`
   then `restore --verify-sig` → non-zero exit, stderr names the missing
   `.asc`.
5. `test_restore_verify_sig_fails_on_bad_signature` — signed `backup`, then
   corrupt the `.asc` bytes, `restore --verify-sig` → non-zero exit.
6. `test_restore_verify_sig_fails_on_wrong_key` — generate a SECOND
   ephemeral key in the same keyring; `backup` signed with key A
   (`POLARIS_GPG_KEY_ID=<fpA>`); `restore --verify-sig` with
   `POLARIS_GPG_KEY_ID=<fpB>` → non-zero exit (signature valid but
   unexpected key — exercises the §2b expected-key check).

## 3. Design decision — for Codex adjudication

**Use `python-gnupg` directly in the script** (not `from
polaris_graph.audit_bundle.gpg_signer import build_gpg_signer`). Rationale:
`backup_orchestrator_state.py` is a deliberately self-contained operational
tool (its own docstring stresses "no built-in network push — that would
couple POLARIS to operator infrastructure the build team can't test"); it
currently imports only stdlib. Importing the slice-004 `gpg_signer`
production module would couple this ops script to the clinical-pipeline
package and need a `sys.path` bump. `python-gnupg` (`import gnupg`) is the
same library `gpg_signer.py` itself wraps and is already a declared
dependency — using it directly gives the identical detached-armored-sig
semantics and reuses the SAME `POLARIS_GPG_KEY_ID` demo key the issue asks
for, without the cross-package coupling. **Codex: confirm gnupg-direct is
the right call**, or if you judge `gpg_signer` reuse is preferable (for its
hardened `.sign()` error-surfacing), say so and it will be folded in with
the `sys.path` bump.

Also for adjudication: `gpg_signer.py` has no `verify` function, so the
restore-side verify is implemented inline with `gnupg.verify_file` either
way — no production-module change.

## 4. Files I have ALSO checked and they're clean

- `scripts/v6/backup_orchestrator_state.py` — read in full; the change is
  additive (a sign step in `cmd_backup`, a flag + verify block in
  `cmd_restore`, one new argparse arg); the sha256 path is untouched.
- `tests/v6/test_backup_restore.py` — the subprocess-drive `_run` + `_build_db`
  pattern the new test replicates; NOT modified.
- `tests/polaris_graph/audit_bundle/test_gpg_signer.py` — the ephemeral
  `gnupg` keyring fixture pattern; NOT modified.
- `src/polaris_graph/audit_bundle/gpg_signer.py` — read for the env-var
  names (`POLARIS_GPG_KEY_ID` / `POLARIS_GPG_PASSPHRASE` / `GNUPGHOME`);
  NOT modified.
- `python-gnupg` confirmed installed; `GPG.sign_file` + `GPG.verify_file`
  both present.

## 5. Test / smoke (planned)

`python -m ast` parse the edited script + new test; `PYTHONPATH='src;.'
python -m pytest tests/v6/test_backup_gpg_sign.py
tests/v6/test_backup_restore.py -q` — new GPG tests pass (or skip cleanly
if the host gpg/gpg-agent is unavailable, per the `test_gpg_signer.py`
precedent), and the existing backup/restore suite still passes (no
regression — the sha256-only path is unchanged). A `backup` + `restore
--verify-sig` manual round-trip with an ephemeral keyring. Any pre-existing
failure verified identical on clean `polaris` HEAD before commit.

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
