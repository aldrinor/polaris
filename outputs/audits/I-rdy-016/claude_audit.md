# Claude architect audit — I-rdy-016 (#512)

**Issue:** Workstream L — off-box backup of the orchestrator SQLite run store
+ signed audit bundles; a backup-and-restore cycle proven.
**Branch:** `bot/I-rdy-016-state-backup` off `polaris`.
**Canonical diff sha256:** `86241366fd6d54b9a41b28d050881cd84d8e2cde49bc88a8fed8b2a686fc8444`

## What shipped

| File | Change |
|---|---|
| `scripts/v6/backup_orchestrator_state.py` | NEW — `backup` + `restore` CLI, 298 lines |
| `tests/v6/test_backup_restore.py` | NEW — subprocess e2e proving the cycle, 186 lines |
| `docs/carney_handover/runbook.md` | §6 rewritten (+47/-3) |

## Design

- **DB snapshot** uses `sqlite3.Connection.backup()` — the SQLite online-backup
  API. WAL-safe, page-consistent against a concurrently-writing app, produces
  a clean single-file DB with no `-wal`/`-shm` sidecars. A raw file copy of a
  WAL DB would be torn — explicitly avoided.
- **Completeness check:** backup reads the snapshot's `runs` table and, for
  every non-null `artifact_dir`, requires the corresponding `<artifact-root>/
  <run_id>` dir to exist on disk. A referenced artifact missing → fail loud.
  A genuinely artifact-free DB still backs up cleanly.
- **Integrity:** a `backup_manifest.json` (schema v1) records `db_sha256`,
  `run_row_count`, `artifact_root`, `run_ids`, `artifact_file_count`,
  `polaris_git_commit`; a `.sha256` sidecar covers the whole tarball. Restore
  verifies the tarball sha256 before extracting.
- **Restore is path-faithful:** artifacts go back to the `artifact_root`
  recorded in the manifest, so `runs.artifact_dir` values stay valid with no
  path rewriting. There is no `--artifact-root` flag on `restore` by design.
- **Safe extraction:** every tar member must be a regular file or directory
  (symlink / hardlink / device / FIFO rejected) and resolve within the
  extraction dir (`..` / absolute rejected) — a manual member check, not the
  version-dependent `tarfile` `filter=` kwarg.
- **`--force`** replaces an existing destination DB / artifact dir; it never
  merges. Without it, an existing destination is refused.
- **"Off-box"** = a portable archive at an operator-configurable `--dest`;
  transport to separate storage is the operator's documented step. No
  built-in network push (would couple to untestable operator infra; the
  sovereignty constraint forbids US object stores).

## Fail-loud surfaces (LAW II)

Missing DB · DB with no usable `runs` table · DB-referenced artifact dir
missing on disk · symlink/special file in the artifact tree · sha256
mismatch · unsafe tar member · clobber without `--force` · missing
manifest/snapshot in the archive. Every path raises `SystemExit` → non-zero
exit.

## Invariant / scope check

- **LAW VII (CLI isolation):** a standalone CLI in `scripts/v6/`, matching
  the existing `cost_summary.py` / `replay_pin.py` pattern. No cross-phase
  imports.
- **LAW VI (zero hard-coding):** all paths come from CLI args or env
  (`POLARIS_V6_RUN_DB`, `POLARIS_V6_OUTPUT_ROOT`, `POLARIS_BACKUP_DIR`).
- **§9.4 hygiene:** no bare `except`, no mock in `src/` (this is `scripts/`),
  no magic numbers, no `time.sleep`. The one unreachable `else` branch in
  `cmd_backup` is annotated with why (the completeness check precedes it).
- No existing code path modified — blast radius is the new files + a doc
  section. No `tests/v6/` regression possible from adding one isolated file.

## Honesty note

The runbook §6 previously documented a backup to `s3://polaris-pins-bhs/`
that does not exist (S3 archived in the AWS→Vexxhost pivot, #486). This PR
replaces a fictional mechanism with a real, tested one — a net honesty fix,
not just an addition.

## Verification

`pytest tests/v6/test_backup_restore.py` — 6 passed (round-trip with DB-row +
artifact-file equality; 5 fail-loud edge cases). CLI `--help` for both
subcommands renders. LOC exceeds the 200-line cap (~484 code); Codex granted
the exemption at brief iter 1 (all-new isolated files; the test IS the
acceptance criterion).

## Verdict

Ready for Codex diff review. The cycle is proven by an end-to-end test that
asserts equality on both the DB and the artifacts, not merely "ran without
error".
