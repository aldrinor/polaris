"""
Pre-fetch off-topic filter — HONEST-REBUILD Phase 2d.

Filters search results BEFORE full-page fetching so we don't waste
network / parse budget on results whose title+snippet is already
clearly unrelated to the research question.

WHY THIS EXISTS (PG_LB_SA_02_CONTENT_AUDIT Section E-03):
- The pre-rebuild pipeline fetched every search result, extracted
  evidence, then filtered off-topic evidence during synthesis.
- The legacy PG_OFFTOPIC_THRESHOLD=0.15 was so low that near-zero-
  similarity evidence (e.g., Japan health insurance general articles
  when the query was semaglutide CV risk) survived.
- The "risk axis retained below threshold" path further defeated
  tightening attempts because its floor was pinned at 0.15.

PHASE 2D APPROACH:
- Filter snippets BEFORE fetch using a looser threshold
  (PG_OFFTOPIC_PREFETCH_THRESHOLD, default 0.25).
- Filter evidence AFTER fetch + extraction using a tighter threshold
  (PG_OFFTOPIC_THRESHOLD, default 0.35).
- Both stages use the scope-protocol's research_question as the
  canonical anchor, not a free-form state.query that could drift.

This module is cheap to call — it uses the embedding service we
already load for evidence deduplication, so there's no new model
cost.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("polaris_graph.prefetch_offtopic")


@dataclass
class SearchCandidate:
    """Minimal shape of a search result for off-topic filtering.

    Callers wrap Serper / OpenAlex / Semantic Scholar results into
    this shape. All fields may be empty; `snippet_text` is the only
    one actually used for similarity scoring.
    """

    url: str
    title: str = ""
    snippet: str = ""
    source: str = ""            # "serper" / "openalex" / "s2" / "exa"
    metadata: dict[str, Any] | None = None

    @property
    def snippet_text(self) -> str:
        """Text used for embedding-based similarity."""
        parts = [self.title.strip(), self.snippet.strip()]
        return " ".join(p for p in parts if p)


@dataclass
class FilterResult:
    """Return value of filter_search_results()."""

    kept: list[SearchCandidate]
    rejected: list[tuple[SearchCandidate, float, str]]  # (cand, sim, reason)
    threshold_used: float
    total_in: int
    total_kept: int
    total_rejected: int


def _load_embedder() -> Any:
    """Lazy-load the embedding service. Returns None on import failure."""
    try:
        from src.polaris_graph.agents.nli_verifier import (  # type: ignore
            EmbeddingService,
        )
        return EmbeddingService()
    except Exception as exc:
        try:
            # Fallback: sentence-transformers direct
            from sentence_transformers import SentenceTransformer
            model_name = os.getenv(
                "PG_EMBED_MODEL",
                "sentence-transformers/all-MiniLM-L6-v2",
            )
            return SentenceTransformer(model_name)
        except Exception:
            logger.warning(
                "[prefetch_offtopic] Embedder not available: %s — "
                "skipping filter (fail-open)",
                str(exc)[:200],
            )
            return None


def _similarity_scores(
    embedder: Any,
    query: str,
    snippets: list[str],
) -> list[float]:
    """Compute cosine similarity between query and each snippet.

    Uses whichever interface the embedder exposes (`embed_batch`,
    `encode`, or direct call). Returns zeros on failure.
    """
    if not snippets:
        return []
    try:
        import numpy as np  # type: ignore

        if hasattr(embedder, "embed_batch"):
            query_vec = embedder.embed_batch([query])[0]
            snippet_vecs = embedder.embed_batch(snippets)
        elif hasattr(embedder, "encode"):
            query_vec = embedder.encode(query, normalize_embeddings=True)
            snippet_vecs = embedder.encode(
                snippets, normalize_embeddings=True,
            )
        else:
            return [0.0] * len(snippets)

        q = np.asarray(query_vec, dtype="float32").reshape(-1)
        q_norm = np.linalg.norm(q)
        if q_norm < 1e-9:
            return [0.0] * len(snippets)
        q = q / q_norm

        sims: list[float] = []
        for vec in snippet_vecs:
            s = np.asarray(vec, dtype="float32").reshape(-1)
            s_norm = np.linalg.norm(s)
            if s_norm < 1e-9:
                sims.append(0.0)
            else:
                sims.append(float(q @ (s / s_norm)))
        return sims
    except Exception as exc:
        logger.warning(
            "[prefetch_offtopic] similarity failed: %s — returning zeros",
            str(exc)[:200],
        )
        return [0.0] * len(snippets)


def filter_search_results(
    candidates: list[SearchCandidate],
    research_question: str,
    threshold: Optional[float] = None,
) -> FilterResult:
    """Filter search candidates by semantic similarity to the research question.

    Args:
        candidates: List of SearchCandidate. Must have .snippet_text.
        research_question: The canonical question from protocol.json.
            This is the ONLY anchor — do not use state.query or
            amplifier-derived variants here.
        threshold: Override for PG_OFFTOPIC_PREFETCH_THRESHOLD. None
            uses the env var (default 0.25).

    Returns:
        FilterResult with kept / rejected lists and telemetry counts.
        FAIL-OPEN: if the embedder fails to load or similarity raises,
        we keep everything and log a warning. Retrieval continues with
        the looser post-fetch filter as the second line of defense.
    """
    if not candidates:
        return FilterResult(
            kept=[], rejected=[], threshold_used=0.0,
            total_in=0, total_kept=0, total_rejected=0,
        )

    if threshold is None:
        threshold = float(
            os.getenv("PG_OFFTOPIC_PREFETCH_THRESHOLD", "0.25")
        )

    # Anchor must be non-empty
    anchor = (research_question or "").strip()
    if not anchor:
        logger.warning(
            "[prefetch_offtopic] empty research_question — FAIL-OPEN, "
            "passing all %d candidates",
            len(candidates),
        )
        return FilterResult(
            kept=list(candidates), rejected=[], threshold_used=threshold,
            total_in=len(candidates), total_kept=len(candidates),
            total_rejected=0,
        )

    embedder = _load_embedder()
    if embedder is None:
        return FilterResult(
            kept=list(candidates), rejected=[], threshold_used=threshold,
            total_in=len(candidates), total_kept=len(candidates),
            total_rejected=0,
        )

    snippets = [c.snippet_text or "" for c in candidates]
    sims = _similarity_scores(embedder, anchor, snippets)

    kept: list[SearchCandidate] = []
    rejected: list[tuple[SearchCandidate, float, str]] = []
    for cand, sim in zip(candidates, sims):
        if not cand.snippet_text.strip():
            # Keep candidates with no snippet — we need to fetch to know.
            kept.append(cand)
            continue
        if sim >= threshold:
            kept.append(cand)
        else:
            rejected.append((cand, float(sim), "below_prefetch_threshold"))

    logger.info(
        "[prefetch_offtopic] filter threshold=%.2f kept=%d rejected=%d "
        "total=%d",
        threshold, len(kept), len(rejected), len(candidates),
    )

    return FilterResult(
        kept=kept, rejected=rejected, threshold_used=threshold,
        total_in=len(candidates),
        total_kept=len(kept),
        total_rejected=len(rejected),
    )
