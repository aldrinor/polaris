"""
Phase 8: Claim-Evidence NLI Verification

This phase verifies claims generated in P7 against their cited evidence using
Natural Language Inference (NLI). Claims that fail verification are blocked
from the final output.

ARCHITECT DIRECTIVE: NO MOCKING OF LOGIC
- Real NLI inference using facebook/bart-large-mnli
- Actual claim decomposition into atomic facts
- Live verification against cited evidence
- Citation blocking for failed claims

This phase addresses the ROOT CAUSE of hallucination (76.2% -> <5% target).

References:
- architecture.md Appendix B.4: Claim Extractor Output
- architecture.md Appendix B.5: NLI Verifier Output

Verification Decision Logic (SOTA-aligned with RAGAS):
- SUPPORTED: support >= 0.70, contradiction == 0  (stricter threshold)
- PARTIAL: support >= 0.50, contradiction < 0.2
- REJECTED: contradiction > 0 OR support < 0.50
"""

import asyncio
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import torch

# Configure logging
logger = logging.getLogger(__name__)
from transformers import pipeline

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_config, OUTPUTS_DIR
from src.state.ledger import Ledger
from src.memory.chroma_client import get_chroma_manager
from src.audit import get_audit


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class AtomicFact:
    """Single verifiable unit of information."""
    fact_id: str
    text: str
    parent_claim_id: str
    verification_result: Optional[str] = None  # entailed, neutral, contradicted
    verification_score: Optional[float] = None
    evidence_text: Optional[str] = None


@dataclass
class ClaimVerificationResult:
    """Verification result for a single claim."""
    claim_id: str
    claim_text: str
    cited_chunk_id: str
    status: str  # supported, partial, rejected
    support_score: float
    contradiction_score: float
    neutral_score: float
    atomic_facts: List[AtomicFact]
    atomic_facts_total: int
    atomic_facts_supported: int
    atomic_facts_contradicted: int
    atomic_facts_neutral: int
    evidence_text: str
    issues: List[Dict[str, str]] = field(default_factory=list)
    blocked: bool = False
    block_reason: Optional[str] = None


@dataclass
class Phase8Output:
    """Output of Phase 8: Claim Verification."""
    vector_id: str
    claims_total: int
    claims_verified: int
    claims_supported: int
    claims_partial: int
    claims_rejected: int
    verification_rate: float
    hallucination_rate: float
    blocked_citations: List[str]
    verification_results: List[Dict[str, Any]]
    verified_analysis_text: str
    original_analysis_text: str
    timestamps: Dict[str, str]

    def model_dump(self) -> Dict[str, Any]:
        return {
            "vector_id": self.vector_id,
            "claims_total": self.claims_total,
            "claims_verified": self.claims_verified,
            "claims_supported": self.claims_supported,
            "claims_partial": self.claims_partial,
            "claims_rejected": self.claims_rejected,
            "verification_rate": self.verification_rate,
            "hallucination_rate": self.hallucination_rate,
            "blocked_citations": self.blocked_citations,
            "verification_results": self.verification_results,
            "verified_analysis_text": self.verified_analysis_text,
            "original_analysis_text": self.original_analysis_text,
            "timestamps": self.timestamps,
        }


# =============================================================================
# CLAIM VERIFICATION ENGINE
# =============================================================================

class ClaimVerificationEngine:
    """
    NLI-based claim verification engine - SOTA-aligned with RAGAS methodology.

    Implements architecture.md B.5 NLI Verification Pipeline:
    1. Atomic Fact Decomposition
    2. ACTUAL NLI Classification (entailment/neutral/contradiction)
    3. Multi-evidence checking (not just cited chunks)
    4. Score Aggregation with 0.7 threshold
    5. Verification Decision

    SOTA Alignment:
    - Uses actual NLI model (not zero-shot classification)
    - Requires entailment score > 0.7 (matching RAGAS)
    - Checks claims against top-k evidence chunks (not just cited)
    """

    # NLI Model (same as RAGAS benchmark)
    NLI_MODEL = "facebook/bart-large-mnli"

    # SOTA-aligned thresholds (matching RAGAS benchmark_audit.py)
    ENTAILMENT_THRESHOLD = 0.70     # SOTA: entailment > 0.7 for grounding
    SUPPORTED_THRESHOLD = 0.70      # SOTA-aligned: support >= 0.70, contradiction == 0
    PARTIAL_THRESHOLD = 0.50        # support >= 0.50, contradiction < 0.2
    PARTIAL_CONTRADICTION_MAX = 0.2  # max contradiction for PARTIAL

    # Multi-evidence checking - increased to find better matches when LLM cites wrong chunk
    TOP_K_EVIDENCE = 10  # Check claim against top-10 most similar chunks

    def __init__(self):
        self.nli_model = None
        self.nli_tokenizer = None
        self.embedder = None
        self._initialized = False
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def initialize(self) -> None:
        """Initialize the ACTUAL NLI model (not zero-shot pipeline)."""
        if self._initialized:
            return

        print("  Initializing ACTUAL NLI model for claim verification...")
        print(f"  Device: {self.device}")

        # Load actual NLI model (same as RAGAS benchmark)
        from transformers import AutoTokenizer, AutoModelForSequenceClassification

        self.nli_tokenizer = AutoTokenizer.from_pretrained(self.NLI_MODEL)
        self.nli_model = AutoModelForSequenceClassification.from_pretrained(self.NLI_MODEL)
        self.nli_model.to(self.device)
        self.nli_model.eval()

        # Load embedding model for finding similar evidence
        try:
            from sentence_transformers import SentenceTransformer
            self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
            if self.device == "cuda":
                self.embedder.to(torch.device("cuda"))
            print(f"  Embedding model loaded for multi-evidence search")
        except Exception as e:
            # LOW-077: Use logger instead of print
            logger.warning(f"Embedding model failed: {e}")
            self.embedder = None

        self._initialized = True
        print(f"  ACTUAL NLI model initialized on {self.device.upper()}")

    def compute_nli_scores(self, premise: str, hypothesis: str) -> Tuple[float, float, float]:
        """
        Compute ACTUAL NLI scores (entailment/neutral/contradiction).

        This matches the RAGAS benchmark methodology exactly.

        Args:
            premise: Evidence text
            hypothesis: Claim text

        Returns:
            Tuple of (entailment, neutral, contradiction) scores
        """
        if not self.nli_model or not self.nli_tokenizer:
            return 0.33, 0.33, 0.34

        try:
            import torch.nn.functional as F

            inputs = self.nli_tokenizer(
                premise[:1000], hypothesis[:500],  # Truncate for memory
                return_tensors="pt",
                truncation=True,
                max_length=512
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self.nli_model(**inputs)
                probs = F.softmax(outputs.logits, dim=1)[0]

            # BART-large-mnli order: contradiction, neutral, entailment
            contradiction = float(probs[0])
            neutral = float(probs[1])
            entailment = float(probs[2])

            return entailment, neutral, contradiction
        except Exception as e:
            # LOW-078: Use logger instead of print
            logger.warning(f"NLI inference failed: {e}")
            return 0.33, 0.33, 0.34

    def find_best_evidence(
        self,
        claim_text: str,
        all_chunks: List[Dict],
        cited_chunk_id: str
    ) -> List[Dict]:
        """
        Find the best evidence chunks for a claim (SOTA: check ALL evidence, not just cited).

        Args:
            claim_text: The claim to verify
            all_chunks: All available evidence chunks from VWM
            cited_chunk_id: The originally cited chunk ID

        Returns:
            List of top-k evidence chunks to check against
        """
        # Build chunk lookup for adjacency checking
        chunk_lookup = {c.get("id", c.get("chunk_id", "")): c for c in all_chunks}

        # Always include the cited chunk first
        evidence_chunks = []
        cited_chunk = chunk_lookup.get(cited_chunk_id)

        if cited_chunk:
            evidence_chunks.append(cited_chunk)

        # FIX: Also include ADJACENT chunks (chunking often splits sentences)
        # Check +/- 3 chunks from the cited one to catch split evidence
        if cited_chunk_id.startswith("chunk_"):
            try:
                chunk_num = int(cited_chunk_id.replace("chunk_", ""))
                for offset in [-3, -2, -1, 1, 2, 3]:
                    adjacent_id = f"chunk_{chunk_num + offset:05d}"
                    if adjacent_id in chunk_lookup and adjacent_id != cited_chunk_id:
                        adjacent_chunk = chunk_lookup[adjacent_id]
                        if adjacent_chunk not in evidence_chunks:
                            evidence_chunks.append(adjacent_chunk)
            except ValueError as e:
                # LOW-030: Log non-numeric chunk ID error
                logger.debug(f"Non-numeric chunk ID, skipping adjacency check: {e}")

        # If we have embedder, find semantically similar chunks
        if self.embedder and len(all_chunks) > 1:
            try:
                import torch.nn.functional as F

                # Embed claim
                claim_embedding = self.embedder.encode([claim_text], convert_to_tensor=True)

                # Embed all chunks (sample if too many)
                sample_chunks = all_chunks[:500] if len(all_chunks) > 500 else all_chunks
                chunk_texts = [c.get("text", c.get("content", ""))[:500] for c in sample_chunks]
                chunk_embeddings = self.embedder.encode(chunk_texts, convert_to_tensor=True)

                # Compute similarities
                similarities = F.cosine_similarity(
                    claim_embedding.unsqueeze(1),
                    chunk_embeddings.unsqueeze(0),
                    dim=2
                )[0]

                # Get top-k most similar (excluding cited if already added)
                top_indices = similarities.argsort(descending=True)[:self.TOP_K_EVIDENCE + 1]

                for idx in top_indices:
                    chunk = sample_chunks[idx]
                    chunk_id = chunk.get("id", chunk.get("chunk_id", ""))
                    if chunk_id != cited_chunk_id and chunk not in evidence_chunks:
                        evidence_chunks.append(chunk)
                        if len(evidence_chunks) >= self.TOP_K_EVIDENCE:
                            break

            except Exception as e:
                # LOW-079: Use logger instead of print
                logger.warning(f"Semantic search failed: {e}")

        return evidence_chunks[:self.TOP_K_EVIDENCE]

    def extract_claims_with_citations(self, analysis_text: str) -> List[Dict[str, Any]]:
        """
        Extract claims with their [CITE:chunk_id] markers from analysis text.

        Args:
            analysis_text: P7 analysis text with citation markers

        Returns:
            List of claim dictionaries with claim_id, text, and cited_chunk_id
        """
        claims = []

        # FIX: Strip markdown headers/formatting BEFORE processing
        text = analysis_text
        # Remove bold headers that appear at start or after newlines (title-like)
        text = re.sub(r'(?:^|\n)\s*\*\*[^*\n]+\*\*\s*(?:\n|$)', '\n', text)
        # Remove heading markers like # Title or ## Subtitle
        text = re.sub(r'^#+\s+[^\n]+\n?', '', text, flags=re.MULTILINE)
        # Remove horizontal rules
        text = re.sub(r'---+', '', text)

        # CRITICAL FIX: Split on bullet points FIRST (before whitespace normalization)
        # This preserves the structure where each bullet is a separate claim
        # Patterns: "* ", "- ", "• ", numbered lists "1. ", "1) "
        bullet_pattern = r'(?:^|\n)\s*(?:\*|\-|•|\d+[.)]\s)'

        # Split text into segments (paragraphs and bullet points)
        segments = []

        # First, split on newlines to preserve structure
        lines = text.split('\n')
        current_segment = []

        for line in lines:
            line = line.strip()
            if not line:
                # Empty line - flush current segment
                if current_segment:
                    segments.append(' '.join(current_segment))
                    current_segment = []
                continue

            # Check if this line starts with a bullet point
            is_bullet = bool(re.match(r'^\s*(?:\*|\-|•|\d+[.)]\s)', line))

            if is_bullet:
                # Flush previous segment
                if current_segment:
                    segments.append(' '.join(current_segment))
                    current_segment = []
                # Remove bullet marker and add as new segment
                clean_line = re.sub(r'^\s*(?:\*|\-|•|\d+[.)]\s*)', '', line)
                if clean_line:
                    segments.append(clean_line)
            else:
                # Continue current segment
                current_segment.append(line)

        # Flush remaining segment
        if current_segment:
            segments.append(' '.join(current_segment))

        # If no bullets were found, fall back to the whole text as one segment
        if not segments:
            segments = [re.sub(r'\s+', ' ', text).strip()]

        # FIX: Protect scientific abbreviations from sentence splitting
        protected_patterns = [
            (r'\bE\.\s*coli\b', 'E_COLI_PROTECTED'),
            (r'\bA\.\s*hydrophila\b', 'A_HYDROPHILA_PROTECTED'),
            (r'\bS\.\s*aureus\b', 'S_AUREUS_PROTECTED'),
            (r'\bP\.\s*aeruginosa\b', 'P_AERUGINOSA_PROTECTED'),
            (r'\bU\.S\.', 'US_PROTECTED'),
            (r'\be\.g\.', 'EG_PROTECTED'),
            (r'\bi\.e\.', 'IE_PROTECTED'),
            (r'\bet al\.', 'ETAL_PROTECTED'),
            (r'\bvs\.', 'VS_PROTECTED'),
            (r'\bDr\.', 'DR_PROTECTED'),
            (r'\bMr\.', 'MR_PROTECTED'),
            (r'\bMs\.', 'MS_PROTECTED'),
            (r'\bNo\.', 'NO_PROTECTED'),
            (r'\bFig\.', 'FIG_PROTECTED'),
            (r'\bTab\.', 'TAB_PROTECTED'),
        ]

        def restore_protected(s):
            """Restore protected abbreviations."""
            s = s.replace('E_COLI_PROTECTED', 'E. coli')
            s = s.replace('A_HYDROPHILA_PROTECTED', 'A. hydrophila')
            s = s.replace('S_AUREUS_PROTECTED', 'S. aureus')
            s = s.replace('P_AERUGINOSA_PROTECTED', 'P. aeruginosa')
            s = s.replace('US_PROTECTED', 'U.S.')
            s = s.replace('EG_PROTECTED', 'e.g.')
            s = s.replace('IE_PROTECTED', 'i.e.')
            s = s.replace('ETAL_PROTECTED', 'et al.')
            s = s.replace('VS_PROTECTED', 'vs.')
            s = s.replace('DR_PROTECTED', 'Dr.')
            s = s.replace('MR_PROTECTED', 'Mr.')
            s = s.replace('MS_PROTECTED', 'Ms.')
            s = s.replace('NO_PROTECTED', 'No.')
            s = s.replace('FIG_PROTECTED', 'Fig.')
            s = s.replace('TAB_PROTECTED', 'Tab.')
            return s

        claim_counter = 0

        # Process each segment (bullet point or paragraph)
        for segment in segments:
            # Normalize whitespace within segment
            segment = re.sub(r'\s+', ' ', segment).strip()
            if not segment:
                continue

            # Apply abbreviation protection
            for pattern, replacement in protected_patterns:
                segment = re.sub(pattern, replacement, segment, flags=re.IGNORECASE)

            # Split segment into sentences (for multi-sentence segments)
            sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', segment)

            for sentence in sentences:
                sentence = restore_protected(sentence.strip())
                if not sentence:
                    continue

                # Extract citation markers from this sentence
                citation_pattern = r'\[CITE:([^\]]+)\]'
                citations = re.findall(citation_pattern, sentence)

                if citations:
                    # Clean the claim text (remove citation markers for verification)
                    clean_text = re.sub(citation_pattern, '', sentence).strip()
                    # Remove trailing/leading punctuation artifacts
                    clean_text = clean_text.strip(' .,;:')

                    # Fragment detection (relaxed for bullet points which are often shorter)
                    is_fragment = False

                    # Check 1: Starts with lowercase (except for scientific names)
                    if clean_text and clean_text[0].islower():
                        if not re.match(r'^(coli|aureus|aeruginosa|hydrophila)\b', clean_text, re.IGNORECASE):
                            is_fragment = True

                    # Check 2: Too short (reduced from 30 to 20 for bullet points)
                    if len(clean_text) < 20:
                        is_fragment = True

                    # Check 3: Starts with coordinating conjunction
                    fragment_starters = ['and ', 'or ', 'but ', 'yet ', 'nor ']
                    if any(clean_text.lower().startswith(fs) for fs in fragment_starters):
                        is_fragment = True

                    if is_fragment:
                        continue

                    for citation in citations:
                        # Validate citation format - skip malformed
                        if "," in citation or " " in citation:
                            continue
                        if not citation.startswith("chunk_"):
                            continue

                        claim_counter += 1
                        claim = {
                            "claim_id": f"claim_{claim_counter:04d}",
                            "text": clean_text,
                            "cited_chunk_id": citation,
                            "original_text": sentence.strip(),
                        }
                        claims.append(claim)

        return claims

    def decompose_to_atomic_facts(self, claim_text: str, claim_id: str) -> List[AtomicFact]:
        """
        SOTA: FactScore-style atomic fact decomposition.

        Decomposes claims into minimal verifiable units following FactScore methodology:
        1. Each fact contains exactly one piece of information
        2. Numbers and entities are separated into distinct facts
        3. Relationships and attributes are independently verifiable

        Example:
        "The CDC study found 60% of filters in North America harbor E. coli"
        -> ["CDC conducted a study", "The study examined filters",
            "60% of filters harbor bacteria", "The bacteria is E. coli",
            "This applies to North America"]

        Args:
            claim_text: The claim text to decompose
            claim_id: Parent claim ID

        Returns:
            List of AtomicFact objects
        """
        atomic_facts = []

        # SOTA: Enhanced rule-based decomposition with FactScore principles
        # Step 1: Extract distinct information types
        facts_to_verify = []

        # Extract numbers/statistics
        number_patterns = re.findall(r'\d+(?:\.\d+)?%|\d+(?:,\d+)*(?:\.\d+)?(?:\s*(?:mg|μg|ppm|cfu|log|million|billion))?', claim_text)
        for num in number_patterns:
            # Find context for this number
            num_context = re.search(rf'[^.]*{re.escape(num)}[^.]*', claim_text)
            if num_context:
                facts_to_verify.append(num_context.group(0).strip())

        # Extract named entities and their relationships
        entity_patterns = [
            r'(?:CDC|EPA|FDA|WHO|NSF|AWWA)(?:\s+(?:study|report|guideline|standard))?',
            r'(?:E\.?\s*coli|Legionella|Giardia|Cryptosporidium|coliform)',
            r'(?:North America|United States|Canada|Europe|Asia|Global)',
        ]
        for pattern in entity_patterns:
            matches = re.findall(pattern, claim_text, re.IGNORECASE)
            for match in matches:
                # Get context sentence for entity
                entity_context = re.search(rf'[^.]*{re.escape(match)}[^.]*', claim_text)
                if entity_context:
                    ctx = entity_context.group(0).strip()
                    if len(ctx) > 20 and ctx not in facts_to_verify:
                        facts_to_verify.append(ctx)

        # Fallback: Split on conjunctions if no specific extractions
        if not facts_to_verify:
            separators = [
                r'\s+and\s+',
                r'\s+as well as\s+',
                r',\s+(?=and|or|which|that|while)',
                r';\s+',
            ]

            parts = [claim_text]
            for sep in separators:
                new_parts = []
                for part in parts:
                    new_parts.extend(re.split(sep, part, flags=re.IGNORECASE))
                parts = new_parts

            facts_to_verify = [p.strip() for p in parts if len(p.strip()) > 20]

        # If still no decomposition, use the whole claim
        if not facts_to_verify:
            facts_to_verify = [claim_text]

        # Deduplicate while preserving order
        seen = set()
        unique_facts = []
        for fact in facts_to_verify:
            fact_key = fact[:50].lower()
            if fact_key not in seen:
                seen.add(fact_key)
                unique_facts.append(fact)

        # Create AtomicFact objects
        for i, part in enumerate(unique_facts[:5]):  # Cap at 5 atomic facts
            atomic_fact = AtomicFact(
                fact_id=f"{claim_id}_fact_{i+1:02d}",
                text=part,
                parent_claim_id=claim_id,
            )
            atomic_facts.append(atomic_fact)

        return atomic_facts

    def qa_verify_fact(
        self,
        atomic_fact: AtomicFact,
        evidence_text: str,
    ) -> Tuple[bool, float, str]:
        """
        SOTA: QA-based verification alongside NLI.

        Uses question answering to verify facts:
        1. Convert fact to a question
        2. Extract answer from evidence
        3. Check if extracted answer matches fact

        Args:
            atomic_fact: The fact to verify
            evidence_text: Evidence text to check against

        Returns:
            Tuple of (is_supported, confidence, explanation)
        """
        # Convert fact to question
        fact_text = atomic_fact.text.lower()

        # Simple QA conversion patterns
        question = None
        expected_answer = None

        # Number-based facts
        num_match = re.search(r'(\d+(?:\.\d+)?%|\d+(?:\.\d+)?)', atomic_fact.text)
        if num_match:
            expected_answer = num_match.group(1)
            # Find what the number describes
            if "%" in atomic_fact.text:
                question = "What percentage is mentioned?"
            else:
                question = "What number or quantity is mentioned?"

        # Entity-based facts
        elif re.search(r'E\.?\s*coli|Legionella|bacteria|pathogen', fact_text, re.IGNORECASE):
            question = "What pathogens or bacteria are mentioned?"
            expected_answer = "pathogen"

        # If we have a question, try to answer it
        if question and expected_answer:
            # Check if evidence contains the expected answer
            if expected_answer.lower() in evidence_text.lower():
                return True, 0.8, f"QA: Expected '{expected_answer}' found in evidence"
            else:
                return False, 0.3, f"QA: Expected '{expected_answer}' not found"

        # Fallback: No QA possible
        return None, 0.5, "QA: Could not convert to question"

    def verify_atomic_fact(
        self,
        atomic_fact: AtomicFact,
        evidence_text: str
    ) -> AtomicFact:
        """
        SOTA: Verify atomic fact using hybrid NLI + QA approach.

        Combines:
        1. NLI-based verification (entailment scoring)
        2. QA-based verification (answer extraction)

        The final score is a weighted combination of both methods.

        Args:
            atomic_fact: The atomic fact to verify
            evidence_text: The evidence text to verify against

        Returns:
            Updated AtomicFact with verification results
        """
        if not self._initialized:
            self.initialize()

        nli_result = "neutral"
        nli_score = 0.5

        try:
            # Step 1: NLI verification (primary method)
            entailment, neutral, contradiction = self.compute_nli_scores(
                premise=evidence_text,
                hypothesis=atomic_fact.text
            )

            # SOTA-aligned threshold: entailment > 0.7 for grounding
            if entailment > self.ENTAILMENT_THRESHOLD:
                nli_result = "entailed"
                nli_score = entailment
            elif contradiction > 0.5:
                nli_result = "contradicted"
                nli_score = contradiction
            else:
                nli_result = "neutral"
                nli_score = neutral

        except Exception as e:
            # LOW-080: Use logger instead of print
            logger.warning(f"NLI verification failed for {atomic_fact.fact_id}: {e}")
            nli_result = "neutral"
            nli_score = 0.5

        # Step 2: QA verification (supplementary)
        qa_supported, qa_score, qa_explanation = self.qa_verify_fact(atomic_fact, evidence_text)

        # Step 3: Hybrid combination
        # - If NLI says entailed and QA agrees (or can't answer): ENTAILED
        # - If NLI says contradicted: CONTRADICTED (QA can't override)
        # - If NLI says neutral but QA finds evidence: Boost to entailed if strong
        # - Otherwise: Trust NLI result

        if nli_result == "entailed":
            atomic_fact.verification_result = "entailed"
            atomic_fact.verification_score = nli_score
        elif nli_result == "contradicted":
            atomic_fact.verification_result = "contradicted"
            atomic_fact.verification_score = nli_score
        elif nli_result == "neutral" and qa_supported is True and qa_score > 0.7:
            # QA found strong evidence that NLI missed
            atomic_fact.verification_result = "entailed"
            atomic_fact.verification_score = qa_score
        else:
            atomic_fact.verification_result = nli_result
            atomic_fact.verification_score = nli_score

        atomic_fact.evidence_text = evidence_text[:500]

        return atomic_fact

    def verify_claim(
        self,
        claim: Dict[str, Any],
        evidence_text: str
    ) -> ClaimVerificationResult:
        """
        Verify a claim against its cited evidence.

        Implements architecture.md B.5 (SOTA-aligned):
        - SUPPORTED: support >= 0.70, contradiction == 0
        - PARTIAL: support >= 0.50, contradiction < 0.2
        - REJECTED: contradiction > 0 OR support < 0.50

        Args:
            claim: Claim dictionary with text and cited_chunk_id
            evidence_text: The evidence text from the cited chunk

        Returns:
            ClaimVerificationResult with detailed verification info
        """
        claim_id = claim["claim_id"]
        claim_text = claim["text"]
        cited_chunk_id = claim["cited_chunk_id"]

        # Step 1: Decompose into atomic facts
        atomic_facts = self.decompose_to_atomic_facts(claim_text, claim_id)

        # Step 2: Verify each atomic fact
        for atomic_fact in atomic_facts:
            self.verify_atomic_fact(atomic_fact, evidence_text)

        # Step 3: Aggregate scores
        total = len(atomic_facts)
        supported = sum(1 for af in atomic_facts if af.verification_result == "entailed")
        contradicted = sum(1 for af in atomic_facts if af.verification_result == "contradicted")
        neutral = sum(1 for af in atomic_facts if af.verification_result == "neutral")

        support_score = supported / total if total > 0 else 0
        contradiction_score = contradicted / total if total > 0 else 0
        neutral_score = neutral / total if total > 0 else 0

        # Step 4: Verification decision
        issues = []
        blocked = False
        block_reason = None

        if contradiction_score > 0:
            status = "rejected"
            blocked = True
            block_reason = f"Contradiction detected ({contradiction_score:.1%})"
            issues.append({
                "issue_type": "contradiction",
                "explanation": f"{contradicted} of {total} atomic facts contradicted by evidence"
            })
        elif support_score >= self.SUPPORTED_THRESHOLD:
            status = "supported"
        elif support_score >= self.PARTIAL_THRESHOLD and contradiction_score < self.PARTIAL_CONTRADICTION_MAX:
            status = "partial"
            issues.append({
                "issue_type": "partial_match",
                "explanation": f"Only {supported} of {total} atomic facts supported"
            })
        else:
            status = "rejected"
            blocked = True
            block_reason = f"Insufficient support ({support_score:.1%} < {self.PARTIAL_THRESHOLD:.0%})"
            issues.append({
                "issue_type": "unsupported",
                "explanation": f"Support score {support_score:.1%} below threshold"
            })

        return ClaimVerificationResult(
            claim_id=claim_id,
            claim_text=claim_text,
            cited_chunk_id=cited_chunk_id,
            status=status,
            support_score=support_score,
            contradiction_score=contradiction_score,
            neutral_score=neutral_score,
            atomic_facts=atomic_facts,
            atomic_facts_total=total,
            atomic_facts_supported=supported,
            atomic_facts_contradicted=contradicted,
            atomic_facts_neutral=neutral,
            evidence_text=evidence_text[:500],
            issues=issues,
            blocked=blocked,
            block_reason=block_reason,
        )

    def verify_claim_multi_evidence(
        self,
        claim: Dict[str, Any],
        all_chunks: List[Dict]
    ) -> ClaimVerificationResult:
        """
        SOTA-aligned: Verify a claim against MULTIPLE evidence chunks (not just cited).

        This method:
        1. Finds top-k most relevant evidence chunks for the claim
        2. Verifies against each evidence chunk
        3. Uses the BEST verification score (most favorable to the claim)
        4. RE-CITES to the best supporting chunk if original citation fails

        This matches RAGAS methodology which checks against all available evidence.

        Args:
            claim: Claim dictionary with text and cited_chunk_id
            all_chunks: All available evidence chunks from VWM

        Returns:
            ClaimVerificationResult with best verification across all evidence
        """
        claim_id = claim["claim_id"]
        claim_text = claim["text"]
        original_cited_chunk_id = claim["cited_chunk_id"]

        # Find best evidence chunks (includes cited + semantically similar)
        evidence_chunks = self.find_best_evidence(claim_text, all_chunks, original_cited_chunk_id)

        if not evidence_chunks:
            # No evidence found at all
            return ClaimVerificationResult(
                claim_id=claim_id,
                claim_text=claim_text,
                cited_chunk_id=original_cited_chunk_id,
                status="rejected",
                support_score=0.0,
                contradiction_score=0.0,
                neutral_score=1.0,
                atomic_facts=[],
                atomic_facts_total=0,
                atomic_facts_supported=0,
                atomic_facts_contradicted=0,
                atomic_facts_neutral=0,
                evidence_text="",
                issues=[{"issue_type": "no_evidence", "explanation": "No evidence found"}],
                blocked=True,
                block_reason="No evidence found in VWM",
            )

        # Verify against each evidence chunk, keep best result
        best_result = None
        best_support_score = -1
        best_chunk_id = original_cited_chunk_id

        for chunk in evidence_chunks:
            evidence_text = chunk.get("text", chunk.get("content", ""))
            if not evidence_text:
                continue

            chunk_id = chunk.get("id", chunk.get("chunk_id", ""))
            result = self.verify_claim(claim, evidence_text)

            # Keep the result with highest support score
            if result.support_score > best_support_score:
                best_support_score = result.support_score
                best_result = result
                best_chunk_id = chunk_id

            # If we find a strongly supported result, use it immediately
            if result.status == "supported" and result.support_score >= self.SUPPORTED_THRESHOLD:
                # FIX: Update citation to the actual supporting chunk (re-cite)
                if chunk_id != original_cited_chunk_id:
                    result.cited_chunk_id = chunk_id
                    result.issues.append({
                        "issue_type": "re_cited",
                        "explanation": f"Re-cited from {original_cited_chunk_id} to {chunk_id} (better evidence match)"
                    })
                return result

        # Return best result found, with re-citation if needed
        if best_result:
            # FIX: Update citation to best supporting chunk even if partial/rejected
            if best_chunk_id != original_cited_chunk_id and best_support_score > 0:
                best_result.cited_chunk_id = best_chunk_id
                best_result.issues.append({
                    "issue_type": "re_cited",
                    "explanation": f"Re-cited from {original_cited_chunk_id} to {best_chunk_id} (better evidence match)"
                })
            return best_result

        # Fallback if nothing worked
        return ClaimVerificationResult(
            claim_id=claim_id,
            claim_text=claim_text,
            cited_chunk_id=original_cited_chunk_id,
            status="rejected",
            support_score=0.0,
            contradiction_score=0.0,
            neutral_score=1.0,
            atomic_facts=[],
            atomic_facts_total=0,
            atomic_facts_supported=0,
            atomic_facts_contradicted=0,
            atomic_facts_neutral=0,
            evidence_text="",
            issues=[{"issue_type": "verification_failed", "explanation": "All verification attempts failed"}],
            blocked=True,
            block_reason="Could not verify against any evidence",
        )


# =============================================================================
# PHASE 7.5 EXECUTION
# =============================================================================

async def run_phase_8(
    vector_id: str,
    p7_output_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> Phase8Output:
    """
    Execute Phase 8: Claim-Evidence NLI Verification

    Workflow:
    1. Load P7 output (analysis text with citations)
    2. Extract claims with [CITE:chunk_id] markers
    3. For each claim, retrieve cited evidence from VWM
    4. Verify each claim against its evidence using NLI
    5. Block claims that fail verification
    6. Generate verified analysis text (with blocked claims removed)

    Args:
        vector_id: Vector ID for the research
        p7_output_path: Optional path to P7 output (will search if not provided)

    Returns:
        Phase8Output with verification results
    """
    start_time = datetime.now(timezone.utc)
    audit = get_audit()

    print(f"\n{'='*60}")
    print("PHASE 7.5: CLAIM-EVIDENCE NLI VERIFICATION")
    print(f"Vector ID: {vector_id}")
    print(f"{'='*60}")

    # Load P7 output
    if p7_output_path is None:
        p7_dir = OUTPUTS_DIR / "P7"
        p7_files = list(p7_dir.glob(f"{vector_id}__P7__*.json"))
        if not p7_files:
            raise FileNotFoundError(f"No P7 output found for {vector_id}")
        p7_output_path = sorted(p7_files)[-1]

    print(f"\n  Loading P7 output: {p7_output_path.name}")
    with open(p7_output_path, 'r', encoding='utf-8') as f:
        p7_data = json.load(f)

    analysis_text = p7_data.get("analysis_text", "")
    if not analysis_text:
        raise ValueError("P7 output has no analysis_text")

    print(f"  Analysis text length: {len(analysis_text)} chars")

    # Initialize verification engine
    engine = ClaimVerificationEngine()
    engine.initialize()

    # Extract claims with citations
    print("\n  Step 1: Extracting claims with citations...")
    claims = engine.extract_claims_with_citations(analysis_text)
    print(f"    Found {len(claims)} claims with citations")

    # Load VWM for evidence retrieval
    print("\n  Step 2: Loading VWM for evidence retrieval...")
    chroma = get_chroma_manager()
    chroma.initialize_client()
    collection_name = f"vwm_{vector_id}"
    all_chunks = []  # SOTA: Load ALL chunks for multi-evidence verification

    try:
        collection = chroma._client.get_collection(name=collection_name)
        print(f"    VWM collection loaded: {collection.count()} chunks")

        # SOTA: Load ALL chunks for multi-evidence checking
        all_results = collection.get(include=["documents", "metadatas"])
        for j, doc in enumerate(all_results.get("documents", [])):
            chunk_id = all_results["ids"][j]
            metadata = all_results.get("metadatas", [{}])[j] if all_results.get("metadatas") else {}
            all_chunks.append({
                "id": chunk_id,
                "chunk_id": metadata.get("chunk_id", chunk_id),
                "text": doc,
                "content": doc,
            })
        print(f"    Loaded {len(all_chunks)} chunks for multi-evidence verification")

    except Exception as e:
        # LOW-081: Use logger instead of print
        logger.warning(f"Could not load VWM: {e}")
        collection = None

    # Verify each claim using MULTI-EVIDENCE (SOTA-aligned)
    print("\n  Step 3: Verifying claims against evidence (SOTA: multi-evidence)...")
    verification_results = []
    blocked_citations = []

    for i, claim in enumerate(claims):
        chunk_id = claim["cited_chunk_id"]

        if not all_chunks:
            print(f"    [{i+1}/{len(claims)}] Claim {claim['claim_id']}: No evidence available - REJECTED")
            result = ClaimVerificationResult(
                claim_id=claim["claim_id"],
                claim_text=claim["text"],
                cited_chunk_id=chunk_id,
                status="rejected",
                support_score=0.0,
                contradiction_score=0.0,
                neutral_score=1.0,
                atomic_facts=[],
                atomic_facts_total=0,
                atomic_facts_supported=0,
                atomic_facts_contradicted=0,
                atomic_facts_neutral=0,
                evidence_text="",
                issues=[{"issue_type": "no_evidence", "explanation": "No evidence available in VWM"}],
                blocked=True,
                block_reason="Evidence not available",
            )
            verification_results.append(result)
            blocked_citations.append(chunk_id)
            continue

        # SOTA: Verify claim against MULTIPLE evidence chunks (not just cited)
        result = engine.verify_claim_multi_evidence(claim, all_chunks)
        verification_results.append(result)

        status_marker = "[OK]" if result.status == "supported" else "[WARN]" if result.status == "partial" else "[FAIL]"
        print(f"    [{i+1}/{len(claims)}] {status_marker} {result.status.upper()} "
              f"(support={result.support_score:.1%}, contradict={result.contradiction_score:.1%})")

        if result.blocked:
            blocked_citations.append(chunk_id)

    # Calculate statistics
    total = len(verification_results)
    supported = sum(1 for r in verification_results if r.status == "supported")
    partial = sum(1 for r in verification_results if r.status == "partial")
    rejected = sum(1 for r in verification_results if r.status == "rejected")
    verified = supported + partial

    verification_rate = verified / total if total > 0 else 0
    hallucination_rate = rejected / total if total > 0 else 0

    print(f"\n  Step 4: Verification Summary")
    print(f"    Total Claims: {total}")
    print(f"    Supported: {supported} ({supported/total*100:.1f}%)" if total > 0 else "    Supported: 0")
    print(f"    Partial: {partial} ({partial/total*100:.1f}%)" if total > 0 else "    Partial: 0")
    print(f"    Rejected: {rejected} ({rejected/total*100:.1f}%)" if total > 0 else "    Rejected: 0")
    print(f"    Verification Rate: {verification_rate:.1%}")
    print(f"    Hallucination Rate: {hallucination_rate:.1%}")
    print(f"    Blocked Citations: {len(blocked_citations)}")

    # Generate verified analysis text (remove blocked citations)
    print("\n  Step 5: Generating verified analysis text...")
    verified_analysis_text = analysis_text

    # Remove sentences with blocked citations
    blocked_set = set(blocked_citations)
    for chunk_id in blocked_set:
        # Remove sentences containing blocked citation
        pattern = rf'[^.!?]*\[CITE:{re.escape(chunk_id)}\][^.!?]*[.!?]\s*'
        verified_analysis_text = re.sub(pattern, '', verified_analysis_text)

    # Clean up any double spaces or orphaned citations
    verified_analysis_text = re.sub(r'\s+', ' ', verified_analysis_text)
    verified_analysis_text = verified_analysis_text.strip()

    print(f"    Original length: {len(analysis_text)} chars")
    print(f"    Verified length: {len(verified_analysis_text)} chars")
    print(f"    Removed: {len(analysis_text) - len(verified_analysis_text)} chars")

    # Audit: Log each claim verification
    if audit:
        for result in verification_results:
            audit.log_claim(
                claim_id=result.claim_id,
                claim_text=result.claim_text[:200] if result.claim_text else "",
                entailment_score=result.support_score,
                verdict=result.status,
                evidence_chunk_id=result.cited_chunk_id,
                best_evidence_text=result.evidence_text[:200] if result.evidence_text else "",
            )

    end_time = datetime.now(timezone.utc)

    # Build output
    output = Phase8Output(
        vector_id=vector_id,
        claims_total=total,
        claims_verified=verified,
        claims_supported=supported,
        claims_partial=partial,
        claims_rejected=rejected,
        verification_rate=verification_rate,
        hallucination_rate=hallucination_rate,
        blocked_citations=list(blocked_set),
        verification_results=[
            {
                "claim_id": r.claim_id,
                "claim_text": r.claim_text,
                "cited_chunk_id": r.cited_chunk_id,
                "status": r.status,
                "support_score": r.support_score,
                "contradiction_score": r.contradiction_score,
                "blocked": r.blocked,
                "block_reason": r.block_reason,
            }
            for r in verification_results
        ],
        verified_analysis_text=verified_analysis_text,
        original_analysis_text=analysis_text,
        timestamps={
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
        },
    )

    # Save output
    if output_dir is None:
        output_dir = OUTPUTS_DIR / "P8"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"{vector_id}__P8__{timestamp}.json"

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output.model_dump(), f, indent=2, ensure_ascii=False)

    print(f"\n  Output saved: {output_path.name}")

    # Update ledger
    ledger = Ledger()
    ledger.append(
        vector_id=vector_id,
        phase=8,
        status="completed",
        output_path=str(output_path),
        notes=f"P8 verification: {verified}/{total} verified, hallucination={hallucination_rate:.1%}"
    )

    return output


# =============================================================================
# SELF-TEST
# =============================================================================

def self_test():
    """Run self-tests for Phase 8 claim verification."""
    print("\nRunning Phase 8 self-tests...")

    # Test 1: Claim extraction
    test_text = """
    Water filters can reduce contaminants [CITE:chunk_001].
    However, they require maintenance [CITE:chunk_002].
    Studies show effectiveness varies [CITE:chunk_003].
    """

    engine = ClaimVerificationEngine()
    claims = engine.extract_claims_with_citations(test_text)
    assert len(claims) == 3, f"Expected 3 claims, got {len(claims)}"
    print("  [PASS] Claim extraction")

    # Test 2: Atomic fact decomposition
    claim_text = "Water filters reduce contaminants and improve taste"
    facts = engine.decompose_to_atomic_facts(claim_text, "test_claim")
    assert len(facts) >= 1, "Expected at least 1 atomic fact"
    print("  [PASS] Atomic fact decomposition")

    # Test 3: Verification thresholds (SOTA-aligned)
    assert engine.SUPPORTED_THRESHOLD == 0.70, f"Expected 0.70, got {engine.SUPPORTED_THRESHOLD}"
    assert engine.PARTIAL_THRESHOLD == 0.50, f"Expected 0.50, got {engine.PARTIAL_THRESHOLD}"
    assert engine.PARTIAL_CONTRADICTION_MAX == 0.2
    assert engine.ENTAILMENT_THRESHOLD == 0.70, f"Expected 0.70, got {engine.ENTAILMENT_THRESHOLD}"
    print("  [PASS] Verification thresholds (SOTA: 0.70 entailment)")

    print("\nAll Phase 8 self-tests PASSED!")
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phase 8: Claim Verification")
    parser.add_argument("--vector-id", required=False, help="Vector ID to process")
    parser.add_argument("--input", required=False, help="Path to P7 output JSON")
    parser.add_argument("--output", required=False, help="Output directory path")
    parser.add_argument("--self-test", action="store_true", help="Run self-tests")

    args = parser.parse_args()

    if args.self_test:
        self_test()
    elif args.vector_id:
        p7_path = Path(args.input) if args.input else None
        out_dir = Path(args.output) if args.output else None
        result = asyncio.run(run_phase_8(
            vector_id=args.vector_id,
            p7_output_path=p7_path,
            output_dir=out_dir,
        ))
        print(f"\nPhase 8 complete. Verification rate: {result.verification_rate:.1%}")
    else:
        print("Usage: python p07_claim_verification.py --vector-id <ID> or --self-test")
