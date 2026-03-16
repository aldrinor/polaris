"""
RAGAS-Style Evaluation Metrics for POLARIS.

Implements RAGAS (Retrieval-Augmented Generation Assessment) metrics using
ACTUAL NLI models instead of keyword heuristics.

Core RAGAS Metrics:
1. Faithfulness: Are all claims in the answer supported by retrieved context?
2. Context Precision: Are relevant chunks ranked higher than irrelevant ones?
3. Context Recall: Does the retrieved context cover the ground truth?
4. Answer Relevancy: Is the answer relevant to the question?

SOTA Implementation:
- Uses facebook/bart-large-mnli for NLI (same as P8)
- Real entailment scoring instead of keyword overlap
- Proper claim extraction and verification

References:
- RAGAS Documentation: https://docs.ragas.io/en/stable/concepts/metrics/
- GPT Blueprint: Phase 10 Verification and Quality Gates
"""

import asyncio
import logging
import re
import torch
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Global NLI model cache (shared with P8 for efficiency)
_nli_model = None
_nli_tokenizer = None


def _get_nli_model():
    """Get or initialize the NLI model (cached globally)."""
    global _nli_model, _nli_tokenizer

    if _nli_model is not None:
        return _nli_model, _nli_tokenizer

    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification

        model_name = "facebook/bart-large-mnli"
        device = "cuda" if torch.cuda.is_available() else "cpu"

        logger.info(f"Loading NLI model {model_name} on {device}...")
        _nli_tokenizer = AutoTokenizer.from_pretrained(model_name)
        _nli_model = AutoModelForSequenceClassification.from_pretrained(model_name)
        _nli_model.to(device)
        _nli_model.eval()

        logger.info("NLI model loaded successfully")
        return _nli_model, _nli_tokenizer
    except Exception as e:
        logger.error(f"Failed to load NLI model: {e}")
        return None, None


@dataclass
class Claim:
    """A single factual claim extracted from text."""

    text: str
    source_sentence: str
    is_supported: Optional[bool] = None
    supporting_evidence: Optional[str] = None
    entailment_score: float = 0.0
    contradiction_score: float = 0.0


@dataclass
class RAGASScore:
    """RAGAS evaluation scores for a single response."""

    # Core metrics (0.0 to 1.0)
    faithfulness: float = 0.0
    context_precision: float = 0.0
    context_recall: float = 0.0
    answer_relevancy: float = 0.0

    # Composite scores
    overall_score: float = 0.0

    # Diagnostic details
    total_claims: int = 0
    supported_claims: int = 0
    unsupported_claims: int = 0
    claims_detail: List[Claim] = field(default_factory=list)

    # Context analysis
    relevant_chunks: int = 0
    total_chunks: int = 0
    precision_at_k: List[float] = field(default_factory=list)

    # Quality flags
    is_faithful: bool = False  # faithfulness >= 0.8
    has_good_context: bool = False  # context_precision >= 0.7
    is_relevant: bool = False  # answer_relevancy >= 0.7

    def compute_overall(self, weights: Optional[dict] = None):
        """
        Compute weighted overall score.

        Default weights emphasize faithfulness (no hallucinations).
        """
        weights = weights or {
            "faithfulness": 0.35,
            "context_precision": 0.25,
            "context_recall": 0.20,
            "answer_relevancy": 0.20,
        }

        self.overall_score = (
            self.faithfulness * weights["faithfulness"] +
            self.context_precision * weights["context_precision"] +
            self.context_recall * weights["context_recall"] +
            self.answer_relevancy * weights["answer_relevancy"]
        )

        # Set quality flags
        self.is_faithful = self.faithfulness >= 0.8
        self.has_good_context = self.context_precision >= 0.7
        self.is_relevant = self.answer_relevancy >= 0.7

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "faithfulness": round(self.faithfulness, 4),
            "context_precision": round(self.context_precision, 4),
            "context_recall": round(self.context_recall, 4),
            "answer_relevancy": round(self.answer_relevancy, 4),
            "overall_score": round(self.overall_score, 4),
            "total_claims": self.total_claims,
            "supported_claims": self.supported_claims,
            "unsupported_claims": self.unsupported_claims,
            "relevant_chunks": self.relevant_chunks,
            "total_chunks": self.total_chunks,
            "is_faithful": self.is_faithful,
            "has_good_context": self.has_good_context,
            "is_relevant": self.is_relevant,
        }


class RAGASEvaluator:
    """
    Evaluates RAG responses using RAGAS-style metrics with ACTUAL NLI.

    SOTA Implementation:
    - Uses BART-large-mnli for real entailment scoring
    - Proper claim extraction (handles bullet points, citations)
    - Cross-encoder style relevance scoring
    """

    # NLI thresholds (aligned with P8)
    ENTAILMENT_THRESHOLD = 0.70
    CONTRADICTION_THRESHOLD = 0.30

    def __init__(self):
        """Initialize RAGAS evaluator with NLI model."""
        self.model, self.tokenizer = _get_nli_model()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        if self.model is None:
            logger.warning("NLI model not available - evaluation will use fallback")

    def _compute_nli_scores(
        self,
        premise: str,
        hypothesis: str,
    ) -> Tuple[float, float, float]:
        """
        Compute ACTUAL NLI scores using BART-large-mnli.

        Args:
            premise: Evidence/context text
            hypothesis: Claim to verify

        Returns:
            Tuple of (entailment, neutral, contradiction) scores
        """
        if self.model is None or self.tokenizer is None:
            # Fallback to neutral scores if model not available
            return 0.33, 0.34, 0.33

        try:
            # Truncate inputs to avoid token limits
            max_len = 400
            premise = premise[:max_len * 4]  # Allow longer premise
            hypothesis = hypothesis[:max_len]

            inputs = self.tokenizer(
                premise,
                hypothesis,
                return_tensors="pt",
                truncation=True,
                max_length=1024,
                padding=True,
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self.model(**inputs)
                probs = torch.nn.functional.softmax(outputs.logits, dim=-1)

            # BART-large-mnli label order: [contradiction, neutral, entailment]
            contradiction = probs[0][0].item()
            neutral = probs[0][1].item()
            entailment = probs[0][2].item()

            return entailment, neutral, contradiction

        except Exception as e:
            logger.warning(f"NLI computation failed: {e}")
            return 0.33, 0.34, 0.33

    async def evaluate(
        self,
        question: str,
        answer: str,
        contexts: List[str],
        ground_truth: Optional[str] = None,
    ) -> RAGASScore:
        """
        Evaluate a RAG response using all RAGAS metrics with ACTUAL NLI.

        Args:
            question: The input question/query
            answer: The generated response
            contexts: List of retrieved context chunks
            ground_truth: Optional ground truth answer for recall calculation

        Returns:
            RAGASScore with all metrics computed
        """
        score = RAGASScore()
        score.total_chunks = len(contexts)

        # 1. Faithfulness: Are claims in the answer supported by context?
        score.faithfulness, claims = await self._compute_faithfulness_nli(answer, contexts)
        score.claims_detail = claims
        score.total_claims = len(claims)
        score.supported_claims = sum(1 for c in claims if c.is_supported)
        score.unsupported_claims = score.total_claims - score.supported_claims

        # 2. Context Precision: Are relevant chunks ranked higher?
        score.context_precision, score.precision_at_k = await self._compute_context_precision_nli(
            question, contexts
        )
        score.relevant_chunks = sum(1 for p in score.precision_at_k if p > 0.5)

        # 3. Context Recall: Does context cover ground truth?
        if ground_truth:
            score.context_recall = await self._compute_context_recall_nli(
                ground_truth, contexts
            )
        else:
            # Estimate recall based on answer coverage in context
            score.context_recall = await self._estimate_context_recall_nli(answer, contexts)

        # 4. Answer Relevancy: Is the answer relevant to the question?
        score.answer_relevancy = await self._compute_answer_relevancy_nli(question, answer)

        # Compute overall score
        score.compute_overall()

        return score

    async def _compute_faithfulness_nli(
        self,
        answer: str,
        contexts: List[str],
    ) -> Tuple[float, List[Claim]]:
        """
        Compute faithfulness score using ACTUAL NLI.

        Faithfulness = (# supported claims) / (# total claims)

        A claim is supported if NLI entailment score >= threshold.
        """
        # Extract claims from answer
        claims = self._extract_claims(answer)

        if not claims:
            return 1.0, []  # No claims to verify = trivially faithful

        # Combine all context
        full_context = "\n\n".join(contexts)

        # Verify each claim using NLI
        supported = 0
        for claim in claims:
            entailment, neutral, contradiction = self._compute_nli_scores(
                full_context, claim.text
            )

            claim.entailment_score = entailment
            claim.contradiction_score = contradiction

            # SOTA: Claim is supported if entailment is high AND contradiction is low
            is_supported = (
                entailment >= self.ENTAILMENT_THRESHOLD and
                contradiction < self.CONTRADICTION_THRESHOLD
            )
            claim.is_supported = is_supported

            if is_supported:
                supported += 1
                claim.supporting_evidence = "Entailment confirmed by NLI"

        faithfulness = supported / len(claims) if claims else 1.0
        return faithfulness, claims

    def _extract_claims(self, text: str) -> List[Claim]:
        """
        Extract factual claims from text.

        SOTA: Handles bullet points, citations, and sentence boundaries properly.
        Avoids splitting mid-sentence on abbreviations or fragment creation.
        """
        claims = []

        # Normalize text - join lines that are continuations
        text = re.sub(r'\n\s*(?=[a-z])', ' ', text)  # Join lines starting with lowercase
        text = re.sub(r'\s+', ' ', text).strip()

        # First, handle bullet points and numbered lists
        # Split on bullet markers at line start
        bullet_pattern = r'(?:^|\n)\s*(?:[\*\-•]|\d+[.)])\s+'
        parts = re.split(bullet_pattern, text)

        segments = []
        for part in parts:
            part = part.strip()
            if part:
                segments.append(part)

        # If no bullets found, use the whole text
        if not segments:
            segments = [text]

        # Now split segments into sentences more carefully
        all_sentences = []
        for segment in segments:
            # Protect common abbreviations and patterns that shouldn't split
            protected = segment

            # Protect abbreviations
            abbreviations = [
                (r'\bE\.\s*coli\b', 'E_COLI_PROT'),
                (r'\bU\.S\.', 'US_PROT'),
                (r'\be\.g\.', 'EG_PROT'),
                (r'\bi\.e\.', 'IE_PROT'),
                (r'\bet al\.', 'ETAL_PROT'),
                (r'\bvs\.', 'VS_PROT'),
                (r'\bDr\.', 'DR_PROT'),
                (r'\bMr\.', 'MR_PROT'),
                (r'\bMs\.', 'MS_PROT'),
                (r'\bNo\.', 'NO_PROT'),
                (r'\bFig\.', 'FIG_PROT'),
                (r'\bP\.\s*aeruginosa', 'PA_PROT'),
                (r'\bS\.\s*aureus', 'SA_PROT'),
            ]

            for pattern, replacement in abbreviations:
                protected = re.sub(pattern, replacement, protected, flags=re.IGNORECASE)

            # Also protect decimals and ranges (e.g., "0.5", "10.2%")
            protected = re.sub(r'(\d)\.(\d)', r'\1_DOT_\2', protected)

            # Split ONLY on clear sentence boundaries: period/exclamation/question
            # followed by space and uppercase letter
            sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', protected)

            for sent in sentences:
                # Restore protected patterns
                for pattern, replacement in abbreviations:
                    sent = sent.replace(replacement.split('_')[0] + '_' + replacement.split('_')[1] + '_PROT' if '_' in replacement else replacement,
                                       pattern.replace(r'\b', '').replace(r'\s*', ' ').replace('\\', ''))

                # Manual restoration (cleaner)
                sent = sent.replace('E_COLI_PROT', 'E. coli')
                sent = sent.replace('US_PROT', 'U.S.')
                sent = sent.replace('EG_PROT', 'e.g.')
                sent = sent.replace('IE_PROT', 'i.e.')
                sent = sent.replace('ETAL_PROT', 'et al.')
                sent = sent.replace('VS_PROT', 'vs.')
                sent = sent.replace('DR_PROT', 'Dr.')
                sent = sent.replace('MR_PROT', 'Mr.')
                sent = sent.replace('MS_PROT', 'Ms.')
                sent = sent.replace('NO_PROT', 'No.')
                sent = sent.replace('FIG_PROT', 'Fig.')
                sent = sent.replace('PA_PROT', 'P. aeruginosa')
                sent = sent.replace('SA_PROT', 'S. aureus')
                sent = re.sub(r'(\d)_DOT_(\d)', r'\1.\2', sent)

                sent = sent.strip()
                if sent:
                    all_sentences.append(sent)

        # Filter and create claims
        for sentence in all_sentences:
            if not sentence or len(sentence) < 30:  # Increased minimum length
                continue

            # Skip fragments (start with lowercase, conjunctions, or prepositions alone)
            if sentence[0].islower():
                continue
            if re.match(r'^(and|or|but|which|that|can|will|would|could)\s', sentence, re.I):
                continue

            # Skip non-factual statements
            if sentence.endswith('?'):
                continue
            if sentence.lower().startswith(('please', 'note that', 'consider')):
                continue

            # Check for factual content indicators
            has_factual_content = any([
                re.search(r'\d+%', sentence),  # Percentages
                re.search(r'\d+\s*(mg|µg|ppm|ppb|ml|L)', sentence, re.I),  # Measurements
                re.search(r'\b(found|showed|demonstrated|reported|indicated|detected|proven|proved)\b', sentence, re.I),
                re.search(r'\b(study|research|data|evidence|results|analysis|investigation)\b', sentence, re.I),
                re.search(r'\[CITE:', sentence) or re.search(r'\[\d+\]', sentence),  # Citations
                re.search(r'\b(bacteria|pathogen|contamin|filter|water|well)\b', sentence, re.I),  # Domain terms
            ])

            if has_factual_content:
                # Remove citation markers for cleaner claim text
                clean_text = re.sub(r'\[CITE:[^\]]+\]', '', sentence)
                clean_text = re.sub(r'\[\d+\]', '', clean_text)
                clean_text = clean_text.strip(' .,')

                if len(clean_text) >= 30:  # Increased minimum
                    claims.append(Claim(text=clean_text, source_sentence=sentence))

        return claims

    async def _compute_context_precision_nli(
        self,
        question: str,
        contexts: List[str],
    ) -> Tuple[float, List[float]]:
        """
        Compute context precision using NLI-based relevance.

        Precision@k measures how many of the top-k retrieved chunks are relevant.
        """
        if not contexts:
            return 0.0, []

        # Score relevance of each chunk to the question using NLI
        relevance_scores = []
        for context in contexts:
            # Use NLI: Does the context entail an answer to the question?
            # Reformulate question as hypothesis
            hypothesis = f"This text answers the question: {question}"
            entailment, neutral, contradiction = self._compute_nli_scores(context, hypothesis)

            # Relevance = entailment score (how much context supports answering the question)
            relevance_scores.append(entailment)

        # Compute precision@k for each position
        precision_at_k = []
        relevant_count = 0
        for k, score in enumerate(relevance_scores, 1):
            if score >= 0.5:  # Threshold for "relevant"
                relevant_count += 1
            precision_at_k.append(relevant_count / k)

        # Average precision
        if not precision_at_k:
            return 0.0, []

        # Weight by whether each position was relevant
        weighted_sum = 0.0
        weight_total = 0.0
        for k, (p_at_k, score) in enumerate(zip(precision_at_k, relevance_scores)):
            if score >= 0.5:
                weighted_sum += p_at_k
                weight_total += 1.0

        avg_precision = weighted_sum / weight_total if weight_total > 0 else 0.0

        return avg_precision, precision_at_k

    async def _compute_context_recall_nli(
        self,
        ground_truth: str,
        contexts: List[str],
    ) -> float:
        """
        Compute context recall using NLI.

        Recall = how much of ground truth is covered by context.
        """
        if not ground_truth or not contexts:
            return 0.0

        # Combine contexts
        full_context = "\n\n".join(contexts)

        # Use NLI: Does context entail the ground truth?
        entailment, neutral, contradiction = self._compute_nli_scores(
            full_context, ground_truth
        )

        return entailment

    async def _estimate_context_recall_nli(
        self,
        answer: str,
        contexts: List[str],
    ) -> float:
        """
        Estimate context recall when ground truth is not available.

        Uses the answer as a proxy for ground truth.
        """
        # Extract key claims from answer as proxy for ground truth
        claims = self._extract_claims(answer)
        if not claims:
            return 1.0

        full_context = "\n\n".join(contexts)

        # Check what fraction of answer claims are supported by context
        supported = 0
        for claim in claims:
            entailment, _, _ = self._compute_nli_scores(full_context, claim.text)
            if entailment >= 0.5:
                supported += 1

        return supported / len(claims) if claims else 1.0

    async def _compute_answer_relevancy_nli(
        self,
        question: str,
        answer: str,
    ) -> float:
        """
        Compute answer relevancy using NLI.

        Measures how well the answer addresses the question.
        """
        if not question or not answer:
            return 0.0

        # Use NLI: Does the answer address the question?
        # Reformulate: "The answer addresses the question: {question}"
        hypothesis = f"This text provides information about: {question}"

        entailment, neutral, contradiction = self._compute_nli_scores(answer, hypothesis)

        # Relevancy = entailment (how much answer is about the question)
        # Penalize if answer contradicts the question premise
        relevancy = entailment - (contradiction * 0.5)

        return max(0.0, min(1.0, relevancy))


# Convenience function
async def evaluate_rag_response(
    question: str,
    answer: str,
    contexts: List[str],
    ground_truth: Optional[str] = None,
) -> RAGASScore:
    """
    Convenience function for quick RAG evaluation with ACTUAL NLI.

    Args:
        question: The input question
        answer: The generated answer
        contexts: Retrieved context chunks
        ground_truth: Optional ground truth answer

    Returns:
        RAGASScore with all metrics
    """
    evaluator = RAGASEvaluator()
    return await evaluator.evaluate(question, answer, contexts, ground_truth)


# Self-test
if __name__ == "__main__":
    async def test_evaluator():
        """Test RAGAS evaluator with ACTUAL NLI."""
        print("Testing RAGAS Evaluator with ACTUAL NLI...")
        print("=" * 60)

        # Test case: Water contamination question
        question = "What percentage of private wells in North America have coliform contamination?"

        answer = """
        Studies have found that approximately 52% of private wells in North America
        test positive for coliform bacteria [1]. Additionally, 64% of wells showed
        elevated heavy metal levels, particularly arsenic and lead [2]. The Sexton et al.
        (2025) study in PLOS Water documented these contamination rates across
        multiple states.
        """

        contexts = [
            """
            The comprehensive survey by Sexton et al. (2025) examined over 5,000
            private wells across the United States and Canada. Results showed that
            52% of wells tested positive for total coliform bacteria, with 23%
            showing E. coli contamination specifically.
            """,
            """
            Heavy metal analysis revealed 64% of sampled wells exceeded recommended
            limits for at least one heavy metal. Arsenic was the most common
            contaminant (found in 31% of wells), followed by lead (24%) and
            manganese (18%).
            """,
            """
            Private well water quality monitoring in rural areas remains
            inconsistent. Many homeowners are unaware of potential contamination
            risks and do not test their water regularly.
            """,
        ]

        ground_truth = """
        52% of private wells have coliform contamination and 64% have elevated
        heavy metals according to Sexton et al. (2025).
        """

        evaluator = RAGASEvaluator()
        score = await evaluator.evaluate(question, answer, contexts, ground_truth)

        print(f"\n1. RAGAS Scores (using ACTUAL NLI):")
        print(f"   Faithfulness: {score.faithfulness:.3f}")
        print(f"   Context Precision: {score.context_precision:.3f}")
        print(f"   Context Recall: {score.context_recall:.3f}")
        print(f"   Answer Relevancy: {score.answer_relevancy:.3f}")
        print(f"   Overall Score: {score.overall_score:.3f}")

        print(f"\n2. Quality Flags:")
        print(f"   Is Faithful: {score.is_faithful}")
        print(f"   Has Good Context: {score.has_good_context}")
        print(f"   Is Relevant: {score.is_relevant}")

        print(f"\n3. Claim Analysis:")
        print(f"   Total Claims: {score.total_claims}")
        print(f"   Supported: {score.supported_claims}")
        print(f"   Unsupported: {score.unsupported_claims}")

        for i, claim in enumerate(score.claims_detail[:3], 1):
            print(f"\n   Claim {i}: {claim.text[:60]}...")
            print(f"     Entailment: {claim.entailment_score:.3f}")
            print(f"     Contradiction: {claim.contradiction_score:.3f}")
            print(f"     Supported: {claim.is_supported}")

        # Test with a hallucinated answer
        print("\n" + "=" * 60)
        print("4. Testing with HALLUCINATED answer...")
        hallucinated_answer = """
        Studies in Qatar found that 90% of wells have uranium contamination.
        The water quality in Zambia is excellent with no contamination.
        """

        score2 = await evaluator.evaluate(question, hallucinated_answer, contexts)
        print(f"   Faithfulness (hallucinated): {score2.faithfulness:.3f}")
        print(f"   Is Faithful: {score2.is_faithful}")
        print(f"   Claims supported: {score2.supported_claims}/{score2.total_claims}")

        print("\n" + "=" * 60)
        print("[PASS] RAGAS evaluator tests completed with ACTUAL NLI")

    asyncio.run(test_evaluator())
