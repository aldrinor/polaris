#!/usr/bin/env python3
"""
POLARIS ChromaDB Client (FIX 68 - Dual-Scope Memory)
=====================================================
Persistent vector database wrapper for VWM/LTM memory tiers.

This module provides the ChromaManager class for all vector database
operations. NO MOCKS - uses real chromadb.PersistentClient.

FIX 68 CHANGES:
- Integrated EmbeddingService singleton (FIX 67)
- Fixed duplicate promote_to_ltm_stage methods
- Fixed LTM-Stage collection naming mismatch
- Added dual-scope support: run-scoped VWM vs project-scoped LTM

Memory Tiers:
- VWM (Vector Working Memory): Per-vector session storage (RUN-SCOPED)
- LTM-Stage: Stage+region persistent storage (PROJECT-SCOPED)
- LTM-Global: Cross-stage fingerprint deduplication (PROJECT-SCOPED)

Collection Naming (FIXED):
- VWM: vwm_{vector_id}
- LTM-Stage: ltm_stage_{stage}_{region}  (NOT ltm_stage_stage_X)
- LTM-Global: ltm_global

Usage:
    from src.memory.chroma_client import ChromaManager, get_chroma_manager

    chroma = get_chroma_manager()
    chroma.register_vwm("S1V1_Household_Water_Filter_NORTH_AMERICA")
"""

import hashlib
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import chromadb
import chromadb.errors
from chromadb.config import Settings

from src.config import get_config
from src.utils.embedding_service import get_chromadb_embedding_function, EMBEDDING_DIMENSIONS

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# COLLECTION NAMES
# =============================================================================

LTM_GLOBAL_COLLECTION = "ltm_global"
LTM_STAGE_PREFIX = "ltm_stage_"
VWM_PREFIX = "vwm_"


# =============================================================================
# CHROMA MANAGER CLASS
# =============================================================================

class ChromaManager:
    """
    ChromaDB manager for POLARIS memory tiers.

    Handles VWM (working memory), LTM-Stage, and LTM-Global collections.
    Uses PersistentClient for disk-based storage.

    FIX 68: Dual-Scope Memory
    - VWM collections are RUN-SCOPED (cleared per vector)
    - LTM collections are PROJECT-SCOPED (persist across runs)
    - All collections use the same embedding function (FIX 67)
    """

    def __init__(self, persist_dir: Optional[str] = None):
        """
        Initialize ChromaManager.

        Args:
            persist_dir: Override path for ChromaDB persistence.
                         Defaults to config.env.chroma_persist_dir
        """
        self._client: Optional[chromadb.ClientAPI] = None
        self._persist_dir = persist_dir
        self._initialized = False
        self._embedding_function = None  # FIX 67: Lazy-loaded embedding function

    @property
    def persist_dir(self) -> Path:
        """Get the persistence directory path."""
        if self._persist_dir:
            return Path(self._persist_dir)
        config = get_config()
        return Path(config.env.chroma_persist_dir)

    def initialize_client(self) -> None:
        """
        Initialize the ChromaDB client (idempotent).

        Creates PersistentClient pointing to CHROMA_PERSIST_DIR.
        Safe to call multiple times - will reuse existing client.
        """
        if self._initialized and self._client is not None:
            logger.debug("ChromaDB client already initialized")
            return

        persist_path = self.persist_dir
        persist_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initializing ChromaDB client at: {persist_path}")

        self._client = chromadb.PersistentClient(
            path=str(persist_path),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            )
        )

        self._initialized = True

        # Ensure LTM-Global collection exists (after marking initialized)
        self._ensure_ltm_global()

        logger.info("ChromaDB client initialized successfully")

    def _ensure_client(self) -> chromadb.ClientAPI:
        """Ensure client is initialized and return it."""
        if not self._initialized or self._client is None:
            self.initialize_client()
        return self._client

    def _get_embedding_function(self):
        """
        Get the standardized embedding function (FIX 67).

        Returns:
            ChromaDB-compatible embedding function using all-MiniLM-L6-v2
        """
        if self._embedding_function is None:
            self._embedding_function = get_chromadb_embedding_function()
            logger.debug(f"Embedding function initialized ({EMBEDDING_DIMENSIONS} dims)")
        return self._embedding_function

    def _ensure_ltm_global(self) -> None:
        """Ensure LTM-Global collection exists with correct embedding function."""
        if self._client is None:
            raise RuntimeError("Client not initialized")
        try:
            self._client.get_or_create_collection(
                name=LTM_GLOBAL_COLLECTION,
                metadata={
                    "description": "Global fingerprint deduplication store",
                    "embedding_model": "all-MiniLM-L6-v2",
                    "embedding_dims": EMBEDDING_DIMENSIONS,
                    "scope": "project",  # FIX 68: PROJECT-SCOPED
                },
                embedding_function=self._get_embedding_function(),
            )
            logger.debug(f"LTM-Global collection ready: {LTM_GLOBAL_COLLECTION}")
        except Exception as e:
            logger.error(f"Failed to create LTM-Global collection: {e}")
            raise

    # =========================================================================
    # COLLECTION MANAGEMENT
    # =========================================================================

    def get_collection(
        self,
        name: str,
        use_embedding: bool = True,
    ) -> chromadb.Collection:
        """
        Get or create a collection by name with standardized embedding.

        FIX 68: All collections use the same embedding function for consistency.

        Args:
            name: Collection name
            use_embedding: Whether to use the standardized embedding function

        Returns:
            ChromaDB Collection object
        """
        client = self._ensure_client()
        if use_embedding:
            return client.get_or_create_collection(
                name=name,
                embedding_function=self._get_embedding_function(),
            )
        return client.get_or_create_collection(name=name)

    def delete_collection(self, name: str) -> bool:
        """
        Delete a collection if it exists.

        Args:
            name: Collection name

        Returns:
            True if deleted, False if didn't exist
        """
        client = self._ensure_client()
        try:
            client.delete_collection(name=name)
            logger.info(f"Deleted collection: {name}")
            return True
        except (ValueError, chromadb.errors.NotFoundError):
            # Collection doesn't exist
            logger.debug(f"Collection not found for deletion: {name}")
            return False
        except Exception as e:
            # Handle any other collection not found errors
            if "not exist" in str(e).lower() or "not found" in str(e).lower():
                logger.debug(f"Collection not found for deletion: {name}")
                return False
            raise

    def list_collections(self) -> List[str]:
        """List all collection names."""
        client = self._ensure_client()
        collections = client.list_collections()
        return [c.name for c in collections]

    # =========================================================================
    # VWM (Vector Working Memory) OPERATIONS
    # =========================================================================

    def get_vwm_name(self, vector_id: str) -> str:
        """Generate VWM collection name for a vector."""
        # Sanitize for ChromaDB collection name requirements
        import re
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', vector_id)
        return f"{VWM_PREFIX}{safe_id}"

    def register_vwm(self, vector_id: str) -> chromadb.Collection:
        """
        Register a new VWM collection for a vector.

        Deletes any existing collection and creates fresh.
        This ensures clean state for each vector run.

        FIX 68: VWM is RUN-SCOPED - cleared per vector.

        Args:
            vector_id: The vector ID

        Returns:
            Fresh ChromaDB Collection for the vector
        """
        collection_name = self.get_vwm_name(vector_id)

        # Delete existing to ensure clean state (RUN-SCOPED)
        self.delete_collection(collection_name)

        # Create fresh collection with standardized embedding
        client = self._ensure_client()
        collection = client.create_collection(
            name=collection_name,
            metadata={
                "vector_id": vector_id,
                "type": "vwm",
                "scope": "run",  # FIX 68: RUN-SCOPED
                "description": f"Working memory for {vector_id}",
                "embedding_model": "all-MiniLM-L6-v2",
                "embedding_dims": EMBEDDING_DIMENSIONS,
            },
            embedding_function=self._get_embedding_function(),
        )

        logger.info(f"Registered VWM collection: {collection_name}")
        return collection

    def get_vwm(self, vector_id: str) -> Optional[chromadb.Collection]:
        """
        Get existing VWM collection for a vector.

        Args:
            vector_id: The vector ID

        Returns:
            Collection if exists, None otherwise
        """
        collection_name = self.get_vwm_name(vector_id)
        client = self._ensure_client()

        try:
            return client.get_collection(
                name=collection_name,
                embedding_function=self._get_embedding_function(),
            )
        except (ValueError, chromadb.errors.NotFoundError):
            return None
        except Exception as e:
            if "not exist" in str(e).lower() or "not found" in str(e).lower():
                return None
            raise

    # =========================================================================
    # LTM-STAGE OPERATIONS (SOTA UPGRADE)
    # =========================================================================

    def get_ltm_stage_name(self, stage: int, region: str = None) -> str:
        """Generate LTM-Stage collection name with optional region."""
        if region:
            sanitized = region.lower().replace(" ", "_")
            return f"{LTM_STAGE_PREFIX}{stage}_{sanitized}"
        return f"{LTM_STAGE_PREFIX}{stage}"

    def get_ltm_stage(self, stage: int, region: str = None) -> chromadb.Collection:
        """
        Get or create LTM-Stage collection.

        SOTA: Supports stage+region specific collections for better organization.
        FIX 68: PROJECT-SCOPED - persists across runs.

        Args:
            stage: Stage number (1-13)
            region: Optional region filter (NORTH_AMERICA, EUROPE, etc.)

        Returns:
            ChromaDB Collection for the stage
        """
        collection_name = self.get_ltm_stage_name(stage, region)
        client = self._ensure_client()

        metadata = {
            "stage": stage,
            "type": "ltm_stage",
            "scope": "project",  # FIX 68: PROJECT-SCOPED
            "description": f"Long-term memory for Stage {stage}",
            "embedding_model": "all-MiniLM-L6-v2",
            "embedding_dims": EMBEDDING_DIMENSIONS,
        }
        if region:
            metadata["region"] = region

        return client.get_or_create_collection(
            name=collection_name,
            metadata=metadata,
            embedding_function=self._get_embedding_function(),
        )

    def promote_to_ltm_stage(
        self,
        vector_id: str,
        stage: int,
        region: str,
        verified_chunks: List[str],
        chunk_texts: Dict[str, str],
        chunk_metadata: Dict[str, Dict[str, Any]] = None,
    ) -> int:
        """
        Promote verified chunks from VWM to LTM-Stage.

        SOTA Implementation:
        - Only promotes verified chunks
        - Adds source tracking metadata
        - Supports region-specific LTM

        Args:
            vector_id: Source vector ID
            stage: Stage number
            region: Region string
            verified_chunks: List of verified chunk IDs
            chunk_texts: Dict mapping chunk_id to text
            chunk_metadata: Optional metadata per chunk

        Returns:
            Number of chunks promoted
        """
        if not verified_chunks:
            return 0

        ltm_collection = self.get_ltm_stage(stage, region)
        promoted = 0
        chunk_metadata = chunk_metadata or {}

        for chunk_id in verified_chunks:
            text = chunk_texts.get(chunk_id, "")
            if not text:
                continue

            # Build LTM metadata
            ltm_id = f"ltm_s{stage}_{vector_id}_{chunk_id}"
            metadata = {
                "source_vector_id": vector_id,
                "original_chunk_id": chunk_id,
                "stage": stage,
                "region": region,
                "promoted_at": datetime.now(timezone.utc).isoformat(),
                **(chunk_metadata.get(chunk_id, {})),
            }

            try:
                ltm_collection.upsert(
                    ids=[ltm_id],
                    documents=[text],
                    metadatas=[metadata],
                )
                promoted += 1
            except Exception as e:
                logger.warning(f"Failed to promote chunk {chunk_id}: {e}")

        logger.info(f"Promoted {promoted} chunks to LTM-Stage {stage} ({region})")
        return promoted

    def query_ltm_stage(
        self,
        query: str,
        stage: int,
        region: str = None,
        n_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Query LTM-Stage for relevant prior knowledge.

        Args:
            query: Query string
            stage: Stage number
            region: Optional region filter
            n_results: Number of results

        Returns:
            List of matching documents with metadata
        """
        ltm_collection = self.get_ltm_stage(stage, region)

        results = ltm_collection.query(
            query_texts=[query],
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )

        documents = []
        if results and results.get("ids") and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                documents.append({
                    "id": doc_id,
                    "text": results["documents"][0][i] if results.get("documents") else "",
                    "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                    "distance": results["distances"][0][i] if results.get("distances") else 0,
                })

        return documents

    # =========================================================================
    # LTM-GLOBAL OPERATIONS (Fingerprint Novelty)
    # =========================================================================

    def get_ltm_global(self) -> chromadb.Collection:
        """Get LTM-Global collection with standardized embedding."""
        client = self._ensure_client()
        return client.get_or_create_collection(
            name=LTM_GLOBAL_COLLECTION,
            embedding_function=self._get_embedding_function(),
        )

    def check_fingerprint_novelty(
        self,
        fingerprint: str,
        stage: Optional[int] = None,
        region: Optional[str] = None,
    ) -> Tuple[str, Optional[str], Optional[float]]:
        """
        Check if a fingerprint is novel (not duplicate).

        Queries LTM-Global for matching or similar fingerprints.

        Args:
            fingerprint: SHA256 hash of the question
            stage: Optional stage filter
            region: Optional region filter

        Returns:
            Tuple of (status, peer_vector_id, similarity_score)
            status: "proceed" | "duplicate" | "near_duplicate"
        """
        collection = self.get_ltm_global()

        # Check for exact match first
        results = collection.get(
            ids=[fingerprint],
            include=["metadatas"]
        )

        if results and results["ids"]:
            # Exact duplicate found
            metadata = results["metadatas"][0] if results["metadatas"] else {}
            peer_id = metadata.get("vector_id", "unknown")
            logger.warning(f"Duplicate fingerprint found: {peer_id}")
            return "duplicate", peer_id, 1.0

        # Query for similar fingerprints (if embeddings exist)
        try:
            # Generate a pseudo-embedding from fingerprint for similarity search
            # In production, this would use the actual question embedding
            query_results = collection.query(
                query_texts=[fingerprint],
                n_results=5,
                include=["metadatas", "distances"]
            )

            if query_results and query_results["distances"]:
                distances = query_results["distances"][0]
                if distances and len(distances) > 0:
                    min_distance = min(distances)
                    # ChromaDB returns L2 distance; convert to similarity
                    similarity = 1.0 / (1.0 + min_distance)

                    if similarity > 0.95:
                        idx = distances.index(min_distance)
                        metadata = query_results["metadatas"][0][idx]
                        peer_id = metadata.get("vector_id", "unknown")
                        logger.warning(f"Near-duplicate found: {peer_id} (sim={similarity:.3f})")
                        return "near_duplicate", peer_id, similarity

        except Exception as e:
            # Query failed - likely no embeddings yet, proceed
            logger.debug(f"Similarity query skipped: {e}")

        # No duplicates found
        return "proceed", None, None

    def register_fingerprint(
        self,
        fingerprint: str,
        vector_id: str,
        question: str,
        stage: int,
        region: str,
    ) -> None:
        """
        Register a fingerprint in LTM-Global.

        Args:
            fingerprint: SHA256 hash of the question
            vector_id: Vector ID
            question: The full question text
            stage: Stage number
            region: Region string
        """
        collection = self.get_ltm_global()

        collection.add(
            ids=[fingerprint],
            documents=[question],
            metadatas=[{
                "vector_id": vector_id,
                "stage": stage,
                "region": region,
                "fingerprint": fingerprint,
            }]
        )

        logger.info(f"Registered fingerprint for {vector_id}")

    # =========================================================================
    # DOCUMENT OPERATIONS
    # =========================================================================

    def add_document(
        self,
        collection_name: str,
        doc_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
    ) -> None:
        """
        Add a document to a collection.

        Args:
            collection_name: Target collection
            doc_id: Unique document ID
            content: Document text content
            metadata: Optional metadata dict
            embedding: Optional pre-computed embedding
        """
        collection = self.get_collection(collection_name)

        add_kwargs = {
            "ids": [doc_id],
            "documents": [content],
        }

        if metadata:
            add_kwargs["metadatas"] = [metadata]

        if embedding:
            add_kwargs["embeddings"] = [embedding]

        collection.add(**add_kwargs)
        logger.debug(f"Added document {doc_id} to {collection_name}")

    def add_documents(
        self,
        collection_name: str,
        doc_ids: List[str],
        contents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        embeddings: Optional[List[List[float]]] = None,
    ) -> None:
        """
        Add multiple documents to a collection.

        Args:
            collection_name: Target collection
            doc_ids: List of document IDs
            contents: List of document texts
            metadatas: Optional list of metadata dicts
            embeddings: Optional list of embeddings
        """
        collection = self.get_collection(collection_name)

        add_kwargs = {
            "ids": doc_ids,
            "documents": contents,
        }

        if metadatas:
            add_kwargs["metadatas"] = metadatas

        if embeddings:
            add_kwargs["embeddings"] = embeddings

        collection.add(**add_kwargs)
        logger.debug(f"Added {len(doc_ids)} documents to {collection_name}")

    def query(
        self,
        collection_name: str,
        query_text: str,
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
        include: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Query a collection for similar documents.

        Args:
            collection_name: Collection to query
            query_text: Query string
            n_results: Number of results to return
            where: Optional metadata filter
            include: Fields to include (metadatas, documents, distances)

        Returns:
            Query results dict
        """
        collection = self.get_collection(collection_name)

        query_kwargs = {
            "query_texts": [query_text],
            "n_results": n_results,
        }

        if where:
            query_kwargs["where"] = where

        if include:
            query_kwargs["include"] = include
        else:
            query_kwargs["include"] = ["metadatas", "documents", "distances"]

        return collection.query(**query_kwargs)

    def get_document(
        self,
        collection_name: str,
        doc_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific document by ID.

        Args:
            collection_name: Collection name
            doc_id: Document ID

        Returns:
            Document dict or None if not found
        """
        collection = self.get_collection(collection_name)

        results = collection.get(
            ids=[doc_id],
            include=["metadatas", "documents"]
        )

        if results and results["ids"]:
            return {
                "id": results["ids"][0],
                "content": results["documents"][0] if results["documents"] else None,
                "metadata": results["metadatas"][0] if results["metadatas"] else None,
            }

        return None

    def count(self, collection_name: str) -> int:
        """Get document count in a collection."""
        collection = self.get_collection(collection_name)
        return collection.count()

    # =========================================================================
    # CLEANUP
    # =========================================================================

    def reset(self) -> None:
        """
        Reset the entire database.

        WARNING: Deletes all data! Use only for testing.
        """
        client = self._ensure_client()
        client.reset()
        logger.warning("ChromaDB reset - all data deleted")

    def cleanup_vwm(self, vector_id: str) -> None:
        """Delete VWM collection for a vector after processing."""
        collection_name = self.get_vwm_name(vector_id)
        self.delete_collection(collection_name)

    # =========================================================================
    # SOTA FIX: Issues #47-50 - Memory Architecture Improvements
    # =========================================================================

    def deduplicate_entities(
        self,
        entities: List[Dict[str, Any]],
        similarity_threshold: float = 0.9,
    ) -> List[Dict[str, Any]]:
        """
        Deduplicate entities by name similarity.

        SOTA FIX: Issue #49 - Entity deduplication in graph.

        Args:
            entities: List of entity dicts with 'name' key
            similarity_threshold: Threshold for considering duplicates

        Returns:
            Deduplicated list of entities
        """
        if not entities:
            return []

        seen_normalized = {}
        deduplicated = []

        for entity in entities:
            name = entity.get('name', '')
            if not name:
                continue

            # Normalize name
            normalized = name.lower().strip()

            # Check for exact or near-duplicate
            is_duplicate = False
            for seen_norm, seen_entity in seen_normalized.items():
                # Simple string similarity
                if normalized == seen_norm:
                    is_duplicate = True
                    break

                # Check Levenshtein-like similarity
                similarity = self._string_similarity(normalized, seen_norm)
                if similarity >= similarity_threshold:
                    is_duplicate = True
                    # Merge metadata if needed
                    if 'count' in seen_entity:
                        seen_entity['count'] += entity.get('count', 1)
                    break

            if not is_duplicate:
                seen_normalized[normalized] = entity
                deduplicated.append(entity)

        logger.debug(
            f"Entity deduplication: {len(entities)} -> {len(deduplicated)} "
            f"({len(entities) - len(deduplicated)} duplicates removed)"
        )
        return deduplicated

    def _string_similarity(self, s1: str, s2: str) -> float:
        """Calculate simple string similarity (0-1)."""
        if not s1 or not s2:
            return 0.0
        if s1 == s2:
            return 1.0

        # Jaccard similarity on character n-grams
        n = 3
        if len(s1) < n or len(s2) < n:
            return 1.0 if s1 == s2 else 0.0

        ngrams1 = set(s1[i:i+n] for i in range(len(s1) - n + 1))
        ngrams2 = set(s2[i:i+n] for i in range(len(s2) - n + 1))

        intersection = len(ngrams1 & ngrams2)
        union = len(ngrams1 | ngrams2)

        return intersection / union if union > 0 else 0.0

    def promote_documents_to_ltm_stage(
        self,
        vector_id: str,
        stage: int,
        region: str,
        documents: List[Dict[str, Any]],
    ) -> int:
        """
        Promote documents from VWM to LTM-Stage (simplified interface).

        FIX 68: Uses correct naming convention: ltm_stage_{stage}_{region}
        (NOT the buggy ltm_stage_stage_{stage})

        Args:
            vector_id: Vector ID
            stage: Stage number
            region: Region string (e.g., "NORTH_AMERICA")
            documents: List of document dicts with 'id', 'content', 'metadata'

        Returns:
            Number of documents promoted
        """
        if not documents:
            return 0

        # Use correct collection naming via get_ltm_stage
        ltm_collection = self.get_ltm_stage(stage, region)

        promoted = 0
        for doc in documents:
            try:
                doc_id = f"ltm_s{stage}_{vector_id}_{doc.get('id', str(promoted))}"
                metadata = doc.get('metadata', {})
                metadata['source_vector_id'] = vector_id
                metadata['stage'] = stage
                metadata['region'] = region
                metadata['promoted_at'] = datetime.now(timezone.utc).isoformat()

                ltm_collection.upsert(
                    ids=[doc_id],
                    documents=[doc.get('content', '')],
                    metadatas=[metadata],
                )
                promoted += 1
            except Exception as e:
                logger.warning(f"Failed to promote document: {e}")

        logger.info(f"Promoted {promoted} documents from VWM to LTM-Stage {stage} ({region})")
        return promoted

    def promote_to_ltm_global(
        self,
        stage: int,
        region: str = None,
        quality_threshold: float = 0.8,
    ) -> int:
        """
        Promote high-quality documents from LTM-Stage to LTM-Global.

        FIX 68: Uses correct naming convention via get_ltm_stage_name.

        Args:
            stage: Stage number to promote from
            region: Region string (uses correct naming)
            quality_threshold: Minimum quality score for promotion

        Returns:
            Number of documents promoted
        """
        # FIX 68: Use correct naming via get_ltm_stage_name
        stage_collection_name = self.get_ltm_stage_name(stage, region)
        try:
            stage_collection = self._ensure_client().get_collection(
                name=stage_collection_name,
                embedding_function=self._get_embedding_function(),
            )
        except Exception as e:
            logger.debug(f"LTM-Stage {stage_collection_name} not found, nothing to promote: {e}")
            return 0

        global_collection = self.get_ltm_global()

        # Get all documents from stage collection
        results = stage_collection.get(
            include=["metadatas", "documents"],
        )

        if not results or not results["ids"]:
            return 0

        promoted = 0
        for i, doc_id in enumerate(results["ids"]):
            metadata = results["metadatas"][i] if results["metadatas"] else {}
            quality = metadata.get("quality_score", metadata.get("relevance_score", 0.5))

            if quality >= quality_threshold:
                try:
                    global_doc_id = f"global_{doc_id}"
                    metadata["promoted_to_global_at"] = datetime.now(timezone.utc).isoformat()

                    global_collection.upsert(
                        ids=[global_doc_id],
                        documents=[results["documents"][i]] if results["documents"] else [""],
                        metadatas=[metadata],
                    )
                    promoted += 1
                except Exception as e:
                    # May already exist
                    logger.debug(f"Could not promote to global: {e}")

        logger.info(f"Promoted {promoted} documents from {stage_collection_name} to LTM-Global")
        return promoted

    def get_cross_session_context(
        self,
        query: str,
        n_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context from LTM-Global for cross-session memory.

        SOTA FIX: Issue #48 - Cross-session memory persistence.

        Args:
            query: Query text
            n_results: Number of results to retrieve

        Returns:
            List of relevant documents from global memory
        """
        global_collection = self.get_ltm_global()

        try:
            results = global_collection.query(
                query_texts=[query],
                n_results=n_results,
                include=["metadatas", "documents", "distances"],
            )

            if not results or not results["ids"] or not results["ids"][0]:
                return []

            documents = []
            for i, doc_id in enumerate(results["ids"][0]):
                documents.append({
                    "id": doc_id,
                    "content": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 1.0,
                })

            logger.debug(f"Retrieved {len(documents)} documents from LTM-Global for query")
            return documents

        except Exception as e:
            logger.warning(f"Failed to retrieve cross-session context: {e}")
            return []


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_chroma_manager: Optional[ChromaManager] = None


def get_chroma_manager() -> ChromaManager:
    """Get the singleton ChromaManager instance."""
    global _chroma_manager
    if _chroma_manager is None:
        _chroma_manager = ChromaManager()
        _chroma_manager.initialize_client()
    return _chroma_manager


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    import tempfile
    import shutil

    print("=" * 60)
    print("CHROMA CLIENT SELF-TEST")
    print("=" * 60)

    # Use temporary directory for test
    test_dir = Path(tempfile.mkdtemp(prefix="polaris_chroma_test_"))
    print(f"\nTest directory: {test_dir}")

    try:
        # Test 1: Initialize client
        print("\n[TEST 1] Initialize client...")
        manager = ChromaManager(persist_dir=str(test_dir))
        manager.initialize_client()
        print("  [PASS] Client initialized")

        # Test 2: Register VWM
        print("\n[TEST 2] Register VWM...")
        test_vector = "S1V1_Household_Water_Filter_NORTH_AMERICA"
        vwm = manager.register_vwm(test_vector)
        assert vwm is not None
        print(f"  [PASS] VWM registered: {vwm.name}")

        # Test 3: Get VWM
        print("\n[TEST 3] Get VWM...")
        vwm2 = manager.get_vwm(test_vector)
        assert vwm2 is not None
        assert vwm2.name == vwm.name
        print("  [PASS] VWM retrieved")

        # Test 4: LTM-Global exists
        print("\n[TEST 4] LTM-Global collection...")
        ltm_global = manager.get_ltm_global()
        assert ltm_global is not None
        print(f"  [PASS] LTM-Global ready: {ltm_global.name}")

        # Test 5: Check fingerprint novelty (should proceed - empty DB)
        print("\n[TEST 5] Fingerprint novelty check...")
        test_fingerprint = hashlib.sha256(b"test question").hexdigest()
        status, peer_id, sim = manager.check_fingerprint_novelty(test_fingerprint)
        assert status == "proceed"
        assert peer_id is None
        print(f"  [PASS] Novelty check returned: {status}")

        # Test 6: Register fingerprint
        print("\n[TEST 6] Register fingerprint...")
        manager.register_fingerprint(
            fingerprint=test_fingerprint,
            vector_id=test_vector,
            question="What is the test question?",
            stage=1,
            region="NORTH_AMERICA",
        )
        print("  [PASS] Fingerprint registered")

        # Test 7: Check same fingerprint (should be duplicate)
        print("\n[TEST 7] Duplicate detection...")
        status2, peer_id2, sim2 = manager.check_fingerprint_novelty(test_fingerprint)
        assert status2 == "duplicate"
        assert peer_id2 == test_vector
        print(f"  [PASS] Duplicate detected: {peer_id2}")

        # Test 8: Add and query documents
        print("\n[TEST 8] Document operations...")
        manager.add_document(
            collection_name=vwm.name,
            doc_id="doc1",
            content="This is test content about water filtration.",
            metadata={"source": "test", "type": "article"}
        )
        count = manager.count(vwm.name)
        assert count == 1
        print(f"  [PASS] Document added, count={count}")

        # Test 9: Query documents
        print("\n[TEST 9] Query documents...")
        results = manager.query(
            collection_name=vwm.name,
            query_text="water filtration",
            n_results=5
        )
        assert results and results["ids"]
        print(f"  [PASS] Query returned {len(results['ids'][0])} results")

        # Test 10: List collections
        print("\n[TEST 10] List collections...")
        collections = manager.list_collections()
        assert len(collections) >= 2  # VWM + LTM-Global
        print(f"  [PASS] Collections: {collections}")

        # Test 11: Cleanup VWM
        print("\n[TEST 11] Cleanup VWM...")
        manager.cleanup_vwm(test_vector)
        vwm3 = manager.get_vwm(test_vector)
        assert vwm3 is None
        print("  [PASS] VWM cleaned up")

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60)

    finally:
        # Cleanup test directory
        shutil.rmtree(test_dir, ignore_errors=True)
        print(f"\nTest directory cleaned up: {test_dir}")
