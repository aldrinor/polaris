"""
Unit tests for wiki mesh CLI (Unit 8).

Tests the CLI command handlers directly (not via subprocess) to verify
argument parsing, store interaction, and output formatting.

Strategy:
  - Call `main(argv=[...])` with explicit arguments.
  - Redirect stdout via capsys to verify output.
  - Use a temporary mesh.db for each test.
  - Skip LLM-dependent commands (ask without --dry-run) — those
    require OpenRouterClient which is not available in tests.
  - Test --dry-run ask path which exercises retrieval without LLM.

Run:
    python -m pytest tests/unit/test_mesh_cli.py -v
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.polaris_graph.wiki.mesh import MeshStore
from src.polaris_graph.wiki.mesh.cli.main import main
from src.polaris_graph.wiki.mesh.store import EMBEDDING_DIM


# ───── helpers ─────

def _ref_vec(dim: int = EMBEDDING_DIM) -> np.ndarray:
    arr = np.zeros(dim, dtype=np.float32)
    arr[0] = 1.0
    return arr


# ───── fixtures ─────

@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "test_cli.db")


@pytest.fixture
def seeded_db(db_path: str) -> str:
    """Create a db with one workspace + one source + one claim."""
    store = MeshStore.open(Path(db_path))
    ws_id = store.create_workspace(
        name="CLI Test Workspace",
        root_question="How do PFAS filters work?",
    )
    src_id = store.insert_source(
        workspace_id=ws_id,
        kind="web",
        filepath="cli_test.md",
        content_hash="c" * 64,
        sig_authority=0.5,
        url="https://example.com/cli-test",
        title="CLI Test Source",
        year=2024,
    )
    store.insert_claim(
        workspace_id=ws_id,
        source_page_id=src_id,
        statement="GAC removes 85% of PFOS in controlled trials",
        direct_quote="GAC achieved 85% removal of PFOS",
        char_start=0, char_end=33,
        tier="GOLD", relevance_score=0.9,
        has_numeric=True,
        embedding=_ref_vec(),
    )
    store.close()
    return db_path


@pytest.fixture
def ws_id(seeded_db: str) -> str:
    store = MeshStore.open(Path(seeded_db))
    rows = store._conn.execute("SELECT id FROM workspaces LIMIT 1").fetchall()
    ws = rows[0]["id"]
    store.close()
    return ws


# ───── TestWorkspaceCommands ─────

class TestWorkspaceCreate:
    def test_creates_workspace(self, db_path, capsys):
        code = main(["--db", db_path, "workspace-create", "Test WS"])
        assert code == 0
        out = capsys.readouterr().out
        assert "Created workspace" in out
        assert "Test WS" in out

    def test_with_seed_question(self, db_path, capsys):
        code = main([
            "--db", db_path,
            "workspace-create", "PFAS Research",
            "--seed", "How do filters remove PFAS?",
        ])
        assert code == 0
        out = capsys.readouterr().out
        assert "Seed question" in out


class TestWorkspaceList:
    def test_empty_db(self, db_path, capsys):
        # Create the db first (MeshStore.open initializes schema)
        store = MeshStore.open(Path(db_path))
        store.close()
        code = main(["--db", db_path, "workspace-list"])
        assert code == 0
        out = capsys.readouterr().out
        assert "No workspaces" in out

    def test_lists_existing(self, seeded_db, capsys):
        code = main(["--db", seeded_db, "workspace-list"])
        assert code == 0
        out = capsys.readouterr().out
        assert "CLI Test Workspace" in out
        assert "Sources:" in out


# ───── TestAskCommand ─────

class TestAskDryRun:
    def test_dry_run_shows_retrieval(self, seeded_db, ws_id, capsys):
        code = main([
            "--db", seeded_db,
            "ask", "How does GAC remove PFOS?",
            "--workspace", ws_id,
            "--dry-run",
        ])
        assert code == 0
        out = capsys.readouterr().out
        assert "Gap:" in out
        assert "Total claims:" in out

    def test_dry_run_empty_workspace(self, db_path, capsys):
        store = MeshStore.open(Path(db_path))
        ws_id = store.create_workspace(name="Empty WS")
        store.close()
        code = main([
            "--db", db_path,
            "ask", "Any question",
            "--workspace", ws_id,
            "--dry-run",
        ])
        assert code == 0
        out = capsys.readouterr().out
        assert "Total claims: 0" in out


# ───── TestStatsCommand ─────

class TestStats:
    def test_shows_workspace_stats(self, seeded_db, ws_id, capsys):
        code = main(["--db", seeded_db, "stats", "--workspace", ws_id])
        assert code == 0
        out = capsys.readouterr().out
        assert "CLI Test Workspace" in out
        assert "GOLD:" in out
        assert "Sources:" in out


# ───── TestEntitiesReview ─────

class TestEntitiesReview:
    def test_no_quarantined(self, seeded_db, ws_id, capsys):
        code = main([
            "--db", seeded_db,
            "entities-review", "--workspace", ws_id,
        ])
        assert code == 0
        out = capsys.readouterr().out
        assert "No quarantined" in out

    def test_shows_quarantined(self, seeded_db, ws_id, capsys):
        store = MeshStore.open(Path(seeded_db))
        store.insert_entity(
            workspace_id=ws_id,
            canonical_name="PFOS",
            entity_type="compound",
            aliases=["pfos", "perfluorooctane sulfonate"],
            confidence=0.5,
            user_confirmed=False,
            embedding=_ref_vec(),
        )
        store.close()
        code = main([
            "--db", seeded_db,
            "entities-review", "--workspace", ws_id,
        ])
        assert code == 0
        out = capsys.readouterr().out
        assert "PFOS" in out
        assert "compound" in out
        assert "quarantined" in out.lower()


# ───── TestErrorHandling ─────

class TestErrorHandling:
    def test_no_command_prints_help(self, db_path, capsys):
        code = main(["--db", db_path])
        assert code == 1

    def test_invalid_workspace_shows_error(self, seeded_db, capsys):
        code = main([
            "--db", seeded_db,
            "stats", "--workspace", "ws_nonexistent",
        ])
        assert code == 1
        err = capsys.readouterr().err
        assert "Error" in err
