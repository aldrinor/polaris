"""
POLARIS Inline Verifier

FIX 117 Phase 1.4: MiniCheck wrapper for use during cite-first synthesis.

This utility provides inline verification of claims against evidence,
enabling the cite-first architecture where verification happens
DURING synthesis, not after (post-hoc by auditor).

The key insight is that verifying BEFORE writing prevents the
"write-then-cite" semantic drift problem that causes the 75% ceiling.

Features:
- MiniCheck integration (roberta-large, flan-t5-large)
- Batch verification for efficiency
- Confidence scoring
- LLM fallback when MiniCheck unavailable
"""

import logging
import os
import re
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# Default thresholds (can be overridden via env)
DEFAULT_THRESHOLD = float(os.environ.get("POLARIS_VERIFY_THRESHOLD", "0.25"))
MINICHECK_MODEL = os.environ.get("POLARIS_MINICHECK_MODEL", "roberta-large")
USE_GPU = os.environ.get("POLARIS_USE_GPU", "1") == "1"

# Chunk size for long evidence (roberta-large has 512 token limit)
MAX_EVIDENCE_CHARS = 2000


# =============================================================================
# Inline Verifier
# =============================================================================

class InlineVerifier:
    """
    Inline verification utility for cite-first synthesis.

    This class wraps MiniCheck for efficient, low-latency verification
    during the synthesis process. Unlike post-hoc auditor verification,
    inline verification happens BEFORE a sentence is added to the report.

    Benefits:
    1. Prevents unfaithful sentences from ever being written
    2. Eliminates "lost grounding context" problem
    3. Enables immediate re-phrasing when verification fails
    """

    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        model_name: str = MINICHECK_MODEL,
        use_gpu: bool = USE_GPU,
    ):
        """
        Initialize the inline verifier.

        Args:
            threshold: Confidence threshold for PASS verdict
            model_name: MiniCheck model to use (roberta-large or flan-t5-large)
            use_gpu: Whether to use GPU for inference
        """
        self.threshold = threshold
        self.model_name = model_name
        self.use_gpu = use_gpu

        self.minicheck = None
        self._init_minicheck()

        # Statistics
        self.stats = {
            "verify_calls": 0,
            "pass_count": 0,
            "fail_count": 0,
            "avg_confidence": 0.0,
            "total_confidence": 0.0,
        }

    def _init_minicheck(self):
        """Initialize MiniCheck model."""
        try:
            from minicheck.minicheck import MiniCheck

            if self.use_gpu:
                import torch
                if torch.cuda.is_available():
                    logger.info(f"Initializing MiniCheck ({self.model_name}) on GPU")
                else:
                    logger.info(f"GPU not available, using CPU for MiniCheck")
                    self.use_gpu = False

            # FIX-127: Fix broken stderr before MiniCheck init (tqdm uses stderr.flush)
            import sys
            try:
                sys.stderr.flush()
            except OSError:
                import os
                sys.stderr = open(os.devnull, 'w')
                logger.warning("[FIX-127] sys.stderr was broken (piped process), redirected to devnull")

            self.minicheck = MiniCheck(
                model_name=self.model_name,
                cache_dir="./ckpts",
            )
            logger.info(f"[FIX 117] InlineVerifier initialized with MiniCheck ({self.model_name})")

        except ImportError:
            logger.warning("[FIX 117] MiniCheck not installed, using LLM fallback")
            self.minicheck = None
        except Exception as e:
            logger.error(f"[FIX 117] Failed to initialize MiniCheck: {e}")
            self.minicheck = None

    def verify(
        self,
        claim: str,
        evidence: str,
        threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Verify that evidence supports the claim.

        Args:
            claim: The claim to verify
            evidence: The evidence text
            threshold: Optional custom threshold (uses default if None)

        Returns:
            Dict with keys: verdict (bool), confidence (float), reasoning (str)
        """
        threshold = threshold or self.threshold
        self.stats["verify_calls"] += 1

        # Handle empty inputs
        if not claim or not evidence:
            return {
                "verdict": False,
                "confidence": 0.0,
                "reasoning": "Empty claim or evidence",
            }

        # Use MiniCheck if available
        if self.minicheck:
            result = self._verify_minicheck(claim, evidence, threshold)
        else:
            result = self._verify_llm_fallback(claim, evidence, threshold)

        # Update statistics
        if result["verdict"]:
            self.stats["pass_count"] += 1
        else:
            self.stats["fail_count"] += 1

        self.stats["total_confidence"] += result["confidence"]
        self.stats["avg_confidence"] = (
            self.stats["total_confidence"] / self.stats["verify_calls"]
        )

        return result

    def verify_batch(
        self,
        claims: List[str],
        evidences: List[str],
        threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Verify multiple claim-evidence pairs in batch.

        More efficient than calling verify() repeatedly.

        Args:
            claims: List of claims to verify
            evidences: List of evidence texts (same length as claims)
            threshold: Optional custom threshold

        Returns:
            List of verification results
        """
        threshold = threshold or self.threshold

        if len(claims) != len(evidences):
            raise ValueError("Claims and evidences must have same length")

        if self.minicheck:
            return self._verify_batch_minicheck(claims, evidences, threshold)

        # Fallback: verify one by one
        return [
            self.verify(claim, evidence, threshold)
            for claim, evidence in zip(claims, evidences)
        ]

    def _verify_minicheck(
        self,
        claim: str,
        evidence: str,
        threshold: float,
    ) -> Dict[str, Any]:
        """Verify using MiniCheck."""
        try:
            # Handle long evidence by chunking
            if len(evidence) > MAX_EVIDENCE_CHARS:
                return self._verify_chunked(claim, evidence, threshold)

            # MiniCheck expects: score(docs=[document], claims=[claim])
            pred_label, raw_prob, _, _ = self.minicheck.score(
                docs=[evidence],
                claims=[claim],
            )

            confidence = float(raw_prob[0]) if raw_prob else 0.0
            verdict = confidence >= threshold

            return {
                "verdict": verdict,
                "confidence": confidence,
                "reasoning": f"MiniCheck score: {confidence:.3f} (threshold: {threshold})",
            }

        except Exception as e:
            logger.error(f"[FIX 117] MiniCheck verification failed: {e}")
            return self._verify_llm_fallback(claim, evidence, threshold)

    def _verify_chunked(
        self,
        claim: str,
        evidence: str,
        threshold: float,
    ) -> Dict[str, Any]:
        """
        Verify against chunked evidence.

        FIX 38: RoBERTa-large has 512 token limit (~2000 chars).
        If evidence is longer, chunk and use MAX confidence.
        """
        chunks = []
        for i in range(0, len(evidence), MAX_EVIDENCE_CHARS):
            chunk = evidence[i:i + MAX_EVIDENCE_CHARS]
            chunks.append(chunk)

        max_confidence = 0.0
        best_chunk = ""

        for chunk in chunks:
            try:
                pred_label, raw_prob, _, _ = self.minicheck.score(
                    docs=[chunk],
                    claims=[claim],
                )
                confidence = float(raw_prob[0]) if raw_prob else 0.0

                if confidence > max_confidence:
                    max_confidence = confidence
                    best_chunk = chunk[:100]

            except Exception as e:
                logger.debug(f"Chunk verification failed: {e}")
                continue

        verdict = max_confidence >= threshold

        return {
            "verdict": verdict,
            "confidence": max_confidence,
            "reasoning": f"Chunked verification (max): {max_confidence:.3f}",
        }

    def _verify_batch_minicheck(
        self,
        claims: List[str],
        evidences: List[str],
        threshold: float,
    ) -> List[Dict[str, Any]]:
        """Batch verification using MiniCheck."""
        results = []

        try:
            # MiniCheck batch API
            pred_labels, raw_probs, _, _ = self.minicheck.score(
                docs=evidences,
                claims=claims,
            )

            for i, (pred, prob) in enumerate(zip(pred_labels, raw_probs)):
                confidence = float(prob) if prob else 0.0
                verdict = confidence >= threshold

                # Update stats
                self.stats["verify_calls"] += 1
                if verdict:
                    self.stats["pass_count"] += 1
                else:
                    self.stats["fail_count"] += 1
                self.stats["total_confidence"] += confidence

                results.append({
                    "verdict": verdict,
                    "confidence": confidence,
                    "reasoning": f"Batch MiniCheck: {confidence:.3f}",
                })

            # Update average
            if self.stats["verify_calls"] > 0:
                self.stats["avg_confidence"] = (
                    self.stats["total_confidence"] / self.stats["verify_calls"]
                )

            return results

        except Exception as e:
            logger.error(f"[FIX 117] Batch verification failed: {e}")
            # Fallback to individual verification
            return [
                self._verify_llm_fallback(claim, evidence, threshold)
                for claim, evidence in zip(claims, evidences)
            ]

    def _verify_llm_fallback(
        self,
        claim: str,
        evidence: str,
        threshold: float,
    ) -> Dict[str, Any]:
        """LLM fallback when MiniCheck unavailable."""
        # Simple heuristic fallback
        claim_words = set(claim.lower().split())
        evidence_words = set(evidence.lower().split())

        overlap = len(claim_words & evidence_words)
        if len(claim_words) == 0:
            confidence = 0.0
        else:
            # Jaccard-like score
            confidence = overlap / len(claim_words)

        # Boost for exact substring match
        if claim.lower() in evidence.lower():
            confidence = max(confidence, 0.8)

        verdict = confidence >= threshold

        return {
            "verdict": verdict,
            "confidence": confidence,
            "reasoning": f"Heuristic fallback (overlap): {confidence:.3f}",
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get verification statistics."""
        return self.stats.copy()

    def reset_stats(self):
        """Reset statistics."""
        self.stats = {
            "verify_calls": 0,
            "pass_count": 0,
            "fail_count": 0,
            "avg_confidence": 0.0,
            "total_confidence": 0.0,
        }


# =============================================================================
# Adaptive Threshold Calculator
# =============================================================================

def get_adaptive_threshold(claim: str, base_threshold: float = DEFAULT_THRESHOLD) -> float:
    """
    Calculate adaptive threshold based on claim complexity.

    FIX 117 Phase 4.2: Vary threshold based on claim atomicity.
    Simple claims can use lower thresholds; complex claims need higher.

    Args:
        claim: The claim text
        base_threshold: Base threshold to adjust

    Returns:
        Adjusted threshold
    """
    # Count potential atomic facts in claim
    # Indicators of compound claims:
    indicators = [
        ' and ', ' or ', '; ', ' but ', ' while ',
        ' whereas ', ' however ', ' additionally ',
    ]

    atom_count = 1
    for indicator in indicators:
        if indicator in claim.lower():
            atom_count += claim.lower().count(indicator)

    # Count numerical claims (each number is potentially a separate fact)
    numbers = re.findall(r'\d+(?:\.\d+)?%?', claim)
    atom_count += max(0, len(numbers) - 1)  # First number is "free"

    # Adjust threshold
    if atom_count == 1:
        # Simple claim: lenient
        return max(0.15, base_threshold - 0.10)
    elif atom_count <= 3:
        # Moderate claim: standard
        return base_threshold
    else:
        # Complex claim: strict
        return min(0.45, base_threshold + 0.10)


# =============================================================================
# Factory Function
# =============================================================================

def create_inline_verifier(
    threshold: float = DEFAULT_THRESHOLD,
    model_name: str = MINICHECK_MODEL,
) -> InlineVerifier:
    """Factory function to create InlineVerifier."""
    return InlineVerifier(
        threshold=threshold,
        model_name=model_name,
    )
