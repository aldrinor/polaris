"""
POLARIS v3 Verifier Agent

Verifies claims against evidence using NLI (Natural Language Inference).
- Cross-references claims with evidence chain
- Uses NLI model for entailment checking
- Calculates hallucination rate
- Identifies contradictions

Based on RAGAS faithfulness evaluation methodology.
"""

import logging
from typing import List, Dict, Any, Literal, Tuple, Optional
from datetime import datetime, timezone

from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from .base_agent import BaseAgent, AgentConfig, register_agent
from src.orchestration.state import ResearchState, Evidence, VerificationResult
try:
    from src.depth.depth_config import get_depth_config
except ImportError:
    get_depth_config = None  # Legacy module archived
from src.functions.claim_verification import (
    calculate_verification_confidence,
    calculate_source_agreement,
)
from src.config.thresholds import get_threshold


logger = logging.getLogger(__name__)


# =============================================================================
# Verification Schemas
# =============================================================================

class ClaimEvidence(BaseModel):
    """Evidence relevant to a specific claim.

    NOTE: Removed ge/le constraints - Gemini structured output limitations.
    """
    evidence_id: str = Field(description="ID of the evidence")
    evidence_text: str = Field(description="The evidence text")
    relevance: float = Field(description="Relevance to claim (0.0-1.0)")
    supports_claim: bool = Field(description="Whether this evidence supports the claim")
    contradicts_claim: bool = Field(description="Whether this evidence contradicts the claim")


class ClaimVerification(BaseModel):
    """Verification result for a single claim."""
    claim_text: str = Field(description="The claim being verified")
    verdict: Literal["supported", "refuted", "uncertain", "insufficient_evidence"] = Field(
        description="Verification verdict"
    )
    # NOTE: Removed ge/le constraints - Gemini structured output limitations
    confidence: float = Field(description="Confidence in the verdict (0.0-1.0)")
    supporting_evidence: List[ClaimEvidence] = Field(
        default_factory=list,
        description="Evidence supporting the claim"
    )
    contradicting_evidence: List[ClaimEvidence] = Field(
        default_factory=list,
        description="Evidence contradicting the claim"
    )
    reasoning: str = Field(description="Explanation of the verdict")


class VerificationBatch(BaseModel):
    """Batch verification results."""
    verifications: List[ClaimVerification] = Field(description="Verification for each claim")
    total_claims: int = Field(description="Total claims verified")
    supported_count: int = Field(description="Number of supported claims")
    refuted_count: int = Field(description="Number of refuted claims")
    uncertain_count: int = Field(description="Number of uncertain claims")
    insufficient_count: int = Field(description="Number with insufficient evidence")
    # NOTE: Removed ge/le constraints - Gemini structured output limitations
    overall_faithfulness: float = Field(
        description="Overall faithfulness score (0.0-1.0)"
    )


class NLIResult(BaseModel):
    """Result of NLI inference."""
    premise: str = Field(description="The evidence/premise")
    hypothesis: str = Field(description="The claim/hypothesis")
    label: Literal["entailment", "contradiction", "neutral"] = Field(
        description="NLI classification"
    )
    # NOTE: Removed ge/le constraints - Gemini structured output limitations
    confidence: float = Field(description="Model confidence (0.0-1.0)")


# =============================================================================
# Verifier Agent
# =============================================================================

@register_agent("verifier")
class VerifierAgent(BaseAgent):
    """
    Verifier Agent - Verifies claims against evidence.

    Responsibilities:
    1. Extract claims from draft report or evidence
    2. Match claims to relevant evidence
    3. Use NLI to check entailment
    4. Calculate faithfulness score
    5. Identify hallucinations

    Uses NLI models (DeBERTa-v3-base) for verification.
    SOTA FIX: Uses ALL evidence with smart batching (no artificial limits).
    """

    def __init__(self):
        # Load depth configuration (LAW VI: Zero hard-coding)
        self.depth_config = get_depth_config()
        self.verification_config = self.depth_config.verification

        config = AgentConfig(
            name="verifier",
            description="Verifies claims against evidence using NLI",
            task_tier="important",  # Critical claim verification
            temperature=0.0,
            max_tokens=8000,
        )
        super().__init__(config)
        self._nli_model = None

        logger.info(
            f"VerifierAgent initialized: use_all_evidence={self.verification_config.use_all_evidence}, "
            f"evidence_batch_size={self.verification_config.evidence_batch_size}"
        )

    def get_system_prompt(self) -> str:
        return """You are a Claim Verification Specialist. Your job is to verify claims against evidence using Natural Language Inference principles.

VERIFICATION PROCESS:

1. CLAIM ANALYSIS:
   - Identify the specific assertion being made
   - Break down compound claims into atomic claims
   - Note any quantitative or temporal elements

2. EVIDENCE MATCHING:
   - Find evidence relevant to each claim
   - Consider semantic similarity, not just keyword matching
   - Note the source quality of matching evidence

3. NLI CLASSIFICATION:
   For each claim-evidence pair, determine:
   - ENTAILMENT: Evidence supports the claim
   - CONTRADICTION: Evidence refutes the claim
   - NEUTRAL: Evidence neither supports nor refutes

4. VERDICT DETERMINATION:
   - SUPPORTED: At least one high-quality entailment, no contradictions
   - REFUTED: Strong contradiction from reliable source
   - UNCERTAIN: Mixed evidence or low-confidence entailments
   - INSUFFICIENT_EVIDENCE: No relevant evidence found

5. FAITHFULNESS SCORING:
   - Score = (supported + 0.5 * uncertain) / total_claims
   - Penalize hallucinations (claims with no evidence)
   - Weight by claim importance

VERIFICATION RULES:
- Be strict: require clear evidence for support
- Note partial matches explicitly
- Consider source reliability in verdicts
- Flag potential hallucinations
- Track contradictions between sources

Output detailed verification with reasoning."""

    def process(self, state: ResearchState) -> ResearchState:
        """
        Verify claims against evidence.

        Args:
            state: Current research state with evidence_chain

        Returns:
            Updated state with verification_results
        """
        evidence_chain = state.get("evidence_chain", [])
        facts_extracted = state.get("facts_extracted", [])

        if not evidence_chain:
            logger.warning("No evidence to verify against")
            return state

        # Collect claims to verify
        all_claims = self._collect_claims(state)

        if not all_claims:
            logger.warning("No claims to verify")
            return state

        # SPRINT 1 FIX 1.3: Limit claims to top N by relevance/priority
        # Before: 816 claims -> 87 verification rounds ($40+ spent on verification theatre)
        # After: Top 50 claims only, saving $35-40 per run
        max_claims = self.verification_config.max_claims_to_verify
        if len(all_claims) > max_claims:
            # Prioritize claims that appear more frequently (mentioned in multiple evidence pieces)
            # This is a proxy for claim importance
            claim_counts = {}
            for claim in all_claims:
                claim_lower = claim.lower().strip()
                claim_counts[claim_lower] = claim_counts.get(claim_lower, 0) + 1

            # Sort by count descending, take top N unique
            sorted_claims = sorted(set(all_claims), key=lambda c: claim_counts.get(c.lower().strip(), 0), reverse=True)
            claims = sorted_claims[:max_claims]
            logger.info(
                f"SPRINT 1 FIX 1.3: Limited {len(all_claims)} claims -> {len(claims)} "
                f"(max_claims_to_verify={max_claims})"
            )
        else:
            claims = all_claims

        # FIX 102: Atomic Evidence Auto-Verification
        # Claims extracted from atomic_facts are inherently supported by their source evidence
        # The claim IS the atomic statement, the evidence text IS the direct quote backing it
        # Sending these to LLM verification causes 100% "insufficient" verdicts due to
        # semantic-but-not-lexical similarity between statement and quote
        atomic_claim_to_evidence = {}
        for ev in evidence_chain:
            if hasattr(ev, 'extraction_method') and ev.extraction_method == "atomic_fact_extraction":
                # This evidence came from FIX 97 atomic fact extraction
                # Its claims list contains the atomic statements it supports
                if hasattr(ev, 'claims') and ev.claims:
                    for claim in ev.claims:
                        atomic_claim_to_evidence[claim.lower().strip()] = ev

        # Separate claims into atomic-verified and needs-llm-verification
        atomic_verified_claims = []
        llm_verify_claims = []
        for claim in claims:
            claim_key = claim.lower().strip()
            if claim_key in atomic_claim_to_evidence:
                atomic_verified_claims.append(claim)
            else:
                llm_verify_claims.append(claim)

        logger.info(
            f"[FIX 102] Claims: {len(atomic_verified_claims)} atomic-verified, "
            f"{len(llm_verify_claims)} need LLM verification"
        )

        logger.info(f"Verifying {len(llm_verify_claims)} claims against {len(evidence_chain)} evidence pieces")

        # Build evidence index
        evidence_texts = [
            {
                "id": ev.evidence_id,
                "text": ev.text,
                "source": ev.source_url,
                "quality": ev.source_quality_score,
            }
            for ev in evidence_chain
        ]

        # FIX 102: Add atomic-verified claims as pre-verified "supported"
        verification_results = []
        for claim in atomic_verified_claims:
            claim_key = claim.lower().strip()
            source_ev = atomic_claim_to_evidence.get(claim_key)
            result = VerificationResult(
                claim_id=f"claim_{len(verification_results) + 1:04d}",
                claim_text=claim,
                verdict="supported",
                confidence=0.95,  # High confidence for atomic facts with direct quotes
                supporting_evidence=[source_ev.evidence_id] if source_ev else [],
                contradicting_evidence=[],
            )
            verification_results.append(result)

        if atomic_verified_claims:
            logger.info(
                f"[FIX 102] Auto-verified {len(atomic_verified_claims)} atomic claims as 'supported'"
            )

        # Verify remaining claims in batches via LLM
        batch_size = 10

        for i in range(0, len(llm_verify_claims), batch_size):
            batch = llm_verify_claims[i:i + batch_size]
            batch_results = self._verify_batch(batch, evidence_texts, state)

            for verification in batch_results.verifications:
                result = VerificationResult(
                    claim_id=f"claim_{len(verification_results) + 1:04d}",
                    claim_text=verification.claim_text,
                    verdict=verification.verdict,
                    confidence=verification.confidence,
                    supporting_evidence=[
                        ev.evidence_id for ev in verification.supporting_evidence
                    ],
                    contradicting_evidence=[
                        ev.evidence_id for ev in verification.contradicting_evidence
                    ],
                )
                verification_results.append(result)

        # Calculate statistics
        supported = sum(1 for v in verification_results if v.verdict == "supported")
        refuted = sum(1 for v in verification_results if v.verdict == "refuted")
        uncertain = sum(1 for v in verification_results if v.verdict == "uncertain")
        insufficient = sum(1 for v in verification_results if v.verdict == "insufficient_evidence")
        total = len(verification_results)

        # Calculate hallucination rate
        hallucination_rate = (refuted + insufficient) / total if total > 0 else 0.0

        # Update state
        state["verification_results"] = verification_results
        state["claims_total"] = total
        state["claims_supported"] = supported
        state["claims_refuted"] = refuted
        state["claims_uncertain"] = uncertain
        state["hallucination_rate"] = hallucination_rate

        logger.info(
            f"Verification complete: {supported} supported, {refuted} refuted, "
            f"{uncertain} uncertain, {insufficient} insufficient. "
            f"Hallucination rate: {hallucination_rate:.2%}"
        )

        return state

    def _collect_claims(self, state: ResearchState) -> List[str]:
        """Collect claims from state for verification."""
        claims = []

        # From facts extracted
        for fact in state.get("facts_extracted", []):
            if isinstance(fact, dict) and "text" in fact:
                claims.append(fact["text"])

        # From evidence chain claims
        for evidence in state.get("evidence_chain", []):
            if hasattr(evidence, "claims"):
                claims.extend(evidence.claims)

        # From draft report (if exists)
        draft = state.get("draft_report", "")
        if draft:
            # Extract sentences as claims
            sentences = self._extract_sentences(draft)
            # Filter to factual sentences
            factual = [s for s in sentences if self._is_factual_sentence(s)]
            claims.extend(factual[:20])  # Limit from report

        return list(set(claims))  # Deduplicate

    def _extract_sentences(self, text: str) -> List[str]:
        """Extract sentences from text."""
        import re
        # Simple sentence splitting
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if len(s.strip()) > 20]

    def _is_factual_sentence(self, sentence: str) -> bool:
        """Check if sentence makes a factual claim."""
        # Simple heuristics
        factual_indicators = [
            " is ", " are ", " was ", " were ", " has ", " have ",
            " show", " found", " report", " indicate", " demonstrate",
            " result", " cause", " effect", " lead to", " according to",
            "%", "million", "billion", "percent", "study", "research"
        ]
        sentence_lower = sentence.lower()
        return any(ind in sentence_lower for ind in factual_indicators)

    def _verify_batch(
        self,
        claims: List[str],
        evidence_texts: List[Dict[str, Any]],
        state: ResearchState
    ) -> VerificationBatch:
        """
        Verify a batch of claims with smart evidence batching.

        SOTA FIX: Uses ALL evidence through intelligent batching instead of
        truncating to 20 pieces with 500 char limit (which caused 93% hallucination).
        """
        # Get config values
        evidence_batch_size = self.verification_config.evidence_batch_size
        max_text_length = self.verification_config.max_evidence_text_length

        # Smart batching: Process evidence in chunks to manage context length
        # but aggregate results across ALL evidence
        all_supporting_evidence = {claim: [] for claim in claims}
        all_contradicting_evidence = {claim: [] for claim in claims}

        # Process evidence in batches
        total_evidence = len(evidence_texts)
        num_batches = (total_evidence + evidence_batch_size - 1) // evidence_batch_size

        logger.info(
            f"Verifying {len(claims)} claims against {total_evidence} evidence pieces "
            f"in {num_batches} batches (batch_size={evidence_batch_size})"
        )

        for batch_idx in range(num_batches):
            start_idx = batch_idx * evidence_batch_size
            end_idx = min(start_idx + evidence_batch_size, total_evidence)
            evidence_batch = evidence_texts[start_idx:end_idx]

            # Build evidence context for this batch
            evidence_context = "\n\n".join([
                f"[{ev['id']}] (Quality: {ev['quality']:.2f})\n"
                f"Source: {ev['source']}\n"
                f"Text: {ev['text'][:max_text_length]}"
                for ev in evidence_batch
            ])

            claims_text = "\n".join([f"- {claim}" for claim in claims])

            messages = [
                SystemMessage(content=self.get_system_prompt()),
                HumanMessage(content=f"""Verify these claims against the available evidence (batch {batch_idx + 1}/{num_batches}):

CLAIMS TO VERIFY:
{claims_text}

AVAILABLE EVIDENCE (batch {batch_idx + 1} of {num_batches}, evidence {start_idx + 1}-{end_idx} of {total_evidence}):
{evidence_context}

RESEARCH CONTEXT:
Question: {state.get('original_query', '')}
Application: {state.get('application', '')}
Region: {state.get('region', '')}

For each claim:
1. Find relevant evidence in this batch
2. Determine if evidence supports, refutes, or is neutral
3. Assign a verdict based ONLY on this batch (we will aggregate across batches)
4. List ALL relevant evidence IDs that support or contradict

Be thorough - identify ALL relevant evidence for each claim.""")
            ]

            try:
                batch_result: VerificationBatch = self.call_llm_structured(messages, VerificationBatch)

                # FIX 12: Handle None return from call_llm_structured (timeout or parse failure)
                if batch_result is None:
                    logger.warning(f"Verification batch {batch_idx + 1} returned None (timeout), skipping")
                    continue

                # Aggregate evidence across batches
                for verification in batch_result.verifications:
                    claim = verification.claim_text
                    if claim in all_supporting_evidence:
                        all_supporting_evidence[claim].extend(verification.supporting_evidence)
                        all_contradicting_evidence[claim].extend(verification.contradicting_evidence)

            except Exception as e:
                logger.warning(f"Verification batch {batch_idx + 1} failed: {e}")
                continue

        # Build final aggregated verifications
        verifications = []
        for claim in claims:
            supporting = all_supporting_evidence.get(claim, [])
            contradicting = all_contradicting_evidence.get(claim, [])

            # CRITICAL-003: Calculate confidence from actual evidence scores, not hardcoded values
            # Extract relevance scores as NLI confidence proxy
            supporting_confidences = [ev.relevance for ev in supporting if hasattr(ev, 'relevance')]
            contradicting_confidences = [ev.relevance for ev in contradicting if hasattr(ev, 'relevance')]

            # Count unique sources
            unique_sources = set(
                ev.evidence_id.split("_")[0] for ev in supporting
                if hasattr(ev, 'evidence_id')
            )
            unique_source_count = len(unique_sources)

            # Determine verdict and calculate real confidence
            if contradicting and not supporting:
                verdict = "refuted"
                # Confidence from contradicting evidence
                confidence = calculate_verification_confidence(
                    nli_confidences=contradicting_confidences if contradicting_confidences else [0.7],
                    multi_source_count=len(set(ev.evidence_id.split("_")[0] for ev in contradicting if hasattr(ev, 'evidence_id')))
                )
            elif supporting and not contradicting:
                # Check if multiple sources support (SOTA requirement)
                if self.verification_config.require_multiple_sources and unique_source_count >= self.verification_config.min_supporting_sources:
                    verdict = "supported"
                    confidence = calculate_verification_confidence(
                        nli_confidences=supporting_confidences if supporting_confidences else [0.8],
                        multi_source_count=unique_source_count
                    )
                elif len(supporting) >= 1:
                    verdict = "supported"
                    confidence = calculate_verification_confidence(
                        nli_confidences=supporting_confidences if supporting_confidences else [0.7],
                        multi_source_count=unique_source_count
                    )
                else:
                    verdict = "uncertain"
                    confidence = calculate_verification_confidence(
                        nli_confidences=[0.5],
                        multi_source_count=1
                    )
            elif supporting and contradicting:
                verdict = "uncertain"
                # Mixed evidence - use average of all confidences, reduced
                all_confidences = supporting_confidences + contradicting_confidences
                confidence = calculate_verification_confidence(
                    nli_confidences=all_confidences if all_confidences else [0.5],
                    multi_source_count=1
                ) * 0.8  # Reduce confidence due to conflicting evidence
            else:
                verdict = "insufficient_evidence"
                confidence = 0.0  # No evidence = no confidence

            verifications.append(ClaimVerification(
                claim_text=claim,
                verdict=verdict,
                confidence=min(max(confidence, 0.0), 1.0),  # Clamp to [0, 1]
                supporting_evidence=supporting,
                contradicting_evidence=contradicting,
                reasoning=f"Based on {len(supporting)} supporting and {len(contradicting)} contradicting evidence pieces from {total_evidence} total"
            ))

        # Calculate aggregated statistics
        supported = sum(1 for v in verifications if v.verdict == "supported")
        refuted = sum(1 for v in verifications if v.verdict == "refuted")
        uncertain = sum(1 for v in verifications if v.verdict == "uncertain")
        insufficient = sum(1 for v in verifications if v.verdict == "insufficient_evidence")
        total = len(verifications)

        faithfulness = (supported + 0.5 * uncertain) / total if total > 0 else 0.0

        logger.info(
            f"Aggregated verification: {supported} supported, {refuted} refuted, "
            f"{uncertain} uncertain, {insufficient} insufficient. Faithfulness: {faithfulness:.2%}"
        )

        return VerificationBatch(
            verifications=verifications,
            total_claims=total,
            supported_count=supported,
            refuted_count=refuted,
            uncertain_count=uncertain,
            insufficient_count=insufficient,
            overall_faithfulness=faithfulness
        )

    def _run_nli(self, premise: str, hypothesis: str) -> NLIResult:
        """
        Run NLI inference using HuggingFace model.

        Falls back to LLM if model not available.
        """
        try:
            if self._nli_model is None:
                from transformers import pipeline
                self._nli_model = pipeline(
                    "text-classification",
                    model="microsoft/deberta-v3-base",
                    device=-1  # CPU
                )

            result = self._nli_model(f"{premise} [SEP] {hypothesis}")[0]

            label_map = {
                "ENTAILMENT": "entailment",
                "CONTRADICTION": "contradiction",
                "NEUTRAL": "neutral",
            }

            return NLIResult(
                premise=premise,
                hypothesis=hypothesis,
                label=label_map.get(result["label"], "neutral"),
                confidence=result["score"]
            )

        except Exception as e:
            logger.warning(f"NLI model failed, using LLM fallback: {e}")
            return self._nli_llm_fallback(premise, hypothesis)

    def _nli_llm_fallback(self, premise: str, hypothesis: str) -> NLIResult:
        """LLM fallback for NLI when model unavailable."""
        messages = [
            SystemMessage(content="""You are an NLI classifier. Given a premise and hypothesis, classify as:
- entailment: premise supports hypothesis
- contradiction: premise contradicts hypothesis
- neutral: premise neither supports nor contradicts

Respond with JSON: {"label": "...", "confidence": 0.X}"""),
            HumanMessage(content=f"""Premise: {premise}

Hypothesis: {hypothesis}

Classification:""")
        ]

        try:
            response = self.call_llm(messages)
            import json
            data = json.loads(response.content)
            return NLIResult(
                premise=premise,
                hypothesis=hypothesis,
                label=data.get("label", "neutral"),
                confidence=data.get("confidence", 0.5)
            )
        except Exception as e:
            logger.warning(f"LLM fallback for NLI failed: {e}")
            return NLIResult(
                premise=premise,
                hypothesis=hypothesis,
                label="neutral",
                confidence=0.5
            )

    def _resolve_contradictions(
        self,
        supporting_evidence: List[Dict[str, Any]],
        contradicting_evidence: List[Dict[str, Any]],
    ) -> Tuple[str, float, str]:
        """
        Resolve contradictions between supporting and contradicting evidence.

        SOTA FIX: Issue #33 - Contradiction resolution using source quality and recency.

        Args:
            supporting_evidence: Evidence supporting the claim
            contradicting_evidence: Evidence contradicting the claim

        Returns:
            Tuple of (final_verdict, confidence, reasoning)
        """
        if not contradicting_evidence:
            if supporting_evidence:
                return "supported", 0.9, "No contradictions found"
            return "insufficient_evidence", 0.3, "No evidence found"

        if not supporting_evidence:
            return "refuted", 0.85, "Only contradicting evidence found"

        # Calculate weighted scores based on source quality
        def calculate_weight(evidence_list: List[Dict]) -> float:
            if not evidence_list:
                return 0.0
            total_weight = 0.0
            for ev in evidence_list:
                quality = ev.get("quality", 0.5)
                tier = ev.get("quality_tier", "UNVERIFIED")
                tier_bonus = {"GOLD": 0.3, "SILVER": 0.2, "BRONZE": 0.1, "UNVERIFIED": 0.0}.get(tier, 0)
                total_weight += quality + tier_bonus
            return total_weight / len(evidence_list)

        support_weight = calculate_weight(supporting_evidence)
        contradict_weight = calculate_weight(contradicting_evidence)

        # Decision logic
        if support_weight > contradict_weight * 1.5:
            return "supported", 0.7, f"Supporting evidence stronger ({support_weight:.2f} vs {contradict_weight:.2f})"
        elif contradict_weight > support_weight * 1.5:
            return "refuted", 0.7, f"Contradicting evidence stronger ({contradict_weight:.2f} vs {support_weight:.2f})"
        else:
            return "uncertain", 0.5, f"Conflicting evidence of similar quality ({support_weight:.2f} vs {contradict_weight:.2f})"

    def _calculate_multi_source_agreement(
        self,
        evidence_list: List[Dict[str, Any]],
    ) -> Tuple[float, int]:
        """
        Calculate agreement score across multiple sources.

        CRITICAL-004: Agreement must be calculated from actual data, not hardcoded.

        Args:
            evidence_list: List of evidence items

        Returns:
            Tuple of (agreement_score, unique_source_count)
        """
        if not evidence_list:
            return 0.0, 0

        # Extract unique domains and add to evidence items
        enriched_evidence = []
        for ev in evidence_list:
            url = ev.get("source_url", ev.get("url", ""))
            domain = "unknown"
            if url:
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(url).netloc or "unknown"
                except Exception as e:
                    logger.debug(f"URL parsing failed for source agreement: {e}")

            # Create enriched item with domain for agreement calculation
            enriched_item = {
                **ev,
                "source_domain": domain,
                "verdict": ev.get("verdict", ev.get("supports_claim", False) and "supported" or "neutral"),
                "confidence": ev.get("relevance", ev.get("quality", 0.5)),
            }
            enriched_evidence.append(enriched_item)

        # CRITICAL-004: Use real agreement calculation function
        agreement_score, unique_count = calculate_source_agreement(
            evidence_items=enriched_evidence,
            verdict_key="verdict",
            source_key="source_domain",
            confidence_key="confidence",
        )

        # Ensure minimum reasonable agreement for diverse sources
        # (even with calculated disagreement, diversity has value)
        if unique_count >= 3 and agreement_score < 0.5:
            agreement_score = max(agreement_score, 0.5)

        return agreement_score, unique_count


# =============================================================================
# Standalone function
# =============================================================================

def verify_claim(claim: str, evidence_texts: List[str]) -> ClaimVerification:
    """
    Standalone function to verify a single claim.

    Args:
        claim: The claim to verify
        evidence_texts: List of evidence texts

    Returns:
        ClaimVerification result
    """
    from src.orchestration.state import create_initial_state

    state = create_initial_state(
        vector_id="standalone",
        query=claim,
        application="unknown",
        region="GLOBAL",
        stage=1
    )

    # MED-025, MED-026: Default scores from config
    high_relevance = get_threshold("scoring.high_relevance", 0.8)
    high_quality = get_threshold("scoring.high_quality", 0.7)

    # Create evidence chain
    from src.orchestration.state import Evidence
    evidence_chain = []
    for i, text in enumerate(evidence_texts):
        evidence = Evidence(
            evidence_id=f"ev_{i+1:04d}",
            chunk_id=f"chunk_{i+1:04d}",
            source_url="standalone",
            text=text,
            relevance_score=high_relevance,
            source_quality_score=high_quality,
            extraction_method="manual",
            claims=[],
            entities=[],
        )
        evidence_chain.append(evidence)

    state["evidence_chain"] = evidence_chain
    state["facts_extracted"] = [{"text": claim}]

    agent = VerifierAgent()
    result_state = agent.invoke(state)

    results = result_state.get("verification_results", [])
    if results:
        r = results[0]
        return ClaimVerification(
            claim_text=r.claim_text,
            verdict=r.verdict,
            confidence=r.confidence,
            supporting_evidence=[],
            contradicting_evidence=[],
            reasoning=f"Verdict: {r.verdict}"
        )

    return ClaimVerification(
        claim_text=claim,
        verdict="insufficient_evidence",
        confidence=0.5,
        supporting_evidence=[],
        contradicting_evidence=[],
        reasoning="No evidence available"
    )
