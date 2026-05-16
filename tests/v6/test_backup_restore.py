"""I-rdy-016 (#512) — proven backup/restore cycle for v6 orchestrator state.

Subprocess-drives `scripts/v6/backup_orchestrator_state.py` end-to-end (same
harness style as test_scripts_v6_handover.py): builds a real run-store DB +
artifact dirs via the genuine `run_store` API, backs up, wipes, restores, and
asserts DB-row + artifact-file equality. Plus the fail-loud edge cases.

"Ran without error" is not accepted as proof — equality on both the DB rows
and the artifact files is asserted.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

from polaris_v6.queue import run_store

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "v6" / "backup_orchestrator_state.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_rows(db: Path) -> list[dict]:
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM runs ORDER BY run_id")]
    finally:
        conn.close()


def _build_db(db: Path, artifact_root: Path, run_ids: list[str]) -> None:
    """Build a genuine run-store DB + artifact dirs via the real run_store API."""
    db.parent.mkdir(parents=True, exist_ok=True)
    for run_id in run_ids:
        run_store.insert_run(run_id, "clinical_efficacy", f"Question {run_id}", path=str(db))
        adir = artifact_root / run_id
        adir.mkdir(parents=True)
        (adir / "manifest.json").write_text(json.dumps({"run_id": run_id}), encoding="utf-8")
        (adir / "report.md").write_text(f"# report for {run_id}\n", encoding="utf-8")
        run_store.set_pipeline_meta(run_id, artifact_dir=str(adir), path=str(db))
        run_store.mark_completed(run_id, {"ok": True}, path=str(db))


def test_backup_restore_round_trip(tmp_path):
    db = tmp_path / "state" / "v6_runs.sqlite"
    artifact_root = tmp_path / "outputs" / "v6_runs"
    dest = tmp_path / "backups"
    run_ids = ["run-aaa", "run-bbb", "run-ccc"]
    _build_db(db, artifact_root, run_ids)

    rows_before = _read_rows(db)
    report_sha_before = _sha(artifact_root / "run-bbb" / "report.md")

    result = _run("backup", "--db", str(db), "--artifact-root", str(artifact_root),
                  "--dest", str(dest))
    assert result.returncode == 0, result.stderr
    archives = list(dest.glob("polaris_v6_state_*.tar.gz"))
    assert len(archives) == 1, archives
    archive = archives[0]
    assert (dest / f"{archive.name}.sha256").is_file()

    # Wipe the live state entirely, then restore from the archive.
    shutil.rmtree(db.parent)
    shutil.rmtree(artifact_root)

    result = _run("restore", "--archive", str(archive), "--db", str(db))
    assert result.returncode == 0, result.stderr

    rows_after = _read_rows(db)
    assert len(rows_after) == 3
    assert rows_after == rows_before  # every column of every row, deep-equal

    for run_id in run_ids:
        row = next(r for r in rows_after if r["run_id"] == run_id)
        adir = Path(row["artifact_dir"])
        assert adir.is_dir(), f"restored artifact_dir missing: {adir}"
        assert (adir / "manifest.json").is_file()
    assert _sha(artifact_root / "run-bbb" / "report.md") == report_sha_before


def test_backup_fails_loud_on_missing_referenced_artifact(tmp_path):
    db = tmp_path / "state" / "v6_runs.sqlite"
    artifact_root = tmp_path / "outputs" / "v6_runs"
    _build_db(db, artifact_root, ["run-aaa"])
    shutil.rmtree(artifact_root / "run-aaa")  # DB still references it

    result = _run("backup", "--db", str(db), "--artifact-root", str(artifact_root),
                  "--dest", str(tmp_path / "backups"))
    assert result.returncode != 0
    assert "incomplete" in result.stderr.lower() or "missing" in result.stderr.lower()


def test_restore_refuses_clobber_without_force(tmp_path):
    db = tmp_path / "state" / "v6_runs.sqlite"
    artifact_root = tmp_path / "outputs" / "v6_runs"
    dest = tmp_path / "backups"
    _build_db(db, artifact_root, ["run-aaa"])

    result = _run("backup", "--db", str(db), "--artifact-root", str(artifact_root),
                  "--dest", str(dest))
    assert result.returncode == 0, result.stderr
    archive = next(dest.glob("polaris_v6_state_*.tar.gz"))

    # DB still exists — restore without --force must refuse.
    result = _run("restore", "--archive", str(archive), "--db", str(db))
    assert result.returncode != 0
    assert "force" in result.stderr.lower()

    # With --force it succeeds (replaces DB + the existing artifact dir).
    result = _run("restore", "--archive", str(archive), "--db", str(db), "--force")
    assert result.returncode == 0, result.stderr


def test_restore_rejects_tampered_archive(tmp_path):
    db = tmp_path / "state" / "v6_runs.sqlite"
    artifact_root = tmp_path / "outputs" / "v6_runs"
    dest = tmp_path / "backups"
    _build_db(db, artifact_root, ["run-aaa"])

    result = _run("backup", "--db", str(db), "--artifact-root", str(artifact_root),
                  "--dest", str(dest))
    assert result.returncode == 0, result.stderr
    archive = next(dest.glob("polaris_v6_state_*.tar.gz"))

    data = bytearray(archive.read_bytes())
    data[len(data) // 2] ^= 0xFF  # flip a byte; sidecar sha256 is now stale
    archive.write_bytes(bytes(data))

    fresh_db = tmp_path / "restore" / "v6_runs.sqlite"
    result = _run("restore", "--archive", str(archive), "--db", str(fresh_db))
    assert result.returncode != 0
    assert "sha256" in result.stderr.lower()
    assert not fresh_db.exists()  # destination untouched


def test_restore_rejects_unsafe_tar_member(tmp_path):
    # An archive with a path-escaping member AND a correct sha256 sidecar, so
    # the rejection is proven to happen at extraction, not at the digest check.
    archive = tmp_path / "polaris_v6_state_evil.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        payload = b"pwned"
        info = tarfile.TarInfo("../escape.txt")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (tmp_path / f"{archive.name}.sha256").write_text(f"{digest}  {archive.name}\n",
                                                     encoding="utf-8")

    result = _run("restore", "--archive", str(archive),
                  "--db", str(tmp_path / "v6_runs.sqlite"))
    assert result.returncode != 0
    assert "unsafe" in result.stderr.lower() or "escape" in result.stderr.lower()


def test_backup_fails_loud_on_missing_db(tmp_path):
    result = _run("backup", "--db", str(tmp_path / "does_not_exist.sqlite"),
                  "--artifact-root", str(tmp_path / "art"),
                  "--dest", str(tmp_path / "backups"))
    assert result.returncode != 0
    assert "not found" in result.stderr.lower()
