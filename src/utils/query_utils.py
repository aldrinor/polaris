"""
POLARIS Query Utilities

Topic anchoring and query optimization utilities to prevent corpus pollution.

FIX-124C: Core topic extraction and query anchoring to ensure queries
stay relevant to the research topic and don't drift into unrelated domains.
"""

import re
import logging
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Region/location terms that should not be treated as core topic terms
REGION_TERMS = {
    # Cardinal directions
    "north", "south", "east", "west", "central", "northern", "southern",
    "eastern", "western", "northeast", "northwest", "southeast", "southwest",
    # Continents
    "america", "americas", "europe", "asia", "africa", "oceania", "australia",
    "antarctica",
    # Common geographic qualifiers
    "global", "worldwide", "international", "domestic", "regional", "local",
    "national", "continental", "pacific", "atlantic", "arctic", "tropical",
    # Common country/region abbreviations
    "us", "usa", "uk", "eu", "apac", "emea", "latam", "mena",
}

# Common stop words that shouldn't be core topic terms
STOP_WORDS = {
    'the', 'a', 'an', 'in', 'on', 'at', 'for', 'to', 'of', 'and', 'or',
    'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be', 'been',
    'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
    'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need',
    'this', 'that', 'these', 'those', 'what', 'which', 'who', 'whom',
    'how', 'when', 'where', 'why', 'all', 'each', 'every', 'both', 'few',
    'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
    'own', 'same', 'so', 'than', 'too', 'very', 'just', 'but', 'if',
}


# =============================================================================
# Core Topic Extraction
# =============================================================================

def extract_core_topic_terms(vector_id: str) -> List[str]:
    """
    Extract core topic terms from vector ID that MUST appear in queries.

    The vector ID format is typically: S{stage}V{num}_{topic}_{region}
    Example: S1V1_Household_Water_Filter_NORTH_AMERICA

    This function extracts terms like "household", "water", "filter" that
    define the core research topic (excluding region qualifiers).

    Args:
        vector_id: The vector identifier string

    Returns:
        List of core topic terms (lowercase)
    """
    if not vector_id:
        return []

    # Split by underscores
    parts = vector_id.split("_")

    # Skip the first part if it matches pattern S{n}V{n} (stage/vector identifier)
    if parts and re.match(r'^S\d+V\d+$', parts[0]):
        parts = parts[1:]

    core_terms = []
    for term in parts:
        term_lower = term.lower()

        # Skip if it's a region term
        if term_lower in REGION_TERMS:
            continue

        # Skip if it's too short (< 3 chars)
        if len(term_lower) < 3:
            continue

        # Skip if it's a stop word
        if term_lower in STOP_WORDS:
            continue

        # Skip if it looks like a number or code
        if term_lower.isdigit() or re.match(r'^[a-z]\d+$', term_lower):
            continue

        core_terms.append(term_lower)

    logger.debug(f"[FIX-124C] Extracted core terms from '{vector_id}': {core_terms}")
    return core_terms


def extract_core_topic_from_query(query: str, min_term_length: int = 4) -> List[str]:
    """
    Extract core topic terms from a natural language query.

    Uses simple heuristics to identify the most likely core topic terms:
    - Nouns (typically longer words)
    - Not stop words
    - Not very common research terms

    Args:
        query: The research query string
        min_term_length: Minimum term length to consider

    Returns:
        List of potential core topic terms
    """
    if not query:
        return []

    # Common research terms that are not topic-specific
    generic_research_terms = {
        "research", "study", "studies", "analysis", "review", "investigation",
        "examination", "evaluation", "assessment", "survey", "report", "data",
        "results", "findings", "conclusion", "method", "methods", "approach",
        "evidence", "impact", "effect", "effects", "cause", "causes",
        "risk", "risks", "factor", "factors", "current", "recent", "latest",
    }

    # Tokenize and filter
    words = re.findall(r'\b[a-zA-Z]+\b', query.lower())
    core_terms = []

    for word in words:
        if len(word) < min_term_length:
            continue
        if word in STOP_WORDS:
            continue
        if word in REGION_TERMS:
            continue
        if word in generic_research_terms:
            continue
        core_terms.append(word)

    # Remove duplicates while preserving order
    seen = set()
    unique_terms = []
    for term in core_terms:
        if term not in seen:
            seen.add(term)
            unique_terms.append(term)

    return unique_terms[:5]  # Return top 5 terms


# =============================================================================
# Topic Anchoring
# =============================================================================

def anchor_query_to_topic(
    query: str,
    core_terms: List[str],
    min_matches: int = 1
) -> Tuple[str, bool]:
    """
    Ensure query contains at least one core topic term.

    If the query doesn't contain any core terms, append the first core term
    to anchor it back to the research topic. This prevents corpus pollution
    where queries drift into unrelated domains.

    Args:
        query: The search query to check/anchor
        core_terms: List of core topic terms from vector_id or query
        min_matches: Minimum number of core terms required in query

    Returns:
        Tuple of (possibly modified query, was_modified: bool)
    """
    if not core_terms:
        return query, False

    query_lower = query.lower()
    matches = sum(1 for term in core_terms if term in query_lower)

    if matches >= min_matches:
        return query, False  # Already anchored

    # Need to anchor - add first core term
    anchor_term = core_terms[0]
    anchored_query = f"{query} {anchor_term}"

    logger.debug(
        f"[FIX-124C] Anchored query: '{query[:40]}...' -> '{anchored_query[:50]}...' "
        f"(added '{anchor_term}')"
    )
    return anchored_query, True


def validate_query_relevance(
    query: str,
    core_terms: List[str],
    min_term_overlap: float = 0.2
) -> Tuple[bool, float]:
    """
    Validate that a query is relevant to the core research topic.

    Uses term overlap ratio to determine if the query is on-topic.
    A query with no overlap with core terms is likely off-topic.

    Args:
        query: The query to validate
        core_terms: List of core topic terms
        min_term_overlap: Minimum overlap ratio (0-1) to consider on-topic

    Returns:
        Tuple of (is_relevant: bool, overlap_score: float)
    """
    if not core_terms:
        return True, 1.0  # No core terms to check against

    query_lower = query.lower()
    query_words = set(re.findall(r'\b[a-z]+\b', query_lower))

    # Count matches
    core_set = set(core_terms)
    overlap = len(query_words.intersection(core_set))

    # Calculate overlap ratio based on core terms
    overlap_score = overlap / len(core_set) if core_set else 0.0

    is_relevant = overlap_score >= min_term_overlap

    if not is_relevant:
        logger.warning(
            f"[FIX-124C] Off-topic query detected (overlap={overlap_score:.2f}): "
            f"'{query[:60]}...'"
        )

    return is_relevant, overlap_score


# =============================================================================
# Query Optimization
# =============================================================================

def simplify_query_for_api(
    query: str,
    max_words: int = 6,
    preserve_quotes: bool = False
) -> str:
    """
    Simplify a query for API consumption.

    Many search APIs work better with shorter, simpler queries.
    This function extracts the most significant words.

    Args:
        query: The query to simplify
        max_words: Maximum number of words in output
        preserve_quotes: Whether to preserve quoted phrases

    Returns:
        Simplified query string
    """
    if preserve_quotes:
        # Extract quoted phrases first
        quoted = re.findall(r'"[^"]+"', query)
        if quoted:
            # Return first quoted phrase
            return quoted[0]

    # Remove quotes for processing
    clean_query = query.replace('"', '').replace("'", '')

    # Tokenize
    words = clean_query.split()

    if len(words) <= max_words:
        return clean_query

    # Filter stop words and keep significant terms
    significant = [w for w in words if w.lower() not in STOP_WORDS and len(w) > 2]

    # Return first N significant words
    simplified = ' '.join(significant[:max_words])

    logger.debug(f"[QUERY-SIMPLIFY] '{query[:40]}...' -> '{simplified}'")
    return simplified


def create_boolean_query(
    primary_terms: List[str],
    secondary_terms: Optional[List[str]] = None,
    operator: str = "AND"
) -> str:
    """
    Create a boolean search query from term lists.

    Args:
        primary_terms: Primary search terms (required)
        secondary_terms: Secondary/optional terms
        operator: Boolean operator (AND, OR)

    Returns:
        Boolean query string
    """
    if not primary_terms:
        return ""

    # Join primary terms
    primary_part = f" {operator} ".join(primary_terms)

    if secondary_terms:
        secondary_part = " OR ".join(secondary_terms)
        return f"({primary_part}) AND ({secondary_part})"

    return primary_part
