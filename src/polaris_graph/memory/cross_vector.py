"""
Cross-vector knowledge sharing via ChromaDB.

Bridges the polaris_graph evidence system with the existing ChromaDB
long-term memory (src/memory/chroma_client.py).  High-quality evidence
is promoted to LTM-Global for reuse across vectors; existing knowledge
can be queried before starting a new research run.

Collection: polaris_ltm_global

This module is best-effort: if ChromaDB is unavailable the functions
degrade gracefully (log a warning, return empty/zero).
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

LTM_COLLECTION_NAME = "polaris_ltm_global"

# Quality tier ordering for comparison
_TIER_RANK = {"GOLD": 3, "SILVER": 2, "BRONZE": 1}


def _get_chroma_manager():
    """Try to obtain the existing ChromaManager singleton.

    Returns the manager instance, or None if ChromaDB is not available.
    """
    try:
        from src.memory.chroma_client import get_chroma_manager
        manager = get_chroma_manager()
        return manager
    except Exception as exc:
        logger.debug(
            "[cross_vector] ChromaManager import failed, "
            "trying local ChromaDB client: %s",
            str(exc)[:200],
        )

    # Fallback: create a local PersistentClient
    try:
        import chromadb
        from chromadb.config import Settings

        persist_dir = Path(os.getenv("CHROMA_PERSIST_DIR", "data/chroma_db"))
        persist_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=False,
            ),
        )
        return client
    except Exception as exc:
        logger.warning(
            "[cross_vector] ChromaDB not available: %s", str(exc)[:200],
        )
        return None


def _get_collection(manager):
    """Get or create the LTM-Global collection from a manager or raw client.

    Handles both ChromaManager (has .get_collection) and raw chromadb.ClientAPI.
    Returns the collection object, or None on failure.
    """
    try:
        # ChromaManager path
        if hasattr(manager, "get_collection"):
            return manager.get_collection(LTM_COLLECTION_NAME, use_embedding=True)
        # Raw chromadb client path
        if hasattr(manager, "get_or_create_collection"):
            return manager.get_or_create_collection(name=LTM_COLLECTION_NAME)
        logger.warning("[cross_vector] Unknown manager type: %s", type(manager))
        return None
    except Exception as exc:
        logger.warning(
            "[cross_vector] Failed to get collection '%s': %s",
            LTM_COLLECTION_NAME, str(exc)[:200],
        )
        return None


def _extract_domain(url: str) -> str:
    """Extract the domain from a URL for stats aggregation."""
    try:
        parsed = urlparse(url)
        return parsed.netloc or url[:60]
    except Exception:
        return url[:60] if url else ""


def promote_to_ltm(
    evidence_pieces: list[dict],
    vector_id: str,
    min_quality: str | None = None,
    min_faithfulness: float | None = None,
) -> int:
    """Promote high-quality evidence to ChromaDB LTM-Global.

    Filters evidence_pieces by quality tier and faithfulness, then
    upserts qualifying items into the polaris_ltm_global collection.

    Args:
        evidence_pieces: List of evidence dicts. Expected keys:
            evidence_id (str), statement (str), source (str/url),
            quality_tier (str), faithfulness (float), perspective (str),
            relevance_score (float).
        vector_id: Source vector identifier for provenance.
        min_quality: Minimum quality tier ('GOLD', 'SILVER', 'BRONZE').
        min_faithfulness: Minimum faithfulness score (0.0-1.0).

    Returns:
        Number of evidence pieces promoted. 0 if ChromaDB unavailable.
    """
    if not evidence_pieces:
        return 0

    # LAW VI: env var overrides for LTM promotion thresholds
    if min_quality is None:
        min_quality = os.getenv("PG_LTM_MIN_QUALITY", "GOLD")
    if min_faithfulness is None:
        try:
            min_faithfulness = float(os.getenv("PG_LTM_MIN_FAITHFULNESS", "0.9"))
        except (ValueError, TypeError):
            min_faithfulness = 0.9

    manager = _get_chroma_manager()
    if manager is None:
        logger.warning("[cross_vector] ChromaDB not available; skipping promote_to_ltm")
        return 0

    collection = _get_collection(manager)
    if collection is None:
        logger.warning("[cross_vector] Collection unavailable; skipping promote_to_ltm")
        return 0

    min_rank = _TIER_RANK.get(min_quality, 3)
    promoted = 0

    for piece in evidence_pieces:
        evidence_id = piece.get("evidence_id", "")
        if not evidence_id:
            continue

        # Quality gate
        tier = piece.get("quality_tier", "BRONZE")
        tier_rank = _TIER_RANK.get(tier, 0)
        if tier_rank < min_rank:
            continue

        # Faithfulness gate
        faithfulness = piece.get("faithfulness", 0.0)
        if faithfulness < min_faithfulness:
            continue

        statement = piece.get("statement", "")
        if not statement:
            continue

        # Build metadata (ChromaDB requires flat string/int/float values)
        source = piece.get("source", "")
        metadata = {
            "vector_id": vector_id,
            "quality_tier": tier,
            "faithfulness": float(faithfulness),
            "relevance_score": float(piece.get("relevance_score", 0.0)),
            "perspective": piece.get("perspective", ""),
            "source": source[:500] if source else "",
            "domain": _extract_domain(source),
        }

        doc_id = f"ltm_{vector_id}_{evidence_id}"

        try:
            collection.upsert(
                ids=[doc_id],
                documents=[statement],
                metadatas=[metadata],
            )
            promoted += 1
        except Exception as exc:
            logger.debug(
                "[cross_vector] Failed to upsert %s: %s",
                doc_id[:60], str(exc)[:200],
            )

    if promoted > 0:
        logger.info(
            "[cross_vector] Promoted %d/%d evidence pieces to LTM-Global for %s",
            promoted, len(evidence_pieces), vector_id[:60],
        )
    return promoted


def query_ltm(query: str, max_results: int = 20) -> list[dict]:
    """Query ChromaDB LTM-Global for existing evidence on related topics.

    Args:
        query: Natural-language query string.
        max_results: Maximum number of results (default 20).

    Returns:
        List of dicts with keys: id, statement, source, quality_tier,
        faithfulness, relevance_score, vector_id, distance.
        Empty list if ChromaDB is unavailable.
    """
    if not query:
        return []

    manager = _get_chroma_manager()
    if manager is None:
        logger.warning("[cross_vector] ChromaDB not available; query_ltm returns []")
        return []

    collection = _get_collection(manager)
    if collection is None:
        logger.warning("[cross_vector] Collection unavailable; query_ltm returns []")
        return []

    try:
        results = collection.query(
            query_texts=[query],
            n_results=max_results,
            include=["documents", "metadatas", "distances"],
        )

        if not results or not results.get("ids") or not results["ids"][0]:
            return []

        items = []
        for i, doc_id in enumerate(results["ids"][0]):
            meta = (
                results["metadatas"][0][i]
                if results.get("metadatas") and results["metadatas"][0]
                else {}
            )
            document = (
                results["documents"][0][i]
                if results.get("documents") and results["documents"][0]
                else ""
            )
            distance = (
                results["distances"][0][i]
                if results.get("distances") and results["distances"][0]
                else 1.0
            )
            items.append({
                "id": doc_id,
                "statement": document,
                "source": meta.get("source", ""),
                "quality_tier": meta.get("quality_tier", ""),
                "faithfulness": meta.get("faithfulness", 0.0),
                "relevance_score": meta.get("relevance_score", 0.0),
                "vector_id": meta.get("vector_id", ""),
                "distance": distance,
            })

        logger.debug(
            "[cross_vector] query_ltm returned %d results for '%s'",
            len(items), query[:50],
        )
        return items

    except Exception as exc:
        logger.warning(
            "[cross_vector] query_ltm failed for '%s': %s",
            query[:50], str(exc)[:200],
        )
        return []


def get_ltm_stats() -> dict:
    """Get statistics for the LTM-Global collection.

    Returns dict with keys:
        total_items (int), by_tier (dict[str, int]),
        top_domains (list[dict]), available (bool).
    """
    manager = _get_chroma_manager()
    if manager is None:
        return {
            "total_items": 0,
            "by_tier": {},
            "top_domains": [],
            "available": False,
        }

    collection = _get_collection(manager)
    if collection is None:
        return {
            "total_items": 0,
            "by_tier": {},
            "top_domains": [],
            "available": False,
        }

    try:
        total = collection.count()

        if total == 0:
            return {
                "total_items": 0,
                "by_tier": {},
                "top_domains": [],
                "available": True,
            }

        # Fetch all metadata for aggregation (capped at 10000 for safety)
        fetch_limit = min(total, 10000)
        all_items = collection.get(
            limit=fetch_limit,
            include=["metadatas"],
        )

        by_tier: dict[str, int] = {}
        domain_counts: dict[str, int] = {}

        if all_items and all_items.get("metadatas"):
            for meta in all_items["metadatas"]:
                if not meta:
                    continue
                tier = meta.get("quality_tier", "UNKNOWN")
                by_tier[tier] = by_tier.get(tier, 0) + 1

                domain = meta.get("domain", "")
                if domain:
                    domain_counts[domain] = domain_counts.get(domain, 0) + 1

        # Top 20 domains by count
        sorted_domains = sorted(
            domain_counts.items(), key=lambda x: x[1], reverse=True
        )[:20]
        top_domains = [
            {"domain": d, "count": c} for d, c in sorted_domains
        ]

        return {
            "total_items": total,
            "by_tier": by_tier,
            "top_domains": top_domains,
            "available": True,
        }

    except Exception as exc:
        logger.warning(
            "[cross_vector] get_ltm_stats failed: %s", str(exc)[:200],
        )
        return {
            "total_items": 0,
            "by_tier": {},
            "top_domains": [],
            "available": False,
        }


def list_ltm_items(limit: int = 100, offset: int = 0) -> dict:
    """List LTM-Global items with pagination.

    Returns dict with keys: items (list[dict]), total (int), limit, offset.
    """
    manager = _get_chroma_manager()
    if manager is None:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    collection = _get_collection(manager)
    if collection is None:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    try:
        total = collection.count()
        if total == 0:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}

        # ChromaDB get() with limit+offset
        result = collection.get(
            limit=limit,
            offset=offset,
            include=["documents", "metadatas"],
        )

        items = []
        if result and result.get("ids"):
            for i, doc_id in enumerate(result["ids"]):
                meta = result["metadatas"][i] if result.get("metadatas") else {}
                document = result["documents"][i] if result.get("documents") else ""
                items.append({
                    "id": doc_id,
                    "statement": document,
                    "source": (meta or {}).get("source", ""),
                    "domain": (meta or {}).get("domain", ""),
                    "quality_tier": (meta or {}).get("quality_tier", ""),
                    "faithfulness": (meta or {}).get("faithfulness", 0.0),
                    "relevance_score": (meta or {}).get("relevance_score", 0.0),
                    "vector_id": (meta or {}).get("vector_id", ""),
                    "perspective": (meta or {}).get("perspective", ""),
                })

        return {"items": items, "total": total, "limit": limit, "offset": offset}

    except Exception as exc:
        logger.warning(
            "[cross_vector] list_ltm_items failed: %s", str(exc)[:200],
        )
        return {"items": [], "total": 0, "limit": limit, "offset": offset}


def delete_ltm_item(item_id: str) -> bool:
    """Delete a specific LTM-Global item by its ID.

    Returns True if deleted, False if not found or error.
    """
    manager = _get_chroma_manager()
    if manager is None:
        logger.warning("[cross_vector] ChromaDB not available; cannot delete")
        return False

    collection = _get_collection(manager)
    if collection is None:
        return False

    try:
        # Check if item exists
        existing = collection.get(ids=[item_id])
        if not existing or not existing.get("ids") or not existing["ids"]:
            return False

        collection.delete(ids=[item_id])
        logger.info("[cross_vector] Deleted LTM item: %s", item_id[:60])
        return True

    except Exception as exc:
        logger.warning(
            "[cross_vector] delete_ltm_item failed for '%s': %s",
            item_id[:60], str(exc)[:200],
        )
        return False


# ---------------------------------------------------------------------------
# Human Override Storage (Sprint 3, A7.4)
# ---------------------------------------------------------------------------
OVERRIDE_COLLECTION_NAME = "polaris_human_overrides"


def _get_override_collection(manager):
    """Get or create the human overrides collection."""
    try:
        if hasattr(manager, "get_collection"):
            return manager.get_collection(OVERRIDE_COLLECTION_NAME, use_embedding=True)
        if hasattr(manager, "get_or_create_collection"):
            return manager.get_or_create_collection(name=OVERRIDE_COLLECTION_NAME)
        return None
    except Exception as exc:
        logger.warning(
            "[cross_vector] Failed to get override collection: %s",
            str(exc)[:200],
        )
        return None


def store_human_override(override: dict) -> bool:
    """Store a human correction in the overrides collection.

    Args:
        override: Dict with keys: override_id, vector_id, checkpoint_id,
            node, override_type, original_value, corrected_value, context.

    Returns True if stored successfully, False otherwise.
    """
    manager = _get_chroma_manager()
    if manager is None:
        logger.warning("[cross_vector] ChromaDB not available; cannot store override")
        return False

    collection = _get_override_collection(manager)
    if collection is None:
        return False

    override_id = override.get("override_id", "")
    context = override.get("context", "")
    if not override_id or not context:
        return False

    try:
        # Build document text for embedding: context + original + correction
        doc_text = (
            f"Context: {context}. "
            f"Original: {str(override.get('original_value', ''))[:500]}. "
            f"Corrected: {str(override.get('corrected_value', ''))[:500]}"
        )

        metadata = {
            "vector_id": override.get("vector_id", ""),
            "checkpoint_id": override.get("checkpoint_id", ""),
            "node": override.get("node", ""),
            "override_type": override.get("override_type", ""),
            "timestamp": override.get("timestamp", ""),
        }

        collection.upsert(
            ids=[override_id],
            documents=[doc_text],
            metadatas=[metadata],
        )
        logger.info(
            "[cross_vector] Stored human override: %s (type=%s, node=%s)",
            override_id[:40], override.get("override_type", ""), override.get("node", ""),
        )
        return True

    except Exception as exc:
        logger.warning(
            "[cross_vector] store_human_override failed: %s", str(exc)[:200],
        )
        return False


def query_human_overrides(
    query: str,
    node: Optional[str] = None,
    k: int = 5,
) -> list[dict]:
    """Find relevant human overrides for the current research context.

    Args:
        query: Research question or topic for semantic similarity search.
        node: Optional pipeline node filter (e.g., 'verify', 'analyze').
        k: Maximum number of results.

    Returns list of override dicts with keys: id, context, override_type,
        original_value, corrected_value, node, vector_id, distance.
    """
    if not query:
        return []

    manager = _get_chroma_manager()
    if manager is None:
        return []

    collection = _get_override_collection(manager)
    if collection is None:
        return []

    try:
        where_filter = None
        if node:
            where_filter = {"node": node}

        results = collection.query(
            query_texts=[query],
            n_results=k,
            include=["documents", "metadatas", "distances"],
            where=where_filter,
        )

        if not results or not results.get("ids") or not results["ids"][0]:
            return []

        items = []
        for i, doc_id in enumerate(results["ids"][0]):
            meta = (
                results["metadatas"][0][i]
                if results.get("metadatas") and results["metadatas"][0]
                else {}
            )
            document = (
                results["documents"][0][i]
                if results.get("documents") and results["documents"][0]
                else ""
            )
            distance = (
                results["distances"][0][i]
                if results.get("distances") and results["distances"][0]
                else 1.0
            )
            items.append({
                "id": doc_id,
                "context": document,
                "override_type": meta.get("override_type", ""),
                "node": meta.get("node", ""),
                "vector_id": meta.get("vector_id", ""),
                "checkpoint_id": meta.get("checkpoint_id", ""),
                "timestamp": meta.get("timestamp", ""),
                "distance": distance,
            })

        logger.debug(
            "[cross_vector] query_human_overrides returned %d results for '%s'",
            len(items), query[:50],
        )
        return items

    except Exception as exc:
        logger.warning(
            "[cross_vector] query_human_overrides failed: %s", str(exc)[:200],
        )
        return []
