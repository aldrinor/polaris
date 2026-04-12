"""
Unit tests for wiki mesh compose + artifact directives (Unit 6).

Tests:
  - Claim hydration + bibliography building from scored claims
  - LLM-mocked answer composition with citation normalization
  - CoT scrubbing
  - [REF:N] → [N] normalization
  - Empty retrieval → graceful "no claims" message
  - FIX S7 artifact validation: missing claim_ids stripped
  - TABLE rendering: valid table, insufficient rows stripped
  - Deferred artifact types return stub messages
  - Payload parsing

Run:
    python -m pytest tests/unit/test_mesh_compose.py -v
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from src.polaris_graph.wiki.mesh import MeshStore
from src.polaris_graph.wiki.mesh.compose.artifact_directives import (
    ARTIFACT_PATTERN,
    _parse_payload,
    render_artifacts,
)
from src.polaris_graph.wiki.mesh.compose.composer import (
    ComposeResult,
    _format_bibliography,
    _format_claims,
    _hydrate_claims,
    _normalize_refs,
    _scrub_cot,
    compose_answer,
)
from src.polaris_graph.wiki.mesh.store import EMBEDDING_DIM


# ───── helpers ─────

def _ref_vec(dim: int = EMBEDDING_DIM) -> np.ndarray:
    arr = np.zeros(dim, dtype=np.float32)
    arr[0] = 1.0
    return arr


class _MockRetrievalResult:
    def __init__(self, scored_claims: list[tuple[str, float]]):
        self.scored_claims = scored_claims


class _MockComposeClient:
    def __init__(self, response: str):
        self._response = response
        self.calls = 0

    async def generate(self, *, prompt, system, max_tokens, timeout):
        self.calls += 1
        return self._response


# ───── fixtures ─────

@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "mesh_compose.db"


@pytest.fixture
def store(tmp_db: Path):
    s = MeshStore.open(tmp_db)
    yield s
    s.close()


@pytest.fixture
def workspace_id(store: MeshStore) -> str:
    return store.create_workspace(
        name="compose_test",
        root_question="Compose tests",
    )


@pytest.fixture
def source_a(store: MeshStore, workspace_id: str) -> str:
    return store.insert_source(
        workspace_id=workspace_id,
        kind="web",
        filepath="src_a.md",
        content_hash="a" * 64,
        sig_authority=0.5,
        url="https://example.com/source-a",
        title="Source A: PFAS Study",
        year=2023,
    )


@pytest.fixture
def source_b(store: MeshStore, workspace_id: str) -> str:
    return store.insert_source(
        workspace_id=workspace_id,
        kind="upload",
        filepath="src_b.md",
        content_hash="b" * 64,
        sig_authority=0.95,
        url="https://example.com/source-b",
        title="Source B: GAC Report",
        year=2024,
    )


@pytest.fixture
def two_claims(
    store: MeshStore, workspace_id: str, source_a: str, source_b: str,
) -> tuple[str, str]:
    clm_a = store.insert_claim(
        workspace_id=workspace_id,
        source_page_id=source_a,
        statement="GAC achieved 85% removal of PFOS in controlled trials",
        direct_quote="GAC achieved 85% removal of PFOS compounds",
        char_start=0, char_end=44,
        tier="GOLD", relevance_score=0.9,
        has_numeric=True,
        embedding=_ref_vec(),
    )
    clm_b = store.insert_claim(
        workspace_id=workspace_id,
        source_page_id=source_b,
        statement="Reverse osmosis removes 95% of PFAS at typical pressures",
        direct_quote="RO membranes remove 95% of PFAS contaminants",
        char_start=0, char_end=45,
        tier="GOLD", relevance_score=0.85,
        has_numeric=True,
        embedding=_ref_vec(),
    )
    return clm_a, clm_b


# ───── TestHelpers ─────

class TestScrubCoT:
    def test_removes_think_tags(self):
        text = "<think>Planning my answer...</think>The answer is 42."
        assert _scrub_cot(text) == "The answer is 42."

    def test_removes_reasoning_tags(self):
        text = "<reasoning>step 1, step 2</reasoning>Final result."
        assert _scrub_cot(text) == "Final result."

    def test_clean_text_unchanged(self):
        text = "A clean answer with [1] citations."
        assert _scrub_cot(text) == text


class TestNormalizeRefs:
    def test_ref_n_to_n(self):
        assert _normalize_refs("Result was 85% [REF:3].") == "Result was 85% [3]."

    def test_multiple_refs(self):
        assert _normalize_refs("[REF:1] and [REF:2]") == "[1] and [2]"

    def test_already_normalized(self):
        assert _normalize_refs("Text [1] here.") == "Text [1] here."


class TestFormatClaims:
    def test_basic_formatting(self):
        claims = [
            {"ref_num": 1, "statement": "Fact one", "direct_quote": "quote one"},
            {"ref_num": 2, "statement": "Fact two", "direct_quote": ""},
        ]
        out = _format_claims(claims)
        assert "[1] Fact one" in out
        assert "[2] Fact two" in out
        assert 'QUOTE: "quote one"' in out


class TestFormatBibliography:
    def test_basic_formatting(self):
        bib = [
            {"ref_num": 1, "title": "Study A", "url": "http://a.com", "year": 2023},
            {"ref_num": 2, "title": "Study B", "url": "http://b.com", "year": 2024},
        ]
        out = _format_bibliography(bib)
        assert "[1] Study A (2023)" in out
        assert "[2] Study B (2024)" in out


# ───── TestHydrateClaims ─────

class TestHydrateClaims:
    def test_hydrates_and_builds_bibliography(
        self, store, workspace_id, source_a, source_b, two_claims,
    ):
        clm_a, clm_b = two_claims
        scored = [(clm_a, 0.9), (clm_b, 0.85)]
        hydrated, bib = _hydrate_claims(store, scored)

        assert len(hydrated) == 2
        assert len(bib) == 2  # two different sources

        # First claim gets ref_num=1, second gets ref_num=2
        assert hydrated[0]["ref_num"] == 1
        assert hydrated[1]["ref_num"] == 2
        assert hydrated[0]["claim_id"] == clm_a

        # Bibliography entries
        assert bib[0]["title"] == "Source A: PFAS Study"
        assert bib[1]["title"] == "Source B: GAC Report"

    def test_same_source_gets_same_ref_num(
        self, store, workspace_id, source_a,
    ):
        clm_1 = store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_a,
            statement="Fact 1",
            direct_quote="q1",
            char_start=0, char_end=2,
            tier="GOLD", relevance_score=0.9,
            embedding=_ref_vec(),
        )
        clm_2 = store.insert_claim(
            workspace_id=workspace_id,
            source_page_id=source_a,
            statement="Fact 2",
            direct_quote="q2",
            char_start=0, char_end=2,
            tier="SILVER", relevance_score=0.8,
            embedding=_ref_vec(),
        )
        hydrated, bib = _hydrate_claims(store, [(clm_1, 0.9), (clm_2, 0.8)])
        assert hydrated[0]["ref_num"] == hydrated[1]["ref_num"]
        assert len(bib) == 1

    def test_missing_claim_skipped(self, store):
        hydrated, bib = _hydrate_claims(store, [("clm_missing", 0.5)])
        assert hydrated == []
        assert bib == []


# ───── TestComposeAnswer ─────

class TestComposeAnswer:
    @pytest.mark.asyncio
    async def test_end_to_end_with_mock_llm(
        self, store, workspace_id, two_claims,
    ):
        clm_a, clm_b = two_claims
        retrieval = _MockRetrievalResult([(clm_a, 0.9), (clm_b, 0.85)])

        client = _MockComposeClient(
            "GAC removes 85% of PFOS [1]. RO removes 95% [2]. "
            "Both are effective filtration methods."
        )

        result = await compose_answer(
            client,
            store,
            workspace_id=workspace_id,
            retrieval_result=retrieval,
            question_text="How do PFAS filters work?",
        )

        assert client.calls == 1
        assert "[1]" in result.answer_text
        assert "[2]" in result.answer_text
        assert len(result.bibliography) == 2
        assert len(result.claim_ids_used) == 2

    @pytest.mark.asyncio
    async def test_empty_retrieval_returns_no_claims_message(
        self, store, workspace_id,
    ):
        retrieval = _MockRetrievalResult([])
        client = _MockComposeClient("should not be called")

        result = await compose_answer(
            client,
            store,
            workspace_id=workspace_id,
            retrieval_result=retrieval,
            question_text="Anything",
        )

        assert client.calls == 0
        assert "No relevant claims" in result.answer_text
        assert result.bibliography == []

    @pytest.mark.asyncio
    async def test_cot_scrubbed_from_output(
        self, store, workspace_id, two_claims,
    ):
        clm_a, _ = two_claims
        retrieval = _MockRetrievalResult([(clm_a, 0.9)])

        client = _MockComposeClient(
            "<think>Let me plan...</think>"
            "GAC is effective [1]."
        )

        result = await compose_answer(
            client,
            store,
            workspace_id=workspace_id,
            retrieval_result=retrieval,
            question_text="test",
        )

        assert "<think>" not in result.answer_text
        assert "GAC is effective [1]." in result.answer_text

    @pytest.mark.asyncio
    async def test_ref_n_normalized(
        self, store, workspace_id, two_claims,
    ):
        clm_a, _ = two_claims
        retrieval = _MockRetrievalResult([(clm_a, 0.9)])

        client = _MockComposeClient("Result was 85% [REF:1].")

        result = await compose_answer(
            client,
            store,
            workspace_id=workspace_id,
            retrieval_result=retrieval,
            question_text="test",
        )

        assert "[REF:1]" not in result.answer_text
        assert "[1]" in result.answer_text


# ───── TestArtifactDirectives ─────

class TestParsePayload:
    def test_basic_claim_ids(self):
        p = _parse_payload("claim_ids=a,b,c")
        assert p["claim_ids"] == ["a", "b", "c"]

    def test_multiple_params(self):
        p = _parse_payload("claim_ids=a,b;x_label=Year;y_label=Removal %")
        assert p["claim_ids"] == ["a", "b"]
        assert p["x_label"] == "Year"

    def test_empty_string(self):
        assert _parse_payload("") == {}


class TestRenderArtifacts:
    def test_no_directives_unchanged(self):
        text = "Plain text with [1] citations."
        out, arts = render_artifacts(text, {})
        assert out == text
        assert arts == []

    def test_missing_claim_ids_stripped(self):
        text = "[TABLE:col1,col2]{claim_ids=clm_a,clm_b}"
        out, arts = render_artifacts(text, {})
        assert "stripped" in out.lower()
        assert "TABLE" in out

    def test_deferred_types_return_stub(self):
        claims = {"clm_a": {"statement": "test", "ref_num": 1}}
        for kind in ("CHART", "FLOW", "DECK", "FLASHCARDS"):
            text = f"[{kind}:spec]{{claim_ids=clm_a}}"
            out, _ = render_artifacts(text, claims)
            assert "deferred" in out.lower()

    def test_table_valid_renders_markdown(self):
        claims = {
            "clm_a": {
                "statement": "GAC removal was 85%",
                "direct_quote": "GAC removal efficiency",
                "ref_num": 1,
            },
            "clm_b": {
                "statement": "RO removal was 95%",
                "direct_quote": "RO removal rate",
                "ref_num": 2,
            },
        }
        text = "[TABLE:removal]{claim_ids=clm_a,clm_b}"
        out, _ = render_artifacts(text, claims)
        assert "|" in out  # markdown table
        assert "removal" in out.lower()

    def test_table_insufficient_rows_stripped(self):
        claims = {
            "clm_a": {
                "statement": "No matching data here",
                "direct_quote": "irrelevant content",
                "ref_num": 1,
            },
        }
        text = "[TABLE:specific_column]{claim_ids=clm_a}"
        out, _ = render_artifacts(text, claims)
        assert "stripped" in out.lower()

    def test_unknown_kind_stripped(self):
        claims = {"clm_a": {"statement": "test"}}
        text = "[UNKNOWN:spec]{claim_ids=clm_a}"
        # UNKNOWN doesn't match the regex pattern (only TABLE|CHART|FLOW|DECK|FLASHCARDS)
        out, _ = render_artifacts(text, claims)
        assert out == text  # unchanged — regex didn't match


class TestArtifactPattern:
    def test_pattern_matches_table(self):
        m = ARTIFACT_PATTERN.search("[TABLE:col1,col2]{claim_ids=a,b}")
        assert m is not None
        assert m.group(1) == "TABLE"
        assert m.group(2) == "col1,col2"

    def test_pattern_matches_chart(self):
        m = ARTIFACT_PATTERN.search("[CHART:line]{claim_ids=a;x_label=Year}")
        assert m is not None
        assert m.group(1) == "CHART"
