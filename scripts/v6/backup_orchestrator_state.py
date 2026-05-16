#!/usr/bin/env python3
"""Off-box backup + restore of POLARIS v6 orchestrator state (I-rdy-016, #512).

Backs up the two pieces of durable v6 orchestrator state:
  1. the SQLite run store (run_store.py — the `runs` table; a WAL-mode DB);
  2. the run artifact directories (outputs/v6_runs/<run_id>/ — the source
     material from which signed audit bundles are rebuilt on demand by
     GET /runs/{run_id}/bundle.tar.gz);
into a single portable tar.gz archive with a sha256 integrity sidecar.

"Off-box" means the archive is written to an operator-configurable
destination directory; transporting it to genuinely separate storage (a
second Canadian VM, a mounted volume, an offline disk) is the operator's
step, documented in docs/carney_handover/runbook.md §6. There is
deliberately no built-in network push — that would couple POLARIS to
operator infrastructure the build team cannot test.

The DB snapshot uses the SQLite online-backup API, which is WAL-safe and
consistent against a concurrently-writing app. The artifact tree is NOT
snapshot-atomic against concurrent workers, and restore over a live app
is undefined — the supported sequence is:
    docker compose -f docker-compose.v6.yml stop
    <backup or restore>
    docker compose -f docker-compose.v6.yml start

`restore --force` REPLACES an existing destination DB / run-artifact dir
(it never merges); without it, an existing destination is refused.

Usage:
    python scripts/v6/backup_orchestrator_state.py backup \
        [--db PATH] [--artifact-root PATH] [--dest DIR]
    python scripts/v6/backup_orchestrator_state.py restore \
        --archive PATH [--db PATH] [--expect-sha256 HEX] [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_NAME = "backup_manifest.json"
SNAPSHOT_DB_NAME = "v6_runs.sqlite"
ARTIFACTS_DIRNAME = "artifacts"
SCHEMA_VERSION = 1

DEFAULT_DB = "state/v6_runs.sqlite"
DEFAULT_ARTIFACT_ROOT = "outputs/v6_runs"
DEFAULT_DEST = "backups"


def _fail(msg: str) -> None:
    """Fail loud: print to stderr, exit non-zero (CLAUDE.md LAW II)."""
    raise SystemExit(f"[backup_orchestrator_state] ERROR: {msg}")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _assert_no_symlinks(root: Path) -> None:
    """Reject symlinks / special files anywhere in the artifact tree.

    An artifact dir is plain manifest.json + data files; a symlink there is
    anomalous and must not be silently followed or copied into the archive.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            entry = Path(dirpath) / name
            if entry.is_symlink():
                _fail(f"artifact tree contains a symlink, refusing to back up: {entry}")
            if not entry.is_dir() and not entry.is_file():
                _fail(f"artifact tree contains a special file: {entry}")


def _snapshot_db(db_path: Path, dest_path: Path) -> None:
    """Consistent WAL-safe DB snapshot via the SQLite online-backup API."""
    src = sqlite3.connect(str(db_path))
    try:
        dst = sqlite3.connect(str(dest_path))
        try:
            with dst:
                src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _db_artifact_dirs(db_path: Path) -> tuple[int, list[str]]:
    """Return (row_count, [non-null artifact_dir values]) from the runs table."""
    conn = sqlite3.connect(str(db_path))
    try:
        try:
            row_count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            rows = conn.execute(
                "SELECT artifact_dir FROM runs WHERE artifact_dir IS NOT NULL"
            ).fetchall()
        except sqlite3.OperationalError as exc:
            _fail(f"DB has no usable `runs` table ({exc}) — wrong file?")
    finally:
        conn.close()
    return row_count, [r[0] for r in rows]


def cmd_backup(args: argparse.Namespace) -> None:
    db_path = Path(args.db).resolve()
    artifact_root = Path(args.artifact_root).resolve()
    dest = Path(args.dest)

    if not db_path.is_file():
        _fail(f"run-store DB not found: {db_path}")
    dest.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="polaris_backup_") as tmp:
        staging = Path(tmp)
        snapshot = staging / SNAPSHOT_DB_NAME
        _snapshot_db(db_path, snapshot)
        row_count, referenced = _db_artifact_dirs(snapshot)

        # Completeness check: every DB-referenced artifact dir must exist on
        # disk under artifact_root, else the backup cannot rebuild signed
        # audit bundles — fail loud rather than write a broken backup.
        for ref in referenced:
            run_id = Path(ref).name
            if not (artifact_root / run_id).is_dir():
                _fail(
                    f"DB references an artifact dir for run {run_id!r} but "
                    f"{artifact_root / run_id} is missing on disk — incomplete "
                    f"state, refusing to write a broken backup"
                )

        staged_artifacts = staging / ARTIFACTS_DIRNAME
        run_ids: list[str] = []
        artifact_file_count = 0
        if artifact_root.is_dir():
            _assert_no_symlinks(artifact_root)
            shutil.copytree(artifact_root, staged_artifacts)
            run_ids = [c.name for c in sorted(staged_artifacts.iterdir()) if c.is_dir()]
            artifact_file_count = sum(1 for p in staged_artifacts.rglob("*") if p.is_file())
        else:
            # Unreachable when `referenced` is non-empty — the completeness
            # check above already failed. Reached only for an artifact-free DB.
            staged_artifacts.mkdir()

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "db_sha256": _sha256_file(snapshot),
            "run_row_count": row_count,
            "artifact_root": str(artifact_root),
            "run_ids": run_ids,
            "artifact_file_count": artifact_file_count,
            "polaris_git_commit": os.environ.get("POLARIS_GIT_COMMIT", ""),
        }
        (staging / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )

        archive = dest / f"polaris_v6_state_{_utc_stamp()}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(staging, arcname=".")

    digest = _sha256_file(archive)
    (archive.parent / f"{archive.name}.sha256").write_text(
        f"{digest}  {archive.name}\n", encoding="utf-8"
    )
    print(f"backup OK: {archive}")
    print(f"  sha256: {digest}")
    print(f"  runs: {row_count}  artifact dirs: {len(run_ids)}  files: {artifact_file_count}")


def _safe_members(tar: tarfile.TarFile, dest: Path):
    """Yield only regular-file / dir members whose path stays within dest.

    Rejects symlink / hardlink / device / FIFO members and any member whose
    resolved path escapes the extraction directory (absolute path or `..`).
    """
    dest_real = os.path.realpath(dest)
    for member in tar.getmembers():
        if not (member.isreg() or member.isdir()):
            _fail(f"unsafe tar member (symlink/hardlink/device): {member.name}")
        target = os.path.realpath(os.path.join(dest_real, member.name))
        if target != dest_real and not target.startswith(dest_real + os.sep):
            _fail(f"unsafe tar member (path escape): {member.name}")
        yield member


def cmd_restore(args: argparse.Namespace) -> None:
    archive = Path(args.archive).resolve()
    if not archive.is_file():
        _fail(f"archive not found: {archive}")

    expected = args.expect_sha256
    if expected is None:
        sidecar = archive.parent / f"{archive.name}.sha256"
        if not sidecar.is_file():
            _fail(f"no --expect-sha256 given and no sidecar {sidecar.name}")
        expected = sidecar.read_text(encoding="utf-8").split()[0]
    actual = _sha256_file(archive)
    if actual != expected:
        _fail(f"archive sha256 mismatch (expected {expected}, got {actual}) — refusing restore")

    db_path = Path(args.db).resolve()

    with tempfile.TemporaryDirectory(prefix="polaris_restore_") as tmp:
        extracted = Path(tmp)
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(extracted, members=_safe_members(tar, extracted))

        manifest_path = extracted / MANIFEST_NAME
        snapshot = extracted / SNAPSHOT_DB_NAME
        if not manifest_path.is_file() or not snapshot.is_file():
            _fail("archive is missing backup_manifest.json or the snapshot DB")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        # DB restore — refuse to clobber an existing DB without --force.
        if db_path.exists() and not args.force:
            _fail(f"destination DB exists: {db_path} — pass --force to replace")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        for stale in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
            if stale.exists():
                stale.unlink()
        shutil.copy2(snapshot, db_path)

        # Artifact restore — path-faithful to the manifest's artifact_root so
        # the restored runs.artifact_dir values stay valid (no path rewrite).
        artifact_root = Path(manifest["artifact_root"])
        artifact_root.mkdir(parents=True, exist_ok=True)
        staged_artifacts = extracted / ARTIFACTS_DIRNAME
        restored = 0
        if staged_artifacts.is_dir():
            for child in sorted(staged_artifacts.iterdir()):
                if not child.is_dir():
                    continue
                target = artifact_root / child.name
                if target.exists():
                    if not args.force:
                        _fail(f"artifact dir exists: {target} — pass --force to replace")
                    shutil.rmtree(target)
                shutil.copytree(child, target)
                restored += 1

    print(f"restore OK: DB -> {db_path}")
    print(f"  runs: {manifest['run_row_count']}  artifact dirs restored: {restored}")
    print(f"  artifact root: {artifact_root}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="POLARIS v6 orchestrator-state backup / restore"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    backup = sub.add_parser("backup", help="snapshot the run store + artifact dirs to a tar.gz")
    backup.add_argument("--db", default=os.environ.get("POLARIS_V6_RUN_DB", DEFAULT_DB))
    backup.add_argument(
        "--artifact-root",
        default=os.environ.get("POLARIS_V6_OUTPUT_ROOT", DEFAULT_ARTIFACT_ROOT),
    )
    backup.add_argument("--dest", default=os.environ.get("POLARIS_BACKUP_DIR", DEFAULT_DEST))
    backup.set_defaults(func=cmd_backup)

    restore = sub.add_parser("restore", help="restore a tar.gz produced by `backup`")
    restore.add_argument("--archive", required=True)
    restore.add_argument("--db", default=os.environ.get("POLARIS_V6_RUN_DB", DEFAULT_DB))
    restore.add_argument("--expect-sha256", default=None)
    restore.add_argument(
        "--force",
        action="store_true",
        help="replace an existing destination DB / artifact dir (never merges)",
    )
    restore.set_defaults(func=cmd_restore)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
