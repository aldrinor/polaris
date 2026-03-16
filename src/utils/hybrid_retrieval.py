#!/usr/bin/env python3
"""
POLARIS Hybrid Retrieval Module
================================
Combines dense (embedding) and sparse (BM25) retrieval for better recall.

Hybrid retrieval is a SOTA technique that leverages:
1. Dense retrieval: Semantic similarity via embeddings
2. Sparse retrieval: Exact keyword matching via BM25/TF-IDF

This addresses the limitations of each approach:
- Dense: May miss exact keyword matches
- Sparse: May miss semantic relationships

Usage:
    from src.utils.hybrid_retrieval import HybridRetriever, hybrid_search

    retriever = HybridRetriever()
    results = retriever.search(
        query="pathogen contamination in water filters",
        documents=chunk_texts,
        top_k=20,
    )
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# BM25 IMPLEMENTATION
# =============================================================================

class BM25:
    """
    BM25 (Best Matching 25) implementation.

    BM25 is a probabilistic ranking function used for keyword-based retrieval.
    It extends TF-IDF by adding document length normalization.

    Parameters:
        k1: Term frequency saturation parameter (default: 1.5)
        b: Document length normalization (default: 0.75)
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """Initialize BM25 with parameters."""
        self.k1 = k1
        self.b = b
        self.corpus_size = 0
        self.avgdl = 0.0
        self.doc_freqs: Dict[str, int] = {}  # term -> document frequency
        self.idf: Dict[str, float] = {}  # term -> IDF score
        self.doc_lens: List[int] = []  # document lengths
        self.tokenized_corpus: List[List[str]] = []  # tokenized documents

    def _tokenize(self, text: str) -> List[str]:
        """
        Tokenize text into terms.

        Simple tokenization with lowercasing and basic cleaning.
        """
        # Lowercase and extract words
        text = text.lower()
        tokens = re.findall(r'\b[a-z0-9]{2,}\b', text)
        return tokens

    def fit(self, corpus: List[str]) -> "BM25":
        """
        Fit BM25 on a corpus of documents.

        Args:
            corpus: List of document strings

        Returns:
            Self for chaining
        """
        self.corpus_size = len(corpus)
        self.tokenized_corpus = [self._tokenize(doc) for doc in corpus]
        self.doc_lens = [len(doc) for doc in self.tokenized_corpus]
        self.avgdl = sum(self.doc_lens) / self.corpus_size if self.corpus_size > 0 else 0

        # Calculate document frequencies
        self.doc_freqs = {}
        for doc_tokens in self.tokenized_corpus:
            unique_tokens = set(doc_tokens)
            for token in unique_tokens:
                self.doc_freqs[token] = self.doc_freqs.get(token, 0) + 1

        # Calculate IDF scores
        self.idf = {}
        for term, freq in self.doc_freqs.items():
            # IDF formula: log((N - n + 0.5) / (n + 0.5))
            idf = math.log((self.corpus_size - freq + 0.5) / (freq + 0.5) + 1)
            self.idf[term] = idf

        return self

    def get_scores(self, query: str) -> List[float]:
        """
        Calculate BM25 scores for all documents given a query.

        Args:
            query: Search query string

        Returns:
            List of scores (one per document)
        """
        query_tokens = self._tokenize(query)
        scores = []

        for idx, doc_tokens in enumerate(self.tokenized_corpus):
            score = 0.0
            doc_len = self.doc_lens[idx]
            doc_term_freqs = Counter(doc_tokens)

            for term in query_tokens:
                if term not in self.idf:
                    continue

                tf = doc_term_freqs.get(term, 0)
                idf = self.idf[term]

                # BM25 formula
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
                score += idf * numerator / denominator

            scores.append(score)

        return scores

    def get_top_k(self, query: str, k: int = 10) -> List[Tuple[int, float]]:
        """
        Get top-k documents for a query.

        Args:
            query: Search query
            k: Number of results

        Returns:
            List of (doc_index, score) tuples sorted by score descending
        """
        scores = self.get_scores(query)
        indexed_scores = list(enumerate(scores))
        indexed_scores.sort(key=lambda x: x[1], reverse=True)
        return indexed_scores[:k]


# =============================================================================
# HYBRID RETRIEVER
# =============================================================================

@dataclass
class RetrievalResult:
    """Result from hybrid retrieval."""
    doc_index: int
    document: str
    dense_score: float
    sparse_score: float
    combined_score: float
    metadata: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_index": self.doc_index,
            "document": self.document[:200] + "..." if len(self.document) > 200 else self.document,
            "dense_score": round(self.dense_score, 4),
            "sparse_score": round(self.sparse_score, 4),
            "combined_score": round(self.combined_score, 4),
            "metadata": self.metadata,
        }


class HybridRetriever:
    """
    Hybrid retrieval combining dense and sparse methods.

    Fusion methods:
    - RRF (Reciprocal Rank Fusion): Combines by reciprocal ranks
    - Linear: Weighted sum of normalized scores
    """

    def __init__(
        self,
        dense_weight: float = 0.6,
        sparse_weight: float = 0.4,
        fusion_method: str = "rrf",  # "rrf" or "linear"
        rrf_k: int = 60,  # RRF constant
    ):
        """
        Initialize hybrid retriever.

        Args:
            dense_weight: Weight for dense scores (0-1)
            sparse_weight: Weight for sparse scores (0-1)
            fusion_method: "rrf" or "linear"
            rrf_k: Constant for RRF fusion
        """
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight
        self.fusion_method = fusion_method
        self.rrf_k = rrf_k
        self.bm25: Optional[BM25] = None
        self._corpus: List[str] = []
        self._metadata: List[Dict[str, Any]] = []

    def index(
        self,
        documents: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> "HybridRetriever":
        """
        Index documents for retrieval.

        Args:
            documents: List of document strings
            metadata: Optional list of metadata dicts per document

        Returns:
            Self for chaining
        """
        self._corpus = documents
        self._metadata = metadata or [{} for _ in documents]

        # Build BM25 index
        self.bm25 = BM25()
        self.bm25.fit(documents)

        return self

    def _get_dense_scores(
        self,
        query: str,
        embedding_model: Any = None,
    ) -> List[float]:
        """
        Get dense retrieval scores.

        If no embedding model provided, uses keyword overlap as fallback.
        """
        if embedding_model is not None:
            # Use actual embedding model
            try:
                query_embedding = embedding_model.encode(query)
                doc_embeddings = embedding_model.encode(self._corpus)

                # Cosine similarity
                scores = []
                for doc_emb in doc_embeddings:
                    # Normalize
                    query_norm = sum(x**2 for x in query_embedding) ** 0.5
                    doc_norm = sum(x**2 for x in doc_emb) ** 0.5
                    if query_norm > 0 and doc_norm > 0:
                        dot_product = sum(q * d for q, d in zip(query_embedding, doc_emb))
                        score = dot_product / (query_norm * doc_norm)
                    else:
                        score = 0.0
                    scores.append(score)
                return scores
            except (AttributeError, TypeError, ValueError) as e:
                # Embedding model failed, fall through to keyword fallback
                print(f"[HYBRID] Embedding model failed, using keyword fallback: {e}")

        # Fallback: Use keyword overlap with position weighting
        query_tokens = set(re.findall(r'\b[a-z0-9]{3,}\b', query.lower()))
        scores = []

        for doc in self._corpus:
            doc_tokens = set(re.findall(r'\b[a-z0-9]{3,}\b', doc.lower()))
            overlap = len(query_tokens & doc_tokens)
            # Normalize by query size
            score = overlap / len(query_tokens) if query_tokens else 0.0
            scores.append(score)

        return scores

    def search(
        self,
        query: str,
        top_k: int = 20,
        embedding_model: Any = None,
        rerank: bool = False,
    ) -> List[RetrievalResult]:
        """
        Search documents using hybrid retrieval.

        Args:
            query: Search query
            top_k: Number of results to return
            embedding_model: Optional embedding model for dense retrieval
            rerank: If True, re-rank results by combined score

        Returns:
            List of RetrievalResult objects
        """
        if not self._corpus:
            return []

        # Get dense scores
        dense_scores = self._get_dense_scores(query, embedding_model)

        # Get sparse scores (BM25)
        sparse_scores = self.bm25.get_scores(query) if self.bm25 else [0.0] * len(self._corpus)

        # Normalize scores
        dense_norm = self._normalize_scores(dense_scores)
        sparse_norm = self._normalize_scores(sparse_scores)

        # Combine scores
        if self.fusion_method == "rrf":
            combined = self._rrf_fusion(dense_norm, sparse_norm)
        else:
            combined = self._linear_fusion(dense_norm, sparse_norm)

        # Create results
        results = []
        for idx in range(len(self._corpus)):
            results.append(RetrievalResult(
                doc_index=idx,
                document=self._corpus[idx],
                dense_score=dense_norm[idx],
                sparse_score=sparse_norm[idx],
                combined_score=combined[idx],
                metadata=self._metadata[idx] if idx < len(self._metadata) else {},
            ))

        # Sort by combined score
        results.sort(key=lambda x: x.combined_score, reverse=True)

        return results[:top_k]

    def _normalize_scores(self, scores: List[float]) -> List[float]:
        """Normalize scores to 0-1 range."""
        if not scores:
            return []
        min_score = min(scores)
        max_score = max(scores)
        range_score = max_score - min_score

        if range_score == 0:
            return [0.5] * len(scores)

        return [(s - min_score) / range_score for s in scores]

    def _linear_fusion(
        self,
        dense_scores: List[float],
        sparse_scores: List[float],
    ) -> List[float]:
        """Linear weighted combination of scores."""
        combined = []
        for d, s in zip(dense_scores, sparse_scores):
            score = self.dense_weight * d + self.sparse_weight * s
            combined.append(score)
        return combined

    def _rrf_fusion(
        self,
        dense_scores: List[float],
        sparse_scores: List[float],
    ) -> List[float]:
        """Reciprocal Rank Fusion of scores."""
        # Get ranks (1-indexed, lower score = higher rank)
        n = len(dense_scores)

        # Sort indices by score to get ranks
        dense_ranks = self._get_ranks(dense_scores)
        sparse_ranks = self._get_ranks(sparse_scores)

        # RRF formula: sum(1 / (k + rank))
        combined = []
        for idx in range(n):
            rrf_score = (
                1.0 / (self.rrf_k + dense_ranks[idx]) +
                1.0 / (self.rrf_k + sparse_ranks[idx])
            )
            combined.append(rrf_score)

        return combined

    def _get_ranks(self, scores: List[float]) -> List[int]:
        """Convert scores to ranks (1-indexed, higher score = rank 1)."""
        indexed = list(enumerate(scores))
        indexed.sort(key=lambda x: x[1], reverse=True)

        ranks = [0] * len(scores)
        for rank, (idx, _) in enumerate(indexed, 1):
            ranks[idx] = rank

        return ranks


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def hybrid_search(
    query: str,
    documents: List[str],
    top_k: int = 20,
    dense_weight: float = 0.6,
    sparse_weight: float = 0.4,
    metadata: Optional[List[Dict[str, Any]]] = None,
) -> List[RetrievalResult]:
    """
    Perform hybrid search on documents.

    Convenience function for one-off searches.

    Args:
        query: Search query
        documents: List of document strings
        top_k: Number of results
        dense_weight: Weight for dense scores
        sparse_weight: Weight for sparse scores
        metadata: Optional metadata per document

    Returns:
        List of RetrievalResult objects
    """
    retriever = HybridRetriever(
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
    )
    retriever.index(documents, metadata)
    return retriever.search(query, top_k=top_k)


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("HYBRID RETRIEVAL MODULE SELF-TEST")
    print("=" * 60)

    # Test documents
    documents = [
        "Water filters remove bacteria and pathogens from drinking water using activated carbon.",
        "E. coli contamination in household water can be reduced by 99% using proper filtration.",
        "The EPA recommends NSF-certified water filters for safe drinking water.",
        "Market research shows water filter sales growing at 8% CAGR globally.",
        "Reverse osmosis membranes achieve high pathogen removal rates.",
        "Climate change affects water quality in North America and Europe.",
        "Bacteria in untreated water can cause serious gastrointestinal illness.",
        "Water purification systems must meet safety standards set by regulatory agencies.",
    ]

    # Test queries
    queries = [
        "bacteria removal rates in water filters",
        "EPA water filter regulations",
        "market size water industry",
    ]

    print("\n[TEST] BM25 Retrieval:")
    bm25 = BM25()
    bm25.fit(documents)

    for query in queries:
        results = bm25.get_top_k(query, k=3)
        print(f"\n  Query: '{query}'")
        for idx, score in results:
            doc_preview = documents[idx][:50] + "..."
            print(f"    [{idx}] Score: {score:.3f} - {doc_preview}")

    print("\n[TEST] Hybrid Retrieval (RRF):")
    retriever = HybridRetriever(fusion_method="rrf")
    retriever.index(documents)

    for query in queries:
        results = retriever.search(query, top_k=3)
        print(f"\n  Query: '{query}'")
        for r in results:
            doc_preview = r.document[:50] + "..."
            print(f"    [{r.doc_index}] Combined: {r.combined_score:.3f} (dense={r.dense_score:.2f}, sparse={r.sparse_score:.2f})")
            print(f"          {doc_preview}")

    print("\n[TEST] Hybrid Retrieval (Linear):")
    retriever_linear = HybridRetriever(
        fusion_method="linear",
        dense_weight=0.5,
        sparse_weight=0.5,
    )
    retriever_linear.index(documents)

    for query in queries[:1]:  # Just first query
        results = retriever_linear.search(query, top_k=3)
        print(f"\n  Query: '{query}'")
        for r in results:
            print(f"    [{r.doc_index}] Combined: {r.combined_score:.3f}")

    print("\n" + "=" * 60)
    print("SELF-TEST COMPLETE")
    print("=" * 60)
