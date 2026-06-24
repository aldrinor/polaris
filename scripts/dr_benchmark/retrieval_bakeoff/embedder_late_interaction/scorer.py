#!/usr/bin/env python3
"""I-ret-002 (#1294) — embedder_late_interaction layer: SCORER MATH (shared, no models).

Pure, deterministic scoring functions used by BOTH the GATE-0 scorer-math canary and the real
``run_bakeoff.py``. Keeping the math in one module means the canary validates the EXACT code
that scores candidates (the anti-drb_72 principle: the scorer cannot pass the canary and then
silently use different math on the real run).

NO model, NO network, NO GPU here. ``run_bakeoff.py`` produces the per-row vectors / MaxSim
scores; this module turns scores+labels into the two metrics:

  Axis A — AUC(on-topic > off-topic): P(score(pos) > score(neg)) over all POS-NEG pairs.
           Reused verbatim from the named seam ``scripts/relevance_scorer_bakeoff.py``
           (``auc_pos_gt_neg``) so the metric is identical to the I-arch-009 relevance gate.
  Axis B — reasoning-retrieval recall@k: per claim, is the gold supporting source within the
           top-k of the ranked candidate pool (ranked by the candidate's score)?

Single-vector candidates score a (query/claim, doc) pair by cosine of L2-normalized vectors.
Late-interaction (ColBERT/PyLate) candidates score by MaxSim over token-level vectors. Both
collapse to a single scalar per (query, doc); these functions are agnostic to which produced it.
"""
from __future__ import annotations

from typing import Optional


def auc_pos_gt_neg(pos_scores: list[float], neg_scores: list[float]) -> Optional[float]:
    """AUC = P(score(pos) > score(neg)) over all POS-NEG pairs (ties = 0.5).

    Identical semantics to scripts/relevance_scorer_bakeoff.py::auc_pos_gt_neg (the named seam).
    Returns None if either class is empty (cannot compute — never a fake 0.5).
    """
    if not pos_scores or not neg_scores:
        return None
    wins = ties = 0
    for p in pos_scores:
        for n in neg_scores:
            if p > n:
                wins += 1
            elif p == n:
                ties += 1
    return (wins + 0.5 * ties) / (len(pos_scores) * len(neg_scores))


def recall_at_k(ranked_ids: list[str], gold_ids: set[str], k: int) -> Optional[float]:
    """Fraction of gold ids present in the top-k of a ranked id list.

    ranked_ids must be ordered best-first (highest candidate score first). Returns None if there
    are no gold ids (undefined — never a fake number).
    """
    if not gold_ids:
        return None
    topk = ranked_ids[:k]
    hit = sum(1 for g in gold_ids if g in topk)
    return hit / len(gold_ids)


def rank_by_score(doc_ids: list[str], scores: list[float]) -> list[str]:
    """Return doc_ids ordered by descending score (stable for ties: input order preserved)."""
    if len(doc_ids) != len(scores):
        raise ValueError(f"doc_ids ({len(doc_ids)}) and scores ({len(scores)}) length mismatch")
    order = sorted(range(len(doc_ids)), key=lambda i: (-scores[i], i))
    return [doc_ids[i] for i in order]


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors (returns 0.0 for a zero vector — no div-by-zero)."""
    if len(a) != len(b):
        raise ValueError(f"vector length mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def maxsim(query_token_vecs: list[list[float]], doc_token_vecs: list[list[float]]) -> float:
    """ColBERT MaxSim late-interaction score (sum over query tokens of max cosine to any doc token).

    This is the canonical late-interaction operator (Khattab & Zaharia 2020; PyLate's scoring):
    for each query token, take the max cosine similarity against every document token, then sum.
    Operates on L2-normalizable vectors; ``cosine`` handles normalization implicitly.
    """
    if not query_token_vecs or not doc_token_vecs:
        return 0.0
    total = 0.0
    for q in query_token_vecs:
        best = max(cosine(q, d) for d in doc_token_vecs)
        total += best
    return total
