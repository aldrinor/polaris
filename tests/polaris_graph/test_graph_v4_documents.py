"""Unit tests for I-f3-001 — graph_v4 _load_uploaded_documents + q-dict threading."""

from __future__ import annotations

import logging

import pytest


class StubIngester:
    """Regular class (no unittest.mock per CLAUDE.md §9.4)."""

    def __init__(self, docs: dict) -> None:
        self._docs = docs

    def get_document(self, doc_id: str):
        return self._docs.get(doc_id)


def _import_helper():
    from src.polaris_graph.graph_v4 import _load_uploaded_documents
    return _load_uploaded_documents


def test_empty_or_none_returns_empty():
    fn = _import_helper()
    assert fn([]) == []


def test_invalid_doc_id_format_skipped_with_warning(caplog):
    fn = _import_helper()
    valid = "a" * 16
    docs = {valid: {"content": "hello world", "metadata": {"original_filename": "h.txt"}}}
    ingester = StubIngester(docs)
    bad_ids = ["../etc/passwd", "abc", "X" * 16, "g" * 16]  # path-traversal, too short, non-hex
    with caplog.at_level(logging.WARNING):
        out = fn([*bad_ids, valid], ingester=ingester)
    assert len(out) == 1
    assert out[0]["document_id"] == valid
    assert "invalid doc_id format" in caplog.text


def test_loads_chunks_from_documents():
    fn = _import_helper()
    docs = {
        "a" * 16: {"content": "x" * 5, "metadata": {"original_filename": "alpha.txt"}},
        "b" * 16: {"content": "y" * 5, "metadata": {"filename": "beta.md"}},
    }
    out = fn(["a" * 16, "b" * 16], ingester=StubIngester(docs), chunk_size=10)
    assert len(out) == 2
    assert out[0]["document_id"] == "a" * 16
    assert out[0]["filename"] == "alpha.txt"
    assert out[0]["chunk_index"] == 0
    assert out[0]["text"] == "xxxxx"
    assert out[1]["filename"] == "beta.md"


def test_missing_document_id_skipped_with_warning(caplog):
    fn = _import_helper()
    valid = "a" * 16
    docs = {valid: {"content": "z" * 5, "metadata": {}}}
    other = "b" * 16
    with caplog.at_level(logging.WARNING):
        out = fn([valid, other], ingester=StubIngester(docs))
    assert len(out) == 1
    assert out[0]["document_id"] == valid
    assert out[0]["filename"] == valid  # fallback chain: doc_id when no filename in metadata
    assert "not found" in caplog.text


def test_all_invalid_or_missing_raises():
    fn = _import_helper()
    with pytest.raises(RuntimeError, match="every requested"):
        fn(["bad-id", "g" * 16], ingester=StubIngester({}))


def test_chunk_size_respected():
    fn = _import_helper()
    valid = "a" * 16
    docs = {valid: {"content": "x" * 4500, "metadata": {}}}
    out = fn([valid], ingester=StubIngester(docs), chunk_size=1500)
    assert len(out) == 3
    assert all(len(c["text"]) == 1500 for c in out)
    assert [c["chunk_index"] for c in out] == [0, 1, 2]


@pytest.mark.asyncio
async def test_q_dict_threading_with_stubbed_run_one_query(monkeypatch):
    """Test 7 per Codex iter-2 P2 #1: stubs run_one_query + DocumentIngester
    and asserts q['uploaded_documents'] reaches pipeline-A."""
    from src.polaris_graph import graph_v4

    captured = {}
    docs = {
        "a" * 16: {"content": "alpha content", "metadata": {"original_filename": "a.txt"}},
        "b" * 16: {"content": "beta content", "metadata": {"original_filename": "b.txt"}},
    }

    async def stub_run_one_query(q, out_root):
        captured["q"] = q
        return {"status": "success", "manifest": {"status": "success"}, "run_dir": str(out_root)}

    monkeypatch.setattr(
        "src.polaris_graph.document_ingester.DocumentIngester",
        lambda: StubIngester(docs),
    )
    monkeypatch.setattr("scripts.run_honest_sweep_r3.run_one_query", stub_run_one_query)

    await graph_v4.build_and_run_v4(
        vector_id="test", query="Q", document_ids=["a" * 16, "b" * 16],
        enable_dashboard=False,
    )
    assert "uploaded_documents" in captured["q"]
    assert len(captured["q"]["uploaded_documents"]) == 2
    assert captured["q"]["uploaded_documents"][0]["chunk_index"] == 0
    assert captured["q"]["uploaded_documents"][0]["filename"] == "a.txt"
