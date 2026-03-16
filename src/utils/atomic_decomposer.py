"""
POLARIS SOTA Validation Framework - LLM-Based Atomic Fact Decomposition

Created: 2026-02-05
Purpose: Replace heuristic atom counting with real LLM decomposition per Min et al. 2023

This module implements proper atomic fact decomposition for honest FactScore calculation.
Unlike the heuristic in auditor_agent.py:737-766 which counts conjunctions and numbers,
this uses an LLM to semantically decompose sentences into verifiable atomic claims.

Reference: Min et al. 2023 - "FacTool: Factuality Detection in Generative AI"
"""

import os
import logging
import asyncio
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AtomicFact:
    """A single atomic fact extracted from a sentence."""

    fact: str
    """The atomic fact statement."""

    source_sentence: str
    """The original sentence this fact was extracted from."""

    fact_type: str = "claim"
    """Type of fact: 'claim', 'definition', 'statistic', 'comparison'."""

    verifiable: bool = True
    """Whether this fact can be independently verified."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional metadata about the fact."""


@dataclass
class DecompositionResult:
    """Result of atomic decomposition for a sentence."""

    original_sentence: str
    """The original sentence that was decomposed."""

    atomic_facts: List[AtomicFact]
    """List of atomic facts extracted."""

    decomposition_method: str = "llm"
    """Method used: 'llm' or 'heuristic' (fallback)."""

    confidence: float = 1.0
    """Confidence in the decomposition quality."""

    metadata: Dict[str, Any] = field(default_factory=dict)


class AtomicDecomposer:
    """
    LLM-based atomic fact decomposition for honest FactScore calculation.

    Per Min et al. 2023, atomic facts are:
    - Single, indivisible claims
    - Can be verified independently
    - Do not contain conjunctions that combine separate claims
    - Each represents one piece of verifiable information

    Example:
        Input: "The iPhone 15 Pro costs $999 and has a titanium frame."
        Output: [
            "The iPhone 15 Pro costs $999.",
            "The iPhone 15 Pro has a titanium frame."
        ]
    """

    DECOMPOSITION_PROMPT = """Extract all atomic facts from this sentence.

An atomic fact is:
1. A single, indivisible claim that can be verified independently
2. Contains exactly ONE piece of verifiable information
3. Does not combine multiple claims with 'and', 'or', 'but', etc.

Rules:
- Split compound sentences into separate atomic facts
- Preserve the meaning and context of each fact
- Each fact should be a complete, standalone statement
- Include implicit facts when they contain verifiable information
- Exclude opinions, predictions, and speculation UNLESS they are attributed

Sentence: {sentence}

Extract atomic facts (one per line, no numbering):"""

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        use_heuristic_fallback: bool = True,
        max_facts_per_sentence: int = 10,
    ):
        """
        Initialize the atomic decomposer.

        Args:
            llm_client: LLM client for decomposition. If None, will attempt to load.
            use_heuristic_fallback: If True, fall back to heuristic if LLM fails.
            max_facts_per_sentence: Maximum atomic facts to extract per sentence.
        """
        self.llm_client = llm_client
        self.use_heuristic_fallback = use_heuristic_fallback
        self.max_facts_per_sentence = max_facts_per_sentence
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize LLM client if not provided."""
        if self.llm_client is not None:
            self._initialized = True
            return True

        try:
            # Try to import KIMI client (primary)
            from src.llm.kimi_client import KIMIClient
            self.llm_client = KIMIClient()
            self._initialized = True
            logger.info("AtomicDecomposer initialized with KIMI client")
            return True
        except ImportError:
            try:
                # Fallback to Gemini
                from src.llm.gemini_client import GeminiClient
                self.llm_client = GeminiClient()
                self._initialized = True
                logger.info("AtomicDecomposer initialized with Gemini client")
                return True
            except ImportError:
                logger.warning("No LLM client available for atomic decomposition")
                self._initialized = False
                return False

    async def decompose(self, sentence: str) -> DecompositionResult:
        """
        Decompose a sentence into atomic facts.

        Args:
            sentence: The sentence to decompose.

        Returns:
            DecompositionResult with extracted atomic facts.
        """
        if not self._initialized:
            await self.initialize()

        # Try LLM decomposition first
        if self._initialized and self.llm_client is not None:
            try:
                return await self._llm_decompose(sentence)
            except Exception as e:
                logger.warning(f"LLM decomposition failed: {e}")
                if not self.use_heuristic_fallback:
                    raise

        # Fallback to heuristic
        if self.use_heuristic_fallback:
            return self._heuristic_decompose(sentence)

        raise RuntimeError("LLM decomposition failed and heuristic fallback disabled")

    async def _llm_decompose(self, sentence: str) -> DecompositionResult:
        """Decompose using LLM."""
        prompt = self.DECOMPOSITION_PROMPT.format(sentence=sentence)

        # Call LLM
        response = await self.llm_client.generate(
            prompt=prompt,
            max_tokens=500,
            temperature=0.0,  # Deterministic for consistency
        )

        # Parse response into atomic facts
        facts = []
        lines = response.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Skip numbering prefixes like "1.", "- ", "* "
            if line[0].isdigit() and len(line) > 2 and line[1] in '.):':
                line = line[2:].strip()
            elif line[0] in '-*':
                line = line[1:].strip()

            if len(line) > 10:  # Minimum meaningful fact length
                facts.append(AtomicFact(
                    fact=line,
                    source_sentence=sentence,
                    fact_type=self._classify_fact(line),
                ))

        # Cap at maximum
        facts = facts[:self.max_facts_per_sentence]

        # Ensure at least one fact (the sentence itself if decomposition failed)
        if not facts:
            facts = [AtomicFact(
                fact=sentence,
                source_sentence=sentence,
                fact_type="claim",
            )]

        return DecompositionResult(
            original_sentence=sentence,
            atomic_facts=facts,
            decomposition_method="llm",
            confidence=0.9 if len(facts) > 1 else 0.7,
        )

    def _heuristic_decompose(self, sentence: str) -> DecompositionResult:
        """
        Fallback heuristic decomposition.

        This is similar to the original _estimate_atom_count but actually
        attempts to split the sentence rather than just count.
        """
        import re

        facts = []

        # Split on conjunctions
        conjunctions = [' and ', ' but ', ' while ', ' whereas ', ' however ', '; ']
        parts = [sentence]

        for conj in conjunctions:
            new_parts = []
            for part in parts:
                splits = part.split(conj)
                new_parts.extend(splits)
            parts = new_parts

        # Clean and filter
        for part in parts:
            part = part.strip()
            if len(part) > 20:  # Minimum meaningful length
                # Ensure it's a complete thought
                if not part[0].isupper():
                    part = part[0].upper() + part[1:]
                if part[-1] not in '.!?':
                    part = part + '.'

                facts.append(AtomicFact(
                    fact=part,
                    source_sentence=sentence,
                    fact_type=self._classify_fact(part),
                ))

        # If no splits, use original
        if not facts:
            facts = [AtomicFact(
                fact=sentence,
                source_sentence=sentence,
                fact_type="claim",
            )]

        return DecompositionResult(
            original_sentence=sentence,
            atomic_facts=facts[:self.max_facts_per_sentence],
            decomposition_method="heuristic",
            confidence=0.5,  # Lower confidence for heuristic
        )

    def _classify_fact(self, fact: str) -> str:
        """Classify the type of atomic fact."""
        import re

        fact_lower = fact.lower()

        # Check for statistics
        if re.search(r'\d+(?:\.\d+)?%', fact):
            return "statistic"
        if re.search(r'\$[\d,]+', fact):
            return "statistic"
        if re.search(r'\d+(?:,\d{3})+', fact):
            return "statistic"

        # Check for comparisons
        if any(word in fact_lower for word in [' more than ', ' less than ', ' compared to ', ' versus ', ' vs ']):
            return "comparison"

        # Check for definitions
        if ' is defined as ' in fact_lower or ' refers to ' in fact_lower:
            return "definition"

        return "claim"

    async def decompose_batch(self, sentences: List[str]) -> List[DecompositionResult]:
        """Decompose multiple sentences."""
        tasks = [self.decompose(s) for s in sentences]
        return await asyncio.gather(*tasks)

    def count_atoms(self, sentence: str) -> int:
        """
        Synchronous method to count atomic facts (for compatibility).

        This provides a drop-in replacement for _estimate_atom_count
        but uses actual decomposition when possible.
        """
        try:
            # Try to run async decomposition synchronously
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If already in async context, use heuristic
                result = self._heuristic_decompose(sentence)
            else:
                result = loop.run_until_complete(self.decompose(sentence))
            return len(result.atomic_facts)
        except Exception:
            # Ultimate fallback: use old heuristic count
            return self._legacy_estimate_atom_count(sentence)

    def _legacy_estimate_atom_count(self, sentence: str) -> int:
        """
        Legacy atom count estimation (matches auditor_agent.py:737-766).

        Only used as ultimate fallback when LLM and heuristic decomposition fail.
        """
        import re

        atoms = 1  # Base: at least one claim

        # Conjunctions indicate compound claims
        conjunctions = [' and ', ' or ', '; ', ' but ', ' while ', ' whereas ']
        for conj in conjunctions:
            atoms += sentence.lower().count(conj)

        # Numerical values often represent separate facts
        numbers = re.findall(r'\d+(?:\.\d+)?%?', sentence)
        if len(numbers) > 1:
            atoms += len(numbers) - 1

        # Comparatives/superlatives indicate additional claims
        comparatives = [' more than ', ' less than ', ' compared to ', ' versus ']
        for comp in comparatives:
            if comp in sentence.lower():
                atoms += 1

        return min(atoms, 10)


# Convenience function for synchronous usage
def decompose_to_atomic_facts(sentence: str, use_llm: bool = True) -> List[str]:
    """
    Convenience function to decompose a sentence into atomic facts.

    Args:
        sentence: The sentence to decompose.
        use_llm: Whether to attempt LLM decomposition.

    Returns:
        List of atomic fact strings.
    """
    decomposer = AtomicDecomposer(use_heuristic_fallback=True)

    if use_llm:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                result = decomposer._heuristic_decompose(sentence)
            else:
                result = loop.run_until_complete(decomposer.decompose(sentence))
        except Exception:
            result = decomposer._heuristic_decompose(sentence)
    else:
        result = decomposer._heuristic_decompose(sentence)

    return [f.fact for f in result.atomic_facts]


# Module-level instance for convenience
_default_decomposer: Optional[AtomicDecomposer] = None


def get_decomposer() -> AtomicDecomposer:
    """Get or create the default decomposer instance."""
    global _default_decomposer
    if _default_decomposer is None:
        _default_decomposer = AtomicDecomposer()
    return _default_decomposer
