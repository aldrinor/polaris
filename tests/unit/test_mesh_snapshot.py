"""
Unit tests for mesh snapshot create/restore/list (Unit 10).

Run:
    python -m pytest tests/unit/test_mesh_snapshot.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.wiki.mesh import MeshStore
from src.polaris_graph.wiki.mesh.snapshot import (
    SNAPSHOT_SUFFIX,
    create_snapshot,
    list_snapshots,
    restore_snapshot,
)


@pytest.fixture
def db_with_data(tmp_path: Path) -> Path:
    db_path = tmp_path / "mesh.db"
    store = MeshStore.open(db_path)
    ws_id = store.create_workspace(name="Snapshot Test")
    store.insert_source(
        workspace_id=ws_id,
        kind="web",
        filepath="snap.md",
        content_hash="s" * 64,
        sig_authority=0.5,
    )
    store.close()
    return db_path


@pytest.fixture
def snapshot_dir(tmp_path: Path) -> Path:
    d = tmp_path / "snapshots"
    d.mkdir()
    return d


class TestCreateSnapshot:
    def test_creates_compressed_file(self, db_with_data, snapshot_dir):
        path = create_snapshot(db_with_data, snapshot_dir)
        assert path.exists()
        assert path.name.endswith(SNAPSHOT_SUFFIX)
        assert path.stat().st_size > 0
        # Compressed should be smaller than original
        assert path.stat().st_size < db_with_data.stat().st_size

    def test_missing_db_raises(self, tmp_path, snapshot_dir):
        with pytest.raises(FileNotFoundError):
            create_snapshot(tmp_path / "nonexistent.db", snapshot_dir)

    def test_creates_snapshot_dir_if_missing(self, db_with_data, tmp_path):
        new_dir = tmp_path / "new_snapshots"
        path = create_snapshot(db_with_data, new_dir)
        assert path.exists()
        assert new_dir.exists()


class TestRestoreSnapshot:
    def test_roundtrip_preserves_data(self, db_with_data, snapshot_dir, tmp_path):
        snap_path = create_snapshot(db_with_data, snapshot_dir)

        # Restore to a new location
        restored_db = tmp_path / "restored.db"
        restore_snapshot(snap_path, restored_db)

        # Verify data survived
        store = MeshStore.open(restored_db)
        rows = store._conn.execute("SELECT name FROM workspaces").fetchall()
        assert len(rows) == 1
        assert rows[0]["name"] == "Snapshot Test"
        src_count = store._conn.execute(
            "SELECT COUNT(*) AS c FROM source_pages"
        ).fetchone()["c"]
        assert src_count == 1
        store.close()

    def test_missing_snapshot_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            restore_snapshot(tmp_path / "no.mesh.zst", tmp_path / "db")


class TestListSnapshots:
    def test_empty_dir(self, snapshot_dir):
        assert list_snapshots(snapshot_dir) == []

    def test_lists_created_snapshots(self, db_with_data, snapshot_dir):
        create_snapshot(db_with_data, snapshot_dir)
        create_snapshot(db_with_data, snapshot_dir)
        snaps = list_snapshots(snapshot_dir)
        # May be 1 or 2 depending on timestamp resolution
        assert len(snaps) >= 1
        assert all(s["name"].endswith(SNAPSHOT_SUFFIX) for s in snaps)
        assert all(s["size_bytes"] > 0 for s in snaps)

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        assert list_snapshots(tmp_path / "nope") == []
