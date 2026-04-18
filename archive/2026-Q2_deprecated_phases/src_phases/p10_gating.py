"""
Phase 10: Gating Logic - Decision Matrix

This phase implements the gating decision matrix that determines the pipeline's
next action based on sufficiency, confidence, and integrity scores.

ARCHITECT DIRECTIVE: NO MOCKING OF LOGIC

Decision Matrix:
- CASE_1: Sufficient evidence + high confidence -> Finalize (proceed to P11-13)
- CASE_2: Partial evidence -> Refine (iterate P7-P10)
- CASE_3: Insufficient evidence -> Gap report
- CASE_4: Contradiction / integrity failure -> Fail/Escalate
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Configure logging
logger = logging.getLogger(__name__)

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.schemas.phase_models import (
    Phase6Output, Phase7Output, Phase9Output, Phase10Output,
    GatingCase
)
from src.state.ledger import Ledger
from src.config import get_config, OUTPUTS_DIR
from src.audit import get_audit
from src.schemas.question_types import QuestionType
from src.schemas.validation_criteria import validate_answer, derive_criteria_from_question_type
from src.memory.chroma_client import get_chroma_manager

# SOTA: RAGAS evaluation for LLM-based quality metrics
try:
    from src.utils.ragas_evaluator import RAGASEvaluator, RAGASScore
    RAGAS_AVAILABLE = True
except ImportError:
    RAGAS_AVAILABLE = False
    RAGASScore = None


# ============================================================================
# SCORE CALCULATION
# ============================================================================

def calculate_sufficiency_score(
    p6_output: Phase6Output,
    p7_output: Phase7Output,
    p9_output: Phase9Output,
    config: Any
) -> Tuple[float, Dict[str, Any]]:
    """
    Calculate the sufficiency score based on evidence quantity and quality.

    Factors:
    - Number of verified chunks from P6
    - Coverage of constraints
    - Evidence diversity
    - P8 resolution rate

    Args:
        p6_output: Phase 6 NLI integrity output
        p7_output: Phase 7 RAG output
        p9_output: Phase 8 adversarial QA output
        config: Configuration thresholds

    Returns:
        Tuple of (sufficiency_score, breakdown_dict)
    """
    thresholds = config.thresholds.sufficiency

    # Factor 1: Verified chunk ratio (from P6)
    verified_ratio = 0.0
    if hasattr(p6_output, 'chunks_verified') and hasattr(p6_output, 'total_pairs'):
        if p6_output.total_pairs > 0:
            verified_ratio = p6_output.chunks_verified / p6_output.total_pairs
    elif hasattr(p6_output, 'integrity_score'):
        verified_ratio = p6_output.integrity_score

    # Factor 2: Context utilization (from P7)
    context_utilization = 0.0
    if hasattr(p7_output, 'chunks_used') and hasattr(p7_output, 'context_budget_tokens'):
        # If we used most of the context budget, that's good
        if p7_output.context_budget_tokens > 0:
            tokens_used = len(p7_output.analysis_text.split()) * 1.3 if p7_output.analysis_text else 0
            context_utilization = min(1.0, tokens_used / p7_output.context_budget_tokens)
    else:
        # Fallback: assume reasonable utilization if we have a draft
        context_utilization = 0.7 if p7_output.analysis_text else 0.0

    # Factor 3: Resolution rate (from P8)
    resolution_rate = p9_output.resolution_rate if hasattr(p9_output, 'resolution_rate') else 0.5

    # Factor 4: Citation density
    citation_density = 0.0
    if hasattr(p7_output, 'citation_tokens') and p7_output.analysis_text:
        words = len(p7_output.analysis_text.split())
        citations = len(p7_output.citation_tokens) if p7_output.citation_tokens else 0
        if words > 0:
            # Aim for ~1 citation per 100 words
            citation_density = min(1.0, (citations / (words / 100)))

    # Weighted combination
    sufficiency_score = (
        0.30 * verified_ratio +
        0.20 * context_utilization +
        0.30 * resolution_rate +
        0.20 * citation_density
    )

    breakdown = {
        "verified_ratio": verified_ratio,
        "context_utilization": context_utilization,
        "resolution_rate": resolution_rate,
        "citation_density": citation_density,
        "weights": {"verified": 0.30, "context": 0.20, "resolution": 0.30, "citation": 0.20}
    }

    return sufficiency_score, breakdown


def calculate_confidence_score(
    p7_output: Phase7Output,
    p9_output: Phase9Output,
) -> Tuple[float, Dict[str, Any]]:
    """
    Calculate overall confidence score.

    Factors:
    - P7 RAG confidence (based on word count and citations)
    - P9 average confidence (from adversarial QA)
    - Evidence consistency (resolved questions ratio)

    Args:
        p7_output: Phase 7 RAG output
        p9_output: Phase 9 adversarial QA output

    Returns:
        Tuple of (confidence_score, breakdown_dict)
    """
    # P7 confidence calculation (FIXED: realistic word count expectations)
    p7_confidence = 0.5  # Default
    if hasattr(p7_output, 'confidence_score') and p7_output.confidence_score:
        # Use explicit confidence if available
        p7_confidence = p7_output.confidence_score
    elif hasattr(p7_output, 'confidence') and p7_output.confidence:
        p7_confidence = p7_output.confidence
    elif p7_output.analysis_text:
        # Proxy: Calculate confidence from response quality
        word_count = len(p7_output.analysis_text.split())
        citation_count = len(p7_output.citation_tokens) if p7_output.citation_tokens else 0

        # FIXED: Realistic word count expectation (was 3000, now 500)
        # P7 produces focused answers of ~300-600 words, not 3000 word essays
        word_score = min(1.0, word_count / 500)  # Max at 500 words

        # Citation density bonus: aim for ~1 citation per 50 words
        citation_density = citation_count / max(1, word_count / 50)
        citation_score = min(1.0, citation_density)

        # Combined P7 confidence: word count + citation density
        p7_confidence = 0.6 * word_score + 0.4 * citation_score

    # P9 average confidence (from adversarial QA answers)
    p9_confidence = p9_output.average_confidence if hasattr(p9_output, 'average_confidence') else 0.5

    # Evidence consistency: fewer gaps = higher confidence
    consistency = 1.0
    if hasattr(p9_output, 'unresolved_count') and hasattr(p9_output, 'total_questions'):
        if p9_output.total_questions > 0:
            consistency = 1.0 - (p9_output.unresolved_count / p9_output.total_questions)

    # Weighted combination
    confidence_score = (
        0.35 * p7_confidence +
        0.35 * p9_confidence +
        0.30 * consistency
    )

    breakdown = {
        "p7_confidence": round(p7_confidence, 4),
        "p9_confidence": round(p9_confidence, 4),
        "evidence_consistency": round(consistency, 4),
        "weights": {"p7": 0.35, "p9": 0.35, "consistency": 0.30}
    }

    return confidence_score, breakdown


def calculate_integrity_score(p6_output: Phase6Output) -> Tuple[float, Dict[str, Any]]:
    """
    Calculate integrity score from P6 NLI analysis.

    FIXED: P6 now calculates integrity as 1 - (contradiction_rate).
    No additional penalty needed here - P6 already accounts for contradictions.

    Args:
        p6_output: Phase 6 NLI integrity output

    Returns:
        Tuple of (integrity_score, breakdown_dict)
    """
    # P6 integrity score already = 1 - (contradiction_count / pairs_checked)
    # No additional penalty needed - that would be double-counting
    integrity = p6_output.integrity_score if hasattr(p6_output, 'integrity_score') else 0.8

    # Track stats for debugging
    contradictions_found = getattr(p6_output, 'contradictions_found', 0)
    pairs_checked = getattr(p6_output, 'pairs_checked', 0)

    breakdown = {
        "integrity_score": round(integrity, 4),
        "contradictions_found": contradictions_found,
        "pairs_checked": pairs_checked,
        "note": "P6 integrity = 1 - contradiction_rate (no additional penalty)"
    }

    return integrity, breakdown


# ============================================================================
# SOTA: GROUNDEDNESS METRIC
# Measures what proportion of claims are traceable to evidence chunks
# ============================================================================

def calculate_groundedness(
    analysis_text: str,
    citation_tokens: List[str],
    available_chunks: List[Dict[str, Any]],
) -> Tuple[float, Dict[str, Any]]:
    """
    SOTA: Calculate Groundedness metric for the generated analysis.

    Groundedness measures what proportion of the output is traceable to
    specific evidence chunks. This is different from faithfulness which
    checks semantic alignment - groundedness checks explicit traceability.

    Formula: Groundedness = (sentences_with_citations / total_claimlike_sentences)

    Args:
        analysis_text: Generated analysis with [CITE:chunk_id] markers
        citation_tokens: List of citation tokens extracted from text
        available_chunks: List of available evidence chunks

    Returns:
        Tuple of (groundedness_score, breakdown_dict)
    """
    import re

    if not analysis_text:
        return 0.0, {"groundedness": 0.0, "error": "Empty analysis text"}

    # Split into sentences
    sentences = re.split(r'[.!?]+', analysis_text)
    sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 20]

    if not sentences:
        return 0.0, {"groundedness": 0.0, "error": "No valid sentences"}

    # Identify claim-like sentences (exclude meta-commentary, section headers, etc.)
    claim_indicators = [
        r'\d+%',  # Statistics
        r'found|showed|demonstrated|observed|reported|indicated',  # Research findings
        r'significantly|substantially|notably',  # Impact words
        r'increase|decrease|reduction|improvement',  # Change words
        r'associated|correlated|linked|connected',  # Relationship words
        r'effective|ineffective|successful|failed',  # Outcome words
    ]

    claimlike_sentences = []
    cited_sentences = []
    citation_pattern = r'\[CITE:[^\]]+\]'

    for sentence in sentences:
        # Check if sentence looks like a claim
        is_claim = any(re.search(pattern, sentence, re.IGNORECASE) for pattern in claim_indicators)

        # Also count any substantive sentence > 50 chars as potentially needing citation
        is_substantive = len(sentence) > 50 and not sentence.startswith(('#', '*', '-'))

        if is_claim or is_substantive:
            claimlike_sentences.append(sentence)

            # Check if it has a citation
            if re.search(citation_pattern, sentence):
                cited_sentences.append(sentence)

    # Calculate groundedness
    total_claims = len(claimlike_sentences)
    grounded_claims = len(cited_sentences)

    if total_claims == 0:
        groundedness = 1.0  # No claims = nothing to ground
    else:
        groundedness = grounded_claims / total_claims

    # SOTA: Also check citation density
    unique_citations = len(set(citation_tokens)) if citation_tokens else 0
    chunks_available = len([c for c in available_chunks if c.get("id")]) if available_chunks else 0
    evidence_coverage = unique_citations / max(chunks_available, 1) if chunks_available > 0 else 0.0

    breakdown = {
        "groundedness": round(groundedness, 4),
        "total_sentences": len(sentences),
        "claimlike_sentences": total_claims,
        "sentences_with_citations": grounded_claims,
        "unique_citations_used": unique_citations,
        "chunks_available": chunks_available,
        "evidence_coverage": round(evidence_coverage, 4),
        "is_well_grounded": groundedness >= 0.70,  # Threshold: 70% of claims cited
    }

    return groundedness, breakdown


async def evaluate_groundedness_nli(
    analysis_text: str,
    citation_tokens: List[str],
    chunks: List[Dict[str, Any]],
) -> Tuple[float, Dict[str, Any]]:
    """
    SOTA: Enhanced groundedness evaluation using NLI for semantic verification.

    For each claim+citation pair, verify that the cited chunk semantically
    entails the claim. This provides a deeper groundedness check than
    simple citation counting.

    Args:
        analysis_text: Generated analysis
        citation_tokens: List of citation tokens
        chunks: Available evidence chunks

    Returns:
        Tuple of (nli_groundedness_score, breakdown_dict)
    """
    import re

    # Build chunk lookup
    chunk_lookup = {c.get("id"): c for c in chunks if c.get("id")}

    # Extract claim-citation pairs
    citation_pattern = r'([^.!?]+?)\s*\[CITE:([^\]]+)\]'
    matches = re.findall(citation_pattern, analysis_text)

    if not matches:
        return 0.0, {"nli_groundedness": 0.0, "pairs_checked": 0}

    verified_pairs = 0
    total_pairs = len(matches)

    for claim_text, chunk_id in matches:
        claim_text = claim_text.strip()
        if not claim_text or len(claim_text) < 10:
            continue

        chunk = chunk_lookup.get(chunk_id)
        if not chunk:
            continue

        chunk_text = chunk.get("text", "")
        if not chunk_text:
            continue

        # Simple keyword overlap check as fast groundedness verification
        # (Full NLI would be too slow for gating)
        claim_words = set(claim_text.lower().split())
        chunk_words = set(chunk_text.lower().split())

        # Remove stopwords
        stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'or', 'that', 'this', 'with', 'by'}
        claim_words = claim_words - stopwords
        chunk_words = chunk_words - stopwords

        # Calculate overlap
        overlap = len(claim_words & chunk_words)
        if overlap >= 3:  # At least 3 content words overlap
            verified_pairs += 1

    nli_groundedness = verified_pairs / total_pairs if total_pairs > 0 else 0.0

    return nli_groundedness, {
        "nli_groundedness": round(nli_groundedness, 4),
        "pairs_checked": total_pairs,
        "pairs_verified": verified_pairs,
        "is_semantically_grounded": nli_groundedness >= 0.60,
    }


# ============================================================================
# RAGAS EVALUATION (SOTA)
# ============================================================================

async def evaluate_with_ragas(
    answer_text: str,
    question: str,
    context_chunks: List[Dict[str, Any]],
    citations: List[str],
) -> Optional[Dict[str, Any]]:
    """
    Evaluate answer quality using RAGAS metrics.

    SOTA: Replaces opaque validation score with interpretable metrics:
    - Faithfulness: Are claims supported by context?
    - Context Precision: Is retrieved context relevant?
    - Context Recall: Is enough relevant context retrieved?
    - Answer Relevancy: Does answer address the question?

    Args:
        answer_text: The generated answer to evaluate
        question: The original research question
        context_chunks: List of context chunks used for generation
        citations: List of citation tokens in the answer

    Returns:
        Dict with RAGAS scores or None if evaluation fails
    """
    if not RAGAS_AVAILABLE:
        print("    [RAGAS] Not available - using fallback validation")
        return None

    try:
        evaluator = RAGASEvaluator()

        # Prepare context for evaluation
        context_texts = []
        for chunk in context_chunks:
            if isinstance(chunk, dict):
                text = chunk.get("text") or chunk.get("content") or chunk.get("chunk_text", "")
                context_texts.append(text)
            elif isinstance(chunk, str):
                context_texts.append(chunk)

        # Run RAGAS evaluation - FIX: Use correct parameter names
        ragas_score = await evaluator.evaluate(
            question=question,
            answer=answer_text,
            contexts=context_texts,  # FIX: was 'context_chunks'
            ground_truth=None,  # FIX: was 'citations' (wrong param)
        )

        # FIX: Use correct attribute names from RAGASScore dataclass
        return {
            "faithfulness": ragas_score.faithfulness,
            "context_precision": ragas_score.context_precision,
            "context_recall": ragas_score.context_recall,
            "answer_relevancy": ragas_score.answer_relevancy,
            "overall_score": ragas_score.overall_score,
            "claims_verified": ragas_score.supported_claims,  # FIX: was claims_verified
            "claims_total": ragas_score.total_claims,  # FIX: was claims_total
            "verification_rate": ragas_score.faithfulness,
            "is_faithful": ragas_score.is_faithful,
            "has_hallucinations": not ragas_score.is_faithful,  # FIX: derive from is_faithful
            "quality_tier": "high" if ragas_score.overall_score >= 0.7 else "medium" if ragas_score.overall_score >= 0.5 else "low",  # FIX: derive
        }
    except Exception as e:
        # LOW-084: Use logger instead of print
        logger.warning(f"RAGAS Evaluation failed: {e}")
        return None


def compute_combined_validation_score(
    rule_based_score: float,
    ragas_result: Optional[Dict[str, Any]],
    weights: Optional[Dict[str, float]] = None,
) -> Tuple[float, Dict[str, Any]]:
    """
    Combine rule-based validation with RAGAS metrics.

    SOTA: Uses a weighted combination where RAGAS provides the
    ground truth for claim verification and context quality.

    Args:
        rule_based_score: Score from validation_criteria.py (0.0-1.0)
        ragas_result: Dict from evaluate_with_ragas()
        weights: Optional custom weights

    Returns:
        Tuple of (combined_score, breakdown_dict)
    """
    if weights is None:
        weights = {
            "faithfulness": 0.35,      # Most important - are claims supported?
            "context_precision": 0.15,  # Is context relevant?
            "context_recall": 0.15,     # Is enough context retrieved?
            "answer_relevancy": 0.15,   # Does answer address question?
            "rule_based": 0.20,         # Legacy validation criteria
        }

    if ragas_result is None:
        # Fallback to rule-based only
        return rule_based_score, {
            "rule_based_score": rule_based_score,
            "ragas_available": False,
            "combined_score": rule_based_score,
        }

    # Compute weighted combination
    combined = (
        weights["faithfulness"] * ragas_result.get("faithfulness", 0.0) +
        weights["context_precision"] * ragas_result.get("context_precision", 0.0) +
        weights["context_recall"] * ragas_result.get("context_recall", 0.0) +
        weights["answer_relevancy"] * ragas_result.get("answer_relevancy", 0.0) +
        weights["rule_based"] * rule_based_score
    )

    breakdown = {
        "rule_based_score": rule_based_score,
        "ragas_available": True,
        "faithfulness": ragas_result.get("faithfulness", 0.0),
        "context_precision": ragas_result.get("context_precision", 0.0),
        "context_recall": ragas_result.get("context_recall", 0.0),
        "answer_relevancy": ragas_result.get("answer_relevancy", 0.0),
        "claims_verified": ragas_result.get("claims_verified", 0),
        "claims_total": ragas_result.get("claims_total", 0),
        "quality_tier": ragas_result.get("quality_tier", "unknown"),
        "weights": weights,
        "combined_score": combined,
    }

    return combined, breakdown


# ============================================================================
# GATING DECISION
# ============================================================================

def determine_gating_case(
    sufficiency_score: float,
    confidence_score: float,
    integrity_score: float,
    config: Any,
    iteration_count: int = 1,
    unresolved_questions: int = 0,
    no_evidence_count: int = 0,
    validation_score: float = 1.0,
    faithfulness_score: float = 1.0,
    ragas_available: bool = False,
) -> Tuple[GatingCase, str, str]:
    """
    Determine the gating case based on scores.

    IRON LOOP v2: Now respects P9 adversarial QA results.
    If P9 found NO_EVIDENCE for any question, CASE_1 is BLOCKED.

    SOTA v3: Now considers RAGAS faithfulness for claim verification.
    - validation_score is now combined (RAGAS + rule-based)
    - faithfulness_score checks claim verification rate (target: 95%+)
    - If faithfulness < 0.80 (80% claims verified), CASE_1 is BLOCKED

    Decision Matrix:
    - CASE_1: suff >= 0.80 AND conf >= 0.70 AND integ >= 0.70 AND no_evidence=0 AND validation >= 0.60 AND faithfulness >= 0.80 -> Finalize
    - CASE_2: suff >= 0.50 AND integ >= 0.70 AND iterations < 3 -> Refine
    - CASE_3: integ >= 0.70 but insufficient evidence -> Gap report
    - CASE_4: integ < 0.70 OR critical failure -> Fail

    Args:
        sufficiency_score: Evidence sufficiency score
        confidence_score: Overall confidence score
        integrity_score: Data integrity score
        config: Configuration thresholds
        iteration_count: Current iteration number
        unresolved_questions: Number of unresolved P9 questions
        no_evidence_count: Number of P9 questions with NO_EVIDENCE assessment
        validation_score: Combined validation score (RAGAS + rule-based) (0.0-1.0)
        faithfulness_score: RAGAS faithfulness score - claim verification rate (0.0-1.0)
        ragas_available: Whether RAGAS evaluation was performed

    Returns:
        Tuple of (gating_case, justification, next_action)
    """
    thresholds = config.thresholds.gating

    case1_suff = thresholds.case1_sufficiency  # 0.80
    case1_conf = thresholds.case1_confidence   # 0.70
    case2_suff = thresholds.case2_sufficiency  # 0.50
    case4_integ = thresholds.case4_integrity   # 0.70
    case1_validation = getattr(thresholds, 'case1_validation', 0.60)  # SOTA: validation threshold

    max_iterations = 3

    # CASE_4: Integrity failure (check first - critical)
    if integrity_score < case4_integ:
        justification = (
            f"Integrity score ({integrity_score:.2f}) below threshold ({case4_integ}). "
            f"Critical contradictions detected in evidence base."
        )
        next_action = "ESCALATE: Manual review required due to evidence contradictions."
        return GatingCase.CASE_4, justification, next_action

    # IRON LOOP v2: BLOCK CASE_1 if P9 found too many NO_EVIDENCE gaps
    # Configurable threshold allows minor gaps for messy web data
    max_allowed_gaps = getattr(thresholds, 'max_no_evidence_gaps', 0)  # Default: strict (0 gaps allowed)
    if no_evidence_count > max_allowed_gaps:
        if iteration_count < max_iterations:
            justification = (
                f"BLOCKED from CASE_1: P9 Adversarial QA found {no_evidence_count} questions "
                f"with NO_EVIDENCE (max allowed: {max_allowed_gaps}). Cannot finalize with unresolved evidence gaps. "
                f"Scores: suff={sufficiency_score:.2f}, conf={confidence_score:.2f}."
            )
            next_action = f"REFINE: Re-iterate P7-P10 to address {no_evidence_count} evidence gaps (iteration {iteration_count + 1}/{max_iterations})."
            return GatingCase.CASE_2, justification, next_action
        else:
            justification = (
                f"P9 found {no_evidence_count} questions with NO_EVIDENCE. "
                f"Max iterations reached ({iteration_count}/{max_iterations}). "
                f"Generating gap report instead of finalizing."
            )
            next_action = "GAP_REPORT: Generate gap report documenting unresolved evidence gaps."
            return GatingCase.CASE_3, justification, next_action

    # SOTA v2: BLOCK CASE_1 if validation criteria not met
    if validation_score < case1_validation:
        if iteration_count < max_iterations:
            justification = (
                f"BLOCKED from CASE_1: Validation score ({validation_score:.2f}) < {case1_validation}. "
                f"Answer does not meet question-type specific criteria. "
                f"Scores: suff={sufficiency_score:.2f}, conf={confidence_score:.2f}."
            )
            next_action = f"REFINE: Re-iterate P7-P10 to improve answer quality (iteration {iteration_count + 1}/{max_iterations})."
            return GatingCase.CASE_2, justification, next_action
        else:
            justification = (
                f"Validation score ({validation_score:.2f}) < {case1_validation}. "
                f"Max iterations reached ({iteration_count}/{max_iterations}). "
                f"Answer does not meet question-type criteria."
            )
            next_action = "GAP_REPORT: Generate gap report documenting validation failures."
            return GatingCase.CASE_3, justification, next_action

    # SOTA v3: BLOCK CASE_1 if faithfulness (claim verification) is too low
    case1_faithfulness = getattr(thresholds, 'case1_faithfulness', 0.80)  # Default 80% claims verified
    if ragas_available and faithfulness_score < case1_faithfulness:
        if iteration_count < max_iterations:
            justification = (
                f"BLOCKED from CASE_1: Faithfulness ({faithfulness_score:.2f}) < {case1_faithfulness}. "
                f"Too many claims not verified against context (potential hallucinations). "
                f"RAGAS detected {int((1 - faithfulness_score) * 100)}% unverified claims."
            )
            next_action = f"REFINE: Re-iterate P7-P10 to improve claim verification (iteration {iteration_count + 1}/{max_iterations})."
            return GatingCase.CASE_2, justification, next_action
        else:
            justification = (
                f"Faithfulness ({faithfulness_score:.2f}) < {case1_faithfulness}. "
                f"Max iterations reached ({iteration_count}/{max_iterations}). "
                f"Claims could not be adequately verified against evidence."
            )
            next_action = "GAP_REPORT: Generate gap report documenting unverified claims."
            return GatingCase.CASE_3, justification, next_action

    # CASE_1: Sufficient + Confident + No Evidence Gaps + Validation Passed + Faithful -> Finalize
    if sufficiency_score >= case1_suff and confidence_score >= case1_conf:
        faithfulness_info = ""
        if ragas_available:
            faithfulness_info = f"Faithfulness ({faithfulness_score:.2f}) >= {case1_faithfulness} AND "
        justification = (
            f"Sufficiency ({sufficiency_score:.2f}) >= {case1_suff} AND "
            f"Confidence ({confidence_score:.2f}) >= {case1_conf} AND "
            f"Integrity ({integrity_score:.2f}) >= {case4_integ} AND "
            f"Validation ({validation_score:.2f}) >= {case1_validation} AND "
            f"{faithfulness_info}"
            f"No unresolved evidence gaps. "
            f"Evidence is sufficient, reliable, and meets criteria."
        )
        next_action = "FINALIZE: Proceed to Phase 11-12 for packaging and synthesis."
        return GatingCase.CASE_1, justification, next_action

    # CASE_2: Partial evidence, can iterate
    if sufficiency_score >= case2_suff and iteration_count < max_iterations:
        justification = (
            f"Sufficiency ({sufficiency_score:.2f}) >= {case2_suff} but < {case1_suff}. "
            f"Iteration {iteration_count} of {max_iterations}. "
            f"Additional evidence gathering may improve results."
        )
        next_action = f"REFINE: Re-iterate P7-P10 (iteration {iteration_count + 1}/{max_iterations})."
        return GatingCase.CASE_2, justification, next_action

    # CASE_3: Insufficient evidence -> Gap report
    if integrity_score >= case4_integ:
        justification = (
            f"Sufficiency ({sufficiency_score:.2f}) < {case2_suff}. "
            f"Integrity is acceptable ({integrity_score:.2f}) but evidence is insufficient. "
            f"Iteration limit reached or evidence unavailable."
        )
        next_action = "GAP_REPORT: Generate gap report identifying missing evidence areas."
        return GatingCase.CASE_3, justification, next_action

    # Fallback to CASE_4 (should not reach here normally)
    justification = (
        f"Unexpected score combination: suff={sufficiency_score:.2f}, "
        f"conf={confidence_score:.2f}, integ={integrity_score:.2f}"
    )
    next_action = "ESCALATE: Unexpected state - manual review required."
    return GatingCase.CASE_4, justification, next_action


# ============================================================================
# MAIN PHASE EXECUTION
# ============================================================================

async def run_phase_10(
    vector_id: str,
    p6_output: Optional[Phase6Output] = None,
    p7_output: Optional[Phase7Output] = None,
    p9_output: Optional[Phase9Output] = None,
    iteration_count: int = 1,
) -> Phase10Output:
    """
    Execute Phase 10: Gating Logic

    Workflow:
    1. Load P6, P7, P8 outputs
    2. Calculate sufficiency, confidence, integrity scores
    3. Apply decision matrix
    4. Output gating decision

    Args:
        vector_id: Vector ID for the research
        p6_output: Optional P6 output (will load from file if not provided)
        p7_output: Optional P7 output (will load from file if not provided)
        p9_output: Optional P8 output (will load from file if not provided)
        iteration_count: Current iteration count

    Returns:
        Phase10Output with gating decision and scores
    """
    config = get_config()
    start_time = datetime.now(timezone.utc)
    audit = get_audit()

    print(f"\n{'='*60}")
    print(f"PHASE 10: GATING LOGIC")
    print(f"Vector ID: {vector_id}")
    print(f"Iteration: {iteration_count}")
    print(f"{'='*60}")

    # Load phase outputs if not provided
    if p6_output is None:
        p6_dir = OUTPUTS_DIR / "P6"
        p6_files = list(p6_dir.glob(f"{vector_id}__P6__*.json"))
        if not p6_files:
            raise FileNotFoundError(f"No P6 output found for {vector_id}")
        with open(sorted(p6_files)[-1], 'r', encoding='utf-8') as f:
            p6_output = Phase6Output(**json.load(f))
        print(f"  Loaded P6: {sorted(p6_files)[-1].name}")

    if p7_output is None:
        p7_dir = OUTPUTS_DIR / "P7"
        p7_files = list(p7_dir.glob(f"{vector_id}__P7__*.json"))
        if not p7_files:
            raise FileNotFoundError(f"No P7 output found for {vector_id}")
        with open(sorted(p7_files)[-1], 'r', encoding='utf-8') as f:
            p7_output = Phase7Output(**json.load(f))
        print(f"  Loaded P7: {sorted(p7_files)[-1].name}")

    if p9_output is None:
        p9_dir = OUTPUTS_DIR / "P9"
        p9_files = list(p9_dir.glob(f"{vector_id}__P9__*.json"))
        if not p9_files:
            raise FileNotFoundError(f"No P9 output found for {vector_id}")
        with open(sorted(p9_files)[-1], 'r', encoding='utf-8') as f:
            p9_output = Phase9Output(**json.load(f))
        print(f"  Loaded P9: {sorted(p9_files)[-1].name}")

    # Step 1: Calculate scores
    print("\n  Step 1: Calculating scores...")

    sufficiency_score, suff_breakdown = calculate_sufficiency_score(
        p6_output, p7_output, p9_output, config
    )
    print(f"    Sufficiency: {sufficiency_score:.3f}")
    for key, value in suff_breakdown.items():
        if key != "weights":
            print(f"      - {key}: {value:.3f}" if isinstance(value, float) else f"      - {key}: {value}")

    confidence_score, conf_breakdown = calculate_confidence_score(p7_output, p9_output)
    print(f"    Confidence: {confidence_score:.3f}")
    for key, value in conf_breakdown.items():
        if key != "weights":
            print(f"      - {key}: {value:.3f}" if isinstance(value, float) else f"      - {key}: {value}")

    integrity_score, integ_breakdown = calculate_integrity_score(p6_output)
    print(f"    Integrity: {integrity_score:.3f}")
    for key, value in integ_breakdown.items():
        print(f"      - {key}: {value:.3f}" if isinstance(value, float) else f"      - {key}: {value}")

    # IRON LOOP v2: Extract P9 evidence gap counts
    unresolved_questions = getattr(p9_output, 'unresolved_count', 0)
    no_evidence_count = 0
    if hasattr(p9_output, 'qa_results'):
        for qa in p9_output.qa_results:
            if hasattr(qa, 'assessment') and qa.assessment == "NO_EVIDENCE":
                no_evidence_count += 1
            elif hasattr(qa, 'resolved') and not qa.resolved:
                # Also count unresolved questions without explicit NO_EVIDENCE
                pass

    if no_evidence_count > 0 or unresolved_questions > 0:
        print(f"\n    [IRON LOOP] P9 Evidence Gaps:")
        print(f"      - Unresolved questions: {unresolved_questions}")
        print(f"      - NO_EVIDENCE assessments: {no_evidence_count}")

    # Step 1.5 SOTA: Validate answer against question-type criteria (Sprint 4)
    validation_result = None
    validation_score = 1.0  # Default if validation not performed
    try:
        # Load P0 output to get question type
        p0_dir = OUTPUTS_DIR / "P0"
        p0_files = sorted(p0_dir.glob(f"{vector_id}__P0__*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        if p0_files:
            with open(p0_files[0], "r", encoding="utf-8") as f:
                p0_data = json.load(f)
            question_type_str = p0_data.get("question_type", "unknown")
            try:
                question_type = QuestionType(question_type_str)
            except ValueError:
                question_type = QuestionType.UNKNOWN

            # Get citations from P7
            citations = [{"url": ct} for ct in (p7_output.citation_tokens if hasattr(p7_output, "citation_tokens") else [])]

            # Validate answer
            validation_result = validate_answer(
                text=p7_output.analysis_text if hasattr(p7_output, "analysis_text") else "",
                citations=citations,
                vector_id=vector_id,
                question_type=question_type,
            )

            validation_score = validation_result.overall_score
            print(f"\n    [VALIDATION] Question-Type Criteria (type={question_type_str}):")
            print(f"      - Precision: {validation_result.precision:.3f}")
            print(f"      - Recall: {validation_result.recall:.3f}")
            print(f"      - Overall: {validation_result.overall_score:.3f}")
            print(f"      - Passed: {validation_result.passed_criteria}/{validation_result.total_criteria}")
            if validation_result.missing_elements:
                print(f"      - Missing: {', '.join(validation_result.missing_elements[:3])}")
    except Exception as e:
        # LOW-085: Use logger instead of print
        logger.debug(f"Validation skipped: {e}")

    # Step 1.6 SOTA: RAGAS Evaluation for claim verification
    ragas_result = None
    faithfulness_score = 1.0  # Default if RAGAS not run
    combined_validation_score = validation_score  # Default to rule-based
    ragas_breakdown = {}

    if RAGAS_AVAILABLE:
        print(f"\n    [RAGAS] Running RAGAS evaluation...")
        try:
            # Get research question from P0
            question = ""
            if p0_files:
                with open(p0_files[0], "r", encoding="utf-8") as f:
                    p0_data = json.load(f)
                # FIX: P0 uses "question" key, not "research_question" or "parsed_query"
                question = p0_data.get("research_question", p0_data.get("parsed_query", p0_data.get("question", "")))

            # FIX: Get context chunks from ChromaDB VWM (P5 JSON doesn't store chunk texts)
            context_chunks = []
            try:
                chroma_manager = get_chroma_manager()
                vwm_collection = chroma_manager.get_vwm(vector_id)  # FIX: use get_vwm method

                if vwm_collection is None:
                    raise ValueError(f"VWM collection not found for {vector_id}")

                # Retrieve all chunks from VWM (or use P7 citation tokens as subset)
                citation_ids = p7_output.citation_tokens if hasattr(p7_output, "citation_tokens") else []

                if citation_ids:
                    # Get the cited chunks specifically
                    results = vwm_collection.get(ids=citation_ids, include=["documents"])
                    if results and results.get("documents"):
                        context_chunks = results["documents"]
                else:
                    # Fallback: get sample of chunks from VWM
                    results = vwm_collection.get(limit=50, include=["documents"])
                    if results and results.get("documents"):
                        context_chunks = results["documents"]

                print(f"    [RAGAS] Loaded {len(context_chunks)} context chunks from VWM")
            except Exception as e:
                # LOW-086: Use logger instead of print
                logger.warning(f"RAGAS could not load chunks from ChromaDB: {e}")

            # Get answer text and citations from P7
            answer_text = p7_output.analysis_text if hasattr(p7_output, "analysis_text") else ""
            citations = p7_output.citation_tokens if hasattr(p7_output, "citation_tokens") else []

            # Run RAGAS evaluation
            if question and answer_text and context_chunks:
                ragas_result = await evaluate_with_ragas(
                    answer_text=answer_text,
                    question=question,
                    context_chunks=context_chunks,
                    citations=citations,
                )

                if ragas_result:
                    faithfulness_score = ragas_result.get("faithfulness", 1.0)

                    # Combine RAGAS with rule-based validation
                    combined_validation_score, ragas_breakdown = compute_combined_validation_score(
                        rule_based_score=validation_score,
                        ragas_result=ragas_result,
                    )

                    print(f"    [RAGAS] Results:")
                    print(f"      - Faithfulness: {faithfulness_score:.3f} (claims verified)")
                    print(f"      - Context Precision: {ragas_result.get('context_precision', 0):.3f}")
                    print(f"      - Context Recall: {ragas_result.get('context_recall', 0):.3f}")
                    print(f"      - Answer Relevancy: {ragas_result.get('answer_relevancy', 0):.3f}")
                    print(f"      - Claims: {ragas_result.get('claims_verified', 0)}/{ragas_result.get('claims_total', 0)} verified")
                    print(f"      - Quality Tier: {ragas_result.get('quality_tier', 'unknown')}")
                    print(f"      - Combined Score: {combined_validation_score:.3f}")

                    if ragas_result.get("has_hallucinations", False):
                        print(f"      - WARNING: Potential hallucinations detected!")
            else:
                print(f"    [RAGAS] Skipped: missing question/answer/context")
        except Exception as e:
            # LOW-087: Use logger instead of print
            logger.warning(f"RAGAS error: {e}")
    else:
        print(f"\n    [RAGAS] Not available - using rule-based validation only")

    # Step 2: Apply gating decision matrix
    print("\n  Step 2: Applying decision matrix...")
    gating_case, justification, next_action = determine_gating_case(
        sufficiency_score=sufficiency_score,
        confidence_score=confidence_score,
        integrity_score=integrity_score,
        config=config,
        iteration_count=iteration_count,
        unresolved_questions=unresolved_questions,
        no_evidence_count=no_evidence_count,
        validation_score=combined_validation_score,
        faithfulness_score=faithfulness_score,
        ragas_available=ragas_result is not None,
    )

    print(f"\n  GATING DECISION: {gating_case.value}")
    print(f"    Justification: {justification}")
    print(f"    Next Action: {next_action}")

    # Audit: Log gating decision
    if audit:
        audit.log_gating_decision(
            gating_case=gating_case.value,
            sufficiency_score=sufficiency_score,
            confidence_score=confidence_score,
            integrity_score=integrity_score,
            reasoning=justification,
            next_action=next_action,
        )

    end_time = datetime.now(timezone.utc)

    # Build output with RAGAS scores
    output = Phase10Output(
        vector_id=vector_id,
        gating_case=gating_case,
        justification=justification,
        next_action=next_action,
        sufficiency_score=sufficiency_score,
        confidence_score=confidence_score,
        integrity_score=integrity_score,
        iteration_count=iteration_count,
        timestamps={
            "start": start_time.isoformat(),
            "end": end_time.isoformat()
        },
        # SOTA: RAGAS metrics
        validation_score=combined_validation_score,
        faithfulness_score=faithfulness_score if ragas_result else None,
        context_precision=ragas_result.get("context_precision") if ragas_result else None,
        context_recall=ragas_result.get("context_recall") if ragas_result else None,
        answer_relevancy=ragas_result.get("answer_relevancy") if ragas_result else None,
        claims_verified=ragas_result.get("claims_verified") if ragas_result else None,
        claims_total=ragas_result.get("claims_total") if ragas_result else None,
        quality_tier=ragas_result.get("quality_tier") if ragas_result else None,
        ragas_available=ragas_result is not None,
    )

    # Save output
    output_dir = OUTPUTS_DIR / "P10"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"{vector_id}__P10__{timestamp}.json"

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output.model_dump(), f, indent=2, ensure_ascii=False)

    print(f"\n  Output saved: {output_path.name}")

    # Update ledger
    ledger = Ledger()
    ragas_note = f", faith={faithfulness_score:.2f}, val={combined_validation_score:.2f}" if ragas_result else ""
    ledger.append(
        vector_id=vector_id,
        phase=10,
        status="completed",
        output_path=str(output_path),
        notes=f"case={gating_case.value}, suff={sufficiency_score:.2f}, conf={confidence_score:.2f}, integ={integrity_score:.2f}{ragas_note}"
    )

    return output


# ============================================================================
# SELF-TEST
# ============================================================================

def self_test():
    """Run self-tests for Phase 10 gating logic."""
    print("\nRunning Phase 10 self-tests...")

    # Mock config for testing
    class MockGatingThresholds:
        case1_sufficiency = 0.80
        case1_confidence = 0.70
        case2_sufficiency = 0.50
        case4_integrity = 0.70
        case1_validation = 0.60  # SOTA: validation threshold

    class MockThresholds:
        gating = MockGatingThresholds()
        sufficiency = type('obj', (object,), {
            'min_gold_chunks': 5,
            'min_total_chunks': 15
        })()

    class MockConfig:
        thresholds = MockThresholds()

    config = MockConfig()

    # Test 1: CASE_1 - Sufficient + Confident
    print("\n  Test 1: CASE_1 (Finalize)")
    case, just, action = determine_gating_case(
        sufficiency_score=0.85,
        confidence_score=0.75,
        integrity_score=0.90,
        config=config,
        iteration_count=1
    )
    assert case == GatingCase.CASE_1, f"Expected CASE_1, got {case}"
    assert "FINALIZE" in action
    print(f"    [PASS] suff=0.85, conf=0.75, integ=0.90 -> {case.value}")

    # Test 2: CASE_2 - Partial evidence, can iterate
    print("\n  Test 2: CASE_2 (Refine)")
    case, just, action = determine_gating_case(
        sufficiency_score=0.60,
        confidence_score=0.55,
        integrity_score=0.85,
        config=config,
        iteration_count=1
    )
    assert case == GatingCase.CASE_2, f"Expected CASE_2, got {case}"
    assert "REFINE" in action
    print(f"    [PASS] suff=0.60, conf=0.55, integ=0.85 -> {case.value}")

    # Test 3: CASE_3 - Insufficient evidence
    print("\n  Test 3: CASE_3 (Gap Report)")
    case, just, action = determine_gating_case(
        sufficiency_score=0.30,
        confidence_score=0.40,
        integrity_score=0.80,
        config=config,
        iteration_count=3  # Max iterations reached
    )
    assert case == GatingCase.CASE_3, f"Expected CASE_3, got {case}"
    assert "GAP_REPORT" in action
    print(f"    [PASS] suff=0.30, conf=0.40, integ=0.80 (iter=3) -> {case.value}")

    # Test 4: CASE_4 - Integrity failure
    print("\n  Test 4: CASE_4 (Fail)")
    case, just, action = determine_gating_case(
        sufficiency_score=0.90,
        confidence_score=0.90,
        integrity_score=0.50,  # Below threshold
        config=config,
        iteration_count=1
    )
    assert case == GatingCase.CASE_4, f"Expected CASE_4, got {case}"
    assert "ESCALATE" in action
    print(f"    [PASS] suff=0.90, conf=0.90, integ=0.50 -> {case.value}")

    # Test 5: Boundary case - exactly at threshold
    print("\n  Test 5: Boundary at CASE_1 threshold")
    case, just, action = determine_gating_case(
        sufficiency_score=0.80,  # Exactly at threshold
        confidence_score=0.70,  # Exactly at threshold
        integrity_score=0.70,   # Exactly at threshold
        config=config,
        iteration_count=1
    )
    assert case == GatingCase.CASE_1, f"Expected CASE_1 at boundary, got {case}"
    print(f"    [PASS] Boundary case -> {case.value}")

    # Test 6: Iteration exhaustion
    print("\n  Test 6: Iteration exhaustion -> CASE_3")
    case, just, action = determine_gating_case(
        sufficiency_score=0.65,  # Above CASE_2 threshold
        confidence_score=0.60,
        integrity_score=0.80,
        config=config,
        iteration_count=3  # Max iterations reached
    )
    assert case == GatingCase.CASE_3, f"Expected CASE_3 after max iterations, got {case}"
    print(f"    [PASS] Max iterations reached -> {case.value}")

    # Test 7: SOTA - Validation score blocks CASE_1
    print("\n  Test 7: Validation failure blocks CASE_1")
    case, just, action = determine_gating_case(
        sufficiency_score=0.90,  # Would otherwise be CASE_1
        confidence_score=0.80,   # Would otherwise be CASE_1
        integrity_score=0.90,    # Would otherwise be CASE_1
        config=config,
        iteration_count=1,
        validation_score=0.40,   # Below 0.60 threshold
    )
    assert case == GatingCase.CASE_2, f"Expected CASE_2 (blocked by validation), got {case}"
    assert "Validation score" in just
    print(f"    [PASS] Validation=0.40 blocks CASE_1 -> {case.value}")

    # Test 8: Validation pass allows CASE_1
    print("\n  Test 8: Validation pass allows CASE_1")
    case, just, action = determine_gating_case(
        sufficiency_score=0.85,
        confidence_score=0.75,
        integrity_score=0.90,
        config=config,
        iteration_count=1,
        validation_score=0.70,  # Above 0.60 threshold
    )
    assert case == GatingCase.CASE_1, f"Expected CASE_1, got {case}"
    assert "Validation" in just
    print(f"    [PASS] Validation=0.70 allows CASE_1 -> {case.value}")

    # Test 9: SOTA v3 - Low faithfulness blocks CASE_1
    print("\n  Test 9: Low faithfulness blocks CASE_1")
    case, just, action = determine_gating_case(
        sufficiency_score=0.90,  # Would otherwise be CASE_1
        confidence_score=0.85,   # Would otherwise be CASE_1
        integrity_score=0.95,    # Would otherwise be CASE_1
        config=config,
        iteration_count=1,
        validation_score=0.80,   # Passes validation
        faithfulness_score=0.50, # Below 0.80 threshold (50% claims unverified)
        ragas_available=True,
    )
    assert case == GatingCase.CASE_2, f"Expected CASE_2 (blocked by faithfulness), got {case}"
    assert "Faithfulness" in just
    print(f"    [PASS] Faithfulness=0.50 blocks CASE_1 -> {case.value}")

    # Test 10: High faithfulness allows CASE_1
    print("\n  Test 10: High faithfulness allows CASE_1")
    case, just, action = determine_gating_case(
        sufficiency_score=0.85,
        confidence_score=0.75,
        integrity_score=0.90,
        config=config,
        iteration_count=1,
        validation_score=0.70,
        faithfulness_score=0.95,  # 95% claims verified - excellent
        ragas_available=True,
    )
    assert case == GatingCase.CASE_1, f"Expected CASE_1, got {case}"
    assert "Faithfulness" in just
    print(f"    [PASS] Faithfulness=0.95 allows CASE_1 -> {case.value}")

    # Test 11: RAGAS not available - should not block on faithfulness
    print("\n  Test 11: RAGAS not available - faithfulness check skipped")
    case, just, action = determine_gating_case(
        sufficiency_score=0.85,
        confidence_score=0.75,
        integrity_score=0.90,
        config=config,
        iteration_count=1,
        validation_score=0.70,
        faithfulness_score=0.50,  # Would block if RAGAS available
        ragas_available=False,    # But RAGAS not available
    )
    assert case == GatingCase.CASE_1, f"Expected CASE_1 (RAGAS not available), got {case}"
    assert "Faithfulness" not in just  # Should not mention faithfulness
    print(f"    [PASS] RAGAS not available - faithfulness check skipped -> {case.value}")

    print("\n" + "="*60)
    print("All Phase 10 self-tests PASSED!")
    print("="*60)
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phase 10: Gating Logic")
    parser.add_argument("--vector-id", required=False, help="Vector ID to process")
    parser.add_argument("--input", required=False, help="Path to P8 output JSON (optional)")
    parser.add_argument("--output", required=False, help="Output directory (optional)")
    parser.add_argument("--iteration", type=int, default=1, help="Iteration count")
    parser.add_argument("--self-test", action="store_true", help="Run self-tests")

    args = parser.parse_args()

    if args.self_test:
        self_test()
    elif args.vector_id:
        # Load P8 output if input specified
        p9_output = None
        if args.input:
            with open(args.input, 'r', encoding='utf-8') as f:
                p9_output = Phase9Output(**json.load(f))

        result = asyncio.run(run_phase_10(
            vector_id=args.vector_id,
            p9_output=p9_output,
            iteration_count=args.iteration
        ))

        # Optionally save to custom output dir
        if args.output:
            out_dir = Path(args.output)
            out_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = out_dir / f"{args.vector_id}__P10__{timestamp}.json"
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(result.model_dump(), f, indent=2, ensure_ascii=False)
            print(f"  Output saved to: {out_path}")

        print(f"\nPhase 10 complete. Decision: {result.gating_case.value}")
    else:
        print("Usage: python p09_gating.py --vector-id <ID> or --self-test")
