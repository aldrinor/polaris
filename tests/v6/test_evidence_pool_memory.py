"""Tests for I-f14-004 — memory-as-corpus injection into evidence pool."""

from __future__ import annotations

from polaris_v6.adapters.evidence_pool_merger import (
    MemoryDerivedSummary,
    UploadedChunk,
    merge_evidence_pool,
)
from polaris_v6.schemas.evidence_contract import SourceSpan


def _retrieval_span(evidence_id: str, text: str, url: str = "https://gc.ca") -> SourceSpan:
    return SourceSpan(
        evidence_id=evidence_id,
        source_url=url,
        source_tier="T1",
        span_start=0,
        span_end=len(text),
        span_text=text,
    )


def test_memory_summaries_appear_in_pool():
    summary = MemoryDerivedSummary(
        entry_id="abc123",
        content="Prior CMHC housing-starts review.",
        created_at="2026-04-30T00:00:00Z",
    )
    pool = merge_evidence_pool(
        retrieval_spans=[],
        uploaded_chunks=[],
        memory_summaries=[summary],
    )
    assert len(pool) == 1
    span = pool[0]
    assert span.evidence_id.startswith("ev_memory_")
    assert span.source_tier == "T3"
    assert span.source_url == "memory://abc123"
    assert span.span_start == 0
    assert span.span_end == len(summary.content)
    assert span.span_text == summary.content


def test_memory_summaries_dedup_internal():
    s1 = MemoryDerivedSummary(entry_id="a", content="Same text.", created_at="x")
    s2 = MemoryDerivedSummary(entry_id="b", content=" SAME TEXT. ", created_at="y")
    pool = merge_evidence_pool(
        retrieval_spans=[],
        uploaded_chunks=[],
        memory_summaries=[s1, s2],
    )
    assert len(pool) == 1


def test_uploaded_takes_priority_over_memory():
    pool = merge_evidence_pool(
        retrieval_spans=[],
        uploaded_chunks=[
            UploadedChunk(document_id="doc1", chunk_index=0, text="Shared content."),
        ],
        memory_summaries=[
            MemoryDerivedSummary(
                entry_id="m1", content="Shared content.", created_at="z"
            ),
        ],
    )
    assert len(pool) == 1
    assert pool[0].evidence_id.startswith("ev_upload_")


def test_retrieval_takes_priority_over_memory():
    pool = merge_evidence_pool(
        retrieval_spans=[_retrieval_span("ret1", "Shared retrieval text.")],
        uploaded_chunks=[],
        memory_summaries=[
            MemoryDerivedSummary(
                entry_id="m1", content="Shared retrieval text.", created_at="z"
            ),
        ],
    )
    assert len(pool) == 1
    span = pool[0]
    assert span.source_tier == "T1"
    assert not span.evidence_id.startswith("ev_memory_")


def test_pool_with_all_three_kinds():
    pool = merge_evidence_pool(
        retrieval_spans=[_retrieval_span("ret1", "Retrieval-only text.")],
        uploaded_chunks=[
            UploadedChunk(document_id="doc1", chunk_index=0, text="Uploaded-only text."),
        ],
        memory_summaries=[
            MemoryDerivedSummary(
                entry_id="m1", content="Memory-only summary.", created_at="z"
            ),
        ],
    )
    assert len(pool) == 3
    tiers = [s.source_tier for s in pool]
    assert tiers.count("T2") == 1
    assert tiers.count("T1") == 1
    assert tiers.count("T3") == 1
    urls = [s.source_url for s in pool]
    assert "memory://m1" in urls
