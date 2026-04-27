"""Tests for src/polaris_graph/audit_ir/corpus_brief.py (M-12)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.polaris_graph.audit_ir.corpus_brief import (
    BriefCitation,
    BriefParagraph,
    CorpusBrief,
    LlmClient,
    brief_to_dict,
    compose_brief,
)
from src.polaris_graph.audit_ir.corpus_retriever import RetrievedChunk
from src.polaris_graph.audit_ir.provenance import TextSpan, to_dict
from src.polaris_graph.audit_ir.workspace_store import WorkspaceStore


class FakeLlm:
    """Minimal LlmClient for tests. Returns whatever the test set."""

    def __init__(self, paragraphs: list[dict[str, Any]] | None = None,
                 raise_with: Exception | None = None) -> None:
        self._paragraphs = paragraphs or []
        self._raise = raise_with
        self.calls: list[tuple[str, list[RetrievedChunk]]] = []

    def draft_brief(
        self, question: str, chunks: list[RetrievedChunk]
    ) -> list[dict[str, Any]]:
        self.calls.append((question, chunks))
        if self._raise:
            raise self._raise
        return self._paragraphs


@pytest.fixture
def populated_store(tmp_path: Path) -> tuple[WorkspaceStore, str]:
    store = WorkspaceStore(tmp_path / "ws.sqlite")
    ws = store.create_workspace("Brief", max_docs=10)
    up = store.upload_file(
        ws.workspace_id, "diabetes.txt", "text/plain", 100, "/p/d",
    )
    store.transition_parser_status(up.upload_id, "parsing")
    store.insert_chunks(up.upload_id, [
        ("Tirzepatide for type 2 diabetes shows efficacy in trials.",
         to_dict(TextSpan(up.upload_id, 0, 60))),
        ("Adverse events for tirzepatide include nausea and reduced appetite.",
         to_dict(TextSpan(up.upload_id, 60, 130))),
    ])
    store.transition_parser_status(up.upload_id, "parsed")
    return store, ws.workspace_id


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_compose_brief_with_supported_paragraphs(populated_store) -> None:
    store, ws_id = populated_store
    # Pre-fetch chunks so we know valid chunk_ids.
    from src.polaris_graph.audit_ir.corpus_retriever import retrieve_chunks
    chunks = retrieve_chunks(store, ws_id, "tirzepatide diabetes efficacy")
    assert chunks, "fixture must produce retrievable chunks"
    cid = chunks[0].chunk_id

    llm = FakeLlm(paragraphs=[
        {
            "claim": "Tirzepatide is effective for type 2 diabetes.",
            "citations": [{"chunk_id": cid}],
        },
    ])
    brief = compose_brief(
        store=store, workspace_id=ws_id,
        question="tirzepatide diabetes efficacy", llm=llm,
    )
    assert isinstance(brief, CorpusBrief)
    assert len(brief.paragraphs) == 1
    p = brief.paragraphs[0]
    assert p.support_status == "supported"
    assert p.claim
    assert len(p.citations) == 1
    assert p.citations[0].chunk_id == cid
    assert p.citations[0].provenance["kind"] == "text_span"


# ---------------------------------------------------------------------------
# Insufficient-support semantics (per LAW II)
# ---------------------------------------------------------------------------


def test_compose_brief_no_retrieval_yields_insufficient_support(populated_store) -> None:
    """No chunks pass the floor → single insufficient_support
    paragraph. Per FINAL_PLAN: 'every paragraph cited or
    insufficient support'."""
    store, ws_id = populated_store
    llm = FakeLlm()  # never called
    brief = compose_brief(
        store=store, workspace_id=ws_id,
        question="blockchain governance crypto", llm=llm,
    )
    assert len(brief.paragraphs) == 1
    p = brief.paragraphs[0]
    assert p.support_status == "insufficient_support"
    assert p.citations == ()
    assert "insufficient" in p.claim.lower()
    assert llm.calls == [], "LLM must not be called when retrieval is empty"


def test_compose_brief_drops_paragraphs_with_unknown_chunk_ids(populated_store) -> None:
    """LAW II: a paragraph that cites a chunk_id NOT in the
    retrieved set is dropped — never leak fabricated citations."""
    store, ws_id = populated_store
    llm = FakeLlm(paragraphs=[
        {
            "claim": "Made-up claim citing nonexistent chunk.",
            "citations": [{"chunk_id": "ck_does_not_exist"}],
        },
    ])
    brief = compose_brief(
        store=store, workspace_id=ws_id,
        question="tirzepatide diabetes efficacy", llm=llm,
    )
    # All paragraphs dropped → insufficient_support fallback.
    assert len(brief.paragraphs) == 1
    assert brief.paragraphs[0].support_status == "insufficient_support"
    assert "drafted claims could" in brief.paragraphs[0].claim


def test_compose_brief_strips_invalid_citations_but_keeps_valid_paragraph(
    populated_store,
) -> None:
    """If a paragraph has a mix of valid + invalid chunk_ids, keep
    the paragraph with only the valid citations."""
    store, ws_id = populated_store
    from src.polaris_graph.audit_ir.corpus_retriever import retrieve_chunks
    chunks = retrieve_chunks(store, ws_id, "tirzepatide diabetes")
    assert chunks
    cid = chunks[0].chunk_id

    llm = FakeLlm(paragraphs=[
        {
            "claim": "Tirzepatide efficacy in type 2 diabetes.",
            "citations": [
                {"chunk_id": cid},
                {"chunk_id": "ck_fabricated"},
            ],
        },
    ])
    brief = compose_brief(
        store=store, workspace_id=ws_id,
        question="tirzepatide diabetes", llm=llm,
    )
    assert len(brief.paragraphs) == 1
    assert brief.paragraphs[0].support_status == "supported"
    assert len(brief.paragraphs[0].citations) == 1
    assert brief.paragraphs[0].citations[0].chunk_id == cid


def test_compose_brief_drops_paragraphs_with_no_citations(populated_store) -> None:
    """A paragraph with empty citations array must NOT appear in the
    brief — every supported paragraph requires ≥1 citation."""
    store, ws_id = populated_store
    llm = FakeLlm(paragraphs=[
        {"claim": "Uncited claim about diabetes.", "citations": []},
    ])
    brief = compose_brief(
        store=store, workspace_id=ws_id,
        question="tirzepatide diabetes", llm=llm,
    )
    assert len(brief.paragraphs) == 1
    assert brief.paragraphs[0].support_status == "insufficient_support"


def test_compose_brief_drops_paragraphs_with_empty_claim(populated_store) -> None:
    """Empty / whitespace-only claims are silently dropped."""
    store, ws_id = populated_store
    from src.polaris_graph.audit_ir.corpus_retriever import retrieve_chunks
    chunks = retrieve_chunks(store, ws_id, "tirzepatide diabetes")
    cid = chunks[0].chunk_id
    llm = FakeLlm(paragraphs=[
        {"claim": "", "citations": [{"chunk_id": cid}]},
        {"claim": "   ", "citations": [{"chunk_id": cid}]},
        {"claim": "Real claim.", "citations": [{"chunk_id": cid}]},
    ])
    brief = compose_brief(
        store=store, workspace_id=ws_id,
        question="tirzepatide diabetes", llm=llm,
    )
    assert len(brief.paragraphs) == 1
    assert brief.paragraphs[0].claim == "Real claim."


# ---------------------------------------------------------------------------
# LLM error propagation (LAW II — no silent fallbacks)
# ---------------------------------------------------------------------------


def test_compose_brief_propagates_llm_errors(populated_store) -> None:
    """A failing LLM call must propagate, not silently fall back to
    insufficient_support."""
    store, ws_id = populated_store
    llm = FakeLlm(raise_with=RuntimeError("LLM timeout"))
    with pytest.raises(RuntimeError, match="LLM timeout"):
        compose_brief(
            store=store, workspace_id=ws_id,
            question="tirzepatide diabetes", llm=llm,
        )


# ---------------------------------------------------------------------------
# Workspace boundary
# ---------------------------------------------------------------------------


def test_compose_brief_unknown_workspace_raises(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "ws.sqlite")
    llm = FakeLlm()
    with pytest.raises(ValueError, match="unknown workspace"):
        compose_brief(
            store=store, workspace_id="ws_no", question="x", llm=llm,
        )


# ---------------------------------------------------------------------------
# Malformed LLM responses
# ---------------------------------------------------------------------------


def test_compose_brief_handles_malformed_paragraph_dicts(populated_store) -> None:
    """Non-dict items in paragraph list are skipped; non-list
    citations are skipped; non-dict citations are skipped."""
    store, ws_id = populated_store
    from src.polaris_graph.audit_ir.corpus_retriever import retrieve_chunks
    chunks = retrieve_chunks(store, ws_id, "tirzepatide diabetes")
    cid = chunks[0].chunk_id
    llm = FakeLlm(paragraphs=[
        "garbage string",
        None,
        {"claim": "Bad citations", "citations": "not a list"},
        {"claim": "Good claim", "citations": [
            "string citation",
            None,
            {"chunk_id": cid},
        ]},
    ])
    brief = compose_brief(
        store=store, workspace_id=ws_id,
        question="tirzepatide diabetes", llm=llm,
    )
    assert len(brief.paragraphs) == 1
    assert brief.paragraphs[0].claim == "Good claim"


def test_compose_brief_dedupes_citations(populated_store) -> None:
    """If the LLM cites the same chunk_id twice in one paragraph,
    keep only one."""
    store, ws_id = populated_store
    from src.polaris_graph.audit_ir.corpus_retriever import retrieve_chunks
    chunks = retrieve_chunks(store, ws_id, "tirzepatide diabetes")
    cid = chunks[0].chunk_id
    llm = FakeLlm(paragraphs=[{
        "claim": "Tirzepatide.",
        "citations": [{"chunk_id": cid}, {"chunk_id": cid}],
    }])
    brief = compose_brief(
        store=store, workspace_id=ws_id,
        question="tirzepatide diabetes", llm=llm,
    )
    assert len(brief.paragraphs[0].citations) == 1


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_brief_to_dict_round_trip(populated_store) -> None:
    store, ws_id = populated_store
    from src.polaris_graph.audit_ir.corpus_retriever import retrieve_chunks
    chunks = retrieve_chunks(store, ws_id, "tirzepatide diabetes")
    cid = chunks[0].chunk_id
    llm = FakeLlm(paragraphs=[{
        "claim": "Claim.", "citations": [{"chunk_id": cid}],
    }])
    brief = compose_brief(
        store=store, workspace_id=ws_id,
        question="tirzepatide diabetes", llm=llm,
    )
    d = brief_to_dict(brief)
    assert d["workspace_id"] == ws_id
    assert d["question"] == "tirzepatide diabetes"
    assert len(d["paragraphs"]) == 1
    assert d["paragraphs"][0]["claim"] == "Claim."
    assert d["paragraphs"][0]["support_status"] == "supported"
    assert len(d["paragraphs"][0]["citations"]) == 1
    assert d["paragraphs"][0]["citations"][0]["chunk_id"] == cid
    assert "retrieved_chunks" in d
    assert all("text_preview" in c for c in d["retrieved_chunks"])
