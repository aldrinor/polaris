"""
SmartArt diagram generator for polaris graph reports (Amendment A5).

Analyzes completed report sections to identify which benefit from visual
diagrams, then generates content-level Mermaid.js code grounded in the
section text and supporting evidence. All diagram facts are traceable to
the source material — no invented data.

Entry point: SmartArtGenerator.generate_smart_art_for_report()
"""

import logging
import os
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from src.polaris_graph.llm.openrouter_client import OpenRouterClient
from src.polaris_graph.tracing import get_tracer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (LAW VI — zero hard-coding)
# ---------------------------------------------------------------------------

PG_MAX_SMART_ART: int = int(os.getenv("PG_MAX_SMART_ART", "5"))
PG_SMART_ART_ENABLED: bool = os.getenv("PG_SMART_ART_ENABLED", "1") == "1"

# LLM call parameters — configurable via environment
_ANALYSIS_MAX_TOKENS: int = int(os.getenv("PG_SMART_ART_ANALYSIS_MAX_TOKENS", "4096"))
_MERMAID_MAX_TOKENS: int = int(os.getenv("PG_SMART_ART_MERMAID_MAX_TOKENS", "4096"))
_ANALYSIS_TEMPERATURE: float = float(os.getenv("PG_SMART_ART_ANALYSIS_TEMP", "0.4"))
_MERMAID_TEMPERATURE: float = float(os.getenv("PG_SMART_ART_MERMAID_TEMP", "0.3"))
_ANALYSIS_TIMEOUT: float = float(os.getenv("PG_SMART_ART_ANALYSIS_TIMEOUT", "120"))
_MERMAID_TIMEOUT: float = float(os.getenv("PG_SMART_ART_MERMAID_TIMEOUT", "90"))

# ---------------------------------------------------------------------------
# Diagram type registry
# ---------------------------------------------------------------------------

DIAGRAM_TYPES: dict[str, str] = {
    "process_flow": "How X works (step-by-step process)",
    "comparison_matrix": "X vs Y vs Z comparison",
    "causal_chain": "A causes B which leads to C",
    "hierarchy": "Classification/taxonomy of findings",
    "timeline": "Chronological development of topic",
    "pros_cons": "Advantages vs disadvantages",
    "decision_tree": "If X then Y, else Z",
}

# ---------------------------------------------------------------------------
# Pydantic schemas for structured LLM output
# ---------------------------------------------------------------------------


class DiagramRecommendation(BaseModel):
    """A single recommendation for a diagram to add to a report section."""

    section_id: str = Field(description="The section_id this diagram targets")
    section_title: str = Field(description="Title of the targeted section")
    diagram_type: str = Field(description="One of the supported DIAGRAM_TYPES keys")
    description: str = Field(
        description="What the diagram should show, grounded in the section content"
    )

    @field_validator("diagram_type")
    @classmethod
    def validate_diagram_type(cls, v: str) -> str:
        """Coerce to closest valid type; reject unknowns."""
        normalised = v.strip().lower().replace("-", "_").replace(" ", "_")
        if normalised in DIAGRAM_TYPES:
            return normalised
        # Attempt fuzzy match on prefix
        for key in DIAGRAM_TYPES:
            if normalised.startswith(key[:6]):
                logger.debug(
                    "[smart_art] Coerced diagram_type '%s' -> '%s'", v, key
                )
                return key
        logger.warning(
            "[smart_art] Unknown diagram_type '%s', defaulting to 'process_flow'", v
        )
        return "process_flow"


class DiagramAnalysisResult(BaseModel):
    """Full analysis output: which sections deserve diagrams."""

    recommendations: list[DiagramRecommendation] = Field(
        default_factory=list,
        description="2-5 sections that would benefit from a visual diagram",
    )


# ---------------------------------------------------------------------------
# Mermaid validation helpers
# ---------------------------------------------------------------------------

# Valid Mermaid diagram start tokens (non-exhaustive but covers common types)
_MERMAID_START_PATTERNS = [
    "graph ",
    "graph\n",
    "flowchart ",
    "flowchart\n",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "erDiagram",
    "gantt",
    "pie",
    "journey",
    "gitgraph",
    "mindmap",
    "timeline",
    "xychart",
    "block-beta",
    "sankey-beta",
    "quadrantChart",
]

_CODE_FENCE_RE = re.compile(
    r"^```(?:mermaid|mmd|text)?\s*\n(.*?)```\s*$",
    re.DOTALL | re.MULTILINE,
)


def _strip_code_fences(raw: str) -> str:
    """Remove markdown code fences wrapping Mermaid code."""
    text = raw.strip()
    match = _CODE_FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    # Also handle single-line fence at start/end
    if text.startswith("```"):
        lines = text.split("\n")
        # Drop first line (```mermaid) and last line (```)
        inner_lines = []
        started = False
        for line in lines:
            if not started and line.strip().startswith("```"):
                started = True
                continue
            if started and line.strip() == "```":
                break
            if started:
                inner_lines.append(line)
        if inner_lines:
            return "\n".join(inner_lines).strip()
    return text


def _validate_mermaid(code: str) -> bool:
    """
    Basic structural validation for Mermaid.js code.

    Checks that the code begins with a recognised diagram declaration
    and contains at least one relationship or node definition. This is
    intentionally lenient — full rendering validation is left to the
    client-side Mermaid renderer.
    """
    if not code or len(code.strip()) < 10:
        return False

    normalised = code.strip().lower()
    has_valid_start = any(
        normalised.startswith(pattern.lower()) for pattern in _MERMAID_START_PATTERNS
    )
    if not has_valid_start:
        logger.debug(
            "[smart_art] Mermaid validation failed: unrecognised start token. "
            "First 60 chars: '%s'",
            code.strip()[:60],
        )
        return False

    # Must have at least two non-empty lines (declaration + content)
    meaningful_lines = [
        line for line in code.strip().split("\n") if line.strip()
    ]
    if len(meaningful_lines) < 2:
        logger.debug("[smart_art] Mermaid validation failed: fewer than 2 lines")
        return False

    return True


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_ANALYSIS_SYSTEM_PROMPT = (
    "You are a research report visualization specialist. "
    "You identify which report sections benefit most from visual diagrams "
    "and select the appropriate diagram type for each.\n\n"
    "Available diagram types:\n"
    + "\n".join(f'- "{k}": {v}' for k, v in DIAGRAM_TYPES.items())
    + "\n\n"
    "Output format example:\n"
    '{"recommendations": [{"section_id": "s01", "section_title": "Mechanisms of Action", '
    '"diagram_type": "process_flow", "description": "Step-by-step process of how compound X '
    'binds to receptor Y, triggers pathway Z, and produces effect W as described in the section"}]}'
)

_ANALYSIS_PROMPT_TEMPLATE = (
    "Given these report sections, identify 2-5 that would benefit from a "
    "visual diagram. For each, specify the diagram type and what the diagram "
    "should show.\n\n"
    "SECTIONS:\n{sections_text}\n\n"
    "Constraints:\n"
    "- Select at most {max_diagrams} sections.\n"
    "- Only recommend a diagram if it adds genuine clarity beyond the text.\n"
    "- The description must reference specific facts or structures present in "
    "the section content.\n"
    "- Choose the diagram type that best fits the section's analytical structure."
)

_MERMAID_SYSTEM_PROMPT = (
    "You are a Mermaid.js diagram expert. "
    "You produce syntactically correct Mermaid code that visualizes "
    "research findings accurately. "
    "Output ONLY the raw Mermaid code — no markdown fences, no explanation, "
    "no commentary."
)

_MERMAID_PROMPT_TEMPLATE = (
    "Given this research section about {topic}, generate a {diagram_type} "
    "Mermaid.js diagram. Use ONLY facts stated in the text. Do not invent "
    "data. Include citation references [N] on relevant nodes where applicable. "
    "Return ONLY the Mermaid code, no explanation.\n\n"
    "Diagram type description: {diagram_description}\n\n"
    "SECTION CONTENT:\n{section_content}\n\n"
    "SUPPORTING EVIDENCE SUMMARIES:\n{evidence_summaries}"
)


# ---------------------------------------------------------------------------
# SmartArtGenerator
# ---------------------------------------------------------------------------


class SmartArtGenerator:
    """
    Generates content-level Mermaid.js diagrams for research report sections.

    Usage:
        generator = SmartArtGenerator()
        diagrams = await generator.generate_smart_art_for_report(
            sections=report_sections,
            evidence=all_evidence,
            llm_client=openrouter_client,
        )
        # diagrams: {section_id: mermaid_code_string, ...}
    """

    def __init__(self) -> None:
        self._tracer = get_tracer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze_sections(
        self,
        sections: list[dict],
        llm_client: OpenRouterClient,
    ) -> list[dict]:
        """
        Identify which sections (2-5) would benefit from a visual diagram.

        Parameters
        ----------
        sections : list[dict]
            Report sections, each with at minimum ``section_id``, ``title``,
            and ``content`` keys (matching ``ReportSection`` TypedDict).
        llm_client : OpenRouterClient
            The shared LLM client instance.

        Returns
        -------
        list[dict]
            Each entry: ``{"section_id", "section_title", "diagram_type",
            "description"}``. Empty list on total failure.
        """
        if not sections:
            logger.warning("[smart_art] analyze_sections called with empty sections list")
            return []

        sections_text = self._format_sections_for_analysis(sections)
        prompt = _ANALYSIS_PROMPT_TEMPLATE.format(
            sections_text=sections_text,
            max_diagrams=PG_MAX_SMART_ART,
        )

        try:
            result: DiagramAnalysisResult = await llm_client.generate_structured(
                prompt=prompt,
                schema=DiagramAnalysisResult,
                system=_ANALYSIS_SYSTEM_PROMPT,
                max_tokens=_ANALYSIS_MAX_TOKENS,
                timeout=_ANALYSIS_TIMEOUT,
            )
        except Exception as exc:
            logger.error(
                "[smart_art] LLM analysis call failed: %s", str(exc)[:200]
            )
            return []

        # Validate that recommended section_ids actually exist
        valid_ids = {s.get("section_id") or s.get("id", "") for s in sections}
        validated: list[dict] = []
        for rec in result.recommendations:
            if rec.section_id not in valid_ids:
                logger.warning(
                    "[smart_art] LLM recommended non-existent section_id '%s', skipping",
                    rec.section_id,
                )
                continue
            validated.append({
                "section_id": rec.section_id,
                "section_title": rec.section_title,
                "diagram_type": rec.diagram_type,
                "description": rec.description,
            })

        # Enforce cap
        if len(validated) > PG_MAX_SMART_ART:
            logger.info(
                "[smart_art] Capping recommendations from %d to %d",
                len(validated),
                PG_MAX_SMART_ART,
            )
            validated = validated[:PG_MAX_SMART_ART]

        logger.info(
            "[smart_art] Analysis complete: %d sections recommended for diagrams",
            len(validated),
        )
        return validated

    async def generate_mermaid(
        self,
        section_title: str,
        section_content: str,
        evidence_summaries: list[str],
        diagram_type: str,
        llm_client: OpenRouterClient,
    ) -> str:
        """
        Generate a Mermaid.js diagram for a single section.

        Parameters
        ----------
        section_title : str
            Title of the target section (used as the topic in the prompt).
        section_content : str
            Full text content of the section.
        evidence_summaries : list[str]
            Summarised evidence statements supporting this section.
        diagram_type : str
            One of the keys in ``DIAGRAM_TYPES``.
        llm_client : OpenRouterClient
            The shared LLM client instance.

        Returns
        -------
        str
            Valid Mermaid.js code string. Empty string on failure.
        """
        if not section_content.strip():
            logger.warning(
                "[smart_art] generate_mermaid called with empty content for '%s'",
                section_title,
            )
            return ""

        diagram_description = DIAGRAM_TYPES.get(diagram_type, DIAGRAM_TYPES["process_flow"])
        evidence_text = "\n".join(
            f"- {summary}" for summary in evidence_summaries
        ) if evidence_summaries else "(No additional evidence summaries provided)"

        prompt = _MERMAID_PROMPT_TEMPLATE.format(
            topic=section_title,
            diagram_type=diagram_type,
            diagram_description=diagram_description,
            section_content=section_content,
            evidence_summaries=evidence_text,
        )

        try:
            response = await llm_client.generate(
                prompt=prompt,
                system=_MERMAID_SYSTEM_PROMPT,
                max_tokens=_MERMAID_MAX_TOKENS,
                temperature=_MERMAID_TEMPERATURE,
                timeout=_MERMAID_TIMEOUT,
            )
        except Exception as exc:
            logger.error(
                "[smart_art] Mermaid generation LLM call failed for '%s': %s",
                section_title,
                str(exc)[:200],
            )
            return ""

        raw_code = response.content.strip()
        if not raw_code:
            logger.warning(
                "[smart_art] LLM returned empty content for '%s' diagram", section_title
            )
            return ""

        # Strip code fences if present (LLM sometimes wraps in ```mermaid)
        mermaid_code = _strip_code_fences(raw_code)

        if not _validate_mermaid(mermaid_code):
            logger.warning(
                "[smart_art] Invalid Mermaid code for section '%s' "
                "(type=%s, length=%d). First 120 chars: '%s'",
                section_title,
                diagram_type,
                len(mermaid_code),
                mermaid_code[:120],
            )
            # FIX-CITE-3/A4: Retry with simpler diagram type (flowchart TD)
            logger.info(
                "[smart_art] FIX-A4: Retrying '%s' with simplified flowchart",
                section_title[:40],
            )
            try:
                retry_prompt = (
                    f"Create a simple Mermaid.js flowchart (flowchart TD) for:\n"
                    f"Section: {section_title}\n"
                    f"Use at most 10 nodes. Keep node labels under 40 characters.\n"
                    f"Output ONLY valid Mermaid code, no markdown fences."
                )
                retry_resp = await llm_client.generate(
                    prompt=retry_prompt,
                    max_tokens=1500,
                    temperature=0.3,
                )
                retry_code = _strip_code_fences(retry_resp.content.strip())
                if _validate_mermaid(retry_code):
                    logger.info(
                        "[smart_art] FIX-A4: Retry succeeded for '%s' (%d chars)",
                        section_title[:40],
                        len(retry_code),
                    )
                    return retry_code
            except Exception as retry_exc:
                logger.warning(
                    "[smart_art] FIX-A4: Retry failed for '%s': %s",
                    section_title[:40],
                    str(retry_exc)[:100],
                )
            return ""

        # FIX-071: Reject trivial diagrams (<10 lines or <200 chars).
        # s05 "Healthy Diet → Insulin Sensitivity" (6 lines) and
        # s12 "Identify Population → Contraindication?" (6 lines)
        # added no value in TEST_071. Minimum 10 lines ensures substance.
        _min_lines = int(os.getenv("PG_DIAGRAM_MIN_LINES", "10"))
        _diagram_lines = len(mermaid_code.strip().split("\n"))
        if _diagram_lines < _min_lines:
            logger.warning(
                "[smart_art] FIX-071: Rejected trivial diagram for '%s' "
                "(%d lines < %d minimum)",
                section_title[:40], _diagram_lines, _min_lines,
            )
            return ""

        logger.info(
            "[smart_art] Generated %s diagram for '%s' (%d chars, %d lines)",
            diagram_type,
            section_title,
            len(mermaid_code),
            _diagram_lines,
        )
        return mermaid_code

    async def generate_smart_art_for_report(
        self,
        sections: list[dict],
        evidence: list[dict],
        llm_client: OpenRouterClient,
        max_diagrams: int = PG_MAX_SMART_ART,
    ) -> dict[str, str]:
        """
        Main entry point: generate Mermaid.js diagrams for a completed report.

        Parameters
        ----------
        sections : list[dict]
            All report sections (``ReportSection`` dicts with ``section_id``,
            ``title``, ``content``, and ``evidence_ids``).
        evidence : list[dict]
            All evidence pieces (``EvidencePiece`` dicts with ``evidence_id``
            and ``statement``).
        llm_client : OpenRouterClient
            The shared LLM client instance.
        max_diagrams : int
            Maximum number of diagrams to generate (overrides env default).

        Returns
        -------
        dict[str, str]
            Mapping of ``section_id`` to Mermaid.js code string for each
            section that received a diagram. Empty dict on total failure
            or when the feature is disabled.
        """
        if not PG_SMART_ART_ENABLED:
            logger.info("[smart_art] Feature disabled (PG_SMART_ART_ENABLED=0)")
            return {}

        if not sections:
            logger.warning("[smart_art] No sections provided, returning empty")
            return {}

        if not llm_client:
            logger.error("[smart_art] No LLM client provided")
            return {}

        effective_max = min(max_diagrams, PG_MAX_SMART_ART)
        logger.info(
            "[smart_art] Starting diagram generation for %d sections (max=%d)",
            len(sections),
            effective_max,
        )

        # Build evidence lookup: evidence_id -> statement
        evidence_by_id: dict[str, str] = {}
        for piece in evidence:
            eid = piece.get("evidence_id", "")
            statement = piece.get("statement", "")
            if eid and statement:
                evidence_by_id[eid] = statement

        # Step 1: Analyze sections to identify diagram candidates
        recommendations = await self.analyze_sections(sections, llm_client)

        if not recommendations:
            logger.info("[smart_art] No sections recommended for diagrams")
            return {}

        # Enforce caller-specified cap
        if len(recommendations) > effective_max:
            recommendations = recommendations[:effective_max]

        # Build section lookup for content retrieval
        section_by_id: dict[str, dict] = {}
        for sec in sections:
            sid = sec.get("section_id") or sec.get("id", "")
            if sid:
                section_by_id[sid] = sec

        # Step 2: Generate Mermaid diagrams for each recommended section
        results: dict[str, str] = {}
        for rec in recommendations:
            sid = rec["section_id"]
            sec_data = section_by_id.get(sid)
            if not sec_data:
                logger.warning(
                    "[smart_art] Section '%s' not found in section lookup, skipping",
                    sid,
                )
                continue

            section_content = sec_data.get("content", "")
            section_title = rec["section_title"]
            diagram_type = rec["diagram_type"]

            # FIX-CITE-3/A3: Heuristic override for diagram type based on content
            table_count = section_content.count("|:---")
            comparison_words = sum(1 for w in ["versus", "vs.", "compared to", "in contrast"]
                                  if w in section_content.lower())
            if table_count >= 2 or comparison_words >= 3:
                if diagram_type not in ("comparison_matrix",):
                    diagram_type = "comparison_matrix"
                    logger.info(
                        "[smart_art] FIX-A3: Overrode type to comparison_matrix "
                        "for '%s' (tables=%d, comparisons=%d)",
                        section_title[:40], table_count, comparison_words,
                    )

            # Gather evidence summaries for this section
            section_evidence_ids = sec_data.get("evidence_ids", [])
            evidence_summaries = [
                evidence_by_id[eid]
                for eid in section_evidence_ids
                if eid in evidence_by_id
            ]

            mermaid_code = await self.generate_mermaid(
                section_title=section_title,
                section_content=section_content,
                evidence_summaries=evidence_summaries,
                diagram_type=diagram_type,
                llm_client=llm_client,
            )

            if mermaid_code:
                results[sid] = mermaid_code
                if self._tracer:
                    self._tracer.log_event(
                        event_type="smart_art_generated",
                        data={
                            "section_id": sid,
                            "section_title": section_title,
                            "diagram_type": diagram_type,
                            "mermaid_length": len(mermaid_code),
                        },
                    )
            else:
                logger.warning(
                    "[smart_art] Failed to generate diagram for section '%s' (%s)",
                    sid,
                    diagram_type,
                )

        logger.info(
            "[smart_art] Diagram generation complete: %d/%d successful",
            len(results),
            len(recommendations),
        )
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_sections_for_analysis(sections: list[dict]) -> str:
        """
        Format report sections into a compact text block for the analysis
        prompt. Includes section_id, title, and a truncated content preview
        to stay within token limits while providing enough context for the
        LLM to make informed diagram-type decisions.
        """
        max_content_preview: int = int(
            os.getenv("PG_SMART_ART_CONTENT_PREVIEW_CHARS", "1500")
        )
        parts: list[str] = []
        for sec in sections:
            sid = sec.get("section_id") or sec.get("id", "unknown")
            title = sec.get("title", "Untitled")
            content = sec.get("content", "")
            word_count = len(content.split())
            preview = content[:max_content_preview]
            if len(content) > max_content_preview:
                preview += " [...]"
            parts.append(
                f"--- Section {sid}: {title} ({word_count} words) ---\n{preview}"
            )
        return "\n\n".join(parts)
