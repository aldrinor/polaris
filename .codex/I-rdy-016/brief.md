# Codex brief review — I-rdy-016 (#512): off-box backup of orchestrator state

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
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

You are reviewing the **brief / acceptance criteria** for GitHub issue #512.

---

## Codex iter-1 findings — resolutions (all 3 P1 + 4 P2 addressed)

**P1-1 (compose-executable commands).** Resolved in the runbook §6 rewrite
below: §6 now gives the **exact `docker compose run` invocation**. The
`api` service already mounts `shared_state:/app/state` + `./outputs:/app/outputs`;
`docker compose run --rm` reuses that service's volume config, `--entrypoint
python` overrides the `/entrypoint.sh` dispatcher (verified: `Dockerfile.v6`
`ENTRYPOINT ["/entrypoint.sh"]` + `CMD ["api"]`), and a `-v "$PWD/backups:/backups"`
bind lands the archive on the host — i.e. outside any container, transportable.

**P1-2 (incomplete-backup must fail loud).** Resolved: `backup` now reads the
`runs` table, collects every non-null `artifact_dir`, and verifies each
referenced dir exists on disk and is captured. A DB-referenced artifact dir
missing from disk → **fail loud, non-zero exit**. A genuinely artifact-free
DB (zero rows with non-null `artifact_dir`) still backs up cleanly.

**P1-3 (DB↔artifact linkage preserved + proven).** Resolved two ways:
(a) restore is **path-faithful** — it restores the artifact tree to the
`artifact_root` recorded in `backup_manifest.json`, NOT to an operator-chosen
root, so the `runs.artifact_dir` values stay valid with no path rewriting.
There is deliberately **no `--artifact-root` flag on `restore`**. (b) the
round-trip test populates `runs.artifact_dir` via the real
`run_store.set_pipeline_meta(artifact_dir=...)` and asserts every restored
row's `artifact_dir` resolves to an existing directory containing its
`manifest.json`.

**P2-1.** Added `test_restore_rejects_unsafe_tar_member` — crafts a tarball
with a `../escape` member AND writes a **correct** sha256 sidecar, so the
rejection is proven to happen at extraction (path check), not at the digest
check.

**P2-2.** Safe-extract allows **only** regular files and directories; it
rejects symlink, hardlink, char/block device and FIFO members. Backup
staging refuses to stage symlinks / special files found in the artifact
tree (fail loud — an artifact dir is plain `manifest.json` + data files; a
symlink there is anomalous and must not be silently followed or copied).

**P2-3.** `restore --force` semantics defined: for each `run_id` present in
the backup whose dir already exists under the restore root, `--force`
**replaces** it (remove the existing dir, then write the restored one) —
never merges, so no stale-file mixing. Run dirs NOT in the backup are left
untouched. Without `--force`, an existing destination DB or an existing
run_id artifact dir → refuse, non-zero exit. Documented in the script
header and runbook.

**P2-4 (LOC exemption).** Acknowledged — granted. Not split.

---

## Issue #512 (I-rdy-016) — verbatim

> **Workstream L. Off-box backup of the orchestrator SQLite run store +
> signed audit bundles.**
> Acceptance: a backup-and-restore cycle is proven; Codex APPROVE.
> Depends on: none (parallel).

## Context — what "orchestrator state" is (verified against HEAD)

The v6 stack (`docker-compose.v6.yml`: redis + api + worker + webui) keeps
two pieces of durable state:

1. **The SQLite run store.** `src/polaris_v6/queue/run_store.py` — one
   `runs` table (PK `run_id`; `lifecycle_status`, `artifact_dir`,
   `pipeline_status`, `cost_usd`, timestamps, result/error JSON). Path
   `state/v6_runs.sqlite`, override env `POLARIS_V6_RUN_DB`. `init_db()`
   sets `PRAGMA journal_mode=WAL` (line 96) → a live DB has `-wal`/`-shm`
   sidecars. In compose it sits on the **named volume `shared_state`**
   (`/app/state`) — `docker compose down -v` destroys it.
2. **Run artifact directories.** `actors.py:89` writes each run under
   `Path(os.environ.get("POLARIS_V6_OUTPUT_ROOT", "outputs/v6_runs")) / run_id`,
   each holding `manifest.json` + the pipeline-A slice chain. `outputs/` is
   a bind mount (`./outputs:/app/outputs`). `GET /runs/{run_id}/bundle.tar.gz`
   (`api/bundle.py`) rebuilds the **signed audit bundle on demand** from
   `artifact_dir` (`build_slice_chain` + GPG sign) — there is no persistent
   signed-bundle store, so "signed audit bundles" in the issue = the
   artifact dirs that are their source material.

`artifact_dir` persisted in each run row is whatever `POLARIS_V6_OUTPUT_ROOT`
resolved to at write time (default the relative `outputs/v6_runs/<run_id>`;
in-container `/app/outputs/v6_runs/<run_id>`). Its basename is always the
`run_id`.

## A real defect this PR fixes

`docs/carney_handover/runbook.md` §6 claims pins are *"Backed up daily to
encrypted Canadian S3-compatible storage at `s3://polaris-pins-bhs/`"*. That
bucket does not exist — S3 was archived in the AWS→Vexxhost pivot (#486; see
`infra/aws.archived/`). §6 documents a non-real mechanism and never mentions
the run DB. This PR replaces it with a working, tested procedure.

## LOCKED constraints (operator-set; NOT for Codex to relax)

- **Sovereign Canadian deploy.** No US object store (no S3/GCS). The tool
  MUST NOT couple to a US-jurisdiction service.
- **"Off-box" definition:** the tool produces a single portable archive at
  an operator-configurable destination directory; the `-v "$PWD/backups:/backups"`
  host bind in the documented compose invocation lands it outside any
  container. *Transport* of that archive to genuinely separate storage (a
  second Canadian VM, an operator-mounted volume, an offline disk) is the
  operator's documented step — deliberately NOT a built-in network push: a
  built-in `rsync`/`scp`/object-store push would hard-couple POLARIS to
  operator infra the build team cannot test, and the sovereignty constraint
  forbids the obvious US object stores. A portable archive + documented
  transport is the honest, testable unit. "Add a network push" is at most
  P2/P3, not P0/P1.

## Proposed implementation

### File 1 (NEW) — `scripts/v6/backup_orchestrator_state.py`

Self-contained CLI (matches the `scripts/v6/` pattern — `cost_summary.py`,
`replay_pin.py`, `run_pin_replay.py` are all self-contained, subprocess-tested).
`argparse` with two subcommands.

**`backup`** — flags `--db`, `--artifact-root`, `--dest`:
1. Resolve `--db` (default env `POLARIS_V6_RUN_DB` else `state/v6_runs.sqlite`),
   `--artifact-root` (default env `POLARIS_V6_OUTPUT_ROOT` else
   `outputs/v6_runs`), `--dest` (default env `POLARIS_BACKUP_DIR` else `backups`).
2. If `--db` does not exist → **fail loud**, non-zero exit (a missing DB is a
   misconfigured path, not "empty state" — the orchestrator creates the DB on
   first `init_db()`).
3. **DB snapshot via the SQLite online-backup API** —
   `sqlite3.connect(db).backup(sqlite3.connect(snapshot_path))`. WAL-safe and
   consistent against a concurrently-writing app; no stack stop needed for
   the DB. A raw file copy of a WAL DB would be torn — forbidden.
4. **Completeness check (P1-2):** open the snapshot, `SELECT artifact_dir
   FROM runs WHERE artifact_dir IS NOT NULL`. For each, take `basename` (the
   `run_id`) and require `<artifact-root>/<run_id>` to exist on disk. Any
   referenced artifact dir missing → **fail loud**, non-zero exit, naming the
   `run_id`. If no rows reference artifacts, an empty artifact capture is OK.
5. Stage the snapshot DB + a copy of every `<artifact-root>/<run_id>` dir
   (only those referenced by the DB, plus any other dirs directly under
   `artifact-root` — capture the whole root) into a temp staging dir.
   **Staging refuses symlinks / special files** in the artifact tree
   (fail loud).
6. Write `backup_manifest.json`: `schema_version`, UTC `created_at`,
   `db_sha256` (of the snapshot DB), `run_row_count`, `artifact_root`
   (the basename layout used, e.g. `v6_runs`), `run_ids` (list captured),
   `artifact_file_count`, `polaris_git_commit` (env `POLARIS_GIT_COMMIT`
   if set).
7. `tar.gz` the staging dir → `<dest>/polaris_v6_state_<utc>.tar.gz`.
8. sha256 the tarball → write sibling `<tarball>.sha256`.
9. Print archive path + digest; exit 0.

**`restore`** — flags `--archive` (required), `--db`, `--expect-sha256`,
`--force`:
1. Verify the tarball sha256 against the sibling `.sha256` file (or
   `--expect-sha256`). Mismatch → **fail loud**, no extraction.
2. **Safe extraction (P2-2):** before extracting, reject any member that is
   not a regular file or directory (symlink/hardlink/device/FIFO), or whose
   resolved path escapes the staging dir (absolute / `..`). Manual
   member-by-member check — does not rely on `tarfile`'s `filter=` kwarg.
3. Read `backup_manifest.json` from the extracted staging dir.
4. **DB restore:** target = `--db` (default as backup). If it exists and
   `--force` not given → refuse, non-zero exit. On restore, place the
   snapshot DB at the target and **delete any stale `-wal`/`-shm`** beside
   it so SQLite cannot replay an old WAL over the restored file.
5. **Artifact restore (P1-3, path-faithful):** restore the artifact tree
   under the root recorded in the manifest (`artifact_root`), resolved
   relative to the DB's parent's sibling (or an absolute root if the
   manifest recorded one) — concretely: artifacts go back exactly where the
   DB's `artifact_dir` values point. For each backed-up `run_id` dir: if it
   exists and `--force` not given → refuse; with `--force` → remove the
   existing dir then write the restored one (**replace, never merge**, P2-3).
   Run dirs not in the backup are left untouched.
6. Print restored run count + artifact count; exit 0.

**Operational note (script header + runbook §6):** the artifact tree is not
snapshot-atomic against concurrent workers, and restore over a live app is
undefined. Supported sequence: `docker compose -f docker-compose.v6.yml stop
→ backup/restore → start`. The DB snapshot itself is online-safe; the stop
covers the artifact tree and restore sanity.

### File 2 (NEW) — `tests/v6/test_backup_restore.py`

Subprocess-driven e2e (harness style of `tests/v6/test_scripts_v6_handover.py`
— `subprocess.run`, `PYTHONPATH=src`), proving the cycle:

- **`test_backup_restore_round_trip`**: build a tmp DB via the real
  `run_store` API — `init_db`, then 3× (`insert_run` → `set_pipeline_meta(
  artifact_dir=<root>/<run_id>)` → `mark_completed`). Create each
  `<root>/<run_id>/` with a `manifest.json` + a data file. Run `backup` →
  delete the DB + artifact tree → run `restore` → assert: (a) restored
  `runs` row count == 3; (b) a sampled row deep-equals the original (every
  column, via `get_run` / direct SELECT); (c) each restored row's
  `artifact_dir` resolves to an existing dir containing its `manifest.json`;
  (d) a sampled artifact data file's sha256 == original. "Ran without error"
  is NOT accepted as proof.
- **`test_backup_fails_loud_on_missing_referenced_artifact`**: DB row has a
  non-null `artifact_dir` but the dir is absent on disk → `backup` exits
  non-zero (P1-2).
- **`test_restore_refuses_clobber_without_force`**: `restore` onto an
  existing DB exits non-zero unless `--force`.
- **`test_restore_rejects_tampered_archive`**: flip a byte in the tarball →
  `restore` fails loud on sha256 mismatch, destination untouched.
- **`test_restore_rejects_unsafe_tar_member`**: craft a tarball with a
  `../escape` member + a **correct** sha256 sidecar → `restore` fails loud
  on the unsafe member (proves the path check, not the digest check) (P2-1).
- **`test_backup_fails_loud_on_missing_db`**: `backup` with a non-existent
  `--db` exits non-zero.

### File 3 (EDIT) — `docs/carney_handover/runbook.md` §6

Rewrite §6: remove the fictional `s3://polaris-pins-bhs/` claim; document
the **exact compose invocation**, e.g.:

```
# Backup (archive lands in ./backups on the host — transport it off-box):
docker compose -f docker-compose.v6.yml stop
docker compose -f docker-compose.v6.yml run --rm \
  -v "$PWD/backups:/backups" --entrypoint python api \
  scripts/v6/backup_orchestrator_state.py backup \
  --db /app/state/v6_runs.sqlite --artifact-root /app/outputs/v6_runs --dest /backups
docker compose -f docker-compose.v6.yml start

# Restore:
docker compose -f docker-compose.v6.yml run --rm \
  -v "$PWD/backups:/backups" --entrypoint python api \
  scripts/v6/backup_orchestrator_state.py restore \
  --archive /backups/polaris_v6_state_<utc>.tar.gz --db /app/state/v6_runs.sqlite --force
```

Plus: the `stop → … → start` sequence, and the explicit statement that the
operator must transport `./backups/*.tar.gz` to genuinely off-box storage
(second Canadian VM / mounted volume / offline disk). Keep the existing
`replay_pin.py` diff guidance — it is correct and still used.

## Explicitly OUT of scope (carved; do not flag as P0/P1)

- **GPG signature over the archive** → carved to **#547** (sha256 manifest +
  `.sha256` sidecar is the CI-testable integrity path; CI has no GPG demo key).
- A scheduled cron/systemd backup unit in `provision.sh` — runbook documents
  the command + cadence; the timer is operator-side.
- Redis state — holds only the transient Dramatiq queue; durable run state
  is already in SQLite. Not backed up by design.

## LOC estimate

~190 lines script + ~140 lines test + ~30 lines doc ≈ **~360, ~330 code**.
Two all-new files + a ~30-line doc rewrite; modifies no existing code path.
LOC-cap exemption granted iter 1 (P2-4). Test file is the acceptance
criterion — not compressed.

## Files I have ALSO checked and they're clean

- `src/polaris_v6/queue/run_store.py` — `_connect`, `init_db` (WAL pragma
  L96), `insert_run`/`set_pipeline_meta`/`mark_completed`/`get_run` public
  API the test fixture uses. No run_store change needed.
- `src/polaris_v6/queue/actors.py:89` — artifact-dir layout
  (`output_root / run_id`); confirms `POLARIS_V6_OUTPUT_ROOT` default.
- `src/polaris_v6/api/bundle.py` — signed bundles rebuilt on demand from
  `artifact_dir`; no persistent bundle store.
- `docker-compose.v6.yml` — `shared_state` named volume vs `./outputs` bind;
  `api` service volume config reused by `docker compose run`.
- `Dockerfile.v6` — `ENTRYPOINT ["/entrypoint.sh"]` + `CMD ["api"]`;
  `--entrypoint python` override confirmed valid.
- `scripts/v6/{cost_summary,replay_pin,run_pin_replay}.py` +
  `tests/v6/test_scripts_v6_handover.py` — the self-contained-script +
  subprocess-test pattern this PR follows.
- `infra/vexxhost/provision.sh`, `infra/aws.archived/` — confirms S3 is
  archived; runbook §6 S3 reference is genuinely stale.
- `tests/v6/conftest.py` — StubBroker setup; the new test does not touch
  dramatiq/broker, so it is unaffected.

## Acceptance criteria for the resulting PR

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

Return the YAML verdict block only.
