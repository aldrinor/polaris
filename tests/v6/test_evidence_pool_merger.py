"""Tests for Phase 1 Task 1.3 evidence-pool merger.

Validates that uploaded documents are NOT silently dropped (the
graph_v4.py:149 bug surfaced in v6 plan errata).
"""

from __future__ import annotations

from polaris_v6.adapters.evidence_pool_merger import (
    UploadedChunk,
    merge_evidence_pool,
)
from polaris_v6.schemas.evidence_contract import SourceSpan


def _retrieval_span(evidence_id: str, text: str, url: str = "https://example.gc.ca") -> SourceSpan:
    return SourceSpan(
        evidence_id=evidence_id,
        source_url=url,
        source_tier="T1",
        span_start=0,
        span_end=len(text),
        span_text=text,
    )


def test_uploaded_chunks_appear_in_pool():
    pool = merge_evidence_pool(
        retrieval_spans=[],
        uploaded_chunks=[
            UploadedChunk(document_id="doc1", chunk_index=0, text="Q3 2025 housing starts rose 3.4%."),
        ],
    )
    assert len(pool) == 1
    assert pool[0].evidence_id.startswith("ev_upload_")


def test_retrieval_and_upload_both_in_pool():
    pool = merge_evidence_pool(
        retrieval_spans=[
            _retrieval_span("ev_001", "CMHC Q3 report shows growth."),
        ],
        uploaded_chunks=[
            UploadedChunk(document_id="doc1", chunk_index=0, text="My internal Q3 analysis."),
        ],
    )
    assert len(pool) == 2
    assert any(s.evidence_id.startswith("ev_upload_") for s in pool)
    assert any(s.evidence_id == "ev_001" for s in pool)


def test_upload_takes_priority_on_duplicate():
    """Same text from same URL: upload version wins (because it's first)."""
    text = "Identical content"
    pool = merge_evidence_pool(
        retrieval_spans=[
            _retrieval_span("ev_001", text, url="upload://"),
        ],
        uploaded_chunks=[
            UploadedChunk(document_id="doc1", chunk_index=0, text=text),
        ],
    )
    assert len(pool) == 1
    assert pool[0].evidence_id.startswith("ev_upload_")


def test_dedup_normalizes_whitespace_and_case():
    pool = merge_evidence_pool(
        retrieval_spans=[],
        uploaded_chunks=[
            UploadedChunk(document_id="doc1", chunk_index=0, text="Housing Starts 2025"),
            UploadedChunk(document_id="doc2", chunk_index=0, text="  housing  starts  2025  "),
        ],
    )
    assert len(pool) == 1


def test_evidence_ids_are_stable():
    chunk = UploadedChunk(document_id="doc1", chunk_index=0, text="Stable content")
    pool_a = merge_evidence_pool(retrieval_spans=[], uploaded_chunks=[chunk])
    pool_b = merge_evidence_pool(retrieval_spans=[], uploaded_chunks=[chunk])
    assert pool_a[0].evidence_id == pool_b[0].evidence_id


def test_empty_inputs_return_empty_pool():
    assert merge_evidence_pool(retrieval_spans=[], uploaded_chunks=[]) == []
