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
from dataclasses import dataclass, field
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
    """Return value of filter_search_results().

    §-1.3 DEMOTE-NOT-DROP (operator-locked 2026-06-13 WEIGHT-and-CONSOLIDATE):
    ``kept`` carries EVERY candidate — cosine is a WEIGHT and an ordering signal,
    NOT a gate. ``kept`` is sorted by cosine DESCENDING so the most-relevant are
    fetched first; below-threshold candidates are KEPT at the tail (DEMOTED) and
    recorded in ``demoted`` (the disclosed drop->demote conversion), NEVER moved to
    ``rejected``. ``rejected`` is reserved ONLY for genuine structural errors, so
    ``total_rejected == 0`` on the normal path. The ONLY sanctioned hard DROP in
    the whole pipeline is the downstream faithfulness engine (strict_verify / NLI /
    4-role D8 / provenance / span-grounding) — which is untouched here.
    """

    kept: list[SearchCandidate]
    rejected: list[tuple[SearchCandidate, float, str]]  # structural errors ONLY (cand, sim, reason)
    threshold_used: float
    total_in: int
    total_kept: int
    total_rejected: int
    # §-1.3 telemetry: the below-threshold-but-KEPT (demoted) candidates with their
    # cosine sim. Surfaced so the drop->demote conversion is DISCLOSED, not silent.
    demoted: list[tuple[SearchCandidate, float]] = field(default_factory=list)
    total_demoted: int = 0


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
        # I-deepfix-001 P0-2a (2026-06-28): EmbeddingService is defined in
        # `src.utils.embedding_service`, NOT `nli_verifier` (which never defined
        # or re-exported it). The old import targeted the wrong module → it ALWAYS
        # raised ImportError, silently knocking out the EmbeddingService primary
        # path and forcing the SentenceTransformer fallback every run. Repointed
        # to the real definition so the EmbeddingService path is reachable again.
        from src.utils.embedding_service import (  # type: ignore
            EmbeddingService,
        )
        return EmbeddingService()
    except Exception as exc:
        try:
            # Production path: sentence-transformers on the env-pinned slate model.
            from sentence_transformers import SentenceTransformer
            model_name = _embed_model_name()
            # I-deepfix-001 P0-3 (2026-06-28): honor PG_EMBED_DEVICE so the run
            # launcher can pin the 8B embedder to a specific card (static 2-GPU
            # split). A LAUNCH-ENV read only (not a slate force-on). Wrapped so an
            # installed sentence-transformers that rejects `device=` falls back to
            # the no-arg constructor with a LOUD warning (never a silent device
            # drop). Empty/unset PG_EMBED_DEVICE => no-arg constructor (unchanged).
            device = (os.getenv("PG_EMBED_DEVICE", "") or "").strip()
            if device:
                try:
                    model = SentenceTransformer(model_name, device=device)
                    logger.info(
                        "[prefetch_offtopic] loading relevance embedder model=%s "
                        "device=%s (B1 locked-slate default; PG_EMBED_MODEL / "
                        "PG_EMBED_DEVICE override)",
                        model_name, device,
                    )
                    return model
                except TypeError:
                    logger.warning(
                        "[prefetch_offtopic] installed sentence-transformers "
                        "rejected device=%r — falling back to no-arg constructor "
                        "(model will land on its default device). model=%s",
                        device, model_name,
                    )
                    return SentenceTransformer(model_name)
            logger.info(
                "[prefetch_offtopic] loading relevance embedder model=%s "
                "(B1 locked-slate default; PG_EMBED_MODEL overrides; "
                "PG_EMBED_DEVICE unset → default device)",
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
    """Order search candidates by semantic similarity to the research question —
    DEMOTE-NOT-DROP (§-1.3 WEIGHT-and-CONSOLIDATE, operator-locked 2026-06-13).

    Cosine similarity to the canonical research question is a WEIGHT and an ordering
    signal, NEVER a gate. EVERY candidate flows through to the fetch stage: the
    returned ``kept`` list is sorted by cosine DESCENDING (most-relevant first) and
    the below-threshold tail is DEMOTED (kept at the end), recorded in ``demoted``
    for disclosure — it is NOT hard-dropped. The downstream fetch BUDGET (the
    disclosed cost bound) decides how far down the cosine-ordered list we actually
    fetch; the off-topic THRESHOLD only orders, it no longer filters. This removes
    the §-1.3-banned hard FILTER at the search-candidate boundary.

    Args:
        candidates: List of SearchCandidate. Must have .snippet_text.
        research_question: The canonical question from protocol.json.
            This is the ONLY anchor — do not use state.query or
            amplifier-derived variants here.
        threshold: Override for PG_OFFTOPIC_PREFETCH_THRESHOLD. None
            uses the env var (default 0.25). NOTE: this is now a DEMOTION
            boundary (below it => demoted, kept at the tail), not a drop gate.

    Returns:
        FilterResult with ``kept`` (ALL candidates, cosine-DESC ordered),
        ``demoted`` (the below-threshold tail, disclosed), an empty ``rejected``
        (reserved for genuine structural errors), and telemetry counts.
        FAIL-OPEN: if the embedder fails to load or similarity raises, we keep
        everything in arrival order and log a warning. Retrieval continues with
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

    # §-1.3 DEMOTE-NOT-DROP: cosine is a WEIGHT/ordering signal, NOT a gate. Keep
    # EVERY candidate; below-threshold ones are DEMOTED (kept, recorded), never
    # moved to `rejected`. `rejected` stays reserved for genuine structural errors
    # (there are none on this path now), so `total_rejected == 0` by default.
    scored: list[tuple[SearchCandidate, float]] = []
    demoted: list[tuple[SearchCandidate, float]] = []
    for cand, sim in zip(candidates, sims):
        sim_val = float(sim)
        scored.append((cand, sim_val))
        # A candidate WITH embeddable text scoring below the threshold is DEMOTED
        # (kept at the tail), never dropped. Empty-snippet candidates carry no
        # relevance signal ("fetch to know") so they are NOT counted as demoted —
        # they simply sort by their ~0.0 sim toward the tail like before they were
        # interspersed, but they still SURVIVE for the fetch stage.
        if cand.snippet_text.strip() and sim_val < threshold:
            demoted.append((cand, sim_val))

    # Sort the FULL kept list by cosine DESCENDING (stable: equal sims keep arrival
    # order). The consumer fetches `kept` in list order up to the fetch budget, so
    # this puts the most-relevant first and lets the below-threshold demoted tail
    # SURVIVE at the end — fetched only if the budget reaches it (a disclosed bound),
    # never hard-dropped here.
    kept: list[SearchCandidate] = [cand for cand, _sim in sorted(scored, key=lambda t: -t[1])]
    rejected: list[tuple[SearchCandidate, float, str]] = []  # structural errors only

    logger.info(
        "[prefetch_offtopic] DEMOTE-not-drop threshold=%.2f kept=%d "
        "(demoted_below_threshold=%d, dropped=0) total=%d",
        threshold, len(kept), len(demoted), len(candidates),
    )

    return FilterResult(
        kept=kept, rejected=rejected, threshold_used=threshold,
        total_in=len(candidates),
        total_kept=len(kept),
        total_rejected=len(rejected),
        demoted=demoted,
        total_demoted=len(demoted),
    )
