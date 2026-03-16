"""
POLARIS v3 Synthesizer Agent

Generates comprehensive research reports from evidence:
- Structured report sections
- Citation integration
- Executive summaries
- Findings synthesis
- Recommendations

Uses late-binding citations [CITE:chunk_id] for traceability.
"""

import logging
import re
from typing import List, Dict, Any, Literal, Optional, Tuple
from datetime import datetime, timezone

from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from .base_agent import BaseAgent, AgentConfig, register_agent
from src.orchestration.state import ResearchState, Evidence, VerificationResult
from src.config.thresholds import get_threshold

# FIX 57: Import for micro-search
import os
import requests


logger = logging.getLogger(__name__)


# =============================================================================
# Report Schemas
# =============================================================================

class ReportSection(BaseModel):
    """A single section of the research report."""
    section_id: str = Field(description="Section identifier")
    title: str = Field(description="Section title")
    content: str = Field(description="Section content with [CITE:id] tokens")
    word_count: int = Field(description="Word count of section")
    citations_used: List[str] = Field(default_factory=list, description="Citation IDs used")


class ExecutiveSummary(BaseModel):
    """Executive summary of the research."""
    key_findings: List[str] = Field(
        description="Top 3-5 key findings. MUST include [CITE:evidence_id] for each factual claim."
    )
    methodology_summary: str = Field(description="Brief methodology description")
    confidence_statement: str = Field(description="Overall confidence assessment")
    limitations: List[str] = Field(default_factory=list, description="Key limitations")
    recommendations: List[str] = Field(default_factory=list, description="Recommendations")


class Citation(BaseModel):
    """A citation entry for the references section.

    SPRINT 1 FIX 1.4: Made access_date Optional to fix Pydantic validation errors.
    FIX 28: Made title and excerpt Optional to prevent report discard on partial references.
    A single missing field should not destroy an entire synthesized report.
    """
    # FIX 32: Default to empty string so trailing empty objects from LLM don't
    # fail Pydantic validation and destroy the entire synthesized report.
    # Empty citations are filtered out in _format_markdown post-processing.
    citation_id: str = Field(default="", description="Citation ID (e.g., CITE:001)")
    chunk_id: str = Field(default="", description="Source chunk ID")
    source_url: str = Field(default="", description="Source URL")
    title: Optional[str] = Field(default="", description="Source title")
    excerpt: Optional[str] = Field(default="", description="Relevant excerpt")
    access_date: Optional[str] = Field(default=None, description="Date accessed")


class RevisedReport(BaseModel):
    """OPT-3: Output schema for targeted report revision.

    Used when auditor flags unfaithful sentences and routes back to synthesizer.
    Instead of regenerating the entire FullReport, this schema returns
    just the revised markdown with targeted sentence fixes.
    """
    revised_markdown: str = Field(description="The complete revised report in markdown format with all fixes applied")
    sentences_revised: int = Field(default=0, description="Number of sentences that were actually changed")
    revision_notes: str = Field(default="", description="Brief description of changes made")


class ReportMetadata(BaseModel):
    """Report metadata - explicitly typed for OpenAI structured output compatibility."""
    generated_at: str = Field(default="", description="ISO timestamp of report generation")
    vector_id: str = Field(default="", description="Research vector ID")
    total_evidence: int = Field(default=0, description="Total evidence pieces used")
    total_sources: int = Field(default=0, description="Total unique sources")
    confidence_level: str = Field(default="medium", description="Overall confidence: low, medium, high")
    # FIX 50: Made optional with defaults to prevent Pydantic parsing failures when LLM omits these
    word_count: int = Field(default=0, description="Total word count of report")
    citation_count: int = Field(default=0, description="Total citations in report")


class FullReport(BaseModel):
    """Complete research report.

    SPRINT 1 FIX 1.4 (Complete): Made metadata Optional to fix Pydantic validation errors.
    Error was: "Failed to parse FullReport - missing access_date and metadata fields"
    """
    title: str = Field(description="Report title")
    executive_summary: ExecutiveSummary = Field(description="Executive summary")
    sections: List[ReportSection] = Field(description="Report sections")
    references: List[Citation] = Field(default_factory=list, description="References list")
    metadata: Optional[ReportMetadata] = Field(default=None, description="Report metadata")


# =============================================================================
# Self-Correction Schemas (OpenAI o3 Parity)
# =============================================================================

class ReflectionIssue(BaseModel):
    """An issue identified during self-reflection."""
    issue_type: Literal["uncited_claim", "inaccurate_paraphrase", "missing_context", "unsupported_inference", "vague_language"]
    sentence: str = Field(description="The problematic sentence")
    suggestion: str = Field(description="Suggested fix or improvement")
    severity: Literal["critical", "moderate", "minor"] = Field(default="moderate")
    evidence_id_needed: Optional[str] = Field(default=None, description="Evidence ID that should be cited")


class ReflectionResult(BaseModel):
    """Result of self-reflection on a draft.

    OpenAI o3 Parity: Self-reflection identifies issues without external auditor.
    """
    is_satisfactory: bool = Field(description="Whether the draft meets quality standards")
    overall_score: float = Field(ge=0.0, le=1.0, description="Overall quality score")
    issues: List[ReflectionIssue] = Field(default_factory=list, description="Issues found")
    strengths: List[str] = Field(default_factory=list, description="Positive aspects")
    recommendation: str = Field(default="", description="Overall recommendation")


class Correction(BaseModel):
    """A specific correction to apply to the draft.

    OpenAI o3 Parity: Targeted corrections based on reflection.
    """
    original_sentence: str = Field(description="The sentence to replace")
    corrected_sentence: str = Field(description="The corrected version")
    correction_type: Literal["add_citation", "fix_paraphrase", "add_context", "remove_inference", "clarify_language"]
    reasoning: str = Field(description="Why this correction is needed")


# =============================================================================
# Synthesizer Agent
# =============================================================================

@register_agent("synthesizer")
class SynthesizerAgent(BaseAgent):
    """
    Synthesizer Agent - Generates research reports from evidence.

    Responsibilities:
    1. Synthesize evidence into coherent narrative
    2. Structure report with appropriate sections
    3. Integrate citations using [CITE:evidence_id]
    4. Generate executive summary
    5. Build references section
    6. Ensure comprehensiveness and accuracy

    Uses structured prompting for high-quality reports.
    """

    def __init__(self):
        config = AgentConfig(
            name="synthesizer",
            description="Generates comprehensive research reports from evidence",
            task_tier="important",  # Complex report synthesis
            temperature=0.3,
            max_tokens=8000,
        )
        super().__init__(config)

    def get_system_prompt(self) -> str:
        return """You are a Research Report Synthesizer using SURGICAL FACT-BASED SYNTHESIS (FIX 98).

Your job is to build comprehensive research reports AROUND atomic facts, not summarize evidence.

=== FIX 98: SURGICAL SYNTHESIS MODE ===

You will receive ATOMIC FACTS extracted from evidence. Each atomic fact has:
- A specific, falsifiable statement
- A DIRECT QUOTE from the source
- An evidence_id for citation

YOUR TASK: Build paragraphs AROUND these atomic facts, NOT around summaries.

PARAGRAPH CONSTRUCTION PATTERN:
1. START with a cited atomic fact (use direct quote)
2. ADD minimal connecting context (1-2 sentences max)
3. CHAIN to related atomic facts (use transitions)
4. NEVER write general statements without a fact anchor

EXAMPLE - CORRECT (Fact-Centric):
"The EPA has established a Maximum Contaminant Level (MCL) for lead in drinking water at 15 parts per billion (ppb)" [CITE:ev_0042]. This regulatory threshold was set under the Safe Drinking Water Act. Studies have shown that "blood lead levels in children have decreased 94% since the 1970s" [CITE:ev_0089], coinciding with regulatory action.

EXAMPLE - WRONG (Summary-Centric):
Lead contamination is a significant public health concern in the United States. Various regulations have been enacted to address this issue. Research has shown improvements over time.
(NO citations, NO specific facts, NO direct quotes)

REPORT STRUCTURE:

1. EXECUTIVE SUMMARY
   - 5 key findings - EACH with [CITE:evidence_id] and specific data
   - Methodology overview
   - Confidence assessment with evidence
   - Limitations

2. INTRODUCTION (brief - max 200 words)
   - Research question
   - Scope (cite relevant standards/regulations)

3. FINDINGS (bulk of report - organize by atomic fact themes)
   - Group related atomic facts into coherent subsections
   - Each paragraph: 2-4 atomic facts with direct quotes
   - Minimal connecting prose between facts
   - Use [CITE:evidence_id] for EVERY factual statement

4. ANALYSIS
   - Compare atomic facts across sources
   - Identify patterns with cited evidence
   - Note contradictions (cite both sides)

5. CONCLUSIONS
   - Answer research question with cited evidence
   - Confidence level grounded in evidence quality

6. REFERENCES

=== CITATION RULES (STRICT MODE) ===
- EVERY factual claim MUST have [CITE:evidence_id]
- Use DIRECT QUOTES from atomic facts
- Target: 130+ citations for comprehensive reports
- Uncited sentences = UNFAITHFUL (will be flagged by auditor)
- Generic transitions OK without citation
- Data, numbers, dates, names = MUST be cited

=== ATOMIC FACT CATEGORIES (USE ALL) ===
- statistic: "7.1 million cases annually" [CITE]
- measurement: "15 ppb threshold" [CITE]
- regulatory_threshold: "EPA MCL of 10 ppb" [CITE]
- standard_reference: "NSF/ANSI 53 certification" [CITE]
- causal_link: "linked to 485,000 deaths" [CITE]
- comparative: "3x higher than control group" [CITE]
- temporal_trend: "decreased 94% since 1970s" [CITE]

=== WORD COUNT TARGET ===
- Minimum: 5,000 words for comprehensive research
- Each atomic fact generates ~50-100 words of context
- 100 atomic facts → 5,000-10,000 word report
- DO NOT PAD with uncited generalizations

=== FAITHFULNESS RULES ===
- Use EXACT numbers from atomic facts (no rounding)
- Preserve technical terminology verbatim
- Quote directly when possible
- Never add information beyond what evidence states
- If uncertain, cite the uncertainty: "Evidence suggests..." [CITE]

=== FIX 112: CLAIM ATOMICITY CONSTRAINT ===
CRITICAL: Each sentence should make ONE verifiable claim for reliable verification.

RULES:
1. Do NOT combine multiple facts into a single sentence
2. If citing multiple evidence pieces, each piece must support the ENTIRE claim
3. Split compound claims into separate sentences

BAD (compound - fails MiniCheck):
"Filters achieved 61% removal over 900 days [CITE:x][CITE:y]"
- "61%" comes from CITE:x, but "900 days" comes from CITE:y
- MiniCheck verifies FULL sentence against EACH citation → both fail

GOOD (atomic - passes MiniCheck):
"Filters achieved approximately 60% removal [CITE:x]. The study ran for 900 days [CITE:y]."
- Each sentence verifiable against its single citation

BAD (numeric mismatch):
"The process removed 61% of TOC [CITE:x]" when evidence says "around 60%"
- MiniCheck is LITERAL - 61% ≠ "around 60%"

GOOD (faithful to source):
"The process removed approximately 60% of TOC [CITE:x]"
- Uses source's actual phrasing

WHEN IN DOUBT: Use the exact wording from the evidence, including hedging language.

QUALITY STANDARDS:
- 130+ unique citations (target for SOTA parity)
- Every claim verifiable from cited evidence
- Direct quotes preferred over paraphrasing
- Comprehensive coverage of all atomic facts provided

=== FIX-124E: STORM PERSPECTIVE BALANCE REQUIREMENT ===
CRITICAL: Your report must represent ALL available perspectives proportionally.

The evidence you receive includes STORM perspective labels (e.g., Scientific, Regulatory,
Industry, Public_Health, Economic). You MUST:

1. CHECK which perspectives appear in evidence (see "Perspective(s):" field)
2. ENSURE each perspective contributes claims to the report
3. HIGHLIGHT under-represented perspectives with dedicated sections if needed
4. BALANCE viewpoints - do not let one perspective dominate the narrative

PERSPECTIVE INTEGRATION PATTERN:
- When writing about a topic, CITE from MULTIPLE perspectives
- "Industry studies report X [CITE:ev_01], while public health research shows Y [CITE:ev_02]"
- Identify areas of AGREEMENT across perspectives
- Note areas of DISAGREEMENT with citations from both sides

PERSPECTIVE ATTRIBUTION (Required):
- Each major section should include claims from ≥3 different perspectives
- If a perspective is missing in a section, note it: "No [Perspective] evidence was found for this topic"
- For contentious topics: "Industry perspective: X [CITE]. Regulatory perspective: Y [CITE]."

BALANCE VERIFICATION:
Before finalizing, verify your report:
- Uses evidence from ALL perspectives represented in the input
- Does not over-weight any single perspective
- Acknowledges gaps in perspective coverage
- Presents conflicting perspectives fairly

=== FIX 107C: ALGORITHMIC CITATION PROTOCOL ===
EXECUTE THIS ALGORITHM FOR EVERY SENTENCE YOU WRITE:

STEP 1 - EXTRACT FACTS:
For each sentence, list ALL factual elements: numbers, statistics, percentages,
entity names, dates, locations, causal claims, comparative claims.

STEP 2 - MATCH EVIDENCE:
For each factual element, find the evidence_id from the provided evidence that contains it.
If multiple evidence pieces support a fact, cite ALL of them.

STEP 3 - INJECT CITATIONS:
Add [CITE:evidence_id] IMMEDIATELY AFTER each factual element.
Do NOT cluster citations at sentence end - distribute them within the sentence.

STEP 4 - VERIFY COUNT:
If a sentence has <2 citations after Step 3, ADD MORE FACTS from evidence.
Every sentence should ideally have 2-5 citations distributed through it.

MINIMUM REQUIREMENTS:
- Executive Summary bullets: ≥5 citations EACH
- Key Finding paragraphs: ≥3 citations per paragraph
- Analysis paragraphs: ≥2 citations per paragraph
- Conclusion: ≥3 citations

EXAMPLE:
WRONG: "Water quality varies significantly across regions. [CITE:ev_01][CITE:ev_02]"
RIGHT: "Water quality [CITE:ev_01] varies from 15 ppb [CITE:ev_02] in the Midwest to 45 ppb [CITE:ev_03] in the South [CITE:ev_04]."

YOU ARE AN EVIDENCE ASSEMBLER. Your job is to weave ALL relevant evidence into the narrative."""

    def process(self, state: ResearchState) -> ResearchState:
        """
        Generate research report from evidence.

        OPT-3: If sentences_to_revise exists and a draft_report already exists,
        perform targeted revision instead of full regeneration.

        FIX 73: Now injects LTM context as valid Evidence objects for citation.

        Args:
            state: Current research state with evidence_chain

        Returns:
            Updated state with draft_report
        """
        evidence_chain = state.get("evidence_chain", [])
        verification_results = state.get("verification_results", [])
        original_query = state.get("original_query", "")
        sub_queries = state.get("sub_queries", [])

        # =================================================================
        # FIX 73: Safe Evidence Merger - Inject LTM as valid Evidence
        # =================================================================
        # Convert LTM documents into Evidence objects so they can be cited
        # (satisfies Strict Mode from FIX 52) and pass Auditor verification.
        ltm_stage_context = state.get("ltm_stage_context", [])
        ltm_global_context = state.get("ltm_global_context", [])

        if ltm_stage_context or ltm_global_context:
            from src.orchestration.state import Evidence

            logger.info(
                f"[FIX 73] Merging LTM context: {len(ltm_stage_context)} stage + "
                f"{len(ltm_global_context)} global documents"
            )

            # Track existing URLs to prevent duplicates
            existing_urls = set()
            for ev in evidence_chain:
                url = ev.source_url if hasattr(ev, "source_url") else ev.get("source_url", "")
                if url:
                    existing_urls.add(url)

            ltm_evidence_added = 0

            # Inject stage-level LTM (most relevant to current research)
            for doc in ltm_stage_context[:10]:  # Cap at 10 to prevent bloat
                url = doc.get("metadata", {}).get("source_url", "LTM_STAGE_RECALL")
                # Skip if we already have this source
                if url in existing_urls and url != "LTM_STAGE_RECALL":
                    continue

                try:
                    doc_id = doc.get("id", "unknown")[:12]
                    content = doc.get("text", doc.get("content", ""))

                    if not content:
                        continue

                    ev = Evidence(
                        evidence_id=f"ltm_s_{doc_id}",
                        chunk_id=f"ltm_chunk_{doc_id}",
                        source_url=url,
                        text=content,
                        relevance_score=doc.get("metadata", {}).get("relevance_score", 0.85),
                        source_quality_score=0.9,  # LTM is trusted (already verified)
                        extraction_method="ltm_stage_recall",
                        quality_tier="GOLD",  # Memory is pre-verified
                        claims=[],
                        entities=[],
                    )
                    evidence_chain.append(ev)
                    existing_urls.add(url)
                    ltm_evidence_added += 1
                except Exception as e:
                    logger.warning(f"[FIX 73] Failed to convert LTM stage doc: {e}")

            # Inject global LTM (cross-stage insights)
            for doc in ltm_global_context[:5]:  # Cap at 5 for global
                url = doc.get("metadata", {}).get("source_url", "LTM_GLOBAL_RECALL")
                if url in existing_urls and url != "LTM_GLOBAL_RECALL":
                    continue

                try:
                    doc_id = doc.get("id", "unknown")[:12]
                    content = doc.get("content", doc.get("text", ""))

                    if not content:
                        continue

                    ev = Evidence(
                        evidence_id=f"ltm_g_{doc_id}",
                        chunk_id=f"ltm_gchunk_{doc_id}",
                        source_url=url,
                        text=content,
                        relevance_score=doc.get("metadata", {}).get("relevance_score", 0.80),
                        source_quality_score=0.85,
                        extraction_method="ltm_global_recall",
                        quality_tier="GOLD",
                        claims=[],
                        entities=[],
                    )
                    evidence_chain.append(ev)
                    existing_urls.add(url)
                    ltm_evidence_added += 1
                except Exception as e:
                    logger.warning(f"[FIX 73] Failed to convert LTM global doc: {e}")

            # Respect global cap to prevent context overflow (FIX 55 compatibility)
            MAX_TOTAL_EVIDENCE = 100
            if len(evidence_chain) > MAX_TOTAL_EVIDENCE:
                # Sort by quality tier then relevance
                def sort_key(ev):
                    tier_order = {"GOLD": 3, "SILVER": 2, "BRONZE": 1, "UNVERIFIED": 0}
                    tier = ev.quality_tier if hasattr(ev, "quality_tier") else ev.get("quality_tier", "UNVERIFIED")
                    relevance = ev.relevance_score if hasattr(ev, "relevance_score") else ev.get("relevance_score", 0)
                    return (tier_order.get(tier, 0), relevance)

                evidence_chain.sort(key=sort_key, reverse=True)
                evidence_chain = evidence_chain[:MAX_TOTAL_EVIDENCE]
                logger.warning(f"[FIX 73] Capped evidence at {MAX_TOTAL_EVIDENCE} items")

            logger.info(f"[FIX 73] Added {ltm_evidence_added} LTM evidence items (total: {len(evidence_chain)})")

            # Update state with merged evidence
            state["evidence_chain"] = evidence_chain

        if not evidence_chain:
            logger.warning("No evidence to synthesize")
            state["draft_report"] = "Insufficient evidence to generate report."
            return state

        # Build evidence context (needed for both generation and revision)
        evidence_context = self._build_evidence_context(evidence_chain, verification_results)

        # OPT-3: Check for revision mode (auditor feedback loop)
        sentences_to_revise = state.get("sentences_to_revise", [])
        existing_report = state.get("draft_report", "")
        if sentences_to_revise and existing_report and existing_report != "Insufficient evidence to generate report.":
            logger.info(
                f"[OPT-3] Revision mode: {len(sentences_to_revise)} sentences flagged by auditor. "
                f"Performing targeted revision instead of full regeneration."
            )
            # FIX 33: Context Slicing — pass only relevant evidence, not the full 500KB context
            # Extract evidence IDs cited in sentences being revised + small buffer
            sliced_context = self._build_sliced_evidence_context(
                sentences_to_revise, evidence_chain, verification_results
            )
            return self._revise_report(state, sentences_to_revise, sliced_context)

        logger.info(f"Synthesizing report from {len(evidence_chain)} evidence pieces")

        # FIX 58: Use iterative synthesis for deeper reports when enough evidence exists
        # This produces 4,000+ word reports via section-by-section synthesis
        use_iterative = state.get("use_iterative_synthesis", False)
        if not use_iterative and len(evidence_chain) >= 50:
            # Auto-enable for large evidence sets
            use_iterative = True
            logger.info("[FIX 58] Auto-enabling iterative synthesis for large evidence set")

        if use_iterative:
            logger.info("[FIX 58] Using iterative section-by-section synthesis for deeper report")
            iterative_synthesizer = IterativeSynthesizer(self)
            return iterative_synthesizer.synthesize_iteratively(state)

        # Generate report
        report = self._generate_report(
            original_query=original_query,
            sub_queries=sub_queries,
            evidence_context=evidence_context,
            state=state
        )

        # FIX 16A: Null check - _generate_report returns None on timeout
        if report is None:
            logger.error("Report generation failed (timeout or parsing failure)")
            state["error"] = "REPORT_GENERATION_FAILED"
            state["draft_report"] = "Report generation failed due to timeout."
            return state

        # FIX 2: Enforce citations in executive summary bullets
        report.executive_summary = self._enforce_exec_summary_citations(
            report.executive_summary,
            evidence_chain
        )

        # Build markdown report
        markdown = self._format_markdown(report)

        # Extract citations
        citations = self._extract_citations(report, evidence_chain)

        # Update state
        state["draft_report"] = markdown
        state["report_sections"] = {s.section_id: s.content for s in report.sections}
        state["citations"] = [c.model_dump() for c in citations]

        word_count = len(markdown.split())
        citation_count = len(citations)

        # FIX-124: Calculate and store perspective coverage statistics
        perspective_counts = {}
        for ev in evidence_chain:
            perspectives = getattr(ev, 'perspective_origins', [])
            for p in perspectives:
                perspective_counts[p] = perspective_counts.get(p, 0) + 1

        if perspective_counts:
            state["perspective_coverage"] = {
                "perspectives_represented": len(perspective_counts),
                "distribution": perspective_counts,
                "dominant_perspective": max(perspective_counts, key=perspective_counts.get) if perspective_counts else None,
                "balance_score": min(perspective_counts.values()) / max(perspective_counts.values()) if perspective_counts else 0,
            }
            logger.info(
                f"[FIX-124] Perspective coverage: {len(perspective_counts)} perspectives, "
                f"balance={state['perspective_coverage']['balance_score']:.2f}"
            )

        logger.info(f"Report generated: {word_count} words, {citation_count} citations")

        # ==========================================================================
        # FIX 81: Reflexive Word Count Expander
        # ==========================================================================
        # If report is too short and we have enough evidence, trigger cost-effective
        # expansion rather than expensive full iterative synthesis.
        MIN_WORD_COUNT = 2000
        MIN_EVIDENCE_FOR_EXPANSION = 15

        if word_count < MIN_WORD_COUNT and len(evidence_chain) >= MIN_EVIDENCE_FOR_EXPANSION:
            logger.info(
                f"[FIX 81] Report too short ({word_count} < {MIN_WORD_COUNT} words) "
                f"with {len(evidence_chain)} evidence pieces. Triggering reflexive expansion."
            )

            expanded_markdown = self._expand_short_report(
                markdown,
                evidence_chain,
                word_count,
                MIN_WORD_COUNT
            )

            if expanded_markdown:
                expanded_word_count = len(expanded_markdown.split())
                if expanded_word_count > word_count:
                    state["draft_report"] = expanded_markdown
                    logger.info(
                        f"[FIX 81] Report expanded: {word_count} -> {expanded_word_count} words "
                        f"(+{expanded_word_count - word_count})"
                    )
                else:
                    logger.warning(f"[FIX 81] Expansion did not increase word count, keeping original")

        return state

    def _revise_report(
        self,
        state: ResearchState,
        sentences_to_revise: List[Dict[str, Any]],
        evidence_context: str
    ) -> ResearchState:
        """OPT-3: Targeted revision of unfaithful sentences.

        Instead of regenerating the entire report from scratch (which produces
        identical output and wastes a full synthesis cycle), this method:
        1. Takes the existing draft report
        2. Identifies the specific unfaithful sentences flagged by the auditor
        3. Sends a focused revision prompt to the LLM
        4. Returns the revised report with only the flagged sentences changed

        Args:
            state: Current research state with draft_report
            sentences_to_revise: List of dicts with sentence, issues, suggested_citation, evidence_texts
            evidence_context: Pre-built evidence context string

        Returns:
            Updated state with revised draft_report
        """
        existing_report = state.get("draft_report", "")
        evidence_chain = state.get("evidence_chain", [])

        # FIX 57: Attempt Retrieval-for-Correction before revision
        # For sentences without evidence, try micro-search to find NEW evidence
        # This is "Surgery" instead of "Amputation" (deletion)
        sentences_without_evidence = [s for s in sentences_to_revise if not s.get("evidence_texts")]
        if sentences_without_evidence:
            logger.info(
                f"[FIX 57] {len(sentences_without_evidence)}/{len(sentences_to_revise)} sentences "
                f"lack evidence - attempting retrieval-for-correction"
            )
            sentences_to_revise, extended_chain = self._attempt_retrieval_for_correction(
                sentences_to_revise, evidence_chain
            )
            # Update state with extended evidence chain
            if len(extended_chain) > len(evidence_chain):
                state["evidence_chain"] = extended_chain
                evidence_chain = extended_chain
                # Rebuild evidence context with new evidence
                evidence_context = self._build_sliced_evidence_context(
                    sentences_to_revise, extended_chain, state.get("verification_results", [])
                )

        # FIX 30B: Batch revisions — cap at 15 sentences per revision pass
        # When >15 sentences are flagged, prioritize those with evidence snippets
        # (they are more likely to be fixable) and defer the rest to next revision cycle
        max_per_batch = 15
        if len(sentences_to_revise) > max_per_batch:
            # Sort: sentences with evidence first (more fixable), then without
            with_evidence = [s for s in sentences_to_revise if s.get("evidence_texts")]
            without_evidence = [s for s in sentences_to_revise if not s.get("evidence_texts")]
            prioritized = (with_evidence + without_evidence)[:max_per_batch]
            deferred_count = len(sentences_to_revise) - len(prioritized)
            logger.info(
                f"[FIX 30B] Batching revision: {len(sentences_to_revise)} flagged, "
                f"revising top {len(prioritized)}, deferring {deferred_count} to next cycle"
            )
            active_sentences = prioritized
        else:
            active_sentences = sentences_to_revise

        # Build revision items for the prompt
        revision_items = []
        for i, item in enumerate(active_sentences, 1):
            evidence_snippets = " | ".join(item.get("evidence_texts", []))
            revision_items.append(
                f"SENTENCE {i}: {item.get('sentence', '')}\n"
                f"  ISSUE: {item.get('issues', 'No specific issue noted')}\n"
                f"  SUGGESTED CITATION: {item.get('suggested_citation', 'N/A')}\n"
                f"  RELEVANT EVIDENCE: {evidence_snippets[:500] if evidence_snippets else 'N/A'}"
            )
        revision_block = "\n---\n".join(revision_items)

        # FIX 29: Count original sentences/words for anti-deletion check
        original_word_count = len(existing_report.split())
        original_cite_count = len(re.findall(r'\[CITE:[^\]]+\]', existing_report))

        messages = [
            SystemMessage(content=self.get_system_prompt()),
            HumanMessage(content=f"""REVISION MODE: You are revising an existing research report.
Do NOT regenerate the entire report. Only fix the specific unfaithful sentences listed below.

EXISTING REPORT ({original_word_count} words, {original_cite_count} citations):
{existing_report}

SENTENCES FLAGGED AS UNFAITHFUL ({len(active_sentences)} to revise this pass):
{revision_block}

EVIDENCE FOR RE-GROUNDING:
{self._truncate_evidence_with_warning(evidence_context, 500000)}

REVISION INSTRUCTIONS:
1. Find each flagged sentence in the report above
2. Rewrite it to be FAITHFUL to the provided evidence — search the evidence list for supporting data
3. Add proper [CITE:evidence_id] citations using the exact evidence_id from evidence
4. PREFERENCE ORDER for unfaithful sentences:
   a) REWRITE with evidence: Find supporting evidence and cite it
   b) HEDGE with evidence: "Some evidence suggests..." WITH a citation to the closest supporting evidence
   c) DELETE (ONLY IF): The claim is factually wrong AND no evidence in the list supports any version of it
5. FIX 34 (Conditional Deletion): You MAY delete a sentence ONLY if it makes a specific claim that contradicts or has zero support in the provided evidence. Do NOT delete sentences that can be hedged or rewritten.
6. CONSTRAINT: The revised report MUST maintain at least 70% of original word count ({int(original_word_count * 0.70)}+ words). Excessive deletion will be rejected.
7. Keep ALL other content unchanged — only modify the flagged sentences
8. Return the COMPLETE revised report as markdown
9. Report the exact number of sentences you changed in the sentences_revised field

FIX 107E - CITATION PRESERVATION (CRITICAL):
- PRESERVE all existing [CITE:xxx] tokens in sentences you do NOT modify
- When rewriting a flagged sentence, KEEP its existing citations if the evidence still supports the rewritten claim
- Only REMOVE a citation if the rewritten sentence no longer contains ANY claim that citation supported
- ADD new citations, but NEVER remove citations from unflagged sentences
- Target: Maintain at least {int(original_cite_count * 0.80)}+ citations ({original_cite_count} original)""")
        ]

        # FIX 30A: Scale timeout based on revision complexity
        # Base 120s + 5s per sentence to revise, cap at 300s
        revision_timeout = min(120 + 5 * len(active_sentences), 300)
        logger.info(
            f"[FIX 30A] Revision timeout: {revision_timeout}s "
            f"(base=120 + {len(active_sentences)} sentences * 5s)"
        )

        revised = self.call_llm_structured(messages, RevisedReport, timeout=revision_timeout)

        if revised is None:
            logger.warning("[OPT-3] Revision LLM call failed, keeping original report")
            return state

        # FIX 29: Anti-deletion safeguard — reject revisions that delete too much content
        revised_word_count = len(revised.revised_markdown.split())
        revised_cite_count = len(re.findall(r'\[CITE:[^\]]+\]', revised.revised_markdown))
        word_ratio = revised_word_count / max(original_word_count, 1)
        cite_ratio = revised_cite_count / max(original_cite_count, 1)

        # FIX 54: Relaxed safeguard for Strict Citation Mode (FIX 52)
        # FIX 52 tells LLM to DELETE uncited sentences (61% of content).
        # If we reject at 70%, the revision will always fail.
        # Lower threshold to 40% to allow aggressive cleanup without rejection.
        # Original: 0.70 -> New: 0.40
        if word_ratio < 0.40:
            # FIX-126C: Track consecutive revision rejections for deadlock detection
            rejection_count = state.get("revision_rejected_count", 0) + 1
            state["revision_rejected_count"] = rejection_count
            logger.warning(
                f"[FIX 54] Revision REJECTED: word count dropped {original_word_count} -> "
                f"{revised_word_count} ({word_ratio:.0%}). Keeping original report. "
                f"Threshold: >= 40% (relaxed for Strict Mode). "
                f"[FIX-126C] Rejection count: {rejection_count}"
            )
            return state

        # FIX 107E: Tightened citation preservation from 50% to 70%
        # Previous 50% threshold allowed losing half the citations during revision
        # Competitors maintain citation density through revision cycles
        if cite_ratio < 0.70:
            # FIX-126C: Track consecutive revision rejections for deadlock detection
            rejection_count = state.get("revision_rejected_count", 0) + 1
            state["revision_rejected_count"] = rejection_count
            logger.warning(
                f"[FIX 107E] Revision REJECTED: citation count dropped {original_cite_count} -> "
                f"{revised_cite_count} ({cite_ratio:.0%}). Keeping original report. "
                f"Threshold: >= 70% (tightened from 50%). "
                f"[FIX-126C] Rejection count: {rejection_count}"
            )
            return state

        # FIX-126C: Reset rejection counter on successful revision acceptance
        state["revision_rejected_count"] = 0

        if word_ratio < 0.90:
            logger.warning(
                f"[FIX 29] Revision accepted with WARNING: word count dropped "
                f"{original_word_count} -> {revised_word_count} ({word_ratio:.0%}). "
                f"Target: >= 90%."
            )

        # Update state with revised report
        state["draft_report"] = revised.revised_markdown
        state["sentences_to_revise"] = []  # Clear revision queue after applying

        logger.info(
            f"[OPT-3] Revision complete: {revised.sentences_revised} sentences revised, "
            f"{revised_word_count} words ({word_ratio:.0%} of original), "
            f"{revised_cite_count} citations ({cite_ratio:.0%} of original). "
            f"Notes: {revised.revision_notes}"
        )

        return state

    def _build_evidence_context(
        self,
        evidence_chain: List[Evidence],
        verification_results: List[VerificationResult]
    ) -> str:
        """Build evidence context for report generation.

        SPRINT 1 FIX 1.1 (Trash Compactor):
        Filter to ONLY GOLD/SILVER evidence that has verification support.
        This removes 61% noise (BRONZE/UNVERIFIED) that causes "Lost in the Middle" syndrome.

        Before: ALL 800 evidence items passed to synthesis (28% faithfulness)
        After: Only ~312 GOLD/SILVER verified items (target: 70-85% faithfulness)
        """
        # Create verification lookup - map evidence IDs to their verdicts
        verification_map = {}
        for v in verification_results:
            for ev_id in v.supporting_evidence:
                verification_map[ev_id] = {
                    "verdict": v.verdict,
                    "confidence": v.confidence,
                    "claim": v.claim_text
                }

        # SPRINT 1 FIX 1.1: Filter to ONLY GOLD/SILVER with verification support
        # This is the "Trash Compactor" - removes 61% noise before synthesis
        allowed_tiers = {"GOLD", "SILVER"}
        allowed_verdicts = {"supported", "partially_supported", "uncertain"}  # Not "refuted" or "insufficient"

        filtered_evidence = []
        for ev in evidence_chain:
            quality_tier = getattr(ev, 'quality_tier', 'UNVERIFIED')
            verification_info = verification_map.get(ev.evidence_id, {})
            verdict = verification_info.get("verdict", "unverified")

            # Include if: (GOLD or SILVER) AND (verified as supported/partially/uncertain OR not yet verified)
            if quality_tier in allowed_tiers:
                if verdict in allowed_verdicts or verdict == "unverified":
                    filtered_evidence.append(ev)

        # FIX: Starvation Safety Net - if GOLD/SILVER evidence is scarce, include BRONZE
        # This prevents the LLM from hallucinating a report with zero evidence
        MIN_EVIDENCE_THRESHOLD = 5
        if len(filtered_evidence) < MIN_EVIDENCE_THRESHOLD:
            logger.warning(
                f"STARVATION DETECTED: Only {len(filtered_evidence)} GOLD/SILVER evidence. "
                f"Opening gates to include BRONZE (threshold: {MIN_EVIDENCE_THRESHOLD})"
            )
            # Re-filter including BRONZE
            allowed_tiers.add("BRONZE")
            filtered_evidence = []
            for ev in evidence_chain:
                quality_tier = getattr(ev, 'quality_tier', 'UNVERIFIED')
                verification_info = verification_map.get(ev.evidence_id, {})
                verdict = verification_info.get("verdict", "unverified")
                if quality_tier in allowed_tiers:
                    if verdict in allowed_verdicts or verdict == "unverified":
                        filtered_evidence.append(ev)

        # Log filtering impact
        original_count = len(evidence_chain)
        filtered_count = len(filtered_evidence)
        logger.info(
            f"TRASH COMPACTOR: Filtered {original_count} -> {filtered_count} evidence pieces "
            f"({100 * (1 - filtered_count / max(original_count, 1)):.1f}% noise removed)"
        )

        # Sort by quality tier then relevance (GOLD first)
        tier_order = {"GOLD": 0, "SILVER": 1}
        sorted_evidence = sorted(
            filtered_evidence,
            key=lambda e: (tier_order.get(getattr(e, 'quality_tier', 'SILVER'), 1), -e.relevance_score)
        )

        # FIX-124: Calculate perspective coverage for balanced synthesis
        perspective_counts = {}
        for ev in sorted_evidence:
            perspectives = getattr(ev, 'perspective_origins', [])
            for p in perspectives:
                perspective_counts[p] = perspective_counts.get(p, 0) + 1

        # Build perspective coverage header for synthesis guidance
        perspective_header = ""
        if perspective_counts:
            total_perspectives = len(perspective_counts)
            coverage_str = ", ".join(f"{k}: {v}" for k, v in sorted(perspective_counts.items(), key=lambda x: -x[1]))
            perspective_header = f"""
=== STORM PERSPECTIVE COVERAGE (FIX-124) ===
Evidence spans {total_perspectives} perspectives: {coverage_str}
SYNTHESIS GUIDANCE: Ensure the report represents ALL perspectives proportionally.
Under-represented perspectives need extra attention in the narrative.
===
"""
            logger.info(f"[FIX-124] Perspective coverage for synthesis: {coverage_str}")

        context_parts = []
        for ev in sorted_evidence:
            verification_info = verification_map.get(ev.evidence_id, {})
            verdict = verification_info.get("verdict", "unverified")
            confidence = verification_info.get("confidence", 0.0)

            # Get quality tier (handle both old and new Evidence models)
            quality_tier = getattr(ev, 'quality_tier', 'UNVERIFIED')
            domain_type = getattr(ev, 'source_domain_type', 'unknown')

            # FIX-124: Include perspective origins in context
            perspectives = getattr(ev, 'perspective_origins', [])
            perspective_str = ", ".join(perspectives) if perspectives else "Unknown"

            context_parts.append(f"""
[{ev.evidence_id}]
Source: {ev.source_url}
Quality Tier: {quality_tier} ({domain_type})
Perspective(s): {perspective_str}
Quality Score: {ev.source_quality_score:.2f}
Relevance: {ev.relevance_score:.2f}
Verification: {verdict} (confidence: {confidence:.2f})

Text: {ev.text[:800]}

Claims: {', '.join(ev.claims[:3]) if ev.claims else 'None extracted'}
Entities: {', '.join(ev.entities[:5]) if ev.entities else 'None extracted'}
""")

        return perspective_header + "\n---\n".join(context_parts)

    def _build_atomic_fact_context(
        self,
        evidence_chain: List[Evidence],
    ) -> str:
        """FIX 98: Build atomic fact context for surgical synthesis.

        Extracts all atomic facts from evidence and formats them for the
        synthesizer to build paragraphs around (not summaries).

        Args:
            evidence_chain: List of Evidence objects with atomic_facts field

        Returns:
            Formatted atomic facts context string for synthesis
        """
        atomic_facts_by_category = {}
        total_facts = 0

        for ev in evidence_chain:
            # Get atomic facts from evidence (FIX 97/98 field)
            atomic_facts = getattr(ev, 'atomic_facts', [])
            if not atomic_facts:
                continue

            for fact in atomic_facts:
                if hasattr(fact, 'model_dump'):
                    fact_dict = fact.model_dump()
                elif isinstance(fact, dict):
                    fact_dict = fact
                else:
                    continue

                category = fact_dict.get('fact_category', 'general')
                if category not in atomic_facts_by_category:
                    atomic_facts_by_category[category] = []

                atomic_facts_by_category[category].append({
                    'evidence_id': ev.evidence_id,
                    'statement': fact_dict.get('statement', ''),
                    'direct_quote': fact_dict.get('direct_quote', ''),
                    'atomicity_score': fact_dict.get('atomicity_score', 0.8),
                    'entities': fact_dict.get('entities', []),
                    'source_url': ev.source_url,
                    'quality_tier': getattr(ev, 'quality_tier', 'UNVERIFIED'),
                })
                total_facts += 1

        if total_facts == 0:
            logger.warning("[FIX 98] No atomic facts found in evidence chain - falling back to text-based synthesis")
            return ""

        # Format atomic facts grouped by category
        context_parts = [
            f"=== FIX 98: ATOMIC FACTS FOR SURGICAL SYNTHESIS ({total_facts} total) ===\n"
        ]

        # Priority order for categories (most citeable first)
        category_priority = [
            "statistic", "measurement", "regulatory_threshold", "standard_reference",
            "causal_link", "comparative", "temporal_trend", "date_time",
            "named_entity", "geographic"
        ]

        for category in category_priority:
            facts = atomic_facts_by_category.get(category, [])
            if not facts:
                continue

            # Sort by atomicity score and quality tier
            tier_order = {"GOLD": 3, "SILVER": 2, "BRONZE": 1, "UNVERIFIED": 0}
            facts.sort(key=lambda f: (
                tier_order.get(f.get('quality_tier', 'UNVERIFIED'), 0),
                f.get('atomicity_score', 0)
            ), reverse=True)

            context_parts.append(f"\n## {category.upper()} FACTS ({len(facts)} items)")
            context_parts.append("-" * 60)

            for i, fact in enumerate(facts[:50], 1):  # Cap at 50 per category
                ev_id = fact['evidence_id']
                statement = fact['statement']
                quote = fact['direct_quote']
                tier = fact['quality_tier']
                entities = ', '.join(fact['entities'][:5]) if fact['entities'] else 'N/A'

                context_parts.append(f"""
FACT {i}: {statement}
  DIRECT QUOTE: "{quote}"
  CITATION: [CITE:{ev_id}]
  QUALITY: {tier}
  ENTITIES: {entities}
""")

        logger.info(
            f"[FIX 98] Built atomic fact context: {total_facts} facts across "
            f"{len(atomic_facts_by_category)} categories"
        )

        return "\n".join(context_parts)

    def _expand_short_report(
        self,
        current_report: str,
        evidence_chain: List[Evidence],
        current_word_count: int,
        target_word_count: int
    ) -> Optional[str]:
        """FIX 81: Reflexive expansion for reports that are too short.

        This is a cost-effective alternative to full iterative synthesis.
        Instead of regenerating the entire report, we ask the LLM to expand
        specific sections using the available evidence.

        Args:
            current_report: The current draft report markdown
            evidence_chain: List of Evidence objects
            current_word_count: Current word count
            target_word_count: Minimum target word count

        Returns:
            Expanded report markdown, or None if expansion failed
        """
        words_needed = target_word_count - current_word_count

        # Build condensed evidence context for expansion (top 30 by relevance)
        sorted_evidence = sorted(
            evidence_chain,
            key=lambda e: getattr(e, 'relevance_score', 0) if hasattr(e, 'relevance_score')
                          else e.get('relevance_score', 0) if isinstance(e, dict) else 0,
            reverse=True
        )[:30]

        evidence_snippets = []
        for ev in sorted_evidence:
            if hasattr(ev, 'model_dump'):
                ev_dict = ev.model_dump()
            elif isinstance(ev, dict):
                ev_dict = ev
            else:
                continue

            ev_id = ev_dict.get("evidence_id", "unknown")
            ev_text = ev_dict.get("text", "")[:600]
            evidence_snippets.append(f"[{ev_id}]: {ev_text}")

        evidence_context = "\n\n".join(evidence_snippets)

        expansion_prompt = f"""You are expanding a research report that is too short.

CURRENT REPORT ({current_word_count} words):
{current_report}

TARGET: Add approximately {words_needed} more words to reach {target_word_count} words minimum.

ADDITIONAL EVIDENCE TO INCORPORATE:
{evidence_context}

EXPANSION INSTRUCTIONS:
1. Identify sections that can be expanded with more detail from the evidence
2. Focus on the "Findings", "Analysis", and "Discussion" sections
3. Add specific data points, statistics, and examples from the evidence
4. Use [CITE:evidence_id] format for ALL new factual claims
5. Do NOT remove existing content - only ADD new content
6. Maintain the existing structure and formatting
7. Ensure smooth transitions between existing and new content

OUTPUT: Return the complete expanded report in markdown format."""

        try:
            from langchain_core.messages import SystemMessage, HumanMessage

            messages = [
                SystemMessage(content=self.get_system_prompt()),
                HumanMessage(content=expansion_prompt)
            ]

            # Use longer timeout for expansion
            response = self.call_llm(messages, timeout=180)

            if response and isinstance(response, str) and len(response) > len(current_report) * 0.8:
                return response
            else:
                logger.warning("[FIX 81] Expansion response was too short or invalid")
                return None

        except Exception as e:
            logger.error(f"[FIX 81] Report expansion failed: {e}")
            return None

    def _build_sliced_evidence_context(
        self,
        sentences_to_revise: List[Dict[str, Any]],
        evidence_chain: List[Evidence],
        verification_results: List[VerificationResult]
    ) -> str:
        """FIX 33: Build SLICED evidence context for revision.

        FIX 83 (AMNESIA CURE): Changed from aggressive slicing to FULL CONTEXT MODE.
        FIX 105B (CONTEXT FLOOD): Gemini Deep Audit recommendation - pass ALL evidence.

        BEFORE (FIX 33 Original): Sliced 100 -> 9 evidence pieces
        PROBLEM: Synthesizer couldn't see evidence to fix unfaithful claims
        RESULT: Sentences deleted -> Section faithfulness dropped -> FIX 62 amputated

        AFTER (FIX 83): Pass up to 200 evidence pieces (was 30)
        AFTER (FIX 105B): FLOOD MODE - Pass ALL GOLD/SILVER evidence without slicing

        The Gemini Deep Audit identified "Contextual Amnesia" as a root cause:
        - FIX 33 context slicing hid evidence from the revision loop
        - Synthesizer couldn't find citations because evidence was filtered out
        - This caused the "Death Spiral" where unfaithful sentences couldn't be fixed

        FIX 105B Solution: FLOOD MODE
        - For revision loop, pass ALL GOLD/SILVER evidence (no cap)
        - KIMI K2.5 has 128K context - use it fully
        - Let the LLM find the right evidence instead of pre-filtering
        """
        import os

        # FIX 105B: Check for FLOOD MODE (pass all evidence during revision)
        flood_mode = os.environ.get("POLARIS_REVISION_FLOOD_MODE", "1") == "1"

        if flood_mode:
            # FLOOD MODE: Pass ALL GOLD/SILVER evidence without any slicing
            # This prevents "Contextual Amnesia" where evidence is hidden from revision
            allowed_tiers = {"GOLD", "SILVER"}
            flood_evidence = [
                ev for ev in evidence_chain
                if getattr(ev, 'quality_tier', 'UNKNOWN') in allowed_tiers
            ]

            # Sort by relevance score descending
            flood_evidence.sort(key=lambda e: -getattr(e, 'relevance_score', 0))

            logger.info(
                f"[FIX 105B] FLOOD MODE: Passing ALL {len(flood_evidence)} GOLD/SILVER evidence "
                f"(from {len(evidence_chain)} total) for revision context"
            )

            # Build context string for flood mode
            verification_map = {v.supporting_evidence[0]: v for v in verification_results if v.supporting_evidence}

            context_parts = []
            for ev in flood_evidence:
                v_info = verification_map.get(ev.evidence_id, None)
                verdict = v_info.verdict if v_info else "unverified"
                confidence = v_info.confidence if v_info else 0.0

                context_parts.append(f"""
[{ev.evidence_id}]
Source: {ev.source_url}
Quality: {getattr(ev, 'quality_tier', 'UNKNOWN')}
Relevance: {ev.relevance_score:.2f}
Verification: {verdict} ({confidence:.2f})

Text: {ev.text[:800]}
""")

            return "\n---\n".join(context_parts)

        # Original FIX 83 logic (non-flood mode) below
        # Collect evidence IDs from sentences being revised
        relevant_ids = set()

        for sent_info in sentences_to_revise:
            # Extract cited IDs from the sentence text
            sentence = sent_info.get("sentence", "")
            cited = re.findall(r'\[CITE:(ev_\d+)\]', sentence)
            relevant_ids.update(cited)

            # Also include any suggested citations from the auditor
            suggested = sent_info.get("suggested_citation", "")
            if suggested and suggested.startswith("ev_"):
                relevant_ids.add(suggested)

            # Include evidence IDs from evidence_texts (if auditor provided them)
            evidence_texts = sent_info.get("evidence_texts", [])
            for ev_text in evidence_texts:
                if isinstance(ev_text, dict) and "evidence_id" in ev_text:
                    relevant_ids.add(ev_text["evidence_id"])

            # FIX 42: Smart Slicing - Use Containment Score instead of Jaccard
            if not cited and not suggested:
                matching_evidence = self._find_evidence_by_containment(sentence, evidence_chain)
                if matching_evidence:
                    relevant_ids.update(matching_evidence)
                    logger.debug(f"[FIX 42] Containment matched {len(matching_evidence)} evidence for uncited sentence")

        # Build evidence lookup
        evidence_map = {ev.evidence_id: ev for ev in evidence_chain}

        # Get the relevant evidence
        relevant_evidence = [evidence_map[eid] for eid in relevant_ids if eid in evidence_map]

        # FIX 33 Safety Net: If we have very few relevant evidence (<5), add top GOLD evidence
        MIN_CONTEXT_EVIDENCE = 5
        if len(relevant_evidence) < MIN_CONTEXT_EVIDENCE:
            gold_evidence = [ev for ev in evidence_chain if getattr(ev, 'quality_tier', '') == 'GOLD']
            gold_evidence.sort(key=lambda e: -e.relevance_score)
            for ev in gold_evidence[:MIN_CONTEXT_EVIDENCE]:
                if ev.evidence_id not in relevant_ids:
                    relevant_evidence.append(ev)

        # FIX 83: AMNESIA CURE - Increased from 30 to 200 evidence pieces
        # Gemini 2.5 Pro has 2M token context - 200 evidence pieces (~150KB) is fine
        # This prevents the "Revision Death Spiral" where evidence is hidden
        MAX_REVISION_EVIDENCE = 200  # Was 30 (FIX 33 original)

        # FIX 83: If we have fewer than 200 evidence pieces, include ALL of them
        # Only slice if we truly have more than 200
        if len(evidence_chain) <= MAX_REVISION_EVIDENCE:
            # FULL CONTEXT MODE: Don't slice at all
            relevant_evidence = list(evidence_chain)
            logger.info(
                f"[FIX 83] FULL CONTEXT MODE: Using all {len(relevant_evidence)} evidence pieces (no slicing)"
            )
        elif len(relevant_evidence) > MAX_REVISION_EVIDENCE:
            # Prioritize: cited evidence first, then by quality/relevance
            cited_ev = [ev for ev in relevant_evidence if ev.evidence_id in relevant_ids]
            extra_ev = [ev for ev in relevant_evidence if ev.evidence_id not in relevant_ids]
            relevant_evidence = cited_ev[:MAX_REVISION_EVIDENCE] + extra_ev[:MAX_REVISION_EVIDENCE - len(cited_ev)]
            logger.info(
                f"[FIX 83] Soft Slicing: {len(evidence_chain)} -> {len(relevant_evidence)} evidence pieces "
                f"(from {len(relevant_ids)} cited IDs, cap={MAX_REVISION_EVIDENCE})"
            )
        else:
            # FIX 83: Add more evidence from the pool if we have room
            # This ensures we don't have blind spots during revision
            remaining_slots = MAX_REVISION_EVIDENCE - len(relevant_evidence)
            if remaining_slots > 0:
                unused_evidence = [ev for ev in evidence_chain if ev.evidence_id not in relevant_ids]
                # Sort by relevance score descending
                unused_evidence.sort(key=lambda e: -getattr(e, 'relevance_score', 0))
                for ev in unused_evidence[:remaining_slots]:
                    relevant_evidence.append(ev)

            logger.info(
                f"[FIX 83] Expanded Context: {len(evidence_chain)} -> {len(relevant_evidence)} evidence pieces "
                f"(from {len(relevant_ids)} cited IDs + {remaining_slots} bonus)"
            )

        # Build context string (same format as _build_evidence_context)
        verification_map = {v.supporting_evidence[0]: v for v in verification_results if v.supporting_evidence}

        context_parts = []
        for ev in relevant_evidence:
            v_info = verification_map.get(ev.evidence_id, None)
            verdict = v_info.verdict if v_info else "unverified"
            confidence = v_info.confidence if v_info else 0.0

            context_parts.append(f"""
[{ev.evidence_id}]
Source: {ev.source_url}
Quality: {getattr(ev, 'quality_tier', 'UNKNOWN')}
Relevance: {ev.relevance_score:.2f}
Verification: {verdict} ({confidence:.2f})

Text: {ev.text[:800]}
""")

        return "\n---\n".join(context_parts)

    def _find_evidence_by_containment(
        self,
        sentence: str,
        evidence_chain: List[Evidence],
        threshold: float = 0.4,
        max_matches: int = 3
    ) -> List[str]:
        """FIX 44: Find evidence using EMBEDDING-BASED semantic similarity.

        Replaces FIX 42's word-overlap containment with true semantic matching.
        Uses sentence-transformers for embeddings and cosine similarity.

        Falls back to word-overlap containment if sentence-transformers unavailable.

        Args:
            sentence: The uncited sentence to find evidence for
            evidence_chain: Full evidence chain to search
            threshold: Minimum similarity (0.4 for embeddings, 0.4 for word-overlap fallback)
            max_matches: Maximum number of matching evidence IDs to return

        Returns:
            List of evidence IDs that match the sentence
        """
        # Clean sentence
        clean_sentence = re.sub(r'\[CITE:[^\]]+\]', '', sentence).strip()

        if len(clean_sentence) < 20:
            return []  # Too short for meaningful matching

        # FIX 44: Try embedding-based similarity first
        embedding_matches = self._find_by_embedding(clean_sentence, evidence_chain, threshold, max_matches)
        if embedding_matches is not None:
            return embedding_matches

        # Fallback to word-overlap containment (FIX 42 logic)
        logger.debug("[FIX 44] Embedding unavailable, falling back to word-overlap")
        return self._find_by_word_overlap(clean_sentence, evidence_chain, threshold, max_matches)

    def _find_by_embedding(
        self,
        sentence: str,
        evidence_chain: List[Evidence],
        threshold: float = 0.4,
        max_matches: int = 3
    ) -> List[str]:
        """FIX 44: Embedding-based semantic similarity matching.

        Uses sentence-transformers all-MiniLM-L6-v2 (fast, good quality).
        FIX 76: Now uses singleton embedding service to avoid RAM duplication.
        Returns None if sentence-transformers is not available.
        """
        try:
            # FIX 76: Use singleton embedding service instead of local import
            from src.utils.embedding_service import get_embedding_service
            import numpy as np

            embed_service = get_embedding_service()
            logger.debug("[FIX 76] Using singleton embedding service for semantic matching")

            # Encode sentence using singleton
            sentence_embedding = np.array(embed_service.embed(sentence))

            # Encode evidence (batch for efficiency) - FIX 76: use singleton
            evidence_texts = [ev.text[:500] for ev in evidence_chain]  # Truncate for speed
            if not evidence_texts:
                return []

            evidence_embeddings = np.array(embed_service.embed_batch(evidence_texts))

            # Compute cosine similarities
            # Normalize for cosine similarity
            sentence_norm = sentence_embedding / np.linalg.norm(sentence_embedding)
            evidence_norms = evidence_embeddings / np.linalg.norm(evidence_embeddings, axis=1, keepdims=True)
            similarities = np.dot(evidence_norms, sentence_norm)

            # Find matches above threshold
            matches = []
            for i, sim in enumerate(similarities):
                if sim >= threshold:
                    # Weight by quality tier
                    tier_boost = {"GOLD": 0.1, "SILVER": 0.05, "BRONZE": 0, "UNVERIFIED": -0.05}
                    quality_tier = getattr(evidence_chain[i], 'quality_tier', 'UNVERIFIED')
                    score = float(sim) + tier_boost.get(quality_tier, 0)
                    matches.append((evidence_chain[i].evidence_id, score))

            # Sort by score descending
            matches.sort(key=lambda x: -x[1])
            result = [ev_id for ev_id, _ in matches[:max_matches]]

            if result:
                logger.debug(f"[FIX 44] Embedding matched {len(result)} evidence (top sim={similarities.max():.2f})")

            return result

        except ImportError:
            logger.warning("[FIX 44] sentence-transformers not installed. Install with: pip install sentence-transformers")
            return None
        except Exception as e:
            logger.warning(f"[FIX 44] Embedding matching failed: {e}")
            return None

    def _find_by_word_overlap(
        self,
        sentence: str,
        evidence_chain: List[Evidence],
        threshold: float = 0.4,
        max_matches: int = 3
    ) -> List[str]:
        """FIX 42 fallback: Word-overlap containment matching.

        FIX 56: Acronym Support - lowered word length from >3 to >=2 with stopwords.
        Critical for water quality domain: EPA, CDC, NSF, WHO, pH, UV, RO would be stripped.
        """
        # FIX 56: Stopwords to filter instead of length-only filtering
        STOPWORDS = {
            "the", "and", "for", "that", "this", "with", "from", "are", "was", "not",
            "but", "in", "on", "at", "to", "by", "of", "is", "it", "or", "as", "an", "be",
            "has", "have", "had", "been", "were", "will", "can", "may", "its", "than"
        }

        sentence_lower = sentence.lower()
        sentence_words = set(
            word.strip('.,!?()[]{}:;"\'')
            for word in sentence_lower.split()
            if len(word) >= 2 and word.strip('.,!?()[]{}:;"\'') not in STOPWORDS  # FIX 56
        )

        if len(sentence_words) < 3:
            return []

        matches = []
        for ev in evidence_chain:
            ev_words = set(
                word.strip('.,!?()[]{}:;"\'')
                for word in ev.text.lower().split()
                if len(word) >= 2 and word.strip('.,!?()[]{}:;"\'') not in STOPWORDS  # FIX 56
            )

            if not ev_words:
                continue

            intersection = len(sentence_words & ev_words)
            sent_len = len(sentence_words)
            containment = intersection / sent_len if sent_len > 0 else 0

            if containment >= threshold:
                tier_boost = {"GOLD": 0.2, "SILVER": 0.1, "BRONZE": 0, "UNVERIFIED": -0.1}
                quality_tier = getattr(ev, 'quality_tier', 'UNVERIFIED')
                score = containment + tier_boost.get(quality_tier, 0)
                matches.append((ev.evidence_id, score))

        matches.sort(key=lambda x: -x[1])
        return [ev_id for ev_id, _ in matches[:max_matches]]

    def _truncate_evidence_with_warning(self, evidence_context: str, max_chars: int = 500000) -> str:
        """Truncate evidence context with warning if needed.

        SPRINT 1: Context truncation fix - increased limit from 15000 to 20000
        SPRINT 2 FIX: Increased to 50000 chars (Gemini 3 Pro supports 1M context)
        FIX 18: Increased to 500000 chars - Gemini 3 Pro supports 1M+ tokens.
        Previous 20000 char limit caused 87% evidence loss (starvation).
        """
        if len(evidence_context) <= max_chars:
            return evidence_context

        logger.warning(
            f"Evidence context truncated: {len(evidence_context)} -> {max_chars} chars. "
            f"Consider filtering more aggressively in Trash Compactor."
        )
        return evidence_context[:max_chars] + "\n\n[... TRUNCATED - see full evidence in state ...]"

    def _generate_report(
        self,
        original_query: str,
        sub_queries: List,
        evidence_context: str,
        state: ResearchState
    ) -> FullReport:
        """Generate the full report using LLM.

        FIX 98: Now includes atomic facts context for surgical synthesis.
        """
        evidence_chain = state.get("evidence_chain", [])

        # Build sub-queries context
        sq_context = ""
        if sub_queries:
            sq_context = "\n".join([
                f"- {sq.query_text} ({sq.expected_data_type})"
                for sq in sub_queries[:10]
            ])

        # FIX 98: Build atomic fact context for surgical synthesis
        atomic_fact_context = self._build_atomic_fact_context(evidence_chain)

        # Quality metrics
        quality = state.get("quality_metrics", {})
        if hasattr(quality, "faithfulness"):
            faithfulness = quality.faithfulness
            precision = quality.context_precision
        else:
            faithfulness = quality.get("faithfulness", 0.0) if isinstance(quality, dict) else 0.0
            precision = quality.get("context_precision", 0.0) if isinstance(quality, dict) else 0.0

        # FIX 98: Build prompt with atomic facts prioritized
        prompt_content = f"""Generate a comprehensive research report using SURGICAL FACT-BASED SYNTHESIS.

RESEARCH QUESTION:
{original_query}

APPLICATION: {state.get('application', 'Unknown')}
REGION: {state.get('region', 'GLOBAL')}
STAGE: {state.get('stage', 1)}

SUB-QUESTIONS:
{sq_context if sq_context else 'No sub-questions defined'}

"""
        # FIX 98: Include atomic facts FIRST if available (prioritized for synthesis)
        if atomic_fact_context:
            prompt_content += f"""{atomic_fact_context}

=== SURGICAL SYNTHESIS INSTRUCTIONS ===
BUILD your report AROUND the atomic facts above. Each paragraph should:
1. START with a cited atomic fact (use the direct quote)
2. ADD minimal connecting context
3. CHAIN to related facts using transitions
4. Target: 130+ citations using the [CITE:evidence_id] format from each fact

"""

        prompt_content += f"""EVIDENCE (for additional context):
{self._truncate_evidence_with_warning(evidence_context, 300000)}

VERIFICATION STATISTICS:
- Total claims: {state.get('claims_total', 0)}
- Supported: {state.get('claims_supported', 0)}
- Refuted: {state.get('claims_refuted', 0)}
- Uncertain: {state.get('claims_uncertain', 0)}
- Hallucination rate: {state.get('hallucination_rate', 0):.2%}

QUALITY METRICS:
- Faithfulness: {faithfulness:.2f}
- Context precision: {precision:.2f}

Generate a complete report with:
1. Executive summary with 5+ key findings (EACH with citation)
2. Introduction explaining scope and methodology
3. Findings section organized by atomic fact themes
4. Analysis synthesizing across sources
5. Conclusions answering the research question
6. Recommendations
7. References list

CRITICAL REQUIREMENTS:
- Use [CITE:evidence_id] for ALL factual claims
- Target 5,000-10,000 words (proportional to evidence depth)
- Target 130+ unique citations
- PREFER direct quotes from atomic facts
- Build paragraphs AROUND facts, not summaries"""

        messages = [
            SystemMessage(content=self.get_system_prompt()),
            HumanMessage(content=prompt_content)
        ]

        try:
            # FIX 31: Scale initial synthesis timeout based on evidence volume
            evidence_count = len(state.get("evidence_chain", state.get("evidence", [])))
            synthesis_timeout = min(120 + evidence_count // 5, 300)
            logger.info(f"[FIX 31] Initial synthesis timeout: {synthesis_timeout}s for {evidence_count} evidence pieces")
            report: FullReport = self.call_llm_structured(messages, FullReport, timeout=synthesis_timeout)
            # FIX 12: Handle None return from call_llm_structured (timeout or parse failure)
            if report is None:
                logger.warning("Synthesizer LLM returned None (timeout or parsing failure)")
                return None
            return report
        except Exception as e:
            logger.error(f"Report generation failed: {e}")
            # Return minimal report with proper ReportMetadata
            return FullReport(
                title=f"Research Report: {original_query[:50]}",
                executive_summary=ExecutiveSummary(
                    key_findings=["Report generation encountered errors"],
                    methodology_summary="Multi-source research with verification",
                    confidence_statement="Unable to assess confidence due to errors",
                    limitations=["Automated report generation failed"],
                    recommendations=["Manual review required"]
                ),
                sections=[
                    ReportSection(
                        section_id="error",
                        title="Generation Error",
                        content=f"Report generation failed: {str(e)}",
                        word_count=10,
                        citations_used=[]
                    )
                ],
                references=[],
                metadata=ReportMetadata(
                    generated_at=datetime.now(timezone.utc).isoformat(),
                    vector_id=state.get('vector_id', 'unknown'),
                    total_evidence=state.get('claims_total', 0),
                    total_sources=0,
                    confidence_level="low",
                    word_count=10,
                    citation_count=0
                )
            )

    def _format_markdown(self, report: FullReport) -> str:
        """Format report as markdown."""
        md = []

        # Title
        md.append(f"# {report.title}")
        md.append("")

        # Executive Summary
        md.append("## Executive Summary")
        md.append("")
        md.append("### Key Findings")
        for finding in report.executive_summary.key_findings:
            md.append(f"- {finding}")
        md.append("")
        md.append(f"**Methodology:** {report.executive_summary.methodology_summary}")
        md.append("")
        md.append(f"**Confidence:** {report.executive_summary.confidence_statement}")
        md.append("")

        if report.executive_summary.limitations:
            md.append("### Limitations")
            for lim in report.executive_summary.limitations:
                md.append(f"- {lim}")
            md.append("")

        if report.executive_summary.recommendations:
            md.append("### Recommendations")
            for rec in report.executive_summary.recommendations:
                md.append(f"- {rec}")
            md.append("")

        # Sections
        for section in report.sections:
            md.append(f"## {section.title}")
            md.append("")
            md.append(section.content)
            md.append("")

        # References
        if report.references:
            # FIX 32: Filter out empty citations (trailing empty objects from LLM)
            valid_refs = [ref for ref in report.references if ref.citation_id and ref.source_url]
            if valid_refs:
                md.append("## References")
                md.append("")
                for ref in valid_refs:
                    md.append(f"[{ref.citation_id}] {ref.title}. {ref.source_url}. Accessed: {ref.access_date}")
                md.append("")

        return "\n".join(md)

    def _extract_citations(
        self,
        report: FullReport,
        evidence_chain: List[Evidence]
    ) -> List[Citation]:
        """Extract and build citation list from report."""
        import re

        # Find all [CITE:xxx] tokens
        all_text = " ".join([s.content for s in report.sections])
        citation_pattern = r'\[CITE:([^\]]+)\]'
        cited_ids = set(re.findall(citation_pattern, all_text))

        # Build evidence lookup
        evidence_map = {ev.evidence_id: ev for ev in evidence_chain}

        citations = []
        for cite_id in cited_ids:
            ev = evidence_map.get(cite_id)
            if ev:
                citations.append(Citation(
                    citation_id=f"CITE:{cite_id}",
                    chunk_id=ev.chunk_id,
                    source_url=ev.source_url,
                    title=ev.source_url.split("/")[-1] if ev.source_url else "Unknown",
                    excerpt=ev.text[:200],
                    access_date=datetime.now(timezone.utc).strftime("%Y-%m-%d")
                ))

        # Also include from report references
        for ref in report.references:
            if ref.citation_id not in [c.citation_id for c in citations]:
                citations.append(ref)

        return citations

    def _enforce_exec_summary_citations(
        self,
        exec_summary: ExecutiveSummary,
        evidence_chain: List[Evidence]
    ) -> ExecutiveSummary:
        """
        Ensure all executive summary bullets have citations.

        FIX 2: Post-generation validation for executive summary bullets.
        Uses keyword matching to find appropriate evidence (not hardcoded).

        Args:
            exec_summary: The generated executive summary
            evidence_chain: List of Evidence objects to draw citations from

        Returns:
            ExecutiveSummary with citations added to findings that lack them
        """
        import re
        citation_pattern = r'\[CITE:[^\]]+\]'

        enhanced_findings = []
        citations_added = 0

        for bullet in exec_summary.key_findings:
            if re.search(citation_pattern, bullet):
                # Already has citation
                enhanced_findings.append(bullet)
            else:
                # Try to find matching evidence and add citation
                best_match = self._find_best_evidence_match(bullet, evidence_chain)
                if best_match:
                    # Add citation at end of bullet
                    enhanced = bullet.rstrip('.')
                    enhanced = f"{enhanced} [CITE:{best_match}]."
                    enhanced_findings.append(enhanced)
                    citations_added += 1
                    logger.debug(f"Added citation {best_match} to exec summary bullet")
                else:
                    # Keep without citation (will be flagged by auditor)
                    enhanced_findings.append(bullet)
                    logger.warning(f"No matching evidence found for exec summary bullet: {bullet[:50]}...")

        if citations_added > 0:
            logger.info(f"FIX 2: Added {citations_added} citations to executive summary bullets")

        exec_summary.key_findings = enhanced_findings
        return exec_summary

    def _find_best_evidence_match(
        self,
        sentence: str,
        evidence_chain: List[Evidence]
    ) -> Optional[str]:
        """
        Find evidence that best supports a sentence using keyword overlap.

        FIX 2 Helper: Uses keyword matching weighted by quality tier.

        Args:
            sentence: The sentence to find evidence for
            evidence_chain: List of Evidence objects to search

        Returns:
            Evidence ID of best match, or None if no good match found
        """
        # FIX 56: Stopwords for acronym support (EPA, CDC, NSF, pH, UV, RO)
        STOPWORDS = {
            "the", "and", "for", "that", "this", "with", "from", "are", "was", "not",
            "but", "in", "on", "at", "to", "by", "of", "is", "it", "or", "as", "an", "be",
            "has", "have", "had", "been", "were", "will", "can", "may", "its", "than"
        }

        # Tokenize sentence - FIX 56: len >= 2 with stopwords instead of > 3
        sentence_words = set(
            word.lower() for word in sentence.split()
            if len(word) >= 2 and word.isalnum() and word.lower() not in STOPWORDS
        )

        if not sentence_words:
            return None

        best_score = 0.0
        best_id = None

        # Quality tier weights
        tier_weights = {
            "GOLD": 1.5,
            "SILVER": 1.2,
            "BRONZE": 0.8,
            "UNVERIFIED": 0.5
        }

        for ev in evidence_chain:
            # Tokenize evidence text - FIX 56: len >= 2 with stopwords
            ev_words = set(
                word.lower() for word in ev.text.split()
                if len(word) >= 2 and word.isalnum() and word.lower() not in STOPWORDS
            )

            # Calculate word overlap
            overlap = len(sentence_words & ev_words)

            # Weight by quality tier
            quality_tier = getattr(ev, 'quality_tier', 'UNVERIFIED')
            tier_weight = tier_weights.get(quality_tier, 0.5)

            # Also consider relevance score
            relevance_weight = getattr(ev, 'relevance_score', 0.5)

            score = overlap * tier_weight * (1.0 + relevance_weight)

            # Minimum 3 word overlap required for a match
            if score > best_score and overlap >= 3:
                best_score = score
                best_id = ev.evidence_id

        return best_id

    # =========================================================================
    # FIX 57: Retrieval-for-Correction (Micro-Search)
    # =========================================================================

    def _micro_search_for_claim(
        self,
        claim: str,
        max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """FIX 57: Perform a targeted micro-search for a specific claim.

        When the auditor flags a sentence as unfaithful and we cannot find
        supporting evidence in the existing chain, this method performs a
        targeted web search to find NEW evidence that might support the claim.

        This is the "Surgery" approach vs "Amputation" (deletion):
        - Instead of deleting unfaithful claims, we try to find evidence for them
        - If evidence is found, the claim can be kept with proper citation
        - If no evidence is found, THEN we delete

        Args:
            claim: The unfaithful sentence/claim to search for
            max_results: Maximum search results to return

        Returns:
            List of search results with url, title, snippet
        """
        api_key = os.environ.get("SERPER_API_KEY")
        if not api_key:
            logger.warning("[FIX 57] SERPER_API_KEY not set, micro-search disabled")
            return []

        # Extract key terms from claim for search query
        # Remove citation tokens and clean up
        clean_claim = re.sub(r'\[CITE:[^\]]+\]', '', claim).strip()

        # Truncate to reasonable search query length
        if len(clean_claim) > 200:
            clean_claim = clean_claim[:200]

        url = "https://google.serper.dev/search"
        payload = {
            "q": clean_claim,
            "num": max_results,
            "gl": "us",
        }
        headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()

            results = []
            for r in data.get("organic", []):
                results.append({
                    "url": r.get("link", ""),
                    "title": r.get("title", ""),
                    "snippet": r.get("snippet", ""),
                })

            logger.info(f"[FIX 57] Micro-search for claim returned {len(results)} results")
            return results

        except Exception as e:
            logger.warning(f"[FIX 57] Micro-search failed: {e}")
            return []

    def _attempt_retrieval_for_correction(
        self,
        sentences_to_revise: List[Dict[str, Any]],
        evidence_chain: List[Evidence]
    ) -> Tuple[List[Dict[str, Any]], List[Evidence]]:
        """FIX 57 + FIX 99: Rescue Mode - aggressive evidence retrieval.

        FIX 99 ENHANCEMENT: Multi-strategy rescue before deletion.
        Before sending sentences to revision (where they might be deleted),
        try MULTIPLE strategies to find evidence:
        1. Direct claim search (FIX 57 original)
        2. Entity-focused search (new)
        3. Number/statistic-focused search (new)
        4. LTM memory search (new)

        Args:
            sentences_to_revise: List of unfaithful sentence info dicts
            evidence_chain: Existing evidence chain

        Returns:
            Tuple of (updated sentences_to_revise, updated evidence_chain with new evidence)
        """
        new_evidence = []
        updated_sentences = []
        evidence_found_count = 0
        rescue_attempts = 0

        for sent_info in sentences_to_revise:
            sentence = sent_info.get("sentence", "")

            # Skip if already has evidence texts (auditor found matches)
            if sent_info.get("evidence_texts"):
                updated_sentences.append(sent_info)
                continue

            # FIX 99: Lower threshold for rescue (was 50, now 30)
            if len(sentence) < 30:
                updated_sentences.append(sent_info)
                continue

            rescue_attempts += 1
            found_evidence = False

            # =================================================================
            # FIX 99 Strategy 1: Direct claim search (original FIX 57)
            # =================================================================
            search_results = self._micro_search_for_claim(sentence, max_results=5)

            if search_results:
                for result in search_results[:2]:
                    snippet = result.get("snippet", "")
                    if len(snippet) > 30:  # FIX 99: Lower threshold (was 50)
                        new_ev_id = f"ev_rescue_{len(evidence_chain) + len(new_evidence):04d}"
                        new_ev = Evidence(
                            evidence_id=new_ev_id,
                            chunk_id=f"rescue_{new_ev_id}",
                            source_url=result.get("url", ""),
                            text=snippet,
                            relevance_score=0.7,
                            source_quality_score=0.6,
                            extraction_method="rescue_mode",
                            claims=[],
                            entities=[],
                            quality_tier="SILVER",
                        )
                        new_evidence.append(new_ev)

                        if "evidence_texts" not in sent_info:
                            sent_info["evidence_texts"] = []
                        sent_info["evidence_texts"].append(snippet[:300])
                        sent_info["suggested_citation"] = new_ev_id

                        evidence_found_count += 1
                        found_evidence = True
                        logger.info(
                            f"[FIX 99] RESCUE SUCCESS (direct search): {new_ev_id} for: "
                            f"{sentence[:60]}..."
                        )
                        break

            # =================================================================
            # FIX 99 Strategy 2: Entity-focused search
            # =================================================================
            if not found_evidence:
                entities = self._extract_entities_for_rescue(sentence)
                if entities:
                    entity_query = " ".join(entities[:5])
                    entity_results = self._micro_search_for_claim(entity_query, max_results=3)

                    for result in entity_results[:2]:
                        snippet = result.get("snippet", "")
                        if len(snippet) > 30 and self._has_sentence_overlap(sentence, snippet):
                            new_ev_id = f"ev_rescue_ent_{len(evidence_chain) + len(new_evidence):04d}"
                            new_ev = Evidence(
                                evidence_id=new_ev_id,
                                chunk_id=f"rescue_ent_{new_ev_id}",
                                source_url=result.get("url", ""),
                                text=snippet,
                                relevance_score=0.65,
                                source_quality_score=0.55,
                                extraction_method="rescue_mode_entity",
                                claims=[],
                                entities=entities,
                                quality_tier="SILVER",
                            )
                            new_evidence.append(new_ev)

                            if "evidence_texts" not in sent_info:
                                sent_info["evidence_texts"] = []
                            sent_info["evidence_texts"].append(snippet[:300])
                            sent_info["suggested_citation"] = new_ev_id

                            evidence_found_count += 1
                            found_evidence = True
                            logger.info(
                                f"[FIX 99] RESCUE SUCCESS (entity search): {new_ev_id} for: "
                                f"{sentence[:60]}..."
                            )
                            break

            # =================================================================
            # FIX 99 Strategy 3: Number/statistic-focused search
            # =================================================================
            if not found_evidence:
                numbers = re.findall(r'\d+(?:\.\d+)?(?:\s*%|\s*percent|\s*ppb|\s*ppm)?', sentence)
                if numbers:
                    # Search for the specific numbers with context
                    number_query = f"{' '.join(numbers[:3])} {sentence[:50]}"
                    number_results = self._micro_search_for_claim(number_query, max_results=3)

                    for result in number_results[:2]:
                        snippet = result.get("snippet", "")
                        # Check if any number appears in the snippet
                        if any(num in snippet for num in numbers):
                            new_ev_id = f"ev_rescue_num_{len(evidence_chain) + len(new_evidence):04d}"
                            new_ev = Evidence(
                                evidence_id=new_ev_id,
                                chunk_id=f"rescue_num_{new_ev_id}",
                                source_url=result.get("url", ""),
                                text=snippet,
                                relevance_score=0.75,  # Higher relevance for number match
                                source_quality_score=0.6,
                                extraction_method="rescue_mode_numeric",
                                claims=[],
                                entities=[],
                                quality_tier="SILVER",
                            )
                            new_evidence.append(new_ev)

                            if "evidence_texts" not in sent_info:
                                sent_info["evidence_texts"] = []
                            sent_info["evidence_texts"].append(snippet[:300])
                            sent_info["suggested_citation"] = new_ev_id

                            evidence_found_count += 1
                            found_evidence = True
                            logger.info(
                                f"[FIX 99] RESCUE SUCCESS (numeric search): {new_ev_id} for: "
                                f"{sentence[:60]}..."
                            )
                            break

            if not found_evidence:
                logger.warning(
                    f"[FIX 99] RESCUE FAILED - no evidence found for: {sentence[:80]}... "
                    f"(will be marked for deletion)"
                )

            updated_sentences.append(sent_info)

        if new_evidence:
            logger.info(
                f"[FIX 99] RESCUE MODE COMPLETE: {evidence_found_count}/{rescue_attempts} claims rescued "
                f"({len(new_evidence)} new evidence pieces)"
            )
        elif rescue_attempts > 0:
            logger.warning(
                f"[FIX 99] RESCUE MODE: 0/{rescue_attempts} claims rescued - all will be deleted"
            )

        extended_chain = list(evidence_chain) + new_evidence
        return updated_sentences, extended_chain

    def _extract_entities_for_rescue(self, sentence: str) -> List[str]:
        """FIX 99: Extract named entities from sentence for rescue search.

        Looks for:
        - Organizations (EPA, CDC, WHO, NSF)
        - Acronyms (all caps words)
        - Proper nouns (capitalized words)
        - Technical terms
        """
        entities = []

        # Known organizations and acronyms
        known_orgs = {"EPA", "CDC", "WHO", "NSF", "FDA", "USDA", "OSHA", "NIH"}
        words = sentence.split()

        for word in words:
            clean_word = re.sub(r'[^\w]', '', word)
            if clean_word.upper() in known_orgs:
                entities.append(clean_word.upper())
            elif clean_word.isupper() and len(clean_word) >= 2:
                entities.append(clean_word)
            elif clean_word and clean_word[0].isupper() and len(clean_word) > 3:
                entities.append(clean_word)

        return list(set(entities))[:10]

    def _has_sentence_overlap(self, sentence: str, snippet: str, threshold: float = 0.3) -> bool:
        """FIX 99: Check if snippet has meaningful overlap with sentence."""
        STOPWORDS = {
            "the", "and", "for", "that", "this", "with", "from", "are", "was", "not",
            "but", "in", "on", "at", "to", "by", "of", "is", "it", "or", "as", "an"
        }

        sent_words = set(
            w.lower() for w in re.findall(r'\w+', sentence)
            if len(w) >= 2 and w.lower() not in STOPWORDS
        )
        snip_words = set(
            w.lower() for w in re.findall(r'\w+', snippet)
            if len(w) >= 2 and w.lower() not in STOPWORDS
        )

        if not sent_words:
            return False

        overlap = len(sent_words & snip_words) / len(sent_words)
        return overlap >= threshold


# =============================================================================
# SPRINT 2 FIX 2.4: Iterative Section-by-Section Synthesis
# =============================================================================

class SectionDraft(BaseModel):
    """A single section draft for iterative synthesis.

    FIX 62: Added faithfulness and status fields for Poison Pill detection.
    """
    section_id: str = Field(description="Section identifier")
    title: str = Field(description="Section title")
    content: str = Field(description="Section content with [CITE:id] tokens")
    citations_used: List[str] = Field(default_factory=list, description="Citation IDs used in this section")
    # FIX 62: Track section health for compilation filtering
    faithfulness: float = Field(default=1.0, description="Section faithfulness score (0.0-1.0)")
    status: str = Field(default="PENDING", description="Section status: PENDING, PASS, FAIL, CRITICAL_FAILURE, SKIPPED")


class IterativeSynthesizer:
    """
    SPRINT 2 FIX 2.4: Iterative Section-by-Section Synthesis.

    Instead of generating the entire report at once:
    1. Define section topics based on sub-queries
    2. For each section, filter evidence relevant to that topic
    3. Generate section with focused evidence (smaller context = better faithfulness)
    4. Verify section immediately using auditor
    5. Revise section if unfaithful sentences found
    6. Continue to next section

    This approach:
    - Reduces context size per LLM call (avoids "Lost in the Middle")
    - Catches hallucinations early (per-section verification)
    - Allows targeted revision (fix only unfaithful sentences)
    """

    def __init__(self, base_agent: 'SynthesizerAgent'):
        self.base_agent = base_agent
        self.auditor = None  # Lazy-loaded

    def _get_auditor(self):
        """Lazy-load the auditor agent."""
        if self.auditor is None:
            try:
                from src.agents.auditor_agent import AuditorAgent
                self.auditor = AuditorAgent()
            except ImportError:
                logger.warning("Auditor not available, skipping per-section verification")
        return self.auditor

    def synthesize_iteratively(
        self,
        state: ResearchState,
        max_revisions_per_section: int = 2
    ) -> ResearchState:
        """
        Synthesize report section by section with per-section verification.

        Args:
            state: Research state with evidence_chain
            max_revisions_per_section: Max revision attempts per section

        Returns:
            Updated state with draft_report
        """
        evidence_chain = state.get("evidence_chain", [])
        original_query = state.get("original_query", "")
        sub_queries = state.get("sub_queries", [])

        if not evidence_chain:
            logger.warning("No evidence for iterative synthesis")
            state["draft_report"] = "Insufficient evidence to generate report."
            return state

        # Define section topics from sub-queries or default structure
        section_topics = self._derive_section_topics(original_query, sub_queries)
        logger.info(f"Iterative synthesis: {len(section_topics)} sections planned")

        # Generate each section
        completed_sections = []
        section_stats = {
            "total_sections": len(section_topics),
            "revisions_needed": 0,
            "total_revisions": 0,
            "per_section_faithfulness": []
        }

        # FIX 106: Check if Context Unleashed mode is enabled
        context_unleashed = os.getenv("POLARIS_CONTEXT_UNLEASHED", "0") == "1"
        if context_unleashed:
            logger.info("[FIX 106] CONTEXT UNLEASHED MODE ACTIVE - Bypassing semantic routing for all sections")

        for i, topic in enumerate(section_topics):
            logger.info(f"Generating section {i+1}/{len(section_topics)}: {topic['title']}")

            # FIX 106: Choose evidence retrieval strategy
            if context_unleashed:
                # FIX 106: Context Unleashed - Pass ALL GOLD/SILVER evidence
                # Gemini Deep Audit: Semantic routing starves synthesizer (6/100 pass)
                section_evidence = self._get_section_evidence_unleashed(
                    evidence_chain,
                    section_query=topic.get("purpose", topic["title"])
                )
            else:
                # Original FIX 65: Semantic routing (may cause citation starvation)
                section_evidence = self._filter_evidence_for_topic(
                    evidence_chain,
                    topic["keywords"],
                    topic_description=topic.get("purpose", topic["title"])
                )
            logger.info(f"  Section evidence: {len(section_evidence)}/{len(evidence_chain)} items")

            # FIX 66B: Conditional Global Fallback
            # Only inject global fallback if we have SOME specific evidence (1-4 pieces).
            # If we have 0 specific pieces, the topic is unsupported - let FIX 63 SKIP it.
            # The old code injected fallback when len < 5, which included len == 0.
            # This defeated FIX 63 by giving 0-evidence sections generic content to hallucinate from.
            if 0 < len(section_evidence) < 5:
                logger.info(f"  [FIX 66] Boosting sparse evidence ({len(section_evidence)}) with global fallback")
                # Add top GOLD evidence as fallback
                gold_evidence = [ev for ev in evidence_chain if getattr(ev, 'quality_tier', '') == 'GOLD'][:10]
                for gev in gold_evidence:
                    if gev not in section_evidence:
                        section_evidence.append(gev)
                logger.info(f"  [FIX 66] After global fallback: {len(section_evidence)} items")
            elif len(section_evidence) == 0:
                logger.warning(f"  [FIX 66] Section has 0 evidence. NOT injecting fallback - FIX 63 SKIP will trigger.")

            # O3 PARITY: Generate section with self-correction loop (FIX 64: pass prior sections)
            # Self-correction catches issues BEFORE external auditor, reducing revision loops
            section_draft = self.synthesize_with_reflection(
                topic=topic,
                evidence=section_evidence,
                query=original_query,
                state=state,
                prior_sections=completed_sections  # FIX 64: Context threading
            )

            # FIX 63: Skip verification for SKIPPED sections (already faithful by definition)
            if section_draft.status == "SKIPPED":
                logger.info(f"  [FIX 63] Section skipped due to zero evidence - marking as faithful")
                section_stats["per_section_faithfulness"].append(1.0)
                completed_sections.append(section_draft)
                continue

            # Verify section
            auditor = self._get_auditor()
            if auditor and section_draft.content:
                verification_result = self._verify_section(
                    section_draft, section_evidence, auditor
                )

                faithfulness = verification_result.get("faithfulness", 1.0)
                section_stats["per_section_faithfulness"].append(faithfulness)

                # FIX 62: Update section with faithfulness tracking
                section_draft.faithfulness = faithfulness

                # Revise if needed
                revisions = 0
                while (
                    verification_result.get("revision_required", False)
                    and revisions < max_revisions_per_section
                ):
                    logger.info(f"  Revising section (attempt {revisions + 1})")
                    section_stats["revisions_needed"] += 1

                    section_draft = self._revise_section(
                        section_draft,
                        verification_result.get("unfaithful_sentences", []),
                        section_evidence,
                        state
                    )

                    verification_result = self._verify_section(
                        section_draft, section_evidence, auditor
                    )
                    revisions += 1
                    section_stats["total_revisions"] += 1

                    # Update faithfulness after revision
                    faithfulness = verification_result.get("faithfulness", 1.0)
                    section_draft.faithfulness = faithfulness

                # FIX 62: Determine section status based on final faithfulness
                if faithfulness >= 0.6:
                    section_draft.status = "PASS"
                elif faithfulness >= 0.5:
                    section_draft.status = "FAIL"
                else:
                    section_draft.status = "CRITICAL_FAILURE"
                    logger.error(f"  [FIX 62] CRITICAL FAILURE: Section '{topic['title']}' at {faithfulness:.1%}")

            completed_sections.append(section_draft)

        # Compile final report
        report = self._compile_sections(
            completed_sections, original_query, state
        )

        # Build markdown
        markdown = self._format_sections_markdown(report, completed_sections)

        # Update state
        state["draft_report"] = markdown
        state["report_sections"] = {s.section_id: s.content for s in completed_sections}
        state["iterative_synthesis_stats"] = section_stats
        state["synthesis_method"] = "iterative"

        # Calculate overall faithfulness from per-section
        if section_stats["per_section_faithfulness"]:
            avg_faith = sum(section_stats["per_section_faithfulness"]) / len(section_stats["per_section_faithfulness"])
            state["iterative_faithfulness"] = avg_faith
            logger.info(f"Iterative synthesis complete: avg faithfulness={avg_faith:.1%}")

        # ======================================================================
        # FIX 81: Reflexive Word Count Expander (Moved into iterative path)
        # ======================================================================
        # If the compiled report is too short and we have enough evidence,
        # trigger cost-effective expansion rather than expensive full re-synthesis.
        MIN_WORD_COUNT = 2000
        MIN_EVIDENCE_FOR_EXPANSION = 15
        word_count = len(markdown.split())

        if word_count < MIN_WORD_COUNT and len(evidence_chain) >= MIN_EVIDENCE_FOR_EXPANSION:
            logger.info(
                f"[FIX 81] Iterative report too short ({word_count} < {MIN_WORD_COUNT} words) "
                f"with {len(evidence_chain)} evidence pieces. Triggering reflexive expansion."
            )

            expanded_markdown = self.base_agent._expand_short_report(
                markdown,
                evidence_chain,
                word_count,
                MIN_WORD_COUNT
            )

            if expanded_markdown:
                expanded_word_count = len(expanded_markdown.split())
                if expanded_word_count > word_count:
                    state["draft_report"] = expanded_markdown
                    logger.info(
                        f"[FIX 81] Iterative report expanded: {word_count} -> {expanded_word_count} words "
                        f"(+{expanded_word_count - word_count})"
                    )
                else:
                    logger.warning(f"[FIX 81] Expansion did not increase word count, keeping original")

        return state

    def _derive_section_topics(
        self,
        query: str,
        sub_queries: List
    ) -> List[Dict]:
        """Derive section topics from query and sub-queries."""
        topics = [
            {
                "section_id": "introduction",
                "title": "Introduction",
                "keywords": ["background", "context", "scope", "methodology"],
                "purpose": "Introduce the research question and methodology"
            }
        ]

        # Create topic for each sub-query cluster
        if sub_queries:
            for i, sq in enumerate(sub_queries[:5]):  # Limit to 5 sub-query sections
                sq_text = sq.query_text if hasattr(sq, 'query_text') else str(sq)
                # Extract keywords from sub-query
                keywords = [w.lower() for w in sq_text.split() if len(w) > 3][:5]
                topics.append({
                    "section_id": f"findings_{i+1}",
                    "title": f"Findings: {sq_text[:50]}",
                    "keywords": keywords,
                    "purpose": f"Address: {sq_text}"
                })
        else:
            # Default findings section
            topics.append({
                "section_id": "findings",
                "title": "Findings",
                "keywords": query.lower().split()[:5],
                "purpose": "Present research findings"
            })

        # Add analysis, conclusions, recommendations
        topics.extend([
            {
                "section_id": "analysis",
                "title": "Analysis",
                "keywords": ["analysis", "pattern", "trend", "comparison", "synthesis"],
                "purpose": "Synthesize and analyze findings"
            },
            {
                "section_id": "conclusions",
                "title": "Conclusions",
                "keywords": ["conclusion", "result", "finding", "outcome", "answer"],
                "purpose": "Draw conclusions and answer research question"
            },
            {
                "section_id": "recommendations",
                "title": "Recommendations",
                "keywords": ["recommendation", "action", "future", "next", "should"],
                "purpose": "Provide actionable recommendations"
            }
        ])

        return topics

    def _filter_evidence_for_topic(
        self,
        evidence_chain: List[Evidence],
        keywords: List[str],
        topic_description: str = None
    ) -> List[Evidence]:
        """Filter evidence relevant to a specific topic.

        FIX 65 (Semantic Routing): Use vector similarity instead of keyword matching.
        The old keyword matching failed when evidence used different terminology
        (e.g., "integrity loss" vs "breakthrough").

        Hybrid approach:
        1. Try semantic similarity first (catches synonyms)
        2. Fall back to keyword matching if embeddings unavailable
        3. Always include some evidence to prevent starvation
        """
        if not keywords and not topic_description:
            return evidence_chain

        # Build topic query for semantic search
        topic_query = topic_description if topic_description else " ".join(keywords)

        # FIX 65: Try semantic similarity first
        # FIX 76: Use singleton embedding service instead of local SentenceTransformer
        # FIX 94: Add guard clauses to prevent [Errno 22] on empty/invalid inputs
        try:
            from src.utils.embedding_service import get_embedding_service
            import numpy as np

            # FIX 94: Guard against empty evidence chain
            if not evidence_chain:
                logger.warning("[FIX 94] Empty evidence chain, skipping semantic routing")
                return []

            # FIX 94: Guard against empty/invalid topic query
            if not topic_query or not topic_query.strip():
                logger.warning("[FIX 94] Empty topic query, falling back to keyword matching")
                raise ValueError("Empty topic query")

            # FIX 76: Use singleton - no need for lazy-load attribute
            embed_service = get_embedding_service()
            logger.debug("[FIX 76] Using singleton embedding service for semantic routing")

            # Embed the topic query
            topic_embedding = np.array(embed_service.embed(topic_query))

            # FIX 94: Guard against zero-vector topic embedding
            if np.linalg.norm(topic_embedding) < 1e-8:
                logger.warning("[FIX 94] Topic embedding is zero vector, falling back to keyword matching")
                raise ValueError("Zero topic embedding")

            # Score each evidence piece by semantic similarity
            # FIX 66A: Use full context (~2000 chars) instead of 500
            # all-MiniLM-L6-v2 supports 512 tokens (~2000 chars)
            # Truncating to 500 chars discards 75% of evidence text
            scored_evidence = []
            for ev in evidence_chain:
                try:
                    # FIX 94: Guard against None/empty evidence text
                    ev_text_raw = getattr(ev, 'text', '') or ''
                    ev_claims = getattr(ev, 'claims', []) or []
                    ev_text = f"{ev_text_raw[:2000]} {' '.join(ev_claims) if ev_claims else ''}"

                    # FIX 94: Skip if evidence text is empty
                    if not ev_text.strip():
                        continue

                    ev_embedding = np.array(embed_service.embed(ev_text))

                    # FIX 94: Guard against zero-norm embeddings (division by zero)
                    ev_norm = np.linalg.norm(ev_embedding)
                    topic_norm = np.linalg.norm(topic_embedding)
                    if ev_norm < 1e-8 or topic_norm < 1e-8:
                        similarity = 0.0
                    else:
                        # Cosine similarity
                        similarity = np.dot(topic_embedding, ev_embedding) / (topic_norm * ev_norm)

                    scored_evidence.append((ev, float(similarity)))
                except Exception as inner_e:
                    # FIX 94: Log but continue on individual evidence failures
                    logger.debug(f"[FIX 94] Skipping evidence due to embedding error: {inner_e}")
                    continue

            # Sort by similarity and filter by threshold
            scored_evidence.sort(key=lambda x: x[1], reverse=True)

            # FIX 65: Use lower threshold (0.2) to catch more relevant evidence
            # The old keyword approach was too strict
            threshold = 0.2
            relevant = [ev for ev, score in scored_evidence if score >= threshold]

            logger.info(f"[FIX 65] Semantic routing: {len(relevant)}/{len(evidence_chain)} evidence above threshold {threshold}")

            if relevant:
                return relevant

            # FIX 66A: Allow returning empty list to trigger FIX 63 (Skip Section)
            # Do NOT force garbage evidence into the synthesizer.
            # The old code returned "top 10 by similarity" which defeated FIX 63.
            # If no evidence meets the threshold, the topic is unsupported. Let it die.
            logger.warning(f"[FIX 66] No evidence met threshold {threshold}. Returning empty list to trigger FIX 63 SKIP.")
            return []

        except ImportError:
            logger.warning("[FIX 65] sentence-transformers not available, falling back to keyword matching")
        except Exception as e:
            logger.warning(f"[FIX 65] Semantic routing failed ({e}), falling back to keyword matching")

        # Fallback: Original keyword matching
        relevant = []
        for ev in evidence_chain:
            text_lower = ev.text.lower()
            claims_lower = " ".join(ev.claims).lower() if ev.claims else ""
            combined = f"{text_lower} {claims_lower}"

            # Score by keyword matches
            match_count = sum(1 for kw in keywords if kw in combined)
            if match_count > 0:
                relevant.append((ev, match_count))

        # Sort by match count and return evidence only
        relevant.sort(key=lambda x: x[1], reverse=True)
        return [ev for ev, _ in relevant]

    def _get_section_evidence_unleashed(
        self,
        evidence_chain: List[Evidence],
        section_query: str = None
    ) -> List[Evidence]:
        """FIX 106: Context Unleashed - Bypass semantic routing.

        Gemini Deep Audit identified that semantic routing (FIX 65) starves the
        synthesizer of evidence - only 6/100 pieces pass the threshold.

        FIX 107I (Gemini Audit "Smart Window"): Per-Section Semantic Re-ranking.
        - Problem: All sections receive identical evidence (identical char counts in logs)
        - The "Frozen Window" means Section 5 (Cost) gets "Effectiveness" evidence
        - Solution: Re-rank evidence SEMANTICALLY for each section's topic
        - This ensures "Cost" section gets cost-related evidence at the top
        """
        if not evidence_chain:
            logger.warning("[FIX 106] Empty evidence chain")
            return []

        # Filter for Quality, NOT Semantic Similarity
        valid_evidence = [
            e for e in evidence_chain
            if getattr(e, 'quality_tier', 'BRONZE') in ["GOLD", "SILVER"]
        ]

        # If no GOLD/SILVER, fall back to all evidence
        if not valid_evidence:
            logger.warning("[FIX 106] No GOLD/SILVER evidence, using all evidence")
            valid_evidence = evidence_chain

        # ======================================================================
        # FIX 107I: Smart Window - Per-Section Semantic Re-ranking
        # ======================================================================
        # Instead of global ranking, re-rank evidence for THIS SPECIFIC SECTION
        smart_window_enabled = os.environ.get("POLARIS_SMART_WINDOW", "1") == "1"

        if section_query and smart_window_enabled:
            logger.info(f"[FIX 107I] Smart Window: Re-ranking evidence for section '{section_query[:50]}...'")
            try:
                # Use fast keyword matching for initial boost
                section_keywords = set(section_query.lower().split())
                # Remove common words
                stopwords = {'the', 'a', 'an', 'and', 'or', 'of', 'to', 'for', 'in', 'on', 'is', 'are', 'what', 'how', 'this', 'that'}
                section_keywords -= stopwords

                # Score each evidence piece by keyword overlap with section
                for ev in valid_evidence:
                    ev_text = getattr(ev, 'text', '').lower()
                    ev_keywords = set(ev_text.split())
                    # Calculate keyword overlap score
                    overlap = len(section_keywords & ev_keywords)
                    # Combine with global relevance (60% section relevance, 40% global)
                    global_score = getattr(ev, 'relevance_score', 0.5)
                    section_score = min(1.0, overlap / max(len(section_keywords), 1) * 2)  # Normalize
                    combined_score = 0.6 * section_score + 0.4 * global_score
                    # Store for sorting (temporary attribute)
                    ev._section_score = combined_score

                # Sort by section-specific score
                valid_evidence.sort(key=lambda x: getattr(x, '_section_score', 0.5), reverse=True)

                # Log top matches for debugging
                top_3_scores = [f"{getattr(e, '_section_score', 0):.2f}" for e in valid_evidence[:3]]
                logger.info(f"[FIX 107I] Top 3 section relevance scores: {top_3_scores}")

            except Exception as e:
                logger.warning(f"[FIX 107I] Smart Window failed, falling back to global ranking: {e}")
                # Fall back to global relevance score
                valid_evidence.sort(
                    key=lambda x: getattr(x, 'relevance_score', 0.5),
                    reverse=True
                )
        else:
            # Original FIX 106 behavior: Sort by global relevance score
            valid_evidence.sort(
                key=lambda x: getattr(x, 'relevance_score', 0.5),
                reverse=True
            )

        # Safety Cap: 150 items (~40k-50k tokens) leaves room for generation
        max_evidence = int(os.getenv("POLARIS_UNLEASHED_MAX_EVIDENCE", "150"))
        selected_evidence = valid_evidence[:max_evidence]

        mode_str = "Smart Window" if (section_query and smart_window_enabled) else "Global Ranking"
        logger.info(
            f"[FIX 106/107I] Context Unleashed ({mode_str}): Passing {len(selected_evidence)}/{len(evidence_chain)} "
            f"items to section generation"
        )

        return selected_evidence

    def _generate_section(
        self,
        topic: Dict,
        evidence: List[Evidence],
        query: str,
        state: ResearchState,
        prior_sections: List[SectionDraft] = None  # FIX 64: Context threading
    ) -> SectionDraft:
        """Generate a single section.

        FIX 63 (Liar's Paradox Breaker): If section has 0 evidence, SKIP it entirely.
        Better to write 0 words than 600 words of hallucinations.

        FIX 64 (Context Threading): For Conclusions/Recommendations, receive prior sections.
        """
        # FIX 63: CRITICAL - Skip sections with zero evidence
        # This breaks the "Liar's Paradox" where the LLM was forced to choose
        # between "write 600 words" and "don't write without citations"
        if not evidence:
            logger.warning(f"[FIX 63] SKIPPING section '{topic['title']}' - ZERO EVIDENCE")
            logger.warning(f"[FIX 63] Better to write 0 words than hallucinate")
            return SectionDraft(
                section_id=topic["section_id"],
                title=topic["title"],
                content="[SECTION SKIPPED: No supporting evidence available for this topic.]",
                citations_used=[],
                faithfulness=1.0,  # Skipped sections are "faithful" (no lies)
                status="SKIPPED"
            )

        # FIX 104: Citation Diversity Enforcement
        # Problem: With 20 evidence pieces per section and overlapping selection,
        # only ~21 unique sources get cited from 82 available.
        # FIX 107G (Gemini Audit "Frozen Window"): Increased from 35 to 150
        # - Must see enough evidence to hit 130+ unique citations target
        # - Modern LLMs (Gemini 1.5/GPT-4o) handle 128k+ tokens easily
        evidence_limit = min(150, len(evidence))  # FIX 107G: Increased from 35 to 150
        evidence_context = "\n---\n".join([
            f"[{ev.evidence_id}]\nSource: {ev.source_url}\nText: {ev.text[:600]}"  # Reduced to 600 chars for more items
            for ev in evidence[:evidence_limit]
        ])
        logger.info(f"[FIX 107G] Section evidence context: {evidence_limit} pieces, {len(evidence_context)} chars")

        # FIX 64: Context Threading for derivative sections (Conclusions, Recommendations)
        # These sections should summarize FINDINGS, not raw evidence
        prior_context = ""
        is_derivative = topic["section_id"] in ("conclusions", "recommendations", "analysis")
        if is_derivative and prior_sections:
            prior_context = "\n\n=== PRIOR SECTIONS (SUMMARIZE THESE) ===\n"
            for ps in prior_sections:
                if ps.status not in ("SKIPPED", "CRITICAL_FAILURE") and ps.content:
                    # Include summary of findings sections
                    prior_context += f"\n### {ps.title}\n{ps.content[:1500]}...\n"
            prior_context += "\n=== END PRIOR SECTIONS ===\n"
            logger.info(f"[FIX 64] Passing {len(prior_sections)} prior sections to {topic['title']}")

        # FIX 58: Increased section word target for deeper reports (600-800 words)
        # FIX 60: Strict Mode Propagation - Include FIX 52 rules in iterative synthesis
        # FIX 63: Conditional length - only write if evidence supports it
        messages = [
            SystemMessage(content=f"""You are writing the "{topic['title']}" section of a research report.

RULES:
- Focus ONLY on this section's purpose: {topic['purpose']}
- Use [CITE:evidence_id] for ALL factual claims
- FIX 58 DEPTH TARGET: Write 600-800 words for this section (not 200-500)
- Include multiple paragraphs with detailed analysis
- Integrate evidence thoroughly - don't just list facts
- Do NOT fabricate citations
- If evidence is insufficient, say so explicitly

FIX 52 STRICT MODE (CRITICAL - APPLIES TO ALL SYNTHESIS):
- EVERY factual claim MUST have [CITE:evidence_id] - NO EXCEPTIONS
- If you CANNOT cite a factual sentence, DO NOT WRITE IT
- Uncited factual claims will be DELETED by the auditor
- Generic transitions ("This section discusses...") are OK without citations
- But ANY sentence with numbers, statistics, findings, or claims MUST be cited
- Target: 90%+ of sentences should have citations
- The auditor WILL reject uncited factual content

FIX 104 CITATION DIVERSITY (CRITICAL):
- Use DIFFERENT evidence pieces throughout the section - do not cite the same source repeatedly
- Each paragraph should cite at least 3-5 DIFFERENT evidence IDs
- If multiple evidence pieces support a claim, cite ALL of them: [CITE:ev_1][CITE:ev_2]
- Spread citations across the full evidence list provided, not just the first few
- Target: Use at least 60% of the evidence pieces provided to this section

SECTION DEPTH GUIDELINES:
- Introduction: 400-500 words (context, scope, methodology overview)
- Findings sections: 600-800 words each (detailed evidence presentation)
- Analysis: 500-700 words (synthesis, patterns, implications)
- Conclusions: 400-500 words (key takeaways, answer to research question)
- Recommendations: 300-400 words (actionable next steps)

FAITHFULNESS RULES:
- Use EXACT numbers from evidence - no rounding, no "approximately"
- PREFER DIRECT QUOTES over paraphrasing
- Do NOT add information beyond what evidence states
- If uncertain, use hedging language WITH a citation"""),
            HumanMessage(content=f"""Write the "{topic['title']}" section.

RESEARCH QUESTION: {query}
{prior_context}
EVIDENCE FOR THIS SECTION:
{evidence_context}

{"FIX 64 NOTE: For this derivative section (Conclusions/Recommendations/Analysis), you should SUMMARIZE THE PRIOR SECTIONS above, not just cite raw evidence. Reference what the report has already established." if is_derivative and prior_context else ""}

Write a comprehensive section (600-800 words) that addresses: {topic['purpose']}

FIX 63 CRITICAL: If the evidence is sparse or doesn't support this topic:
- Write LESS (even 100 words is OK)
- Acknowledge the gap: "Limited evidence exists for..."
- DO NOT fabricate content to meet word count
- Better to write "No data available" than 600 words of hallucinations

Every factual claim MUST have [CITE:evidence_id] support.
If you cannot cite it from the evidence above, DO NOT WRITE IT.
Uncited factual sentences will be deleted.

Provide detailed analysis with dense citations, not fluff.""")
        ]

        try:
            result: SectionDraft = self.base_agent.call_llm_structured(messages, SectionDraft)
            # FIX 12: Handle None return from call_llm_structured (timeout or parse failure)
            if result is None:
                logger.warning(f"Section generation returned None for {topic['title']}")
                return SectionDraft(
                    section_id=topic["section_id"],
                    title=topic["title"],
                    content="Section generation timed out",
                    citations_used=[]
                )
            result.section_id = topic["section_id"]
            result.title = topic["title"]
            return result
        except Exception as e:
            logger.error(f"Section generation failed: {e}")
            return SectionDraft(
                section_id=topic["section_id"],
                title=topic["title"],
                content=f"Section generation failed: {e}",
                citations_used=[]
            )

    def _verify_section(
        self,
        section: SectionDraft,
        evidence: List[Evidence],
        auditor
    ) -> Dict:
        """Verify a section using the auditor."""
        from src.orchestration.state import Evidence as EvidenceClass

        # Create mini-state for auditor
        mini_state = {
            "draft_report": section.content,
            "evidence_chain": evidence
        }

        # Run auditor
        result_state = auditor.process(mini_state)

        return {
            "faithfulness": result_state.get("post_hoc_faithfulness", 1.0),
            "revision_required": result_state.get("audit_result", {}).get("revision_required", False),
            "unfaithful_sentences": result_state.get("sentences_to_revise", [])
        }

    def _revise_section(
        self,
        section: SectionDraft,
        unfaithful_sentences: List[Dict],
        evidence: List[Evidence],
        state: ResearchState
    ) -> SectionDraft:
        """Revise a section to fix unfaithful sentences."""
        if not unfaithful_sentences:
            return section

        # Build evidence context
        evidence_context = "\n---\n".join([
            f"[{ev.evidence_id}]: {ev.text[:300]}"
            for ev in evidence[:15]
        ])

        # Build unfaithful sentences list
        issues = "\n".join([
            f"- \"{s.get('sentence', '')[:100]}...\" - Issue: {s.get('issues', 'Unsupported by evidence')}"
            for s in unfaithful_sentences[:5]
        ])

        # FIX 31+34: Section revision with conditional deletion
        messages = [
            SystemMessage(content="""You are revising a report section to fix unfaithful claims.

RULES:
- Fix ONLY the identified unfaithful sentences
- PREFERENCE: REWRITE with evidence > HEDGE with evidence > DELETE (last resort)
- HEDGE claims you cannot fully verify ("some studies suggest...", "evidence indicates...")
- Cite the closest supporting evidence with [CITE:evidence_id]
- FIX 34: You MAY delete a sentence ONLY if it makes a specific false claim with zero evidence support
- Keep the rest of the section unchanged"""),
            HumanMessage(content=f"""Revise this section to fix unfaithful sentences.

CURRENT SECTION:
{section.content}

UNFAITHFUL SENTENCES TO FIX:
{issues}

AVAILABLE EVIDENCE:
{evidence_context}

Revise the section: REWRITE or HEDGE unfaithful sentences. DELETE only if the claim has zero evidence support.""")
        ]

        try:
            result: SectionDraft = self.base_agent.call_llm_structured(messages, SectionDraft)
            # FIX 12: Handle None return from call_llm_structured (timeout or parse failure)
            if result is None:
                logger.warning(f"Section revision returned None for {section.title}")
                return section
            result.section_id = section.section_id
            result.title = section.title
            return result
        except Exception as e:
            logger.error(f"Section revision failed: {e}")
            return section

    # =========================================================================
    # OpenAI o3 Parity: Self-Correction Loop
    # =========================================================================

    def synthesize_with_reflection(
        self,
        topic: Dict,
        evidence: List[Evidence],
        query: str,
        state: ResearchState,
        prior_sections: List[SectionDraft] = None,
        max_corrections: int = 3
    ) -> SectionDraft:
        """
        OpenAI o3 Parity: Self-correction loop for section synthesis.

        Generate -> Reflect -> Correct -> Repeat until satisfactory.

        This catches issues BEFORE the external auditor, reducing revision loops.

        Args:
            topic: Section topic configuration
            evidence: Evidence for this section
            query: Original research query
            state: Current research state
            prior_sections: Previous sections for context threading
            max_corrections: Maximum self-correction iterations

        Returns:
            Section draft that has passed self-reflection
        """
        # Generate initial draft
        draft = self._generate_section(
            topic=topic,
            evidence=evidence,
            query=query,
            state=state,
            prior_sections=prior_sections or []
        )

        # Skip reflection for SKIPPED sections
        if draft.status == "SKIPPED":
            return draft

        # Self-correction loop
        for correction_round in range(max_corrections):
            # Reflect on the draft
            reflection = self._reflect_on_draft(draft, evidence, query)

            if reflection.is_satisfactory:
                logger.info(
                    f"[SELF-CORRECT] Section '{topic['title']}' passed reflection "
                    f"(score: {reflection.overall_score:.2f}, round: {correction_round})"
                )
                break

            # Generate corrections
            corrections = self._generate_corrections(draft, reflection, evidence)

            if not corrections:
                logger.debug(
                    f"[SELF-CORRECT] No corrections generated for '{topic['title']}' "
                    f"despite reflection issues"
                )
                break

            # Apply corrections
            logger.info(
                f"[SELF-CORRECT] Applying {len(corrections)} corrections to '{topic['title']}' "
                f"(round {correction_round + 1}/{max_corrections})"
            )
            draft = self._apply_corrections(draft, corrections, evidence)

        return draft

    def _reflect_on_draft(
        self,
        draft: SectionDraft,
        evidence: List[Evidence],
        query: str
    ) -> ReflectionResult:
        """
        OpenAI o3 Parity: Self-reflect on draft quality.

        Identifies issues without external auditor:
        - Uncited factual claims
        - Inaccurate paraphrasing
        - Missing context
        - Unsupported inferences
        - Vague language

        Args:
            draft: The section draft to reflect on
            evidence: Evidence used for this section
            query: Original research query

        Returns:
            ReflectionResult with identified issues
        """
        # Build evidence summary for reflection
        evidence_summary = "\n".join([
            f"[{ev.evidence_id}]: {ev.text[:200]}..."
            for ev in evidence[:10]
        ])

        messages = [
            SystemMessage(content="""You are a critical self-editor for research reports.

TASK: Analyze this draft section and identify issues that need fixing.

CHECK FOR:
1. UNCITED CLAIMS: Factual statements without [CITE:evidence_id]
2. INACCURATE PARAPHRASE: Rewording that changes meaning from evidence
3. MISSING CONTEXT: Important caveats or conditions omitted
4. UNSUPPORTED INFERENCE: Conclusions not directly in evidence
5. VAGUE LANGUAGE: Imprecise terms when evidence has specifics

SCORING:
- 0.9-1.0: Excellent, minor style suggestions only
- 0.7-0.9: Good, few issues to address
- 0.5-0.7: Needs work, several issues
- <0.5: Poor, major revision needed

Be HONEST and CRITICAL. Finding issues now prevents auditor rejection later."""),
            HumanMessage(content=f"""Reflect on this draft section:

SECTION TITLE: {draft.title}

DRAFT CONTENT:
{draft.content}

AVAILABLE EVIDENCE (to check claims against):
{evidence_summary}

Identify any issues and provide an overall quality score.""")
        ]

        try:
            result = self.base_agent.call_llm_structured(messages, ReflectionResult)
            if result is None:
                # Default to satisfactory if reflection fails
                return ReflectionResult(
                    is_satisfactory=True,
                    overall_score=0.7,
                    issues=[],
                    recommendation="Reflection failed, proceeding with draft"
                )
            return result
        except Exception as e:
            logger.warning(f"Self-reflection failed: {e}")
            return ReflectionResult(
                is_satisfactory=True,
                overall_score=0.7,
                issues=[],
                recommendation=f"Reflection error: {e}"
            )

    def _generate_corrections(
        self,
        draft: SectionDraft,
        reflection: ReflectionResult,
        evidence: List[Evidence]
    ) -> List[Correction]:
        """
        OpenAI o3 Parity: Generate specific corrections for identified issues.

        Args:
            draft: The current draft
            reflection: Reflection result with issues
            evidence: Available evidence

        Returns:
            List of corrections to apply
        """
        if not reflection.issues:
            return []

        # Build issues list
        issues_text = "\n".join([
            f"- [{issue.severity.upper()}] {issue.issue_type}: \"{issue.sentence[:80]}...\" -> {issue.suggestion}"
            for issue in reflection.issues[:5]  # Cap at 5 issues per round
        ])

        # Build evidence context
        evidence_context = "\n".join([
            f"[{ev.evidence_id}]: {ev.text[:250]}"
            for ev in evidence[:10]
        ])

        messages = [
            SystemMessage(content="""You are generating targeted corrections for a research draft.

For each issue, provide:
1. The EXACT original sentence (copy verbatim)
2. The corrected sentence
3. The type of correction
4. Brief reasoning

CORRECTION TYPES:
- add_citation: Add [CITE:evidence_id] to uncited claim
- fix_paraphrase: Rewrite to match evidence exactly
- add_context: Add missing caveats or conditions
- remove_inference: Delete or hedge unsupported conclusion
- clarify_language: Use specific terms from evidence

RULES:
- Keep corrections minimal and targeted
- Preserve surrounding text
- Use exact evidence_ids from the evidence list"""),
            HumanMessage(content=f"""Generate corrections for these issues:

ISSUES TO FIX:
{issues_text}

CURRENT DRAFT:
{draft.content}

EVIDENCE (for citations):
{evidence_context}

Generate a correction for each issue.""")
        ]

        try:
            # Use structured output for list of corrections
            from pydantic import BaseModel
            from typing import List

            class CorrectionList(BaseModel):
                corrections: List[Correction]

            result = self.base_agent.call_llm_structured(messages, CorrectionList)
            if result is None:
                return []
            return result.corrections
        except Exception as e:
            logger.warning(f"Correction generation failed: {e}")
            return []

    def _apply_corrections(
        self,
        draft: SectionDraft,
        corrections: List[Correction],
        evidence: List[Evidence]
    ) -> SectionDraft:
        """
        OpenAI o3 Parity: Apply corrections to the draft.

        Args:
            draft: The current draft
            corrections: Corrections to apply
            evidence: Available evidence (for validation)

        Returns:
            Updated SectionDraft
        """
        content = draft.content

        corrections_applied = 0
        for correction in corrections:
            if correction.original_sentence in content:
                content = content.replace(
                    correction.original_sentence,
                    correction.corrected_sentence,
                    1  # Replace only first occurrence
                )
                corrections_applied += 1
                logger.debug(
                    f"[SELF-CORRECT] Applied {correction.correction_type}: "
                    f"{correction.original_sentence[:40]}... -> {correction.corrected_sentence[:40]}..."
                )
            else:
                # Try fuzzy matching for minor whitespace differences
                import re
                normalized_original = re.sub(r'\s+', ' ', correction.original_sentence.strip())
                normalized_content = re.sub(r'\s+', ' ', content)

                if normalized_original in normalized_content:
                    # Find and replace with original whitespace handling
                    pattern = re.escape(normalized_original).replace(r'\ ', r'\s+')
                    content = re.sub(pattern, correction.corrected_sentence, content, count=1)
                    corrections_applied += 1

        logger.info(
            f"[SELF-CORRECT] Applied {corrections_applied}/{len(corrections)} corrections"
        )

        # Return updated draft
        return SectionDraft(
            section_id=draft.section_id,
            title=draft.title,
            content=content,
            word_count=len(content.split()),
            citations_used=draft.citations_used,
            faithfulness=draft.faithfulness,
            status=draft.status
        )

    def _compile_sections(
        self,
        sections: List[SectionDraft],
        query: str,
        state: ResearchState
    ) -> Dict:
        """Compile sections into final report structure."""
        return {
            "title": f"Research Report: {query[:50]}",
            "sections": sections,
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "vector_id": state.get("vector_id", "unknown"),
                "synthesis_method": "iterative",
                "total_sections": len(sections)
            }
        }

    def _format_sections_markdown(
        self,
        report: Dict,
        sections: List[SectionDraft]
    ) -> str:
        """Format compiled sections as markdown.

        FIX 62 (Poison Pill Compiler): Original version AMPUTATED toxic sections.

        FIX 107H (Gemini Audit "Lazarus Fix"): QUARANTINE instead of AMPUTATE.
        - Low-faithfulness sections are KEPT but marked with a disclaimer
        - This allows citation enrichment to potentially RECOVER the section
        - Content is preserved for enrichment to inject verified citations
        - Better to have disclaimered content than empty sections

        The "Zombie Section Paradox": Even if enrichment adds citations,
        amputated sections can't be resurrected. By quarantining instead,
        we preserve the content for enrichment to work with.
        """
        import os
        md = [f"# {report['title']}", ""]

        quarantined_count = 0
        included_count = 0

        # FIX 107H: Check if Lazarus mode is enabled (default: ON)
        lazarus_mode = os.environ.get("POLARIS_LAZARUS_MODE", "1") == "1"

        for section in sections:
            # FIX 63: Handle SKIPPED sections gracefully (no content to preserve)
            if section.status == "SKIPPED":
                md.append(f"## {section.title}")
                md.append("")
                md.append(section.content)  # Will say "[SECTION SKIPPED: No supporting evidence...]"
                md.append("")
                continue

            # FIX 107H (Lazarus): QUARANTINE low-faithfulness sections instead of AMPUTATE
            # This preserves content for citation enrichment to potentially recover
            is_low_faith = (
                section.status == "CRITICAL_FAILURE" or
                (section.faithfulness < 0.5 and section.status not in ("SKIPPED", "PASS"))
            )

            if is_low_faith and lazarus_mode:
                # LAZARUS MODE: Quarantine with disclaimer, preserve content
                logger.warning(
                    f"[FIX 107H] QUARANTINING section '{section.title}' (faithfulness={section.faithfulness:.1%}) "
                    f"- Content preserved for enrichment recovery"
                )
                quarantined_count += 1
                md.append(f"## {section.title}")
                md.append("")
                md.append(f"> **Note:** Some claims in this section could not be fully verified against the evidence pool (faithfulness: {section.faithfulness:.1%}). Interpret with caution.")
                md.append("")
                md.append(section.content)  # PRESERVE CONTENT for enrichment
                md.append("")
                continue
            elif is_low_faith:
                # LEGACY MODE: Amputate (FIX 62 original behavior)
                logger.warning(f"[FIX 62] AMPUTATING toxic section '{section.title}' (faithfulness={section.faithfulness:.1%})")
                quarantined_count += 1
                md.append(f"## {section.title}")
                md.append("")
                md.append(f"*[Section removed: Insufficient evidence (faithfulness={section.faithfulness:.1%})]*")
                md.append("")
                continue

            # Include valid sections
            included_count += 1
            md.append(f"## {section.title}")
            md.append("")
            md.append(section.content)
            md.append("")

        # Log compilation summary
        mode_str = "LAZARUS (quarantine)" if lazarus_mode else "LEGACY (amputate)"
        logger.info(f"[FIX 107H] Compilation complete ({mode_str}): {included_count} healthy, {quarantined_count} quarantined/amputated")

        return "\n".join(md)


# =============================================================================
# Standalone function
# =============================================================================

def synthesize_report(
    query: str,
    evidence_texts: List[Dict[str, str]],
    application: str = "Unknown",
    region: str = "GLOBAL"
) -> str:
    """
    Standalone function to synthesize a report.

    Args:
        query: Research question
        evidence_texts: List of dicts with 'text' and 'source' keys
        application: Application context
        region: Geographic region

    Returns:
        Markdown report
    """
    from src.orchestration.state import create_initial_state, Evidence

    state = create_initial_state(
        vector_id="standalone",
        query=query,
        application=application,
        region=region,
        stage=1
    )

    # MED-023, MED-024: Default scores from config
    high_relevance = get_threshold("scoring.high_relevance", 0.8)
    high_quality = get_threshold("scoring.high_quality", 0.7)

    # Build evidence chain
    evidence_chain = []
    for i, ev in enumerate(evidence_texts):
        evidence = Evidence(
            evidence_id=f"ev_{i+1:04d}",
            chunk_id=f"chunk_{i+1:04d}",
            source_url=ev.get("source", "unknown"),
            text=ev.get("text", ""),
            relevance_score=high_relevance,
            source_quality_score=high_quality,
            extraction_method="manual",
            claims=[],
            entities=[],
        )
        evidence_chain.append(evidence)

    state["evidence_chain"] = evidence_chain

    agent = SynthesizerAgent()
    result_state = agent.invoke(state)

    return result_state.get("draft_report", "Report generation failed")
