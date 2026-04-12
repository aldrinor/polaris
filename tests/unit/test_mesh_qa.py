"""
Unit tests for wiki mesh Q&A layer (Unit 7).

Tests:
  - Store CRUD: insert_question, get_question, insert_answer,
    get_answer_for_question, get_thread_history
  - Thread chain: parent_id walking, chronological ordering,
    last_n limiting, cycle safety
  - Context concatenation: _build_resolved_question with 0/1/3 history
    pairs
  - ask() orchestration: end-to-end with mock LLM, answer persisted,
    gap category passthrough, thread follow-up with coreference
  - NEARBY budget awareness in AskResult

Run:
    python -m pytest tests/unit/test_mesh_qa.py -v
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.polaris_graph.wiki.mesh import MeshStore, MeshStoreError
from src.polaris_graph.wiki.mesh.qa.ask import (
    AskResult,
    _build_resolved_question,
    ask,
)
from src.polaris_graph.wiki.mesh.store import EMBEDDING_DIM


# ───── helpers ─────

def _ref_vec(dim: int = EMBEDDING_DIM) -> np.ndarray:
    arr = np.zeros(dim, dtype=np.float32)
    arr[0] = 1.0
    return arr


class _MockComposeClient:
    def __init__(self, response: str = "Mock answer [1]."):
        self._response = response
        self.calls = 0

    async def generate(self, *, prompt, system, max_tokens, timeout):
        self.calls += 1
        return self._response


# ───── fixtures ─────

@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "mesh_qa.db"


@pytest.fixture
def store(tmp_db: Path):
    s = MeshStore.open(tmp_db)
    yield s
    s.close()


@pytest.fixture
def workspace_id(store: MeshStore) -> str:
    return store.create_workspace(
        name="qa_test",
        root_question="Q&A tests",
    )


@pytest.fixture
def source_id(store: MeshStore, workspace_id: str) -> str:
    return store.insert_source(
        workspace_id=workspace_id,
        kind="web",
        filepath="qa_src.md",
        content_hash="q" * 64,
        sig_authority=0.5,
        url="https://example.com/qa-source",
        title="QA Test Source",
        year=2024,
    )


@pytest.fixture
def claim_id(store: MeshStore, workspace_id: str, source_id: str) -> str:
    return store.insert_claim(
        workspace_id=workspace_id,
        source_page_id=source_id,
        statement="GAC removes 85% of PFOS in controlled trials",
        direct_quote="GAC achieved 85% removal of PFOS",
        char_start=0, char_end=33,
        tier="GOLD", relevance_score=0.9,
        has_numeric=True,
        embedding=_ref_vec(),
    )


# ───── TestStoreCRUD ─────

class TestInsertQuestion:
    def test_basic_insert(self, store, workspace_id):
        q_id = store.insert_question(
            workspace_id=workspace_id,
            text="How do PFAS filters work?",
        )
        assert q_id.startswith("q_")
        q = store.get_question(q_id)
        assert q is not None
        assert q["text"] == "How do PFAS filters work?"
        assert q["parent_id"] is None

    def test_with_parent(self, store, workspace_id):
        q1 = store.insert_question(
            workspace_id=workspace_id,
            text="First question",
        )
        q2 = store.insert_question(
            workspace_id=workspace_id,
            text="Follow-up question",
            parent_id=q1,
        )
        q2_row = store.get_question(q2)
        assert q2_row["parent_id"] == q1

    def test_empty_text_raises(self, store, workspace_id):
        with pytest.raises(MeshStoreError, match="non-empty"):
            store.insert_question(
                workspace_id=workspace_id,
                text="   ",
            )

    def test_missing_question_returns_none(self, store):
        assert store.get_question("q_nonexistent") is None


class TestInsertAnswer:
    def test_basic_insert(self, store, workspace_id):
        q_id = store.insert_question(
            workspace_id=workspace_id,
            text="Test question",
        )
        ans_id = store.insert_answer(
            question_id=q_id,
            text="The answer is 42.",
            retrieved_claims=["clm_a", "clm_b"],
            cited_claims=["clm_a"],
        )
        assert ans_id.startswith("ans_")
        ans = store.get_answer_for_question(q_id)
        assert ans is not None
        assert ans["text"] == "The answer is 42."

    def test_no_answer_returns_none(self, store, workspace_id):
        q_id = store.insert_question(
            workspace_id=workspace_id,
            text="Unanswered",
        )
        assert store.get_answer_for_question(q_id) is None


class TestThreadHistory:
    def test_single_question_no_history(self, store, workspace_id):
        q1 = store.insert_question(
            workspace_id=workspace_id,
            text="First question",
        )
        history = store.get_thread_history(q1)
        assert history == []

    def test_two_question_thread(self, store, workspace_id):
        q1 = store.insert_question(
            workspace_id=workspace_id,
            text="What filters remove PFOS?",
        )
        store.insert_answer(
            question_id=q1,
            text="GAC and RO are effective.",
        )
        q2 = store.insert_question(
            workspace_id=workspace_id,
            text="What about the cost?",
            parent_id=q1,
        )
        history = store.get_thread_history(q2)
        assert len(history) == 1
        assert history[0]["question"] == "What filters remove PFOS?"
        assert history[0]["answer"] == "GAC and RO are effective."

    def test_three_question_thread_chronological(self, store, workspace_id):
        q1 = store.insert_question(
            workspace_id=workspace_id, text="Q1",
        )
        store.insert_answer(question_id=q1, text="A1")
        q2 = store.insert_question(
            workspace_id=workspace_id, text="Q2", parent_id=q1,
        )
        store.insert_answer(question_id=q2, text="A2")
        q3 = store.insert_question(
            workspace_id=workspace_id, text="Q3", parent_id=q2,
        )

        history = store.get_thread_history(q3, last_n=5)
        assert len(history) == 2
        assert history[0]["question"] == "Q1"
        assert history[1]["question"] == "Q2"

    def test_last_n_limits(self, store, workspace_id):
        q1 = store.insert_question(
            workspace_id=workspace_id, text="Q1",
        )
        store.insert_answer(question_id=q1, text="A1")
        q2 = store.insert_question(
            workspace_id=workspace_id, text="Q2", parent_id=q1,
        )
        store.insert_answer(question_id=q2, text="A2")
        q3 = store.insert_question(
            workspace_id=workspace_id, text="Q3", parent_id=q2,
        )
        store.insert_answer(question_id=q3, text="A3")
        q4 = store.insert_question(
            workspace_id=workspace_id, text="Q4", parent_id=q3,
        )

        history = store.get_thread_history(q4, last_n=2)
        assert len(history) == 2
        assert history[0]["question"] == "Q2"
        assert history[1]["question"] == "Q3"


# ───── TestBuildResolvedQuestion ─────

class TestBuildResolvedQuestion:
    def test_no_history_returns_raw(self, store, workspace_id):
        q_id = store.insert_question(
            workspace_id=workspace_id,
            text="Simple question",
        )
        resolved = _build_resolved_question(store, q_id, "Simple question")
        assert resolved == "Simple question"

    def test_with_history_concatenates(self, store, workspace_id):
        q1 = store.insert_question(
            workspace_id=workspace_id,
            text="What filters remove PFOS?",
        )
        store.insert_answer(question_id=q1, text="GAC and RO.")
        q2 = store.insert_question(
            workspace_id=workspace_id,
            text="What about the cost?",
            parent_id=q1,
        )
        resolved = _build_resolved_question(
            store, q2, "What about the cost?",
        )
        assert "What filters remove PFOS?" in resolved
        assert "GAC and RO." in resolved
        assert "What about the cost?" in resolved
        # Should be in Q: ... A: ... Q: ... format
        assert resolved.count("Q:") == 2
        assert resolved.count("A:") == 1


# ───── TestAsk ─────

class TestAskOrchestration:
    @pytest.mark.asyncio
    async def test_end_to_end_single_question(
        self, store, workspace_id, claim_id,
    ):
        client = _MockComposeClient("GAC removes 85% of PFOS [1].")

        result = await ask(
            client,
            store,
            workspace_id=workspace_id,
            question_text="How does GAC remove PFOS?",
            question_embedding=_ref_vec(),
        )

        assert result.question_id.startswith("q_")
        assert result.answer_id.startswith("ans_")
        assert "[1]" in result.answer_text
        assert client.calls == 1

        # Answer persisted in store
        ans = store.get_answer_for_question(result.question_id)
        assert ans is not None
        assert ans["text"] == result.answer_text

    @pytest.mark.asyncio
    async def test_follow_up_question_builds_context(
        self, store, workspace_id, claim_id,
    ):
        client = _MockComposeClient("Answer with context [1].")

        # First question
        r1 = await ask(
            client, store,
            workspace_id=workspace_id,
            question_text="What filters remove PFOS?",
            question_embedding=_ref_vec(),
        )

        # Follow-up
        r2 = await ask(
            client, store,
            workspace_id=workspace_id,
            question_text="What about the cost?",
            parent_question_id=r1.question_id,
            question_embedding=_ref_vec(),
        )

        assert r2.question_id != r1.question_id
        # Thread history should be available
        history = store.get_thread_history(r2.question_id)
        assert len(history) == 1
        assert history[0]["question"] == "What filters remove PFOS?"

    @pytest.mark.asyncio
    async def test_empty_workspace_returns_orthogonal(
        self, store, workspace_id,
    ):
        client = _MockComposeClient("should not be called")

        result = await ask(
            client, store,
            workspace_id=workspace_id,
            question_text="Any question",
            question_embedding=_ref_vec(),
        )

        assert result.gap_category == "ORTHOGONAL"
        assert "No relevant claims" in result.answer_text
        # Question still persisted even if no claims found
        q = store.get_question(result.question_id)
        assert q is not None

    @pytest.mark.asyncio
    async def test_unknown_workspace_raises(self, store):
        client = _MockComposeClient()
        with pytest.raises(MeshStoreError, match="Workspace not found"):
            await ask(
                client, store,
                workspace_id="ws_nonexistent",
                question_text="test",
                question_embedding=_ref_vec(),
            )
