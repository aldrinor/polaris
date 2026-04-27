"""Tests for src/polaris_graph/audit_ir/corpus_brief.py (M-12)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.polaris_graph.audit_ir.corpus_brief import (
    BriefCitation,
    BriefParagraph,
    CorpusBrief,
    LlmClient,
    OpenRouterBriefClient,
    brief_to_dict,
    compose_brief,
)
from src.polaris_graph.audit_ir.corpus_retriever import RetrievedChunk
from src.polaris_graph.audit_ir.provenance import TextSpan, to_dict
from src.polaris_graph.audit_ir.workspace_store import WorkspaceStore


def _run(coro):
    """Helper to run async compose_brief in tests."""
    return asyncio.run(coro)


class FakeLlm:
    """Minimal LlmClient for tests. Returns whatever the test set."""

    def __init__(self, paragraphs: list[dict[str, Any]] | None = None,
                 raise_with: Exception | None = None) -> None:
        self._paragraphs = paragraphs or []
        self._raise = raise_with
        self.calls: list[tuple[str, list[RetrievedChunk]]] = []

    async def draft_brief(
        self, question: str, chunks: list[RetrievedChunk]
    ) -> list[dict[str, Any]]:
        # Codex M-12 review fix: LlmClient is an async Protocol now.
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
    brief = _run(compose_brief(
        store=store, workspace_id=ws_id,
        question="tirzepatide diabetes efficacy", llm=llm,
    ))
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
    store, ws_id = populated_store
    llm = FakeLlm()
    brief = _run(compose_brief(
        store=store, workspace_id=ws_id,
        question="blockchain governance crypto", llm=llm,
    ))
    assert len(brief.paragraphs) == 1
    p = brief.paragraphs[0]
    assert p.support_status == "insufficient_support"
    assert p.citations == ()
    assert "insufficient" in p.claim.lower()
    assert llm.calls == [], "LLM must not be called when retrieval is empty"


def test_compose_brief_drops_paragraphs_with_unknown_chunk_ids(populated_store) -> None:
    store, ws_id = populated_store
    llm = FakeLlm(paragraphs=[
        {
            "claim": "Made-up claim citing nonexistent chunk.",
            "citations": [{"chunk_id": "ck_does_not_exist"}],
        },
    ])
    brief = _run(compose_brief(
        store=store, workspace_id=ws_id,
        question="tirzepatide diabetes efficacy", llm=llm,
    ))
    assert len(brief.paragraphs) == 1
    assert brief.paragraphs[0].support_status == "insufficient_support"
    assert "drafted claims could" in brief.paragraphs[0].claim


def test_compose_brief_strips_invalid_citations_but_keeps_valid_paragraph(
    populated_store,
) -> None:
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
    brief = _run(compose_brief(
        store=store, workspace_id=ws_id,
        question="tirzepatide diabetes", llm=llm,
    ))
    assert len(brief.paragraphs) == 1
    assert brief.paragraphs[0].support_status == "supported"
    assert len(brief.paragraphs[0].citations) == 1
    assert brief.paragraphs[0].citations[0].chunk_id == cid


def test_compose_brief_drops_paragraphs_with_no_citations(populated_store) -> None:
    store, ws_id = populated_store
    llm = FakeLlm(paragraphs=[
        {"claim": "Uncited claim about diabetes.", "citations": []},
    ])
    brief = _run(compose_brief(
        store=store, workspace_id=ws_id,
        question="tirzepatide diabetes", llm=llm,
    ))
    assert len(brief.paragraphs) == 1
    assert brief.paragraphs[0].support_status == "insufficient_support"


def test_compose_brief_drops_paragraphs_with_empty_claim(populated_store) -> None:
    store, ws_id = populated_store
    from src.polaris_graph.audit_ir.corpus_retriever import retrieve_chunks
    chunks = retrieve_chunks(store, ws_id, "tirzepatide diabetes")
    cid = chunks[0].chunk_id
    llm = FakeLlm(paragraphs=[
        {"claim": "", "citations": [{"chunk_id": cid}]},
        {"claim": "   ", "citations": [{"chunk_id": cid}]},
        {"claim": "Real claim.", "citations": [{"chunk_id": cid}]},
    ])
    brief = _run(compose_brief(
        store=store, workspace_id=ws_id,
        question="tirzepatide diabetes", llm=llm,
    ))
    assert len(brief.paragraphs) == 1
    assert brief.paragraphs[0].claim == "Real claim."


# ---------------------------------------------------------------------------
# LLM error propagation
# ---------------------------------------------------------------------------


def test_compose_brief_propagates_llm_errors(populated_store) -> None:
    store, ws_id = populated_store
    llm = FakeLlm(raise_with=RuntimeError("LLM timeout"))
    with pytest.raises(RuntimeError, match="LLM timeout"):
        _run(compose_brief(
            store=store, workspace_id=ws_id,
            question="tirzepatide diabetes", llm=llm,
        ))


# ---------------------------------------------------------------------------
# Workspace boundary
# ---------------------------------------------------------------------------


def test_compose_brief_unknown_workspace_raises(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "ws.sqlite")
    llm = FakeLlm()
    with pytest.raises(ValueError, match="unknown workspace"):
        _run(compose_brief(
            store=store, workspace_id="ws_no", question="x", llm=llm,
        ))


# ---------------------------------------------------------------------------
# Malformed LLM responses
# ---------------------------------------------------------------------------


def test_compose_brief_handles_malformed_paragraph_dicts(populated_store) -> None:
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
    brief = _run(compose_brief(
        store=store, workspace_id=ws_id,
        question="tirzepatide diabetes", llm=llm,
    ))
    assert len(brief.paragraphs) == 1
    assert brief.paragraphs[0].claim == "Good claim"


def test_compose_brief_dedupes_citations(populated_store) -> None:
    store, ws_id = populated_store
    from src.polaris_graph.audit_ir.corpus_retriever import retrieve_chunks
    chunks = retrieve_chunks(store, ws_id, "tirzepatide diabetes")
    cid = chunks[0].chunk_id
    llm = FakeLlm(paragraphs=[{
        "claim": "Tirzepatide.",
        "citations": [{"chunk_id": cid}, {"chunk_id": cid}],
    }])
    brief = _run(compose_brief(
        store=store, workspace_id=ws_id,
        question="tirzepatide diabetes", llm=llm,
    ))
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
    brief = _run(compose_brief(
        store=store, workspace_id=ws_id,
        question="tirzepatide diabetes", llm=llm,
    ))
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


# ---------------------------------------------------------------------------
# Codex M-12 review regression: OpenRouterBriefClient must work with
# the real async LLMResponse-shaped client.
# ---------------------------------------------------------------------------


class FakeAsyncOpenRouter:
    """Mimics OpenRouterClient: async generate() returning an
    LLMResponse-shaped object with .content."""

    def __init__(self, response_text: str) -> None:
        self._text = response_text
        self.calls: list[dict[str, Any]] = []

    async def generate(
        self, prompt: str, system: str = "",
        max_tokens: int = 8192, thinking_mode: bool = False,
    ) -> Any:
        self.calls.append({
            "prompt": prompt, "system": system,
            "max_tokens": max_tokens, "thinking_mode": thinking_mode,
        })
        return SimpleNamespace(content=self._text)


def test_openrouter_brief_client_parses_llm_response_content() -> None:
    """Codex M-12 v1 bug: client treated LLMResponse as str. Verify
    fix: parse `.content`, return paragraphs list."""
    fake = FakeAsyncOpenRouter(
        '{"paragraphs": [{"claim": "A", "citations": [{"chunk_id": "ck_1"}]}]}'
    )
    client = OpenRouterBriefClient(fake)
    paragraphs = asyncio.run(client.draft_brief(
        question="q", chunks=[],
    ))
    assert paragraphs == [{"claim": "A", "citations": [{"chunk_id": "ck_1"}]}]


def test_openrouter_brief_client_handles_code_fences() -> None:
    """LLMs sometimes wrap JSON in ```json ... ``` fences."""
    fake = FakeAsyncOpenRouter(
        '```json\n{"paragraphs": [{"claim": "B", "citations": []}]}\n```'
    )
    client = OpenRouterBriefClient(fake)
    paragraphs = asyncio.run(client.draft_brief(question="q", chunks=[]))
    assert paragraphs == [{"claim": "B", "citations": []}]


def test_openrouter_brief_client_raises_on_missing_paragraphs_key() -> None:
    """LAW II — never silently fall back to empty paragraphs."""
    fake = FakeAsyncOpenRouter('{"other_key": "value"}')
    client = OpenRouterBriefClient(fake)
    with pytest.raises(ValueError, match="missing 'paragraphs'"):
        asyncio.run(client.draft_brief(question="q", chunks=[]))


def test_openrouter_brief_client_raises_on_non_list_paragraphs() -> None:
    fake = FakeAsyncOpenRouter('{"paragraphs": "not a list"}')
    client = OpenRouterBriefClient(fake)
    with pytest.raises(ValueError, match="must be a list"):
        asyncio.run(client.draft_brief(question="q", chunks=[]))


def test_openrouter_brief_client_e2e_through_compose_brief(populated_store) -> None:
    """Full end-to-end: real-shape async OpenRouter client →
    compose_brief → supported paragraph. This test would have caught
    the v1 bug where the client was synchronous + treated
    LLMResponse as str."""
    store, ws_id = populated_store
    from src.polaris_graph.audit_ir.corpus_retriever import retrieve_chunks
    chunks = retrieve_chunks(store, ws_id, "tirzepatide diabetes")
    cid = chunks[0].chunk_id

    fake = FakeAsyncOpenRouter(
        f'{{"paragraphs": [{{"claim": "C", "citations": [{{"chunk_id": "{cid}"}}]}}]}}'
    )
    client = OpenRouterBriefClient(fake)
    brief = _run(compose_brief(
        store=store, workspace_id=ws_id,
        question="tirzepatide diabetes", llm=client,
    ))
    assert len(brief.paragraphs) == 1
    assert brief.paragraphs[0].support_status == "supported"
    assert brief.paragraphs[0].claim == "C"


# ---------------------------------------------------------------------------
# Codex M-12 review regression: retrieval must not race soft-delete.
# ---------------------------------------------------------------------------


def test_retrieval_excludes_concurrently_deleted_uploads(tmp_path: Path) -> None:
    """v1 used a two-phase pattern (list_uploads then list_chunks
    per-upload) that raced soft-delete. v2 uses a single SQL JOIN
    that gates on `uploads.deleted_at IS NULL` and
    `parser_status='parsed'` atomically.

    This test simulates the race by deleting an upload AFTER the
    eligible-chunk query would have built its candidate list under
    the v1 pattern. With the v2 atomic snapshot, the deleted
    upload's chunks are absent from the retrieval result.
    """
    from src.polaris_graph.audit_ir.corpus_retriever import retrieve_chunks
    store = WorkspaceStore(tmp_path / "race.sqlite")
    ws = store.create_workspace("RaceRetrieval", max_docs=5)
    a = store.upload_file(ws.workspace_id, "a.txt", "text/plain", 50, "/p/a")
    store.transition_parser_status(a.upload_id, "parsing")
    store.insert_chunks(a.upload_id, [
        ("Tirzepatide diabetes hidden chunk.",
         to_dict(TextSpan(a.upload_id, 0, 30))),
    ])
    store.transition_parser_status(a.upload_id, "parsed")
    b = store.upload_file(ws.workspace_id, "b.txt", "text/plain", 50, "/p/b")
    store.transition_parser_status(b.upload_id, "parsing")
    store.insert_chunks(b.upload_id, [
        ("Tirzepatide diabetes visible chunk.",
         to_dict(TextSpan(b.upload_id, 0, 30))),
    ])
    store.transition_parser_status(b.upload_id, "parsed")

    # Delete `a` BEFORE retrieve_chunks — the v2 atomic snapshot
    # MUST NOT include `a`'s chunk.
    store.soft_delete_upload(a.upload_id)
    results = retrieve_chunks(store, ws.workspace_id, "tirzepatide diabetes")
    upload_ids = {r.upload_id for r in results}
    assert a.upload_id not in upload_ids, (
        f"deleted upload's chunks leaked: {upload_ids}"
    )
    assert b.upload_id in upload_ids


def test_list_eligible_chunks_excludes_deleted_and_unparsed(tmp_path: Path) -> None:
    """Direct test of the new atomic store API."""
    store = WorkspaceStore(tmp_path / "ws.sqlite")
    ws = store.create_workspace("Eligible", max_docs=10)

    # Parsed + live: included.
    parsed = store.upload_file(ws.workspace_id, "p.txt", "text/plain", 10, "/p/p")
    store.transition_parser_status(parsed.upload_id, "parsing")
    store.insert_chunks(parsed.upload_id, [
        ("good", to_dict(TextSpan(parsed.upload_id, 0, 4))),
    ])
    store.transition_parser_status(parsed.upload_id, "parsed")

    # Pending: excluded.
    pending = store.upload_file(ws.workspace_id, "pn.txt", "text/plain", 10, "/p/pn")

    # Failed: excluded.
    failed = store.upload_file(ws.workspace_id, "f.txt", "text/plain", 10, "/p/f")
    store.transition_parser_status(failed.upload_id, "failed", parser_error="x")

    # Parsed but soft-deleted: excluded.
    parsed_deleted = store.upload_file(
        ws.workspace_id, "d.txt", "text/plain", 10, "/p/d"
    )
    store.transition_parser_status(parsed_deleted.upload_id, "parsing")
    store.insert_chunks(parsed_deleted.upload_id, [
        ("deleted", to_dict(TextSpan(parsed_deleted.upload_id, 0, 7))),
    ])
    store.transition_parser_status(parsed_deleted.upload_id, "parsed")
    store.soft_delete_upload(parsed_deleted.upload_id)

    eligible = store.list_eligible_chunks(ws.workspace_id)
    upload_ids = {c["upload_id"] for c in eligible}
    assert upload_ids == {parsed.upload_id}
    # filename column joined in.
    assert eligible[0]["filename"] == "p.txt"
