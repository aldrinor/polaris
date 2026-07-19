"""
Integration test — mesh golden path end-to-end (Unit 10).

Exercises the ENTIRE vertical slice with a mock LLM but REAL embeddings:
  create workspace → ingest file → extract claims (mock LLM) →
  canonicalize entities → discover edges → retrieve_claims →
  compose_answer (mock LLM) → ask() with thread follow-up →
  verify everything persisted

This test proves the units work TOGETHER, not just individually.
It does NOT duplicate the 273 unit tests — it covers the seams.

Run:
    python -m pytest tests/integration/test_mesh_e2e.py -v
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from src.polaris_graph.schemas import SourceAnalysisBatch
from src.polaris_graph.wiki.mesh import MeshStore
from src.polaris_graph.wiki.mesh.claim_extract import extract_claims_from_source
from src.polaris_graph.wiki.mesh.edge_discovery import discover_edges_for_claims
from src.polaris_graph.wiki.mesh.ingest import ingest_file
from src.polaris_graph.wiki.mesh.qa.ask import ask
from src.polaris_graph.wiki.mesh.retrieve.lethal import retrieve_claims
from src.polaris_graph.wiki.mesh.snapshot import (
    create_snapshot,
    list_snapshots,
    restore_snapshot,
)
from src.polaris_graph.wiki.mesh.store import EMBEDDING_DIM


# ───── test content ─────

BODY_A = (
    "This study evaluates granular activated carbon filtration for PFOS "
    "removal in residential water treatment systems. GAC achieved 85% "
    "removal of PFOS compounds across independent trials at typical "
    "residential concentrations over twelve months of continuous operation. "
    "The contact time was standardized at ten minutes per treatment cycle "
    "to ensure consistent filtration performance across all test sites."
)

BODY_B = (
    "Reverse osmosis membrane technology demonstrates superior PFAS "
    "removal performance compared to granular activated carbon methods. "
    "RO membranes achieved 95% removal efficiency at standard operating "
    "pressures in controlled laboratory conditions with a sample size "
    "of forty-two independent measurements over six months of testing."
)


# ───── mock LLM ─────

class _MockLLMClient:
    """Returns predetermined extraction + composition results."""

    def __init__(self):
        self.extract_calls = 0
        self.compose_calls = 0

    async def generate_structured(
        self, *, prompt, schema, system, max_tokens, timeout,
        reasoning_enabled=False,
    ):
        self.extract_calls += 1
        url = "https://example.com/source-a"
        if "source-b" in prompt.lower() or "reverse osmosis" in prompt.lower():
            url = "https://example.com/source-b"

        return SourceAnalysisBatch.model_validate({
            "analyses": [{
                "source_url": url,
                "source_title": "Test Study",
                "source_type": "journal_article",
                "source_quality": 0.8,
                "overall_relevance": 0.85,
                "atomic_facts": [
                    {
                        "statement": "GAC achieved 85% removal of PFOS compounds across independent trials at residential concentrations over twelve months"
                            if "source-a" in url else
                            "RO membranes achieved 95% removal efficiency at standard operating pressures in controlled laboratory conditions over six months",
                        "direct_quote": "GAC achieved 85% removal of PFOS compounds across independent trials at typical residential concentrations over twelve months of continuous operation"
                            if "source-a" in url else
                            "RO membranes achieved 95% removal efficiency at standard operating pressures in controlled laboratory conditions with a sample size of forty-two independent measurements",
                        "relevance_score": 0.9,
                        "confidence": 0.9,
                        "entities": ["GAC", "PFOS"] if "source-a" in url else ["RO", "PFAS"],
                    },
                ],
            }],
        })

    async def generate(self, *, prompt, system, max_tokens, timeout):
        self.compose_calls += 1
        return (
            "GAC removes 85% of PFOS [1] while RO achieves 95% PFAS "
            "removal [2]. Both methods are effective for residential "
            "water treatment."
        )


# ───── golden path test ─────

class TestMeshGoldenPath:

    @pytest.mark.asyncio
    async def test_full_pipeline_end_to_end(self, tmp_path: Path):
        """
        The golden path: workspace → ingest → extract → entities →
        edges → retrieve → compose → Q&A thread → verify persistence.
        """
        db_path = tmp_path / "golden.db"
        store = MeshStore.open(db_path)
        client = _MockLLMClient()

        try:
            # ── Step 1: create workspace ──
            ws_id = store.create_workspace(
                name="Golden Path Test",
                root_question="How do PFAS filters work?",
            )

            # ── Step 2: ingest two source files ──
            file_a = tmp_path / "source_a.md"
            file_a.write_text(BODY_A, encoding="utf-8")
            file_b = tmp_path / "source_b.md"
            file_b.write_text(BODY_B, encoding="utf-8")

            src_a, new_a = ingest_file(
                store=store, workspace_id=ws_id,
                file_path=file_a, kind="upload",
                url="https://example.com/source-a",
            )
            src_b, new_b = ingest_file(
                store=store, workspace_id=ws_id,
                file_path=file_b, kind="web",
                url="https://example.com/source-b",
            )
            assert new_a is True
            assert new_b is True

            # ── Step 3: extract claims (mock LLM, real embeddings) ──
            result_a = await extract_claims_from_source(
                client=client, store=store,
                workspace_id=ws_id,
                source_page_id=src_a,
                query="How do PFAS filters work?",
            )
            result_b = await extract_claims_from_source(
                client=client, store=store,
                workspace_id=ws_id,
                source_page_id=src_b,
                query="How do PFAS filters work?",
            )
            assert len(result_a.inserted_claim_ids) >= 1
            assert len(result_b.inserted_claim_ids) >= 1
            all_claim_ids = result_a.inserted_claim_ids + result_b.inserted_claim_ids

            # ── Step 4: verify entities were canonicalized ──
            entities = store._conn.execute(
                "SELECT canonical_name, entity_type FROM entities "
                "WHERE workspace_id = ?",
                (ws_id,),
            ).fetchall()
            entity_names = {e["canonical_name"] for e in entities}
            assert "GAC" in entity_names or "PFOS" in entity_names

            # ── Step 5: discover edges ──
            edge_result = discover_edges_for_claims(
                store, workspace_id=ws_id,
                new_claim_ids=all_claim_ids,
            )
            # Two claims about PFAS filtration should have some cosine overlap
            # (may or may not hit the 0.85 threshold depending on embedding model)

            # ── Step 6: lethal retrieve ──
            retrieval = retrieve_claims(
                store, workspace_id=ws_id,
                question_text="How does GAC remove PFOS?",
            )
            assert len(retrieval.scored_claims) >= 1
            assert retrieval.gap_category != "ORTHOGONAL"

            # ── Step 7: ask (compose + persist) ──
            ask_result = await ask(
                client, store,
                workspace_id=ws_id,
                question_text="How do PFAS filters work?",
            )
            assert ask_result.question_id.startswith("q_")
            assert ask_result.answer_id.startswith("ans_")
            assert len(ask_result.answer_text) > 0
            assert client.compose_calls == 1

            # ── Step 8: thread follow-up ──
            followup = await ask(
                client, store,
                workspace_id=ws_id,
                question_text="What about the cost?",
                parent_question_id=ask_result.question_id,
            )
            assert followup.question_id != ask_result.question_id

            # Thread history available
            history = store.get_thread_history(followup.question_id)
            assert len(history) == 1
            assert "PFAS filters" in history[0]["question"]

            # ── Step 9: verify persistence ──
            ws = store.get_workspace(ws_id)
            assert ws["source_count"] == 2
            assert ws["claim_count"] >= 2

            # Answers persisted
            ans = store.get_answer_for_question(ask_result.question_id)
            assert ans is not None
            assert len(ans["text"]) > 0

            # Stats work
            stats = store.workspace_stats(ws_id)
            assert stats["source_count"] == 2
            assert stats["gold_claims"] >= 1

        finally:
            store.close()


class TestSnapshotRoundtrip:

    def test_snapshot_preserves_full_mesh(self, tmp_path: Path):
        """Snapshot → modify → restore → original state."""
        db_path = tmp_path / "snap_test.db"
        snap_dir = tmp_path / "snapshots"
        store = MeshStore.open(db_path)

        ws_id = store.create_workspace(name="Snap Test WS")
        src_id = store.insert_source(
            workspace_id=ws_id,
            kind="web", filepath="s.md",
            content_hash="z" * 64, sig_authority=0.5,
        )
        store.close()

        # Create snapshot
        snap_path = create_snapshot(db_path, snap_dir)
        assert snap_path.exists()

        # Destructive modification
        store = MeshStore.open(db_path)
        store._conn.execute("DELETE FROM source_pages")
        count = store._conn.execute(
            "SELECT COUNT(*) AS c FROM source_pages"
        ).fetchone()["c"]
        assert count == 0
        store.close()

        # Restore
        restore_snapshot(snap_path, db_path)

        # Verify original state
        store = MeshStore.open(db_path)
        count = store._conn.execute(
            "SELECT COUNT(*) AS c FROM source_pages"
        ).fetchone()["c"]
        assert count == 1
        ws = store.get_workspace(ws_id)
        assert ws["name"] == "Snap Test WS"
        store.close()

        # List snapshots
        snaps = list_snapshots(snap_dir)
        assert len(snaps) >= 1
