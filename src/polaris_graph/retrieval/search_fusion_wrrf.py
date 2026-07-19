"""I-wire-001 W3 — Weighted Reciprocal Rank Fusion (WRRF) for search candidates.

This module implements the W3 winner: fuse the per-engine RANKED candidate
lists on their original ranks BEFORE URL-dedup, so a high-authority source
(e.g. NEJM/Lancet) that one engine buries below marketing/junk is lifted by
its strong rank in another engine.

DETERMINISTIC, NO LLM. WRRF is a closed-form scoring function over integer
ranks, so the fused order is fully reproducible (standard point 15). It runs
on CPU — there is no GPU benefit for a rank arithmetic step (standard point 2).

Semantics (CLAUDE.md §-1.3 weight-not-filter): fusion is an ORDERING / WEIGHT.
It NEVER hard-drops a source. URL-dedup keeps every distinct URL exactly once
(the union of all engine lists); fusion only decides the ORDER in which they
flow downstream. A source that ranks low is down-ranked, never deleted.

Algorithm (weighted reciprocal rank fusion, Cormack et al. 2009 RRF with
per-engine weights):

    score(url) = sum over engines e that returned url of:
                     weight(e) / (k + rank_e(url))

where rank_e(url) is the 1-based position of url in engine e's returned list
and k is the RRF smoothing constant. Fused candidates are sorted by score
descending; ties broken deterministically by (first-seen engine order, url)
so the output is stable across runs.

All parameters are env knobs (LAW VI): the smoothing constant
``PG_SEARCH_FUSION_WRRF_K`` and the per-engine weights
``PG_SEARCH_FUSION_WRRF_WEIGHTS`` (a comma list of ``engine:weight`` pairs;
any engine not listed uses ``PG_SEARCH_FUSION_WRRF_DEFAULT_WEIGHT``).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any
from src.polaris_graph.settings import resolve

logger = logging.getLogger("polaris_graph.search_fusion_wrrf")

# RRF smoothing constant default (Cormack et al. 2009 use 60). A larger k
# flattens the contribution of rank position; a smaller k sharpens the head.
_DEFAULT_K = 60.0
# Per-engine weight applied to an engine not named in the weights env knob.
_DEFAULT_ENGINE_WEIGHT = 1.0


def wrrf_enabled() -> bool:
    """True iff the W3 search-fusion-WRRF flag is ON.

    Default OFF: the legacy inline-dedup / RRF-free merge path runs unchanged
    and the candidate ordering is byte-identical to before this wiring.
    """
    return resolve("PG_SEARCH_FUSION_WRRF").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _wrrf_k() -> float:
    raw = resolve("PG_SEARCH_FUSION_WRRF_K").strip()
    if not raw:
        return _DEFAULT_K
    try:
        val = float(raw)
    except ValueError:
        logger.warning(
            "[wrrf] PG_SEARCH_FUSION_WRRF_K=%r is not a float — using %.1f",
            raw, _DEFAULT_K,
        )
        return _DEFAULT_K
    # A non-positive k would divide by <=rank, exploding/negating scores; clamp
    # loudly to the default rather than silently corrupt the ordering.
    if val <= 0:
        logger.warning(
            "[wrrf] PG_SEARCH_FUSION_WRRF_K=%r must be > 0 — using %.1f",
            raw, _DEFAULT_K,
        )
        return _DEFAULT_K
    return val


def _default_engine_weight() -> float:
    raw = resolve("PG_SEARCH_FUSION_WRRF_DEFAULT_WEIGHT").strip()
    if not raw:
        return _DEFAULT_ENGINE_WEIGHT
    try:
        val = float(raw)
    except ValueError:
        return _DEFAULT_ENGINE_WEIGHT
    return val if val >= 0 else _DEFAULT_ENGINE_WEIGHT


def _engine_weights() -> dict[str, float]:
    """Parse ``PG_SEARCH_FUSION_WRRF_WEIGHTS`` into an engine->weight map.

    Format: ``serper:1.0,openalex:1.2,europe_pmc:1.2,s2:1.1`` — academic /
    registry engines can be weighted above generic web search so a NEJM hit
    that openalex ranks #1 outweighs a marketing page serper ranks #1. Any
    engine absent from the map uses the default engine weight. Malformed
    entries are skipped loudly (never crash the merge).
    """
    weights: dict[str, float] = {}
    raw = resolve("PG_SEARCH_FUSION_WRRF_WEIGHTS").strip()
    if not raw:
        return weights
    for part in raw.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        name, _, val = part.partition(":")
        name = name.strip().lower()
        try:
            weights[name] = float(val.strip())
        except ValueError:
            logger.warning("[wrrf] skipping malformed weight entry %r", part)
    return weights


def _url_of(cand: Any) -> str:
    url = getattr(cand, "url", "")
    return url if isinstance(url, str) else ""


@dataclass
class WrrfResult:
    """Outcome of a WRRF fusion pass (telemetry for the run manifest)."""

    fused: list[Any]
    # url -> fused score, for the highest-visibility console event + audit.
    scores: dict[str, float]
    # engine -> count of candidates that engine contributed (pre-dedup).
    per_engine_counts: dict[str, int]
    # number of distinct URLs in the fused output.
    n_unique: int
    k_used: float
    weights_used: dict[str, float]


def wrrf_fuse(
    per_engine_lists: dict[str, list[Any]],
    *,
    k: float | None = None,
    weights: dict[str, float] | None = None,
) -> WrrfResult:
    """Fuse per-engine RANKED candidate lists into one deterministic order.

    Args:
        per_engine_lists: engine-name -> that engine's candidates in the order
            the engine returned them (rank = 1-based index). Each candidate is
            any object exposing a ``.url`` attribute (e.g. SearchCandidate).
        k: RRF smoothing constant override (defaults to the env knob).
        weights: engine->weight override (defaults to the env knob).

    Returns:
        WrrfResult whose ``fused`` is the deduped, WRRF-ordered candidate list.
        The FIRST-SEEN candidate object per URL is retained (engines are
        processed in the dict's insertion order, which mirrors the search
        loop's engine order, so the retained object is stable). NO URL is
        dropped — every distinct URL in the union appears exactly once.
    """
    if k is None:
        k = _wrrf_k()
    if weights is None:
        weights = _engine_weights()
    default_w = _default_engine_weight()

    scores: dict[str, float] = {}
    # First-seen candidate object + first-seen ordinal per URL (for stable tie
    # break). The ordinal is a global monotonically-increasing counter across
    # engines in their processing order.
    first_seen: dict[str, Any] = {}
    first_ordinal: dict[str, int] = {}
    per_engine_counts: dict[str, int] = {}
    weights_used: dict[str, float] = {}
    ordinal = 0

    for engine, cands in per_engine_lists.items():
        # I-wire-001 W3 (#1310) P1-3: the live retriever namespaces domain/need
        # backend engines as ``domain:<name>`` / ``need:<name>`` to avoid colliding
        # with the main-loop engines (serper/s2/openalex). Look up the configured
        # PG_SEARCH_FUSION_WRRF_WEIGHTS by the FULL key first, then fall back to the
        # part AFTER a ``<ns>:`` prefix — so a weight entry ``europe_pmc:1.2``
        # matches the ``domain:europe_pmc`` / ``need:europe_pmc`` engine (else the
        # academic backends the weights are FOR would silently get the default).
        _ekey = engine.lower()
        if _ekey in weights:
            w = weights[_ekey]
        elif ":" in _ekey and _ekey.split(":", 1)[1] in weights:
            w = weights[_ekey.split(":", 1)[1]]
        else:
            w = default_w
        weights_used[engine] = w
        per_engine_counts[engine] = len(cands)
        for rank0, cand in enumerate(cands):
            url = _url_of(cand)
            if not url:
                continue
            rank = rank0 + 1  # 1-based rank
            scores[url] = scores.get(url, 0.0) + (w / (k + rank))
            if url not in first_seen:
                first_seen[url] = cand
                first_ordinal[url] = ordinal
                ordinal += 1

    # Sort by score DESC, then by first-seen ordinal ASC (stable, deterministic)
    fused_urls = sorted(
        first_seen.keys(),
        key=lambda u: (-scores[u], first_ordinal[u], u),
    )
    fused = [first_seen[u] for u in fused_urls]

    n_backends = len(per_engine_counts)
    logger.info("[wrrf] fused %d backends -> %d ranked candidates", n_backends, len(fused))

    return WrrfResult(
        fused=fused,
        scores=scores,
        per_engine_counts=per_engine_counts,
        n_unique=len(fused),
        k_used=k,
        weights_used=weights_used,
    )
