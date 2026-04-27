"""Corpus retriever (M-12 — Phase B).

Per FINAL_PLAN.md: Question-Bound Corpus Brief = "answer one user
question over a SELECTED corpus, emit cited brief". This module
handles the retrieval half: given a question + workspace_id, return
the top-K chunks ranked by relevance, each carrying its
(upload_id, provenance) so M-12's brief emitter can cite back to
exact locations.

Phase B uses lexical BM25-style retrieval (no embeddings — keeps
the dependency surface small and the failure mode obvious).
Phase C M-12.5 will swap in a vector backend; the public API
(`retrieve_chunks`) is stable so callers don't change.

Why BM25, not embeddings, for Phase B:
  - Zero new model deps; deterministic results in tests.
  - For Phase B's narrow scope (10-50 docs/workspace, single
    question per call), recall on lexical matches is acceptable.
  - When M-12 emits "insufficient support" because BM25 missed a
    semantically-paraphrased chunk, that's a Phase B feature, not
    a bug — the operator sees the gap and can rephrase.

Workflow boundary:
  - retrieve_chunks() ONLY reads; never mutates the workspace.
  - It does NOT decide "answered" vs "insufficient" — that's the
    verifier's job (corpus_brief.py).
  - It returns chunks from non-deleted, parsed uploads only.

The tokenizer is intentionally identical to template_classifier's
(hyphen split, Unicode hyphen normalize, stopword filter, Roman
+ compact-drug-class normalization) so retrieval ranks consistent
with the routing classifier's notion of content tokens.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any

from src.polaris_graph.audit_ir.template_classifier import (
    _filter_stopwords,
    _tokenize_raw,
)
from src.polaris_graph.audit_ir.workspace_store import WorkspaceStore


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetrievedChunk:
    """One scored chunk pulled from the workspace.

    Carries everything the brief emitter needs to cite:
      - chunk_id / upload_id: stable IDs for downstream use.
      - filename: human-readable label for the citation.
      - text: the chunk content (used by the verifier prompt).
      - provenance: location info (TextSpan, PdfSpan, ...).
      - score: BM25 score; UI may show this for debugging.
    """

    chunk_id: str
    upload_id: str
    filename: str
    text: str
    provenance: dict[str, Any]
    score: float


# ---------------------------------------------------------------------------
# BM25 ranker
# ---------------------------------------------------------------------------


# Standard Robertson-Sparck-Jones BM25 parameters.
_BM25_K1 = 1.5
_BM25_B = 0.75


def _content_tokens(text: str) -> list[str]:
    """Tokenize text the same way the template classifier does, then
    drop stopwords and 1-char tokens. Returns a list (order
    preserved) so we can compute term frequencies; the query side
    uses a frozenset for the same vocabulary."""
    toks_set = _tokenize_raw(text)
    # _tokenize_raw is set-based; we need a multiset for BM25.
    # Re-tokenize directly from the same primitive.
    from src.polaris_graph.audit_ir.template_classifier import _tokenize_raw_seq
    seq = _tokenize_raw_seq(text)
    return [t for t in seq if t in _filter_stopwords(toks_set)]


def _bm25_score(
    query_tokens: list[str],
    chunk_tokens: list[str],
    doc_freqs: dict[str, int],
    n_docs: int,
    avg_doc_len: float,
) -> float:
    """Standard BM25 score for one query against one chunk."""
    if not chunk_tokens or not query_tokens or n_docs == 0:
        return 0.0
    chunk_counter = Counter(chunk_tokens)
    chunk_len = len(chunk_tokens)
    score = 0.0
    seen_terms: set[str] = set()
    for term in query_tokens:
        if term in seen_terms:
            continue
        seen_terms.add(term)
        df = doc_freqs.get(term, 0)
        if df == 0:
            continue
        # Robertson-Sparck-Jones IDF; adds 1 to keep results
        # non-negative even for very common terms.
        idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
        tf = chunk_counter.get(term, 0)
        if tf == 0:
            continue
        denom = tf + _BM25_K1 * (
            1 - _BM25_B + _BM25_B * (chunk_len / avg_doc_len)
        )
        score += idf * (tf * (_BM25_K1 + 1) / denom)
    return score


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


DEFAULT_TOP_K = 8
DEFAULT_MIN_SCORE = 0.5  # BM25 floor for inclusion


def retrieve_chunks(
    store: WorkspaceStore,
    workspace_id: str,
    question: str,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = DEFAULT_MIN_SCORE,
) -> list[RetrievedChunk]:
    """Return up to top_k highest-scoring chunks from the workspace
    that pass `min_score`. Empty list if nothing crosses the floor.

    Drops chunks from soft-deleted or non-`parsed` uploads.

    The workspace MUST exist; raises ValueError otherwise so the
    API layer can return a clean 404. (Per LAW II — never silently
    return empty results when the workspace is missing.)
    """
    if store.get_workspace(workspace_id) is None:
        raise ValueError(f"unknown workspace: {workspace_id}")

    q_tokens = _content_tokens(question)
    if not q_tokens:
        return []

    uploads = store.list_uploads(workspace_id, include_deleted=False)
    parsed = [u for u in uploads if u.parser_status == "parsed"]
    if not parsed:
        return []

    # Build the corpus once: gather all chunks from all parsed
    # uploads in this workspace.
    all_chunks: list[tuple[dict[str, Any], list[str], str]] = []
    # tuple shape: (chunk_record, tokens, filename)
    for upload in parsed:
        chunk_dicts = store.list_chunks(upload.upload_id)
        for ck in chunk_dicts:
            tokens = _content_tokens(ck["text"])
            all_chunks.append((ck, tokens, upload.filename))

    if not all_chunks:
        return []

    n_docs = len(all_chunks)
    avg_doc_len = sum(len(t) for _, t, _ in all_chunks) / n_docs
    if avg_doc_len == 0:
        return []

    # Doc-frequency table — count ONCE per chunk.
    doc_freqs: dict[str, int] = {}
    for _, tokens, _ in all_chunks:
        for term in set(tokens):
            doc_freqs[term] = doc_freqs.get(term, 0) + 1

    scored: list[RetrievedChunk] = []
    for ck, tokens, filename in all_chunks:
        s = _bm25_score(q_tokens, tokens, doc_freqs, n_docs, avg_doc_len)
        if s < min_score:
            continue
        scored.append(RetrievedChunk(
            chunk_id=ck["chunk_id"],
            upload_id=ck["upload_id"],
            filename=filename,
            text=ck["text"],
            provenance=ck["provenance"],
            score=s,
        ))
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:top_k]
