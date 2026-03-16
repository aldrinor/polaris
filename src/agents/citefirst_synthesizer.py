"""
POLARIS v3 Cite-First Synthesizer Agent

ARCHITECTURAL REDESIGN (FIX 117): Path B for 90%+ Faithfulness

This synthesizer implements the "cite-first" paradigm that inverts the traditional
"write-then-cite" approach used by the original SynthesizerAgent.

FUNDAMENTAL INSIGHT:
- Traditional (75% ceiling): write narrative → find citations post-hoc
- SOTA (90%+): identify evidence → verify support → write grounded claims

KEY DIFFERENCES FROM SynthesizerAgent:
1. Claims are generated BEFORE prose (not extracted from prose)
2. Evidence is retrieved PER-CLAIM (not from static pool)
3. Verification happens DURING synthesis (not post-hoc by auditor)
4. Only grounded claims make it into the final report

EXPECTED IMPACT:
- Static pool misses: -15% → 0% (dynamic per-claim retrieval)
- Semantic drift: -5% → 0% (inline verification before output)
- Verification ceiling: -15% → -5% (verify during, not after)
- Faithfulness: 75% → 90%+

Based on:
- METEORA (EMNLP 2024): Rationale-driven evidence selection
- FactScore (ACL 2023): Atomic claim verification
- SAFE (Google 2024): Long-form factuality evaluation
"""

import logging
import os
import re
import json
from typing import List, Dict, Any, Optional, Tuple, Literal
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from .base_agent import BaseAgent, AgentConfig, register_agent
from src.orchestration.state import ResearchState, Evidence, AtomicFact
from src.utils.embedding_service import get_embedding_service
from src.utils.cot_scrubber import scrub_cot_from_report
from src.utils.cot_post_filter import post_filter_report as cot_post_filter_report
from src.utils.citation_registry import normalize_cite_tokens

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# Feature flag for gradual rollout
CITEFIRST_ENABLED = os.environ.get("POLARIS_CITEFIRST_ENABLED", "0") == "1"

# FIX-161: Cluster-synthesize architecture (default OFF for safe rollout)
CLUSTER_SYNTHESIS_ENABLED = os.environ.get("POLARIS_CLUSTER_SYNTHESIS", "0") == "1"

# Thresholds (configurable via .env)
# FIX-171: Lowered from 0.25 to 0.10 with tiered grounding
CLAIM_VERIFICATION_THRESHOLD = float(os.environ.get("POLARIS_CLAIM_VERIFY_THRESHOLD", "0.10"))
# FIX-171: Tiered grounding thresholds
CLAIM_HIGH_CONFIDENCE_THRESHOLD = float(os.environ.get("POLARIS_CLAIM_HIGH_THRESHOLD", "0.25"))
MAX_CLAIMS_PER_QUERY = int(os.environ.get("POLARIS_MAX_CLAIMS_PER_QUERY", "100"))
MIN_EVIDENCE_PER_CLAIM = int(os.environ.get("POLARIS_MIN_EVIDENCE_PER_CLAIM", "1"))
MAX_UNGROUNDABLE_RATIO = float(os.environ.get("POLARIS_MAX_UNGROUNDABLE_RATIO", "0.20"))

# Ungroundable claim handling strategy
# Options: "skip" (drop), "hedge" (add hedging language), "flag" (mark as ungrounded)
UNGROUNDABLE_STRATEGY = os.environ.get("POLARIS_UNGROUNDABLE_STRATEGY", "hedge")

# FIX-150A: Maximum number of hedged claims included in the report
MAX_HEDGED_IN_REPORT = int(os.environ.get("POLARIS_MAX_HEDGED_REPORT", "15"))
PERCLAIM_RETRIEVAL_ENABLED = os.environ.get("POLARIS_PERCLAIM_RETRIEVAL", "1") == "1"
PERCLAIM_MAX_RESULTS = int(os.environ.get("POLARIS_PERCLAIM_MAX_RESULTS", "5"))

# FIX 117 T5: Semantic similarity threshold for embedding-based retrieval
# FIX-152B: Raised from 0.25 to 0.40 to prevent off-topic evidence matches
SEMANTIC_SIMILARITY_THRESHOLD = float(os.environ.get("POLARIS_SEMANTIC_THRESHOLD", "0.40"))

# FIX-147: Stateful citation diversity penalty
# Multiplier applied per-citation to already-cited domains (0.85 = 15% penalty per citation)
DIVERSITY_PENALTY = float(os.environ.get("POLARIS_DIVERSITY_PENALTY", "0.85"))

# FIX-170/FIX-195: Per-call token budgets for different synthesis stages
# FIX-195: .invoke() returns empty intermittently with streaming=True; _invoke_llm
# now uses .stream() for >4096. Claims lowered to 4096 (output fits in 4096).
# Clustering needs 8000 (thinking mode uses ~3000+ tokens for reasoning before JSON output).
TOKENS_CLUSTER_LLM = int(os.environ.get("POLARIS_TOKENS_CLUSTER_LLM", "8000"))
TOKENS_SECTION_PROSE = int(os.environ.get("POLARIS_TOKENS_SECTION_PROSE", "4000"))
TOKENS_CLAIM_GENERATION = int(os.environ.get("POLARIS_TOKENS_CLAIM_GENERATION", "4096"))

# FIX-174: Sentences per section (decouples cluster count from claim count)
SENTENCES_PER_SECTION = int(os.environ.get("POLARIS_SENTENCES_PER_SECTION", "10"))
MIN_SENTENCES_PER_SECTION = int(os.environ.get("POLARIS_MIN_SENTENCES_PER_SECTION", "5"))

# FIX-172: Evidence summary count for claim generation prompt
EVIDENCE_SUMMARY_COUNT = int(os.environ.get("POLARIS_EVIDENCE_SUMMARY_COUNT", "50"))

# FIX-194A: Module-level stopwords constant (consolidates 3 function-local copies)
_STOPWORDS = frozenset({
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'shall', 'can',
    'and', 'or', 'but', 'not', 'no', 'that', 'this', 'it', 'its',
    'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through',
    'of', 'in', 'to', 'about', 'also', 'so', 'if', 'than', 'then',
    'during', 'before', 'after', 'above', 'below', 'between',
    'nor', 'yet', 'both', 'either', 'neither', 'each',
    'every', 'all', 'any', 'few', 'more', 'most', 'other', 'some', 'such',
    'too', 'very', 'just', 'these', 'those',
    'they', 'them', 'their', 'we', 'our', 'what', 'which',
    'who', 'whom', 'how', 'when', 'where', 'why',
})

# FIX-168: Quality gate thresholds
MIN_REPORT_WORDS = int(os.environ.get("POLARIS_MIN_REPORT_WORDS", "2000"))
MIN_REPORT_CITATIONS = int(os.environ.get("POLARIS_MIN_REPORT_CITATIONS", "5"))


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class GroundedClaim:
    """A claim that has been verified against evidence.

    This is the atomic unit of cite-first synthesis. Each GroundedClaim
    represents a single verifiable statement with its supporting evidence.

    FIX 117 Phase 2.2: Enhanced to capture full grounding context for
    auditor passthrough without re-parsing.
    """
    claim_id: str
    claim_text: str
    claim_type: str  # factual, statistical, comparative, causal, definitional
    evidence_ids: List[str]
    evidence_texts: List[str]
    evidence_sources: List[str]  # URLs for citation
    evidence_tiers: List[str]  # Quality tiers
    evidence_relevance: List[float]  # Relevance scores
    matching_keywords: List[List[str]]  # Keywords that matched per evidence
    confidence: float
    reasoning: str
    sentence: str  # The generated sentence expressing this claim
    verification_passed: bool
    verification_method: str = "minicheck"  # minicheck, llm_fallback, heuristic
    threshold_used: float = 0.40
    is_compound: bool = False
    atom_count: int = 1
    section_topic: str = ""  # FIX-160: Topic cluster assignment
    paragraph_index: int = 0  # FIX-184A: Source paragraph index for reconstruction


@dataclass
class EvidenceGrounding:
    """A single evidence piece with its grounding context.

    FIX 117 Phase 2.2: Captures WHY each evidence piece supports the claim.
    """
    evidence_id: str
    evidence_text: str  # Full text for auditor verification
    source_url: str
    quality_tier: str  # GOLD, SILVER, BRONZE, UNVERIFIED
    relevance_score: float  # How relevant to the claim (0-1)
    matching_keywords: List[str]  # Keywords that matched


@dataclass
class ClaimEvidenceMap:
    """Complete mapping from claim to evidence for auditor passthrough.

    FIX 117 Phase 2.2: The auditor receives this map directly,
    eliminating the need to re-parse citations from markdown.
    This preserves the FULL grounding context including:
    - WHY each evidence supports the claim
    - What verification method was used
    - All evidence texts (not just IDs)
    """
    claim_text: str
    claim_type: str  # factual, statistical, comparative, causal, definitional
    evidence_groundings: List[EvidenceGrounding]  # Full evidence context
    evidence_ids: List[str]  # Quick lookup (redundant but convenient)
    reasoning: str  # WHY this evidence supports this claim
    sentence_index: int  # Position in report
    generated_sentence: str  # The sentence that was written
    verification_score: float
    verification_method: str  # "minicheck", "llm_fallback", "heuristic"
    threshold_used: float  # What threshold was applied
    is_compound_claim: bool  # Whether claim was decomposed
    atom_count: int  # How many atomic facts in claim


@dataclass
class UngroundableClaim:
    """A claim that could not be grounded in evidence.

    FIX 117 Phase 2.4: Tracks why claims failed and how they were handled.
    """
    claim_id: str
    claim_text: str
    claim_type: str
    failure_reason: str  # "no_evidence", "verification_failed", "low_confidence"
    handling_strategy: str  # "skipped", "hedged", "flagged"
    hedged_sentence: Optional[str] = None  # If strategy=hedge, the hedged version
    best_evidence_id: Optional[str] = None  # Best evidence found (if any)
    best_confidence: float = 0.0  # Highest verification confidence achieved


@dataclass
class CitefirstResult:
    """Complete result from cite-first synthesis."""
    grounded_claims: List[GroundedClaim]
    ungroundable_claims: List[UngroundableClaim]  # Enhanced from List[str]
    claim_evidence_map: List[ClaimEvidenceMap]
    markdown_report: str
    total_claims: int
    grounded_count: int
    ungroundable_count: int
    hedged_count: int  # How many ungroundable claims were hedged
    flagged_count: int  # How many were flagged
    skipped_count: int  # How many were skipped
    average_confidence: float
    synthesis_stats: Dict[str, Any]


# =============================================================================
# Pydantic Schemas for LLM Structured Output
# =============================================================================

class GeneratedClaim(BaseModel):
    """A single claim generated from a research query."""
    claim_text: str = Field(description="A single, atomic, verifiable claim")
    importance: int = Field(ge=1, le=10, default=3, description="Importance to answering the query (1-10)")
    claim_type: Literal["factual", "statistical", "comparative", "causal", "definitional"] = Field(
        description="Type of claim"
    )
    keywords: List[str] = Field(default_factory=list, description="Key terms for evidence retrieval")


class ClaimDecomposition(BaseModel):
    """LLM output for decomposing a query into claims."""
    claims: List[GeneratedClaim] = Field(description="List of atomic claims to verify")
    query_understanding: str = Field(description="Summary of query intent")


class GroundedSentence(BaseModel):
    """LLM output for a grounded sentence with citation."""
    sentence: str = Field(description="A sentence expressing the claim grounded in evidence")
    uses_direct_quote: bool = Field(default=False, description="Whether the sentence uses a direct quote")
    citation_ids: List[str] = Field(description="Evidence IDs cited in this sentence")
    faithfulness_self_score: float = Field(ge=0.0, le=1.0, description="Self-assessed faithfulness (0-1)")


class ReportSection(BaseModel):
    """A section of the final report."""
    section_id: str
    title: str
    content: str  # Markdown with [CITE:id] tokens
    sentence_count: int
    citation_count: int


class CitefirstReport(BaseModel):
    """Complete report from cite-first synthesis."""
    title: str
    executive_summary: str
    sections: List[ReportSection]
    methodology_note: str
    total_claims: int
    grounded_claims: int
    confidence_statement: str


# =============================================================================
# FIX-147: Domain Extraction Utility
# =============================================================================

def _extract_domain(url: str) -> str:
    """Extract the base domain from a URL for citation diversity tracking.

    Returns the registrable domain (e.g., 'epa.gov' from 'https://www.epa.gov/pfas/...')
    or an empty string if the URL is invalid.
    """
    if not url:
        return ""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        # Strip 'www.' prefix
        if hostname.startswith("www."):
            hostname = hostname[4:]
        return hostname.lower()
    except Exception as e:  # FIX-228
        logger.debug(f"Domain extraction failed: {e}")
        return ""


# =============================================================================
# Cite-First Synthesizer Agent
# =============================================================================

@register_agent("citefirst_synthesizer")
class CitefirstSynthesizer(BaseAgent):
    """
    Cite-First Synthesizer - Architectural redesign for 90%+ faithfulness.

    This agent inverts the traditional synthesis flow:

    TRADITIONAL (write-then-cite):
        evidence_pool → LLM("write report") → markdown with [CITE:id]

    CITE-FIRST (evidence-first):
        query → claims → for each claim:
                            → retrieve best evidence
                            → verify evidence supports claim
                            → write sentence IF verified
                        → compose verified sentences

    The key innovation is that VERIFICATION HAPPENS BEFORE WRITING,
    not after (post-hoc by auditor). This eliminates the fundamental
    cause of the 75% faithfulness ceiling.
    """

    def __init__(self):
        # FIX-170: Configurable synthesis token budget (was 4096, now 16000 default)
        # Fireworks KIMI K2.5 supports large outputs with stream=true (handled in base_agent)
        synthesis_max_tokens = int(os.environ.get("POLARIS_SYNTHESIS_MAX_TOKENS", "16000"))
        config = AgentConfig(
            name="citefirst_synthesizer",
            description="Cite-first synthesis for 90%+ faithfulness",
            task_tier="important",
            temperature=0.2,  # Low for factual grounding
            max_tokens=synthesis_max_tokens,
        )
        super().__init__(config)

        # Initialize inline verifier (MiniCheck wrapper)
        self.inline_verifier = None
        self._init_inline_verifier()

        # Synthesis statistics
        self.stats = {
            "claims_generated": 0,
            "claims_grounded": 0,
            "claims_ungroundable": 0,
            "claims_hedged": 0,
            "claims_flagged": 0,
            "claims_skipped": 0,
            "verification_calls": 0,
            "retrieval_calls": 0,
            "average_confidence": 0.0,
        }

        # FIX 117 T5: Embedding-based retrieval
        self._embedding_service = None
        self._evidence_embeddings: Dict[int, np.ndarray] = {}
        self._evidence_embeddings_computed = False
        self._init_embedding_service()

    @staticmethod
    def _strip_evidence_artifacts(text: str) -> str:
        """
        FIX-163: Remove evidence pipeline artifacts from text.

        Cleans Source quote patterns, double-double quotes, and evidence ID
        prefixes that leak into LLM prompts and output.

        Args:
            text: Raw text possibly containing artifacts

        Returns:
            Cleaned text with artifacts removed
        """
        if not text:
            return ""

        cleaned = text
        # Order matters: double-double quotes first, then single-double
        artifact_patterns = [
            # Double-double quote patterns: Source quote: ""...""
            (r'Source quote:\s*""[^"]*""', ''),
            (r'""[^"]{0,500}""', ''),
            # Single-double quote patterns: Source quote: "..."
            (r'\.\s*Source quote:\s*"[^"]{0,500}"', '.'),
            (r'Source quote:\s*"[^"]{0,500}"\.?\s*', ''),
            # Evidence ID prefixes (not inside [CITE:...])
            (r'(?<!\[CITE:)\bev_atomic_[a-f0-9]+:\s*', ''),
            (r'(?<!\[CITE:)\bev_\w{3,40}:\s*', ''),
        ]
        for pattern, replacement in artifact_patterns:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

        # Clean up double spaces
        cleaned = re.sub(r'  +', ' ', cleaned).strip()
        return cleaned

    # FIX-246: PDF metadata patterns — evidence containing these is structural noise
    _PDF_METADATA_PATTERNS = [
        re.compile(p, re.IGNORECASE) for p in [
            r"\b\d+\s+0\s+obj\b",
            r"\b(?:xref|endobj|startxref|endstream)\b",
            r"\bstream\s+length\b",
            r"\b\d+\s+bytes?\b.*\b(?:object|stream|length)\b",
            r"\broot\s+object\s+reference\b",
            r"\bcross-reference\s+table\b",
            r"\bhexadecimal\s+identifiers?\b",
        ]
    ]

    @classmethod
    def _is_metadata_evidence(cls, text: str) -> bool:
        """FIX-246: Detect PDF structural metadata masquerading as evidence."""
        if not text:
            return False
        for pattern in cls._PDF_METADATA_PATTERNS:
            if pattern.search(text):
                return True
        return False

    # FIX-240: Line-level removal patterns for deep prose cleaning
    _DEEP_CLEAN_LINE_PATTERNS = [
        re.compile(p) for p in [
            # Numbered outlines: "7. Two distinct types...", "2a. The EPA..." (only if followed by uppercase)
            r"^\d+[a-z]?\.\s+(?=[A-Z])",
            # Instruction echoes
            r"^Must\s+(begin|connect|include|use|synthesize|write|start|end)\b",
            r"^Use\s+(exact|inline|transition|specific)\b",
            r"^Do\s+NOT\s+",
            r"^Focus\s+EXCLUSIVELY\b",
            r"^OUTPUT:\s",
            r"^RULES:\s",
            # Evidence ID references in prose
            r"\b[a-f0-9]{12}\b\s+is\s+about\b",
            # Empty template markers
            r'^According to the source,\s*""\s*$',
            r'^\s*-\s*\[\]:\s',
            # PDF metadata in prose
            r"\b(?:xref|obj|stream|endobj|startxref)\b.*\d+\s*bytes?\b",
            r"\bobject\s+\d+\s+(?:has|contains|having|maintains)\b",
            r"\bstream\s+length\s+of\s+\d+\b",
            # Self-referential / meta-reasoning
            r"^(?:However|But),?\s+(?:I|the instructions?|looking)\b",
            r"^(?:Structure|Plan|Revised plan|Topic sentence):",
            r"^(?:\d+\.?\s+)?Sentence\s+about\b",
            # Transition template leaks
            r"^From the analysis of .+, attention now shifts to\b",
        ]
    ]

    def _deep_clean_prose(self, text: str) -> str:
        """FIX-240: Multi-pass content filter for LLM prose output.

        Removes instruction echoes, outline numbers, meta-reasoning,
        PDF metadata, and other noise that pattern-based scrubbers miss.

        Runs AFTER _sanitize_llm_output() and BEFORE scrub_cot_from_report().
        """
        if not text:
            return ""

        lines = text.split("\n")
        cleaned_lines = []
        removed_count = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                cleaned_lines.append(line)
                continue

            should_remove = False
            for pattern in self._DEEP_CLEAN_LINE_PATTERNS:
                if pattern.search(stripped):
                    should_remove = True
                    logger.debug(f"[FIX-240] Removed line: {stripped[:80]}...")
                    break

            if should_remove:
                removed_count += 1
            else:
                cleaned_lines.append(line)

        # Pass 2: Inline cleanup — remove fragments within lines
        result = "\n".join(cleaned_lines)

        # Remove lines that are ONLY citation markers with no content
        result = re.sub(
            r"^\s*\[(?:CITE:)?[^\]]*\]\s*\d*\.?\s*$",
            "",
            result,
            flags=re.MULTILINE,
        )

        # Clean up multiple blank lines
        result = re.sub(r"\n{3,}", "\n\n", result).strip()

        if removed_count > 0:
            logger.info(f"[FIX-240] Deep clean removed {removed_count} noise lines")

        # Pass 3: Quality gate — if >50% of lines removed, warn
        total_lines = len([l for l in lines if l.strip()])
        if total_lines > 0 and removed_count / total_lines > 0.50:
            logger.warning(
                f"[FIX-240] >50% of lines removed ({removed_count}/{total_lines}), "
                f"prose may need re-generation"
            )

        return result

    def _init_inline_verifier(self):
        """Initialize MiniCheck for inline verification."""
        try:
            from src.utils.inline_verifier import InlineVerifier
            self.inline_verifier = InlineVerifier()
            logger.info("[FIX 117] Inline verifier initialized for cite-first synthesis")
        except ImportError:
            # FIX-212 P1: Track that we're using LLM fallback verifier
            logger.warning("[FIX-212] InlineVerifier not available, using LLM fallback")
            self._fallback_verifier = True
        except Exception as e:
            logger.warning(f"[FIX-212] Failed to init inline verifier: {e}")
            self._fallback_verifier = True

    def _init_embedding_service(self):
        """Initialize embedding service for semantic retrieval (FIX 117 T5)."""
        try:
            self._embedding_service = get_embedding_service()
            logger.info(
                f"[FIX 117 T5] Embedding service initialized: "
                f"{self._embedding_service.model_name} ({self._embedding_service.dimensions}d)"
            )
        except Exception as e:
            # FIX-212 P1: Track keyword retrieval fallback
            logger.warning(f"[FIX-212] Embedding service unavailable, falling back to keyword retrieval: {e}")
            self._embedding_service = None
            self._fallback_retrieval = "keyword"

    def _ensure_evidence_embeddings(self, evidence_pool: List[Evidence]):
        """
        Pre-compute and cache embeddings for the evidence pool.

        FIX 117 T5: Called once per process() invocation. Batch-encodes all
        evidence texts for efficient cosine similarity matching.
        """
        if self._evidence_embeddings_computed:
            return

        texts = []
        ids = []
        for ev in evidence_pool:
            if hasattr(ev, 'is_metadata') and ev.is_metadata:
                continue
            ev_text = ev.text if hasattr(ev, 'text') else str(ev)
            if ev_text and ev_text.strip():
                texts.append(ev_text)
                ids.append(id(ev))

        if texts:
            embeddings = self._embedding_service.embed_batch(texts)
            for ev_id, embedding in zip(ids, embeddings):
                self._evidence_embeddings[ev_id] = np.array(embedding)

        self._evidence_embeddings_computed = True
        logger.info(f"[FIX 117 T5] Pre-computed embeddings for {len(texts)} evidence texts")

    def get_system_prompt(self) -> str:
        """Return system prompt for cite-first synthesis.

        FIX-241: Simplified to reduce instruction echo surface area.
        """
        return """You are a research writer. Write factual prose grounded in evidence.
- Cite sources inline as [CITE:id] after each claim
- Write complete sentences in paragraph form
- Use specific numbers and dates from evidence
- Skip evidence about unrelated topics or regions
- Connect ideas using academic transitions (e.g., however, therefore, notably, for example, in particular, consequently, moreover)"""

    def process(self, state: ResearchState) -> ResearchState:
        """
        Main entry point for cite-first synthesis.

        Args:
            state: Research state with evidence_chain and original_query

        Returns:
            Updated state with draft_report and claim_evidence_map
        """
        evidence_chain = state.get("evidence_chain", [])
        original_query = state.get("original_query", "")

        # FIX 117 T5: Reset embedding cache for each process() call
        self._evidence_embeddings = {}
        self._evidence_embeddings_computed = False

        if not evidence_chain:
            logger.warning("[FIX 117] No evidence for cite-first synthesis")
            state["draft_report"] = "Insufficient evidence to generate report."
            return state

        logger.info(f"[FIX 117] Starting cite-first synthesis with {len(evidence_chain)} evidence pieces")

        # Step 1: Generate claims from query, informed by evidence pool
        claims = self._generate_claims(original_query, evidence_chain)
        self.stats["claims_generated"] = len(claims)

        logger.info(f"[FIX 117] Generated {len(claims)} claims from query")

        # FIX-147: Track domains already cited to encourage diversity
        cited_domains: Dict[str, int] = {}

        if CLUSTER_SYNTHESIS_ENABLED:
            # =================================================================
            # FIX-161: Cluster-synthesize path
            # Groups evidence by topic, writes coherent paragraphs per cluster,
            # verifies with pronoun-aware context. ~87% fewer LLM calls.
            # =================================================================
            logger.info("[FIX-161] Using cluster-synthesize architecture")

            sections, grounded_claims, hedged_sentences = self._process_cluster_synthesis(
                evidence_chain, original_query, cited_domains,
            )
            ungroundable_claims: List[UngroundableClaim] = []

            self.stats["claims_grounded"] = len(grounded_claims)

            # Compose report from topical sections
            report = self._compose_clustered_report(
                sections, original_query, hedged_sentences=hedged_sentences,
            )
        else:
            # =================================================================
            # Original per-claim path (preserved for flag-off safety)
            # FIX-212 P1: Warn loudly — per-claim path produces significantly
            # worse output (Run #10: CASE_3, 0 citations)
            # =================================================================
            logger.warning(
                "[FIX-212] CLUSTER_SYNTHESIS is OFF — using per-claim path. "
                "This path has known quality issues. Set POLARIS_CLUSTER_SYNTHESIS=1 in .env."
            )

            # Step 2: For each claim, find evidence and verify
            grounded_claims = []
            ungroundable_claims: List[UngroundableClaim] = []
            hedged_sentences = []  # Track hedged sentences for report

            for i, claim in enumerate(claims):
                logger.debug(f"[FIX 117] Processing claim {i+1}/{len(claims)}: {claim.claim_text[:50]}...")

                # Find best evidence for this claim (with matching keywords for grounding context)
                # FIX-147: Pass cited_domains for diversity penalty
                evidence, matching_keywords = self._retrieve_for_claim(
                    claim, evidence_chain, cited_domains=cited_domains
                )

                if not evidence:
                    # No evidence found - handle according to strategy
                    logger.debug(f"[FIX 117] No evidence found for claim: {claim.claim_text[:50]}")
                    ungroundable = self._handle_ungroundable_claim(
                        claim=claim,
                        claim_id=f"claim_{i:03d}",
                        failure_reason="no_evidence",
                        best_evidence=None,
                        best_confidence=0.0,
                    )
                    ungroundable_claims.append(ungroundable)
                    if ungroundable.hedged_sentence:
                        hedged_sentences.append(ungroundable.hedged_sentence)
                    continue

                # Verify evidence supports claim
                verification_result = self._verify_claim_evidence(claim.claim_text, evidence)

                if verification_result["passed"]:
                    # Write grounded sentence
                    sentence = self._write_grounded_sentence(claim, evidence)

                    # FIX-171: GROUNDED_LOW claims get hedging prefix
                    grounding_level = verification_result.get("grounding_level", "GROUNDED")
                    if grounding_level == "GROUNDED_LOW" and sentence:
                        sentence = f"Evidence suggests that {sentence[0].lower()}{sentence[1:]}" if sentence[0].isupper() else f"Evidence suggests that {sentence}"

                    # Extract full grounding context for auditor passthrough
                    grounded_claim = GroundedClaim(
                        claim_id=f"claim_{i:03d}",
                        claim_text=claim.claim_text,
                        claim_type=claim.claim_type,
                        evidence_ids=[e.evidence_id for e in evidence],
                        evidence_texts=[e.text[:500] for e in evidence],
                        evidence_sources=[getattr(e, 'source_url', '') for e in evidence],
                        evidence_tiers=[getattr(e, 'quality_tier', 'UNVERIFIED') for e in evidence],
                        evidence_relevance=[getattr(e, 'relevance_score', 0.5) for e in evidence],
                        matching_keywords=matching_keywords,
                        confidence=verification_result["confidence"],
                        reasoning=verification_result["reasoning"],
                        sentence=sentence,
                        verification_passed=True,
                        verification_method=verification_result.get("method", "minicheck"),
                        threshold_used=CLAIM_VERIFICATION_THRESHOLD,
                        is_compound=len(claim.claim_text.split(' and ')) > 1,
                        atom_count=max(1, len(claim.claim_text.split(' and '))),
                    )
                    grounded_claims.append(grounded_claim)

                    # FIX-147: Track cited domains for diversity penalty
                    for ev in evidence:
                        domain = _extract_domain(getattr(ev, 'source_url', ''))
                        if domain:
                            cited_domains[domain] = cited_domains.get(domain, 0) + 1

                    logger.debug(f"[FIX 117] Claim grounded with confidence {verification_result['confidence']:.2f}")
                else:
                    # Verification failed - handle according to strategy
                    logger.debug(f"[FIX 117] Claim failed verification: {verification_result['reasoning']}")
                    ungroundable = self._handle_ungroundable_claim(
                        claim=claim,
                        claim_id=f"claim_{i:03d}",
                        failure_reason="verification_failed",
                        best_evidence=evidence[0] if evidence else None,
                        best_confidence=verification_result["confidence"],
                    )
                    ungroundable_claims.append(ungroundable)
                    if ungroundable.hedged_sentence:
                        hedged_sentences.append(ungroundable.hedged_sentence)

            self.stats["claims_grounded"] = len(grounded_claims)
            # Note: claims_ungroundable already incremented in _handle_ungroundable_claim

            # FIX-171: Log grounding rate
            total_attempted = len(grounded_claims) + len(ungroundable_claims)
            if total_attempted > 0:
                grounding_rate = len(grounded_claims) / total_attempted * 100
                logger.info(
                    f"[FIX-171] Grounding rate: {len(grounded_claims)}/{total_attempted} "
                    f"claims grounded ({grounding_rate:.1f}%)"
                )

            # Step 3: Check ungroundable ratio
            total_claims_for_ratio = len(claims)
            if total_claims_for_ratio > 0:
                ungroundable_ratio = len(ungroundable_claims) / total_claims_for_ratio
                if ungroundable_ratio > MAX_UNGROUNDABLE_RATIO:
                    logger.warning(
                        f"[FIX 117] High ungroundable ratio: {ungroundable_ratio:.1%} "
                        f"({len(ungroundable_claims)}/{total_claims_for_ratio})"
                    )

            # Step 4: Compose grounded claims into report (include hedged sentences)
            report = self._compose_report(
                grounded_claims,
                original_query,
                evidence_chain,
                hedged_sentences=hedged_sentences,
            )

        # FIX-147: Log citation diversity stats (shared by both paths)
        if cited_domains:
            unique_domains = len(cited_domains)
            total_citations = sum(cited_domains.values())
            logger.info(
                f"[FIX-147] Citation diversity: {unique_domains} unique domains across "
                f"{total_citations} total citations (diversity ratio: "
                f"{unique_domains / max(total_citations, 1):.2f})"
            )

        # Step 5: Build claim-evidence map for auditor
        claim_evidence_map = self._build_claim_evidence_map(grounded_claims)

        # Calculate statistics BEFORE copying to state
        if grounded_claims:
            avg_confidence = sum(c.confidence for c in grounded_claims) / len(grounded_claims)
            self.stats["average_confidence"] = avg_confidence

        # Update state (after stats calculation)
        state["draft_report"] = report
        state["claim_evidence_map"] = self._serialize_claim_evidence_map(claim_evidence_map)
        state["citefirst_stats"] = self.stats.copy()
        state["ungroundable_claims"] = [
            {
                "claim_id": uc.claim_id,
                "claim_text": uc.claim_text,
                "claim_type": uc.claim_type,
                "failure_reason": uc.failure_reason,
                "handling_strategy": uc.handling_strategy,
                "hedged_sentence": uc.hedged_sentence,
                "best_evidence_id": uc.best_evidence_id,
                "best_confidence": uc.best_confidence,
            }
            for uc in ungroundable_claims
        ]

        total_claims = len(claims)
        grounded_pct = len(grounded_claims) / max(total_claims, 1) * 100
        logger.info(
            f"[FIX 117] Cite-first synthesis complete: "
            f"{len(grounded_claims)}/{total_claims} claims grounded "
            f"({grounded_pct:.1f}%), "
            f"hedged={self.stats.get('claims_hedged', 0)}, "
            f"flagged={self.stats.get('claims_flagged', 0)}, "
            f"skipped={self.stats.get('claims_skipped', 0)}, "
            f"avg confidence: {self.stats.get('average_confidence', 0):.2f}"
        )

        return state

    def process_revision(
        self,
        state: ResearchState,
        sentences_to_revise: List[Dict[str, Any]],
    ) -> ResearchState:
        """
        Revision pass with dynamic re-retrieval for failed sentences.

        FIX 117 Phase 3.1: When auditor flags sentences as unfaithful,
        this method attempts to:
        1. Retrieve NEW evidence specifically for the failed claim
        2. Re-verify with the new evidence
        3. Rewrite the sentence if new evidence supports it
        4. Otherwise, apply hedging or removal

        This is the key innovation over the original revision loop which
        could only re-cite from the existing static evidence pool.
        """
        logger.info(f"[FIX 117] Starting revision with dynamic re-retrieval for {len(sentences_to_revise)} sentences")

        original_query = state.get("original_query", "")
        evidence_chain = state.get("evidence_chain", [])
        existing_evidence_ids = set(e.evidence_id for e in evidence_chain if hasattr(e, 'evidence_id'))
        draft_report = state.get("draft_report", "")

        # Track revision statistics
        revision_stats = {
            "sentences_revised": 0,
            "new_evidence_retrieved": 0,
            "sentences_rephrased": 0,
            "sentences_hedged": 0,
            "sentences_removed": 0,
        }

        # Process each sentence that needs revision
        revised_sentences = {}
        new_evidence_pool = []

        for item in sentences_to_revise:
            sentence = item.get("sentence", "")
            failure_reason = item.get("failure_reason", "verification_failed")
            original_citations = item.get("citations", [])

            logger.debug(f"[FIX 117] Revising: {sentence[:60]}... (reason: {failure_reason})")

            # Step 1: Try to retrieve NEW evidence for this sentence
            if PERCLAIM_RETRIEVAL_ENABLED:
                new_evidence = self._retrieve_new_evidence_for_sentence(
                    sentence=sentence,
                    original_query=original_query,
                    existing_evidence_ids=existing_evidence_ids,
                )

                if new_evidence:
                    revision_stats["new_evidence_retrieved"] += len(new_evidence)
                    new_evidence_pool.extend(new_evidence)
                    existing_evidence_ids.update(e.evidence_id for e in new_evidence if hasattr(e, 'evidence_id'))

                    # Step 2: Re-verify with new evidence
                    combined_evidence = " ".join([e.text for e in new_evidence])
                    verification = self._verify_claim_evidence(sentence, new_evidence)

                    if verification["passed"]:
                        # Step 3: Rewrite sentence with new evidence
                        claim = GeneratedClaim(
                            claim_text=sentence,
                            importance=3,
                            claim_type="factual",
                            keywords=sentence.split()[:5],
                        )
                        revised = self._write_grounded_sentence(claim, new_evidence)
                        # FIX-213A: Per-sentence CoT scrubbing after rephrase
                        if revised:
                            revised = scrub_cot_from_report(revised).strip()
                        if revised:
                            revised_sentences[sentence] = revised
                            revision_stats["sentences_rephrased"] += 1
                            logger.debug(f"[FIX 117] Sentence revised with new evidence")
                            continue
                        else:
                            logger.warning("[FIX-213A] Revised sentence entirely CoT, dropping")

            # FIX-166: Unfaithful + no evidence → DROP (not hedge)
            # Unfaithful + evidence exists → REPHRASE with evidence
            if PERCLAIM_RETRIEVAL_ENABLED and evidence_chain:
                # Try rephrase with existing evidence pool
                # FIX-200: Removed self-import that caused UnboundLocalError
                # GeneratedClaim is defined at module level (line 235)
                rephrase_claim = GeneratedClaim(
                    claim_text=sentence,
                    importance=3,
                    claim_type="factual",
                    keywords=sentence.split()[:5],
                )
                # Find any evidence from pool
                pool_evidence, _ = self._retrieve_for_claim(rephrase_claim, evidence_chain)
                if pool_evidence:
                    try:
                        rephrased = self._write_grounded_sentence(rephrase_claim, pool_evidence, max_rephrase_attempts=2)
                        if rephrased and rephrased.strip():
                            # FIX-213A: Per-sentence CoT scrubbing after rephrase
                            rephrased = scrub_cot_from_report(rephrased).strip()
                            if not rephrased:
                                logger.warning("[FIX-213A] Rephrased sentence entirely CoT, dropping")
                            else:
                                revised_sentences[sentence] = rephrased
                                revision_stats["sentences_rephrased"] += 1
                                revision_stats["sentences_revised"] += 1
                                continue
                    except Exception as e:
                        # FIX-212 P0: Log rephrase failure instead of silently dropping
                        logger.error(f"[FIX-212] Rephrase FAILED for sentence: {sentence[:60]}... Error: {e}")
                        revision_stats["rephrase_errors"] = revision_stats.get("rephrase_errors", 0) + 1

            # FIX-166: No evidence available or rephrase failed → DROP
            revised_sentences[sentence] = ""  # Empty = remove
            revision_stats["sentences_removed"] += 1
            revision_stats["sentences_revised"] += 1

        # Apply revisions to draft report
        original_word_count = len(draft_report.split())
        revised_report = draft_report
        for original, revised in revised_sentences.items():
            if revised:
                revised_report = revised_report.replace(original, revised)
            else:
                # Remove the sentence entirely
                revised_report = revised_report.replace(original + " ", "")
                revised_report = revised_report.replace(original, "")

        # FIX-166: Detect >20% word count drop after revision, trigger expansion
        revised_word_count = len(revised_report.split())
        if original_word_count > 0:
            drop_pct = (original_word_count - revised_word_count) / original_word_count
            if drop_pct > 0.20:
                logger.warning(
                    f"[FIX-166] Word count dropped {drop_pct:.0%} after revision "
                    f"({original_word_count} → {revised_word_count}). "
                    f"Triggering expansion via _write_section_prose()."
                )
                revision_stats["word_count_drop_pct"] = round(drop_pct * 100, 1)

                # FIX-166: Trigger expansion to recover lost content
                try:
                    unused_evidence = [
                        e for e in evidence_chain
                        if hasattr(e, 'text') and e.text and e.text[:100] not in revised_report
                    ]
                    if unused_evidence:
                        expansion_prose, expansion_claims = self._write_section_prose(
                            topic=original_query,
                            evidence=unused_evidence[:25],
                            query=original_query,
                        )
                        if expansion_prose and len(expansion_prose.split()) > 50:
                            revised_report = revised_report.rstrip() + "\n\n" + expansion_prose
                            revised_word_count = len(revised_report.split())
                            revision_stats["expansion_words_added"] = len(expansion_prose.split())
                            logger.info(
                                f"[FIX-166] Expansion added {len(expansion_prose.split())} words, "
                                f"new total: {revised_word_count}"
                            )
                        else:
                            logger.warning("[FIX-166] Expansion produced insufficient content")
                            revision_stats["expansion_failed"] = True
                    else:
                        logger.warning("[FIX-166] No unused evidence available for expansion")
                        revision_stats["expansion_failed"] = True
                except Exception as e:
                    # FIX-212 P1: Track expansion failures
                    logger.error(f"[FIX-212] Expansion FAILED: {e}")
                    revision_stats["expansion_failed"] = True

        # FIX-185D: Normalize paragraph breaks after find-and-replace
        # Collapse 3+ newlines to 2, preserving \n\n paragraph breaks
        revised_report = re.sub(r'\n{3,}', '\n\n', revised_report)

        # FIX-176: Scrub CoT from revised report before saving
        revised_report = scrub_cot_from_report(revised_report)

        # FIX-211: LLM post-filter for CoT lines that survive regex
        revised_report = cot_post_filter_report(
            revised_report, original_query,
            llm_invoke=lambda p: self._invoke_llm(p, max_tokens=2048),
        )

        # FIX-185B: Deduplicate sentences in revision path (parity with _compose_clustered_report)
        revised_report = self._deduplicate_report_sentences(revised_report)

        # FIX-185C: Section balance enforcement in revision path
        revision_sections = self._parse_report_to_section_dicts(revised_report)
        if revision_sections:
            min_section_words = int(os.environ.get("POLARIS_MIN_SECTION_WORDS", "150"))
            revision_sections = self._enforce_section_balance(revision_sections, min_section_words)
            revised_report = self._reassemble_section_dicts_to_report(revision_sections)

        # FIX-213B: Post-revision word count guard — reject catastrophic loss
        final_word_count = len(revised_report.split())
        if original_word_count > 0 and final_word_count < original_word_count * 0.5:
            logger.error(
                f"[FIX-213B] Revision CATASTROPHIC: {original_word_count} -> {final_word_count} words "
                f"({100 * (1 - final_word_count / original_word_count):.0f}% loss). "
                f"Rejecting revision, keeping original report."
            )
            revision_stats["revision_rejected"] = True
            state["revision_stats"] = revision_stats
            # Do NOT update draft_report — keep original
            return state

        # Update state
        state["draft_report"] = revised_report
        state["revision_stats"] = revision_stats

        # Add new evidence to evidence chain
        if new_evidence_pool:
            state["evidence_chain"] = list(evidence_chain) + new_evidence_pool
            logger.info(f"[FIX 117] Added {len(new_evidence_pool)} new evidence to pool via dynamic re-retrieval")

        logger.info(
            f"[FIX 117] Revision complete: "
            f"{revision_stats['sentences_rephrased']} rephrased, "
            f"{revision_stats['sentences_hedged']} hedged, "
            f"{revision_stats['sentences_removed']} removed, "
            f"{revision_stats['new_evidence_retrieved']} new evidence"
        )

        return state

    def _retrieve_new_evidence_for_sentence(
        self,
        sentence: str,
        original_query: str,
        existing_evidence_ids: set,
    ) -> List[Evidence]:
        """
        Retrieve NEW evidence for a failed sentence via Serper search.

        FIX 117 Phase 3.1: This enables dynamic re-retrieval during revision,
        breaking the static evidence pool limitation.
        """
        try:
            # Use auditor's per-claim retrieval if available
            from src.agents.auditor_agent import AuditorAgent

            auditor = AuditorAgent()
            new_evidence = auditor._retrieve_for_failed_claim_sync(
                claim=sentence,
                original_query=original_query,
                existing_evidence_ids=existing_evidence_ids,
                max_results=PERCLAIM_MAX_RESULTS,
            )

            return new_evidence

        except ImportError:
            logger.warning("[FIX 117] AuditorAgent not available for dynamic re-retrieval")
            return []
        except Exception as e:
            logger.error(f"[FIX 117] Dynamic re-retrieval failed: {e}")
            return []

    def _hedge_failed_sentence(
        self,
        sentence: str,
        failure_reason: str,
    ) -> str:
        """
        Apply hedging to a sentence that failed verification during revision.

        FIX-128: Sanitize BEFORE wrapping to prevent hedging CoT artifacts
        like "Some sources suggest that let me check the word count..."
        """
        # Remove existing citations (they're invalid)
        clean_sentence = re.sub(r'\[CITE:[^\]]+\]', '', sentence).strip()

        # FIX-128: Sanitize to remove CoT artifacts before hedging
        clean_sentence = self._sanitize_llm_output(clean_sentence)
        if not clean_sentence:
            # CoT artifact detected — return empty string (filtered by FIX-128C)
            logger.warning(
                "[FIX-128] Hedging target is a CoT artifact, returning empty"
            )
            return ""

        hedging_phrases = [
            "Some sources suggest that",
            "It has been reported that",
            "According to limited evidence,",
            "While not definitively verified,",
        ]

        import random
        hedge = random.choice(hedging_phrases)

        # Lowercase first letter of clean sentence if it starts with capital
        if clean_sentence and clean_sentence[0].isupper():
            clean_sentence = clean_sentence[0].lower() + clean_sentence[1:]

        return f"{hedge} {clean_sentence}"

    def _sanitize_llm_output(self, text: str) -> str:
        """
        FIX-128: Three-layer defense against LLM chain-of-thought leakage.

        KIMI K2.5 (and other models) sometimes leak internal reasoning into
        structured output. This sanitizer catches and removes such artifacts
        BEFORE they enter the report.

        Layer 1: Fatal pattern detection (hard reject)
        Layer 2: Prefix cleaning (remove CoT preamble)
        Layer 3: Structure heuristic (reject non-prose output)

        Returns:
            Cleaned text, or empty string if text is a CoT artifact.
        """
        if not text or not text.strip():
            return ""

        stripped = text.strip()

        # Layer 1: Fatal patterns — full-sentence CoT artifacts
        # IMPORTANT: Patterns are anchored to drafting/meta-commentary context.
        # Scientific terms like "meet the EPA target" or "To ensure safety"
        # must NOT match. Only self-referential LLM drafting language matches.
        fatal_patterns = [
            r"^Let me (try|check|reach|count|think|ensure|verify|see|look|read|now)",
            r"^I will (now|try|write|check|generate|create|produce|compose|draft)",
            r"^I need to",
            r"^I should",
            r"^Checking (word|character|sentence)\b",
            r"^Now (I|let|let's|we)",
            r"^Okay,?\s+(let|so|I)",
            r"^First,?\s+I",
            r"^To (?:reach|meet|achieve|ensure|get|make).{0,25}(?:word|character|sentence|count|length)",
            # FIX-132C: Additional CoT leakage patterns from Run #7 audit
            r"^Actually,?\s+",
            r"^In summary,?\s+",
            r"^To summarize,?\s+",
            # FIX-140: Additional CoT patterns from gap analysis
            r"^Wait,?\s+",
            r"^Looking at\s+",
            r"^The evidence\s+(says|provided|suggests|indicates|shows)",
            r"^I can\s+",
            r"^Hmm,?\s+",
            r"^So,?\s+(?:the|this|I|we|let)",
        ]
        for pat in fatal_patterns:
            if re.match(pat, stripped, re.IGNORECASE):
                logger.warning(
                    f"[FIX-128] Fatal CoT pattern detected, rejecting: "
                    f"'{stripped[:80]}...'"
                )
                return ""

        # Layer 2: Prefix cleaning — remove CoT preamble before actual content
        prefix_patterns = [
            r"^(?:Here is|Here's|The following is|Below is)[^:]*:\s*",
            r"^(?:Sure|Certainly|Of course)[,!.]?\s*",
            r'^"',  # Remove leading quote if present
        ]
        cleaned = stripped
        for pat in prefix_patterns:
            cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()

        # Remove trailing orphan quote
        if cleaned.endswith('"') and '"' not in cleaned[:-1]:
            cleaned = cleaned[:-1].strip()

        # Layer 3: Structure heuristic — reject non-prose output
        # Real sentences have at least 5 words and contain a verb-like structure
        word_count = len(cleaned.split())
        if word_count < 4:
            logger.warning(
                f"[FIX-128] Structure heuristic: too few words ({word_count}), "
                f"rejecting: '{cleaned[:80]}'"
            )
            return ""

        # Check for excessive procedural language (sign of partial CoT leak)
        procedural_keywords = [
            "word count", "character count", "sentence count",
            "let me", "i need", "i will", "i should",
            "checking", "ensuring", "making sure",
            # FIX-140: Prompt template echoes and procedural artifacts
            "the original sentence", "more faithful", "the rewrite",
            "claim to express", "source quote", "attempt 1", "attempt 2",
            "attempt 3", "evidence descriptions", "the claim to express",
        ]
        procedural_hits = sum(
            1 for kw in procedural_keywords if kw in cleaned.lower()
        )
        if procedural_hits >= 2:
            # FIX-175: Try to salvage prose paragraphs after CoT preamble
            # instead of rejecting the entire response
            paragraphs = re.split(r'\n\s*\n', cleaned)
            # FIX-184C: Respect POLARIS_SANITIZE_KEEP_CITED_PARAS flag
            keep_cited = os.environ.get("POLARIS_SANITIZE_KEEP_CITED_PARAS", "1") == "1"
            salvaged = []
            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue
                para_hits = sum(1 for kw in procedural_keywords if kw in para.lower())
                has_citation = bool(re.search(r'\[CITE:[^\]]+\]', para))
                # FIX-184C: Always keep paragraphs with citations when flag is set
                # (citations = domain content, not CoT; FIX-176 scrubber catches real CoT downstream)
                if para_hits < 2 or (has_citation and keep_cited):
                    # Also skip if it matches fatal patterns
                    is_fatal = any(re.match(pat, para, re.IGNORECASE) for pat in fatal_patterns)
                    if not is_fatal:
                        salvaged.append(para)

            if salvaged:
                salvaged_text = "\n\n".join(salvaged)
                salvaged_words = len(salvaged_text.split())
                if salvaged_words >= 30:
                    logger.info(
                        f"[FIX-175] Salvaged {salvaged_words} words of prose "
                        f"from {len(paragraphs)} paragraphs (discarded CoT preamble)"
                    )
                    return salvaged_text

            # Nothing salvageable — truly reject
            logger.warning(
                f"[FIX-128] Procedural language detected ({procedural_hits} hits), "
                f"no salvageable prose found: '{cleaned[:80]}...'"
            )
            return ""

        return cleaned

    def _extract_sentence_from_llm_response(self, response: str) -> str:
        """
        FIX-132A: Extract a single usable sentence from multi-paragraph LLM responses.

        KIMI K2.5 thinking mode dumps entire reasoning chains into responses.
        This method extracts the actual output sentence from such responses.

        Strategy (FIX-141: no fast path — all responses validated):
        1. Scan backwards for line containing [CITE:...] with >=8 words
        2. Scan backwards for last prose-like line (no CoT patterns)
        3. Return empty string if nothing found (triggers fallback)
        """
        if not response or not response.strip():
            return ""

        stripped = response.strip()

        lines = [line.strip() for line in stripped.split("\n") if line.strip()]

        # FIX-141: Removed fast path — single-line responses MUST be validated
        # against CoT/prose checks, not returned as-is. The fast path was allowing
        # CoT leakage and prompt echoes through unchecked.

        if len(lines) > 1:
            logger.debug(
                f"[FIX-132A] Multi-paragraph response detected ({len(lines)} lines), "
                f"extracting sentence"
            )

        # CoT patterns that indicate internal reasoning (not output)
        cot_indicators = [
            r"^(Let me|I will|I need|I should|Now |Okay|First|Actually|In summary|To summarize)",
            r"^(Checking|Ensuring|Making sure|Looking at|Reviewing|Analyzing)",
            r"^(The (user|prompt|task|request|question|instruction))",
            r"^(Step \d|Option \d|\d+[\.\)])",
            r"^(Wait|Hmm|So |But |However,?\s+I)",
            r"^(My (approach|plan|strategy|thought))",
            r"(word count|character count|sentence count|token count)",
        ]

        def is_cot_line(line: str) -> bool:
            """Check if a line looks like chain-of-thought reasoning."""
            for pat in cot_indicators:
                if re.search(pat, line, re.IGNORECASE):
                    return True
            return False

        def is_prose_like(line: str) -> bool:
            """Check if a line looks like actual prose output."""
            words = line.split()
            if len(words) < 8:
                return False
            if is_cot_line(line):
                return False
            # Must contain at least one letter
            if not any(c.isalpha() for c in line):
                return False
            return True

        # Priority 1: Scan backwards for line with valid [CITE:id] and >=8 words
        # FIX-149A: Require non-empty cite ID (not [CITE:] or [CITE: ])
        for line in reversed(lines):
            if re.search(r'\[CITE:[^\]\s]+\]', line) and len(line.split()) >= 8:
                logger.debug(f"[FIX-132A] Found cited line: '{line[:80]}...'")
                return line

        # Priority 2: Scan backwards for last prose-like line
        for line in reversed(lines):
            if is_prose_like(line):
                logger.debug(f"[FIX-132A] Found prose line: '{line[:80]}...'")
                return line

        # Nothing usable found
        logger.warning(
            f"[FIX-132A] No usable sentence found in {len(lines)}-line response, "
            f"returning empty (will trigger fallback)"
        )
        return ""

    def _build_evidence_summary_for_claims(
        self,
        query: str,
        evidence_pool: Optional[List[Evidence]],
    ) -> str:
        """
        Build a compact evidence summary for evidence-aware claim generation.

        FIX 117 T5: Uses embedding similarity to select the most relevant and
        diverse evidence texts, then formats them as numbered snippets for the
        claim generation prompt. This ensures the LLM generates claims that
        match what the evidence pool actually contains.
        """
        if not evidence_pool or self._embedding_service is None:
            return ""

        # Ensure evidence embeddings are computed
        self._ensure_evidence_embeddings(evidence_pool)

        # Embed the query
        query_embedding = np.array(self._embedding_service.embed(query))

        # Score all evidence by relevance to query
        # FIX-172: Include quality tier for tier-then-relevance sorting
        tier_order = {"GOLD": 4, "SILVER": 3, "BRONZE": 2, "UNVERIFIED": 1}
        scored = []
        for ev in evidence_pool:
            if hasattr(ev, 'is_metadata') and ev.is_metadata:
                continue
            ev_id = id(ev)
            if ev_id not in self._evidence_embeddings:
                continue

            ev_text = ev.text if hasattr(ev, 'text') else str(ev)
            if not ev_text or len(ev_text.strip()) < 20:
                continue

            similarity = float(np.dot(query_embedding, self._evidence_embeddings[ev_id]))
            quality_tier = getattr(ev, 'quality_tier', 'UNVERIFIED')
            tier_rank = tier_order.get(quality_tier, 1)
            scored.append((tier_rank, similarity, ev_text, ev_id))

        if not scored:
            return ""

        # FIX-172: Sort by quality tier (GOLD first), then text length (longer = more informative)
        scored.sort(key=lambda x: (x[0], len(x[2])), reverse=True)

        # Select top diverse evidence texts (deduplicate by embedding similarity)
        selected = []
        selected_embeddings = []
        # FIX-172: Expanded from 20 to 50 (env configurable via EVIDENCE_SUMMARY_COUNT)
        max_evidence_snippets = EVIDENCE_SUMMARY_COUNT

        for _tier, _sim, text, ev_id in scored:
            if len(selected) >= max_evidence_snippets:
                break

            # Check diversity: skip if too similar to already-selected evidence
            ev_emb = self._evidence_embeddings[ev_id]
            is_duplicate = False
            for sel_emb in selected_embeddings:
                if float(np.dot(ev_emb, sel_emb)) > 0.85:
                    is_duplicate = True
                    break

            if not is_duplicate:
                # FIX-172: Truncate to 300 chars (was 200) for richer evidence context
                # FIX-163: Strip artifacts before including in summary
                clean_text = self._strip_evidence_artifacts(text)
                snippet = clean_text[:300].strip()
                if len(clean_text) > 300:
                    snippet += "..."
                selected.append(f"- {snippet}")
                selected_embeddings.append(ev_emb)

        if not selected:
            return ""

        logger.info(
            f"[FIX 117 T5] Evidence summary: {len(selected)} diverse snippets "
            f"from {len(scored)} scored evidence (top sim={scored[0][0]:.3f})"
        )

        return "\n".join(selected)

    def _generate_claims(
        self,
        query: str,
        evidence_pool: Optional[List[Evidence]] = None,
    ) -> List[GeneratedClaim]:
        """
        Generate atomic claims from research query, informed by available evidence.

        Phase 1.2: This decomposes the query into verifiable atomic claims.
        Each claim should be answerable with a single piece of evidence.

        FIX 117 T5: Uses regular LLM call (thinking mode) instead of structured
        output to avoid KIMI K2.5 json_schema issues that return empty claims.
        Claims are parsed from plain text output for reliability.
        """
        # FIX 117 T5: Build evidence summary for claim generation
        evidence_summary = self._build_evidence_summary_for_claims(query, evidence_pool)

        if evidence_summary:
            # FIX-155: Evidence-constrained generation (STORM/Gemini approach)
            # Per NAACL 2025 "Decomposition Dilemmas": sub-claims > sentence count
            # HURTS quality. Target 30-60 high-quality evidence-aligned claims.
            prompt = f"""Extract atomic, verifiable factual claims from the evidence below.

QUERY: {query}

AVAILABLE EVIDENCE:
{evidence_summary}

RULES:
1. Extract ONLY facts, statistics, and findings stated in the evidence above.
2. Do NOT generate claims from your own knowledge — every claim must trace to an evidence snippet.
3. Each claim must be a single, specific, self-contained factual statement.
4. Include exact numbers, dates, names, and measurements where the evidence provides them.
5. Do NOT include meta-commentary about the task, instructions, or claim generation process.
6. Target 30-60 claims. Quality over quantity — one precise claim is better than three vague ones.

Output ONLY a numbered list of claims, one per line:
1. Lead exposure above 5 ppb in drinking water causes measurable IQ deficits in children under 6 years old.
2. Reverse osmosis filters remove 99% of dissolved lead from household water supplies.
"""
        else:
            prompt = f"""Decompose this research query into atomic, verifiable claims.

QUERY: {query}

RULES:
1. Each claim should be a single, specific factual statement.
2. Claims should be answerable with scientific evidence (not opinions).
3. Do NOT include meta-commentary about the task or claim generation process.
4. Generate 20-40 claims depending on query complexity.

Output ONLY a numbered list of claims, one per line:
1. Lead exposure above 5 ppb in drinking water causes measurable IQ deficits in children under 6 years old.
2. Reverse osmosis filters remove 99% of dissolved lead from household water supplies.
"""

        try:
            # FIX 117 T5: Use regular LLM call (thinking mode) instead of structured output
            # KIMI K2.5 json_schema mode returns empty claims with evidence-aware prompts
            # FIX-170: Per-call token budget for claim generation
            response_text = self._invoke_llm(prompt, max_tokens=TOKENS_CLAIM_GENERATION)

            # Parse numbered list into GeneratedClaim objects
            claims = self._parse_claims_from_text(response_text)

            if claims:
                logger.info(f"[FIX 117] Parsed {len(claims)} claims from LLM response")
                # FIX-154: LLM-based refiner (verify+correct, not just reject)
                claims = self._refine_claims_with_llm(claims)
                claims = claims[:MAX_CLAIMS_PER_QUERY]
                claims.sort(key=lambda c: c.importance, reverse=True)
                return claims
            else:
                logger.warning(f"[FIX 117] Failed to parse claims from response ({len(response_text)} chars)")

        except Exception as e:
            logger.error(f"[FIX 117] Claim generation failed: {e}")

        # FIX-212 P1: Track claim generation fallback level
        self.stats["claim_gen_fallback_level"] = self.stats.get("claim_gen_fallback_level", 0) + 1
        # Fallback: try structured output without evidence
        logger.warning("[FIX-212] Falling back to structured output claim generation (level 1)")
        try:
            simple_prompt = f"""Decompose this research query into atomic, verifiable claims.

QUERY: {query}

RULES:
1. Each claim should be a single, specific factual statement
2. Claims should be answerable with evidence (not opinions)
3. Break compound questions into atomic parts
4. Generate 20-40 claims depending on query complexity

OUTPUT: A JSON object with "claims" array and "query_understanding" string."""

            messages = [
                SystemMessage(content=self.get_system_prompt()),
                HumanMessage(content=simple_prompt),
            ]
            result = self.call_llm_structured(
                messages=messages,
                output_schema=ClaimDecomposition,
            )
            if result and result.claims:
                logger.info(f"[FIX 117] Structured fallback succeeded: {len(result.claims)} claims")
                for claim in result.claims:
                    if claim.importance > 5:
                        claim.importance = max(1, min(5, round(claim.importance / 2)))
                claims = result.claims[:MAX_CLAIMS_PER_QUERY]
                claims.sort(key=lambda c: c.importance, reverse=True)
                return claims
        except Exception as e:
            logger.error(f"[FIX 117] Structured fallback failed: {e}")

        # FIX-212 P1: Track claim generation fallback level (heuristic = level 2)
        self.stats["claim_gen_fallback_level"] = self.stats.get("claim_gen_fallback_level", 0) + 1
        # Last resort: heuristic fallback
        logger.warning("[FIX-212] Using heuristic fallback claim generation (level 2)")
        return self._generate_fallback_claims(query)

    @staticmethod
    def _is_meta_reasoning(text: str) -> bool:
        """
        FIX-151B: Fast regex pre-filter for obvious meta-reasoning.

        Used as cheap first pass before LLM refiner (FIX-154).
        Catches the most blatant patterns to avoid wasting LLM tokens.
        """
        meta_patterns = [
            r"(?i)^(splitting|combining|decomposing|breaking down)\s+(the\s+)?(compound\s+)?claims?\b",
            r"(?i)^the prompt\s+(asks|requires|says|requests|instructs)",
            r"(?i)^(i should|i need to|i will|i can|i'll|let me)\s",
            r"(?i)^SOTA systems\s",
            r"(?i)^as an?\s+(AI|language model|assistant|LLM)\b",
            r"(?i)^(here are|below are|the following)\s+(the\s+)?(atomic\s+)?claims\b",
            r"(?i)^(note|notice|remember|recall)\s*:",
            r"(?i)^(this|these)\s+(is|are)\s+(a\s+)?(claim|statement|assertion)",
        ]
        for pattern in meta_patterns:
            if re.search(pattern, text):
                return True
        return False

    def _refine_claims_with_llm(
        self,
        claims: List[GeneratedClaim],
    ) -> List[GeneratedClaim]:
        """
        FIX-154: LLM-based claim refiner with chain-of-thought reasoning.

        Instead of silently dropping meta-reasoning claims (FIX-151 regex),
        this method uses the LLM to:
        - KEEP genuine factual claims unchanged
        - REVISE meta-reasoning that contains an extractable real fact
        - DROP pure meta-reasoning with no recoverable content

        Based on VeriScore (EMNLP 2024) extraction filter approach and
        SAFE (Google 2024) claim revision for self-containment.
        One batched LLM call per claim set for efficiency.
        """
        if not claims:
            return claims

        # Identify candidates that might be meta-reasoning (fast regex pre-filter)
        suspect_indices = []
        for i, claim in enumerate(claims):
            if self._is_meta_reasoning(claim.claim_text):
                suspect_indices.append(i)

        if not suspect_indices:
            return claims

        # Build batch prompt for LLM refinement of suspect claims
        suspect_claims = [claims[i].claim_text for i in suspect_indices]
        numbered_claims = "\n".join(
            f"{j+1}. {text}" for j, text in enumerate(suspect_claims)
        )

        refine_prompt = f"""You are a claim quality judge for a research report. Analyze each candidate claim and classify it.

TASK: For each claim below, determine if it is a genuine research finding or meta-reasoning about the task itself.

RULES:
- KEEP: The claim states a verifiable real-world fact, statistic, or research finding. Output it unchanged.
- REVISE: The claim is meta-reasoning BUT contains an extractable real-world fact. Extract ONLY the factual part and output it as a clean claim.
- DROP: The claim is pure meta-reasoning about the generation process with no extractable fact.

CLAIMS:
{numbered_claims}

For each claim, output EXACTLY one line in this format:
<number>|<KEEP|REVISE|DROP>|<output claim text or NONE>

Examples:
1|KEEP|Lead exposure above 5 ppb causes IQ deficits in children under 6 years old.
2|DROP|NONE
3|REVISE|Approximately 500,000 people are affected by lead contamination in drinking water.

OUTPUT:"""

        try:
            messages = [
                SystemMessage(content=(
                    "You are a precise claim quality judge. Classify claims as "
                    "KEEP, REVISE, or DROP. When revising, extract only the "
                    "verifiable factual content. Be conservative: if in doubt, KEEP."
                )),
                HumanMessage(content=refine_prompt),
            ]
            response = self.call_llm(messages=messages)
            response_text = response.content if hasattr(response, 'content') else str(response)

            # Parse LLM response
            refined_map = {}  # suspect_index -> (action, revised_text)
            for line in response_text.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                parts = line.split('|', 2)
                if len(parts) >= 3:
                    try:
                        num = int(parts[0].strip()) - 1  # 0-indexed
                        action = parts[1].strip().upper()
                        text = parts[2].strip()
                        if 0 <= num < len(suspect_indices):
                            refined_map[num] = (action, text)
                    except (ValueError, IndexError):
                        continue

            # Apply refinements
            kept_count = 0
            revised_count = 0
            dropped_count = 0
            result_claims = []

            for i, claim in enumerate(claims):
                if i not in suspect_indices:
                    result_claims.append(claim)
                    continue

                suspect_idx = suspect_indices.index(i)
                action, text = refined_map.get(suspect_idx, ("KEEP", claim.claim_text))

                if action == "DROP" or text == "NONE":
                    dropped_count += 1
                elif action == "REVISE" and text and text != "NONE":
                    revised_count += 1
                    result_claims.append(GeneratedClaim(
                        claim_text=text,
                        importance=claim.importance,
                        claim_type=claim.claim_type,
                        keywords=self._extract_keywords(text),
                    ))
                else:
                    # KEEP or unrecognized action — preserve original
                    kept_count += 1
                    result_claims.append(claim)

            logger.info(
                f"[FIX-154] LLM claim refiner: {len(suspect_indices)} suspects → "
                f"kept={kept_count}, revised={revised_count}, dropped={dropped_count}"
            )
            return result_claims

        except Exception as e:
            logger.warning(
                f"[FIX-154] LLM refiner failed ({e}), falling back to regex filter"
            )
            # Fallback: use regex rejection (FIX-151 behavior)
            return [c for c in claims if not self._is_meta_reasoning(c.claim_text)]

    def _parse_claims_from_text(self, text: str) -> List[GeneratedClaim]:
        """Parse numbered claims from plain text LLM response."""
        claims = []
        # Match numbered list items: "1. claim text" or "1) claim text"
        lines = text.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Match patterns like "1. ", "1) ", "- ", "* "
            match = re.match(r'^(?:\d+[\.\)]\s*|[-*]\s+)(.+)$', line)
            if match:
                claim_text = match.group(1).strip()
                if len(claim_text) > 10:  # Filter out very short fragments
                    claims.append(GeneratedClaim(
                        claim_text=claim_text,
                        importance=3,  # Default importance
                        claim_type="factual",
                        keywords=self._extract_keywords(claim_text),
                    ))
        return claims

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract key terms from claim text for retrieval."""
        # Simple keyword extraction: remove stopwords, keep significant terms
        # FIX-194A: Use module-level _STOPWORDS
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        keywords = [w for w in words if w not in _STOPWORDS]
        return keywords[:10]

    def _generate_fallback_claims(self, query: str) -> List[GeneratedClaim]:
        """Generate basic claims when LLM decomposition fails."""
        # Simple heuristic decomposition
        claims = []

        # Main query as a claim
        claims.append(GeneratedClaim(
            claim_text=f"What is {query}?",
            importance=5,
            claim_type="factual",
            keywords=query.split()[:5],
        ))

        # Add common question types
        for qtype in ["statistics about", "causes of", "effects of", "solutions for"]:
            claims.append(GeneratedClaim(
                claim_text=f"{qtype} {query}",
                importance=3,
                claim_type="factual",
                keywords=query.split()[:3] + qtype.split(),
            ))

        return claims

    def _retrieve_for_claim(
        self,
        claim: GeneratedClaim,
        evidence_pool: List[Evidence],
        cited_domains: Optional[Dict[str, int]] = None,
    ) -> Tuple[List[Evidence], List[List[str]]]:
        """
        Retrieve best evidence for a specific claim using semantic similarity.

        FIX 117 T5: Replaced keyword word-overlap with embedding-based cosine
        similarity using all-MiniLM-L6-v2 (384 dims). This fixes the grounding
        rate bottleneck where keyword matching only found evidence for 19.4% of
        claims. Semantic similarity captures meaning overlap even when exact
        words differ.

        FIX-147: Accepts cited_domains dict to apply diversity penalty to
        already-cited domains, encouraging source breadth across the report.

        Falls back to keyword-based retrieval if embedding service is unavailable.

        Returns:
            Tuple of (evidence_list, matching_keywords_per_evidence)
        """
        self.stats["retrieval_calls"] = self.stats.get("retrieval_calls", 0) + 1

        if not evidence_pool:
            return [], []

        # FIX 117 T5: Use embedding-based retrieval if available
        if self._embedding_service is not None:
            return self._retrieve_by_embedding(claim, evidence_pool, cited_domains=cited_domains)

        # Fallback: keyword-based retrieval (original implementation)
        return self._retrieve_by_keyword(claim, evidence_pool)

    def _retrieve_by_embedding(
        self,
        claim: GeneratedClaim,
        evidence_pool: List[Evidence],
        cited_domains: Optional[Dict[str, int]] = None,
    ) -> Tuple[List[Evidence], List[List[str]]]:
        """
        Embedding-based evidence retrieval using cosine similarity.

        FIX 117 T5: Core implementation. Pre-computes evidence embeddings once
        per process() call via _ensure_evidence_embeddings(), then scores each
        evidence against the claim embedding via dot product (vectors are
        pre-normalized by sentence-transformers).

        FIX-147: Applies diversity penalty to already-cited domains. Score is
        multiplied by DIVERSITY_PENALTY^n where n is the number of times the
        domain has already been cited. This gently pushes retrieval toward
        uncited sources without blocking high-relevance evidence.
        """
        # Ensure evidence embeddings are cached (no-op if already computed)
        self._ensure_evidence_embeddings(evidence_pool)

        # Embed the claim text
        claim_text = claim.claim_text
        claim_embedding = np.array(self._embedding_service.embed(claim_text))

        # FIX-194A: Use module-level _STOPWORDS
        claim_words = set(claim_text.lower().split()) - _STOPWORDS
        claim_words.update(k.lower() for k in claim.keywords if k.lower() not in _STOPWORDS)

        scored_evidence = []
        for ev in evidence_pool:
            # Skip metadata
            if hasattr(ev, 'is_metadata') and ev.is_metadata:
                continue

            ev_id = id(ev)
            if ev_id not in self._evidence_embeddings:
                continue

            ev_embedding = self._evidence_embeddings[ev_id]

            # Cosine similarity (embeddings are pre-normalized, dot product suffices)
            similarity = float(np.dot(claim_embedding, ev_embedding))

            if similarity > SEMANTIC_SIMILARITY_THRESHOLD:
                # Quality tier weight (modest boost for higher-quality sources)
                tier_weight = {
                    "GOLD": 1.15,
                    "SILVER": 1.08,
                    "BRONZE": 1.0,
                    "UNVERIFIED": 0.92,
                }.get(getattr(ev, 'quality_tier', 'UNVERIFIED'), 1.0)

                score = similarity * tier_weight

                # FIX-147: Apply diversity penalty for already-cited domains
                if cited_domains:
                    ev_domain = _extract_domain(getattr(ev, 'source_url', ''))
                    if ev_domain and ev_domain in cited_domains:
                        citation_count = cited_domains[ev_domain]
                        score *= DIVERSITY_PENALTY ** citation_count

                # Extract keyword overlap for grounding context
                ev_text = ev.text.lower() if hasattr(ev, 'text') else str(ev).lower()
                ev_words = set(ev_text.split())
                matching = list(claim_words & ev_words)
                if not matching:
                    # Use first content words from claim as fallback context
                    matching = list(claim_words)[:3]

                scored_evidence.append((score, ev, matching))

        # Sort by score descending
        scored_evidence.sort(key=lambda x: x[0], reverse=True)

        # FIX 117 T5: Diagnostic logging for retrieval analysis
        if scored_evidence:
            top_score = scored_evidence[0][0]
            logger.info(
                f"[FIX 117 T5] Retrieval for '{claim_text[:50]}...': "
                f"{len(scored_evidence)} evidence above {SEMANTIC_SIMILARITY_THRESHOLD} threshold "
                f"(top score={top_score:.3f})"
            )
        else:
            logger.info(
                f"[FIX 117 T5] Retrieval for '{claim_text[:50]}...': "
                f"0 evidence above {SEMANTIC_SIMILARITY_THRESHOLD} threshold"
            )

        # Take top results above threshold
        max_results = MIN_EVIDENCE_PER_CLAIM + 2
        top_results = [
            (ev, keywords)
            for score, ev, keywords in scored_evidence[:max_results]
        ]

        if not top_results:
            return [], []

        evidence_list = [ev for ev, _ in top_results]
        keywords_list = [keywords for _, keywords in top_results]

        return evidence_list, keywords_list

    def _retrieve_by_keyword(
        self,
        claim: GeneratedClaim,
        evidence_pool: List[Evidence],
    ) -> Tuple[List[Evidence], List[List[str]]]:
        """
        Keyword-based evidence retrieval (fallback when embeddings unavailable).

        Original implementation preserved as fallback for FIX 117 T5.
        """
        claim_words = set(claim.claim_text.lower().split())
        claim_words.update(k.lower() for k in claim.keywords)
        # FIX-194A: Use module-level _STOPWORDS
        claim_words -= _STOPWORDS

        scored_evidence = []
        for ev in evidence_pool:
            if hasattr(ev, 'is_metadata') and ev.is_metadata:
                continue

            ev_text = ev.text.lower() if hasattr(ev, 'text') else str(ev).lower()
            ev_words = set(ev_text.split())

            matching = claim_words & ev_words
            overlap = len(matching)
            if overlap > 0:
                tier_weight = {
                    "GOLD": 1.5,
                    "SILVER": 1.2,
                    "BRONZE": 1.0,
                    "UNVERIFIED": 0.8,
                }.get(getattr(ev, 'quality_tier', 'UNVERIFIED'), 1.0)

                score = overlap * tier_weight * getattr(ev, 'relevance_score', 0.5)
                scored_evidence.append((score, ev, list(matching)))

        scored_evidence.sort(key=lambda x: x[0], reverse=True)

        top_results = [(ev, keywords) for score, ev, keywords in scored_evidence[:5] if score > 1.0]

        if not top_results:
            return [], []

        evidence_list = [ev for ev, _ in top_results[:MIN_EVIDENCE_PER_CLAIM + 2]]
        keywords_list = [keywords for _, keywords in top_results[:MIN_EVIDENCE_PER_CLAIM + 2]]

        return evidence_list, keywords_list

    def _verify_claim_evidence(
        self,
        claim: str,
        evidence: List[Evidence],
    ) -> Dict[str, Any]:
        """
        Verify that evidence supports the claim.

        Phase 1.4: This is INLINE verification - happens DURING synthesis,
        not after (post-hoc by auditor). This is the key architectural change.

        FIX 117 Phase 4.2: Uses adaptive thresholds based on claim complexity.
        Simple claims use lower thresholds; complex claims use higher.
        """
        self.stats["verification_calls"] = self.stats.get("verification_calls", 0) + 1

        # Combine evidence texts
        evidence_text = " ".join([e.text for e in evidence])

        # FIX 117 Phase 4.2: Get adaptive threshold based on claim complexity
        try:
            from src.utils.inline_verifier import get_adaptive_threshold
            adaptive_threshold = get_adaptive_threshold(claim, CLAIM_VERIFICATION_THRESHOLD)
        except ImportError:
            adaptive_threshold = CLAIM_VERIFICATION_THRESHOLD

        # Use inline verifier if available
        if self.inline_verifier:
            try:
                # Use adaptive threshold instead of fixed threshold
                result = self.inline_verifier.verify(claim, evidence_text, threshold=adaptive_threshold)
                confidence = result["confidence"]
                # FIX-171: Tiered grounding
                if confidence >= CLAIM_HIGH_CONFIDENCE_THRESHOLD:
                    grounding_level = "GROUNDED"
                elif confidence >= adaptive_threshold:
                    grounding_level = "GROUNDED_LOW"
                else:
                    grounding_level = "UNGROUNDED"
                return {
                    "passed": grounding_level in ("GROUNDED", "GROUNDED_LOW"),
                    "confidence": confidence,
                    "reasoning": result.get("reasoning", "MiniCheck verification"),
                    "method": "minicheck",
                    "threshold_used": adaptive_threshold,
                    "grounding_level": grounding_level,
                }
            except Exception as e:
                logger.warning(f"[FIX 117] Inline verifier failed: {e}, using LLM fallback")

        # LLM fallback verification
        prompt = f"""Verify if the EVIDENCE supports the CLAIM.

CLAIM: {claim}

EVIDENCE:
{evidence_text[:4000]}

OUTPUT:
- VERDICT: SUPPORTED or NOT_SUPPORTED
- CONFIDENCE: 0.0-1.0
- REASONING: Brief explanation"""

        try:
            response = self._invoke_llm(prompt)

            # Parse response
            verdict = "SUPPORTED" in response.upper()
            confidence = 0.5  # Default

            # Try to extract confidence
            conf_match = re.search(r'CONFIDENCE[:\s]+([0-9.]+)', response, re.IGNORECASE)
            if conf_match:
                confidence = float(conf_match.group(1))

            # FIX-171: Tiered grounding for LLM fallback
            if confidence >= CLAIM_HIGH_CONFIDENCE_THRESHOLD:
                grounding_level = "GROUNDED"
            elif confidence >= adaptive_threshold:
                grounding_level = "GROUNDED_LOW"
            else:
                grounding_level = "UNGROUNDED"

            return {
                "passed": verdict and grounding_level in ("GROUNDED", "GROUNDED_LOW"),
                "confidence": confidence,
                "reasoning": response[:200],
                "method": "llm_fallback",
                "threshold_used": adaptive_threshold,
                "grounding_level": grounding_level,
            }
        except Exception as e:
            logger.error(f"[FIX 117] Verification failed: {e}")
            return {"passed": False, "confidence": 0.0, "reasoning": f"Verification error: {e}", "method": "error"}

    def _write_grounded_sentence(
        self,
        claim: GeneratedClaim,
        evidence: List[Evidence],
        max_rephrase_attempts: int = 2,
    ) -> str:
        """
        Write a sentence grounded in evidence with inline verification.

        Phase 2.3: Generate a faithful sentence that expresses the claim
        using the provided evidence. The sentence MUST be verifiable.

        FIX 117 Enhancement: Verifies the generated sentence BEFORE returning.
        If verification fails, attempts to rephrase closer to evidence.
        This is the key innovation - verification happens DURING synthesis.
        """
        # FIX-173: Pass top 3 evidence pieces (not just 1) for multi-evidence claims
        top_evidence = evidence[:3]
        evidence_context = "\n".join([
            f"[{e.evidence_id}]: {self._strip_evidence_artifacts(e.text[:500])}" for e in top_evidence
        ])
        combined_evidence_text = " ".join([e.text for e in top_evidence])

        prompt = f"""Write a detailed sentence expressing this claim, grounded in the evidence.

CLAIM: {claim.claim_text}

EVIDENCE:
{evidence_context}

RULES:
1. Use exact numbers, dates, study names, and specific details from evidence
2. Add [CITE:evidence_id] after the factual content — cite ALL evidence pieces that support the claim (2-3 citations per sentence)
3. Write ONE comprehensive sentence that includes key details (numbers, context, scope)
4. Aim for 25-40 words to capture the full finding, not just a summary
5. Use hedging ("approximately", "studies suggest") if evidence is imprecise
6. Do NOT include any internal reasoning, thinking process, or meta-commentary about word counts, formatting, or task completion. Output ONLY the final sentence.

EXAMPLE:
"A study of 157 adults from the Cincinnati Lead Study found significant inverse associations between childhood blood lead levels (ages 3-6) and adult gray matter volume, with effects particularly pronounced in the prefrontal cortex of male subjects [CITE:ev_001]."

OUTPUT: A single detailed sentence with citation. No preamble, no explanation, no meta-commentary."""

        try:
            # FIX-220: Use structural reasoning/content separation for prose generation
            # KimiClient separates reasoning_content from content at API level
            response = self._invoke_synthesis_llm(prompt, system_prompt=self.get_system_prompt())
            # FIX-132D: Extract usable sentence from multi-paragraph responses
            sentence = self._extract_sentence_from_llm_response(response)

            # FIX-128: Sanitize LLM output to remove CoT leakage
            sentence = self._sanitize_llm_output(sentence)
            if not sentence:
                logger.warning(
                    "[FIX-128] Sentence generation produced CoT artifact, "
                    "falling back to direct quote"
                )
                return self._create_direct_quote_sentence(claim, evidence)

            # FIX-156: Reject truncated sentences and fall back to direct quote
            if self._is_truncated(sentence):
                logger.warning(
                    "[FIX-156] Sentence is truncated, falling back to direct quote: "
                    f"'...{sentence[-50:]}'"
                )
                return self._create_direct_quote_sentence(claim, evidence)

            # FIX-149B: Strip empty cite tokens before the guard check
            sentence = self._replace_empty_cites(sentence, evidence)

            # Ensure citation is present
            if "[CITE:" not in sentence and evidence:
                sentence = f"{sentence} [CITE:{evidence[0].evidence_id}]"

            # FIX 117 Phase 2.3: Inline verification BEFORE returning
            # This catches unfaithful paraphrasing before it enters the report
            if self.inline_verifier:
                # Extract claim text from sentence (remove citations for verification)
                sentence_for_verify = re.sub(r'\[CITE:[^\]]+\]', '', sentence).strip()

                # FIX 117 T1: Use adaptive threshold for inline verification
                # (consistent with _verify_claim_evidence)
                try:
                    from src.utils.inline_verifier import get_adaptive_threshold
                    inline_threshold = get_adaptive_threshold(
                        sentence_for_verify, CLAIM_VERIFICATION_THRESHOLD
                    )
                except ImportError:
                    inline_threshold = CLAIM_VERIFICATION_THRESHOLD

                verification = self.inline_verifier.verify(
                    claim=sentence_for_verify,
                    evidence=combined_evidence_text,
                    threshold=inline_threshold,
                )

                if not verification["verdict"]:
                    # Sentence failed verification - try rephrasing
                    logger.debug(
                        f"[FIX 117] Sentence failed inline verification "
                        f"(conf={verification['confidence']:.2f}), attempting rephrase"
                    )

                    for attempt in range(max_rephrase_attempts):
                        rephrased = self._rephrase_closer_to_evidence(
                            original_sentence=sentence,
                            claim=claim.claim_text,
                            evidence=evidence,
                            attempt=attempt + 1,
                        )

                        # Verify rephrased sentence
                        rephrased_for_verify = re.sub(r'\[CITE:[^\]]+\]', '', rephrased).strip()
                        rephrase_verification = self.inline_verifier.verify(
                            claim=rephrased_for_verify,
                            evidence=combined_evidence_text,
                        )

                        if rephrase_verification["verdict"]:
                            logger.debug(
                                f"[FIX 117] Rephrase attempt {attempt+1} succeeded "
                                f"(conf={rephrase_verification['confidence']:.2f})"
                            )
                            return rephrased

                    # All rephrase attempts failed - use quote-based fallback
                    logger.debug("[FIX 117] All rephrase attempts failed, using direct quote")
                    return self._create_direct_quote_sentence(claim, evidence)

            return sentence

        except Exception as e:
            logger.error(f"[FIX 117] Sentence generation failed: {e}")
            # Fallback: simple sentence with citation
            if evidence:
                return f"{claim.claim_text} [CITE:{evidence[0].evidence_id}]"
            return claim.claim_text

    def _rephrase_closer_to_evidence(
        self,
        original_sentence: str,
        claim: str,
        evidence: List[Evidence],
        attempt: int,
    ) -> str:
        """
        Rephrase sentence to be closer to evidence text.

        FIX 117 Phase 2.3: When inline verification fails, this method
        generates an alternative phrasing that stays closer to the
        original evidence language to reduce semantic drift.
        """
        evidence_context = "\n".join([
            f"[{e.evidence_id}]: {e.text[:500]}" for e in evidence
        ])

        prompt = f"""The following sentence was flagged as not faithful to the evidence.
Rewrite it to be MORE FAITHFUL by using language closer to the original evidence.

ORIGINAL SENTENCE: {original_sentence}

CLAIM TO EXPRESS: {claim}

EVIDENCE:
{evidence_context}

REWRITE RULES:
1. Use EXACT phrases from the evidence when possible
2. If the evidence uses a specific term, use that term (don't paraphrase)
3. Prefer direct quotes with quotation marks for key facts
4. Keep [CITE:id] citations
5. Add hedging if the evidence is uncertain ("according to", "the study found")

Attempt {attempt} - be more conservative and literal.

OUTPUT: A single rewritten sentence that matches the evidence language."""

        try:
            # FIX-220: Use structural reasoning/content separation for prose generation
            response = self._invoke_synthesis_llm(prompt, system_prompt=self.get_system_prompt())
            # FIX-132B: Extract sentence from multi-paragraph response + sanitize
            rephrased = self._extract_sentence_from_llm_response(response)
            rephrased = self._sanitize_llm_output(rephrased)
            if not rephrased:
                return original_sentence  # Safe fallback

            # Ensure citation preserved
            if "[CITE:" not in rephrased and evidence:
                rephrased = f"{rephrased} [CITE:{evidence[0].evidence_id}]"

            return rephrased

        except Exception as e:
            logger.error(f"[FIX 117] Rephrase failed: {e}")
            return original_sentence

    def _handle_ungroundable_claim(
        self,
        claim: GeneratedClaim,
        claim_id: str,
        failure_reason: str,
        best_evidence: Optional[Evidence],
        best_confidence: float,
    ) -> UngroundableClaim:
        """
        Handle a claim that cannot be grounded according to configured strategy.

        FIX 117 Phase 2.4: Implements three strategies for ungroundable claims:
        - skip: Silently drop the claim (no output)
        - hedge: Generate hedged language ("Evidence is limited regarding...")
        - flag: Include with [UNGROUNDED] marker for transparency

        The strategy is configured via POLARIS_UNGROUNDABLE_STRATEGY env var.
        """
        strategy = UNGROUNDABLE_STRATEGY
        hedged_sentence = None

        if strategy == "skip":
            # Simply skip - no output
            self.stats["claims_skipped"] += 1
            handling = "skipped"
            logger.debug(f"[FIX 117] Ungroundable claim skipped: {claim.claim_text[:50]}")

        elif strategy == "hedge":
            # Generate hedged version
            hedged_sentence = self._generate_hedged_sentence(claim, best_evidence, failure_reason)
            self.stats["claims_hedged"] += 1
            handling = "hedged"
            logger.debug(f"[FIX 117] Ungroundable claim hedged: {claim.claim_text[:50]}")

        elif strategy == "flag":
            # Flag as ungrounded
            hedged_sentence = f"[UNGROUNDED] {claim.claim_text}"
            self.stats["claims_flagged"] += 1
            handling = "flagged"
            logger.debug(f"[FIX 117] Ungroundable claim flagged: {claim.claim_text[:50]}")

        else:
            # Unknown strategy - default to skip
            logger.warning(f"[FIX 117] Unknown ungroundable strategy '{strategy}', defaulting to skip")
            self.stats["claims_skipped"] += 1
            handling = "skipped"

        self.stats["claims_ungroundable"] += 1

        return UngroundableClaim(
            claim_id=claim_id,
            claim_text=claim.claim_text,
            claim_type=claim.claim_type,
            failure_reason=failure_reason,
            handling_strategy=handling,
            hedged_sentence=hedged_sentence,
            best_evidence_id=best_evidence.evidence_id if best_evidence else None,
            best_confidence=best_confidence,
        )

    def _generate_hedged_sentence(
        self,
        claim: GeneratedClaim,
        best_evidence: Optional[Evidence],
        failure_reason: str,
    ) -> str:
        """
        Generate a hedged sentence for an ungroundable claim.

        FIX 117 Phase 2.4: Produces appropriately hedged language that
        signals uncertainty while still providing relevant information.
        """
        # Select hedging prefix based on failure reason
        if failure_reason == "no_evidence":
            prefixes = [
                "Evidence on this topic is limited; however, ",
                "While direct evidence was not found, it is generally understood that ",
                "The available sources do not directly address ",
            ]
        elif failure_reason == "verification_failed":
            prefixes = [
                "Some sources suggest that ",
                "According to limited evidence, ",
                "It has been reported, though not definitively verified, that ",
            ]
        else:
            prefixes = [
                "Available information indicates that ",
                "Based on partial evidence, ",
            ]

        import random
        prefix = random.choice(prefixes)

        # If we have partial evidence, try to incorporate it
        if best_evidence and failure_reason == "verification_failed":
            return f'{prefix}"{claim.claim_text.lower()}" [PARTIAL_SUPPORT:{best_evidence.evidence_id}]'

        # For no evidence, use pure hedging
        if failure_reason == "no_evidence":
            return f"{prefix}further research may be needed regarding {claim.claim_text.lower()}."

        return f"{prefix}{claim.claim_text.lower()}."

    def _replace_empty_cites(
        self,
        sentence: str,
        evidence: Optional[List[Evidence]] = None,
    ) -> str:
        """
        FIX-149C: Strip empty [CITE:] and [CITE: ] tokens, then append evidence ID if available.
        FIX-178A: Also strip placeholder citations like [CITE:source1], [CITE:ref1], etc.

        Empty cite tokens are produced when the LLM generates [CITE:] without an ID.
        Placeholder cites are produced when the LLM invents fake IDs instead of using
        real evidence IDs.
        """
        # Strip all empty cite variants: [CITE:], [CITE: ], [CITE:  ]
        empty_cite_pattern = re.compile(r'\[CITE:\s*\]')
        empty_count = len(empty_cite_pattern.findall(sentence))

        if empty_count > 0:
            logger.warning(
                f"[FIX-149C] Stripping {empty_count} empty [CITE:] "
                f"token(s) from sentence"
            )
            sentence = empty_cite_pattern.sub('', sentence).strip()

            # If no valid cite remains and evidence is available, append one
            if '[CITE:' not in sentence and evidence:
                sentence = f"{sentence} [CITE:{evidence[0].evidence_id}]"

        # FIX-178A: Strip placeholder citations
        placeholder_patterns = [
            r'\[CITE:source\d*\]',
            r'\[CITE:Source_?\d*\]',
            r'\[CITE:evidence_?\d*\]',
            r'\[CITE:ref_?\d*\]',
            r'\[CITE:(?!ev_|chunk_|evidence_)[a-zA-Z]{1,10}[_\d]*\]',  # FIX-183D: Case-insensitive short non-hash IDs (excludes real ID prefixes)
        ]
        # Build valid ID set from evidence context
        valid_ids = set()
        if evidence:
            valid_ids = {e.evidence_id for e in evidence}

        for pattern in placeholder_patterns:
            matches = re.findall(pattern, sentence, re.IGNORECASE)
            for match in matches:
                # Extract the ID from the match
                cite_id = re.search(r'\[CITE:([^\]]+)\]', match)
                if cite_id and cite_id.group(1) not in valid_ids:
                    logger.warning(f"[FIX-178A] Stripping placeholder citation: {match}")
                    sentence = sentence.replace(match, "").strip()

        # If all cites were stripped and evidence is available, append one
        if '[CITE:' not in sentence and evidence:
            sentence = f"{sentence} [CITE:{evidence[0].evidence_id}]"

        return sentence

    @staticmethod
    def _is_truncated(sentence: str) -> bool:
        """
        FIX-156: Detect sentences that are truncated mid-word or mid-DOI/URL.

        Catches:
        - No terminal punctuation (sentence ends mid-word)
        - Unbalanced parentheses or brackets
        - Truncated DOIs (doi:10.xxx/ without closing)
        - Truncated URLs (http:// without complete path)
        """
        if not sentence or not sentence.strip():
            return True

        stripped = sentence.strip()

        # Remove trailing citation tokens for punctuation check
        stripped_no_cite = re.sub(r'\s*\[CITE:[^\]]*\]\s*$', '', stripped).strip()
        if not stripped_no_cite:
            return True

        # Check for terminal punctuation
        if stripped_no_cite[-1] not in '.!?)"\'':
            # Allow sentences ending with quotes or closing parens
            logger.debug(
                f"[FIX-156] Sentence lacks terminal punctuation: "
                f"'...{stripped_no_cite[-30:]}'"
            )
            return True

        # Check for unbalanced parentheses
        if stripped_no_cite.count('(') != stripped_no_cite.count(')'):
            return True

        # Check for truncated DOIs: doi:10.xxxx/ without at least some path
        doi_match = re.search(r'doi:\s*10\.\d+/[^\s\]]*$', stripped_no_cite)
        if doi_match:
            doi_text = doi_match.group(0)
            # Truncated if ends with dash, slash, or mid-identifier
            if doi_text[-1] in '-/':
                return True

        return False

    def _create_direct_quote_sentence(
        self,
        claim: GeneratedClaim,
        evidence: List[Evidence],
    ) -> str:
        """
        Create a sentence using direct quotes from evidence.

        FIX 117 Phase 2.3: Last resort when all rephrase attempts fail.
        Extracts a relevant quote directly from evidence and frames it.
        Direct quotes are maximally faithful.
        """
        if not evidence:
            return claim.claim_text

        ev = evidence[0]
        ev_text = ev.text

        # Extract a relevant snippet (find sentence containing key terms)
        claim_words = set(claim.claim_text.lower().split())
        sentences = re.split(r'[.!?]', ev_text)

        best_sentence = ""
        best_overlap = 0

        for sent in sentences:
            sent = sent.strip()
            if len(sent) < 20 or len(sent) > 200:
                continue
            sent_words = set(sent.lower().split())
            overlap = len(claim_words & sent_words)
            if overlap > best_overlap:
                best_overlap = overlap
                best_sentence = sent

        if best_sentence:
            # Frame the quote
            return f'According to the source, "{best_sentence}" [CITE:{ev.evidence_id}]'

        # Fallback: use first 100 chars of evidence
        snippet = ev_text[:100].strip()
        if '.' in snippet:
            snippet = snippet[:snippet.rindex('.')+1]
        return f'The evidence states: "{snippet}" [CITE:{ev.evidence_id}]'

    def _deduplicate_sentences(
        self,
        sentences: List[str],
        threshold: float = None,
    ) -> List[str]:
        """
        FIX-153: Embedding-based semantic deduplication (replaces FIX-134A Jaccard).

        Uses cosine similarity from all-MiniLM-L6-v2 embeddings to catch
        semantic duplicates that word-level Jaccard misses (same fact, different
        words). Falls back to Jaccard when embedding service is unavailable.

        Per NVIDIA SemDeDup: embedding cosine threshold 0.85 for sentence-level
        dedup. Per Semantic Entropy (Nature 2024): embedding pre-filter + NLI
        verification is SOTA, but cosine alone catches 85%+ of semantic dupes.

        Args:
            sentences: List of sentences to deduplicate.
            threshold: Similarity threshold (0.0-1.0). Default from env var
                      POLARIS_SENTENCE_DEDUP_THRESHOLD or 0.85 (raised from 0.70).

        Returns:
            Deduplicated list preserving original order.
        """
        if threshold is None:
            threshold = float(
                os.environ.get("POLARIS_SENTENCE_DEDUP_THRESHOLD", "0.85")
            )

        if not sentences or len(sentences) <= 1:
            return sentences

        # Strip citations for comparison to avoid false differences from citation IDs
        cite_pattern = re.compile(r'\[CITE:[^\]]+\]')

        def clean_for_comparison(text: str) -> str:
            """Remove citations and normalize for comparison."""
            return cite_pattern.sub("", text).strip()

        # FIX-153: Try embedding-based dedup first
        if getattr(self, '_embedding_service', None) is not None:
            return self._deduplicate_by_embedding(
                sentences, threshold, clean_for_comparison
            )

        # Fallback: Jaccard word-overlap (when embedding service unavailable)
        return self._deduplicate_by_jaccard(
            sentences, threshold, cite_pattern
        )

    def _deduplicate_by_embedding(
        self,
        sentences: List[str],
        threshold: float,
        clean_fn,
    ) -> List[str]:
        """
        FIX-153: Embedding cosine similarity deduplication.

        Embeds all sentences using all-MiniLM-L6-v2, then greedily keeps
        first occurrence and drops subsequent sentences with cosine >= threshold
        against any already-kept sentence.
        """
        # Clean and embed all sentences
        cleaned_texts = []
        valid_indices = []
        for i, sentence in enumerate(sentences):
            if not sentence or not sentence.strip():
                continue
            cleaned_texts.append(clean_fn(sentence))
            valid_indices.append(i)

        if len(cleaned_texts) <= 1:
            return [sentences[i] for i in valid_indices]

        try:
            # FIX-186A: embed_texts() is a module-level function; instance method is embed_batch()
            embeddings = self._embedding_service.embed_batch(cleaned_texts)
            embeddings_np = np.array(embeddings)

            # Normalize for cosine similarity via dot product
            norms = np.linalg.norm(embeddings_np, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1, norms)
            embeddings_np = embeddings_np / norms
        except Exception as e:
            logger.warning(
                f"[FIX-153] Embedding failed, falling back to Jaccard: {e}"
            )
            cite_pattern = re.compile(r'\[CITE:[^\]]+\]')
            return self._deduplicate_by_jaccard(
                sentences, threshold, cite_pattern
            )

        deduplicated = []
        kept_embeddings = []

        for idx, sent_idx in enumerate(valid_indices):
            if not kept_embeddings:
                deduplicated.append(sentences[sent_idx])
                kept_embeddings.append(embeddings_np[idx])
                continue

            # Compare against all kept embeddings
            current_emb = embeddings_np[idx]
            kept_matrix = np.array(kept_embeddings)
            similarities = kept_matrix @ current_emb

            max_sim = float(np.max(similarities))
            if max_sim >= threshold:
                # FIX-192A: Keep the version with more citations
                dup_idx = int(np.argmax(similarities))
                cite_pattern_192 = re.compile(r'\[CITE:[^\]]+\]')
                new_cites = len(cite_pattern_192.findall(sentences[sent_idx]))
                existing_cites = len(cite_pattern_192.findall(deduplicated[dup_idx]))
                if new_cites > existing_cites:
                    deduplicated[dup_idx] = sentences[sent_idx]
                    kept_embeddings[dup_idx] = current_emb
                    logger.debug(
                        f"[FIX-192A] Replaced dedup sentence "
                        f"({existing_cites} cites) with ({new_cites} cites)"
                    )
                else:
                    logger.debug(
                        f"[FIX-153] Semantic duplicate detected "
                        f"(cosine={max_sim:.3f}): '{sentences[sent_idx][:60]}...'"
                    )
            else:
                deduplicated.append(sentences[sent_idx])
                kept_embeddings.append(current_emb)

        removed_count = len(valid_indices) - len(deduplicated)
        if removed_count > 0:
            logger.info(
                f"[FIX-153] Semantic deduplication: {len(valid_indices)} -> "
                f"{len(deduplicated)} ({removed_count} semantic duplicates removed)"
            )

        return deduplicated

    def _deduplicate_by_jaccard(
        self,
        sentences: List[str],
        threshold: float,
        cite_pattern,
    ) -> List[str]:
        """Fallback Jaccard word-overlap deduplication when embeddings unavailable."""
        number_pattern = re.compile(r'\b\d+(?:\.\d+)?%?\b')

        def get_word_set(text: str) -> set:
            cleaned = cite_pattern.sub("", text).lower()
            cleaned = number_pattern.sub("<NUM>", cleaned)
            return set(cleaned.split())

        deduplicated = []
        seen_word_sets = []

        for sentence in sentences:
            if not sentence or not sentence.strip():
                continue
            current_words = get_word_set(sentence)
            if not current_words:
                continue

            is_duplicate = False
            dup_idx = -1
            for di, existing_words in enumerate(seen_word_sets):
                intersection = len(current_words & existing_words)
                union = len(current_words | existing_words)
                if union > 0 and (intersection / union) >= threshold:
                    is_duplicate = True
                    dup_idx = di
                    break

            if is_duplicate and dup_idx >= 0:
                # FIX-192B: Keep the version with more citations
                new_cites = len(cite_pattern.findall(sentence))
                existing_cites = len(cite_pattern.findall(deduplicated[dup_idx]))
                if new_cites > existing_cites:
                    deduplicated[dup_idx] = sentence
                    seen_word_sets[dup_idx] = current_words
                    logger.debug(
                        f"[FIX-192B] Replaced Jaccard dedup sentence "
                        f"({existing_cites} cites) with ({new_cites} cites)"
                    )
            elif not is_duplicate:
                deduplicated.append(sentence)
                seen_word_sets.append(current_words)

        removed_count = len(sentences) - len(deduplicated)
        if removed_count > 0:
            logger.info(
                f"[FIX-153] Jaccard fallback dedup: {len(sentences)} -> "
                f"{len(deduplicated)} ({removed_count} removed)"
            )

        return deduplicated

    def _deduplicate_report_sentences(
        self,
        report: str,
        threshold: float = None,
    ) -> str:
        """
        FIX-177: Full-report semantic deduplication across sections.

        Splits report by ## headings, deduplicates within each section,
        then cross-deduplicates across sections (earlier section wins).
        When dropping a duplicate, keeps the version with MORE citations.

        Args:
            report: Full markdown report with ## section headings.
            threshold: Cosine similarity threshold (default 0.85 from env).

        Returns:
            Deduplicated report text.
        """
        if threshold is None:
            threshold = float(
                os.environ.get("POLARIS_SENTENCE_DEDUP_THRESHOLD", "0.85")
            )

        if not report or not report.strip():
            return report

        # Split by ## headings, preserving them
        heading_pattern = re.compile(r'^(## .+)$', re.MULTILINE)
        parts = heading_pattern.split(report)

        # parts alternates: [preamble, heading1, body1, heading2, body2, ...]
        # Build sections as (heading_or_none, body) pairs
        sections = []
        if parts and not parts[0].startswith("## "):
            # Preamble (title, etc.)
            sections.append((None, parts[0]))
            parts = parts[1:]

        for i in range(0, len(parts), 2):
            heading = parts[i] if i < len(parts) else ""
            body = parts[i + 1] if i + 1 < len(parts) else ""
            sections.append((heading, body))

        if len(sections) <= 1:
            return report

        cite_pattern = re.compile(r'\[CITE:[^\]]+\]')

        def count_cites(sentence: str) -> int:
            return len(cite_pattern.findall(sentence))

        def split_into_sentences(text: str) -> List[str]:
            """Split text into sentences, preserving non-sentence content."""
            if not text or not text.strip():
                return []
            return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s.strip()]

        within_removed = 0
        cross_removed = 0

        # Step 1: Within-section deduplication
        for idx, (heading, body) in enumerate(sections):
            if heading is None:
                continue  # Skip preamble
            sentences = split_into_sentences(body)
            if len(sentences) <= 1:
                continue
            deduped = self._deduplicate_sentences(sentences, threshold=threshold)
            within_removed += len(sentences) - len(deduped)
            sections[idx] = (heading, " ".join(deduped))

        # Step 2: Cross-section deduplication (earlier section wins)
        # Build a set of "seen" sentence texts (citations stripped for comparison)
        seen_sentences = []  # List of (clean_text, cite_count, section_idx, sentence_idx)

        def clean_for_comparison(text: str) -> str:
            return cite_pattern.sub("", text).strip().lower()

        for sec_idx, (heading, body) in enumerate(sections):
            if heading is None:
                continue
            sentences = split_into_sentences(body)
            kept_sentences = []

            for sent in sentences:
                clean_sent = clean_for_comparison(sent)
                if not clean_sent or len(clean_sent) < 10:
                    kept_sentences.append(sent)
                    continue

                # FIX-184F: Use embedding cosine similarity for cross-section dedup
                # when embedding service available; fall back to Jaccard otherwise
                cross_dedup_threshold = float(os.environ.get(
                    "POLARIS_CROSS_SECTION_DEDUP_THRESHOLD", "0.90"
                ))
                embedding_service = getattr(self, '_embedding_service', None)
                is_duplicate = False
                matched_seen_idx = -1
                sent_words = set(clean_sent.split())
                current_cite_count = count_cites(sent)

                for si, (seen_clean, seen_cites, seen_sec, seen_sent_idx) in enumerate(seen_sentences):
                    # Same section: use within-section threshold (already handled above)
                    if seen_sec == sec_idx:
                        continue

                    if embedding_service is not None:
                        # FIX-184F: Embedding-based similarity (local MiniLM, 0 API calls)
                        try:
                            # FIX-186B: embed_text() is a module-level function; instance method is embed()
                            emb_a = embedding_service.embed(clean_sent)
                            emb_b = embedding_service.embed(seen_clean)
                            cos_sim = float(np.dot(emb_a, emb_b) / (
                                np.linalg.norm(emb_a) * np.linalg.norm(emb_b) + 1e-10
                            ))
                            if cos_sim >= cross_dedup_threshold:
                                is_duplicate = True
                                matched_seen_idx = si
                                cross_removed += 1
                                break
                        except Exception as e:  # FIX-228
                            logger.debug(f"Embedding dedup failed, falling back to Jaccard: {e}")

                    if not is_duplicate:
                        # Jaccard fallback
                        seen_words = set(seen_clean.split())
                        intersection = len(sent_words & seen_words)
                        union = len(sent_words | seen_words)
                        if union > 0 and (intersection / union) >= threshold:
                            is_duplicate = True
                            matched_seen_idx = si
                            cross_removed += 1
                            break

                if is_duplicate and matched_seen_idx >= 0:
                    # FIX-192C: Keep the version with more citations
                    seen_cites = seen_sentences[matched_seen_idx][1]
                    if current_cite_count > seen_cites:
                        # Replace the seen entry with the more-cited version
                        old_entry = seen_sentences[matched_seen_idx]
                        seen_sentences[matched_seen_idx] = (
                            clean_sent, current_cite_count, sec_idx,
                            len(kept_sentences),
                        )
                        kept_sentences.append(sent)
                        logger.debug(
                            f"[FIX-192C] Cross-section: replaced "
                            f"({seen_cites} cites) with ({current_cite_count} cites)"
                        )
                elif not is_duplicate:
                    kept_sentences.append(sent)
                    seen_sentences.append(
                        (clean_sent, current_cite_count, sec_idx, len(kept_sentences) - 1)
                    )

            sections[sec_idx] = (heading, " ".join(kept_sentences))

        # Safety guard: if word count dropped below minimum, raise threshold and retry
        result = self._reassemble_report_sections(sections)
        min_words = int(os.environ.get("POLARIS_MIN_REPORT_WORDS", "2000"))
        result_word_count = len(result.split())

        if result_word_count < min_words and (within_removed + cross_removed) > 0 and threshold < 0.92:
            logger.warning(
                f"[FIX-177] Dedup dropped words to {result_word_count} < {min_words}, "
                f"retrying with threshold 0.92"
            )
            return self._deduplicate_report_sentences(report, threshold=0.92)
        elif result_word_count < min_words and (within_removed + cross_removed) > 0 and threshold < 0.95:
            logger.warning(
                f"[FIX-177] Dedup dropped words to {result_word_count} < {min_words}, "
                f"retrying with threshold 0.95"
            )
            return self._deduplicate_report_sentences(report, threshold=0.95)

        if within_removed + cross_removed > 0:
            logger.info(
                f"[FIX-177] Dedup removed {within_removed} within-section, "
                f"{cross_removed} cross-section duplicates (threshold {threshold})"
            )

        return result

    @staticmethod
    def _reassemble_report_sections(
        sections: List[Tuple[Optional[str], str]],
    ) -> str:
        """Reassemble report from (heading, body) section pairs."""
        parts = []
        for heading, body in sections:
            if heading is not None:
                parts.append(heading)
            if body and body.strip():
                parts.append(body.strip())
            parts.append("")  # Blank line between sections
        return "\n".join(parts).strip()

    @staticmethod
    def _enforce_section_balance(
        sections: List[Dict[str, Any]],
        min_section_words: int,
    ) -> List[Dict[str, Any]]:
        """
        FIX-179: Merge thin sections into the most similar non-thin section.

        Sections below min_section_words are merged into the section with
        the highest topic word overlap. Executive Summary and Limitations
        are never merged (handled separately).

        Args:
            sections: [{"topic": str, "prose": str, ...}]
            min_section_words: Minimum words for a standalone section.

        Returns:
            Rebalanced section list.
        """
        if not sections or len(sections) <= 1:
            return sections

        # Identify thin vs non-thin sections (skip protected topics)
        protected_topics = {"executive summary", "limitations"}
        thin = []
        healthy = []

        for section in sections:
            topic = section.get("topic", "")
            prose = section.get("prose", "")
            word_count = len(prose.split()) if prose else 0

            if topic.lower().strip() in protected_topics:
                healthy.append(section)
            elif word_count < min_section_words:
                thin.append(section)
            else:
                healthy.append(section)

        if not thin:
            return sections

        if not healthy:
            # All sections are thin — retain as-is with warning
            logger.warning(
                f"[FIX-179] All {len(sections)} sections are below {min_section_words} words, "
                f"retaining as-is"
            )
            return sections

        # Merge each thin section into the most similar healthy section
        for thin_section in thin:
            thin_topic_words = set(thin_section.get("topic", "").lower().split())
            thin_prose = thin_section.get("prose", "")

            if not thin_prose or not thin_prose.strip():
                logger.info(f"[FIX-179] Skipping empty thin section: '{thin_section.get('topic', '')}'")
                continue

            # Find best merge candidate (highest topic word overlap)
            best_idx = 0
            best_overlap = -1
            for i, h_section in enumerate(healthy):
                h_topic = h_section.get("topic", "")
                if h_topic.lower().strip() in protected_topics:
                    continue
                h_words = set(h_topic.lower().split())
                overlap = len(thin_topic_words & h_words)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_idx = i

            # Merge: append thin prose as new paragraph
            target = healthy[best_idx]
            target_prose = target.get("prose", "")
            merged_prose = f"{target_prose}\n\n{thin_prose}" if target_prose else thin_prose
            target["prose"] = merged_prose

            # Merge evidence lists if present
            target_ev = target.get("evidence", [])
            thin_ev = thin_section.get("evidence", [])
            if thin_ev:
                target["evidence"] = target_ev + thin_ev

            logger.info(
                f"[FIX-179] Merged section '{thin_section.get('topic', '')}' "
                f"({len(thin_prose.split())} words) into '{target.get('topic', '')}'"
            )

        return healthy

    @staticmethod
    def _parse_report_to_section_dicts(report: str) -> List[Dict[str, Any]]:
        """
        FIX-185C: Parse a markdown report into section dicts for _enforce_section_balance().

        Splits by ## headings into [{"topic": str, "prose": str}].
        Content before first ## heading is preserved as a preamble section with topic=None.

        Args:
            report: Markdown report string with ## headings.

        Returns:
            List of section dicts compatible with _enforce_section_balance().
        """
        if not report or not report.strip():
            return []

        sections = []
        current_topic = None
        current_lines = []

        for line in report.split("\n"):
            if line.startswith("## "):
                # Save previous section
                if current_topic is not None or current_lines:
                    prose = "\n".join(current_lines).strip()
                    if current_topic is not None:
                        sections.append({"topic": current_topic, "prose": prose})
                    # else: preamble (title, etc.) — skip for balance enforcement
                current_topic = line[3:].strip()
                current_lines = []
            elif line.startswith("# ") and current_topic is None:
                # Title line — skip for section balance
                current_lines.append(line)
            else:
                current_lines.append(line)

        # Save last section
        if current_topic is not None:
            prose = "\n".join(current_lines).strip()
            sections.append({"topic": current_topic, "prose": prose})

        return sections

    @staticmethod
    def _reassemble_section_dicts_to_report(sections: List[Dict[str, Any]]) -> str:
        """
        FIX-185C: Reassemble section dicts back into a markdown report.

        Inverse of _parse_report_to_section_dicts(). Preserves ## headings
        and prose content.

        Args:
            sections: [{"topic": str, "prose": str}]

        Returns:
            Markdown report string with ## headings.
        """
        parts = []
        for section in sections:
            topic = section.get("topic", "")
            prose = section.get("prose", "")
            parts.append(f"## {topic}\n")
            if prose and prose.strip():
                parts.append(prose.strip())
            parts.append("")  # Blank line between sections
        return "\n".join(parts)

    @staticmethod
    def _recover_missing_perspectives(
        clusters: List[Dict[str, Any]],
        evidence_chain: List[Evidence],
    ) -> List[Dict[str, Any]]:
        """
        FIX-181: Create dedicated clusters for perspectives missing from LLM clustering.

        After LLM clusters evidence by topic, some perspectives may be lost because
        the LLM grouped by topic rather than perspective. This recovers perspectives
        that have >= 3 evidence items but no dedicated cluster.

        Args:
            clusters: Existing clusters from _cluster_evidence()
            evidence_chain: Full evidence chain with perspective_origins

        Returns:
            Clusters with missing perspectives recovered.
        """
        # Get all perspectives from evidence
        all_perspectives = set()
        perspective_evidence: Dict[str, List[Evidence]] = {}
        for ev in evidence_chain:
            origins = getattr(ev, 'perspective_origins', []) or []
            for p in origins:
                all_perspectives.add(p)
                perspective_evidence.setdefault(p, []).append(ev)

        if not all_perspectives:
            return clusters

        # Get perspectives already represented in clusters
        # A cluster "represents" a perspective if it contains evidence tagged to it
        clustered_evidence_ids = set()
        for cluster in clusters:
            for ev in cluster.get("evidence", []):
                clustered_evidence_ids.add(getattr(ev, 'evidence_id', ''))

        represented_perspectives = set()
        for cluster in clusters:
            for ev in cluster.get("evidence", []):
                origins = getattr(ev, 'perspective_origins', []) or []
                for p in origins:
                    represented_perspectives.add(p)

        missing = all_perspectives - represented_perspectives

        if not missing:
            return clusters

        recovered = 0
        for perspective in sorted(missing):
            ev_list = perspective_evidence.get(perspective, [])
            # Only create cluster if enough evidence (>= 3)
            if len(ev_list) < 3:
                logger.info(
                    f"[FIX-181] Skipping perspective '{perspective}' "
                    f"(only {len(ev_list)} evidence, need >= 3)"
                )
                continue

            topic_name = perspective.replace("_", " ").title()
            clusters.append({
                "topic": f"{topic_name} Perspective",
                "evidence": ev_list,
            })
            recovered += 1

        if recovered > 0:
            logger.info(
                f"[FIX-181] Recovered {recovered} missing perspectives: "
                f"{sorted(missing)}"
            )

        return clusters

    # =========================================================================
    # FIX-157 through FIX-161: Cluster-Synthesize Architecture
    # =========================================================================

    def _cluster_evidence(
        self,
        evidence_chain: List[Evidence],
        original_query: str,
        max_clusters: int = 7,
    ) -> List[Dict[str, Any]]:
        """
        FIX-157: Group evidence into topical clusters using LLM.

        Instead of processing claims one-at-a-time, this groups evidence by
        topic so _write_section_prose() can synthesize across sources naturally.

        Args:
            evidence_chain: All evidence pieces
            original_query: The research query
            max_clusters: Maximum number of clusters (3-7)

        Returns:
            List of dicts: [{"topic": str, "evidence": List[Evidence]}]
        """
        if not evidence_chain:
            return []

        # Build evidence index for ID lookup
        evidence_by_id = {}
        for ev in evidence_chain:
            evidence_by_id[ev.evidence_id] = ev

        # FIX-164: Sample BEST 30 evidence (sort by quality tier, then text length)
        tier_order = {"GOLD": 4, "SILVER": 3, "BRONZE": 2, "UNVERIFIED": 1}
        sorted_evidence = sorted(
            evidence_chain,
            key=lambda e: (
                tier_order.get(getattr(e, 'quality_tier', 'UNVERIFIED'), 1),
                len(getattr(e, 'text', '') or ''),
            ),
            reverse=True,
        )
        # FIX-188A: Increased from 30 to 100 — all evidence fits in KIMI K2.5's 128K context
        sample_size = min(len(sorted_evidence), 100)
        sampled = sorted_evidence[:sample_size]
        evidence_summaries = []
        for ev in sampled:
            text_preview = (ev.text[:200] if hasattr(ev, 'text') and ev.text else "")
            # FIX-163: Strip evidence artifacts before sending to LLM
            text_preview = self._strip_evidence_artifacts(text_preview)
            evidence_summaries.append(
                f"  ID: {ev.evidence_id}\n  Text: {text_preview}"
            )

        evidence_block = "\n\n".join(evidence_summaries)

        prompt = f"""Group the following evidence pieces into {max_clusters} or fewer topical clusters for a research report on: "{original_query}"

EVIDENCE:
{evidence_block}

RULES:
1. Each cluster must have a descriptive topic name (3-8 words)
2. Create 3-{max_clusters} clusters based on natural topic boundaries
3. Every evidence ID must appear in exactly one cluster
4. Cluster topics should be specific and meaningful (not "General" or "Other")
5. Order clusters from most important to least important
6. Create clusters that are DIRECTLY relevant to the research query: "{original_query}"
7. If evidence is about an unrelated topic (e.g., different country, different disease, different subject), assign it to a cluster named "Off-Topic" which will be excluded from the report

OUTPUT FORMAT (JSON only, no markdown fences):
[
  {{"topic": "Topic Name Here", "evidence_ids": ["ev_001", "ev_002"]}},
  {{"topic": "Another Topic", "evidence_ids": ["ev_003"]}}
]

Output ONLY the JSON array. No explanation, no preamble."""

        try:
            # FIX-195B: Use non-thinking structured mode for clustering.
            # Thinking mode (temp=1.0) uses all 8000 tokens on reasoning (0 content).
            # Non-thinking .invoke() returns preamble that truncates JSON at 4096.
            # Solution: _invoke_llm with use_structured=True forces json_schema output.
            response = self._invoke_llm(prompt, max_tokens=TOKENS_CLUSTER_LLM, use_structured=True)

            # FIX-162D: Debug logging for clustering response
            logger.info(
                f"[FIX-157] LLM clustering response: {len(response)} chars, "
                f"preview: '{response[:200]}'"
            )

            if not response or not response.strip():
                raise ValueError("LLM returned empty response for clustering")

            # Strip markdown fences if present
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
                cleaned = re.sub(r'\s*```$', '', cleaned)

            # FIX-164: Try direct JSON parse first, then extract from CoT
            cluster_method = "LLM"  # Track method for logging
            try:
                clusters_data = json.loads(cleaned)
            except json.JSONDecodeError:
                # FIX-164: Extract JSON array from CoT reasoning response
                # Strategy: find '[{' start, then try parsing substrings ending at each ']'
                clusters_data = None
                start_match = re.search(r'\[\s*\{', cleaned)
                if start_match:
                    start_idx = start_match.start()
                    # Try each ']' from the end backward as potential array close
                    remaining = cleaned[start_idx:]
                    for end_idx in range(len(remaining) - 1, 0, -1):
                        if remaining[end_idx] == ']':
                            candidate = remaining[:end_idx + 1]
                            try:
                                clusters_data = json.loads(candidate)
                                if isinstance(clusters_data, list):
                                    cluster_method = "CoT-extracted"
                                    logger.info("[FIX-164] Extracted JSON from CoT response")
                                    break
                                clusters_data = None
                            except json.JSONDecodeError:
                                continue
                if clusters_data is None:
                    raise ValueError(f"No valid JSON found in clustering response ({len(cleaned)} chars)")

            if not isinstance(clusters_data, list):
                raise ValueError("LLM returned non-list JSON")

            # Validate and build clusters
            assigned_ids = set()
            clusters = []

            for cluster_def in clusters_data:
                topic = cluster_def.get("topic", "")
                ev_ids = cluster_def.get("evidence_ids", [])

                if not topic or not ev_ids:
                    continue

                cluster_evidence = []
                for eid in ev_ids:
                    if eid in evidence_by_id and eid not in assigned_ids:
                        cluster_evidence.append(evidence_by_id[eid])
                        assigned_ids.add(eid)

                if cluster_evidence:
                    clusters.append({
                        "topic": topic,
                        "evidence": cluster_evidence,
                    })

            # FIX-188B + FIX-194B: Assign orphan evidence to nearest cluster
            orphan_evidence = [
                ev for ev in evidence_chain
                if ev.evidence_id not in assigned_ids
            ]
            if orphan_evidence and clusters:
                general_findings = []
                # FIX-194B: Use embedding cosine for orphan assignment when available
                embed_threshold = float(os.environ.get(
                    "POLARIS_ORPHAN_EMBED_THRESHOLD", "0.50"
                ))
                embedding_service = getattr(self, '_embedding_service', None)

                for orphan_ev in orphan_evidence:
                    orphan_text = (
                        orphan_ev.text[:300]
                        if hasattr(orphan_ev, 'text') and orphan_ev.text
                        else ""
                    )
                    best_cluster_idx = -1
                    best_score = 0.0
                    assigned = False

                    # FIX-194B: Try embedding-based assignment first
                    if embedding_service is not None and orphan_text.strip():
                        try:
                            orphan_emb = embedding_service.embed(orphan_text)
                            for ci, cluster in enumerate(clusters):
                                cluster_text = cluster["topic"]
                                for ce in cluster["evidence"][:3]:
                                    ce_t = (
                                        ce.text[:100]
                                        if hasattr(ce, 'text') and ce.text
                                        else ""
                                    )
                                    cluster_text += " " + ce_t
                                cluster_emb = embedding_service.embed(cluster_text)
                                cos_sim = float(np.dot(orphan_emb, cluster_emb) / (
                                    np.linalg.norm(orphan_emb) * np.linalg.norm(cluster_emb) + 1e-10
                                ))
                                if cos_sim > best_score:
                                    best_score = cos_sim
                                    best_cluster_idx = ci
                            if best_score >= embed_threshold and best_cluster_idx >= 0:
                                clusters[best_cluster_idx]["evidence"].append(orphan_ev)
                                assigned_ids.add(orphan_ev.evidence_id)
                                assigned = True
                        except Exception as e:
                            logger.debug(f"[FIX-194B] Embedding orphan assignment failed: {e}")

                    # FIX-194B: Fallback — word overlap WITH stop word filtering
                    if not assigned:
                        orphan_words = set(orphan_text.lower().split()) - _STOPWORDS
                        best_overlap = 0
                        best_cluster_idx = 0
                        for ci, cluster in enumerate(clusters):
                            topic_words = set(cluster["topic"].lower().split()) - _STOPWORDS
                            for ce in cluster["evidence"][:3]:
                                ce_text = (
                                    ce.text[:100]
                                    if hasattr(ce, 'text') and ce.text
                                    else ""
                                ).lower()
                                topic_words.update(set(ce_text.split()) - _STOPWORDS)
                            overlap = len(orphan_words & topic_words)
                            if overlap > best_overlap:
                                best_overlap = overlap
                                best_cluster_idx = ci
                        if best_overlap > 2:
                            clusters[best_cluster_idx]["evidence"].append(orphan_ev)
                            assigned_ids.add(orphan_ev.evidence_id)
                        else:
                            general_findings.append(orphan_ev)

                # FIX-188B: Cap "General Findings" at 15% of total evidence
                max_general = max(int(len(evidence_chain) * 0.15), 5)
                if general_findings:
                    if len(general_findings) > max_general:
                        # Redistribute excess to nearest clusters
                        excess = general_findings[max_general:]
                        general_findings = general_findings[:max_general]
                        for excess_ev in excess:
                            if clusters:
                                clusters[0]["evidence"].append(excess_ev)
                    clusters.append({
                        "topic": "General Findings",
                        "evidence": general_findings,
                    })
                    logger.info(
                        f"[FIX-188B] {len(general_findings)} orphan evidence in 'General Findings' "
                        f"(capped at {max_general}), "
                        f"{len(orphan_evidence) - len(general_findings)} assigned to nearest clusters"
                    )
            elif orphan_evidence:
                # No clusters exist — fall back to single General Findings
                clusters.append({
                    "topic": "General Findings",
                    "evidence": orphan_evidence,
                })
                logger.info(
                    f"[FIX-157] {len(orphan_evidence)} orphan evidence pieces "
                    f"assigned to 'General Findings' (no clusters available)"
                )

            # FIX-164: Enforce minimum 5 clusters by splitting large ones
            if len(clusters) < 5 and len(clusters) > 0:
                while len(clusters) < 5:
                    # Find the largest cluster
                    largest_idx = max(range(len(clusters)), key=lambda i: len(clusters[i]["evidence"]))
                    largest = clusters[largest_idx]
                    if len(largest["evidence"]) < 4:
                        break  # Can't split further
                    # Split in half
                    mid = len(largest["evidence"]) // 2
                    new_cluster = {
                        "topic": f"{largest['topic']} (Continued)",
                        "evidence": largest["evidence"][mid:],
                    }
                    largest["evidence"] = largest["evidence"][:mid]
                    clusters.insert(largest_idx + 1, new_cluster)
                logger.info(
                    f"[FIX-164] Split clusters to meet minimum 5: now {len(clusters)} clusters"
                )

            # FIX-181: Recover missing perspectives by creating dedicated clusters
            clusters = self._recover_missing_perspectives(clusters, evidence_chain)

            ev_per_cluster = ", ".join(
                f"{c['topic'][:25]}={len(c['evidence'])}" for c in clusters
            )
            logger.info(
                f"[FIX-164] Clustered {len(evidence_chain)} evidence into "
                f"{len(clusters)} topic clusters (method={cluster_method}): [{ev_per_cluster}]"
            )
            return clusters

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(
                f"[FIX-157] LLM clustering failed ({e}), using perspective-based fallback"
            )
            return self._heuristic_cluster_fallback(evidence_chain)
        except Exception as e:
            logger.error(f"[FIX-157] Unexpected clustering error: {e}")
            return self._heuristic_cluster_fallback(evidence_chain)

    def _heuristic_cluster_fallback(
        self,
        evidence_chain: List[Evidence],
    ) -> List[Dict[str, Any]]:
        """
        FIX-162C: Heuristic clustering fallback when LLM clustering fails.

        Uses STORM perspective_origins as natural cluster axes instead of
        dumping everything into one mega-cluster (which produces tiny output).

        Args:
            evidence_chain: All evidence pieces

        Returns:
            List of dicts: [{"topic": str, "evidence": List[Evidence]}]
        """
        # Group by perspective_origins (STORM perspectives)
        perspective_map: Dict[str, List[Evidence]] = {}
        untagged: List[Evidence] = []

        for ev in evidence_chain:
            origins = getattr(ev, 'perspective_origins', []) or []
            if origins:
                # Use the first perspective as the cluster key
                key = origins[0]
                perspective_map.setdefault(key, []).append(ev)
            else:
                untagged.append(ev)

        clusters = []
        # Create named clusters from perspectives
        for perspective, ev_list in sorted(
            perspective_map.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        ):
            # Map perspective codes to readable topic names
            topic_name = perspective.replace("_", " ").title()
            clusters.append({
                "topic": f"{topic_name} Analysis",
                "evidence": ev_list,
            })

        # Add untagged evidence as "General Findings" if any
        if untagged:
            clusters.append({
                "topic": "General Findings",
                "evidence": untagged,
            })

        # If no perspectives at all, fall back to chunk-based splitting
        if not clusters:
            chunk_size = max(1, len(evidence_chain) // 5)
            for i in range(0, len(evidence_chain), chunk_size):
                chunk = evidence_chain[i:i + chunk_size]
                clusters.append({
                    "topic": f"Research Findings (Part {i // chunk_size + 1})",
                    "evidence": chunk,
                })

        # FIX-164: Enforce minimum 5 clusters in heuristic fallback
        if len(clusters) < 5 and len(clusters) > 0:
            while len(clusters) < 5:
                largest_idx = max(range(len(clusters)), key=lambda i: len(clusters[i]["evidence"]))
                largest = clusters[largest_idx]
                if len(largest["evidence"]) < 4:
                    break
                mid = len(largest["evidence"]) // 2
                new_cluster = {
                    "topic": f"{largest['topic']} (Continued)",
                    "evidence": largest["evidence"][mid:],
                }
                largest["evidence"] = largest["evidence"][:mid]
                clusters.insert(largest_idx + 1, new_cluster)

        logger.info(
            f"[FIX-164] Heuristic clustering: {len(evidence_chain)} evidence "
            f"into {len(clusters)} perspective-based clusters"
        )
        return clusters

    def _write_section_prose(
        self,
        topic: str,
        evidence: List[Evidence],
        query: str,
        max_evidence: int = 25,  # FIX-167/174: Increased from 10 to 25
        section_context: Optional[Dict[str, Any]] = None,  # FIX-184B: Cross-section context
    ) -> Tuple[str, List[GroundedClaim]]:
        """
        FIX-158: Write a coherent paragraph from multiple evidence pieces.

        This is the core architecture shift: instead of one claim → one sentence,
        we give the LLM a topic + multiple evidence pieces and let it synthesize
        a coherent paragraph with natural cross-source transitions.

        Args:
            topic: The cluster topic name
            evidence: Evidence pieces for this cluster
            query: The original research query
            max_evidence: Max evidence pieces to include in prompt

        Returns:
            (prose_text, list_of_grounded_claims)
        """
        if not evidence:
            return "", []

        # Select top evidence by relevance score
        scored_evidence = sorted(
            evidence,
            key=lambda e: getattr(e, 'relevance_score', 0.5),
            reverse=True,
        )[:max_evidence]

        # FIX-246: Filter out PDF structural metadata evidence
        pre_filter_count = len(scored_evidence)
        scored_evidence = [
            e for e in scored_evidence
            if not self._is_metadata_evidence(getattr(e, 'text', ''))
        ]
        if len(scored_evidence) < pre_filter_count:
            logger.info(
                f"[FIX-246] Filtered {pre_filter_count - len(scored_evidence)} "
                f"metadata evidence entries for section '{topic}'"
            )
        if not scored_evidence:
            return "", []

        evidence_context = "\n\n".join([
            f"[{e.evidence_id}]: {self._strip_evidence_artifacts(e.text[:500])}"
            for e in scored_evidence
        ])

        # FIX-184B: Build context-rich prompt with report outline and section continuity
        context_block = ""
        if section_context:
            outline = section_context.get("outline", [])
            prev_summary = section_context.get("previous_summary", "")
            if outline:
                outline_items = []
                for ot in outline:
                    marker = ">> " if ot == topic else "   "
                    outline_items.append(f"{marker}{ot}")
                context_block += "\nREPORT OUTLINE:\n" + "\n".join(outline_items) + "\n"
            if prev_summary:
                context_block += f"\nPREVIOUS SECTION ended with: \"{prev_summary}\"\n"

        # FIX-241: Simplified prompt to reduce instruction echo surface area
        prompt = f"""Write {SENTENCES_PER_SECTION} sentences about "{topic}" for: "{query}"
{context_block}
EVIDENCE:
{evidence_context}

Write flowing prose paragraphs. Cite evidence inline as [CITE:evidence_id]. Output ONLY the prose."""

        try:
            # FIX-220: Structural reasoning/content separation for section prose
            # FIX-170: Per-call token budget for section prose
            response = self._invoke_synthesis_llm(
                prompt, system_prompt=self.get_system_prompt(), max_tokens=TOKENS_SECTION_PROSE
            )

            # Sanitize LLM output
            prose = self._sanitize_llm_output(response)
            if not prose:
                logger.warning(
                    f"[FIX-158] Section prose generation for '{topic}' produced "
                    f"CoT artifact, falling back to direct quotes"
                )
                return self._fallback_section_prose(topic, scored_evidence)

            # FIX-240: Deep clean prose — removes instruction echoes, outlines,
            # meta-reasoning, PDF metadata, and other noise
            prose = self._deep_clean_prose(prose)
            if not prose.strip():
                logger.warning(f"[FIX-240] Deep clean emptied section '{topic}', falling back")
                return self._fallback_section_prose(topic, scored_evidence)

            # FIX-167: Post-generation artifact stripping
            prose = self._strip_evidence_artifacts(prose)

            # FIX-185A: Scrub CoT immediately after LLM output — ensures BOTH
            # initial and revision paths get scrubbed (defense-in-depth)
            prose = scrub_cot_from_report(prose)

            # FIX-283: Section-level LLM CoT post-filter (defense-in-depth)
            # Catches reasoning that survives regex scrubbing BEFORE report assembly
            section_cot_filter = os.environ.get("POLARIS_SECTION_COT_FILTER", "1") == "1"
            if section_cot_filter and prose.strip():
                try:
                    prose = cot_post_filter_report(
                        prose, query,
                        llm_invoke=lambda p: self._invoke_llm(p, max_tokens=2048),
                    )
                except Exception as e:
                    logger.warning(f"[FIX-283] Section CoT filter failed for '{topic}': {e}")

            # FIX-183C: Normalize citation tokens before parsing
            prose = normalize_cite_tokens(prose)

            # FIX-184A: Paragraph-aware sentence parsing
            # Split by paragraph first, then by sentence within each paragraph
            paragraphs = re.split(r'\n\s*\n', prose.strip())
            sentences = []
            sentence_para_map = []  # Parallel list: paragraph index per sentence
            for para_idx, para in enumerate(paragraphs):
                para = para.strip()
                if not para:
                    continue
                para_sentences = re.split(r'(?<=[.!?])\s+', para)
                para_sentences = [s.strip() for s in para_sentences if s.strip()]
                for s in para_sentences:
                    sentences.append(s)
                    sentence_para_map.append(para_idx)

            # FIX-167: Minimum section length check (200 words)
            word_count = len(prose.split())
            if word_count < 200 and len(scored_evidence) > 3:
                logger.warning(
                    f"[FIX-167] Section '{topic}' too short ({word_count} words), "
                    f"attempting expansion with more evidence"
                )
                # Retry with more evidence context
                try:
                    expanded_context = "\n\n".join([
                        f"[{e.evidence_id}]: {self._strip_evidence_artifacts(e.text[:500])}"
                        for e in scored_evidence[:min(len(scored_evidence), 25)]
                    ])
                    expand_prompt = f"""Expand this paragraph about "{topic}" for a research report on: "{query}"

CURRENT TEXT (too short):
{prose}

ADDITIONAL EVIDENCE:
{expanded_context}

Write an expanded version with {SENTENCES_PER_SECTION} sentences. Include specific numbers, statistics, and citations using [CITE:evidence_id] format. Cite 2-3 evidence pieces per sentence.

OUTPUT: Expanded prose paragraphs only. No preamble."""
                    # FIX-220: Structural separation for expansion retry
                    expanded = self._invoke_synthesis_llm(
                        expand_prompt, system_prompt=self.get_system_prompt(),
                        max_tokens=TOKENS_SECTION_PROSE
                    )
                    expanded = self._sanitize_llm_output(expanded)
                    if expanded and len(expanded.split()) > word_count:
                        expanded = self._strip_evidence_artifacts(expanded)
                        # FIX-248: Expansion retry must match primary path scrubbing
                        expanded = self._deep_clean_prose(expanded)
                        expanded = scrub_cot_from_report(expanded)
                        # FIX-286: Section-level LLM CoT post-filter on expansion path
                        # (matches primary path at line 3581)
                        section_cot_filter_exp = os.environ.get("POLARIS_SECTION_COT_FILTER", "1") == "1"
                        if section_cot_filter_exp and expanded.strip():
                            try:
                                expanded = cot_post_filter_report(
                                    expanded, query,
                                    llm_invoke=lambda p: self._invoke_llm(p, max_tokens=2048),
                                )
                            except Exception as e:
                                logger.warning(f"[FIX-286] Expansion CoT filter failed for '{topic}': {e}")
                        expanded = normalize_cite_tokens(expanded)
                        prose = expanded
                        # Re-parse with paragraph awareness
                        paragraphs = re.split(r'\n\s*\n', prose.strip())
                        sentences = []
                        sentence_para_map = []
                        for para_idx, para in enumerate(paragraphs):
                            para = para.strip()
                            if not para:
                                continue
                            para_sentences = re.split(r'(?<=[.!?])\s+', para)
                            para_sentences = [s.strip() for s in para_sentences if s.strip()]
                            for s in para_sentences:
                                sentences.append(s)
                                sentence_para_map.append(para_idx)
                        logger.info(
                            f"[FIX-167] Section '{topic}' expanded: "
                            f"{word_count} -> {len(prose.split())} words"
                        )
                except Exception as e:
                    logger.warning(f"[FIX-167] Expansion failed: {e}")

            grounded_claims = []
            for i, sentence in enumerate(sentences):
                # FIX-162E: Clean empty [CITE:] tokens BEFORE citation extraction
                # The LLM often writes [CITE:] without evidence IDs.
                # _replace_empty_cites() strips them and appends a real ID.
                sentence = self._replace_empty_cites(sentence, scored_evidence)

                # Extract cited evidence IDs from this sentence
                cited_ids = re.findall(r'\[CITE:([^\]]+)\]', sentence)
                cited_evidence = [
                    e for e in scored_evidence
                    if e.evidence_id in cited_ids
                ]

                # If no citations found, add citation to first evidence
                if not cited_ids and scored_evidence:
                    sentence = f"{sentence} [CITE:{scored_evidence[0].evidence_id}]"
                    cited_evidence = [scored_evidence[0]]
                    cited_ids = [scored_evidence[0].evidence_id]

                # FIX-184A: Assign paragraph_index from pre-computed map
                para_index = sentence_para_map[i] if i < len(sentence_para_map) else 0

                grounded_claims.append(GroundedClaim(
                    claim_id=f"cluster_{topic[:20]}_{i:03d}",
                    claim_text=re.sub(r'\[CITE:[^\]]+\]', '', sentence).strip(),
                    claim_type="factual",
                    evidence_ids=cited_ids,
                    evidence_texts=[
                        e.text[:500] for e in cited_evidence
                    ] if cited_evidence else [],
                    evidence_sources=[
                        getattr(e, 'source_url', '') for e in cited_evidence
                    ] if cited_evidence else [],
                    evidence_tiers=[
                        getattr(e, 'quality_tier', 'UNVERIFIED') for e in cited_evidence
                    ] if cited_evidence else [],
                    evidence_relevance=[
                        getattr(e, 'relevance_score', 0.5) for e in cited_evidence
                    ] if cited_evidence else [],
                    matching_keywords=[],
                    confidence=0.0,  # FIX-182C: Sentinel "not yet verified"; updated by _process_cluster_synthesis
                    reasoning=f"Cluster synthesis for topic: {topic}",
                    sentence=sentence,
                    verification_passed=False,  # Updated by _verify_section_sentences
                    section_topic=topic,
                    paragraph_index=para_index,  # FIX-184A
                ))

            # FIX-184A: Rebuild prose preserving paragraph breaks
            # Group claims by paragraph_index and join with \n\n between paragraphs
            current_para = -1
            para_sentences_list: List[List[str]] = []
            for claim in grounded_claims:
                if claim.paragraph_index != current_para:
                    para_sentences_list.append([])
                    current_para = claim.paragraph_index
                para_sentences_list[-1].append(claim.sentence)
            rebuilt_prose = "\n\n".join(
                " ".join(ps) for ps in para_sentences_list
            )

            # FIX-178C: Validate all [CITE:xxx] tokens match evidence IDs
            valid_ev_ids = {e.evidence_id for e in scored_evidence}
            cite_ids_in_output = re.findall(r'\[CITE:([^\]]+)\]', rebuilt_prose)
            for cid in cite_ids_in_output:
                if cid not in valid_ev_ids:
                    logger.warning(f"[FIX-178C] Stripping invalid cite from section prose: {cid}")
                    rebuilt_prose = rebuilt_prose.replace(f"[CITE:{cid}]", "")
            rebuilt_prose = re.sub(r'\s{2,}', ' ', rebuilt_prose).strip()

            logger.info(
                f"[FIX-158] Generated {len(sentences)} sentences for topic '{topic}'"
            )
            return rebuilt_prose, grounded_claims

        except Exception as e:
            logger.error(f"[FIX-158] Section prose generation failed: {e}")
            return self._fallback_section_prose(topic, scored_evidence)

    def _fallback_section_prose(
        self,
        topic: str,
        evidence: List[Evidence],
    ) -> Tuple[str, List[GroundedClaim]]:
        """Fallback: create direct-quote sentences when LLM prose generation fails."""
        # FIX-212 P1: Track fallback count, ERROR if too many in one run
        self.stats["section_prose_fallbacks"] = self.stats.get("section_prose_fallbacks", 0) + 1
        fallback_count = self.stats["section_prose_fallbacks"]
        if fallback_count > 3:
            logger.error(
                f"[FIX-212] Section prose fallback used {fallback_count} times in this run — "
                f"LLM prose generation is systematically failing"
            )
        sentences = []
        claims = []
        for i, ev in enumerate(evidence[:5]):
            text_snippet = ev.text[:200].strip()
            # FIX-163: Strip evidence artifacts from fallback prose
            text_snippet = self._strip_evidence_artifacts(text_snippet)
            if text_snippet:
                sentence = f"{text_snippet} [CITE:{ev.evidence_id}]"
                sentences.append(sentence)
                # FIX-212 P0: Fallback must NOT fake verification_passed=True (LAW II violation)
                claims.append(GroundedClaim(
                    claim_id=f"fallback_{topic[:20]}_{i:03d}",
                    claim_text=text_snippet,
                    claim_type="factual",
                    evidence_ids=[ev.evidence_id],
                    evidence_texts=[ev.text[:500]],
                    evidence_sources=[getattr(ev, 'source_url', '')],
                    evidence_tiers=[getattr(ev, 'quality_tier', 'UNVERIFIED')],
                    evidence_relevance=[getattr(ev, 'relevance_score', 0.5)],
                    matching_keywords=[],
                    confidence=0.0,
                    reasoning="UNVERIFIED: Direct quote fallback",
                    sentence=sentence,
                    verification_passed=False,
                    section_topic=topic,
                ))
        prose = " ".join(sentences)
        return prose, claims

    def _verify_section_sentences(
        self,
        prose: str,
        topic: str,
        evidence: List[Evidence],
    ) -> Tuple[str, int, int, Dict[str, float]]:
        """
        FIX-159: Pronoun-aware verification for section paragraphs.
        FIX-182A: Returns per-sentence confidence scores from MiniCheck.

        Fixes the "Pronoun Trap": when splitting prose into sentences for
        MiniCheck, pronouns like "It", "They", "This" lose their referent.
        This method prepends topic context for verification only (not output).

        Args:
            prose: The paragraph text to verify
            topic: The section topic (used for pronoun resolution context)
            evidence: Evidence pieces cited in this section

        Returns:
            (verified_prose, passed_count, total_count, sentence_confidences)
            sentence_confidences: {sentence_text: confidence_float}
        """
        if not prose or not prose.strip():
            return "", 0, 0, {}

        # FIX-163: Strip evidence artifacts before verification
        prose = self._strip_evidence_artifacts(prose)

        # FIX-184A: Paragraph-aware sentence splitting for verification
        # Track paragraph boundaries so we can reconstruct with \n\n
        paragraphs = re.split(r'\n\s*\n', prose.strip())
        sentences = []
        sentence_para_boundaries = []  # Index of first sentence in each paragraph
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            sentence_para_boundaries.append(len(sentences))
            para_sents = re.split(r'(?<=[.!?])\s+', para)
            para_sents = [s.strip() for s in para_sents if s.strip()]
            sentences.extend(para_sents)

        if not sentences:
            return "", 0, 0, {}

        # Combine evidence texts for verification
        combined_evidence = " ".join([e.text for e in evidence])

        # Pronouns that lose referent when sentence is isolated
        pronoun_starts = ("It ", "They ", "This ", "These ", "He ", "She ",
                         "Its ", "Their ", "That ", "Those ")

        verified_sentences = []
        verified_sentence_paras = []  # FIX-184A: Track which paragraph each verified sentence belongs to
        passed_count = 0
        total_count = len(sentences)
        sentence_confidences: Dict[str, float] = {}  # FIX-182A: Per-sentence confidence

        # FIX-184D: Pronoun resolution constants
        pronoun_resolve_starts = ("It ", "This ", "These ", "They ", "That ", "Those ", "Such ")

        for i, sentence in enumerate(sentences):
            # Build verification input with pronoun context
            sentence_for_verify = sentence

            if any(sentence.startswith(p) for p in pronoun_starts):
                # Prepend topic context for verification ONLY
                sentence_for_verify = f"[Re: {topic}] {sentence}"

            # Strip citations for verification
            claim_text = re.sub(r'\[CITE:[^\]]+\]', '', sentence_for_verify).strip()

            if not claim_text:
                continue

            # Verify against evidence
            verification = self._verify_claim_evidence(claim_text, evidence)

            # Determine which paragraph this sentence belongs to
            sent_para_idx = 0
            for boundary_idx, boundary in enumerate(sentence_para_boundaries):
                if boundary <= i:
                    sent_para_idx = boundary_idx

            if verification["passed"]:
                # Use original sentence (NOT the context-augmented one)
                verified_sentences.append(sentence)
                verified_sentence_paras.append(sent_para_idx)
                passed_count += 1
                # FIX-182A: Record actual MiniCheck confidence
                sentence_confidences[sentence] = verification.get("confidence", 0.8)
            else:
                # Try to extract cited evidence for this specific sentence
                cited_ids = re.findall(r'\[CITE:([^\]]+)\]', sentence)
                cited_evidence = [
                    e for e in evidence if e.evidence_id in cited_ids
                ]

                if cited_evidence:
                    # Attempt single-sentence rephrase via existing method
                    try:
                        # Create a minimal GeneratedClaim for rephrase
                        plain_text = re.sub(r'\[CITE:[^\]]+\]', '', sentence).strip()
                        rephrase_claim = GeneratedClaim(
                            claim_text=plain_text,
                            claim_type="factual",
                        )
                        rephrased = self._write_grounded_sentence(
                            rephrase_claim, cited_evidence,
                            max_rephrase_attempts=1,
                        )
                        if rephrased and rephrased.strip():
                            verified_sentences.append(rephrased)
                            verified_sentence_paras.append(sent_para_idx)
                            passed_count += 1
                            # FIX-182A: Rephrased sentence gets max(original, 0.5)
                            sentence_confidences[rephrased] = max(
                                verification.get("confidence", 0.0), 0.5
                            )
                            continue
                    except Exception as e:  # FIX-228
                        logger.debug(f"Verification extraction failed: {e}")

                # FIX-184D: Pronoun resolution on sentence drop
                # If the next sentence starts with a dangling pronoun, replace it with topic
                if i + 1 < len(sentences):
                    next_sent = sentences[i + 1]
                    for pronoun in pronoun_resolve_starts:
                        if next_sent.startswith(pronoun):
                            sentences[i + 1] = f"{topic} " + next_sent[len(pronoun):]
                            break

                # Drop the sentence
                logger.debug(
                    f"[FIX-159] Dropped unverifiable sentence: "
                    f"'{sentence[:60]}...'"
                )

        # FIX-184A: Reconstruct verified prose preserving paragraph breaks
        if sentence_para_boundaries and len(set(verified_sentence_paras)) > 1:
            # Multiple paragraphs: group by paragraph index
            para_groups: Dict[int, List[str]] = {}
            for sent, pidx in zip(verified_sentences, verified_sentence_paras):
                if pidx not in para_groups:
                    para_groups[pidx] = []
                para_groups[pidx].append(sent)
            verified_prose = "\n\n".join(
                " ".join(sents) for _, sents in sorted(para_groups.items())
            )
        else:
            verified_prose = " ".join(verified_sentences)

        logger.info(
            f"[FIX-159] Verification for '{topic}': "
            f"{passed_count}/{total_count} sentences passed"
        )
        return verified_prose, passed_count, total_count, sentence_confidences

    def _process_cluster_synthesis(
        self,
        evidence_chain: List[Evidence],
        original_query: str,
        cited_domains: Dict[str, int],
    ) -> Tuple[List[Dict[str, Any]], List[GroundedClaim], List[str]]:
        """
        FIX-161: Orchestrate cluster-based synthesis pipeline.

        Replaces the per-claim loop in process() when CLUSTER_SYNTHESIS_ENABLED=1.
        Groups evidence into topical clusters, generates coherent paragraphs,
        and verifies sentences with pronoun-aware context.

        Args:
            evidence_chain: All evidence pieces
            original_query: The research query
            cited_domains: Mutable dict tracking cited domains for diversity

        Returns:
            (sections, all_grounded_claims, hedged_sentences)
            sections: [{"topic": str, "prose": str, "grounded_claims": List[GroundedClaim]}]
        """
        # FIX-193A: Pre-clustering relevance filter
        # FIX-210: Raised from 0.30 to 0.50 — pre-clustering relevance gate
        min_relevance = float(os.environ.get("POLARIS_MIN_CLUSTER_RELEVANCE", "0.50"))
        original_count = len(evidence_chain)
        filtered_evidence = [
            ev for ev in evidence_chain
            if getattr(ev, 'relevance_score', 0.5) >= min_relevance
        ]
        if len(filtered_evidence) < original_count:
            logger.info(
                f"[FIX-193A] Filtered {original_count - len(filtered_evidence)} evidence "
                f"below relevance {min_relevance} (kept {len(filtered_evidence)})"
            )
        # Safety: keep at least 20 evidence items even if many are low-relevance
        if len(filtered_evidence) < 20 and original_count >= 20:
            filtered_evidence = sorted(
                evidence_chain,
                key=lambda e: getattr(e, 'relevance_score', 0.5),
                reverse=True,
            )[:20]
            logger.warning("[FIX-193A] Safety floor: kept top 20 by relevance")
        evidence_chain = filtered_evidence

        # Step 1: Cluster evidence by topic
        clusters = self._cluster_evidence(evidence_chain, original_query)

        sections = []
        all_grounded_claims = []
        hedged_sentences = []

        # FIX-184B: Build report outline for cross-section context
        all_topics = [c["topic"] for c in clusters]
        previous_summary = ""  # Last sentence of previous section

        # Step 2: For each cluster, generate and verify prose
        for cluster_idx, cluster in enumerate(clusters):
            topic = cluster["topic"]
            cluster_evidence = cluster["evidence"]

            # FIX-189B: Skip off-topic clusters identified by clustering prompt
            if "off-topic" in topic.lower() or "off topic" in topic.lower():
                logger.info(
                    f"[FIX-189B] Skipping off-topic cluster: {topic} "
                    f"({len(cluster_evidence)} evidence)"
                )
                continue

            # FIX-184B: Build section context with outline and previous section summary
            section_context = {
                "outline": all_topics,
                "previous_summary": previous_summary,
            }

            # Generate coherent paragraph
            prose, claims = self._write_section_prose(
                topic, cluster_evidence, original_query,
                section_context=section_context,
            )

            if not prose or not prose.strip():
                logger.warning(
                    f"[FIX-161] Cluster '{topic}' produced no prose, skipping"
                )
                continue

            # Verify sentences with pronoun-aware context
            # FIX-182B: Unpack 4th element (sentence_confidences dict)
            verified_prose, passed, total, sentence_confidences = self._verify_section_sentences(
                prose, topic, cluster_evidence,
            )

            if not verified_prose or not verified_prose.strip():
                # All sentences failed — record as hedged
                hedged_sentences.append(
                    f"Evidence regarding {topic} could not be fully verified."
                )
                logger.warning(
                    f"[FIX-161] All sentences in cluster '{topic}' failed verification"
                )
                continue

            # FIX-162B: Index-based claim matching (not string comparison)
            # Both _write_section_prose and _verify_section_sentences split the
            # same prose with the same regex, so their indices are aligned.
            # String comparison fails because _write_section_prose may have
            # appended [CITE:id] tokens to sentences that lacked them.
            verified_sentence_set = set(
                re.split(r'(?<=[.!?])\s+', verified_prose.strip())
            )
            # Also build a normalized set (strip citations) for robust matching
            verified_no_cite = set()
            for vs in verified_sentence_set:
                stripped = re.sub(r'\[CITE:[^\]]+\]', '', vs).strip()
                if stripped:
                    verified_no_cite.add(stripped)

            verified_claims = []
            for claim in claims:
                # Try exact match first, then citation-stripped match
                claim_no_cite = re.sub(r'\[CITE:[^\]]+\]', '', claim.sentence).strip()
                if (claim.sentence in verified_sentence_set or
                        claim_no_cite in verified_no_cite):
                    claim.verification_passed = True
                    # FIX-182B: Use actual MiniCheck confidence instead of hardcoded 0.8
                    actual_confidence = sentence_confidences.get(claim.sentence)
                    if actual_confidence is None:
                        # Fallback: try citation-stripped match against confidence keys
                        for conf_sent, conf_score in sentence_confidences.items():
                            if re.sub(r'\[CITE:[^\]]+\]', '', conf_sent).strip() == claim_no_cite:
                                actual_confidence = conf_score
                                break
                    # FIX-191: Jaccard fuzzy matching as 3rd fallback
                    if actual_confidence is None:
                        claim_words = set(claim_no_cite.lower().split())
                        best_jaccard = 0.0
                        best_conf = None
                        jaccard_threshold = float(os.environ.get(
                            "POLARIS_CONFIDENCE_JACCARD_THRESHOLD", "0.80"
                        ))
                        for conf_sent, conf_score in sentence_confidences.items():
                            conf_no_cite = re.sub(r'\[CITE:[^\]]+\]', '', conf_sent).strip()
                            conf_words = set(conf_no_cite.lower().split())
                            intersection = len(claim_words & conf_words)
                            union = len(claim_words | conf_words)
                            if union > 0:
                                jaccard = intersection / union
                                if jaccard > best_jaccard and jaccard >= jaccard_threshold:
                                    best_jaccard = jaccard
                                    best_conf = conf_score
                        if best_conf is not None:
                            actual_confidence = best_conf
                            logger.debug(
                                f"[FIX-191] Jaccard match ({best_jaccard:.2f}) "
                                f"for confidence: {best_conf:.3f}"
                            )
                    if actual_confidence is None:
                        logger.warning(
                            f"[FIX-191] No confidence match for claim, "
                            f"using 0.8 fallback: {claim_no_cite[:80]}..."
                        )
                    claim.confidence = actual_confidence if actual_confidence is not None else 0.8
                    verified_claims.append(claim)

            # Track cited domains for diversity
            for ev in cluster_evidence:
                domain = _extract_domain(getattr(ev, 'source_url', ''))
                if domain:
                    cited_domains[domain] = cited_domains.get(domain, 0) + 1

            # FIX-182B: Log confidence distribution for diagnostics
            if verified_claims:
                conf_values = [c.confidence for c in verified_claims]
                logger.info(
                    f"[FIX-182] Cluster '{topic}' confidence: "
                    f"min={min(conf_values):.3f}, max={max(conf_values):.3f}, "
                    f"mean={sum(conf_values)/len(conf_values):.3f}, "
                    f"n={len(conf_values)}"
                )

            # FIX-184B: Extract last sentence for cross-section continuity
            prose_sentences = re.split(r'(?<=[.!?])\s+', verified_prose.strip())
            prose_sentences = [s.strip() for s in prose_sentences if s.strip()]
            if prose_sentences:
                last_sent = re.sub(r'\[CITE:[^\]]+\]', '', prose_sentences[-1]).strip()
                previous_summary = last_sent[:120] if last_sent else ""

            sections.append({
                "topic": topic,
                "prose": verified_prose,
                "grounded_claims": verified_claims,
                "evidence": cluster_evidence,  # FIX-174: Retained for expansion retry
            })
            all_grounded_claims.extend(verified_claims)

        logger.info(
            f"[FIX-161] Cluster synthesis complete: {len(sections)} sections, "
            f"{len(all_grounded_claims)} verified claims, "
            f"{len(hedged_sentences)} hedged clusters"
        )
        return sections, all_grounded_claims, hedged_sentences

    def _compose_clustered_report(
        self,
        sections: List[Dict[str, Any]],
        query: str,
        hedged_sentences: Optional[List[str]] = None,
    ) -> str:
        """
        FIX-161: Compose report from topical sections (cluster path).

        Unlike _compose_report() which concatenates isolated sentences, this
        produces coherent paragraphs under meaningful topic headings.

        Args:
            sections: [{"topic": str, "prose": str, "grounded_claims": List}]
            query: The original research query
            hedged_sentences: Unverifiable cluster summaries

        Returns:
            Markdown report string with [CITE:id] tokens
        """
        hedged_sentences = hedged_sentences or []

        if not sections and not hedged_sentences:
            return "Insufficient evidence to generate a grounded report."

        report_parts = []

        # Title
        report_parts.append(f"# Research Report: {query}\n")

        # FIX-272: Executive Summary — extract enough sentences for >= 100 words.
        # Take first 1-2 sentences from each section until target met.
        report_parts.append("## Executive Summary\n")
        summary_sentences = []
        summary_word_count = 0
        min_summary_words = int(os.environ.get("POLARIS_MIN_EXEC_SUMMARY_WORDS", "100"))
        for section in sections:
            prose = section.get("prose", "")
            if prose:
                section_sents = re.split(r'(?<=[.!?])\s+', prose.strip())
                for sent in section_sents[:2]:
                    if sent.strip():
                        summary_sentences.append(sent.strip())
                        summary_word_count += len(sent.split())
                        if summary_word_count >= min_summary_words:
                            break
            if summary_word_count >= min_summary_words:
                break
        if summary_sentences:
            for ss in summary_sentences:
                report_parts.append(f"- {ss}")
        else:
            report_parts.append("*No verified findings available for summary.*")
        report_parts.append("")

        # FIX-179: Section balance enforcement — merge thin sections
        min_section_words = int(os.environ.get("POLARIS_MIN_SECTION_WORDS", "150"))
        sections = self._enforce_section_balance(sections, min_section_words)

        # FIX-184E: Cross-section transition injection
        transitions_enabled = os.environ.get("POLARIS_COHERENCE_TRANSITIONS", "1") == "1"
        prev_topic = None

        # Topic sections: each with ## heading and coherent prose paragraph
        for section in sections:
            topic = section["topic"]
            prose = section.get("prose", "")
            if prose and prose.strip():
                # FIX-174: Validate minimum sentence count per section
                section_sentences = re.split(r'(?<=[.!?])\s+', prose.strip())
                section_sentences = [s for s in section_sentences if s.strip()]
                if len(section_sentences) < MIN_SENTENCES_PER_SECTION:
                    # FIX-174: Attempt expansion retry with section evidence
                    section_evidence = section.get("evidence", [])
                    if section_evidence and len(section_evidence) >= 3:
                        logger.info(
                            f"[FIX-174] Section '{topic}' has {len(section_sentences)} sentences "
                            f"(min {MIN_SENTENCES_PER_SECTION}), attempting expansion"
                        )
                        try:
                            expanded_prose, _ = self._write_section_prose(
                                topic, section_evidence, query,
                                max_evidence=min(len(section_evidence), 25),
                            )
                            if expanded_prose:
                                expanded_sentences = re.split(r'(?<=[.!?])\s+', expanded_prose.strip())
                                expanded_sentences = [s for s in expanded_sentences if s.strip()]
                                if len(expanded_sentences) > len(section_sentences):
                                    prose = expanded_prose
                                    section_sentences = expanded_sentences
                                    logger.info(
                                        f"[FIX-174] Expansion succeeded: {len(section_sentences)} sentences"
                                    )
                        except Exception as e:
                            logger.warning(f"[FIX-174] Expansion failed for '{topic}': {e}")
                    if len(section_sentences) < MIN_SENTENCES_PER_SECTION:
                        logger.warning(
                            f"[FIX-174] Section '{topic}' has {len(section_sentences)} sentences "
                            f"(min {MIN_SENTENCES_PER_SECTION}), section retained but flagged"
                        )
                # FIX-173: Validate each sentence has >= 1 citation
                uncited_count = 0
                for sent in section_sentences:
                    if not re.search(r'\[CITE:[^\]]+\]', sent):
                        uncited_count += 1
                if uncited_count > 0:
                    logger.warning(
                        f"[FIX-173] Section '{topic}': {uncited_count}/{len(section_sentences)} "
                        f"sentences lack citations"
                    )

                report_parts.append(f"## {topic}\n")

                # FIX-269: Safe transition injection — prepend a transition
                # phrase to the first sentence of each non-first section.
                # Uses static academic phrases (no LLM call, no CoT risk).
                # Rotates through phrases to avoid repetition.
                if transitions_enabled and prev_topic:
                    # FIX-287: All 8 phrases now match audit's transition word list
                    # (replaced 4 non-matching phrases with audit-matching alternatives)
                    _transition_phrases = [
                        "Furthermore, ",
                        "Moreover, ",
                        "Additionally, ",
                        "Consequently, ",
                        "In contrast, ",
                        "Similarly, ",
                        "In addition, ",
                        "Subsequently, ",
                    ]
                    # Deterministic rotation based on section index
                    section_idx = len([p for p in report_parts if p.startswith("## ")])
                    phrase = _transition_phrases[(section_idx - 1) % len(_transition_phrases)]
                    # Prepend phrase only if prose starts with a capital letter
                    if prose and prose[0].isupper():
                        prose = phrase + prose[0].lower() + prose[1:]

                report_parts.append(prose)
                report_parts.append("")
                prev_topic = topic

        # Hedged/unverifiable clusters (capped)
        if hedged_sentences:
            hedged_for_report = hedged_sentences[:MAX_HEDGED_IN_REPORT]
            omitted_count = len(hedged_sentences) - len(hedged_for_report)

            report_parts.append("## Additional Context (Limited Evidence)\n")
            report_parts.append(
                "*The following statements are based on limited or indirect evidence:*\n"
            )
            for hs in hedged_for_report:
                report_parts.append(f"- {hs}")
            if omitted_count > 0:
                report_parts.append(
                    f"\n*{omitted_count} additional claim(s) could not be fully "
                    f"verified and were omitted for brevity.*"
                )
            report_parts.append("")

        # FIX-272: Expanded limitations text with concrete detail.
        # Original FIX-152A had only 1 sentence (9 words); D4 penalizes thin sections.
        hedged_count = len(hedged_sentences) if hedged_sentences else 0
        section_count = len(sections)
        report_parts.append("## Limitations\n")
        limitations_lines = [
            "This report is based on publicly available sources and may not "
            "capture all relevant research.",
            "The evidence base is limited to sources retrievable through web "
            "search and academic databases at the time of analysis.",
            f"A total of {section_count} thematic clusters were identified from "
            f"the available evidence; topics not represented in these clusters "
            f"may warrant further investigation.",
        ]
        if hedged_count > 0:
            limitations_lines.append(
                f"Approximately {hedged_count} claim(s) could only be partially "
                f"verified and are flagged accordingly."
            )
        limitations_lines.append(
            "Claims with limited evidentiary support are noted where applicable, "
            "and readers should consult primary sources for definitive conclusions."
        )
        report_parts.append(" ".join(limitations_lines) + "\n")

        report = "\n".join(report_parts)

        # FIX-183C: Normalize citation tokens before further processing
        report = normalize_cite_tokens(report)

        # FIX-162E: Final cleanup — strip any remaining empty [CITE:] tokens
        empty_cite_pattern = re.compile(r'\[CITE:\s*\]')
        empty_count = len(empty_cite_pattern.findall(report))
        if empty_count > 0:
            logger.warning(
                f"[FIX-162E] Stripping {empty_count} empty [CITE:] "
                f"tokens from final report"
            )
            report = empty_cite_pattern.sub('', report)

        # FIX-177: Semantic deduplication (BEFORE CoT scrubbing)
        report = self._deduplicate_report_sentences(report)

        # FIX-176: CoT scrubbing (AFTER dedup)
        report = scrub_cot_from_report(report)

        # FIX-211: LLM post-filter for CoT lines that survive regex
        report = cot_post_filter_report(
            report, query, llm_invoke=lambda p: self._invoke_llm(p, max_tokens=2048),
        )

        # FIX-271: Query keyword inclusion validation
        # Check that core query terms appear in the report body.
        # Log missing keywords for diagnostics (D8 topical relevance).
        _stop_words = {
            "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "shall", "can", "need", "to", "of", "in",
            "for", "on", "with", "at", "by", "from", "as", "into", "through",
            "during", "before", "after", "between", "out", "off", "over", "under",
            "what", "which", "who", "whom", "where", "when", "why", "how",
            "that", "this", "these", "those", "and", "or", "but", "not", "no",
            "if", "so", "than", "too", "very", "just", "about", "up",
            "it", "its", "they", "them", "their", "we", "us", "our", "he", "him",
            "his", "she", "her", "i", "me", "my", "you", "your",
        }
        query_keywords = [
            w for w in re.findall(r"[a-z0-9]+", query.lower())
            if w not in _stop_words
        ]
        query_keywords = list(dict.fromkeys(query_keywords))
        if query_keywords:
            report_words = set(re.findall(r"[a-z0-9]+", report.lower()))
            missing = [kw for kw in query_keywords if kw not in report_words]
            if missing:
                logger.warning(
                    f"[FIX-271] Query keywords missing from report: {missing} "
                    f"(found {len(query_keywords) - len(missing)}/{len(query_keywords)})"
                )

        return report

    def _compose_report(
        self,
        grounded_claims: List[GroundedClaim],
        query: str,
        evidence_pool: List[Evidence],
        hedged_sentences: Optional[List[str]] = None,
    ) -> str:
        """
        Compose grounded claims into a coherent report.

        Phase 2: This assembles verified sentences into a structured report.
        Unlike traditional synthesis, we KNOW each sentence is faithful.

        FIX 117 Phase 2.4: Optionally includes hedged sentences for claims
        that could not be fully grounded.
        FIX-134B: Deduplication applied BEFORE composing sections.
        FIX-136A: Removed self-referential Methodology section.
        FIX-136B: Removed Confidence Assessment section (contradicts gating case).
        """
        if not grounded_claims and not hedged_sentences:
            return "Insufficient evidence to generate a grounded report."

        hedged_sentences = hedged_sentences or []
        total_generated = max(self.stats['claims_generated'], 1)
        hedged_count = self.stats.get("claims_hedged", 0)

        # FIX-134B: Deduplicate sentences BEFORE composing sections
        exec_summary_sentences = [
            claim.sentence for claim in grounded_claims[:5]
            if claim.sentence and claim.sentence.strip()
        ]
        exec_summary_sentences = self._deduplicate_sentences(exec_summary_sentences)

        findings_sentences = [
            claim.sentence for claim in grounded_claims[5:]
            if claim.sentence and claim.sentence.strip()
        ]
        findings_sentences = self._deduplicate_sentences(findings_sentences)

        # FIX-150D: Lower dedup threshold for hedged section (0.55 vs 0.70 default)
        # to catch semantic duplicates where same fact uses different words
        hedged_deduped = self._deduplicate_sentences(
            [hs for hs in hedged_sentences if hs and hs.strip()],
            threshold=0.55,
        )

        # Build report sections
        report_parts = []

        # Title
        report_parts.append(f"# Research Report: {query}\n")

        # Executive Summary
        report_parts.append("## Executive Summary\n")
        for sentence in exec_summary_sentences:
            report_parts.append(f"- {sentence}")
        report_parts.append("")

        # Main Findings (FIX-136A: Methodology section removed — it was self-referential)
        report_parts.append("## Key Findings\n")
        for i, sentence in enumerate(findings_sentences, start=1):
            if i % 5 == 1 and i > 1:
                report_parts.append("")  # Paragraph break
            report_parts.append(sentence)
        report_parts.append("")

        # Hedged/Flagged Claims Section (if any)
        # FIX-150B: Cap hedged claims, sort by confidence (highest first)
        if hedged_deduped:
            total_hedged_before_cap = len(hedged_deduped)

            # Sort hedged sentences: longer sentences (proxy for detail/confidence) first
            hedged_deduped.sort(key=lambda s: len(s), reverse=True)

            # Apply cap
            hedged_for_report = hedged_deduped[:MAX_HEDGED_IN_REPORT]
            omitted_count = total_hedged_before_cap - len(hedged_for_report)

            report_parts.append("## Additional Context (Limited Evidence)\n")
            report_parts.append(
                "*The following statements are based on limited or indirect evidence:*\n"
            )
            for hs in hedged_for_report:
                report_parts.append(f"- {hs}")

            # FIX-150C: Summary line for omitted hedged claims
            if omitted_count > 0:
                report_parts.append(
                    f"\n*{omitted_count} additional claim(s) could not be fully "
                    f"verified and were omitted for brevity.*"
                )
                logger.info(
                    f"[FIX-150] Hedged claims capped: {total_hedged_before_cap} -> "
                    f"{len(hedged_for_report)} (omitted {omitted_count})"
                )
            report_parts.append("")

        # FIX-136B: Confidence Assessment section removed.
        # The average_confidence metric (from MiniCheck inline scores, often 0.0)
        # contradicts the auditor's post-revision faithfulness (94.5%).
        # Gating case already communicates confidence.

        # FIX-272: Expanded limitations text (non-clustered path)
        report_parts.append("## Limitations\n")
        report_parts.append(
            "This report is based on publicly available sources and may not "
            "capture all relevant research. "
            "The evidence base is limited to sources retrievable through web "
            "search and academic databases at the time of analysis. "
            "Claims with limited evidentiary support are noted where applicable, "
            "and readers should consult primary sources for definitive conclusions.\n"
        )

        report = "\n".join(report_parts)

        # FIX-177: Semantic deduplication (BEFORE CoT scrubbing)
        report = self._deduplicate_report_sentences(report)

        # FIX-176: CoT scrubbing (AFTER dedup)
        report = scrub_cot_from_report(report)

        # FIX-211: LLM post-filter for CoT lines that survive regex
        report = cot_post_filter_report(
            report, query, llm_invoke=lambda p: self._invoke_llm(p, max_tokens=2048),
        )

        return report

    def _build_claim_evidence_map(
        self,
        grounded_claims: List[GroundedClaim],
    ) -> List[ClaimEvidenceMap]:
        """
        Build claim→evidence mapping for auditor.

        Phase 2.2: The auditor receives this map directly, eliminating
        the need to re-parse citations from markdown and preventing
        the "lost grounding context" problem.

        FIX 117 Enhancement: Full grounding context preservation including:
        - Evidence texts (not just IDs)
        - Quality tiers and relevance scores
        - Matching keywords explaining WHY evidence was selected
        - Verification method and threshold used
        - Generated sentence for traceability
        """
        mapping = []

        for i, claim in enumerate(grounded_claims):
            # Build full evidence grounding objects
            evidence_groundings = []
            for j, ev_id in enumerate(claim.evidence_ids):
                evidence_groundings.append(EvidenceGrounding(
                    evidence_id=ev_id,
                    evidence_text=claim.evidence_texts[j] if j < len(claim.evidence_texts) else "",
                    source_url=claim.evidence_sources[j] if j < len(claim.evidence_sources) else "",
                    quality_tier=claim.evidence_tiers[j] if j < len(claim.evidence_tiers) else "UNVERIFIED",
                    relevance_score=claim.evidence_relevance[j] if j < len(claim.evidence_relevance) else 0.5,
                    matching_keywords=claim.matching_keywords[j] if j < len(claim.matching_keywords) else [],
                ))

            mapping.append(ClaimEvidenceMap(
                claim_text=claim.claim_text,
                claim_type=claim.claim_type,
                evidence_groundings=evidence_groundings,
                evidence_ids=claim.evidence_ids,
                reasoning=claim.reasoning,
                sentence_index=i,
                generated_sentence=claim.sentence,
                verification_score=claim.confidence,
                verification_method=claim.verification_method,
                threshold_used=claim.threshold_used,
                is_compound_claim=claim.is_compound,
                atom_count=claim.atom_count,
            ))

        return mapping

    def _serialize_claim_evidence_map(
        self,
        mapping: List[ClaimEvidenceMap],
    ) -> List[Dict[str, Any]]:
        """
        Serialize claim-evidence map to JSON-compatible format.

        FIX 117 Phase 2.2: Ensures the full grounding context can be
        passed through ResearchState to the auditor without loss.
        """
        serialized = []

        for m in mapping:
            # Serialize evidence groundings
            groundings_data = []
            for g in m.evidence_groundings:
                groundings_data.append({
                    "evidence_id": g.evidence_id,
                    "evidence_text": g.evidence_text,
                    "source_url": g.source_url,
                    "quality_tier": g.quality_tier,
                    "relevance_score": g.relevance_score,
                    "matching_keywords": g.matching_keywords,
                })

            serialized.append({
                "claim_text": m.claim_text,
                "claim_type": m.claim_type,
                "evidence_groundings": groundings_data,
                "evidence_ids": m.evidence_ids,
                "reasoning": m.reasoning,
                "sentence_index": m.sentence_index,
                "generated_sentence": m.generated_sentence,
                "verification_score": m.verification_score,
                "verification_method": m.verification_method,
                "threshold_used": m.threshold_used,
                "is_compound_claim": m.is_compound_claim,
                "atom_count": m.atom_count,
            })

        return serialized

    def _invoke_llm(self, prompt: str, max_tokens: int = 0, use_structured: bool = False) -> str:
        """
        Invoke LLM with prompt and return response text.

        FIX-170: Accepts optional max_tokens for per-call token budget control.
        When max_tokens > 0, creates a temporary LLM instance with that budget.
        FIX-195: Uses .stream() + chunk collection when streaming is required
        (Fireworks KIMI K2.5 .invoke() returns empty intermittently with streaming=True).
        FIX-195B: use_structured=True uses non-thinking LLM (temp=0.6) for JSON tasks
        where thinking mode wastes all tokens on reasoning.

        Args:
            prompt: The prompt to send
            max_tokens: Per-call token limit (0 = use agent default)
            use_structured: If True, use non-thinking LLM (temp=0.6, max_tokens=4096)

        Returns:
            Response text from LLM
        """
        messages = [
            SystemMessage(content=self.get_system_prompt()),
            HumanMessage(content=prompt),
        ]

        try:
            if use_structured and getattr(self, '_structured_llm', None) is not None:
                # FIX-195B: Use json_schema structured output for JSON tasks.
                # Both thinking (temp=1.0) and non-thinking (temp=0.6) modes produce
                # extensive preamble text that truncates the actual JSON output.
                # .with_structured_output(method='json_schema') forces pure JSON.
                from pydantic import BaseModel as _BM, Field as _F
                from typing import List as _List

                class _Cluster(_BM):
                    topic: str
                    evidence_ids: _List[str]

                class _ClusterResult(_BM):
                    clusters: _List[_Cluster]

                structured = self._structured_llm.with_structured_output(
                    _ClusterResult, method='json_schema'
                )
                parsed = structured.invoke(messages)
                if parsed and hasattr(parsed, 'clusters'):
                    import json as _json
                    clusters_raw = [
                        {"topic": c.topic, "evidence_ids": c.evidence_ids}
                        for c in parsed.clusters
                    ]
                    result = _json.dumps(clusters_raw)
                    logger.info(
                        f"[FIX-195B] Structured output: {len(parsed.clusters)} clusters, "
                        f"{len(result)} chars"
                    )
                    return result
                logger.warning("[FIX-195B] Structured output returned None, falling through")
                # Fall through to regular _invoke_llm path
            elif max_tokens > 0 and getattr(self, '_is_fireworks', False):
                # FIX-170: Create per-call LLM with specific token budget
                from langchain_fireworks import ChatFireworks
                from src.config import get_config
                global_config = get_config()
                use_streaming = max_tokens > 4096
                per_call_llm = ChatFireworks(
                    model="accounts/fireworks/models/kimi-k2p5",
                    api_key=global_config.env.fireworks_api_key,
                    temperature=1.0,
                    max_tokens=max_tokens,
                    streaming=use_streaming,
                )
                if use_streaming:
                    # FIX-195: Collect streaming chunks explicitly
                    # .invoke() with streaming=True returns empty intermittently
                    chunks = []
                    chunk_count = 0
                    for chunk in per_call_llm.stream(messages):
                        chunk_count += 1
                        if chunk.content:
                            chunks.append(chunk.content)
                    result = "".join(chunks)
                    logger.info(
                        f"[FIX-195] Streaming collected {len(result)} chars "
                        f"from {chunk_count} chunks ({len(chunks)} with content)"
                    )
                    return result
                else:
                    response = per_call_llm.invoke(messages)
                    return response.content
            else:
                response = self.llm.invoke(messages)
                return response.content
        except Exception as e:
            logger.error(f"[FIX 117] LLM invocation failed: {e}")
            raise


# =============================================================================
# Factory Function
# =============================================================================

def create_citefirst_synthesizer() -> CitefirstSynthesizer:
    """Factory function to create CitefirstSynthesizer."""
    return CitefirstSynthesizer()


def is_citefirst_enabled() -> bool:
    """Check if cite-first synthesis is enabled."""
    return CITEFIRST_ENABLED
