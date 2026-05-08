"""Phase 1 Task 1.3 substrate — merge uploaded documents into evidence pool.

The v6 plan errata (substrate_audit_2026-05-01.md) flagged that
graph_v4.py:149 accepts a `document_ids` parameter but does NOT use it.
This is the F3a backend gap — uploaded documents never reached the
evidence pool that the verifier checks against.

This module fixes that by building a deterministic evidence-pool
bridge: given retrieval-side spans + uploaded document chunks, produce
a unified pool with stable evidence_ids that the verifier (and the
EvidenceContract output) can reference.

Phase 0 ships the merger; Phase 1 wires it into the v6 run executor and
ensures graph_v4 (or its v6 successor) consumes the merged pool, not
just the retrieval-side pool.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from polaris_v6.schemas.evidence_contract import SourceSpan


@dataclass
class UploadedChunk:
    """One chunk extracted from an uploaded document."""

    document_id: str
    chunk_index: int
    text: str
    source_url: str = "upload://"  # placeholder; real upload-uri scheme in Phase 1


@dataclass
class MemoryDerivedSummary:
    """One workspace-memory prior_run_summary entry surfaced as evidence (I-f14-004)."""

    entry_id: str
    content: str
    created_at: str


def _evidence_id_for_chunk(chunk: UploadedChunk) -> str:
    """Stable id derived from document_id + chunk_index + content hash."""
    payload = f"{chunk.document_id}:{chunk.chunk_index}:{chunk.text}".encode()
    digest = hashlib.sha256(payload).hexdigest()[:12]
    return f"ev_upload_{digest}"


def _evidence_id_for_memory(summary: MemoryDerivedSummary) -> str:
    """Stable id derived from entry_id + content hash."""
    payload = f"{summary.entry_id}:{summary.content}".encode()
    digest = hashlib.sha256(payload).hexdigest()[:12]
    return f"ev_memory_{digest}"


def _evidence_id_for_retrieval(span: SourceSpan) -> str:
    """Pass-through for already-id'd spans; ensure prefix consistency."""
    if span.evidence_id.startswith("ev_"):
        return span.evidence_id
    return f"ev_{span.evidence_id}"


def merge_evidence_pool(
    *,
    retrieval_spans: list[SourceSpan],
    uploaded_chunks: list[UploadedChunk],
    memory_summaries: list[MemoryDerivedSummary] | None = None,
) -> list[SourceSpan]:
    """Merge retrieval-side + upload-side + workspace-memory into a unified
    deduplicated pool.

    Dedup priority by append order: upload > retrieval > memory.
    Upload + retrieval dedup by (source_url, normalized_text) — same text
    from the same source appears once. Memory entries dedup against the
    ENTIRE existing pool by normalized text only (per I-f14-004 plan), so
    a prior_run_summary that repeats text already surfaced via upload or
    retrieval is dropped.
    """
    pool: list[SourceSpan] = []
    seen: set[tuple[str, str]] = set()

    for chunk in uploaded_chunks:
        normalized = _normalize_for_dedup(chunk.text)
        key = (chunk.source_url, normalized)
        if key in seen:
            continue
        seen.add(key)
        pool.append(
            SourceSpan(
                evidence_id=_evidence_id_for_chunk(chunk),
                source_url=chunk.source_url,
                source_tier="T2",
                span_start=0,
                span_end=len(chunk.text),
                span_text=chunk.text,
            )
        )

    for span in retrieval_spans:
        normalized = _normalize_for_dedup(span.span_text)
        key = (span.source_url, normalized)
        if key in seen:
            continue
        seen.add(key)
        pool.append(
            SourceSpan(
                evidence_id=_evidence_id_for_retrieval(span),
                source_url=span.source_url,
                source_tier=span.source_tier,
                span_start=span.span_start,
                span_end=span.span_end,
                span_text=span.span_text,
            )
        )

    text_seen = {_normalize_for_dedup(s.span_text) for s in pool}
    for summary in memory_summaries or []:
        normalized = _normalize_for_dedup(summary.content)
        if normalized in text_seen:
            continue
        text_seen.add(normalized)
        pool.append(
            SourceSpan(
                evidence_id=_evidence_id_for_memory(summary),
                source_url=f"memory://{summary.entry_id}",
                source_tier="T3",
                span_start=0,
                span_end=len(summary.content),
                span_text=summary.content,
            )
        )

    return pool


_WS_RE = re.compile(r"\s+")


def _normalize_for_dedup(text: str) -> str:
    return _WS_RE.sub(" ", text.strip().lower())
