"""
POLARIS Query Amplifier
=======================
Generates 10x query variants for comprehensive SOTA-level search coverage.

Key features:
- Academic variants (peer-reviewed, meta-analysis, systematic review)
- Regional variants (geographic targeting)
- Source-specific variants (site: operators)
- Temporal variants (recent, 2024-2026)
- Deduplication of generated variants

Per CLAUDE.md LAW VI: Zero hard-coding. Uses DepthConfig for all parameters.
"""

import logging
import os
from typing import List, Optional, Set
from dataclasses import dataclass, field

try:
    from src.depth.depth_config import get_depth_config
except ImportError:
    get_depth_config = None  # Legacy module archived; polaris_graph uses its own query generation


logger = logging.getLogger(__name__)


# =============================================================================
# Constants for variant generation
# =============================================================================

ACADEMIC_SUFFIXES = [
    "",  # Base query
    "peer-reviewed study",
    "systematic review",
    "meta-analysis",
    "clinical trial results",
    "research paper",
    "scientific literature",
    "evidence-based",
]

REGIONAL_PATTERNS = {
    "NORTH_AMERICA": [
        "USA", "United States", "Canada", "North America",
        "American", "Canadian", "US federal",
    ],
    "EUROPE": [
        "Europe", "European Union", "EU", "UK", "United Kingdom",
        "Germany", "France", "European",
    ],
    "ASIA_PACIFIC": [
        "Asia", "China", "Japan", "Australia", "Asia Pacific",
        "India", "Southeast Asia", "APAC",
    ],
    "LATIN_AMERICA": [
        "Latin America", "South America", "Brazil", "Mexico",
        "Argentina", "Latin American",
    ],
    "GLOBAL": [
        "worldwide", "global", "international",
    ],
}

GOVERNMENT_SITES = [
    "site:gov",
    "site:epa.gov",
    "site:fda.gov",
    "site:cdc.gov",
    "site:who.int",
    "site:nih.gov",
    "site:usda.gov",
]

EDUCATIONAL_SITES = [
    "site:edu",
    "site:ac.uk",
    "site:edu.au",
]

TEMPORAL_PATTERNS = [
    "2024 2025 2026",
    "latest research",
    "recent study",
    "current standards",
]


# =============================================================================
# Query Amplifier
# =============================================================================

@dataclass
class AmplificationResult:
    """Result of query amplification."""
    original_query: str
    variants: List[str]
    total_count: int
    dedup_count: int
    variant_types: List[str]


class QueryAmplifier:
    """
    Generates query variants for comprehensive SOTA-level search coverage.

    Features:
    - Academic variants for research literature
    - Regional variants for geographic targeting
    - Source-specific variants (government, educational)
    - Temporal variants for recent research
    - Automatic deduplication

    Usage:
        amplifier = QueryAmplifier()
        result = amplifier.amplify(
            query="household water filter contamination",
            region="NORTH_AMERICA",
            topic="water_quality"
        )
        print(f"Generated {result.total_count} variants")
    """

    def __init__(self):
        """Initialize with DepthConfig (LAW VI)."""
        self.depth_config = get_depth_config()
        self.amplification_config = self.depth_config.query_amplification

    def amplify(
        self,
        query: str,
        region: str = "GLOBAL",
        topic: Optional[str] = None,
        include_academic: Optional[bool] = None,
        include_regional: Optional[bool] = None,
        include_source: Optional[bool] = None,
        include_temporal: Optional[bool] = None,
    ) -> AmplificationResult:
        """
        Amplify a query into multiple variants.

        Args:
            query: Original search query
            region: Geographic region (NORTH_AMERICA, EUROPE, etc.)
            topic: Optional topic category
            include_academic: Override academic variants setting
            include_regional: Override regional variants setting
            include_source: Override source variants setting
            include_temporal: Override temporal variants setting

        Returns:
            AmplificationResult with all generated variants
        """
        if not self.amplification_config.enabled:
            return AmplificationResult(
                original_query=query,
                variants=[query],
                total_count=1,
                dedup_count=1,
                variant_types=["original"],
            )

        variants: List[str] = []
        variant_types: List[str] = []
        seen: Set[str] = set()

        # Always include original and exact match
        variants.append(query)
        variants.append(f'"{query}"')
        seen.add(query.lower())
        seen.add(f'"{query}"'.lower())
        variant_types.extend(["original", "exact_match"])

        # Academic variants
        if include_academic if include_academic is not None else self.amplification_config.include_academic_variants:
            academic_variants = self._generate_academic_variants(query)
            for v in academic_variants:
                if v.lower() not in seen:
                    seen.add(v.lower())
                    variants.append(v)
                    variant_types.append("academic")

        # Regional variants
        if include_regional if include_regional is not None else self.amplification_config.include_regional_variants:
            regional_variants = self._generate_regional_variants(query, region)
            for v in regional_variants:
                if v.lower() not in seen:
                    seen.add(v.lower())
                    variants.append(v)
                    variant_types.append("regional")

        # Source-specific variants
        if include_source if include_source is not None else self.amplification_config.include_source_variants:
            source_variants = self._generate_source_variants(query)
            for v in source_variants:
                if v.lower() not in seen:
                    seen.add(v.lower())
                    variants.append(v)
                    variant_types.append("source")

        # Temporal variants
        if include_temporal if include_temporal is not None else self.amplification_config.include_temporal_variants:
            temporal_variants = self._generate_temporal_variants(query)
            for v in temporal_variants:
                if v.lower() not in seen:
                    seen.add(v.lower())
                    variants.append(v)
                    variant_types.append("temporal")

        # FIX-221C: Topic anchor enforcement
        # Ensure every variant contains at least one topic keyword to prevent drift
        topic_anchor_enabled = os.environ.get("POLARIS_QUERY_TOPIC_ANCHOR", "1") == "1"
        if topic_anchor_enabled and topic:
            # Extract topic anchor words from the original query
            topic_words = [w for w in query.split() if len(w) > 3 and w[0:1].isupper()]
            if not topic_words:
                # Fallback: use first 3 significant words from query
                _stop = {'the', 'a', 'an', 'in', 'on', 'at', 'for', 'to', 'of', 'and', 'or', 'with', 'by',
                         'what', 'how', 'which', 'where', 'when', 'why', 'do', 'does', 'exist', 'rates', 'patterns'}
                topic_words = [w for w in query.split() if w.lower() not in _stop][:3]

            topic_anchor_str = ' '.join(topic_words[:3])
            topic_lower = {w.lower() for w in topic_words[:3]}

            anchored_count = 0
            for i, v in enumerate(variants):
                if i == 0:
                    continue  # Skip original query
                v_lower = v.lower()
                has_topic = any(tw in v_lower for tw in topic_lower)
                if not has_topic:
                    # Prepend topic anchor
                    variants[i] = f"{topic_anchor_str} {v}"
                    anchored_count += 1

            if anchored_count > 0:
                logger.info(
                    f"[FIX-221C] Anchored {anchored_count}/{len(variants)} variants "
                    f"with topic: '{topic_anchor_str}'"
                )

        logger.info(
            f"Query amplification: '{query[:50]}...' -> {len(variants)} variants "
            f"(academic: {variant_types.count('academic')}, "
            f"regional: {variant_types.count('regional')}, "
            f"source: {variant_types.count('source')}, "
            f"temporal: {variant_types.count('temporal')})"
        )

        return AmplificationResult(
            original_query=query,
            variants=variants,
            total_count=len(variants),
            dedup_count=len(variants),  # Already deduped
            variant_types=variant_types,
        )

    def _generate_academic_variants(self, query: str) -> List[str]:
        """Generate academic/research variants."""
        variants = []
        for suffix in ACADEMIC_SUFFIXES:
            if suffix:
                variants.append(f"{query} {suffix}")
        return variants

    def _generate_regional_variants(self, query: str, region: str) -> List[str]:
        """Generate regional/geographic variants."""
        variants = []
        patterns = REGIONAL_PATTERNS.get(region, REGIONAL_PATTERNS["GLOBAL"])

        for pattern in patterns[:4]:  # Limit to 4 regional variants
            variants.append(f"{query} {pattern}")
            variants.append(f"{query} {pattern} statistics data")

        # Add government report variant
        if region in ["NORTH_AMERICA", "EUROPE"]:
            variants.append(f"{query} {patterns[0]} government report")
            variants.append(f"{query} {patterns[0]} regulations standards")

        return variants

    def _generate_source_variants(self, query: str) -> List[str]:
        """Generate source-specific variants (site: operators)."""
        variants = []

        # Government sources
        for site in GOVERNMENT_SITES[:4]:  # Limit to 4 government sites
            variants.append(f"{query} {site}")

        # Educational sources
        for site in EDUCATIONAL_SITES[:2]:  # Limit to 2 educational sites
            variants.append(f"{query} {site}")

        return variants

    def _generate_temporal_variants(self, query: str) -> List[str]:
        """Generate temporal variants for recent research."""
        variants = []
        for pattern in TEMPORAL_PATTERNS:
            variants.append(f"{query} {pattern}")
        return variants

    def amplify_batch(
        self,
        queries: List[str],
        region: str = "GLOBAL",
    ) -> List[str]:
        """
        Amplify multiple queries and return all unique variants.

        Args:
            queries: List of original queries
            region: Geographic region

        Returns:
            List of all unique query variants
        """
        all_variants: Set[str] = set()

        for query in queries:
            result = self.amplify(query, region=region)
            all_variants.update(result.variants)

        unique_variants = list(all_variants)
        logger.info(
            f"Batch amplification: {len(queries)} queries -> {len(unique_variants)} unique variants"
        )

        return unique_variants


# =============================================================================
# Standalone Functions
# =============================================================================

def amplify_query(
    query: str,
    region: str = "GLOBAL",
    topic: Optional[str] = None,
) -> List[str]:
    """
    Standalone function to amplify a query.

    Args:
        query: Original search query
        region: Geographic region
        topic: Optional topic category

    Returns:
        List of query variants
    """
    amplifier = QueryAmplifier()
    result = amplifier.amplify(query, region=region, topic=topic)
    return result.variants


def amplify_queries(
    queries: List[str],
    region: str = "GLOBAL",
) -> List[str]:
    """
    Standalone function to amplify multiple queries.

    Args:
        queries: List of original queries
        region: Geographic region

    Returns:
        List of all unique query variants
    """
    amplifier = QueryAmplifier()
    return amplifier.amplify_batch(queries, region=region)


def count_amplification_factor() -> int:
    """
    Return the approximate amplification factor.

    Returns:
        Approximate number of variants per query
    """
    config = get_depth_config()
    if not config.query_amplification.enabled:
        return 1

    # Approximate: 2 (original) + 7 (academic) + 6 (regional) + 6 (source) + 4 (temporal)
    return config.query_amplification.variants_per_query


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "QueryAmplifier",
    "AmplificationResult",
    "amplify_query",
    "amplify_queries",
    "count_amplification_factor",
]
