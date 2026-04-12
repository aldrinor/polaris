"""
Mesh edge discovery — L4 write path.

Given newly-inserted claim IDs, finds candidate edges to existing claims
in the workspace via vector KNN, applies cosine thresholds, and inserts
typed edges via store.insert_edge.

v1 design (CP-A lock):

  - Cosine-only edge typing (no NLI model in v1). This avoids the
    flan-t5-large 512-token context issue and the "NLI too strict for
    niche domains" failure mode from memory note #19.

  - Edge types (non-overlapping thresholds):

      corroborates:  cosine ≥ CORROBORATION_THRESHOLD (0.85)
                     Any source pair. High semantic similarity implies
                     the claims are making similar assertions.

      contradicts:   cosine ∈ [CONTRADICTION_THRESHOLD, CORROBORATION_THRESHOLD)
                     i.e., 0.80 ≤ cosine < 0.85, DIFFERENT sources only.
                     Without NLI we can't confirm contradiction, so this
                     is a *candidate* — the retrieval penalty (×0.7)
                     applies immediately but the user review queue flags
                     them for resolution.

      elaborates:    deferred to v2 with NLI infrastructure.

  - Edge discovery runs OUTSIDE the claim-insert transaction (separate
    pass after extraction completes). Unlike entity canonicalization,
    edge discovery does KNN over the full claim set — holding a write
    lock during that is architecturally wrong.

  - Each new claim does ONE KNN search, not N pairwise comparisons.
    KNN returns top-k candidates (EDGE_KNN_K=20), then filter by cosine
    threshold. O(k) per new claim, not O(N).

  - evidence_weight follows the design doc bounds:
      corroborates: max(EVIDENCE_WEIGHT_MIN, cosine), ∈ [0.7, 1.0]
      contradicts:  cosine directly (already in [0.80, 0.85))

  - Idempotent: re-running on the same claim IDs hits the store's
    idempotent insert_edge and returns existing edge IDs.

Integration pattern:
  After `extract_claims_from_source` returns claim IDs, the caller
  invokes `discover_edges_for_claims(store, workspace_id, claim_ids)`.
  NOT wired into claim_extract.py — separate step.
"""

from __future__ import annotations

import logging
import os

import numpy as np

from .store import EMBEDDING_DIM, MeshStore, MeshStoreError

logger = logging.getLogger(__name__)

# ───── thresholds (design doc §8, env-overridable) ─────

CORROBORATION_THRESHOLD = float(
    os.getenv("PG_CORROBORATION_THRESHOLD", "0.75"),
)
CONTRADICTION_THRESHOLD = float(
    os.getenv("PG_CONTRADICTION_THRESHOLD", "0.70"),
)
EDGE_KNN_K = int(os.getenv("PG_EDGE_KNN_K", "20"))
EVIDENCE_WEIGHT_MIN = 0.7


# ───── public API ─────

def discover_edges_for_claims(
    store: MeshStore,
    *,
    workspace_id: str,
    new_claim_ids: list[str],
    embeddings: dict[str, np.ndarray] | None = None,
) -> EdgeDiscoveryResult:
    """
    Discover corroboration and contradiction edges between *new_claim_ids*
    and all existing claims in the workspace.

    Parameters
    ----------
    store : MeshStore
        Open mesh store.
    workspace_id : str
        Workspace scope for the KNN search and edge insertion.
    new_claim_ids : list[str]
        Claim IDs that were just inserted. Edges are discovered FROM
        each new claim TO existing claims.
    embeddings : dict[str, np.ndarray] | None
        Optional precomputed claim_id → embedding map. If a claim's
        embedding is present here, we skip the vec0 read-back. Callers
        that just ran `extract_claims_from_source` already hold the
        embeddings and can pass them to avoid a round-trip.

    Returns
    -------
    EdgeDiscoveryResult
        Inserted edge IDs + per-type counts for observability.
    """
    if not new_claim_ids:
        return EdgeDiscoveryResult()

    ws = store.get_workspace(workspace_id)
    if ws is None:
        raise MeshStoreError(f"Workspace not found: {workspace_id}")

    result = EdgeDiscoveryResult()

    for claim_id in new_claim_ids:
        claim = store.get_claim(claim_id)
        if claim is None:
            logger.warning(
                "discover_edges: claim %s not found, skipping", claim_id,
            )
            result.skipped += 1
            continue
        if claim["workspace_id"] != workspace_id:
            logger.warning(
                "discover_edges: claim %s belongs to workspace %s, not %s",
                claim_id, claim["workspace_id"], workspace_id,
            )
            result.skipped += 1
            continue

        emb = (embeddings or {}).get(claim_id)
        if emb is None:
            emb = _read_claim_embedding(store, claim_id)
        if emb is None:
            logger.debug(
                "discover_edges: no embedding for %s, skipping", claim_id,
            )
            result.skipped += 1
            continue

        candidates = store.search_claims_by_vector(
            workspace_id=workspace_id,
            query_embedding=emb,
            k=EDGE_KNN_K,
            tier_filter=("GOLD", "SILVER", "BRONZE"),
            include_flagged=False,
        )

        for candidate_id, distance in candidates:
            if candidate_id == claim_id:
                continue

            cosine = _distance_to_cosine(distance)

            candidate = store.get_claim(candidate_id)
            if candidate is None:
                continue

            same_source = (
                claim["source_page_id"] == candidate["source_page_id"]
            )

            if cosine >= CORROBORATION_THRESHOLD:
                evidence_weight = max(EVIDENCE_WEIGHT_MIN, cosine)
                edge_id = store.insert_edge(
                    workspace_id=workspace_id,
                    claim_a=claim_id,
                    claim_b=candidate_id,
                    kind="corroborates",
                    evidence_weight=evidence_weight,
                    discovery_method="cosine_knn_v1",
                )
                result.edge_ids.append(edge_id)
                result.corroboration_count += 1

            elif cosine >= CONTRADICTION_THRESHOLD and not same_source:
                edge_id = store.insert_edge(
                    workspace_id=workspace_id,
                    claim_a=claim_id,
                    claim_b=candidate_id,
                    kind="contradicts",
                    evidence_weight=cosine,
                    discovery_method="cosine_knn_v1",
                )
                result.edge_ids.append(edge_id)
                result.contradiction_count += 1

    logger.info(
        "discover_edges: %d claims → %d edges "
        "(%d corroborates, %d contradicts, %d skipped)",
        len(new_claim_ids), len(result.edge_ids),
        result.corroboration_count, result.contradiction_count,
        result.skipped,
    )
    return result


# ───── result container ─────

class EdgeDiscoveryResult:
    __slots__ = (
        "edge_ids", "corroboration_count", "contradiction_count", "skipped",
    )

    def __init__(self) -> None:
        self.edge_ids: list[str] = []
        self.corroboration_count: int = 0
        self.contradiction_count: int = 0
        self.skipped: int = 0

    def as_dict(self) -> dict:
        return {
            "edge_count": len(self.edge_ids),
            "edge_ids": list(self.edge_ids),
            "corroboration_count": self.corroboration_count,
            "contradiction_count": self.contradiction_count,
            "skipped": self.skipped,
        }


# ───── helpers ─────

def _distance_to_cosine(distance: float) -> float:
    """Convert sqlite-vec L2 distance to cosine similarity for unit vectors."""
    cosine = 1.0 - 0.5 * distance * distance
    return max(-1.0, min(1.0, cosine))


def _read_claim_embedding(
    store: MeshStore, claim_id: str,
) -> np.ndarray | None:
    """
    Read back a claim's embedding from vec_claims via the mapping table.

    Returns None if the claim has no embedding (shouldn't happen for
    claims inserted through the standard path, but defensive).
    """
    mapping = store._conn.execute(
        "SELECT rowid FROM vec_claims_mapping WHERE entity_id = ?",
        (claim_id,),
    ).fetchone()
    if mapping is None:
        return None

    rowid = mapping["rowid"]
    row = store._conn.execute(
        "SELECT embedding FROM vec_claims WHERE rowid = ?",
        (rowid,),
    ).fetchone()
    if row is None:
        return None

    blob = row["embedding"]
    arr = np.frombuffer(blob, dtype=np.float32).copy()
    if arr.shape != (EMBEDDING_DIM,):
        logger.warning(
            "_read_claim_embedding: dim mismatch for %s — expected %d, got %s",
            claim_id, EMBEDDING_DIM, arr.shape,
        )
        return None
    return arr
