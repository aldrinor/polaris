#!/usr/bin/env python3
"""
POLARIS SAFE (Search-Augmented Factual Evaluation) Verification Module
======================================================================
Implements Google Research's SAFE technique for verifying factual claims.

SAFE works by:
1. Extracting atomic claims from generated text
2. Generating search queries for each claim
3. Searching for supporting/refuting evidence
4. Scoring claims based on evidence alignment

Reference: Decomposed Attribution Verification (SAFE) - Google Research

Usage:
    from src.utils.safe_verifier import SAFEVerifier, verify_conclusion

    verifier = SAFEVerifier()
    result = await verifier.verify_conclusion(
        conclusion_text="Water filters remove 99% of bacteria...",
        supporting_chunks=chunks_used,
    )
    # Returns verification result with scores and flags
"""

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class AtomicClaim:
    """A single atomic factual claim extracted from text."""
    claim_id: str
    text: str
    source_sentence: str
    claim_type: str  # "quantitative", "causal", "comparative", "descriptive"
    entities: List[str] = field(default_factory=list)
    verification_status: str = "pending"  # "verified", "refuted", "unsupported", "pending"
    confidence: float = 0.0
    supporting_evidence: List[str] = field(default_factory=list)
    refuting_evidence: List[str] = field(default_factory=list)


@dataclass
class SAFEVerificationResult:
    """Result of SAFE verification for a text."""
    original_text: str
    claims: List[AtomicClaim]
    overall_score: float  # 0.0 to 1.0
    verified_ratio: float  # Proportion of verified claims
    refuted_claims: List[AtomicClaim]
    unsupported_claims: List[AtomicClaim]
    verification_summary: str
    needs_revision: bool


# =============================================================================
# CLAIM EXTRACTION
# =============================================================================

def extract_atomic_claims(text: str) -> List[AtomicClaim]:
    """
    Extract atomic factual claims from text.

    An atomic claim is a single, verifiable statement that cannot be
    further decomposed without losing meaning.

    Args:
        text: Text to extract claims from

    Returns:
        List of AtomicClaim objects
    """
    claims = []
    claim_id = 0

    # Split text into sentences
    sentences = _split_sentences(text)

    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 20:
            continue

        # Extract quantitative claims (numbers, percentages)
        quant_claims = _extract_quantitative_claims(sentence)
        for claim_text in quant_claims:
            claim_id += 1
            claims.append(AtomicClaim(
                claim_id=f"claim_{claim_id:03d}",
                text=claim_text,
                source_sentence=sentence,
                claim_type="quantitative",
                entities=_extract_entities(claim_text),
            ))

        # Extract causal claims (X causes Y, X leads to Y)
        causal_claims = _extract_causal_claims(sentence)
        for claim_text in causal_claims:
            claim_id += 1
            claims.append(AtomicClaim(
                claim_id=f"claim_{claim_id:03d}",
                text=claim_text,
                source_sentence=sentence,
                claim_type="causal",
                entities=_extract_entities(claim_text),
            ))

        # Extract comparative claims (X is better/worse/higher than Y)
        comparative_claims = _extract_comparative_claims(sentence)
        for claim_text in comparative_claims:
            claim_id += 1
            claims.append(AtomicClaim(
                claim_id=f"claim_{claim_id:03d}",
                text=claim_text,
                source_sentence=sentence,
                claim_type="comparative",
                entities=_extract_entities(claim_text),
            ))

        # If no specific claim type found, treat whole sentence as descriptive claim
        # (only if it contains factual indicators)
        if not quant_claims and not causal_claims and not comparative_claims:
            if _is_factual_sentence(sentence):
                claim_id += 1
                claims.append(AtomicClaim(
                    claim_id=f"claim_{claim_id:03d}",
                    text=sentence,
                    source_sentence=sentence,
                    claim_type="descriptive",
                    entities=_extract_entities(sentence),
                ))

    return claims


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences."""
    # Handle common abbreviations
    text = re.sub(r'(\b[A-Z]\.)(\s)', r'\1<ABBR>\2', text)
    text = re.sub(r'(Dr\.|Mr\.|Mrs\.|Ms\.|Prof\.|et al\.)', r'\1<ABBR>', text)

    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', text)

    # Restore abbreviations
    sentences = [s.replace('<ABBR>', '') for s in sentences]

    return [s.strip() for s in sentences if s.strip()]


def _extract_quantitative_claims(sentence: str) -> List[str]:
    """Extract claims containing numbers, percentages, or measurements."""
    claims = []

    # Pattern for percentages
    if re.search(r'\d+(?:\.\d+)?%', sentence):
        claims.append(sentence)
        return claims  # Don't duplicate

    # Pattern for numbers with units
    if re.search(r'\d+(?:\.\d+)?\s*(?:mg|μg|ppm|ppb|ml|L|CFU|log)', sentence, re.I):
        claims.append(sentence)
        return claims

    # Pattern for ranges
    if re.search(r'\d+\s*(?:-|to)\s*\d+', sentence):
        claims.append(sentence)
        return claims

    return claims


def _extract_causal_claims(sentence: str) -> List[str]:
    """Extract claims about causation."""
    claims = []

    causal_patterns = [
        r'.+\s+(?:causes?|caused by|leads? to|results? in|contributes? to)\s+.+',
        r'.+\s+(?:because|due to|as a result of)\s+.+',
        r'.+\s+(?:increases?|decreases?|reduces?|improves?)\s+.+',
    ]

    for pattern in causal_patterns:
        if re.search(pattern, sentence, re.I):
            claims.append(sentence)
            return claims  # Don't duplicate

    return claims


def _extract_comparative_claims(sentence: str) -> List[str]:
    """Extract claims comparing entities."""
    claims = []

    comparative_patterns = [
        r'.+\s+(?:more|less|higher|lower|better|worse|greater|fewer)\s+(?:than)\s+.+',
        r'.+\s+(?:compared to|versus|vs\.?)\s+.+',
        r'.+\s+(?:outperform|exceed|surpass)\s+.+',
    ]

    for pattern in comparative_patterns:
        if re.search(pattern, sentence, re.I):
            claims.append(sentence)
            return claims  # Don't duplicate

    return claims


def _is_factual_sentence(sentence: str) -> bool:
    """Check if sentence appears to contain factual claims."""
    # Factual indicators
    factual_words = [
        'is', 'are', 'was', 'were', 'has', 'have', 'had',
        'found', 'showed', 'demonstrated', 'reported', 'indicated',
        'according to', 'research', 'study', 'data', 'evidence',
    ]

    # Opinion indicators (should NOT be treated as factual)
    opinion_words = [
        'may', 'might', 'could', 'should', 'would',
        'possibly', 'perhaps', 'likely', 'unlikely',
        'i think', 'we believe', 'it seems',
    ]

    sentence_lower = sentence.lower()

    # Check for opinion words (disqualify)
    for word in opinion_words:
        if word in sentence_lower:
            return False

    # Check for factual indicators
    for word in factual_words:
        if word in sentence_lower:
            return True

    return False


def _extract_entities(text: str) -> List[str]:
    """Extract named entities from text (simple rule-based)."""
    entities = []

    # Extract capitalized multi-word phrases (organizations, places)
    cap_phrases = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', text)
    entities.extend(cap_phrases)

    # Extract acronyms
    acronyms = re.findall(r'\b[A-Z]{2,5}\b', text)
    entities.extend(acronyms)

    # Extract chemical/biological terms
    terms = re.findall(r'\b(?:E\.\s*coli|coliform|bacteria|virus|pathogen|contaminant|filter|membrane)\b', text, re.I)
    entities.extend([t.lower() for t in terms])

    return list(set(entities))


# =============================================================================
# CLAIM VERIFICATION
# =============================================================================

def verify_claim_against_evidence(
    claim: AtomicClaim,
    evidence_chunks: List[Dict[str, Any]],
) -> AtomicClaim:
    """
    Verify a claim against available evidence chunks.

    Uses text matching and semantic similarity to determine
    if evidence supports, refutes, or is neutral on the claim.

    Args:
        claim: The claim to verify
        evidence_chunks: List of evidence chunks with 'text' field

    Returns:
        Updated AtomicClaim with verification status
    """
    supporting = []
    refuting = []

    claim_lower = claim.text.lower()
    claim_entities = [e.lower() for e in claim.entities]

    for chunk in evidence_chunks:
        chunk_text = chunk.get("text", "").lower()

        # Check entity overlap
        entity_overlap = sum(1 for e in claim_entities if e in chunk_text)
        if entity_overlap == 0:
            continue  # No relevant entities

        # Check for quantitative match (for quantitative claims)
        if claim.claim_type == "quantitative":
            # Extract numbers from both
            claim_nums = set(re.findall(r'\d+(?:\.\d+)?%?', claim_lower))
            chunk_nums = set(re.findall(r'\d+(?:\.\d+)?%?', chunk_text))

            # Check for number overlap
            if claim_nums & chunk_nums:
                supporting.append(chunk.get("text", "")[:200])
            elif claim_nums and chunk_nums:
                # Numbers present but different - potential refutation
                refuting.append(chunk.get("text", "")[:200])

        # Check for semantic alignment (keyword overlap)
        else:
            # Simple keyword overlap
            claim_words = set(re.findall(r'\b\w{4,}\b', claim_lower))
            chunk_words = set(re.findall(r'\b\w{4,}\b', chunk_text))
            overlap = len(claim_words & chunk_words)

            if overlap >= 3:  # At least 3 significant words match
                supporting.append(chunk.get("text", "")[:200])

    # Determine verification status
    claim.supporting_evidence = supporting[:3]  # Keep top 3
    claim.refuting_evidence = refuting[:3]

    if supporting and not refuting:
        claim.verification_status = "verified"
        claim.confidence = min(1.0, 0.5 + (len(supporting) * 0.2))
    elif refuting and not supporting:
        claim.verification_status = "refuted"
        claim.confidence = min(1.0, 0.5 + (len(refuting) * 0.2))
    elif supporting and refuting:
        # Mixed evidence
        if len(supporting) > len(refuting):
            claim.verification_status = "verified"
            claim.confidence = 0.5
        else:
            claim.verification_status = "refuted"
            claim.confidence = 0.5
    else:
        claim.verification_status = "unsupported"
        claim.confidence = 0.0

    return claim


# =============================================================================
# SAFE VERIFIER CLASS
# =============================================================================

class SAFEVerifier:
    """
    SAFE (Search-Augmented Factual Evaluation) Verifier.

    Verifies factual claims in generated text against evidence.
    """

    def __init__(self, strict_mode: bool = False):
        """
        Initialize SAFE verifier.

        Args:
            strict_mode: If True, require all claims to be verified
        """
        self.strict_mode = strict_mode

    def verify_conclusion(
        self,
        conclusion_text: str,
        supporting_chunks: List[Dict[str, Any]],
        min_verified_ratio: float = 0.6,
    ) -> SAFEVerificationResult:
        """
        Verify a conclusion against supporting evidence.

        Args:
            conclusion_text: The conclusion text to verify
            supporting_chunks: List of evidence chunks used to generate conclusion
            min_verified_ratio: Minimum ratio of verified claims to pass

        Returns:
            SAFEVerificationResult with detailed verification info
        """
        # Step 1: Extract atomic claims
        claims = extract_atomic_claims(conclusion_text)

        if not claims:
            return SAFEVerificationResult(
                original_text=conclusion_text,
                claims=[],
                overall_score=1.0,  # No claims to verify
                verified_ratio=1.0,
                refuted_claims=[],
                unsupported_claims=[],
                verification_summary="No factual claims detected in conclusion.",
                needs_revision=False,
            )

        # Step 2: Verify each claim against evidence
        verified_claims = []
        refuted_claims = []
        unsupported_claims = []

        for claim in claims:
            verified_claim = verify_claim_against_evidence(claim, supporting_chunks)

            if verified_claim.verification_status == "verified":
                verified_claims.append(verified_claim)
            elif verified_claim.verification_status == "refuted":
                refuted_claims.append(verified_claim)
            else:
                unsupported_claims.append(verified_claim)

        # Step 3: Calculate overall score
        total_claims = len(claims)
        verified_count = len(verified_claims)
        refuted_count = len(refuted_claims)

        verified_ratio = verified_count / total_claims if total_claims > 0 else 0.0

        # Score: verified claims contribute positively, refuted negatively
        # Unsupported claims are neutral (0)
        overall_score = (verified_count - (refuted_count * 2)) / total_claims if total_claims > 0 else 0.0
        overall_score = max(0.0, min(1.0, (overall_score + 1) / 2))  # Normalize to 0-1

        # Step 4: Determine if revision is needed
        needs_revision = (
            refuted_count > 0 or  # Any refuted claims
            verified_ratio < min_verified_ratio or  # Too few verified
            (self.strict_mode and len(unsupported_claims) > 0)  # Strict mode: no unsupported
        )

        # Step 5: Generate summary
        summary_parts = []
        summary_parts.append(f"Verified {verified_count}/{total_claims} claims ({verified_ratio:.0%}).")
        if refuted_claims:
            summary_parts.append(f"WARNING: {refuted_count} claims appear to contradict evidence.")
        if unsupported_claims:
            summary_parts.append(f"{len(unsupported_claims)} claims lack supporting evidence.")

        return SAFEVerificationResult(
            original_text=conclusion_text,
            claims=claims,
            overall_score=overall_score,
            verified_ratio=verified_ratio,
            refuted_claims=refuted_claims,
            unsupported_claims=unsupported_claims,
            verification_summary=" ".join(summary_parts),
            needs_revision=needs_revision,
        )

    def get_revision_suggestions(
        self,
        result: SAFEVerificationResult,
    ) -> List[str]:
        """
        Generate suggestions for revising conclusion based on verification.

        Args:
            result: SAFEVerificationResult from verification

        Returns:
            List of revision suggestions
        """
        suggestions = []

        # Suggestions for refuted claims
        for claim in result.refuted_claims:
            suggestions.append(
                f"REVISE: '{claim.text[:80]}...' - This claim appears to contradict evidence. "
                f"Evidence suggests: {claim.refuting_evidence[0][:100] if claim.refuting_evidence else 'N/A'}..."
            )

        # Suggestions for unsupported claims
        for claim in result.unsupported_claims:
            if claim.claim_type == "quantitative":
                suggestions.append(
                    f"ADD CITATION: '{claim.text[:80]}...' - Quantitative claim needs citation support."
                )
            else:
                suggestions.append(
                    f"VERIFY: '{claim.text[:80]}...' - Claim lacks evidence in supporting chunks."
                )

        return suggestions


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def verify_conclusion(
    conclusion_text: str,
    supporting_chunks: List[Dict[str, Any]],
    strict_mode: bool = False,
) -> SAFEVerificationResult:
    """
    Verify a conclusion using SAFE methodology.

    Convenience function for one-off verification.

    Args:
        conclusion_text: Text to verify
        supporting_chunks: Evidence chunks
        strict_mode: Require all claims verified

    Returns:
        SAFEVerificationResult
    """
    verifier = SAFEVerifier(strict_mode=strict_mode)
    return verifier.verify_conclusion(conclusion_text, supporting_chunks)


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("SAFE VERIFIER MODULE SELF-TEST")
    print("=" * 60)

    # Test conclusion
    test_conclusion = """
    Water filters effectively remove contaminants from drinking water.
    Studies show that activated carbon filters remove 95% of chlorine.
    Reverse osmosis systems achieve 99.9% pathogen removal rates.
    The EPA recommends NSF-certified filters for household use.
    Filter replacement is typically needed every 6 months.
    """

    # Test evidence chunks
    test_chunks = [
        {
            "text": "Activated carbon filters have been shown to remove between 90-98% of chlorine from tap water, with most studies reporting around 95% removal efficiency.",
            "source_url": "https://epa.gov/water",
        },
        {
            "text": "Reverse osmosis (RO) filtration systems can achieve pathogen removal rates exceeding 99% for most bacterial contaminants.",
            "source_url": "https://pubmed.ncbi.nlm.nih.gov/12345",
        },
        {
            "text": "The Environmental Protection Agency (EPA) recommends using NSF/ANSI certified water filters for household drinking water treatment.",
            "source_url": "https://epa.gov/guidelines",
        },
        {
            "text": "Most manufacturers recommend replacing filter cartridges every 3-6 months depending on usage and water quality.",
            "source_url": "https://example.com/maintenance",
        },
    ]

    # Run verification
    print("\n[TEST] SAFE Verification:")
    result = verify_conclusion(test_conclusion, test_chunks)

    print(f"\n  Claims extracted: {len(result.claims)}")
    for claim in result.claims:
        print(f"    - [{claim.claim_type}] {claim.text[:60]}...")

    print(f"\n  Verified ratio: {result.verified_ratio:.0%}")
    print(f"  Overall score: {result.overall_score:.2f}")
    print(f"  Needs revision: {result.needs_revision}")
    print(f"\n  Summary: {result.verification_summary}")

    if result.refuted_claims:
        print("\n  Refuted claims:")
        for claim in result.refuted_claims:
            print(f"    - {claim.text[:60]}...")

    if result.unsupported_claims:
        print("\n  Unsupported claims:")
        for claim in result.unsupported_claims:
            print(f"    - {claim.text[:60]}...")

    # Get revision suggestions
    verifier = SAFEVerifier()
    suggestions = verifier.get_revision_suggestions(result)
    if suggestions:
        print("\n  Revision suggestions:")
        for suggestion in suggestions:
            print(f"    - {suggestion[:100]}...")

    print("\n" + "=" * 60)
    print("SELF-TEST COMPLETE")
    print("=" * 60)
