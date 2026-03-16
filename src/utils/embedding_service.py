#!/usr/bin/env python3
"""
POLARIS Embedding Singleton Service (FIX 67)
=============================================
Standardized embedding service for the entire POLARIS pipeline.

PROBLEM SOLVED:
- ChromaDB uses default embeddings (potentially 1536 dims)
- FIX 65 used all-MiniLM-L6-v2 (384 dims)
- Memory and agents were using different embedders = MISMATCH

SOLUTION:
- Singleton embedding service using all-MiniLM-L6-v2
- 384-dimensional embeddings
- Thread-safe initialization
- Used by both agents and ChromaManager

Usage:
    from src.utils.embedding_service import get_embedding_service, embed_text, embed_texts

    # Single text
    embedding = embed_text("What are water filter pathogens?")

    # Multiple texts (batched)
    embeddings = embed_texts(["text1", "text2", "text3"])

    # Get the service directly
    service = get_embedding_service()
    embedding = service.embed("text")
"""

import logging
import os
import platform
import threading
from typing import List, Optional

import numpy as np

# FIX-I1: Pre-set short cache path on Windows BEFORE any sentence-transformers import.
# sentence-transformers cache path too long for Windows 260-char limit → [Errno 22].
if platform.system() == "Windows":
    _short_cache = os.getenv("PG_ST_CACHE_PATH", r"C:\st_cache")
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", _short_cache)
    os.environ.setdefault("HF_HOME", _short_cache)
    os.makedirs(_short_cache, exist_ok=True)

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Model specification - DO NOT CHANGE without updating all consumers
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384

# Batch processing
DEFAULT_BATCH_SIZE = 32


# =============================================================================
# EMBEDDING SERVICE CLASS
# =============================================================================

class EmbeddingService:
    """
    Singleton embedding service for POLARIS.

    Ensures all components (agents, memory, retrieval) use identical embeddings.
    """

    _instance: Optional["EmbeddingService"] = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern with thread-safe initialization."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance

    def __init__(self):
        """Initialize the embedding model (once)."""
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return

            logger.info(f"Initializing embedding service with {EMBEDDING_MODEL_NAME}")

            try:
                from sentence_transformers import SentenceTransformer

                # FIX-127: Fix sys.stderr for piped background processes.
                # When launched via `cmd | head -N`, head closes the pipe after N lines,
                # leaving sys.stderr invalid. tqdm (used by SentenceTransformer.encode)
                # calls sys.stderr.flush() which fails with [Errno 22] Invalid argument.
                # Fix: ensure stderr is valid before model operations.
                import sys
                try:
                    sys.stderr.flush()
                except OSError:
                    import os
                    sys.stderr = open(os.devnull, 'w')
                    logger.warning("[FIX-127] sys.stderr was broken (piped process), redirected to devnull")

                self._model = SentenceTransformer(EMBEDDING_MODEL_NAME)
                self._model_name = EMBEDDING_MODEL_NAME
                self._dimensions = EMBEDDING_DIMENSIONS

                # Verify dimensions (show_progress_bar=False to avoid tqdm stderr issues)
                test_embedding = self._model.encode(
                    "test", convert_to_numpy=True, show_progress_bar=False
                )
                actual_dims = len(test_embedding)

                if actual_dims != EMBEDDING_DIMENSIONS:
                    raise RuntimeError(
                        f"Embedding dimension mismatch! "
                        f"Expected {EMBEDDING_DIMENSIONS}, got {actual_dims}"
                    )

                self._initialized = True
                logger.info(
                    f"Embedding service initialized: {EMBEDDING_MODEL_NAME} "
                    f"({EMBEDDING_DIMENSIONS} dimensions)"
                )

            except ImportError:
                logger.error(
                    "sentence-transformers not installed. "
                    "Run: pip install sentence-transformers"
                )
                raise
            except Exception as e:
                logger.error(f"Failed to initialize embedding service: {e}")
                raise

    @property
    def model_name(self) -> str:
        """Get the model name."""
        return self._model_name

    @property
    def dimensions(self) -> int:
        """Get the embedding dimensions."""
        return self._dimensions

    def embed(self, text: str) -> List[float]:
        """
        Embed a single text string.

        Args:
            text: Text to embed

        Returns:
            List of floats (384 dimensions)
        """
        if not text or not text.strip():
            # Return zero vector for empty text
            return [0.0] * self._dimensions

        embedding = self._model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

        return embedding.tolist()

    def embed_batch(
        self,
        texts: List[str],
        batch_size: int = DEFAULT_BATCH_SIZE,
        show_progress: bool = False,
    ) -> List[List[float]]:
        """
        Embed multiple texts with batching.

        Args:
            texts: List of texts to embed
            batch_size: Batch size for processing
            show_progress: Whether to show progress bar

        Returns:
            List of embeddings (each 384 dimensions)
        """
        if not texts:
            return []

        # Handle empty strings
        non_empty_indices = []
        non_empty_texts = []
        for i, text in enumerate(texts):
            if text and text.strip():
                non_empty_indices.append(i)
                non_empty_texts.append(text)

        # Embed non-empty texts
        if non_empty_texts:
            embeddings_np = self._model.encode(
                non_empty_texts,
                batch_size=batch_size,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=show_progress,
            )
        else:
            embeddings_np = np.array([])

        # Build result with zero vectors for empty strings
        result = [[0.0] * self._dimensions for _ in range(len(texts))]
        for idx, embedding in zip(non_empty_indices, embeddings_np):
            result[idx] = embedding.tolist()

        return result

    def similarity(self, text1: str, text2: str) -> float:
        """
        Calculate cosine similarity between two texts.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score (0 to 1)
        """
        emb1 = np.array(self.embed(text1))
        emb2 = np.array(self.embed(text2))

        # Embeddings are already normalized, so dot product = cosine similarity
        return float(np.dot(emb1, emb2))

    def get_chromadb_embedding_function(self):
        """
        Get a ChromaDB-compatible embedding function.

        Returns:
            Callable that ChromaDB can use for embedding
        """
        return PolarisEmbeddingFunction(self)


class PolarisEmbeddingFunction:
    """
    ChromaDB-compatible embedding function wrapper.

    This wraps our singleton embedding service for use with ChromaDB collections.
    FIX 78: Added 'name' attribute required by ChromaDB.
    FIX 79: Made name() a method (ChromaDB calls ef.name(), not ef.name).
    """

    def __init__(self, service: EmbeddingService):
        self._service = service
        # FIX 78+79: ChromaDB calls name() as a method
        self._name = f"polaris_{EMBEDDING_MODEL_NAME.replace('-', '_')}"

    def name(self) -> str:
        """Return embedding function name (required by ChromaDB)."""
        return self._name

    def __call__(self, input: List[str]) -> List[List[float]]:
        """
        ChromaDB calls this to embed documents.

        Args:
            input: List of texts to embed

        Returns:
            List of embeddings
        """
        return self._service.embed_batch(input)


# =============================================================================
# MODULE-LEVEL CONVENIENCE FUNCTIONS
# =============================================================================

_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """
    Get the singleton embedding service instance.

    Returns:
        EmbeddingService singleton
    """
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


def embed_text(text: str) -> List[float]:
    """
    Embed a single text string.

    Args:
        text: Text to embed

    Returns:
        List of floats (384 dimensions)
    """
    return get_embedding_service().embed(text)


def embed_texts(texts: List[str], batch_size: int = DEFAULT_BATCH_SIZE) -> List[List[float]]:
    """
    Embed multiple texts with batching.

    Args:
        texts: List of texts to embed
        batch_size: Batch size for processing

    Returns:
        List of embeddings
    """
    return get_embedding_service().embed_batch(texts, batch_size=batch_size)


def get_chromadb_embedding_function():
    """
    Get a ChromaDB-compatible embedding function.

    Use this when creating ChromaDB collections to ensure consistent embeddings.

    Returns:
        PolarisEmbeddingFunction instance
    """
    return get_embedding_service().get_chromadb_embedding_function()


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("EMBEDDING SERVICE SELF-TEST (FIX 67)")
    print("=" * 60)

    # Test 1: Initialize singleton
    print("\n[TEST 1] Initialize embedding service...")
    service = get_embedding_service()
    print(f"  Model: {service.model_name}")
    print(f"  Dimensions: {service.dimensions}")
    print("  [PASS] Service initialized")

    # Test 2: Singleton pattern
    print("\n[TEST 2] Verify singleton pattern...")
    service2 = get_embedding_service()
    assert service is service2, "Not a singleton!"
    print("  [PASS] Same instance returned")

    # Test 3: Single embedding
    print("\n[TEST 3] Single text embedding...")
    text = "What pathogen contamination rates exist in water filters?"
    embedding = embed_text(text)
    assert len(embedding) == 384, f"Wrong dimensions: {len(embedding)}"
    print(f"  Embedded text: '{text[:50]}...'")
    print(f"  Dimensions: {len(embedding)}")
    print("  [PASS] Correct dimensions")

    # Test 4: Batch embedding
    print("\n[TEST 4] Batch embedding...")
    texts = [
        "What bacterial biofilm formation patterns occur?",
        "What viral transmission pathways are documented?",
        "What fungal growth conditions persist?",
    ]
    embeddings = embed_texts(texts)
    assert len(embeddings) == 3, f"Wrong count: {len(embeddings)}"
    assert all(len(e) == 384 for e in embeddings), "Wrong dimensions in batch"
    print(f"  Embedded {len(texts)} texts")
    print("  [PASS] Batch embedding works")

    # Test 5: Empty text handling
    print("\n[TEST 5] Empty text handling...")
    empty_emb = embed_text("")
    assert len(empty_emb) == 384, "Empty should return zero vector"
    assert all(v == 0.0 for v in empty_emb), "Empty should be zeros"
    print("  [PASS] Empty text returns zero vector")

    # Test 6: Similarity calculation
    print("\n[TEST 6] Similarity calculation...")
    sim_same = service.similarity(
        "Water filter contamination",
        "Water filter contamination"
    )
    sim_related = service.similarity(
        "Water filter contamination",
        "Water purifier pathogens"
    )
    sim_unrelated = service.similarity(
        "Water filter contamination",
        "Stock market analysis"
    )
    print(f"  Same text similarity: {sim_same:.4f}")
    print(f"  Related texts similarity: {sim_related:.4f}")
    print(f"  Unrelated texts similarity: {sim_unrelated:.4f}")
    assert sim_same > sim_related > sim_unrelated, "Similarity ordering wrong"
    print("  [PASS] Similarity ordering correct")

    # Test 7: ChromaDB embedding function
    print("\n[TEST 7] ChromaDB embedding function...")
    chroma_ef = get_chromadb_embedding_function()
    chroma_result = chroma_ef(["test text"])
    assert len(chroma_result) == 1, "Wrong result count"
    assert len(chroma_result[0]) == 384, "Wrong dimensions"
    print("  [PASS] ChromaDB function works")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED - FIX 67 COMPLETE")
    print("=" * 60)
