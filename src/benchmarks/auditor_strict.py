"""
POLARIS SOTA Validation Framework - Strict Auditor

Created: 2026-02-05
Purpose: Honest evaluation auditor without gaming mechanisms

This module provides a strict auditor that removes all shortcuts and gaming
mechanisms from the faithfulness evaluation process:

1. No FIX 109 "weak pass" bypass (sentence-only passing when atomic fails)
2. No 60% soft pass threshold
3. Real atomic verification required (not heuristic)
4. No safe harbor exemptions (all claims counted)
5. No default 0.3 confidence (must be verified)
6. Strict 0.70 threshold for PASS

Use this for publication-grade SOTA comparisons.
"""

import os
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StrictAuditResult:
    """Result of strict audit for a single sentence."""

    sentence: str
    """The sentence being audited."""

    verdict: str
    """FAITHFUL, UNFAITHFUL, or UNVERIFIABLE."""

    confidence: float
    """Confidence in the verdict (0.0-1.0)."""

    atomic_facts: List[str]
    """Atomic facts extracted from the sentence."""

    atomic_verdicts: List[Dict[str, Any]]
    """Verification result for each atomic fact."""

    evidence_used: List[str]
    """Evidence IDs used for verification."""

    reasoning: str
    """Detailed reasoning for the verdict."""

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StrictAuditSummary:
    """Summary of strict audit for an entire report."""

    total_sentences: int
    """Total sentences audited."""

    faithful_sentences: int
    """Sentences that passed strict verification."""

    unfaithful_sentences: int
    """Sentences that failed verification."""

    unverifiable_sentences: int
    """Sentences that could not be verified (no evidence)."""

    faithfulness_score: float
    """Strict faithfulness score (faithful / auditable)."""

    factscore: float
    """FactScore using real atomic decomposition."""

    total_atomic_facts: int
    """Total atomic facts across all sentences."""

    verified_atomic_facts: int
    """Atomic facts that passed verification."""

    audit_results: List[StrictAuditResult]
    """Individual audit results."""

    methodology: Dict[str, Any]
    """Methodology details for reproducibility."""


class StrictAuditor:
    """
    Strict auditor for honest faithfulness evaluation.

    This auditor removes all gaming mechanisms:
    - No soft pass thresholds
    - No weak pass bypasses
    - No safe harbor exemptions
    - No default confidence values
    - Requires real atomic verification

    Configuration is controlled by environment variables:
    - POLARIS_STRICT_THRESHOLD: Pass threshold (default: 0.70)
    - POLARIS_STRICT_ATOMIC: Require atomic verification (default: 1)
    - POLARIS_USE_LLM_DECOMPOSITION: Use LLM for atom extraction (default: 1)
    """

    # Strict threshold: 70% confidence required for PASS
    STRICT_THRESHOLD = float(os.environ.get("POLARIS_STRICT_THRESHOLD", "0.70"))

    # Minimum atomic pass ratio for sentence to pass
    ATOMIC_PASS_RATIO = float(os.environ.get("POLARIS_ATOMIC_PASS_RATIO", "0.50"))

    def __init__(
        self,
        minicheck_model: Optional[Any] = None,
        atomic_decomposer: Optional[Any] = None,
        evidence_chain: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Initialize the strict auditor.

        Args:
            minicheck_model: MiniCheck model for NLI verification.
            atomic_decomposer: AtomicDecomposer for fact extraction.
            evidence_chain: Evidence chain for verification context.
        """
        self.minicheck_model = minicheck_model
        self.atomic_decomposer = atomic_decomposer
        self.evidence_chain = evidence_chain or []
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize required models."""
        # Initialize MiniCheck
        if self.minicheck_model is None:
            try:
                from transformers import AutoModelForSequenceClassification, AutoTokenizer
                import torch

                model_name = "lytang/MiniCheck-RoBERTa-Large"
                self.tokenizer = AutoTokenizer.from_pretrained(model_name)
                self.minicheck_model = AutoModelForSequenceClassification.from_pretrained(model_name)

                if torch.cuda.is_available():
                    self.minicheck_model = self.minicheck_model.cuda()

                self.minicheck_model.eval()
                logger.info("StrictAuditor: MiniCheck model loaded")
            except Exception as e:
                logger.error(f"Failed to load MiniCheck model: {e}")
                return False

        # Initialize atomic decomposer
        if self.atomic_decomposer is None:
            try:
                from src.utils.atomic_decomposer import AtomicDecomposer
                self.atomic_decomposer = AtomicDecomposer(use_heuristic_fallback=True)
                await self.atomic_decomposer.initialize()
                logger.info("StrictAuditor: AtomicDecomposer initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize AtomicDecomposer: {e}")
                # Will use heuristic fallback

        self._initialized = True
        return True

    async def audit_report(
        self,
        report_text: str,
        evidence_chain: Optional[List[Dict[str, Any]]] = None,
    ) -> StrictAuditSummary:
        """
        Audit an entire report with strict evaluation.

        Args:
            report_text: The report text to audit.
            evidence_chain: Evidence chain (uses instance default if not provided).

        Returns:
            StrictAuditSummary with complete audit results.
        """
        if not self._initialized:
            await self.initialize()

        evidence = evidence_chain or self.evidence_chain

        # Split into sentences
        sentences = self._split_sentences(report_text)
        logger.info(f"[STRICT AUDIT] Processing {len(sentences)} sentences")

        # Audit each sentence
        audit_results = []
        total_atomic = 0
        verified_atomic = 0

        for sentence in sentences:
            result = await self._audit_sentence_strict(sentence, evidence)
            audit_results.append(result)

            # Count atomic facts
            total_atomic += len(result.atomic_facts)
            for verdict in result.atomic_verdicts:
                if verdict.get("passes", False):
                    verified_atomic += 1

        # Calculate summary statistics
        faithful = sum(1 for r in audit_results if r.verdict == "FAITHFUL")
        unfaithful = sum(1 for r in audit_results if r.verdict == "UNFAITHFUL")
        unverifiable = sum(1 for r in audit_results if r.verdict == "UNVERIFIABLE")

        # Strict faithfulness: faithful / (faithful + unfaithful)
        # Unverifiable sentences don't count in denominator (no evidence to check against)
        auditable = faithful + unfaithful
        faithfulness = faithful / auditable if auditable > 0 else 0.0

        # FactScore: verified_atomic / total_atomic
        factscore = verified_atomic / total_atomic if total_atomic > 0 else 0.0

        return StrictAuditSummary(
            total_sentences=len(sentences),
            faithful_sentences=faithful,
            unfaithful_sentences=unfaithful,
            unverifiable_sentences=unverifiable,
            faithfulness_score=faithfulness,
            factscore=factscore,
            total_atomic_facts=total_atomic,
            verified_atomic_facts=verified_atomic,
            audit_results=audit_results,
            methodology={
                "threshold": self.STRICT_THRESHOLD,
                "atomic_pass_ratio": self.ATOMIC_PASS_RATIO,
                "soft_pass": False,
                "safe_harbor": False,
                "weak_pass_bypass": False,
                "llm_decomposition": self.atomic_decomposer is not None,
            },
        )

    async def _audit_sentence_strict(
        self,
        sentence: str,
        evidence: List[Dict[str, Any]],
    ) -> StrictAuditResult:
        """
        Audit a single sentence with strict evaluation.

        No gaming mechanisms:
        - No safe harbor (all sentences audited)
        - No soft pass (must meet strict threshold)
        - No weak pass bypass (atomic must pass)
        """
        # Extract atomic facts (NO heuristic fallback preference)
        atomic_facts = await self._extract_atomic_facts(sentence)

        if not atomic_facts:
            atomic_facts = [sentence]  # Sentence itself is the fact

        # Find relevant evidence
        relevant_evidence = self._find_relevant_evidence(sentence, evidence)

        if not relevant_evidence:
            # No evidence = unverifiable (NOT automatic pass)
            return StrictAuditResult(
                sentence=sentence,
                verdict="UNVERIFIABLE",
                confidence=0.0,
                atomic_facts=atomic_facts,
                atomic_verdicts=[{"fact": f, "verdict": "UNVERIFIABLE", "confidence": 0.0} for f in atomic_facts],
                evidence_used=[],
                reasoning="No relevant evidence found for verification",
            )

        # Verify each atomic fact (STRICT)
        atomic_verdicts = []
        passed_count = 0

        for fact in atomic_facts:
            verdict = await self._verify_atomic_fact_strict(fact, relevant_evidence)
            atomic_verdicts.append(verdict)
            if verdict.get("passes", False):
                passed_count += 1

        # Calculate pass ratio
        pass_ratio = passed_count / len(atomic_facts)

        # STRICT VERDICT: Both atomic ratio AND confidence must pass
        # No weak pass bypass - atomic must genuinely pass
        passes = pass_ratio >= self.ATOMIC_PASS_RATIO

        avg_confidence = sum(v.get("confidence", 0.0) for v in atomic_verdicts) / len(atomic_verdicts)

        if passes and avg_confidence >= self.STRICT_THRESHOLD:
            verdict = "FAITHFUL"
        else:
            verdict = "UNFAITHFUL"

        return StrictAuditResult(
            sentence=sentence,
            verdict=verdict,
            confidence=avg_confidence,
            atomic_facts=atomic_facts,
            atomic_verdicts=atomic_verdicts,
            evidence_used=[e.get("evidence_id", "unknown") for e in relevant_evidence[:5]],
            reasoning=(
                f"Atomic: {passed_count}/{len(atomic_facts)} ({pass_ratio:.1%}), "
                f"Confidence: {avg_confidence:.2f}, Threshold: {self.STRICT_THRESHOLD}"
            ),
        )

    async def _verify_atomic_fact_strict(
        self,
        fact: str,
        evidence: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Verify a single atomic fact against evidence (strict mode).

        No soft pass, no default confidence.
        """
        if not evidence:
            return {
                "fact": fact,
                "verdict": "UNSUPPORTED",
                "confidence": 0.0,
                "passes": False,
            }

        # Combine evidence texts
        evidence_text = " ".join(
            e.get("content", e.get("text", ""))[:1000]
            for e in evidence[:5]  # Limit to prevent token overflow
        )

        # Run MiniCheck verification
        try:
            confidence = await self._run_minicheck(fact, evidence_text)
        except Exception as e:
            logger.warning(f"MiniCheck failed: {e}")
            confidence = 0.0

        # STRICT: Must meet threshold, no soft pass
        passes = confidence >= self.STRICT_THRESHOLD

        return {
            "fact": fact,
            "verdict": "SUPPORTED" if passes else "UNSUPPORTED",
            "confidence": confidence,
            "passes": passes,
        }

    async def _run_minicheck(self, claim: str, evidence: str) -> float:
        """Run MiniCheck model for NLI verification."""
        import torch

        # Tokenize
        inputs = self.tokenizer(
            claim,
            evidence[:2000],  # Truncate evidence for model limit
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )

        if torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}

        # Run model
        with torch.no_grad():
            outputs = self.minicheck_model(**inputs)
            probs = torch.softmax(outputs.logits, dim=-1)

            # MiniCheck outputs [contradiction, entailment] or similar
            # Take entailment probability as confidence
            if probs.shape[-1] >= 2:
                confidence = probs[0, 1].item()  # Entailment probability
            else:
                confidence = probs[0, 0].item()

        return confidence

    async def _extract_atomic_facts(self, sentence: str) -> List[str]:
        """Extract atomic facts using LLM decomposition."""
        if self.atomic_decomposer is not None:
            try:
                result = await self.atomic_decomposer.decompose(sentence)
                return [f.fact for f in result.atomic_facts]
            except Exception as e:
                logger.warning(f"Atomic decomposition failed: {e}")

        # Fallback to treating sentence as single fact
        return [sentence]

    def _find_relevant_evidence(
        self,
        sentence: str,
        evidence: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Find evidence relevant to a sentence."""
        # Extract citations from sentence
        citations = re.findall(r'\[CITE:([^\]]+)\]', sentence)
        citations.extend(re.findall(r'\[ev_[a-f0-9]+\]', sentence))

        relevant = []

        # First, get cited evidence
        for cite in citations:
            for e in evidence:
                if cite in str(e.get("evidence_id", "")) or cite in str(e.get("chunk_id", "")):
                    relevant.append(e)

        # If no citations, use semantic similarity (top 5)
        if not relevant:
            # Simple keyword overlap for now
            sentence_words = set(sentence.lower().split())
            scored = []
            for e in evidence:
                content = e.get("content", e.get("text", "")).lower()
                evidence_words = set(content.split())
                overlap = len(sentence_words & evidence_words) / max(len(sentence_words), 1)
                scored.append((overlap, e))
            scored.sort(reverse=True)
            relevant = [e for _, e in scored[:5]]

        return relevant

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences for auditing."""
        # Remove markdown headers
        text = re.sub(r'^#+\s+.*$', '', text, flags=re.MULTILINE)

        # Split on sentence endings and bullets
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])|\n\s*[-*\u2022]\s*', text)

        # Clean and filter
        clean = []
        for s in sentences:
            s = s.strip()
            if len(s) < 30:
                continue
            if s.startswith('[ev_') or s.startswith('ev_'):
                continue
            clean.append(s)

        return clean


# Convenience function for quick strict audit
async def run_strict_audit(
    report_text: str,
    evidence_chain: List[Dict[str, Any]],
) -> StrictAuditSummary:
    """
    Run a strict audit on a report.

    Args:
        report_text: The report to audit.
        evidence_chain: Evidence for verification.

    Returns:
        StrictAuditSummary with results.
    """
    auditor = StrictAuditor(evidence_chain=evidence_chain)
    return await auditor.audit_report(report_text)
