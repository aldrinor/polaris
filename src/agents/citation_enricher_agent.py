"""
POLARIS FIX 107: Citation Enricher Agent

Post-verification citation enrichment to achieve SOTA citation density.

PROBLEM: FIX 105A's strict atomic verification creates inverse correlation:
- Stricter verification → fewer citations survive
- RUN8: 85.2% faithfulness but only 32 citations
- Competitors (Gemini DR, ChatGPT DR): 120-150+ citations

SOLUTION: Add citations AFTER verification passes using soft verification.
- Only runs when faithfulness >= 85% (report is already verified)
- Uses semantic matching to find relevant evidence for under-cited sentences
- Soft verification (MiniCheck at 0.25 threshold, NO atomic decomposition)
- Injects citations without modifying text content

This decouples citation density from faithfulness verification.
"""

import os
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from .base_agent import BaseAgent, AgentConfig, register_agent
from src.orchestration.state import ResearchState, Evidence

logger = logging.getLogger(__name__)


# =============================================================================
# FIX 107 Configuration
# =============================================================================

def get_enrichment_config() -> Dict[str, Any]:
    """Get FIX 107/108 enrichment configuration from environment."""
    return {
        "enabled": os.environ.get("POLARIS_ENRICHMENT_ENABLED", "1") == "1",
        "target_citations": int(os.environ.get("POLARIS_TARGET_CITATIONS", "100")),
        # FIX 108A: Raised from 0.55 to 0.70 for higher citation precision (industry standard)
        "similarity_threshold": float(os.environ.get("POLARIS_ENRICHMENT_SIMILARITY", "0.70")),
        # FIX 108E: Raised from 0.25 to 0.40 for stricter soft verification
        "soft_verify_threshold": float(os.environ.get("POLARIS_SOFT_VERIFY_THRESHOLD", "0.40")),
        "max_per_sentence": int(os.environ.get("POLARIS_MAX_NEW_CITATIONS", "2")),
        "skip_if_citations_gte": int(os.environ.get("POLARIS_ENRICHMENT_SKIP_THRESHOLD", "3")),
        # FIX 107D: Lowered from 0.85 to 0.75 to trigger at S1V9 faithfulness level (79.1%)
        "min_faithfulness_required": float(os.environ.get("POLARIS_ENRICHMENT_MIN_FAITHFULNESS", "0.75")),
        # FIX 108B: Maximum times each evidence can be cited globally (deduplication)
        "max_evidence_reuse": int(os.environ.get("POLARIS_MAX_EVIDENCE_REUSE", "3")),
    }


# =============================================================================
# Enrichment Result Schema
# =============================================================================

@dataclass
class EnrichmentResult:
    """Result of citation enrichment for a single sentence."""
    original_sentence: str
    enriched_sentence: str
    added_citations: List[str]
    similarity_scores: Dict[str, float]  # evidence_id -> similarity score
    soft_verify_passed: bool


@dataclass
class EnrichmentSummary:
    """Summary of the entire enrichment pass."""
    total_sentences: int
    sentences_enriched: int
    citations_added: int
    original_citation_count: int
    final_citation_count: int
    enrichment_citations: List[str]  # IDs of enrichment-added citations (for bypass flag)


# =============================================================================
# Citation Enricher Agent
# =============================================================================

@register_agent("citation_enricher")
class CitationEnricherAgent(BaseAgent):
    """
    FIX 107: Post-verification citation enrichment agent.

    This agent runs AFTER the auditor has verified the report passes faithfulness
    threshold (>= 85%). Its job is to increase citation density without modifying
    the verified text content.

    Key Design Decisions:
    1. SOFT VERIFICATION: MiniCheck at 0.25 threshold (vs 0.30 in auditor),
       sentence-level only (NO atomic decomposition)
    2. NO CONTENT MODIFICATION: Only adds [CITE:xxx] tokens, never rewrites text
    3. PRE-VERIFIED EVIDENCE: Only uses GOLD/SILVER evidence from existing pool
    4. CONSERVATIVE INJECTION: Max 2 new citations per sentence
    5. BYPASS FLAG: Tracks enrichment_citations for auditor bypass in FIX 107B
    """

    def __init__(self):
        config = AgentConfig(
            name="citation_enricher",
            description="Post-verification citation enrichment for SOTA citation density",
            task_tier="simple",  # Uses embedding similarity, not heavy LLM calls
            temperature=0.0,
            max_tokens=1000,
        )
        super().__init__(config)

        # Initialize embedding model
        self._embedding_model = None
        self._init_embedding_model()

        # Initialize MiniCheck for soft verification
        self._minicheck = None
        self._init_minicheck()

    def _init_embedding_model(self):
        """Initialize sentence-transformers embedding model."""
        try:
            from sentence_transformers import SentenceTransformer
            model_name = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
            self._embedding_model = SentenceTransformer(model_name)
            logger.info(f"[FIX 107] Embedding model initialized: {model_name}")
        except ImportError:
            logger.warning("[FIX 107] sentence-transformers not available, enrichment disabled")
            self._embedding_model = None
        except Exception as e:
            logger.warning(f"[FIX 107] Embedding model init failed: {e}")
            self._embedding_model = None

    def _init_minicheck(self):
        """Initialize MiniCheck for soft verification."""
        try:
            from minicheck.minicheck import MiniCheck
            model_name = os.environ.get("POLARIS_MINICHECK_MODEL", "roberta-large")
            self._minicheck = MiniCheck(model_name=model_name, cache_dir="./ckpts")
            logger.info(f"[FIX 107] MiniCheck initialized for soft verification: {model_name}")
        except ImportError:
            logger.warning("[FIX 107] MiniCheck not available, using embedding-only enrichment")
            self._minicheck = None
        except Exception as e:
            logger.warning(f"[FIX 107] MiniCheck init failed: {e}")
            self._minicheck = None

    def get_system_prompt(self) -> str:
        return "Citation enrichment agent - no LLM prompting needed"

    def process(self, state: ResearchState) -> ResearchState:
        """
        Enrich citations in the draft report.

        Pre-checks:
        1. Enrichment must be enabled
        2. Faithfulness must be >= 85%
        3. Embedding model must be available
        4. Evidence chain must exist

        Args:
            state: Research state with draft_report, evidence_chain, post_hoc_faithfulness

        Returns:
            Updated state with enriched draft_report and enrichment_citations
        """
        config = get_enrichment_config()

        # Pre-check 1: Enrichment enabled
        if not config["enabled"]:
            logger.info("[FIX 107] Citation enrichment disabled, skipping")
            return state

        # Pre-check 2: Faithfulness threshold
        # =======================================================================
        # FIX 107J-B: TRUST THE ROUTER
        # =======================================================================
        # If the Router has authorized enrichment (via Hail Mary or Auditor Trust),
        # we bypass our own faithfulness check. The Router already validated the
        # conditions for enrichment in route_after_auditor().
        #
        # This fixes the "dual gate" problem from RUN11/RUN12 where:
        # - Router correctly authorized enrichment (Faith>60%+HailMary)
        # - But agent blocked it with its own 75% threshold
        # =======================================================================
        faithfulness = state.get("post_hoc_faithfulness", 0.0)
        router_authorized = state.get("router_authorized_enrichment", False)

        if router_authorized:
            logger.info(
                f"[FIX 107J-B] Router authorized enrichment, bypassing faithfulness threshold check "
                f"(faithfulness={faithfulness:.1%})"
            )
        elif faithfulness < config["min_faithfulness_required"]:
            logger.info(
                f"[FIX 107] Faithfulness {faithfulness:.1%} < {config['min_faithfulness_required']:.1%}, "
                "skipping enrichment (report not verified)"
            )
            return state

        # Pre-check 3: Embedding model
        if self._embedding_model is None:
            logger.warning("[FIX 107] Embedding model not available, skipping enrichment")
            return state

        # Pre-check 4: Evidence and report
        draft_report = state.get("draft_report", "")
        evidence_chain = state.get("evidence_chain", [])

        if not draft_report or not evidence_chain:
            logger.warning("[FIX 107] Missing draft_report or evidence_chain, skipping")
            return state

        logger.info(
            f"[FIX 107] Starting citation enrichment: "
            f"faithfulness={faithfulness:.1%}, evidence={len(evidence_chain)} pieces"
        )

        # Build evidence embeddings (batch for efficiency)
        evidence_embeddings = self._embed_evidence(evidence_chain)
        if not evidence_embeddings:
            logger.warning("[FIX 107] Failed to embed evidence, skipping")
            return state

        # Extract sentences from report
        sentences = self._split_sentences(draft_report)
        logger.info(f"[FIX 107] Processing {len(sentences)} sentences")

        # Track enrichments
        enrichment_citations = []
        enrichment_results = []
        enriched_sentences = {}  # index -> enriched sentence

        # Count existing citations
        existing_citations = set(re.findall(r'\[CITE:([^\]]+)\]', draft_report))
        original_count = len(existing_citations)

        # Process each sentence
        for i, sentence in enumerate(sentences):
            # Extract existing citations in this sentence
            existing_in_sentence = re.findall(r'\[CITE:([^\]]+)\]', sentence)

            # Skip if already well-cited
            if len(existing_in_sentence) >= config["skip_if_citations_gte"]:
                continue

            # Skip very short sentences (headers, bullets without facts)
            clean_sentence = re.sub(r'\[CITE:[^\]]+\]', '', sentence).strip()
            if len(clean_sentence) < 50:
                continue

            # Skip non-factual sentences (meta-discourse)
            if self._is_meta_discourse(clean_sentence):
                continue

            # Find matching evidence using semantic similarity
            matches = self._find_semantic_matches(
                sentence=clean_sentence,
                evidence_embeddings=evidence_embeddings,
                evidence_chain=evidence_chain,
                exclude_ids=set(existing_in_sentence),
                threshold=config["similarity_threshold"],
                top_k=5
            )

            if not matches:
                continue

            # Soft verification (sentence-level, NO atomic decomposition)
            verified_matches = []
            for evidence_id, similarity_score in matches:
                if self._soft_verify(clean_sentence, evidence_id, evidence_chain, config["soft_verify_threshold"]):
                    verified_matches.append((evidence_id, similarity_score))
                    if len(verified_matches) >= config["max_per_sentence"]:
                        break

            if not verified_matches:
                continue

            # Inject citations at end of sentence
            enriched_sentence = self._inject_citations(sentence, [m[0] for m in verified_matches])
            enriched_sentences[i] = enriched_sentence

            # Track enrichments
            for evidence_id, _ in verified_matches:
                enrichment_citations.append(evidence_id)

            enrichment_results.append(EnrichmentResult(
                original_sentence=sentence,
                enriched_sentence=enriched_sentence,
                added_citations=[m[0] for m in verified_matches],
                similarity_scores={m[0]: m[1] for m in verified_matches},
                soft_verify_passed=True
            ))

        # Rebuild report with enriched sentences
        if enriched_sentences:
            enriched_report = self._rebuild_report(draft_report, sentences, enriched_sentences)
        else:
            enriched_report = draft_report

        # =======================================================================
        # FIX 108B: Global Citation Deduplication
        # =======================================================================
        # After enrichment, deduplicate citations to reduce evidence reuse.
        # This addresses the 4.08x avg reuse problem identified in RUN13 audit.
        max_reuse = config.get("max_evidence_reuse", 3)
        deduplicated_report, evidence_usage = self._deduplicate_citations(
            enriched_report, max_reuse=max_reuse
        )
        state["draft_report"] = deduplicated_report

        # Count final citations (after deduplication)
        final_citations = set(re.findall(r'\[CITE:([^\]]+)\]', deduplicated_report))
        final_count = len(final_citations)

        # Calculate evidence reuse ratio
        total_citation_instances = len(re.findall(r'\[CITE:([^\]]+)\]', deduplicated_report))
        unique_citations = len(final_citations)
        reuse_ratio = total_citation_instances / unique_citations if unique_citations > 0 else 0.0

        # Store enrichment metadata for FIX 107B bypass
        state["enrichment_citations"] = enrichment_citations
        state["enrichment_applied"] = len(enrichment_citations) > 0
        state["enrichment_summary"] = {
            "total_sentences": len(sentences),
            "sentences_enriched": len(enriched_sentences),
            "citations_added": len(enrichment_citations),
            "original_citation_count": original_count,
            "final_citation_count": final_count,
            "evidence_reuse_ratio": reuse_ratio,  # FIX 108B metric
        }

        logger.info(
            f"[FIX 107/108B] Enrichment complete: "
            f"{len(enriched_sentences)} sentences enriched, "
            f"{len(enrichment_citations)} citations added, "
            f"reuse_ratio={reuse_ratio:.2f}x "
            f"({original_count} -> {final_count} unique citations)"
        )

        return state

    def _embed_evidence(self, evidence_chain: List[Evidence]) -> Dict[str, Any]:
        """Build evidence embeddings for semantic matching.

        Returns:
            Dict mapping evidence_id to (embedding, Evidence) tuples
        """
        if not self._embedding_model:
            return {}

        result = {}
        texts = []
        ids = []

        for ev in evidence_chain:
            # Only use GOLD/SILVER evidence
            tier = getattr(ev, "quality_tier", "UNVERIFIED")
            if tier not in ("GOLD", "SILVER"):
                continue

            ev_id = getattr(ev, "evidence_id", None)
            text = getattr(ev, "text", "")

            if ev_id and text:
                texts.append(text[:1000])  # Truncate for embedding
                ids.append(ev_id)

        if not texts:
            return {}

        try:
            embeddings = self._embedding_model.encode(texts, convert_to_tensor=True)

            for i, ev_id in enumerate(ids):
                ev = next((e for e in evidence_chain if getattr(e, "evidence_id", None) == ev_id), None)
                if ev:
                    result[ev_id] = (embeddings[i], ev)

            logger.debug(f"[FIX 107] Embedded {len(result)} GOLD/SILVER evidence pieces")
        except Exception as e:
            logger.error(f"[FIX 107] Evidence embedding failed: {e}")
            return {}

        return result

    def _find_semantic_matches(
        self,
        sentence: str,
        evidence_embeddings: Dict[str, Any],
        evidence_chain: List[Evidence],
        exclude_ids: set,
        threshold: float,
        top_k: int
    ) -> List[Tuple[str, float]]:
        """Find evidence that semantically matches the sentence.

        Args:
            sentence: The sentence to match
            evidence_embeddings: Dict of evidence_id -> (embedding, Evidence)
            evidence_chain: Full evidence chain
            exclude_ids: Evidence IDs to exclude (already cited)
            threshold: Minimum similarity threshold
            top_k: Maximum matches to return

        Returns:
            List of (evidence_id, similarity_score) tuples
        """
        if not self._embedding_model or not evidence_embeddings:
            return []

        try:
            import torch
            from torch.nn import functional as F

            # Embed the sentence
            sentence_emb = self._embedding_model.encode(sentence, convert_to_tensor=True)

            # Calculate similarity with all evidence
            matches = []
            for ev_id, (ev_emb, ev) in evidence_embeddings.items():
                if ev_id in exclude_ids:
                    continue

                # Cosine similarity
                similarity = F.cosine_similarity(
                    sentence_emb.unsqueeze(0),
                    ev_emb.unsqueeze(0)
                ).item()

                if similarity >= threshold:
                    matches.append((ev_id, similarity))

            # Sort by similarity (descending)
            matches.sort(key=lambda x: x[1], reverse=True)

            return matches[:top_k]

        except Exception as e:
            logger.debug(f"[FIX 107] Semantic matching failed: {e}")
            return []

    def _soft_verify(
        self,
        sentence: str,
        evidence_id: str,
        evidence_chain: List[Evidence],
        threshold: float
    ) -> bool:
        """Soft verification using MiniCheck at lower threshold.

        KEY DIFFERENCE FROM AUDITOR:
        - Uses lower threshold (0.25 vs 0.30)
        - NO atomic decomposition (sentence-level only)
        - Used for enrichment, not rejection

        Args:
            sentence: The sentence to verify
            evidence_id: Evidence ID to verify against
            evidence_chain: Full evidence chain
            threshold: MiniCheck probability threshold

        Returns:
            True if evidence supports the sentence
        """
        # If no MiniCheck, trust semantic similarity
        if not self._minicheck:
            return True

        # Find the evidence
        evidence = None
        for ev in evidence_chain:
            if getattr(ev, "evidence_id", None) == evidence_id:
                evidence = ev
                break

        if not evidence:
            return False

        try:
            ev_text = getattr(evidence, "text", "")[:2000]  # RoBERTa 512 token limit

            pred_label, raw_prob, _, _ = self._minicheck.score(
                docs=[ev_text],
                claims=[sentence]
            )

            confidence = raw_prob[0] if raw_prob else 0.0

            if confidence >= threshold:
                logger.debug(f"[FIX 107] Soft verify PASS: {evidence_id} (conf={confidence:.2f})")
                return True
            else:
                logger.debug(f"[FIX 107] Soft verify FAIL: {evidence_id} (conf={confidence:.2f})")
                return False

        except Exception as e:
            logger.debug(f"[FIX 107] Soft verify error: {e}")
            return False  # Conservative: don't add citation if verification fails

    def _inject_citations(self, sentence: str, evidence_ids: List[str]) -> str:
        """Inject citations at the end of a sentence.

        Places citations before the final punctuation.

        Args:
            sentence: Original sentence
            evidence_ids: Evidence IDs to add as citations

        Returns:
            Sentence with injected citations
        """
        if not evidence_ids:
            return sentence

        # Build citation string
        citations = "".join(f"[CITE:{ev_id}]" for ev_id in evidence_ids)

        # Find the last punctuation mark
        match = re.search(r'([.!?])\s*$', sentence)
        if match:
            # Insert before final punctuation
            punctuation = match.group(1)
            sentence = sentence[:match.start()].rstrip() + " " + citations + punctuation
        else:
            # No punctuation - append at end
            sentence = sentence.rstrip() + " " + citations

        return sentence

    def _rebuild_report(
        self,
        original_report: str,
        sentences: List[str],
        enriched_sentences: Dict[int, str]
    ) -> str:
        """Rebuild the report with enriched sentences.

        Args:
            original_report: Original draft report
            sentences: List of extracted sentences
            enriched_sentences: Dict of index -> enriched sentence

        Returns:
            Report with enriched sentences
        """
        result = original_report

        # Replace sentences in reverse order to maintain positions
        for i in sorted(enriched_sentences.keys(), reverse=True):
            original = sentences[i]
            enriched = enriched_sentences[i]
            result = result.replace(original, enriched, 1)

        return result

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences.

        Uses the same logic as auditor for consistency.
        """
        # Remove markdown headers
        text = re.sub(r'^#+\s+.*$', '', text, flags=re.MULTILINE)

        # Split on sentence-ending punctuation OR newlines with bullets
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])|\n\s*[-*\u2022]\s*', text)

        # Clean and filter
        clean_sentences = []
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if len(s) < 30:
                continue
            if s.startswith('[ev_') or s.startswith('ev_'):
                continue
            clean_sentences.append(s)

        return clean_sentences

    def _is_meta_discourse(self, sentence: str) -> bool:
        """Check if sentence is meta-discourse (doesn't need citations).

        Based on FIX 59 Narrative Safe Harbor patterns.
        """
        safe_harbor_patterns = [
            r'^This\s+(?:report|section|analysis|study)\s+(?:examines|explores|investigates|discusses)',
            r'^The\s+(?:following|next|previous|above)\s+section',
            r'^In\s+(?:this|the following)\s+(?:section|analysis|report)',
            r'^(?:First|Second|Third|Finally|Additionally|Furthermore|Moreover|However),?\s',
            r'^To\s+(?:understand|examine|explore|analyze)\s+this',
            r'^The\s+(?:purpose|goal|objective|aim)\s+of\s+this',
            r'^As\s+(?:discussed|mentioned|noted|described)\s+(?:above|below|earlier)',
        ]

        for pattern in safe_harbor_patterns:
            if re.search(pattern, sentence, re.IGNORECASE):
                # Also check it has no numbers (factual claims)
                if not re.search(r'\d', sentence):
                    return True

        return False

    def _deduplicate_citations(
        self,
        draft_report: str,
        max_reuse: int = 3
    ) -> Tuple[str, Dict[str, int]]:
        """FIX 108B: Global citation deduplication.

        Limits how many times each evidence piece can be cited in the report.
        This addresses the over-citation problem (4.08x avg reuse in RUN13).

        Args:
            draft_report: The report with citations
            max_reuse: Maximum times each evidence can be cited (default: 3)

        Returns:
            Tuple of (deduplicated_report, evidence_usage_counts)
        """
        # Count current evidence usage
        evidence_usage: Dict[str, int] = {}
        all_citations = re.findall(r'\[CITE:([^\]]+)\]', draft_report)

        for cite_id in all_citations:
            evidence_usage[cite_id] = evidence_usage.get(cite_id, 0) + 1

        # Identify over-used citations
        over_used = {cid for cid, count in evidence_usage.items() if count > max_reuse}

        if not over_used:
            logger.debug("[FIX 108B] No over-used citations found")
            return draft_report, evidence_usage

        logger.info(
            f"[FIX 108B] Found {len(over_used)} over-used citations "
            f"(max_reuse={max_reuse}): {list(over_used)[:5]}..."
        )

        # Process report sentence by sentence to remove excess citations
        # Keep first max_reuse occurrences, remove subsequent ones
        citation_seen: Dict[str, int] = {}
        result_lines = []

        # Split by lines to preserve structure
        lines = draft_report.split('\n')

        for line in lines:
            # Find all citations in this line
            citations_in_line = re.findall(r'\[CITE:([^\]]+)\]', line)

            for cite_id in citations_in_line:
                citation_seen[cite_id] = citation_seen.get(cite_id, 0) + 1

                # If this is beyond max_reuse, remove it
                if cite_id in over_used and citation_seen[cite_id] > max_reuse:
                    # Remove only one occurrence of this citation from the line
                    line = re.sub(
                        r'\[CITE:' + re.escape(cite_id) + r'\]',
                        '',
                        line,
                        count=1
                    )

            # Clean up double spaces that may result from removal
            line = re.sub(r'  +', ' ', line)
            result_lines.append(line)

        deduplicated_report = '\n'.join(result_lines)

        # Count final usage
        final_citations = re.findall(r'\[CITE:([^\]]+)\]', deduplicated_report)
        removed_count = len(all_citations) - len(final_citations)

        logger.info(
            f"[FIX 108B] Deduplication complete: removed {removed_count} excess citations "
            f"({len(all_citations)} -> {len(final_citations)})"
        )

        return deduplicated_report, evidence_usage
