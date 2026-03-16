#!/usr/bin/env python3
"""
POLARIS Evaluation Module (SOTA: FactScore + G-Eval)
=====================================================
Implements state-of-the-art evaluation metrics for research synthesis.

Metrics Implemented:
1. FactScore - Atomic fact precision against evidence corpus
2. G-Eval - LLM-as-judge evaluation (coherence, fluency, consistency, relevance)
3. Citation Metrics - Coverage, precision, recall
4. Content Quality - Information density, redundancy

References:
- FactScore: https://arxiv.org/abs/2305.14251
- G-Eval: https://arxiv.org/abs/2303.16634
- RAGAS: https://arxiv.org/abs/2309.15217

Usage:
    from src.utils.evaluation import evaluate_report, FactScoreEvaluator, GEvalEvaluator

    results = await evaluate_report(report_text, evidence_chunks)
    print(f"FactScore: {results['factscore']:.2f}")
    print(f"G-Eval: {results['geval_average']:.2f}")
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

# Configure logging
logger = logging.getLogger(__name__)
from typing import Any, Dict, List, Optional, Tuple

try:
    from transformers import pipeline
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class FactScoreResult:
    """Result of FactScore evaluation."""
    total_facts: int
    supported_facts: int
    unsupported_facts: int
    factscore: float  # supported / total
    facts_detail: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class GEvalResult:
    """Result of G-Eval evaluation."""
    coherence: float
    fluency: float
    consistency: float
    relevance: float
    average: float
    explanations: Dict[str, str] = field(default_factory=dict)


@dataclass
class CitationMetrics:
    """Citation quality metrics."""
    total_citations: int
    unique_citations: int
    citation_density: float  # citations per 100 words
    coverage: float  # % of claims that are cited
    precision: float  # % of citations that are valid


@dataclass
class EvaluationResult:
    """Complete evaluation result."""
    factscore: float
    factscore_detail: FactScoreResult
    geval_average: float
    geval_detail: GEvalResult
    citation_metrics: CitationMetrics
    word_count: int
    information_density: float
    timestamp: str


# =============================================================================
# FACTSCORE EVALUATOR
# =============================================================================

class FactScoreEvaluator:
    """
    SOTA: FactScore evaluation for atomic fact precision.

    Measures what percentage of generated facts are actually supported
    by the evidence corpus.

    Methodology:
    1. Decompose generated text into atomic facts
    2. Verify each fact against evidence using NLI
    3. Calculate precision = supported_facts / total_facts
    """

    # NLI model for verification
    NLI_MODEL = "facebook/bart-large-mnli"
    SUPPORT_THRESHOLD = 0.7

    def __init__(self):
        self._nli_pipeline = None
        self._initialized = False

    def initialize(self):
        """Initialize NLI model."""
        if self._initialized:
            return

        if not TRANSFORMERS_AVAILABLE:
            print("[EVAL] transformers not available, using fallback NLI")
            self._initialized = True
            return

        try:
            import torch
            device = 0 if torch.cuda.is_available() else -1
            self._nli_pipeline = pipeline(
                "text-classification",
                model=self.NLI_MODEL,
                device=device,
                top_k=None,
            )
            self._initialized = True
            logger.info(f"FactScore evaluator initialized with {self.NLI_MODEL}")
        except Exception as e:
            # LOW-116: Use logger instead of print
            logger.warning(f"Failed to load NLI model: {e}")
            self._initialized = True  # Mark as initialized to prevent retries

    def decompose_to_facts(self, text: str) -> List[str]:
        """
        Decompose text into atomic facts.

        Args:
            text: Input text

        Returns:
            List of atomic fact strings
        """
        facts = []

        # Split into sentences first
        sentences = re.split(r'(?<=[.!?])\s+', text)

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 30:
                continue

            # Skip headers and meta text
            if sentence.startswith('#') or sentence.startswith('**'):
                continue

            # Skip citation-only content
            if sentence.count('[') > 3:
                continue

            # Split compound sentences
            parts = re.split(r'\s+and\s+|\s*;\s*|\s*,\s+(?=which|that|where)', sentence)

            for part in parts:
                part = part.strip()
                if len(part) > 30 and len(part) < 300:
                    # Remove citation markers for evaluation
                    clean_part = re.sub(r'\[CITE:[^\]]+\]|\[\d+\]', '', part).strip()
                    if len(clean_part) > 25:
                        facts.append(clean_part)

        return facts

    def verify_fact(self, fact: str, evidence_corpus: List[str]) -> Tuple[bool, float, str]:
        """
        Verify a single fact against evidence corpus.

        Args:
            fact: The fact to verify
            evidence_corpus: List of evidence texts

        Returns:
            Tuple of (is_supported, confidence, best_evidence)
        """
        if not self._nli_pipeline:
            # Fallback: keyword overlap
            return self._verify_fact_keyword(fact, evidence_corpus)

        best_score = 0.0
        best_evidence = ""

        for evidence in evidence_corpus[:20]:  # Check top 20 evidence chunks
            if len(evidence) < 50:
                continue

            try:
                # NLI expects (premise, hypothesis) format
                input_text = f"{evidence[:1000]} [SEP] {fact}"
                result = self._nli_pipeline(input_text)

                # Extract entailment score
                entailment = 0.0
                for item in result:
                    if isinstance(item, dict) and item.get('label', '').upper() == 'ENTAILMENT':
                        entailment = item.get('score', 0)
                        break
                    elif isinstance(item, list):
                        for sub in item:
                            if sub.get('label', '').upper() == 'ENTAILMENT':
                                entailment = sub.get('score', 0)
                                break

                if entailment > best_score:
                    best_score = entailment
                    best_evidence = evidence[:200]

            except Exception as e:
                # LOW-026: Log NLI inference error
                logger.debug(f"NLI inference error for fact verification: {e}")
                continue

        is_supported = best_score >= self.SUPPORT_THRESHOLD
        return is_supported, best_score, best_evidence

    def _verify_fact_keyword(self, fact: str, evidence_corpus: List[str]) -> Tuple[bool, float, str]:
        """Fallback keyword-based verification."""
        fact_words = set(re.findall(r'\b[a-z]{4,}\b', fact.lower()))
        fact_numbers = set(re.findall(r'\d+(?:\.\d+)?%?', fact))

        best_overlap = 0.0
        best_evidence = ""

        for evidence in evidence_corpus[:20]:
            evidence_words = set(re.findall(r'\b[a-z]{4,}\b', evidence.lower()))
            evidence_numbers = set(re.findall(r'\d+(?:\.\d+)?%?', evidence))

            # Calculate overlap
            if fact_words:
                word_overlap = len(fact_words & evidence_words) / len(fact_words)
            else:
                word_overlap = 0

            # Bonus for matching numbers (very important for facts)
            number_match = 1.0 if fact_numbers and fact_numbers & evidence_numbers else 0.0

            combined = (word_overlap + number_match) / 2
            if combined > best_overlap:
                best_overlap = combined
                best_evidence = evidence[:200]

        is_supported = best_overlap >= 0.5
        return is_supported, best_overlap, best_evidence

    def evaluate(self, text: str, evidence_corpus: List[str]) -> FactScoreResult:
        """
        Evaluate text using FactScore methodology.

        Args:
            text: Generated text to evaluate
            evidence_corpus: List of evidence texts

        Returns:
            FactScoreResult with precision score
        """
        if not self._initialized:
            self.initialize()

        facts = self.decompose_to_facts(text)
        if not facts:
            return FactScoreResult(
                total_facts=0,
                supported_facts=0,
                unsupported_facts=0,
                factscore=1.0,  # No facts = no errors
                facts_detail=[],
            )

        supported = 0
        facts_detail = []

        for fact in facts[:50]:  # Limit to 50 facts for efficiency
            is_supported, confidence, evidence = self.verify_fact(fact, evidence_corpus)

            facts_detail.append({
                "fact": fact[:150],
                "supported": is_supported,
                "confidence": round(confidence, 3),
                "evidence": evidence[:100] if is_supported else "",
            })

            if is_supported:
                supported += 1

        total = len(facts_detail)
        factscore = supported / total if total > 0 else 1.0

        return FactScoreResult(
            total_facts=total,
            supported_facts=supported,
            unsupported_facts=total - supported,
            factscore=round(factscore, 4),
            facts_detail=facts_detail,
        )


# =============================================================================
# G-EVAL EVALUATOR
# =============================================================================

GEVAL_PROMPTS = {
    "coherence": """Evaluate the coherence of the following text on a scale of 1-5.

Coherence measures how well the text flows logically from one idea to the next.
- 5: Excellent - Ideas flow seamlessly with clear transitions
- 4: Good - Generally coherent with minor flow issues
- 3: Adequate - Some logical gaps but overall understandable
- 2: Poor - Frequent logical jumps, hard to follow
- 1: Very Poor - Disjointed, no clear structure

Text to evaluate:
{text}

Score (1-5):""",

    "fluency": """Evaluate the fluency of the following text on a scale of 1-5.

Fluency measures how naturally the text reads (grammar, word choice, readability).
- 5: Excellent - Reads naturally, professional quality
- 4: Good - Minor issues but reads well
- 3: Adequate - Some awkward phrasing
- 2: Poor - Frequent grammatical issues
- 1: Very Poor - Difficult to read

Text to evaluate:
{text}

Score (1-5):""",

    "consistency": """Evaluate the consistency of the following text on a scale of 1-5.

Consistency measures whether the text contradicts itself.
- 5: Excellent - Completely consistent throughout
- 4: Good - No contradictions
- 3: Adequate - Minor inconsistencies
- 2: Poor - Some contradictions
- 1: Very Poor - Major contradictions

Text to evaluate:
{text}

Score (1-5):""",

    "relevance": """Evaluate the relevance of the following text on a scale of 1-5.

The text should answer the research question about contamination rates in water filters.
- 5: Excellent - Directly addresses the question with specific evidence
- 4: Good - Mostly relevant with some tangential content
- 3: Adequate - Partially relevant
- 2: Poor - Mostly off-topic
- 1: Very Poor - Completely irrelevant

Text to evaluate:
{text}

Score (1-5):""",
}


class GEvalEvaluator:
    """
    SOTA: G-Eval LLM-as-judge evaluation.

    Uses an LLM to evaluate text quality across multiple dimensions:
    - Coherence: Logical flow and structure
    - Fluency: Language quality and readability
    - Consistency: Internal consistency (no contradictions)
    - Relevance: How well it addresses the research question
    """

    def __init__(self, llm_client=None):
        """
        Initialize G-Eval evaluator.

        Args:
            llm_client: Optional LLM client for evaluation
        """
        self.llm_client = llm_client

    async def evaluate_dimension(self, text: str, dimension: str) -> Tuple[float, str]:
        """
        Evaluate text on a single dimension.

        Args:
            text: Text to evaluate
            dimension: One of coherence, fluency, consistency, relevance

        Returns:
            Tuple of (score 0-1, explanation)
        """
        if dimension not in GEVAL_PROMPTS:
            return 0.5, f"Unknown dimension: {dimension}"

        prompt = GEVAL_PROMPTS[dimension].format(text=text[:3000])

        if self.llm_client:
            try:
                response = await self.llm_client.generate(prompt)

                # Extract score from response
                score_match = re.search(r'[1-5]', response)
                if score_match:
                    raw_score = int(score_match.group())
                    normalized = (raw_score - 1) / 4  # Convert 1-5 to 0-1
                    return normalized, response[:100]

            except Exception as e:
                # LOW-117: Use logger instead of print
                logger.warning(f"G-Eval {dimension} evaluation failed: {e}")

        # Fallback: heuristic evaluation
        return self._heuristic_evaluate(text, dimension)

    def _heuristic_evaluate(self, text: str, dimension: str) -> Tuple[float, str]:
        """Heuristic fallback evaluation."""
        if dimension == "coherence":
            # Check for transition words and sentence variety
            transitions = len(re.findall(r'\b(?:however|therefore|furthermore|additionally|moreover)\b', text, re.I))
            sentences = len(re.findall(r'[.!?]+', text))
            score = min(1.0, (transitions / max(sentences, 1)) * 2 + 0.3)
            return score, "Heuristic: transition word density"

        elif dimension == "fluency":
            # Check sentence length variance and word diversity
            sentences = re.split(r'[.!?]+', text)
            if sentences:
                lengths = [len(s.split()) for s in sentences if len(s.split()) > 3]
                avg_len = sum(lengths) / len(lengths) if lengths else 0
                score = 0.7 if 10 < avg_len < 25 else 0.5
            else:
                score = 0.5
            return score, "Heuristic: sentence length analysis"

        elif dimension == "consistency":
            # Check for contradiction markers
            contradictions = len(re.findall(r'\b(?:however|but|although|contrary)\b', text, re.I))
            score = max(0.5, 1.0 - (contradictions * 0.05))
            return score, "Heuristic: contradiction markers"

        elif dimension == "relevance":
            # Check for domain keywords
            keywords = len(re.findall(r'\b(?:filter|water|contamin|bacteria|pathogen|%)\b', text, re.I))
            words = len(text.split())
            density = keywords / max(words, 1) * 100
            score = min(1.0, density * 0.2)
            return score, "Heuristic: keyword density"

        return 0.5, "Unknown dimension"

    async def evaluate(self, text: str) -> GEvalResult:
        """
        Evaluate text using G-Eval methodology.

        Args:
            text: Text to evaluate

        Returns:
            GEvalResult with scores for all dimensions
        """
        dimensions = ["coherence", "fluency", "consistency", "relevance"]
        scores = {}
        explanations = {}

        for dim in dimensions:
            score, explanation = await self.evaluate_dimension(text, dim)
            scores[dim] = score
            explanations[dim] = explanation

        average = sum(scores.values()) / len(scores)

        return GEvalResult(
            coherence=round(scores["coherence"], 3),
            fluency=round(scores["fluency"], 3),
            consistency=round(scores["consistency"], 3),
            relevance=round(scores["relevance"], 3),
            average=round(average, 3),
            explanations=explanations,
        )


# =============================================================================
# CITATION METRICS
# =============================================================================

def calculate_citation_metrics(text: str, valid_chunk_ids: List[str]) -> CitationMetrics:
    """
    Calculate citation quality metrics.

    Args:
        text: Report text with citations
        valid_chunk_ids: List of valid chunk IDs

    Returns:
        CitationMetrics
    """
    # Count words
    words = len(text.split())

    # Extract citations
    cite_pattern = r'\[CITE:([^\]]+)\]|\[(\d+)\]'
    citations = re.findall(cite_pattern, text)
    total_citations = len(citations)

    # Get unique citations
    unique_ids = set()
    for match in citations:
        cite_id = match[0] or match[1]
        unique_ids.add(cite_id)
    unique_citations = len(unique_ids)

    # Citation density (per 100 words)
    density = (total_citations / words * 100) if words > 0 else 0

    # Calculate precision (what % of citations are valid)
    valid_count = sum(1 for cid in unique_ids if cid in valid_chunk_ids or cid.isdigit())
    precision = valid_count / unique_citations if unique_citations > 0 else 0

    # Count claims (sentences with factual content)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    claim_sentences = [s for s in sentences if re.search(r'\d+%|\d+ \w+|found|showed|demonstrated', s, re.I)]
    cited_claims = [s for s in claim_sentences if re.search(r'\[CITE:|\[\d+\]', s)]
    coverage = len(cited_claims) / len(claim_sentences) if claim_sentences else 0

    return CitationMetrics(
        total_citations=total_citations,
        unique_citations=unique_citations,
        citation_density=round(density, 2),
        coverage=round(coverage, 3),
        precision=round(precision, 3),
    )


# =============================================================================
# MAIN EVALUATION FUNCTION
# =============================================================================

async def evaluate_report(
    report_text: str,
    evidence_chunks: List[str],
    valid_chunk_ids: Optional[List[str]] = None,
    llm_client=None,
) -> EvaluationResult:
    """
    Comprehensive evaluation of a generated report.

    Args:
        report_text: The generated report text
        evidence_chunks: List of evidence chunk texts
        valid_chunk_ids: Optional list of valid chunk IDs for citation validation
        llm_client: Optional LLM client for G-Eval

    Returns:
        EvaluationResult with all metrics
    """
    # FactScore evaluation
    factscore_eval = FactScoreEvaluator()
    factscore_result = factscore_eval.evaluate(report_text, evidence_chunks)

    # G-Eval evaluation
    geval_eval = GEvalEvaluator(llm_client=llm_client)
    geval_result = await geval_eval.evaluate(report_text)

    # Citation metrics
    citation_metrics = calculate_citation_metrics(
        report_text,
        valid_chunk_ids or [],
    )

    # Word count
    word_count = len(report_text.split())

    # Information density (unique meaningful words per 100 words)
    meaningful_words = set(re.findall(r'\b[a-z]{5,}\b', report_text.lower()))
    stop_words = {"which", "there", "these", "those", "would", "could", "should", "their", "about", "being"}
    meaningful_words -= stop_words
    info_density = len(meaningful_words) / word_count * 100 if word_count > 0 else 0

    return EvaluationResult(
        factscore=factscore_result.factscore,
        factscore_detail=factscore_result,
        geval_average=geval_result.average,
        geval_detail=geval_result,
        citation_metrics=citation_metrics,
        word_count=word_count,
        information_density=round(info_density, 2),
        timestamp=datetime.now(UTC).isoformat(),
    )


# =============================================================================
# CLI SELF-TEST
# =============================================================================

if __name__ == "__main__":
    async def test():
        print("=" * 60)
        print("POLARIS EVALUATION MODULE SELF-TEST")
        print("=" * 60)

        # Test data
        test_text = """
        Water filters can harbor significant bacterial contamination.
        Studies show that 60% of point-of-use filters in North America
        contain detectable levels of E. coli after 30 days of use [CITE:chunk_001].
        The CDC recommends replacing filters every 3-6 months [CITE:chunk_002].
        Regular maintenance is essential for preventing biofilm formation.
        """

        test_evidence = [
            "Research indicates that 60% of household water filters show bacterial contamination after extended use.",
            "E. coli was detected in 60% of point-of-use water filter samples collected from North American households.",
            "The Centers for Disease Control and Prevention guidelines suggest filter replacement every 3-6 months.",
            "Biofilm formation in water filters can lead to increased bacterial loads if maintenance is neglected.",
        ]

        # Test FactScore
        print("\n[TEST 1] FactScore Evaluation")
        factscore_eval = FactScoreEvaluator()
        factscore_result = factscore_eval.evaluate(test_text, test_evidence)
        print(f"  Total facts: {factscore_result.total_facts}")
        print(f"  Supported: {factscore_result.supported_facts}")
        print(f"  FactScore: {factscore_result.factscore:.2f}")

        # Test G-Eval
        print("\n[TEST 2] G-Eval Evaluation")
        geval_eval = GEvalEvaluator(llm_client=None)
        geval_result = await geval_eval.evaluate(test_text)
        print(f"  Coherence: {geval_result.coherence:.2f}")
        print(f"  Fluency: {geval_result.fluency:.2f}")
        print(f"  Consistency: {geval_result.consistency:.2f}")
        print(f"  Relevance: {geval_result.relevance:.2f}")
        print(f"  Average: {geval_result.average:.2f}")

        # Test Citation Metrics
        print("\n[TEST 3] Citation Metrics")
        citation_metrics = calculate_citation_metrics(test_text, ["chunk_001", "chunk_002"])
        print(f"  Total citations: {citation_metrics.total_citations}")
        print(f"  Unique citations: {citation_metrics.unique_citations}")
        print(f"  Density: {citation_metrics.citation_density:.2f} per 100 words")
        print(f"  Coverage: {citation_metrics.coverage:.2f}")
        print(f"  Precision: {citation_metrics.precision:.2f}")

        # Full evaluation
        print("\n[TEST 4] Complete Evaluation")
        result = await evaluate_report(test_text, test_evidence, ["chunk_001", "chunk_002"])
        print(f"  FactScore: {result.factscore:.2f}")
        print(f"  G-Eval Avg: {result.geval_average:.2f}")
        print(f"  Word Count: {result.word_count}")
        print(f"  Info Density: {result.information_density:.2f}")

        print("\n" + "=" * 60)
        print("SELF-TEST COMPLETE")
        print("=" * 60)

    asyncio.run(test())
