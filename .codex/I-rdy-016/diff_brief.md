# Codex diff review — I-rdy-016 (#512): off-box backup of orchestrator state

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (return THIS, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

You are reviewing the **diff** for issue #512 against the APPROVE'd brief
(`.codex/I-rdy-016/brief.md`, brief verdict APPROVE iter 2).

## What to review

The canonical diff is `.codex/I-rdy-016/codex_diff.patch`
(sha256 trailer `# canonical-diff-sha256: 86241366fd6d54b9a41b28d050881cd84d8e2cde49bc88a8fed8b2a686fc8444`).
3 files, +528/-3:

- `scripts/v6/backup_orchestrator_state.py` (NEW, 298 lines) — `backup` +
  `restore` CLI.
- `tests/v6/test_backup_restore.py` (NEW, 186 lines) — subprocess e2e.
- `docs/carney_handover/runbook.md` (+47/-3) — §6 rewrite.

## Brief acceptance criteria (verbatim)

1. `scripts/v6/backup_orchestrator_state.py` with `backup` + `restore`;
   DB snapshot via `sqlite3` online-backup API; fail-loud on missing DB,
   missing DB-referenced artifact, sha256 mismatch, unsafe tar member,
   clobber-without-force; `--force` = replace (never merge).
2. `tests/v6/test_backup_restore.py` proves the round-trip with DB-row +
   artifact-file + `artifact_dir`-resolves equality assertions, plus the
   5 edge tests.
3. `docs/carney_handover/runbook.md` §6 rewritten — fictional S3 removed,
   exact compose invocation + off-box transport documented.
4. `pytest tests/v6/test_backup_restore.py` passes; no `tests/v6/` regression.

## How the brief's iter-1 P1/P2 findings were implemented

- **P1-1** (compose-executable): runbook §6 gives the exact
  `docker compose run --rm -v "$PWD/backups:/backups" --entrypoint python api
  scripts/v6/backup_orchestrator_state.py …` invocation for both backup and
  restore; the script is path-agnostic via `--db`/`--artifact-root`/`--dest`.
- **P1-2** (incomplete-backup fails loud): `cmd_backup` runs the completeness
  check — `_db_artifact_dirs` collects non-null `artifact_dir`, each
  `<artifact-root>/<run_id>` must exist on disk or `_fail`.
- **P1-3** (DB↔artifact linkage): restore is path-faithful (no
  `--artifact-root` flag — artifacts go to `manifest["artifact_root"]`); the
  round-trip test populates `artifact_dir` via `run_store.set_pipeline_meta`
  and asserts each restored row's `artifact_dir` resolves to a real dir.
- **P2-1** (unsafe-tar test with valid sha): `test_restore_rejects_unsafe_tar_member`
  writes a correct `.sha256` sidecar so the rejection is proven at extraction.
- **P2-2** (reject hardlinks/devices, no symlink-follow): `_safe_members`
  allows only `isreg()`/`isdir()`; `_assert_no_symlinks` rejects symlinks +
  special files in the artifact tree before staging.
- **P2-3** (`--force` semantics): `--force` removes then re-copies an
  existing DB / run dir (replace, never merge); documented in the header.

## Verification done

- `pytest tests/v6/test_backup_restore.py` → 6 passed (round-trip + 5 edge).
- `backup --help` / `restore --help` render.
- No existing code path modified; the new test is one isolated file, so no
  `tests/v6/` regression is possible.

## Out of scope (do not flag as P0/P1)

- GPG-signing the archive → carved to follow-up **#547** (sha256 manifest +
  sidecar is the CI-testable integrity path; CI has no GPG demo key).
- A cron/systemd backup timer → operator-side; runbook documents cadence.
- Redis state — transient Dramatiq queue only; not backed up by design.

## LOC

+528/-3, ~484 of which is code (new script + new test). Exceeds the 200-LOC
cap; **exemption granted at brief review iter 1 (P2-4)** — two all-new
isolated files, no existing code path touched, and the test file is the
issue's acceptance criterion.

## Files I have ALSO checked and they're clean

- `src/polaris_v6/queue/run_store.py` — `insert_run`/`set_pipeline_meta`/
  `mark_completed`/`get_run` signatures the test fixture calls; backup only
  reads the `runs` table via raw `sqlite3`, no run_store change.
- `tests/v6/conftest.py` — the new test imports only `run_store` (pure
  sqlite), not dramatiq/broker; conftest's StubBroker setup is unaffected.
- `tests/v6/test_scripts_v6_handover.py` — the subprocess-test pattern the
  new test mirrors.
- `Dockerfile.v6` — `ENTRYPOINT ["/entrypoint.sh"]` + `CMD ["api"]`;
  `--entrypoint python` override in the runbook is valid.
- `docker-compose.v6.yml` — `api` service mounts `shared_state` + `./outputs`,
  reused by `docker compose run`.

Return the YAML verdict block only.
