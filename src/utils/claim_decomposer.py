"""
POLARIS Claim Decomposer

FIX 117 Phase 1.2: Decomposes research queries into atomic, verifiable claims.

This module is critical for the cite-first architecture. It transforms
complex research questions into atomic claims that can be individually
verified against evidence.

Based on:
- FactScore (ACL 2023): Atomic fact decomposition
- SAFE (Google 2024): Long-form factuality decomposition
- FActScore: Atomic fact generation for fact-checking
"""

import logging
import re
from typing import List, Dict, Any, Optional, Literal
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class AtomicClaim:
    """An atomic claim decomposed from a query or sentence.

    Properties of a good atomic claim:
    1. Single fact: Contains exactly one verifiable statement
    2. Self-contained: Can be understood without additional context
    3. Falsifiable: Can be verified as true/false with evidence
    4. Specific: Contains concrete details (numbers, names, dates)
    """
    claim_id: str
    claim_text: str
    claim_type: Literal["factual", "statistical", "comparative", "causal", "definitional", "temporal"]
    keywords: List[str] = field(default_factory=list)
    importance: int = 3  # 1-5 scale
    parent_query: str = ""
    is_compound: bool = False  # True if this was split from a compound


@dataclass
class DecompositionResult:
    """Result of decomposing a query into atomic claims."""
    original_query: str
    claims: List[AtomicClaim]
    query_understanding: str
    complexity_score: float  # 0-1, how complex the query is
    decomposition_method: str  # "llm" or "heuristic"


# =============================================================================
# Pydantic Schemas for LLM Output
# =============================================================================

class LLMAtomicClaim(BaseModel):
    """LLM output schema for a single atomic claim."""
    claim_text: str = Field(description="The atomic claim as a statement")
    claim_type: Literal["factual", "statistical", "comparative", "causal", "definitional", "temporal"] = Field(
        default="factual",
        description="Type of claim"
    )
    keywords: List[str] = Field(default_factory=list, description="Key terms for evidence retrieval")
    importance: int = Field(ge=1, le=10, default=3, description="Importance to the query (1-10)")


class LLMDecomposition(BaseModel):
    """LLM output schema for query decomposition."""
    claims: List[LLMAtomicClaim] = Field(description="List of atomic claims")
    query_understanding: str = Field(description="Summary of what the query is asking")
    complexity: Literal["simple", "moderate", "complex"] = Field(default="moderate")


# =============================================================================
# Claim Decomposer
# =============================================================================

class ClaimDecomposer:
    """
    Decomposes research queries into atomic, verifiable claims.

    This is the first step in cite-first synthesis. By breaking down
    complex queries into atomic claims, we can:
    1. Retrieve evidence for each claim individually
    2. Verify each claim independently
    3. Build reports from verified atomic units

    The key insight is that FAITHFULNESS IS EASIER AT THE ATOMIC LEVEL.
    A compound sentence with 5 claims has a 44% pass rate (0.85^5),
    but 5 atomic sentences have an 85% pass rate each.
    """

    def __init__(self, llm=None):
        """
        Initialize the claim decomposer.

        Args:
            llm: Optional LLM for decomposition. Falls back to heuristics if None.
        """
        self.llm = llm
        self._cache: Dict[str, DecompositionResult] = {}

    def decompose(
        self,
        query: str,
        max_claims: int = 50,
        use_cache: bool = True,
    ) -> DecompositionResult:
        """
        Decompose a query into atomic claims.

        Args:
            query: The research query to decompose
            max_claims: Maximum number of claims to generate
            use_cache: Whether to use cached results

        Returns:
            DecompositionResult with atomic claims
        """
        # Check cache
        cache_key = f"{query}:{max_claims}"
        if use_cache and cache_key in self._cache:
            logger.debug(f"Using cached decomposition for: {query[:50]}...")
            return self._cache[cache_key]

        # Try LLM decomposition first
        if self.llm:
            result = self._decompose_with_llm(query, max_claims)
            if result and result.claims:
                self._cache[cache_key] = result
                return result

        # Fall back to heuristic decomposition
        result = self._decompose_heuristic(query, max_claims)
        self._cache[cache_key] = result
        return result

    def decompose_sentence(
        self,
        sentence: str,
        evidence_context: Optional[str] = None,
    ) -> List[AtomicClaim]:
        """
        Decompose a sentence into atomic claims.

        Used for verifying sentences in existing reports.

        Args:
            sentence: The sentence to decompose
            evidence_context: Optional context from evidence

        Returns:
            List of atomic claims from the sentence
        """
        # Check if sentence is already atomic
        if self._is_atomic(sentence):
            return [AtomicClaim(
                claim_id="atom_0",
                claim_text=sentence,
                claim_type=self._classify_claim_type(sentence),
                keywords=self._extract_keywords(sentence),
                importance=3,
                parent_query=sentence,
                is_compound=False,
            )]

        # Decompose compound sentence
        if self.llm:
            return self._decompose_sentence_llm(sentence)

        return self._decompose_sentence_heuristic(sentence)

    def _decompose_with_llm(
        self,
        query: str,
        max_claims: int,
    ) -> Optional[DecompositionResult]:
        """Use LLM to decompose query into atomic claims."""
        prompt = f"""Decompose this research query into atomic, verifiable claims.

RESEARCH QUERY: {query}

RULES FOR ATOMIC CLAIMS:
1. Each claim should contain EXACTLY ONE verifiable fact
2. Claims should be self-contained (understandable without context)
3. Claims should be falsifiable (can be checked against evidence)
4. Include specific details when the query implies them
5. Prioritize claims by importance to answering the query

CLAIM TYPES:
- factual: A statement of fact (e.g., "X is Y")
- statistical: Contains numbers/percentages (e.g., "X affects Y% of Z")
- comparative: Compares two things (e.g., "X is better than Y")
- causal: Describes cause-effect (e.g., "X causes Y")
- definitional: Defines something (e.g., "X is defined as Y")
- temporal: About time/dates (e.g., "X happened in Y")

Generate {min(max_claims, 50)} atomic claims.

OUTPUT FORMAT (JSON):
{{
    "claims": [
        {{
            "claim_text": "...",
            "claim_type": "factual|statistical|comparative|causal|definitional|temporal",
            "keywords": ["key", "terms"],
            "importance": 1-5
        }}
    ],
    "query_understanding": "Summary of query intent",
    "complexity": "simple|moderate|complex"
}}"""

        try:
            # Call LLM (assuming structured output support)
            if hasattr(self.llm, 'invoke'):
                response = self.llm.invoke(prompt)
                content = response.content if hasattr(response, 'content') else str(response)

                # Parse JSON from response
                import json
                # Try to extract JSON from response
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    data = json.loads(json_match.group())

                    claims = []
                    for i, c in enumerate(data.get("claims", [])[:max_claims]):
                        claims.append(AtomicClaim(
                            claim_id=f"claim_{i:03d}",
                            claim_text=c.get("claim_text", ""),
                            claim_type=c.get("claim_type", "factual"),
                            keywords=c.get("keywords", []),
                            importance=c.get("importance", 3),
                            parent_query=query,
                            is_compound=False,
                        ))

                    complexity_map = {"simple": 0.3, "moderate": 0.6, "complex": 0.9}
                    complexity = complexity_map.get(data.get("complexity", "moderate"), 0.6)

                    return DecompositionResult(
                        original_query=query,
                        claims=claims,
                        query_understanding=data.get("query_understanding", ""),
                        complexity_score=complexity,
                        decomposition_method="llm",
                    )
        except Exception as e:
            logger.warning(f"LLM decomposition failed: {e}")

        return None

    def _decompose_heuristic(
        self,
        query: str,
        max_claims: int,
    ) -> DecompositionResult:
        """Heuristic decomposition when LLM is unavailable."""
        claims = []

        # Extract key components
        keywords = self._extract_keywords(query)

        # Generate claims based on question patterns
        claim_templates = [
            ("What is {topic}?", "definitional"),
            ("What are the main characteristics of {topic}?", "factual"),
            ("What statistics exist about {topic}?", "statistical"),
            ("What causes {topic}?", "causal"),
            ("What are the effects of {topic}?", "causal"),
            ("How does {topic} compare to alternatives?", "comparative"),
            ("What is the history of {topic}?", "temporal"),
            ("What are the current trends in {topic}?", "temporal"),
            ("What regulations govern {topic}?", "factual"),
            ("What research has been done on {topic}?", "factual"),
        ]

        # Use main topic from query
        topic = " ".join(keywords[:3]) if keywords else query

        for i, (template, claim_type) in enumerate(claim_templates):
            if i >= max_claims:
                break

            claim_text = template.format(topic=topic)
            claims.append(AtomicClaim(
                claim_id=f"claim_{i:03d}",
                claim_text=claim_text,
                claim_type=claim_type,
                keywords=keywords,
                importance=5 if i < 3 else 3,
                parent_query=query,
                is_compound=False,
            ))

        # Calculate complexity based on query length and structure
        complexity = min(1.0, len(query.split()) / 20)

        return DecompositionResult(
            original_query=query,
            claims=claims,
            query_understanding=f"Research about {topic}",
            complexity_score=complexity,
            decomposition_method="heuristic",
        )

    def _decompose_sentence_llm(self, sentence: str) -> List[AtomicClaim]:
        """Decompose a sentence into atomic claims using LLM."""
        prompt = f"""Decompose this sentence into atomic claims.

SENTENCE: {sentence}

Each atomic claim should contain exactly ONE verifiable fact.
If the sentence is already atomic, return it as a single claim.

OUTPUT FORMAT (JSON array):
[
    {{"claim_text": "...", "claim_type": "factual"}}
]"""

        try:
            if hasattr(self.llm, 'invoke'):
                response = self.llm.invoke(prompt)
                content = response.content if hasattr(response, 'content') else str(response)

                import json
                # Extract JSON array
                json_match = re.search(r'\[[\s\S]*\]', content)
                if json_match:
                    data = json.loads(json_match.group())

                    claims = []
                    for i, c in enumerate(data):
                        claims.append(AtomicClaim(
                            claim_id=f"atom_{i}",
                            claim_text=c.get("claim_text", sentence),
                            claim_type=c.get("claim_type", "factual"),
                            keywords=self._extract_keywords(c.get("claim_text", sentence)),
                            importance=3,
                            parent_query=sentence,
                            is_compound=len(data) > 1,
                        ))
                    return claims
        except Exception as e:
            logger.warning(f"LLM sentence decomposition failed: {e}")

        return self._decompose_sentence_heuristic(sentence)

    def _decompose_sentence_heuristic(self, sentence: str) -> List[AtomicClaim]:
        """Decompose a sentence using heuristics."""
        claims = []

        # Split on common conjunctions
        # "X and Y" -> ["X", "Y"]
        # "X, Y, and Z" -> ["X", "Y", "Z"]
        # "X; Y" -> ["X", "Y"]

        # First, try semicolon split
        parts = sentence.split(';')
        if len(parts) > 1:
            for i, part in enumerate(parts):
                part = part.strip()
                if part:
                    claims.append(AtomicClaim(
                        claim_id=f"atom_{i}",
                        claim_text=part,
                        claim_type=self._classify_claim_type(part),
                        keywords=self._extract_keywords(part),
                        importance=3,
                        parent_query=sentence,
                        is_compound=True,
                    ))
            return claims

        # Try "and" split for compound sentences
        and_pattern = r',?\s+and\s+'
        parts = re.split(and_pattern, sentence)
        if len(parts) > 1 and all(len(p.split()) > 2 for p in parts):
            for i, part in enumerate(parts):
                part = part.strip()
                if part:
                    claims.append(AtomicClaim(
                        claim_id=f"atom_{i}",
                        claim_text=part,
                        claim_type=self._classify_claim_type(part),
                        keywords=self._extract_keywords(part),
                        importance=3,
                        parent_query=sentence,
                        is_compound=True,
                    ))
            return claims

        # Sentence is already atomic
        return [AtomicClaim(
            claim_id="atom_0",
            claim_text=sentence,
            claim_type=self._classify_claim_type(sentence),
            keywords=self._extract_keywords(sentence),
            importance=3,
            parent_query=sentence,
            is_compound=False,
        )]

    def _is_atomic(self, sentence: str) -> bool:
        """Check if a sentence is atomic (single claim)."""
        # Heuristics for atomicity
        indicators_of_compound = [
            '; ',  # Semicolon usually joins independent clauses
            ' and ',  # "and" can join multiple facts
            ' but ',  # Contrast suggests multiple claims
            ' while ',  # Simultaneous actions
            ' whereas ',  # Comparison
            ', which ',  # Relative clause adding info
        ]

        sentence_lower = sentence.lower()
        for indicator in indicators_of_compound:
            if indicator in sentence_lower:
                # Check if it's truly compound by seeing if parts are independent
                parts = sentence.split(indicator)
                if len(parts) > 1 and all(len(p.split()) > 3 for p in parts):
                    return False

        return True

    def _classify_claim_type(
        self,
        claim: str,
    ) -> Literal["factual", "statistical", "comparative", "causal", "definitional", "temporal"]:
        """Classify the type of claim based on content."""
        claim_lower = claim.lower()

        # Statistical: contains numbers/percentages
        if re.search(r'\d+%|\d+\.\d+|million|billion|thousand', claim_lower):
            return "statistical"

        # Comparative: contains comparison words
        if any(word in claim_lower for word in ['than', 'more', 'less', 'better', 'worse', 'compared']):
            return "comparative"

        # Causal: contains cause-effect words
        if any(word in claim_lower for word in ['cause', 'effect', 'result', 'lead to', 'because']):
            return "causal"

        # Definitional: contains definition patterns
        if any(pattern in claim_lower for pattern in ['is defined as', 'refers to', 'is a type of', 'is called']):
            return "definitional"

        # Temporal: contains time references
        if any(word in claim_lower for word in ['year', 'century', 'decade', 'since', 'before', 'after', 'during']):
            return "temporal"

        # Default to factual
        return "factual"

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text."""
        # Remove common words
        stopwords = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
            'ought', 'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by',
            'from', 'as', 'into', 'through', 'during', 'before', 'after',
            'above', 'below', 'between', 'under', 'again', 'further', 'then',
            'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all',
            'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no',
            'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very',
            'just', 'and', 'but', 'if', 'or', 'because', 'as', 'until', 'while',
            'what', 'which', 'who', 'this', 'that', 'these', 'those', 'am',
        }

        # Tokenize and filter
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        keywords = [w for w in words if w not in stopwords]

        # Return unique keywords, preserving order
        seen = set()
        unique = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique.append(kw)

        return unique[:10]  # Limit to top 10


# =============================================================================
# Factory Function
# =============================================================================

def create_claim_decomposer(llm=None) -> ClaimDecomposer:
    """Factory function to create ClaimDecomposer."""
    return ClaimDecomposer(llm=llm)
