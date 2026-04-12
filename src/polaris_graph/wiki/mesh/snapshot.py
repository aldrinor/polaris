"""
Mesh snapshot — zstd-compressed database backup and restore.

Creates point-in-time snapshots of mesh.db for backup/restore.
Uses zstandard streaming (file-to-file, not in-memory) so large
databases don't need to fit in RAM.

Usage:
    from mesh.snapshot import create_snapshot, restore_snapshot, list_snapshots

    path = create_snapshot(db_path, snapshot_dir)
    restore_snapshot(path, db_path)
    snapshots = list_snapshots(snapshot_dir)
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

import zstandard as zstd

logger = logging.getLogger(__name__)

ZSTD_LEVEL = 3
SNAPSHOT_SUFFIX = ".mesh.zst"


def create_snapshot(
    db_path: str | Path,
    snapshot_dir: str | Path,
) -> Path:
    """
    Create a zstd-compressed snapshot of the mesh database.

    Returns the path to the snapshot file. The filename includes an
    ISO timestamp for ordering.

    The store MUST be closed (or at least not mid-transaction) before
    calling this — we copy the raw file bytes.
    """
    db_path = Path(db_path)
    snapshot_dir = Path(snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot_name = f"{timestamp}{SNAPSHOT_SUFFIX}"
    snapshot_path = snapshot_dir / snapshot_name

    compressor = zstd.ZstdCompressor(level=ZSTD_LEVEL)
    with open(db_path, "rb") as src, open(snapshot_path, "wb") as dst:
        compressor.copy_stream(src, dst)

    size_mb = snapshot_path.stat().st_size / (1024 * 1024)
    logger.info(
        "Snapshot created: %s (%.1f MB)", snapshot_path.name, size_mb,
    )
    return snapshot_path


def restore_snapshot(
    snapshot_path: str | Path,
    db_path: str | Path,
) -> None:
    """
    Restore a mesh database from a zstd-compressed snapshot.

    Overwrites the existing mesh.db. The store MUST be closed before
    calling this.
    """
    snapshot_path = Path(snapshot_path)
    db_path = Path(db_path)

    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)

    decompressor = zstd.ZstdDecompressor()
    with open(snapshot_path, "rb") as src, open(db_path, "wb") as dst:
        decompressor.copy_stream(src, dst)

    logger.info("Snapshot restored: %s → %s", snapshot_path.name, db_path)


def list_snapshots(snapshot_dir: str | Path) -> list[dict]:
    """
    List all snapshots in the directory, sorted by timestamp descending
    (newest first).

    Returns list of {"path": Path, "name": str, "size_bytes": int,
    "timestamp": str}.
    """
    snapshot_dir = Path(snapshot_dir)
    if not snapshot_dir.exists():
        return []

    snapshots = []
    for f in sorted(snapshot_dir.glob(f"*{SNAPSHOT_SUFFIX}"), reverse=True):
        snapshots.append({
            "path": f,
            "name": f.name,
            "size_bytes": f.stat().st_size,
            "timestamp": f.stem.replace(SNAPSHOT_SUFFIX.replace(".zst", ""), ""),
        })
    return snapshots
