"""
POLARIS Content Deduplicator
============================
Detects and removes duplicate/near-duplicate content in research sources.

Features:
- MinHash-based similarity detection
- SimHash for fingerprinting
- Configurable similarity thresholds
- Duplicate cluster identification
- Original source tracking

Usage:
    from src.utils.content_deduplicator import ContentDeduplicator

    dedup = ContentDeduplicator()
    unique_chunks, duplicates = dedup.deduplicate(evidence_chunks)

    # Check similarity between two texts
    similarity = dedup.calculate_similarity(text1, text2)
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Number of hash functions for MinHash
DEFAULT_NUM_HASHES = 128

# Shingle size for text tokenization
DEFAULT_SHINGLE_SIZE = 3

# Default similarity threshold for duplicate detection
DEFAULT_SIMILARITY_THRESHOLD = 0.85


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class DeduplicationConfig:
    """Configuration for content deduplication."""

    # Similarity thresholds
    exact_match_threshold: float = 1.0
    near_duplicate_threshold: float = 0.85
    similar_threshold: float = 0.70

    # MinHash parameters
    num_hashes: int = DEFAULT_NUM_HASHES
    shingle_size: int = DEFAULT_SHINGLE_SIZE

    # Processing options
    normalize_text: bool = True
    ignore_case: bool = True
    remove_punctuation: bool = True
    remove_numbers: bool = False
    min_content_length: int = 50

    # Deduplication behavior
    keep_first: bool = True  # Keep first occurrence
    merge_metadata: bool = True  # Merge metadata from duplicates
    track_duplicates: bool = True  # Track which items are duplicates


# =============================================================================
# Data Classes
# =============================================================================

class DuplicateType(str, Enum):
    """Types of duplication."""
    EXACT = "exact"
    NEAR_DUPLICATE = "near_duplicate"
    SIMILAR = "similar"
    UNIQUE = "unique"


@dataclass
class ContentFingerprint:
    """Fingerprint for a piece of content."""
    content_hash: str  # MD5 hash for exact matching
    simhash: int  # SimHash for similarity
    minhash: List[int]  # MinHash signature
    shingles: Set[str]  # Text shingles
    word_count: int


@dataclass
class DuplicateInfo:
    """Information about a duplicate item."""
    original_index: int
    duplicate_index: int
    duplicate_type: DuplicateType
    similarity: float
    original_url: str = ""
    duplicate_url: str = ""


@dataclass
class DeduplicationResult:
    """Result of deduplication process."""

    # Unique items (after deduplication)
    unique_items: List[Dict[str, Any]] = field(default_factory=list)

    # Removed duplicates
    duplicates: List[DuplicateInfo] = field(default_factory=list)

    # Statistics
    original_count: int = 0
    unique_count: int = 0
    exact_duplicates: int = 0
    near_duplicates: int = 0
    similar_items: int = 0

    # Duplicate clusters (groups of similar items)
    clusters: List[List[int]] = field(default_factory=list)

    @property
    def deduplication_ratio(self) -> float:
        """Calculate ratio of content removed."""
        if self.original_count == 0:
            return 0.0
        return 1.0 - (self.unique_count / self.original_count)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "original_count": self.original_count,
            "unique_count": self.unique_count,
            "deduplication_ratio": round(self.deduplication_ratio, 3),
            "exact_duplicates": self.exact_duplicates,
            "near_duplicates": self.near_duplicates,
            "similar_items": self.similar_items,
            "cluster_count": len(self.clusters),
            "duplicates": [
                {
                    "original_index": d.original_index,
                    "duplicate_index": d.duplicate_index,
                    "type": d.duplicate_type.value,
                    "similarity": round(d.similarity, 3),
                }
                for d in self.duplicates
            ],
        }


# =============================================================================
# Content Deduplicator
# =============================================================================

class ContentDeduplicator:
    """
    Detects and removes duplicate/near-duplicate content.

    Uses MinHash for efficient similarity detection and SimHash
    for content fingerprinting.
    """

    def __init__(self, config: Optional[DeduplicationConfig] = None):
        """
        Initialize the deduplicator.

        Args:
            config: Deduplication configuration
        """
        self.config = config or DeduplicationConfig()
        self._hash_coefficients = self._generate_hash_coefficients()

    def deduplicate(
        self,
        items: List[Dict[str, Any]],
        content_key: str = "content",
    ) -> DeduplicationResult:
        """
        Remove duplicate content from a list of items.

        Args:
            items: List of items with content field
            content_key: Key for content field (default: "content")

        Returns:
            DeduplicationResult with unique items and duplicate info
        """
        result = DeduplicationResult(original_count=len(items))

        if not items:
            return result

        # Generate fingerprints for all items
        fingerprints = []
        for item in items:
            content = item.get(content_key, item.get("text", ""))
            fp = self._generate_fingerprint(content)
            fingerprints.append(fp)

        # Find duplicates
        is_duplicate = [False] * len(items)
        duplicate_of = [-1] * len(items)  # Index of original

        for i in range(len(items)):
            if is_duplicate[i]:
                continue

            for j in range(i + 1, len(items)):
                if is_duplicate[j]:
                    continue

                dup_type, similarity = self._check_duplicate(
                    fingerprints[i],
                    fingerprints[j],
                )

                if dup_type != DuplicateType.UNIQUE:
                    is_duplicate[j] = True
                    duplicate_of[j] = i

                    dup_info = DuplicateInfo(
                        original_index=i,
                        duplicate_index=j,
                        duplicate_type=dup_type,
                        similarity=similarity,
                        original_url=items[i].get("url", ""),
                        duplicate_url=items[j].get("url", ""),
                    )
                    result.duplicates.append(dup_info)

                    if dup_type == DuplicateType.EXACT:
                        result.exact_duplicates += 1
                    elif dup_type == DuplicateType.NEAR_DUPLICATE:
                        result.near_duplicates += 1
                    elif dup_type == DuplicateType.SIMILAR:
                        result.similar_items += 1

        # Build unique items list
        for i, item in enumerate(items):
            if not is_duplicate[i]:
                result.unique_items.append(item)

        result.unique_count = len(result.unique_items)

        # Build clusters
        result.clusters = self._build_clusters(duplicate_of, len(items))

        # Firing canary (W9): emitted ONLY when deduplicate() actually runs on
        # the real path, reporting real runtime counts (n_in -> n_out). A wired
        # consumer's run log will show this line; absence == the stage never
        # executed. Distinct from the per-duplicate-class logs above so the
        # canary fires even on a no-op (zero duplicates removed) pass.
        # SCOPE (I-wire-001 P1-2): the only callers of this method are pipeline-B/
        # agents code (CRAGRetriever via graph_v2; agents/analyst_agent;
        # polaris_graph/agents/analyzer; polaris_graph/graph) — NONE are on the
        # Gate-B sweep path (run_honest_sweep_r3 imports none of them). So this
        # canary fires for those callers only; its ABSENCE on a Gate-B run is
        # EXPECTED (W9 is build-deferred there — no consolidate-keep-all content-
        # dedup stage is wired onto the sweep evidence path yet), not a regression.
        # See run_gate_b.py W9 slate comment + the build-deferred WARNING.
        logger.info(
            "[content_dedup] deduped %d -> %d findings",
            result.original_count,
            result.unique_count,
        )

        return result

    def calculate_similarity(
        self,
        text1: str,
        text2: str,
    ) -> float:
        """
        Calculate similarity between two texts.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score (0-1)
        """
        fp1 = self._generate_fingerprint(text1)
        fp2 = self._generate_fingerprint(text2)

        return self._minhash_similarity(fp1.minhash, fp2.minhash)

    def is_duplicate(
        self,
        text1: str,
        text2: str,
        threshold: Optional[float] = None,
    ) -> bool:
        """
        Check if two texts are duplicates.

        Args:
            text1: First text
            text2: Second text
            threshold: Similarity threshold (default: near_duplicate_threshold)

        Returns:
            True if texts are duplicates
        """
        threshold = threshold or self.config.near_duplicate_threshold
        similarity = self.calculate_similarity(text1, text2)
        return similarity >= threshold

    def find_duplicates_for(
        self,
        text: str,
        items: List[Dict[str, Any]],
        content_key: str = "content",
        threshold: Optional[float] = None,
    ) -> List[Tuple[int, float]]:
        """
        Find duplicates of a text in a list of items.

        Args:
            text: Text to find duplicates for
            items: List of items to search
            content_key: Key for content field
            threshold: Similarity threshold

        Returns:
            List of (index, similarity) tuples for duplicates
        """
        threshold = threshold or self.config.near_duplicate_threshold
        duplicates = []

        fp_text = self._generate_fingerprint(text)

        for i, item in enumerate(items):
            content = item.get(content_key, item.get("text", ""))
            fp_item = self._generate_fingerprint(content)

            similarity = self._minhash_similarity(fp_text.minhash, fp_item.minhash)
            if similarity >= threshold:
                duplicates.append((i, similarity))

        return sorted(duplicates, key=lambda x: x[1], reverse=True)

    def get_unique_content(
        self,
        items: List[Dict[str, Any]],
        content_key: str = "content",
    ) -> List[Dict[str, Any]]:
        """
        Get only unique content from items (convenience method).

        Args:
            items: List of items
            content_key: Key for content field

        Returns:
            List of unique items
        """
        result = self.deduplicate(items, content_key)
        return result.unique_items

    # =========================================================================
    # Internal Methods
    # =========================================================================

    def _generate_fingerprint(self, text: str) -> ContentFingerprint:
        """Generate fingerprint for text."""
        # Normalize text
        normalized = self._normalize_text(text)

        # Generate shingles
        shingles = self._generate_shingles(normalized)

        # Generate content hash (for exact matching)
        content_hash = hashlib.md5(normalized.encode()).hexdigest()

        # Generate MinHash signature
        minhash = self._compute_minhash(shingles)

        # Generate SimHash
        simhash = self._compute_simhash(normalized)

        return ContentFingerprint(
            content_hash=content_hash,
            simhash=simhash,
            minhash=minhash,
            shingles=shingles,
            word_count=len(normalized.split()),
        )

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        if not text:
            return ""

        result = text

        if self.config.ignore_case:
            result = result.lower()

        if self.config.remove_punctuation:
            result = re.sub(r'[^\w\s]', ' ', result)

        if self.config.remove_numbers:
            result = re.sub(r'\d+', '', result)

        # Normalize whitespace
        result = ' '.join(result.split())

        return result

    def _generate_shingles(self, text: str) -> Set[str]:
        """Generate character shingles from text."""
        shingles = set()
        words = text.split()

        if len(words) < self.config.shingle_size:
            # For short text, use the whole text as a shingle
            if text:
                shingles.add(text)
            return shingles

        # Generate word-level shingles
        for i in range(len(words) - self.config.shingle_size + 1):
            shingle = ' '.join(words[i:i + self.config.shingle_size])
            shingles.add(shingle)

        return shingles

    def _generate_hash_coefficients(self) -> List[Tuple[int, int]]:
        """Generate hash function coefficients for MinHash."""
        import random
        random.seed(42)  # Deterministic for reproducibility

        max_hash = 2**32 - 1
        coefficients = []

        for _ in range(self.config.num_hashes):
            a = random.randint(1, max_hash)
            b = random.randint(0, max_hash)
            coefficients.append((a, b))

        return coefficients

    def _compute_minhash(self, shingles: Set[str]) -> List[int]:
        """Compute MinHash signature."""
        if not shingles:
            return [0] * self.config.num_hashes

        max_hash = 2**32 - 1
        signature = [max_hash] * self.config.num_hashes

        for shingle in shingles:
            shingle_hash = hash(shingle) & max_hash

            for i, (a, b) in enumerate(self._hash_coefficients):
                hash_val = (a * shingle_hash + b) % max_hash
                signature[i] = min(signature[i], hash_val)

        return signature

    def _compute_simhash(self, text: str) -> int:
        """Compute SimHash fingerprint."""
        if not text:
            return 0

        # Use 64-bit hash
        v = [0] * 64

        for word in text.split():
            h = int(hashlib.md5(word.encode()).hexdigest(), 16)
            for i in range(64):
                bit = (h >> i) & 1
                if bit:
                    v[i] += 1
                else:
                    v[i] -= 1

        simhash = 0
        for i in range(64):
            if v[i] > 0:
                simhash |= (1 << i)

        return simhash

    def _minhash_similarity(
        self,
        sig1: List[int],
        sig2: List[int],
    ) -> float:
        """Calculate Jaccard similarity from MinHash signatures."""
        if not sig1 or not sig2:
            return 0.0

        matches = sum(1 for a, b in zip(sig1, sig2) if a == b)
        return matches / len(sig1)

    def _simhash_distance(self, hash1: int, hash2: int) -> int:
        """Calculate Hamming distance between SimHash values."""
        xor = hash1 ^ hash2
        distance = 0
        while xor:
            distance += 1
            xor &= xor - 1
        return distance

    def _check_duplicate(
        self,
        fp1: ContentFingerprint,
        fp2: ContentFingerprint,
    ) -> Tuple[DuplicateType, float]:
        """Check if two fingerprints represent duplicates."""
        # Check exact match first
        if fp1.content_hash == fp2.content_hash:
            return DuplicateType.EXACT, 1.0

        # Check MinHash similarity
        similarity = self._minhash_similarity(fp1.minhash, fp2.minhash)

        if similarity >= self.config.exact_match_threshold:
            return DuplicateType.EXACT, similarity
        elif similarity >= self.config.near_duplicate_threshold:
            return DuplicateType.NEAR_DUPLICATE, similarity
        elif similarity >= self.config.similar_threshold:
            return DuplicateType.SIMILAR, similarity
        else:
            return DuplicateType.UNIQUE, similarity

    def _build_clusters(
        self,
        duplicate_of: List[int],
        total_items: int,
    ) -> List[List[int]]:
        """Build clusters of duplicate items."""
        clusters_map: Dict[int, List[int]] = defaultdict(list)

        for i in range(total_items):
            original = duplicate_of[i]
            if original == -1:
                # This is an original item
                clusters_map[i].insert(0, i)
            else:
                # This is a duplicate
                clusters_map[original].append(i)

        # Only return clusters with duplicates
        clusters = [
            indices for indices in clusters_map.values()
            if len(indices) > 1
        ]

        return clusters


# =============================================================================
# Convenience Functions
# =============================================================================

def deduplicate_content(
    items: List[Dict[str, Any]],
    content_key: str = "content",
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> Tuple[List[Dict[str, Any]], DeduplicationResult]:
    """
    Deduplicate content in a list of items.

    Args:
        items: List of items with content
        content_key: Key for content field
        threshold: Similarity threshold

    Returns:
        Tuple of (unique_items, result)
    """
    config = DeduplicationConfig(near_duplicate_threshold=threshold)
    dedup = ContentDeduplicator(config)
    result = dedup.deduplicate(items, content_key)
    return result.unique_items, result


def calculate_content_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two texts.

    Args:
        text1: First text
        text2: Second text

    Returns:
        Similarity score (0-1)
    """
    dedup = ContentDeduplicator()
    return dedup.calculate_similarity(text1, text2)


def are_duplicates(
    text1: str,
    text2: str,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> bool:
    """
    Check if two texts are duplicates.

    Args:
        text1: First text
        text2: Second text
        threshold: Similarity threshold

    Returns:
        True if texts are duplicates
    """
    dedup = ContentDeduplicator()
    return dedup.is_duplicate(text1, text2, threshold)


def get_unique_texts(
    texts: List[str],
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> List[str]:
    """
    Get unique texts from a list.

    Args:
        texts: List of texts
        threshold: Similarity threshold

    Returns:
        List of unique texts
    """
    items = [{"content": t} for t in texts]
    unique_items, _ = deduplicate_content(items, threshold=threshold)
    return [item["content"] for item in unique_items]


# =============================================================================
# Self-Test
# =============================================================================

def self_test() -> bool:
    """Run self-tests for content deduplicator."""
    print("Running Content Deduplicator self-tests...")

    # Test data
    test_items = [
        {"content": "The quick brown fox jumps over the lazy dog.", "url": "source1"},
        {"content": "The quick brown fox jumps over the lazy dog.", "url": "source2"},  # Exact dup
        {"content": "A quick brown fox jumped over a lazy dog.", "url": "source3"},  # Near dup
        {"content": "Machine learning is revolutionizing AI.", "url": "source4"},  # Unique
        {"content": "Machine learning revolutionizes artificial intelligence.", "url": "source5"},  # Similar
        {"content": "The weather today is sunny and warm.", "url": "source6"},  # Unique
    ]

    dedup = ContentDeduplicator()

    # Test deduplication
    result = dedup.deduplicate(test_items)
    assert result.original_count == 6
    assert result.unique_count < 6
    assert result.exact_duplicates >= 1
    print("  [PASS] Deduplication")

    # Test similarity calculation
    sim = dedup.calculate_similarity(
        "The quick brown fox",
        "The quick brown fox"
    )
    assert sim == 1.0
    print("  [PASS] Exact similarity")

    sim = dedup.calculate_similarity(
        "Hello world test",
        "Completely different text here"
    )
    assert sim < 0.5
    print("  [PASS] Low similarity")

    # Test is_duplicate
    assert dedup.is_duplicate(
        "The quick brown fox",
        "The quick brown fox"
    )
    print("  [PASS] is_duplicate (true)")

    assert not dedup.is_duplicate(
        "Hello world",
        "Goodbye universe"
    )
    print("  [PASS] is_duplicate (false)")

    # Test find_duplicates_for
    dups = dedup.find_duplicates_for(
        "The quick brown fox jumps over the lazy dog.",
        test_items
    )
    assert len(dups) >= 1
    print("  [PASS] find_duplicates_for")

    # Test convenience functions
    unique, _ = deduplicate_content(test_items)
    assert len(unique) < len(test_items)
    print("  [PASS] deduplicate_content")

    sim = calculate_content_similarity("test one", "test one")
    assert sim == 1.0
    print("  [PASS] calculate_content_similarity")

    assert are_duplicates("same text", "same text")
    print("  [PASS] are_duplicates")

    unique_texts = get_unique_texts(["hello", "hello", "world"])
    assert len(unique_texts) == 2
    print("  [PASS] get_unique_texts")

    # Test result serialization
    data = result.to_dict()
    assert "original_count" in data
    assert "deduplication_ratio" in data
    print("  [PASS] Result serialization")

    print("\nAll Content Deduplicator self-tests PASSED!")
    return True


if __name__ == "__main__":
    self_test()
