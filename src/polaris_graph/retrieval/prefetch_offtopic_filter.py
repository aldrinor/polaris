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
    # I-meta-002-q1d (#951): the query that surfaced this candidate, so the fetch-time
    # rerank can reserve at least one slot per sub-query (no single query monopolizes the
    # cap). Empty for legacy callers / a stable fallback bucket.
    query_origin: str = ""

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


# I-deepfix-001 B1 (2026-06-28): the relevance embedder is the LOCKED slate
# Qwen3-Embedding-8B, NOT MiniLM. `evidence_selector._get_semantic_embedder`
# reuses THIS loader, so repointing it here repoints the entire B1/B4 relevance
# story (one embedder = one relevance scale). Env-overridable (LAW VI); MiniLM
# was the silent off-topic-survival root (a 384-dim MiniLM cosine cannot resolve
# clinical topicality the way the slate 8B model does).
_DEFAULT_EMBED_MODEL = "Qwen/Qwen3-Embedding-8B"


def _embed_model_name() -> str:
    """The relevance embedder id — LOCKED slate Qwen3-Embedding-8B by default,
    env-overridable via ``PG_EMBED_MODEL`` (LAW VI)."""
    return (os.getenv("PG_EMBED_MODEL", _DEFAULT_EMBED_MODEL).strip()
            or _DEFAULT_EMBED_MODEL)


def _load_embedder() -> Any:
    """Lazy-load the relevance embedding model. Returns None on load failure
    (the caller fails OPEN — keeps all candidates — never a silent off-topic
    keep at a wrong scale).

    The model id is ``PG_EMBED_MODEL`` (default: the locked slate
    ``Qwen/Qwen3-Embedding-8B``). The ``EmbeddingService`` indirection is kept
    as an optional primary for callers that wire it, but the SentenceTransformer
    path on the env-pinned model is the production loader."""
    try:
        from src.polaris_graph.agents.nli_verifier import (  # type: ignore
            EmbeddingService,
        )
        return EmbeddingService()
    except Exception as exc:
        try:
            # Production path: sentence-transformers on the env-pinned slate model.
            from sentence_transformers import SentenceTransformer
            model_name = _embed_model_name()
            logger.info(
                "[prefetch_offtopic] loading relevance embedder model=%s "
                "(B1 locked-slate default; PG_EMBED_MODEL overrides)",
                model_name,
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
) -> Optional[list[float]]:
    """Compute cosine similarity between query and each snippet.

    Uses whichever interface the embedder exposes (`embed_batch` or `encode`).

    I-deepfix-001 B1 (Codex wave-1 P0): a SCORER/INFRA FAILURE must be SIGNALLED,
    never laundered into below-threshold 0.0 scores that the caller hard-drops.
    Returns ``None`` on a whole-batch scoring failure — (a) the embedder exposes no
    ``embed_batch``/``encode`` interface, (b) the QUERY vector is degenerate
    (zero-norm), or (c) the encode call raises — so EVERY consumer fails OPEN
    (keeps candidates / falls back to the lexical scorer), never drops a source on a
    scoring error (§-1.3: an embedder error must not drop a source).

    A genuinely empty/degenerate SNIPPET vector still scores 0.0 (the documented
    "no embeddable text -> not relevant" path), distinct from an infra failure.
    Returns ``[]`` for an empty snippet list.
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
            logger.warning(
                "[prefetch_offtopic] embedder exposes no embed_batch/encode "
                "interface — FAIL-OPEN (None), caller keeps candidates."
            )
            return None

        q = np.asarray(query_vec, dtype="float32").reshape(-1)
        q_norm = np.linalg.norm(q)
        if q_norm < 1e-9:
            logger.warning(
                "[prefetch_offtopic] degenerate (zero-norm) query vector — "
                "FAIL-OPEN (None), caller keeps candidates."
            )
            return None
        q = q / q_norm

        sims: list[float] = []
        for vec in snippet_vecs:
            s = np.asarray(vec, dtype="float32").reshape(-1)
            s_norm = np.linalg.norm(s)
            if s_norm < 1e-9:
                # Genuinely empty/degenerate SNIPPET text -> "no relevance" (a real
                # 0.0), NOT an infra failure. Documented no-embeddable-text path.
                sims.append(0.0)
            else:
                sims.append(float(q @ (s / s_norm)))
        return sims
    except Exception as exc:
        logger.warning(
            "[prefetch_offtopic] similarity scoring FAILED: %s — FAIL-OPEN "
            "(None), caller keeps candidates / falls back to lexical.",
            str(exc)[:200],
        )
        return None


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
    if sims is None:
        # I-deepfix-001 B1 (Codex wave-1 P0): a scorer/infra failure must FAIL OPEN
        # — keep every candidate, never hard-drop on a scoring error. The looser
        # post-fetch filter remains the second line of defense.
        logger.warning(
            "[prefetch_offtopic] scorer unavailable (infra failure) — FAIL-OPEN, "
            "passing all %d candidates",
            len(candidates),
        )
        return FilterResult(
            kept=list(candidates), rejected=[], threshold_used=threshold,
            total_in=len(candidates), total_kept=len(candidates),
            total_rejected=0,
        )

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
