"""
Mesh lethal retrieval — 6-stage algorithm (FIX D3, S5, S8).

Surfaces the most relevant claims from the workspace for a given
question, using vector KNN, entity expansion, edge walking, and a
multi-factor re-ranking score with bounded snowball feedback.

v1 design (CP-A lock):

  - Stage 0 (coreference): skipped — accepts optional `resolved_question`
    parameter for Unit 7 integration. Raw question used when absent.
  - Stage 1 (semantic seed): KNN over ALL tiers (GOLD/SILVER/BRONZE).
    BRONZE included because graph edges can promote them.
  - Stage 2 (entity expansion): simple string matching, no LLM. FIX D2
    quarantine gate + FIX S5 cosine filter apply.
  - Stage 3 (corroboration walk): 1-hop walk via corroboration edges.
  - Stage 4 (contradiction surface): always include contradicting claims.
  - Stage 5 (elaboration follow): structurally present, no-op until v2
    creates `elaborates` edges.
  - Stage 6 (lethal re-rank): snowball formulas from snowball.py +
    source authority + entity match + recency. 10% exploration budget
    for unseen GOLD claims (FIX D3).

  All stages are synchronous (no LLM calls in v1).
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import date, datetime

import numpy as np

from ..snowball import (
    contradiction_penalty,
    corroboration_factor,
    upload_gravity_boost,
    usage_bonus,
)
from ..store import EMBEDDING_DIM, MeshStore, MeshStoreError

logger = logging.getLogger(__name__)

# ───── constants ─────

SEED_K = int(os.getenv("PG_LETHAL_SEED_K", "80"))
ENTITY_COSINE_MIN = float(os.getenv("PG_ENTITY_COSINE_MIN", "0.50"))
CORROBORATION_WALK_LIMIT = int(os.getenv("PG_CORROBORATION_WALK_LIMIT", "5"))
CORROBORATION_WALK_MIN_WEIGHT = 0.6
CORROBORATION_WALK_DECAY = 0.7
CONTRADICTION_BASE_SCORE = 0.3
ELABORATION_FOLLOW_LIMIT = 3
ELABORATION_FOLLOW_DECAY = 0.5
ELABORATION_TOP_N = 20
EXPLORATION_FRACTION = 0.10


# ───── result container ─────

class RetrievalResult:
    __slots__ = (
        "scored_claims", "gap_category", "seed_count",
        "entity_expansion_count", "walked_count", "exploration_count",
    )

    def __init__(self) -> None:
        self.scored_claims: list[tuple[str, float]] = []
        self.gap_category: str = "ORTHOGONAL"
        self.seed_count: int = 0
        self.entity_expansion_count: int = 0
        self.walked_count: int = 0
        self.exploration_count: int = 0

    def claim_ids(self) -> list[str]:
        return [cid for cid, _ in self.scored_claims]

    def as_dict(self) -> dict:
        return {
            "claim_count": len(self.scored_claims),
            "scored_claims": list(self.scored_claims),
            "gap_category": self.gap_category,
            "seed_count": self.seed_count,
            "entity_expansion_count": self.entity_expansion_count,
            "walked_count": self.walked_count,
            "exploration_count": self.exploration_count,
        }


# ───── public API ─────

def lethal_retrieve(
    store: MeshStore,
    *,
    workspace_id: str,
    question_text: str,
    K: int = 40,
    resolved_question: str | None = None,
    question_embedding: np.ndarray | None = None,
) -> RetrievalResult:
    """
    6-stage lethal retrieval.

    Parameters
    ----------
    store : MeshStore
    workspace_id : str
    question_text : str
        The raw user question.
    K : int
        Total number of claims to return.
    resolved_question : str | None
        Coreference-resolved question (from Unit 7). If None, uses
        `question_text` directly.
    question_embedding : np.ndarray | None
        Pre-computed embedding for the question. If None, embeds via
        `embed_texts`. Tests pass this to avoid loading the real model.

    Returns
    -------
    RetrievalResult
    """
    ws = store.get_workspace(workspace_id)
    if ws is None:
        raise MeshStoreError(f"Workspace not found: {workspace_id}")

    result = RetrievalResult()
    effective_question = resolved_question or question_text

    # ── Embed the question ──
    if question_embedding is not None:
        q_emb = np.asarray(question_embedding, dtype=np.float32)
    else:
        q_emb = _embed_question(effective_question)

    # ══════ STAGE 1: semantic seed ══════
    seeds_raw = store.search_claims_by_vector(
        workspace_id=workspace_id,
        query_embedding=q_emb,
        k=SEED_K,
        tier_filter=("GOLD", "SILVER", "BRONZE"),
        include_flagged=False,
    )
    pool: dict[str, float] = {}
    for claim_id, distance in seeds_raw:
        cosine = _distance_to_cosine(distance)
        pool[claim_id] = max(pool.get(claim_id, 0.0), cosine)
    result.seed_count = len(pool)

    # ══════ STAGE 2: entity expansion (FIX D2 + S5) ══���═══
    q_entities = _extract_question_entities(store, workspace_id, effective_question)
    if q_entities:
        entity_claims = _find_claims_by_entities(
            store, workspace_id, q_entities,
        )
        added = 0
        for clm_id in entity_claims:
            if clm_id in pool:
                continue
            clm_emb = _read_claim_embedding(store, clm_id)
            if clm_emb is None:
                continue
            cos = float(np.dot(q_emb, clm_emb))
            if cos >= ENTITY_COSINE_MIN:
                pool[clm_id] = max(pool.get(clm_id, 0.0), cos)
                added += 1
        result.entity_expansion_count = added

    # ══════ STAGE 3: corroboration walk (1 hop) ══════
    walked_additions = 0
    for claim_id, score in list(pool.items()):
        edges = store.get_edges_from(
            claim_id,
            kind="corroborates",
            min_evidence_weight=CORROBORATION_WALK_MIN_WEIGHT,
        )
        for edge in edges[:CORROBORATION_WALK_LIMIT]:
            nb_id = edge["claim_b"]
            composite = edge["effective"]
            propagated = score * composite * CORROBORATION_WALK_DECAY
            if pool.get(nb_id, 0.0) < propagated:
                pool[nb_id] = propagated
                walked_additions += 1
    result.walked_count = walked_additions

    # ══════ STAGE 4: contradiction surface ══��═══
    for claim_id in list(pool.keys()):
        contras = store.get_edges_from(claim_id, kind="contradicts")
        for edge in contras:
            c_id = edge["claim_b"]
            pool[c_id] = max(
                pool.get(c_id, 0.0), CONTRADICTION_BASE_SCORE,
            )

    # ══════ STAGE 5: elaboration follow (no-op until v2 edges) ══════
    top_claims = sorted(pool.items(), key=lambda x: -x[1])[:ELABORATION_TOP_N]
    for claim_id, score in top_claims:
        elabs = store.get_edges_from(
            claim_id, kind="elaborates",
        )
        for edge in elabs[:ELABORATION_FOLLOW_LIMIT]:
            e_id = edge["claim_b"]
            propagated = score * float(edge["evidence_weight"]) * ELABORATION_FOLLOW_DECAY
            pool[e_id] = max(pool.get(e_id, 0.0), propagated)

    # ══════ STAGE 6: lethal re-rank ══════
    today = date.today()
    lethal_scored: list[tuple[str, float]] = []

    for claim_id, base_score in pool.items():
        claim = store.get_claim(claim_id)
        if claim is None:
            continue
        source = store.get_source(claim["source_page_id"])
        sig_authority = float(source["sig_authority"]) if source else 0.5

        corr_count = _count_edges(store, claim_id, "corroborates")
        has_contra = _count_edges(store, claim_id, "contradicts") > 0

        times_used_val = int(claim.get("times_used", 0) or 0)
        extracted_at = claim.get("extracted_at")
        if extracted_at:
            try:
                dt = datetime.fromisoformat(str(extracted_at))
                age_days = (today - dt.date()).days
            except (ValueError, TypeError):
                age_days = 0
        else:
            age_days = 0

        is_upload = (source["kind"] == "upload") if source else False
        source_year = source.get("year") if source else None

        entity_frac = _entity_match_fraction(store, claim_id, q_entities)
        recency = _recency_factor(today.year, source_year)

        lethal = (
            base_score
            * sig_authority
            * corroboration_factor(corr_count)
            * contradiction_penalty(has_contra)
            * upload_gravity_boost(is_upload)
            * (1.0 + 0.5 * entity_frac)
            * recency
            * usage_bonus(times_used_val, float(age_days))
        )
        lethal_scored.append((claim_id, lethal))

    lethal_scored.sort(key=lambda x: -x[1])

    # Main pool: top 90%
    main_k = max(1, int(K * (1.0 - EXPLORATION_FRACTION)))
    main = lethal_scored[:main_k]
    main_ids = {cid for cid, _ in main}

    # Exploration: 10% random GOLD claims never used
    exploration_k = K - len(main)
    exploration: list[tuple[str, float]] = []
    if exploration_k > 0:
        exploration = _exploration_claims(
            store, workspace_id, main_ids, exploration_k,
        )
    result.exploration_count = len(exploration)

    result.scored_claims = main + exploration

    from .gap_classify import classify_gap
    result.gap_category = classify_gap(
        seed_count=result.seed_count,
        entity_count=result.entity_expansion_count,
        total_count=len(pool),
        max_score=lethal_scored[0][1] if lethal_scored else 0.0,
    ).value

    logger.info(
        "lethal_retrieve: %d claims (seed=%d, entity=%d, walked=%d, "
        "exploration=%d, gap=%s)",
        len(result.scored_claims), result.seed_count,
        result.entity_expansion_count, result.walked_count,
        result.exploration_count, result.gap_category,
    )
    return result


# ───── helpers ─────

def _distance_to_cosine(distance: float) -> float:
    cosine = 1.0 - 0.5 * distance * distance
    return max(-1.0, min(1.0, cosine))


def _embed_question(text: str) -> np.ndarray:
    try:
        from src.utils.embedding_service import embed_texts
    except ImportError as exc:
        raise MeshStoreError(
            f"Embedding service required for retrieval ({exc}). "
            "Pass question_embedding= to skip."
        ) from exc
    vecs = embed_texts([text])
    return np.asarray(vecs[0], dtype=np.float32)


def _read_claim_embedding(
    store: MeshStore, claim_id: str,
) -> np.ndarray | None:
    mapping = store._conn.execute(
        "SELECT rowid FROM vec_claims_mapping WHERE entity_id = ?",
        (claim_id,),
    ).fetchone()
    if mapping is None:
        return None
    row = store._conn.execute(
        "SELECT embedding FROM vec_claims WHERE rowid = ?",
        (mapping["rowid"],),
    ).fetchone()
    if row is None:
        return None
    arr = np.frombuffer(row["embedding"], dtype=np.float32).copy()
    return arr if arr.shape == (EMBEDDING_DIM,) else None


def _extract_question_entities(
    store: MeshStore, workspace_id: str, question: str,
) -> list[str]:
    """
    Simple string matching: find entities whose canonical_name or
    aliases appear as substrings in the question. No LLM call.
    Returns a list of canonical entity names.
    """
    q_lower = question.lower()
    matched: list[str] = []
    rows = store._conn.execute(
        """SELECT canonical_name, aliases FROM entities
           WHERE workspace_id = ?
           AND (confidence >= 0.8 OR user_confirmed = 1)""",
        (workspace_id,),
    ).fetchall()
    for row in rows:
        canonical = row["canonical_name"]
        if canonical.lower() in q_lower:
            matched.append(canonical)
            continue
        aliases_raw = row["aliases"]
        if aliases_raw:
            try:
                aliases = json.loads(aliases_raw)
            except (ValueError, TypeError):
                continue
            for alias in aliases:
                if isinstance(alias, str) and alias.lower() in q_lower:
                    matched.append(canonical)
                    break
    return matched


def _find_claims_by_entities(
    store: MeshStore, workspace_id: str, entity_names: list[str],
) -> list[str]:
    """Find claim IDs linked to any of the given entity canonical names."""
    if not entity_names:
        return []
    placeholders = ",".join("?" * len(entity_names))
    rows = store._conn.execute(
        f"""SELECT DISTINCT ce.claim_id
            FROM claim_entities ce
            JOIN entities e ON e.id = ce.entity_id
            JOIN claims c ON c.id = ce.claim_id
            WHERE e.workspace_id = ?
            AND e.canonical_name IN ({placeholders})
            AND c.flagged = 0""",
        [workspace_id] + entity_names,
    ).fetchall()
    return [r["claim_id"] for r in rows]


def _count_edges(store: MeshStore, claim_id: str, kind: str) -> int:
    row = store._conn.execute(
        "SELECT COUNT(*) AS c FROM edges WHERE claim_a = ? AND kind = ?",
        (claim_id, kind),
    ).fetchone()
    return row["c"]


def _entity_match_fraction(
    store: MeshStore, claim_id: str, q_entities: list[str],
) -> float:
    """Fraction of this claim's entities that overlap with question entities."""
    if not q_entities:
        return 0.0
    rows = store._conn.execute(
        """SELECT e.canonical_name FROM claim_entities ce
           JOIN entities e ON e.id = ce.entity_id
           WHERE ce.claim_id = ?""",
        (claim_id,),
    ).fetchall()
    if not rows:
        return 0.0
    claim_entities = {r["canonical_name"] for r in rows}
    q_set = set(q_entities)
    overlap = len(claim_entities & q_set)
    return overlap / len(claim_entities)


def _recency_factor(current_year: int, source_year: int | None) -> float:
    """0.7 + 0.3 * exp(-(current_year - year) / 10). Always in [0.7, 1.0]."""
    year = source_year or 2020
    age = max(0, current_year - year)
    return 0.7 + 0.3 * math.exp(-age / 10.0)


def _exploration_claims(
    store: MeshStore,
    workspace_id: str,
    exclude_ids: set[str],
    k: int,
) -> list[tuple[str, float]]:
    """FIX D3: random GOLD claims never used, not in the main pool."""
    rows = store._conn.execute(
        """SELECT id FROM claims
           WHERE workspace_id = ?
           AND tier = 'GOLD'
           AND times_used = 0
           AND flagged = 0
           ORDER BY RANDOM()
           LIMIT ?""",
        (workspace_id, k * 3),
    ).fetchall()
    result: list[tuple[str, float]] = []
    for row in rows:
        if row["id"] not in exclude_ids and len(result) < k:
            result.append((row["id"], 0.5))
    return result
