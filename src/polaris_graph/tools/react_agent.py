"""ReAct analysis agent — autonomous tool selection for evidence analysis.

Supports three pipeline modes (PG_ANALYSIS_PIPELINE env var):
- "8phase" (default): 6-phase adaptive pipeline when PG_ADAPTIVE_SCAFFOLD=1:
    Plan→Execute→Briefing+Classify→Scaffold(5-lens)→GapFill→Write+SelfRefine→Verify
  Falls back to legacy 8-phase (critique→rewrite) when PG_ADAPTIVE_SCAFFOLD=0.
- "legacy": Plan→Execute→Interpret→Verify (2 LLM calls, ReWOO pattern)
- "react": Per-step LLM decisions (up to 5+1 LLM calls)

The adaptive pipeline fixes 6 loopholes identified by red team review:
1. Time budget trap → deleted critique+rewrite, 75s headroom
2. Refinement spaghetti → SELF-REFINE absorbs critique+rewrite
3. Length guard kills artifacts → table-aware bypass
4. Semantic vector trap → JSON gap queries with positive phrasing
5. Self-scoring sycophancy → boolean checklist, not 1-10 score
6. Intent anchoring bias → WILL not WON'T in intent brief

The agent enforces citation provenance: every analysis result traces back
to original evidence IDs, never "POLARIS Analysis Toolkit".
"""

import asyncio
import json
import logging
import os
import re
import time

import numpy as np
from pydantic import BaseModel, Field, field_validator, model_validator
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist

from src.polaris_graph.tools.analysis_notebook import AnalysisNotebook, AnalysisStep
from src.polaris_graph.tools.analysis_toolkit import _safe_float
from src.polaris_graph.tools.tool_registry import (
    ToolRegistry,
    ToolResult,
    build_default_registry,
)
from src.utils.embedding_service import embed_text, embed_texts
from src.polaris_graph.settings import resolve

logger = logging.getLogger("polaris_graph")

_MAX_ITERATIONS = int(resolve("PG_REACT_MAX_ITERATIONS"))
_TIMEOUT_SECONDS = int(resolve("PG_REACT_TIMEOUT_SECONDS"))
_TOOL_TIMEOUT = int(resolve("PG_REACT_TOOL_TIMEOUT"))
_INTERPRET_TIMEOUT = int(os.getenv("PG_REACT_INTERPRET_TIMEOUT", "180"))

# 8-phase pipeline env vars
_ANALYSIS_PIPELINE = os.getenv("PG_ANALYSIS_PIPELINE", "8phase")
_DOMAIN_RELEVANCE_THRESHOLD = float(
    resolve("PG_DOMAIN_RELEVANCE_THRESHOLD"),
)
_LEARNINGS_PER_CLUSTER = int(resolve("PG_LEARNINGS_PER_CLUSTER"))
_EVIDENCE_PER_CLUSTER = int(resolve("PG_EVIDENCE_PER_CLUSTER"))
_MAX_CLUSTERS = int(resolve("PG_MAX_CLUSTERS"))
_MAX_GAP_EVIDENCE = int(resolve("PG_MAX_GAP_EVIDENCE"))
_MAX_INTERPRETATION_REWRITES = int(
    resolve("PG_MAX_INTERPRETATION_REWRITES"),
)
_SCAFFOLD_TIMEOUT = int(resolve("PG_SCAFFOLD_TIMEOUT"))
_CRITIQUE_TIMEOUT = int(resolve("PG_CRITIQUE_TIMEOUT"))

# 6-phase adaptive pipeline env vars
_ADAPTIVE_SCAFFOLD = resolve("PG_ADAPTIVE_SCAFFOLD") == "1"
_REFINER_ENABLED = resolve("PG_REFINER_ENABLED") == "1"
_SELF_REFINE_ENABLED = resolve("PG_SELF_REFINE_ENABLED") == "1"
_SELF_REFINE_MAX_ITERATIONS = int(
    resolve("PG_SELF_REFINE_MAX_ITERATIONS"),
)

# WS-5: CiteFix post-processing (ACL 2025 Industry)
_CITEFIX_ENABLED = resolve("PG_CITEFIX_ENABLED") == "1"
_CITEFIX_KEYWORD_MIN = int(os.getenv("PG_CITEFIX_KEYWORD_MIN", "3"))
_CITEFIX_SEMANTIC_THRESHOLD = float(
    resolve("PG_CITEFIX_SEMANTIC_THRESHOLD"),
)

# Generate-Then-Attribute: separate prose generation from citation placement
# When ON, scaffold uses (refs: ev_xxx) metadata instead of [CITE:ev_xxx],
# write prompts produce citation-free prose, and _attribute_citations()
# adds citations programmatically at sentence boundaries using 3 strategies:
# number matching → keyword overlap → embedding similarity.
_GTA_ENABLED = resolve("PG_GENERATE_THEN_ATTRIBUTE") == "1"
_GTA_THRESHOLD = float(resolve("PG_ATTRIBUTION_THRESHOLD"))
_GTA_MAX_PER_SENTENCE = int(
    resolve("PG_ATTRIBUTION_MAX_PER_SENTENCE"),
)
_GTA_KEYWORD_MIN = int(os.getenv("PG_ATTRIBUTION_KEYWORD_MIN", "3"))

# Hybrid Evidence: numbered source passages instead of claim questions
# STORM/OpenScholar/Attribute-First pattern (ACL 2024-2026).
# When ON: evidence grouped by theme with [N] markers, LLM cites by
# number, post-process maps [N] -> [CITE:ev_xxx].
_HYBRID_EVIDENCE = resolve("PG_HYBRID_EVIDENCE") == "1"

# Learnings extraction env vars
_LLM_LEARNINGS_ENABLED = resolve("PG_LLM_LEARNINGS_ENABLED") == "1"
_LEARNINGS_BATCH_SIZE = int(resolve("PG_LEARNINGS_BATCH_SIZE"))
_LEARNINGS_BATCH_TIMEOUT = int(resolve("PG_LEARNINGS_BATCH_TIMEOUT"))
_LEARNINGS_MAX_CONCURRENCY = int(
    resolve("PG_LEARNINGS_MAX_CONCURRENCY"),
)

# Tool names Qwen is allowed to pick (for extraction from malformed JSON)
_KNOWN_TOOLS = {
    "extract_numeric_data", "query_evidence_sql", "statistical_summary",
    "comparison_table", "meta_analysis", "agreement_analysis",
    "execute_python", "rank_by_impact", "stop",
}

# Wave 4: Domain terms excluded from parroting Jaccard to focus on structural
# words that indicate actual copying (PlagBench domain-term exclusion pattern).
# C6 fix: only truly universal academic stopwords, not domain-specific terms.
# Override via PG_DOMAIN_TERMS_EXTRA env var (comma-separated).
_DOMAIN_TERMS_BASE = frozenset({
    "results", "study", "research", "data", "method", "using", "based",
    "system", "applied", "found", "showed", "observed", "reported",
    "obtained", "measured", "determined", "compared", "evaluated",
    "analysis", "performance", "process", "demonstrated", "indicated",
    "significant", "respectively", "approximately", "conditions",
})
_extra = resolve("PG_DOMAIN_TERMS_EXTRA")
_DOMAIN_TERMS = _DOMAIN_TERMS_BASE | frozenset(
    w.strip().lower() for w in _extra.split(",") if w.strip()
)

# Wave 3: Non-entity words filtered from entity extraction to avoid
# matching sentence-initial words that aren't real entities.
_NON_ENTITIES = frozenset({
    "The", "However", "Additionally", "Furthermore", "Moreover",
    "Although", "While", "Because", "Since", "When", "Where",
    "This", "That", "These", "Those", "Each", "Every", "Some",
    "Most", "Many", "Several", "Here", "There", "Both", "All",
    "Other", "Such", "Any", "One", "Two", "Three", "Four", "Five",
    "For", "From", "With", "Into", "Over", "Under", "About",
    "After", "Before", "During", "Between", "Through", "Among",
})

# P4: Hyphenated compound prefixes — words that are NOT standalone entities
# when they appear as the first component of a hyphenated compound
# (e.g., "Cross-linked" → should return "Cross-linked", not "Cross").
_ENTITY_PREFIXES = frozenset({
    "Cross", "Pre", "Post", "Non", "Sub", "Multi",
    "Over", "Under", "Out", "Re",
})

# P0: RCS template echo patterns — unambiguous template leakage.
# CR5: only match "performs regarding" (clear template echo) and
# "role in X regarding" (from the replacement template if it leaks).
# "demonstrates significant" is NOT matched — it's valid analytical prose.
_TEMPLATE_ECHO = re.compile(
    r'[^.!?]*\b(?:performs?\s+regarding\b|'
    r'\brole\s+in\s+\w+\s+regarding\b)[^.!?]*[.!?]',
    re.IGNORECASE,
)

# P0 Fix 3: Filler "X demonstrates Y" sentences — only match when the
# entire sentence is "{Entity} demonstrates {vague adj} {vague noun}."
# with no specific data or citations.
_FILLER_DEMONSTRATES = re.compile(
    r'(?:^|(?<=[.!?]\s))[A-Z]\w+\s+demonstrates?\s+'
    r'(?:significant|important|notable)\s+\w+\s*\.',
    re.MULTILINE,
)

# D2-FIX: Broader template-echo pattern — catches "Surface demonstrates
# surface modification via plasma" where the subject word echoes in the
# predicate.  Jaccard guard in _post_process_interpretation() prevents
# over-stripping valid prose.
_TEMPLATE_ECHO_DEMONSTRATES = re.compile(
    r'(?:^|(?<=[.!?]\s))'               # sentence boundary
    r'([A-Z][A-Za-z]+(?:\s+[A-Za-z]+)*'  # subject phrase (1+ words)
    r'\s+demonstrates?\s+'                # "demonstrate(s)"
    r'[^.!?]+[.!?])',                     # rest of sentence
    re.MULTILINE,
)

# P1: Synonym substitution table (BloomScrub pattern, arxiv:2504.16046).
# CR2: ONLY non-technical connectors/adverbs. Domain terms (removal,
# concentration, treatment, membrane, etc.) are EXCLUDED — swapping
# them changes technical meaning.
_SYNONYM_TABLE: dict[str, str] = {
    # Verbs (non-domain-specific)
    "achieves": "attains", "demonstrates": "exhibits",
    "shows": "reveals", "indicates": "suggests",
    "provides": "delivers", "utilizes": "employs",
    "obtained": "recorded", "observed": "noted",
    "reported": "documented", "conducted": "performed",
    # Adjectives (non-domain)
    "significant": "substantial", "important": "critical",
    "promising": "encouraging", "excellent": "outstanding",
    "various": "diverse", "suitable": "appropriate",
    "traditional": "conventional", "enhanced": "augmented",
    "rapid": "swift", "superior": "preferable",
    # Adverbs
    "relatively": "comparatively", "currently": "presently",
    "typically": "generally", "widely": "broadly",
    "primarily": "chiefly", "approximately": "roughly",
    # Nouns (non-domain connectors only)
    "advantages": "benefits", "challenges": "difficulties",
    "limitation": "constraint", "approach": "methodology",
}

# P1: Verbatim-required patterns — skip synonym rewrite for these.
_VERBATIM_REQUIRED = re.compile(
    r'US\s+\d+,\d+|'                                    # Patent refs
    r'\$\d+\.?\d*\s*(?:billion|million|trillion)|'       # Dollar figures
    r'(?:\d+\.?\d*\s*(?:%|mg|nm|µm|°C|kWh|MPa)){3,}',  # 3+ nums+units
)

# P2: Citation validation threshold (cosine similarity).
# CR3: 0.15 is derived from stress test data — FAIL cases had
# sem=-0.04 and sem=0.15, all PASS cases had sem>=0.41.
_CITE_VALIDATION_THRESHOLD = float(
    resolve("PG_CITE_VALIDATION_THRESHOLD"),
)

# R5: Legitimate doubled words (preserved by PDF artifact repair).
_R5_LEGIT_DOUBLES = frozenset({"had", "that", "can", "the"})

# R6: Scientific lens context words (skip scrubbing near these).
_R6_SCI_LENS_WORDS = frozenset({
    "optical", "convex", "concave", "camera", "microscope",
    "zoom", "contact", "objective", "focal", "crystalline",
    "fisheye", "achromatic", "telephoto",
})

# R3: Scale transformation words (billion, million, etc.).
_R3_SCALE_WORDS = frozenset({
    "billion", "million", "trillion", "thousand", "bn", "mn", "tn",
})

# R7: Known transitive verbs for active-to-passive transform.
# Only these verbs are accepted — prevents misidentifying
# nouns/adjectives as verbs (CRITICAL-1 fix).
_R7_TRANSITIVE_VERBS = frozenset({
    "achieve", "show", "provide", "remove", "demonstrate",
    "exhibit", "indicate", "suggest", "reveal", "produce",
    "generate", "require", "enable", "reduce", "increase",
    "enhance", "maintain", "offer", "display", "yield",
    "cause", "create", "support", "facilitate", "ensure",
    "obtain", "prevent", "improve", "determine", "measure",
    "report", "describe", "confirm", "establish", "represent",
})

# R7: Irregular past participles for passive voice transform.
_R7_IRREGULAR_PP = {
    "show": "shown", "give": "given", "take": "taken",
    "make": "made", "find": "found", "get": "gotten",
    "keep": "kept", "know": "known", "see": "seen",
    "write": "written", "drive": "driven", "break": "broken",
    "choose": "chosen", "grow": "grown", "speak": "spoken",
    "wear": "worn", "begin": "begun", "run": "run",
    "become": "become", "come": "come", "hold": "held",
    "lead": "led", "build": "built", "send": "sent",
    "spend": "spent", "leave": "left", "bring": "brought",
    "buy": "bought", "catch": "caught", "teach": "taught",
    "think": "thought", "seek": "sought", "tell": "told",
    "sell": "sold", "stand": "stood", "lose": "lost",
    "pay": "paid", "meet": "met", "set": "set", "cut": "cut",
    "put": "put", "read": "read", "hit": "hit",
}

# R7: Words ending in 's' that are NOT plural (skip "are" logic).
_R7_SINGULAR_S = frozenset({
    "analysis", "process", "stress", "loss", "access",
    "success", "mass", "class", "glass", "gas", "basis",
    "thesis", "crisis", "diagnosis", "hypothesis", "synthesis",
    "apparatus", "status", "consensus", "focus", "radius",
})

# Wave 2: Metric category lookup for analytical claim generation
_METRIC_CATEGORIES = [
    (re.compile(r'%'), "efficiency/rate"),
    (re.compile(r'mg/[Ll]|ppt|ppb|ppm|µg/[Ll]|ng/[Ll]'), "concentration level"),
    (re.compile(r'\$|cost|price|USD'), "cost metric"),
    (re.compile(r'kWh|MWh|energy'), "energy requirement"),
    (re.compile(r'µm|nm|mm|cm'), "particle/pore size"),
    (re.compile(r'MPa|GPa|kPa|PSI'), "mechanical strength"),
    (re.compile(r'°C|°F|kelvin'), "temperature condition"),
    (re.compile(r'[Ll]/min|m³/h|GPD|gallon'), "flow rate"),
]


class ReactDecision(BaseModel):
    """LLM's decision on what to do next in the ReAct loop.

    Qwen 3.5 Plus sometimes returns simplified JSON that doesn't match
    the schema exactly (e.g. {"tool": "extract_numeric_data"} instead
    of {"reasoning": "...", "action": "..."}). The model_validator
    normalizes common deviations.
    """

    reasoning: str = Field(
        description="Your reasoning for choosing this tool",
        default="",
    )
    action: str = Field(
        description="Tool name to execute, or 'stop' to finish analysis",
    )
    action_input: dict = Field(
        description="Parameters for the tool (empty dict if none needed)",
        default_factory=dict,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_qwen_response(cls, data):
        """Handle common Qwen deviations from the expected schema.

        Known patterns:
        - {"tool": "xxx"} instead of {"action": "xxx"}
        - {"action": {"tool": "xxx"}} nested dict
        - {"next_step": "xxx"} alternate field name
        - Missing "reasoning" field entirely
        - {"thought": "..."} instead of {"reasoning": "..."}
        """
        if not isinstance(data, dict):
            return data

        # Normalize "tool" -> "action"
        for alt in ("tool", "tool_name", "next_step", "next_action", "name"):
            if alt in data and "action" not in data:
                data["action"] = data.pop(alt)

        # Unwrap nested {"action": {"tool": "xxx"}}
        if isinstance(data.get("action"), dict):
            nested = data["action"]
            tool_name = (
                nested.get("tool")
                or nested.get("name")
                or nested.get("tool_name")
                or ""
            )
            if tool_name:
                data["action"] = str(tool_name)
            else:
                # Last resort: find any known tool name in the dict values
                for v in nested.values():
                    if isinstance(v, str) and v in _KNOWN_TOOLS:
                        data["action"] = v
                        break
                else:
                    data["action"] = "stop"

        # Normalize "thought"/"explanation"/"reason" -> "reasoning"
        for alt in ("thought", "explanation", "reason", "thinking",
                     "rationale"):
            if alt in data and "reasoning" not in data:
                data["reasoning"] = data.pop(alt)

        # Default reasoning if missing
        if "reasoning" not in data or not data["reasoning"]:
            action = data.get("action", "unknown")
            data["reasoning"] = f"Selected {action}"

        # Normalize "params"/"parameters"/"input"/"args" -> "action_input"
        for alt in ("params", "parameters", "input", "args",
                     "tool_input", "kwargs"):
            if alt in data and "action_input" not in data:
                data["action_input"] = data.pop(alt)

        return data

    @field_validator("action", mode="before")
    @classmethod
    def coerce_action(cls, v):
        """Coerce action to string, handling unexpected types."""
        if isinstance(v, str):
            return v.strip().lower()
        if isinstance(v, dict):
            # {"tool": "xxx"} pattern
            return str(
                v.get("tool") or v.get("name") or v.get("action") or "stop"
            ).strip().lower()
        return str(v).strip().lower() if v else "stop"


class PlannedStep(BaseModel):
    """A single planned analysis step for the agentic pipeline.

    Qwen 3.5 Plus returns simplified JSON — the model_validator
    normalizes common deviations (same pattern as ReactDecision).
    """

    tool_name: str = Field(description="Tool to execute")
    reasoning: str = Field(
        description="Why this tool should run", default="",
    )
    parameters: dict = Field(
        description="Tool parameters", default_factory=dict,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_qwen_response(cls, data):
        """Handle common Qwen deviations from the expected schema."""
        if not isinstance(data, dict):
            return data
        for alt in ("tool", "name", "action", "step", "tool_id"):
            if alt in data and "tool_name" not in data:
                data["tool_name"] = data.pop(alt)
        for alt in ("thought", "explanation", "reason", "rationale", "why"):
            if alt in data and "reasoning" not in data:
                data["reasoning"] = data.pop(alt)
        for alt in ("params", "args", "input", "kwargs", "action_input"):
            if alt in data and "parameters" not in data:
                data["parameters"] = data.pop(alt)
        if "reasoning" not in data or not data.get("reasoning"):
            data["reasoning"] = f"Run {data.get('tool_name', 'unknown')}"
        return data

    @field_validator("tool_name", mode="before")
    @classmethod
    def coerce_tool_name(cls, v):
        """Coerce tool_name to lowercase string."""
        if isinstance(v, str):
            return v.strip().lower()
        if isinstance(v, dict):
            return str(
                v.get("tool") or v.get("name") or "extract_numeric_data"
            ).strip().lower()
        return str(v).strip().lower() if v else "extract_numeric_data"


class AnalysisPlan(BaseModel):
    """LLM's analysis plan — ordered list of tools to execute.

    The agentic pipeline asks for ONE plan upfront (ReWOO pattern),
    then executes all steps deterministically without further LLM calls.
    """

    steps: list[PlannedStep] = Field(
        description="Ordered list of analysis steps",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_qwen_response(cls, data):
        """Handle common Qwen deviations from the expected schema."""
        # Handle bare list: Qwen returns ["tool1", "tool2"] or [{"tool": ...}]
        if isinstance(data, list):
            data = {"steps": data}
        if not isinstance(data, dict):
            return data
        for alt in ("plan", "tools", "actions", "tool_sequence", "sequence",
                     "analysis_steps", "ordered_steps"):
            if alt in data and "steps" not in data:
                data["steps"] = data.pop(alt)
        # Handle flat tool list: ["extract_numeric_data", "statistical_summary"]
        if isinstance(data.get("steps"), list) and data["steps"]:
            if isinstance(data["steps"][0], str):
                data["steps"] = [{"tool_name": t} for t in data["steps"]]
        return data


# ---------------------------------------------------------------------------
# 8-phase pipeline schemas
# ---------------------------------------------------------------------------

class CritiqueDimension(BaseModel):
    """Single dimension of the interpretation critique."""

    dimension: str = Field(description="Dimension name")
    passed: bool = Field(
        description="Whether this dimension passes", default=False,
    )
    issues: list[str] = Field(
        description="Specific problems found", default_factory=list,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_qwen_response(cls, data):
        if not isinstance(data, dict):
            return data
        for alt in ("name", "dim", "category", "dimension_name"):
            if alt in data and "dimension" not in data:
                data["dimension"] = data.pop(alt)
        for alt in ("pass", "ok", "passed", "status", "result",
                     "verdict"):
            if alt in data and "passed" not in data:
                data["passed"] = data.pop(alt)
        # Coerce string "PASS"/"FAIL" → bool
        if isinstance(data.get("passed"), str):
            data["passed"] = data["passed"].upper() in (
                "PASS", "TRUE", "YES", "OK", "PASSED",
            )
        for alt in ("problems", "findings", "errors"):
            if alt in data and "issues" not in data:
                data["issues"] = data.pop(alt)
        return data


class InterpretationCritique(BaseModel):
    """Structured critique of an interpretation across 5 dimensions."""

    dimensions: list[CritiqueDimension] = Field(
        description="Critique per dimension",
    )
    needs_rewrite: bool = Field(
        description="Whether the interpretation needs rewriting",
    )
    rewrite_instructions: str = Field(
        description="Specific fix instructions for the rewriter",
        default="",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_qwen_response(cls, data):
        if not isinstance(data, dict):
            return data
        # Unwrap nested wrappers: Qwen sometimes wraps in
        # {"interpretation_critique": {actual_fields...}}
        for wrapper_key in list(data.keys()):
            val = data[wrapper_key]
            if (
                isinstance(val, dict)
                and len(data) == 1
                and any(
                    k in val
                    for k in ("dimensions", "needs_rewrite", "evaluation",
                              "dimension_evaluations")
                )
            ):
                data = val
                break
        # Catch-all: ANY key containing a list of dicts → dimensions
        # Qwen invents new field names every run.
        if "dimensions" not in data:
            for key, val in list(data.items()):
                if (
                    isinstance(val, list)
                    and val
                    and isinstance(val[0], dict)
                    and key not in ("needs_rewrite", "rewrite_instructions")
                ):
                    data["dimensions"] = data.pop(key)
                    break
            else:
                # Qwen returned evaluation as a single dict instead of
                # list — convert dict values to dimension list
                for key, val in list(data.items()):
                    if (
                        isinstance(val, dict)
                        and key not in (
                            "needs_rewrite", "rewrite_instructions",
                        )
                        and any(
                            isinstance(v, str)
                            for v in val.values()
                        )
                    ):
                        # {"sub_question_coverage": "PASS", ...}
                        dims = [
                            {"dimension": k, "passed": v}
                            for k, v in val.items()
                        ]
                        data["dimensions"] = dims
                        del data[key]
                        break
        for alt in ("rewrite", "needs_revision", "should_rewrite",
                     "verdict"):
            if alt in data and "needs_rewrite" not in data:
                val = data.pop(alt)
                # Coerce string verdicts like "PASS"/"FAIL" to bool
                if isinstance(val, str):
                    val = val.upper() in ("PASS", "TRUE", "YES", "OK")
                data["needs_rewrite"] = val
        for alt in ("instructions", "fix_instructions", "fixes"):
            if alt in data and "rewrite_instructions" not in data:
                data["rewrite_instructions"] = data.pop(alt)
        # Coerce None/list → "" for rewrite_instructions
        if not isinstance(data.get("rewrite_instructions"), str):
            data["rewrite_instructions"] = str(
                data.get("rewrite_instructions") or ""
            )
        return data


class ExtractedLearning(BaseModel):
    """A single distilled learning extracted from evidence."""

    fact: str = Field(description="Paraphrased concise factual learning")
    source_ids: list[str] = Field(
        description="Evidence IDs this was extracted from",
    )
    category: str = Field(
        description="Fact category", default="general",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_qwen_response(cls, data):
        if not isinstance(data, dict):
            return data
        for alt in ("learning", "insight", "finding", "statement",
                     "text", "content"):
            if alt in data and "fact" not in data:
                data["fact"] = data.pop(alt)
        for alt in ("sources", "evidence_ids", "ids", "evidence",
                     "source_evidence", "from_ids"):
            if alt in data and "source_ids" not in data:
                data["source_ids"] = data.pop(alt)
        for alt in ("type", "topic", "cat", "fact_category"):
            if alt in data and "category" not in data:
                data["category"] = data.pop(alt)
        if isinstance(data.get("source_ids"), str):
            data["source_ids"] = [data["source_ids"]]
        return data


class LearningsBatch(BaseModel):
    """Batch of extracted learnings from evidence statements."""

    learnings: list[ExtractedLearning] = Field(
        description="Extracted factual learnings",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_qwen_response(cls, data):
        if isinstance(data, list):
            data = {"learnings": data}
        if not isinstance(data, dict):
            return data
        for alt in ("facts", "findings", "insights", "extracted",
                     "results", "items"):
            if alt in data and "learnings" not in data:
                data["learnings"] = data.pop(alt)
        return data


class ReactAnalysisAgent:
    """ReAct loop that autonomously analyzes evidence using registered tools.

    Usage:
        agent = ReactAnalysisAgent(client, evidence_store, evidence_ids, query)
        notebook = await agent.run()
        entries = notebook.to_entries()
    """

    def __init__(
        self,
        client,
        evidence_store: dict,
        evidence_ids: list[str],
        query: str,
        registry: ToolRegistry | None = None,
        tracer=None,
        mode: str | None = None,
    ):
        self._client = client
        self._evidence_store = evidence_store
        self._evidence_ids = evidence_ids
        self._query = query
        self._registry = registry or build_default_registry()
        # Hybrid evidence passage state
        self._passage_reverse_map: dict[int, str] = {}
        self._evidence_passages_text: str = ""
        self._tracer = tracer
        self._notebook = AnalysisNotebook(query, evidence_ids)
        # Mode precedence: PG_REACT_MODE env (legacy compat) > constructor
        # > PG_ANALYSIS_PIPELINE env (pipeline default) > "8phase"
        react_mode = resolve("PG_REACT_MODE")
        if react_mode:
            self._mode = react_mode
        elif mode:
            self._mode = mode
        else:
            self._mode = os.getenv("PG_ANALYSIS_PIPELINE", "8phase") or "8phase"

    async def run(self) -> AnalysisNotebook:
        """Execute analysis and return the notebook.

        Dispatches based on pipeline mode:
        - "8phase": Plan→Execute→Briefing→Scaffold→Write→Critique→Rewrite→Verify
        - "legacy"/"agentic": Plan→Execute→Interpret→Verify (2 LLM calls)
        - "react": Per-step LLM decisions
        """
        if self._mode == "react":
            return await self._run_react()
        if self._mode in ("legacy", "agentic"):
            return await self._run_agentic_analysis()
        return await self._run_8phase_analysis()

    async def _run_react(self) -> AnalysisNotebook:
        """Execute the ReAct loop (legacy mode)."""
        start_time = time.monotonic()
        max_iterations = _MAX_ITERATIONS
        timeout = _TIMEOUT_SECONDS

        logger.info(
            "[react] Starting analysis: %d evidence, max_iter=%d, timeout=%ds",
            len(self._evidence_ids), max_iterations, timeout,
        )

        for iteration in range(1, max_iterations + 1):
            elapsed = time.monotonic() - start_time

            # Budget check
            if elapsed >= timeout:
                logger.info(
                    "[react] Timeout reached after %.1fs, stopping", elapsed,
                )
                break

            # Decide next action (retry once on failure)
            decision = None
            for attempt in range(2):
                try:
                    decision = await self._decide(iteration)
                    break
                except Exception as exc:
                    logger.warning(
                        "[react] Decision attempt %d failed at iter %d: %s "
                        "(%s)",
                        attempt + 1, iteration,
                        type(exc).__name__, str(exc)[:200],
                    )
                    if attempt == 0:
                        await asyncio.sleep(1)  # Brief pause before retry

            if decision is None:
                logger.warning(
                    "[react] Decision failed after 2 attempts at iter %d, "
                    "running fallback",
                    iteration,
                )
                await self._run_fallback()
                break

            if decision.action == "stop":
                logger.info(
                    "[react] LLM chose to stop: %s", decision.reasoning[:100],
                )
                break

            # Execute the chosen tool
            step = await self._execute_tool(iteration, decision)
            self._notebook.add_step(step)

            logger.info(
                "[react] Step %d: %s [%s] %.1fs — %s",
                iteration,
                decision.action,
                "OK" if step.result.success else "FAIL",
                step.elapsed_seconds,
                decision.reasoning[:60],
            )

            # Check sufficiency
            if self._is_sufficient():
                logger.info("[react] Sufficient analysis achieved, stopping")
                break

        # If no steps succeeded, run fallback
        if self._notebook.successful_steps == 0:
            logger.warning("[react] No successful steps, running fallback")
            await self._run_fallback()

        # POST-PROCESSING: LLM interprets raw results into real insights
        # This is what separates "regex + scipy" from "analyst with reasoning"
        if self._notebook.successful_steps > 0 and self._client:
            await self._interpret_results()

        total_elapsed = time.monotonic() - start_time
        logger.info(
            "[react] Analysis complete: %d steps (%d ok), %d data points, "
            "%.1fs",
            self._notebook.step_count,
            self._notebook.successful_steps,
            len(self._notebook.data_points),
            total_elapsed,
        )

        return self._notebook

    # -------------------------------------------------------------------
    # Agentic pipeline (Plan -> Execute -> Interpret -> Verify)
    # -------------------------------------------------------------------

    async def _run_agentic_analysis(self) -> AnalysisNotebook:
        """Execute Plan -> Execute -> Interpret -> Verify pipeline.

        Phase 1: PLAN — 1 generate_structured() call produces AnalysisPlan
        Phase 2: EXECUTE — deterministic tool execution, 0 LLM calls
        Phase 3: INTERPRET — 1 generate() call produces analytical prose
        Phase 4: VERIFY — programmatic claim<->evidence check, 0 LLM calls
        """
        start_time = time.monotonic()
        timeout = _TIMEOUT_SECONDS

        logger.info(
            "[agentic] Starting analysis: %d evidence, timeout=%ds",
            len(self._evidence_ids), timeout,
        )

        # Phase 1: PLAN (1 LLM call, ~75s)
        plan = None
        try:
            plan = await self._plan_analysis()
            logger.info(
                "[agentic] Plan: %s",
                [s.tool_name for s in plan.steps],
            )
        except Exception as exc:
            logger.warning(
                "[agentic] Plan failed: %s: %s, using fallback plan",
                type(exc).__name__, str(exc)[:200],
            )

        if not plan or not plan.steps:
            plan = AnalysisPlan(steps=[
                PlannedStep(
                    tool_name="extract_numeric_data",
                    reasoning="Always extract first",
                ),
                PlannedStep(
                    tool_name="statistical_summary",
                    reasoning="Compute statistics on extracted data",
                ),
                PlannedStep(
                    tool_name="query_evidence_sql",
                    reasoning="Get tier distribution and metadata",
                ),
            ])
            logger.info(
                "[agentic] Using fallback plan: %s",
                [s.tool_name for s in plan.steps],
            )

        # Phase 2: EXECUTE (0 LLM calls, ~10s)
        for step_def in plan.steps:
            elapsed = time.monotonic() - start_time
            if elapsed >= timeout:
                logger.info(
                    "[agentic] Timeout after %.1fs, stopping execution",
                    elapsed,
                )
                break

            tool_def = self._registry.get_tool(step_def.tool_name)
            if not tool_def or not tool_def.execute:
                logger.warning(
                    "[agentic] Skipping unknown tool: %s",
                    step_def.tool_name,
                )
                continue

            # Skip data-requiring tools if no data yet
            if tool_def.requires_data and not self._notebook.has_data:
                logger.info(
                    "[agentic] Skipping %s (requires data, none yet)",
                    step_def.tool_name,
                )
                continue

            step_start = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    tool_def.execute(
                        evidence_store=self._evidence_store,
                        data_points=self._notebook.data_points,
                        client=self._client,
                        **step_def.parameters,
                    ),
                    timeout=_TOOL_TIMEOUT,
                )
            except asyncio.TimeoutError:
                result = ToolResult(
                    success=False,
                    tool_name=step_def.tool_name,
                    markdown=f"Tool timed out after {_TOOL_TIMEOUT}s",
                    error=f"Timeout after {_TOOL_TIMEOUT}s",
                )
            except Exception as exc:
                result = ToolResult(
                    success=False,
                    tool_name=step_def.tool_name,
                    markdown=f"Tool error: {str(exc)[:200]}",
                    error=str(exc)[:500],
                )

            step_elapsed = time.monotonic() - step_start
            step = AnalysisStep(
                step_number=self._notebook.step_count + 1,
                reasoning=step_def.reasoning or f"Planned: {step_def.tool_name}",
                tool_name=step_def.tool_name,
                result=result,
                elapsed_seconds=round(step_elapsed, 3),
            )
            self._notebook.add_step(step)

            logger.info(
                "[agentic] Step %d: %s [%s] %.1fs",
                step.step_number,
                step_def.tool_name,
                "OK" if result.success else "FAIL",
                step_elapsed,
            )

        # If no steps succeeded, run deterministic fallback
        if self._notebook.successful_steps == 0:
            logger.warning("[agentic] No successful steps, running fallback")
            await self._run_fallback()

        # Phase 3: INTERPRET (1 LLM call, ~120s)
        if self._notebook.successful_steps > 0 and self._client:
            await self._interpret_results()

        # Phase 4: VERIFY (programmatic, ~5s)
        verification = self._verify_claims()
        if verification:
            logger.info(
                "[agentic] Verification: %d/%d claims verified, "
                "%d mismatches",
                verification.get("verified", 0),
                verification.get("total_claims_checked", 0),
                verification.get("mismatches", 0),
            )

        total_elapsed = time.monotonic() - start_time
        logger.info(
            "[agentic] Complete: %d steps (%d ok), %d data points, %.1fs",
            self._notebook.step_count,
            self._notebook.successful_steps,
            len(self._notebook.data_points),
            total_elapsed,
        )

        return self._notebook

    # -------------------------------------------------------------------
    # 8-phase pipeline (Briefing→Scaffold→Write→Critique→Rewrite→Verify)
    # -------------------------------------------------------------------

    async def _run_8phase_analysis(self) -> AnalysisNotebook:
        """Execute analysis pipeline (6-phase adaptive or 8-phase legacy).

        When PG_ADAPTIVE_SCAFFOLD=1 (default):
          Phase 1: PLAN       — 1 generate_structured() call
          Phase 2: EXECUTE    — deterministic tool execution, 0 LLM calls
          Phase 3: BRIEFING+CLASSIFY — cluster + archetype detection
          Phase 4: SCAFFOLD   — 1 reason(): intent brief + 5-lens + gap queries
          Phase 5: GAP FILL   — 0 LLM: embedding search for missing evidence
          Phase 6: WRITE+REFINE — 2-4 generate(): draft + SELF-REFINE loop
          Phase 6.5: POST-POLISH — programmatic cleanup
          Phase 7: VERIFY     — programmatic claim verification

        When PG_ADAPTIVE_SCAFFOLD=0 (legacy):
          Phases 5-7 use separate write→critique→rewrite flow.
        """
        start_time = time.monotonic()
        timeout = _TIMEOUT_SECONDS
        # INF-3: Per-phase cost/time tracking
        phase_timings: dict[str, float] = {}
        phase_costs: dict[str, float] = {}

        def _snap_cost() -> float:
            """Snapshot current cost from client usage tracker."""
            try:
                cost = self._client.usage.total_cost_usd
                # Guard against MagicMock or non-numeric values
                if isinstance(cost, (int, float)):
                    return float(cost)
                return 0.0
            except (AttributeError, TypeError):
                return 0.0

        logger.info(
            "[8phase] Starting analysis: %d evidence, timeout=%ds",
            len(self._evidence_ids), timeout,
        )

        # Phase 1: PLAN (1 LLM call)
        phase_start = time.monotonic()
        cost_before = _snap_cost()
        plan = None
        try:
            plan = await self._plan_analysis()
            logger.info(
                "[8phase] Plan: %s",
                [s.tool_name for s in plan.steps],
            )
        except Exception as exc:
            logger.warning(
                "[8phase] Plan failed: %s: %s, using fallback",
                type(exc).__name__, str(exc)[:200],
            )

        if not plan or not plan.steps:
            plan = AnalysisPlan(steps=[
                PlannedStep(
                    tool_name="extract_numeric_data",
                    reasoning="Always extract first",
                ),
                PlannedStep(
                    tool_name="statistical_summary",
                    reasoning="Compute statistics on extracted data",
                ),
                PlannedStep(
                    tool_name="query_evidence_sql",
                    reasoning="Get tier distribution and metadata",
                ),
            ])

        phase_timings["plan"] = time.monotonic() - phase_start
        phase_costs["plan"] = _snap_cost() - cost_before

        # Phase 2: EXECUTE (0 LLM calls)
        phase_start = time.monotonic()
        cost_before = _snap_cost()
        for step_def in plan.steps:
            elapsed = time.monotonic() - start_time
            if elapsed >= timeout:
                logger.info("[8phase] Timeout after %.1fs", elapsed)
                break

            tool_def = self._registry.get_tool(step_def.tool_name)
            if not tool_def or not tool_def.execute:
                continue
            if tool_def.requires_data and not self._notebook.has_data:
                continue

            step_start = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    tool_def.execute(
                        evidence_store=self._evidence_store,
                        data_points=self._notebook.data_points,
                        client=self._client,
                        **step_def.parameters,
                    ),
                    timeout=_TOOL_TIMEOUT,
                )
            except asyncio.TimeoutError:
                result = ToolResult(
                    success=False, tool_name=step_def.tool_name,
                    error=f"Timeout after {_TOOL_TIMEOUT}s",
                )
            except Exception as exc:
                result = ToolResult(
                    success=False, tool_name=step_def.tool_name,
                    error=str(exc)[:500],
                )

            step_elapsed = time.monotonic() - step_start
            step = AnalysisStep(
                step_number=self._notebook.step_count + 1,
                reasoning=step_def.reasoning or f"Planned: {step_def.tool_name}",
                tool_name=step_def.tool_name,
                result=result,
                elapsed_seconds=round(step_elapsed, 3),
            )
            self._notebook.add_step(step)
            logger.info(
                "[8phase] Step %d: %s [%s] %.1fs",
                step.step_number, step_def.tool_name,
                "OK" if result.success else "FAIL", step_elapsed,
            )

        if self._notebook.successful_steps == 0:
            await self._run_fallback()

        phase_timings["execute"] = time.monotonic() - phase_start
        phase_costs["execute"] = _snap_cost() - cost_before

        # Phase 3: BRIEFING + CLASSIFY
        phase_start = time.monotonic()
        cost_before = _snap_cost()
        elapsed_before_briefing = time.monotonic() - start_time
        remaining = timeout - elapsed_before_briefing
        briefing = await self._build_evidence_briefing()
        classification = (
            self._classify_query(briefing) if _ADAPTIVE_SCAFFOLD else None
        )
        logger.info(
            "[8phase] Briefing: %d learnings, %d clusters, %d sub-questions "
            "(%.0fs remaining)%s",
            len(briefing.get("learnings", [])),
            len(briefing.get("clusters", [])),
            len(briefing.get("sub_questions", [])),
            remaining,
            f", archetype={classification['archetype']}"
            if classification else "",
        )

        phase_timings["briefing"] = time.monotonic() - phase_start
        phase_costs["briefing"] = _snap_cost() - cost_before

        # Phase 4: SCAFFOLD (1 reason() call, includes intent + gaps)
        phase_start = time.monotonic()
        cost_before = _snap_cost()
        scaffold = ""
        gap_queries = []
        elapsed = time.monotonic() - start_time
        if (
            self._notebook.successful_steps > 0
            and self._client
            and elapsed < timeout - 60
        ):
            scaffold_result = await self._generate_analytical_scaffold(
                briefing, classification,
            )
            if isinstance(scaffold_result, dict):
                scaffold = scaffold_result.get("scaffold", "")
                gap_queries = scaffold_result.get("gap_queries", [])
                intent_brief = scaffold_result.get("intent_brief", "")
                if intent_brief:
                    logger.info(
                        "[8phase] Intent brief: %s",
                        intent_brief[:120],
                    )
            else:
                scaffold = scaffold_result
            logger.info(
                "[8phase] Scaffold: %d chars, %d gap queries",
                len(scaffold), len(gap_queries),
            )

        phase_timings["scaffold"] = time.monotonic() - phase_start
        phase_costs["scaffold"] = _snap_cost() - cost_before

        # Phase 5: GAP FILL (0 LLM calls, embedding search)
        phase_start = time.monotonic()
        cost_before = _snap_cost()
        gap_evidence = []
        if gap_queries and _ADAPTIVE_SCAFFOLD:
            gap_evidence = self._fill_evidence_gaps(gap_queries, briefing)

        phase_timings["gap_fill"] = time.monotonic() - phase_start
        phase_costs["gap_fill"] = _snap_cost() - cost_before

        # Phase 6: WRITE + SELF-REFINE (replaces old Phases 5+6+7)
        phase_start = time.monotonic()
        cost_before = _snap_cost()
        interpretation = ""
        elapsed = time.monotonic() - start_time
        if scaffold and self._client and elapsed < timeout - 30:
            if _ADAPTIVE_SCAFFOLD and classification:
                # Attach gap_queries to classification for feedback use
                classification["_gap_queries"] = gap_queries
                interpretation = await self._write_and_refine(
                    scaffold, briefing, classification, gap_evidence,
                    pipeline_start=start_time,
                )
            else:
                # Legacy path: separate write (no self-refine)
                interpretation = await self._write_interpretation(
                    scaffold, briefing,
                )
            logger.info(
                "[8phase] Interpretation: %d chars", len(interpretation),
            )

        # FALLBACK: if scaffold or write failed, ALWAYS use legacy interpret.
        if not interpretation and self._notebook.successful_steps > 0:
            if self._client:
                logger.info(
                    "[8phase] Scaffold/write failed, falling back to "
                    "legacy interpret (elapsed=%.0fs)",
                    time.monotonic() - start_time,
                )
                await self._interpret_results()
                for step in self._notebook.steps:
                    if (
                        step.tool_name == "interpret_results"
                        and step.result.success
                    ):
                        interpretation = step.result.markdown
                        break

        # Hybrid: map passage numbers for legacy/fallback paths
        if (
            _HYBRID_EVIDENCE
            and interpretation
            and self._passage_reverse_map
            and not (_ADAPTIVE_SCAFFOLD and classification)
        ):
            interpretation = self._map_passage_citations(
                interpretation, self._passage_reverse_map,
            )

        # CRITICAL-5: GTA attribution for legacy write + fallback paths
        # (adaptive path attribution happens inside _write_and_refine)
        if (
            _GTA_ENABLED
            and interpretation
            and not (_ADAPTIVE_SCAFFOLD and classification)
        ):
            # Strip LLM-generated citations before programmatic ones
            interpretation = re.sub(
                r'\[CITE:ev_[a-f0-9]+\]', '', interpretation,
            )
            interpretation = re.sub(r'  +', ' ', interpretation)
            interpretation = re.sub(
                r' ([.,;:!?])', r'\1', interpretation,
            )
            interpretation = self._attribute_citations(interpretation)
            logger.info(
                "[8phase] GTA attribution (legacy/fallback): %d cites",
                len(re.findall(
                    r'\[CITE:ev_[a-f0-9]+\]', interpretation,
                )),
            )

        # Legacy critique+rewrite path (when adaptive scaffold OFF)
        if not _ADAPTIVE_SCAFFOLD:
            critique = None
            elapsed = time.monotonic() - start_time
            if (
                interpretation and self._client
                and elapsed < timeout - 30
            ):
                critique = await self._critique_interpretation(
                    interpretation, briefing,
                )
                if critique:
                    logger.info(
                        "[8phase] Critique: needs_rewrite=%s, "
                        "%d/%d dims passed",
                        critique.get("needs_rewrite"),
                        sum(
                            1 for d in critique.get("dimensions", [])
                            if d.get("passed")
                        ),
                        len(critique.get("dimensions", [])),
                    )

            elapsed = time.monotonic() - start_time
            if (
                critique
                and critique.get("needs_rewrite")
                and interpretation
                and self._client
                and elapsed < timeout - 30
            ):
                rewritten = await self._rewrite_interpretation(
                    interpretation, critique, briefing,
                )
                if rewritten:
                    interpretation = rewritten
                    logger.info(
                        "[8phase] Rewrite: %d chars",
                        len(interpretation),
                    )

        # Phase 6.25: AUTO-CHART (VIZ-1: matplotlib via execute_python)
        elapsed = time.monotonic() - start_time
        if (
            interpretation
            and self._client
            and elapsed < timeout - 300
            and _ADAPTIVE_SCAFFOLD
        ):
            chart_text = await self._generate_charts(
                classification, briefing,
            )
            if chart_text:
                interpretation = interpretation.rstrip() + "\n\n" + chart_text

        # VIZ-3: Decision flowchart for conditional recommendations
        if interpretation and _ADAPTIVE_SCAFFOLD:
            flowchart = self._generate_decision_flowchart(interpretation)
            if flowchart:
                interpretation = interpretation.rstrip() + "\n\n" + flowchart

        # Phase 6.5: POST-PROCESS (programmatic cleanup)
        if interpretation:
            cleaned = self._post_process_interpretation(interpretation)
            if cleaned != interpretation:
                interpretation = cleaned
                # Update the notebook step with cleaned content
                for step in self._notebook.steps:
                    if (
                        step.tool_name == "interpret_results"
                        and step.result.success
                    ):
                        step.result = ToolResult(
                            success=True,
                            tool_name="interpret_results",
                            markdown=cleaned,
                            source_evidence_ids=(
                                step.result.source_evidence_ids
                            ),
                            insights=step.result.insights,
                        )
                        break
                logger.info(
                    "[8phase] Post-process: %d -> %d chars",
                    len(interpretation), len(cleaned),
                )

        # Phase 7: VERIFY (programmatic)
        verification = self._verify_claims(briefing=briefing)
        if verification:
            logger.info(
                "[8phase] Verification: %d/%d verified, %d mismatches",
                verification.get("verified", 0),
                verification.get("total_claims_checked", 0),
                verification.get("mismatches", 0),
            )

        # G1: Log gap evidence utilization
        if gap_evidence and interpretation:
            gap_eids = {ge["evidence_id"] for ge in gap_evidence}
            cited_eids = set(
                re.findall(r'\[CITE:(ev_[a-f0-9]+)\]', interpretation),
            )
            gap_cited = gap_eids & cited_eids
            logger.info(
                "[verify] G1: Gap evidence utilization: %d/%d gap IDs cited",
                len(gap_cited), len(gap_eids),
            )

        # G2: Log sub-question coverage from verification
        if verification:
            sq_cov = verification.get("sub_question_coverage", 0)
            logger.info(
                "[verify] G2: Sub-question coverage: %.0f%%",
                sq_cov * 100,
            )

        # G3: 5-lens diversity check (Jaccard on section CONTENT)
        if interpretation and scaffold:
            # Split interpretation into sections by headings
            section_splits = re.split(
                r'(?:^|\n)#{1,3}\s+[^\n]+\n',
                interpretation,
            )
            # Filter to non-trivial sections (>50 chars)
            section_texts = [
                s.strip() for s in section_splits
                if s.strip() and len(s.strip()) > 50
            ]
            if len(section_texts) >= 2:
                max_jaccard = 0.0
                for i, s1 in enumerate(section_texts):
                    w1 = set(
                        w for w in re.findall(r'[a-z]{4,}', s1.lower())
                    )
                    for s2 in section_texts[i + 1:]:
                        w2 = set(
                            w for w in re.findall(
                                r'[a-z]{4,}', s2.lower(),
                            )
                        )
                        if w1 | w2:
                            j = len(w1 & w2) / len(w1 | w2)
                            max_jaccard = max(max_jaccard, j)
                if max_jaccard > 0.6:
                    logger.warning(
                        "[verify] G3: High section content similarity "
                        "(Jaccard=%.2f, %d sections) — lenses may "
                        "overlap",
                        max_jaccard, len(section_texts),
                    )
                else:
                    logger.info(
                        "[verify] G3: Section diversity OK "
                        "(max Jaccard=%.2f, %d sections)",
                        max_jaccard, len(section_texts),
                    )

        total_elapsed = time.monotonic() - start_time
        # INF-3: Log per-phase timing + cost breakdown
        timing_str = ", ".join(
            f"{k}={v:.1f}s" for k, v in phase_timings.items()
        )
        total_cost = _snap_cost()
        cost_str = ", ".join(
            f"{k}=${v:.4f}" for k, v in phase_costs.items() if v > 0
        )
        logger.info(
            "[8phase] Complete: %d steps (%d ok), %d data points, "
            "%.1fs, $%.4f [%s] [%s]",
            self._notebook.step_count,
            self._notebook.successful_steps,
            len(self._notebook.data_points),
            total_elapsed,
            total_cost,
            timing_str,
            cost_str or "no cost data",
        )

        return self._notebook

    # -------------------------------------------------------------------
    # Phase 3: BRIEFING — evidence distillation + clustering
    # -------------------------------------------------------------------

    @staticmethod
    def _distill_fact(statement: str) -> str:
        """Distill an evidence statement to a concise fact (~20 words).

        Strips common boilerplate prefixes and truncates to ~20 words.
        Pure regex, no LLM call.
        """
        if not statement:
            return ""

        text = statement.strip()

        # Strip boilerplate prefixes
        boilerplate_patterns = [
            r'^(?:the\s+)?(?:study|research|analysis|report|paper|'
            r'investigation|review|assessment)\s+'
            r'(?:found|showed|demonstrated|revealed|indicated|reported|'
            r'concluded|suggests?|confirms?|determined)\s+that\s+',
            r'^(?:according\s+to\s+(?:the|a|this)\s+'
            r'(?:study|research|report|analysis|data|findings)),?\s*',
            r'^(?:it\s+(?:was|is|has\s+been)\s+'
            r'(?:found|shown|demonstrated|reported|observed)\s+that\s+)',
            r'^(?:results?\s+(?:show|indicate|suggest|demonstrate)\s+that\s+)',
            r'^(?:data\s+(?:shows?|indicates?|suggests?)\s+that\s+)',
        ]
        for pattern in boilerplate_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        # Truncate to ~20 words
        words = text.split()
        if len(words) > 20:
            text = " ".join(words[:20]) + "..."

        return text.strip()

    # -------------------------------------------------------------------
    # Learnings extraction (LLM-based, replaces regex _distill_fact)
    # -------------------------------------------------------------------

    async def _extract_learnings_batch(
        self,
        evidence_batch: list[dict],
    ) -> list[dict]:
        """Extract learnings from a batch of evidence via free-form LLM.

        Uses generate() (NOT generate_structured) — Qwen is much faster
        without JSON schema enforcement. Parses markdown bullets with regex.
        Falls back to _distill_fact() on failure.
        """
        if not self._client or not evidence_batch:
            return self._fallback_distill_batch(evidence_batch)

        evidence_lines = []
        valid_ids = set()
        for ev_dict in evidence_batch:
            eid = ev_dict["eid"]
            # 60 chars per item keeps prompt compact for large batches
            stmt = ev_dict["statement"][:60]
            valid_ids.add(eid)
            evidence_lines.append(f"[{eid}]: {stmt}")

        evidence_text = "\n".join(evidence_lines)

        # Scale target learnings to batch size
        target_min = max(10, len(evidence_batch) // 5)
        target_max = max(20, len(evidence_batch) // 2)

        prompt = (
            f"RESEARCH: {self._query[:100]}\n\n"
            f"EVIDENCE ({len(evidence_batch)} items):\n"
            f"{evidence_text}\n\n"
            f"Distill into {target_min}-{target_max} paraphrased "
            f"learnings. Format EXACTLY:\n"
            f"- [ev_xxx] (category) Paraphrased fact with numbers\n\n"
            f"REPHRASE (never copy wording), keep numbers exact, "
            f"merge duplicates. Categories: performance, cost, "
            f"comparison, mechanism, limitation, application, general."
        )

        system = (
            "Distill evidence into paraphrased bullet points. "
            "Format: - [ev_xxx] (category) fact. Never copy wording."
        )

        # Learnings must fail fast — scaffold is what produces quality.
        # Cap at 45s so 3 concurrent batches consume ≤45s total,
        # leaving 500+ seconds for scaffold+write+critique.
        # MUST pass to generate() — otherwise DEFAULT_TIMEOUT_SECONDS=90
        # kills the httpx call internally.
        batch_timeout = _LEARNINGS_BATCH_TIMEOUT  # default 45s

        try:
            response = await asyncio.wait_for(
                self._client.generate(
                    prompt=prompt,
                    system=system,
                    max_tokens=min(4096, len(evidence_batch) * 40),
                    temperature=0.3,
                    timeout=batch_timeout,
                ),
                timeout=batch_timeout + 30,
            )

            content = response.content.strip()
            if not content:
                return self._fallback_distill_batch(evidence_batch)

            raw_learnings = self._parse_learning_bullets(
                content, valid_ids,
            )

            if raw_learnings:
                logger.info(
                    "[8phase] LLM learnings: %d input -> %d learnings",
                    len(evidence_batch), len(raw_learnings),
                )
                return raw_learnings

            logger.warning(
                "[8phase] LLM learnings parsed 0 from %d chars, "
                "regex fallback",
                len(content),
            )
            return self._fallback_distill_batch(evidence_batch)

        except asyncio.TimeoutError:
            logger.warning(
                "[8phase] LLM learnings timed out (%ds for %d ev), "
                "regex fallback",
                batch_timeout, len(evidence_batch),
            )
            return self._fallback_distill_batch(evidence_batch)
        except Exception as exc:
            logger.warning(
                "[8phase] LLM learnings failed: %s: %s, regex fallback",
                type(exc).__name__, str(exc)[:300],
            )
            return self._fallback_distill_batch(evidence_batch)

    def _fallback_distill_batch(
        self, evidence_batch: list[dict],
    ) -> list[dict]:
        """Regex-based fallback for a failed LLM learnings batch."""
        results = []
        for ev_dict in evidence_batch:
            fact = self._distill_fact(ev_dict["statement"])
            if fact:
                results.append({
                    "fact": fact,
                    "source_ids": [ev_dict["eid"]],
                    "category": ev_dict["category"],
                })
        return results

    async def _extract_all_learnings(self) -> list[dict]:
        """Extract learnings from ALL evidence in a single LLM call.

        Uses generate() with a compact evidence summary — one call for
        all evidence instead of batched calls. Qwen's per-call overhead
        (~6s routing + thinking) makes batching unviable.

        Returns list of dicts compatible with _build_evidence_briefing.
        """
        evidence_items = []
        for eid in self._evidence_ids:
            ev = self._evidence_store.get(eid, {})
            stmt = ev.get("statement", "")
            if not stmt or len(stmt) < 10:
                continue
            evidence_items.append({
                "eid": eid,
                "statement": stmt,
                "category": ev.get("fact_category", "general"),
                "tier": ev.get("quality_tier", "BRONZE"),
                "relevance": float(ev.get("relevance_score", 0.5)),
                "perspective": ev.get("perspective", ""),
            })

        if not evidence_items:
            return []

        # Gate: LLM learnings disabled, no client, or evidence >100
        # INF-1: Skip LLM for large evidence sets (timeout risk)
        _learnings_llm_threshold = int(
            resolve("PG_LEARNINGS_LLM_THRESHOLD"),
        )
        if (
            not _LLM_LEARNINGS_ENABLED
            or not self._client
            or len(evidence_items) > _learnings_llm_threshold
        ):
            logger.info(
                "[8phase] LLM learnings skipped (%d ev, threshold=%d), "
                "using regex",
                len(evidence_items), _learnings_llm_threshold,
            )
            return self._build_learnings_from_regex(evidence_items)

        # Split into ~3 large batches for concurrent extraction
        # Qwen takes ~3s/item — 3 batches of 85 items concurrently ≈ 90s
        batch_size = max(
            _LEARNINGS_BATCH_SIZE,
            (len(evidence_items) + 2) // 3,  # ~3 batches
        )
        batches = [
            evidence_items[i:i + batch_size]
            for i in range(0, len(evidence_items), batch_size)
        ]

        logger.info(
            "[8phase] LLM learnings: %d evidence -> %d batches of ~%d",
            len(evidence_items), len(batches), batch_size,
        )

        # Run batches concurrently
        sem = asyncio.Semaphore(_LEARNINGS_MAX_CONCURRENCY)

        async def _run_batch(batch):
            async with sem:
                return await self._extract_learnings_batch(batch)

        batch_results = await asyncio.gather(
            *[_run_batch(b) for b in batches],
            return_exceptions=True,
        )

        # Merge results, regex fallback per failed batch
        raw_learnings = []
        for i, result in enumerate(batch_results):
            if isinstance(result, Exception):
                logger.warning(
                    "[8phase] Batch %d failed (%s), regex fallback",
                    i, str(result)[:100],
                )
                raw_learnings.extend(
                    self._fallback_distill_batch(batches[i]),
                )
            elif isinstance(result, list):
                raw_learnings.extend(result)
            else:
                raw_learnings.extend(
                    self._fallback_distill_batch(batches[i]),
                )

        return self._enrich_learnings(raw_learnings, evidence_items)

    def _parse_learning_bullets(
        self,
        content: str,
        valid_ids: set[str],
    ) -> list[dict]:
        """Parse markdown bullet list into learning dicts.

        Expected format: - [ev_xxx] (category) fact text
        Also handles: - [ev_xxx, ev_yyy] (category) fact text
        Tolerant of trailing commas, truncated IDs, missing parens.
        """
        learnings = []

        # Primary pattern: - [ev_xxx] (category) fact
        bullet_pattern = re.compile(
            r'^[-*]\s*\[([^\]]+)\]\s*'      # evidence IDs in brackets
            r'(?:\((\w+)\)\s*)?'             # optional category in parens
            r'(.+)$',                         # fact text
            re.MULTILINE,
        )

        for match in bullet_pattern.finditer(content):
            ids_str = match.group(1)
            category = (match.group(2) or "general").lower()
            fact = match.group(3).strip()

            # Extract all ev_xxx patterns from the IDs string
            # (handles trailing commas, spaces, truncated hashes)
            raw_ids = re.findall(r'ev_[a-f0-9]{6,}', ids_str)
            validated_ids = [sid for sid in raw_ids if sid in valid_ids]

            if not validated_ids or not fact or len(fact) < 10:
                continue

            learnings.append({
                "fact": fact,
                "source_ids": validated_ids,
                "category": category,
            })

        return learnings

    def _build_learnings_from_regex(
        self, evidence_items: list[dict],
    ) -> list[dict]:
        """Build learnings via regex fallback for ALL evidence."""
        results = []
        for ev in evidence_items:
            fact = self._distill_fact(ev["statement"])
            if not fact:
                continue
            results.append({
                "fact": fact,
                "category": ev["category"],
                "tier": ev["tier"],
                "evidence_ids": [ev["eid"]],
                "relevance": ev["relevance"],
                "perspective": ev["perspective"],
                "original_statement": ev["statement"],
            })
        return results

    def _enrich_learnings(
        self,
        raw_learnings: list[dict],
        evidence_items: list[dict],
    ) -> list[dict]:
        """Enrich LLM-extracted learnings with metadata from sources.

        Maps source_ids back to tier/relevance/perspective, producing
        dicts compatible with downstream consumers.
        """
        ev_lookup = {ev["eid"]: ev for ev in evidence_items}
        tier_order = {"GOLD": 0, "SILVER": 1, "BRONZE": 2}

        enriched = []
        for learning in raw_learnings:
            source_ids = learning.get(
                "source_ids", learning.get("evidence_ids", []),
            )
            tier = "BRONZE"
            relevance = 0.5
            perspective = ""
            original_stmt = ""
            for sid in source_ids:
                if sid in ev_lookup:
                    src = ev_lookup[sid]
                    if tier_order.get(src["tier"], 3) < tier_order.get(
                        tier, 3,
                    ):
                        tier = src["tier"]
                    relevance = max(relevance, src["relevance"])
                    if not perspective:
                        perspective = src["perspective"]
                    if not original_stmt:
                        original_stmt = src["statement"]

            enriched.append({
                "fact": learning["fact"],
                "category": learning.get("category", "general"),
                "tier": tier,
                "evidence_ids": source_ids,
                "relevance": relevance,
                "perspective": perspective,
                "original_statement": original_stmt,
            })

        return enriched

    async def _build_evidence_briefing(self) -> dict:
        """Build structured evidence briefing from ALL evidence (Phase 3).

        Uses LLM-based learnings extraction (when enabled) to force
        paraphrasing. Falls back to regex distillation on failure.

        Returns:
            {
                "learnings": [{"fact": str, "category": str, "tier": str,
                              "evidence_ids": [str], "relevance": float}],
                "clusters": [{"theme": str, "learning_indices": [int],
                             "evidence_count": int}],
                "sub_questions": [str],
                "comparison_matrix": str,
            }
        """
        # Step 1: Extract learnings (LLM-based or regex fallback)
        raw_learnings = await self._extract_all_learnings()

        if not raw_learnings:
            return {
                "learnings": [],
                "clusters": [],
                "sub_questions": self._decompose_query(),
                "comparison_matrix": "",
            }

        # Step 2: Domain filter via embedding similarity
        try:
            query_embedding = embed_text(self._query)
            fact_texts = [l["fact"] for l in raw_learnings]
            fact_embeddings = embed_texts(fact_texts)

            query_vec = np.array(query_embedding)
            filtered_learnings = []
            filtered_embeddings = []
            for i, learning in enumerate(raw_learnings):
                fact_vec = np.array(fact_embeddings[i])
                norm_q = np.linalg.norm(query_vec)
                norm_f = np.linalg.norm(fact_vec)
                if norm_q > 0 and norm_f > 0:
                    cos_sim = float(
                        np.dot(query_vec, fact_vec) / (norm_q * norm_f)
                    )
                else:
                    cos_sim = 0.0

                if cos_sim >= _DOMAIN_RELEVANCE_THRESHOLD:
                    learning["relevance"] = max(
                        learning["relevance"], cos_sim,
                    )
                    filtered_learnings.append(learning)
                    filtered_embeddings.append(fact_embeddings[i])

            logger.info(
                "[8phase] Domain filter: %d/%d learnings passed (threshold=%.2f)",
                len(filtered_learnings), len(raw_learnings),
                _DOMAIN_RELEVANCE_THRESHOLD,
            )
        except Exception as exc:
            logger.warning(
                "[8phase] Embedding failed, skipping domain filter: %s",
                str(exc)[:200],
            )
            filtered_learnings = raw_learnings
            filtered_embeddings = []

        if not filtered_learnings:
            # If filter was too aggressive, keep top 50% by relevance
            raw_learnings.sort(key=lambda x: x["relevance"], reverse=True)
            filtered_learnings = raw_learnings[:max(5, len(raw_learnings) // 2)]
            filtered_embeddings = []

        # Step 3: Cluster by embedding similarity
        clusters = self._cluster_learnings(
            filtered_learnings, filtered_embeddings,
        )

        # Step 4: Decompose query into sub-questions
        sub_questions = self._decompose_query()

        # Step 5: Build comparison matrix
        comparison_matrix = self._build_comparison_matrix(
            filtered_learnings, sub_questions,
        )

        return {
            "learnings": filtered_learnings,
            "clusters": clusters,
            "sub_questions": sub_questions,
            "comparison_matrix": comparison_matrix,
        }

    def _cluster_learnings(
        self,
        learnings: list[dict],
        embeddings: list[list[float]],
    ) -> list[dict]:
        """Cluster learnings by embedding similarity.

        Uses scipy agglomerative clustering with cosine distance.
        Falls back to category-based grouping if embeddings unavailable.
        """
        if len(learnings) <= 1:
            if learnings:
                return [{
                    "theme": learnings[0].get("category", "general"),
                    "learning_indices": [0],
                    "evidence_count": 1,
                }]
            return []

        # Try embedding-based clustering
        if embeddings and len(embeddings) == len(learnings):
            try:
                emb_matrix = np.array(embeddings)
                # Compute pairwise cosine distances
                dists = pdist(emb_matrix, metric="cosine")
                # Replace NaN distances (zero-norm vectors) with 1.0
                dists = np.nan_to_num(dists, nan=1.0)
                linkage_matrix = linkage(dists, method="average")
                labels = fcluster(linkage_matrix, t=0.5, criterion="distance")

                cluster_map: dict[int, list[int]] = {}
                for idx, label in enumerate(labels):
                    cluster_map.setdefault(int(label), []).append(idx)

                clusters = []
                for label in sorted(cluster_map.keys()):
                    indices = cluster_map[label]
                    # Label cluster by most common category
                    cats = [
                        learnings[i].get("category", "general")
                        for i in indices
                    ]
                    theme = max(set(cats), key=cats.count)

                    # Sort: GOLD first, then by relevance desc
                    tier_order = {"GOLD": 0, "SILVER": 1, "BRONZE": 2}
                    indices.sort(key=lambda i: (
                        tier_order.get(learnings[i].get("tier", "BRONZE"), 3),
                        -learnings[i].get("relevance", 0),
                    ))

                    # Cap per cluster
                    capped = indices[:_LEARNINGS_PER_CLUSTER]
                    clusters.append({
                        "theme": theme,
                        "learning_indices": capped,
                        "evidence_count": len(capped),
                    })

                # Cap total clusters
                clusters.sort(
                    key=lambda c: c["evidence_count"], reverse=True,
                )
                return clusters[:_MAX_CLUSTERS]
            except Exception as exc:
                logger.warning(
                    "[8phase] Clustering failed: %s, using category groups",
                    str(exc)[:200],
                )

        # Fallback: group by category
        cat_map: dict[str, list[int]] = {}
        for i, learning in enumerate(learnings):
            cat = learning.get("category", "general")
            cat_map.setdefault(cat, []).append(i)

        clusters = []
        for cat, indices in cat_map.items():
            # Sort by tier + relevance
            tier_order = {"GOLD": 0, "SILVER": 1, "BRONZE": 2}
            indices.sort(key=lambda i: (
                tier_order.get(learnings[i].get("tier", "BRONZE"), 3),
                -learnings[i].get("relevance", 0),
            ))
            clusters.append({
                "theme": cat,
                "learning_indices": indices[:_LEARNINGS_PER_CLUSTER],
                "evidence_count": min(len(indices), _LEARNINGS_PER_CLUSTER),
            })

        clusters.sort(key=lambda c: c["evidence_count"], reverse=True)
        return clusters[:_MAX_CLUSTERS]

    def _decompose_query(self) -> list[str]:
        """Decompose query into sub-questions via regex.

        Detects multi-criteria patterns and generates targeted sub-questions.
        """
        query = self._query.lower()
        sub_questions = []

        # Pattern: "effective AND affordable" / "X and Y"
        and_match = re.findall(
            r'(\w+)\s+(?:and|&|as well as|plus)\s+(\w+)',
            query, re.IGNORECASE,
        )
        for w1, w2 in and_match:
            sub_questions.append(f"What is the {w1} of each option?")
            sub_questions.append(f"What is the {w2} of each option?")

        # Pattern: "compare X vs Y" / "X versus Y"
        vs_match = re.findall(
            r'compare\s+(.+?)\s+(?:vs|versus|with|against|to)\s+(.+?)(?:\s|$)',
            query, re.IGNORECASE,
        )
        for entity1, entity2 in vs_match:
            sub_questions.append(
                f"What are the strengths of {entity1.strip()}?"
            )
            sub_questions.append(
                f"What are the strengths of {entity2.strip()}?"
            )

        # Pattern: "most effective" / "best" → ranking question
        if re.search(r'\b(?:most|best|top|leading|optimal)\b', query):
            sub_questions.append(
                "What is the evidence-based ranking of options?"
            )

        # Pattern: cost-related
        if re.search(r'\b(?:cost|afford|cheap|expens|price|budget)\b', query):
            sub_questions.append(
                "What are the cost considerations for each option?"
            )

        # Pattern: effectiveness
        if re.search(
            r'\b(?:effect|efficien|remov|treat|perform|capab)\b', query,
        ):
            sub_questions.append(
                "What is the effectiveness/performance of each option?"
            )

        # Always include a gaps question
        sub_questions.append("What gaps remain in the evidence?")

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for q in sub_questions:
            q_lower = q.lower()
            if q_lower not in seen:
                seen.add(q_lower)
                unique.append(q)

        return unique

    def _classify_query(self, briefing: dict) -> dict:
        """Classify query archetype and determine required artifacts.

        Returns dict with archetype, artifacts list, and evidence_signals.
        Zero LLM calls — pure regex + evidence inspection.
        """
        query = self._query.lower()
        learnings = briefing.get("learnings", [])

        # Detect archetype via regex patterns
        archetype = "general"
        if re.search(
            r'\b(?:compare|vs|versus|difference|between)\b', query,
        ):
            archetype = "comparison"
        elif re.search(
            r'\b(?:how\s+does|mechanism|why\s+does|process|pathway)\b',
            query,
        ):
            archetype = "mechanism"
        elif re.search(
            r'\b(?:best|rank|top|most\s+effective|optimal|recommend)\b',
            query,
        ):
            archetype = "ranking"
        elif re.search(
            r'\b(?:cost|price|afford|budget|economic|roi)\b', query,
        ):
            archetype = "cost_analysis"

        # Evidence signal inspection
        cost_learnings = sum(
            1 for l in learnings
            if re.search(
                r'(?:cost|\$|price|USD|afford|budget)', l.get("fact", ""),
                re.IGNORECASE,
            )
        )
        numeric_learnings = sum(
            1 for l in learnings
            if re.search(r'\d+\.?\d*\s*%', l.get("fact", ""))
        )
        has_entities = bool(re.search(
            r'(?:compare|vs|versus)\s+\w+', query,
        ))
        # Detect implicit multi-option queries (plural nouns =
        # multiple options to compare even without "compare/vs")
        implies_multiple = bool(re.search(
            r'\b(?:technologies|methods|options|approaches|'
            r'techniques|systems|materials|alternatives)\b',
            query,
        ))

        # Determine required artifacts based on archetype + evidence
        artifacts = []
        # Comparison table: explicit comparison OR ranking queries
        # that imply multiple options (e.g., "most effective
        # technologies" = multiple techs to compare)
        if (
            archetype == "comparison"
            or has_entities
            or (archetype == "ranking" and implies_multiple)
        ):
            artifacts.append("comparison_table")
        if archetype in ("ranking", "comparison"):
            artifacts.append("evidence_based_ranking")
        if archetype == "mechanism":
            artifacts.append("mechanism_analysis")
        if cost_learnings >= 2:
            artifacts.append("cost_model")
        # Conditional recommendations: ranking, comparison, and
        # cost_analysis archetypes all benefit from If/Then guidance
        if (
            archetype in ("ranking", "comparison", "cost_analysis")
            or cost_learnings >= 1
        ):
            artifacts.append("conditional_recommendations")
        # decision_matrix removed: LLM fabricates numeric scores
        # instead of filling the template. Evidence-based ranking
        # table serves the same purpose without hallucination risk.

        return {
            "archetype": archetype,
            "artifacts": artifacts,
            "evidence_signals": {
                "cost_learnings": cost_learnings,
                "numeric_learnings": numeric_learnings,
                "has_entities": has_entities,
            },
        }

    def _build_comparison_matrix(
        self,
        learnings: list[dict],
        sub_questions: list[str],
    ) -> str:
        """Build a markdown comparison matrix for multi-criteria queries.

        Groups learnings by subject entity × criterion.
        Returns empty string if query is single-criterion.
        """
        if len(sub_questions) < 3:
            return ""

        # Extract entity mentions from learnings
        entities: dict[str, list[dict]] = {}
        for learning in learnings:
            fact = learning["fact"].lower()
            # Try to extract the subject (first capitalized noun phrase)
            subject_match = re.search(
                r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
                learning["fact"],
            )
            if subject_match:
                entity = subject_match.group(1)
            else:
                # Use category as fallback
                entity = learning.get("category", "general")
            entities.setdefault(entity, []).append(learning)

        if len(entities) < 2:
            return ""

        # Build markdown table
        # Columns: entity | key findings
        lines = ["| Entity | Key Finding | Evidence |"]
        lines.append("|--------|-------------|----------|")

        for entity, entity_learnings in sorted(
            entities.items(), key=lambda x: -len(x[1]),
        )[:10]:
            # Pick highest-relevance learning
            best = max(entity_learnings, key=lambda l: l["relevance"])
            ev_ids = ", ".join(best["evidence_ids"][:2])
            lines.append(
                f"| {entity} | {best['fact'][:80]} | {ev_ids} |"
            )

        return "\n".join(lines)

    # -------------------------------------------------------------------
    # Phase 4: SCAFFOLD — analytical framework generation
    # -------------------------------------------------------------------

    def _build_scaffold_prompt(
        self, briefing: dict, classification: dict | None,
    ) -> str:
        """Build 3-section scaffold prompt: intent + 5-lens + gap queries.

        Merges intent brief, analytical framework, and gap search into a
        single reason() call. Classification controls which artifacts
        (tables, conditional recs, decision matrix) are requested.
        """
        learnings = briefing.get("learnings", [])
        clusters = briefing.get("clusters", [])

        # Wave 2 RCS: Convert raw learnings to analytical claims
        # PaperQA2 pattern: scaffold LLM sees questions, not raw facts
        analytical_claims = self._build_analytical_claims(
            briefing, top_n=_EVIDENCE_PER_CLUSTER,
        )

        archetype = (classification or {}).get("archetype", "general")
        artifacts = (classification or {}).get("artifacts", [])
        artifact_list = ", ".join(artifacts) if artifacts else "analytical prose"

        # Build artifact-specific sections
        artifact_sections = []
        if "comparison_table" in artifacts:
            artifact_sections.append(
                "LENS 3 — COMPARATOR: Head-to-head analysis.\n"
                "Build this comparison table (fill ALL rows from evidence):\n"
                "| Entity | [Criterion_1] | [Criterion_2] | [Criterion_3] "
                "| Key Limitation |\n"
                "|--------|---------------|---------------|---------------|"
                "----------------|"
            )
        else:
            artifact_sections.append(
                "LENS 3 — COMPARATOR: Head-to-head analysis "
                "where evidence supports direct comparison."
            )

        conditional_section = ""
        if "conditional_recommendations" in artifacts:
            if _GTA_ENABLED:
                conditional_section = (
                    "\nCONDITIONAL RECOMMENDATIONS:\n"
                    "- **If** a specific application scenario "
                    "applies: recommend the best option "
                    "**because** evidence shows the rationale\n"
                    "- **If** a different condition or constraint "
                    "applies: recommend the alternative "
                    "**because** evidence shows the benefit"
                )
            else:
                conditional_section = (
                    "\nCONDITIONAL RECOMMENDATIONS:\n"
                    "- **If** a specific application scenario "
                    "applies: recommend the best option "
                    "**because** evidence "
                    "shows the rationale [CITE:ev_xxx]\n"
                    "- **If** a different condition or constraint "
                    "applies: recommend the alternative "
                    "**because** "
                    "evidence demonstrates the benefit "
                    "[CITE:ev_xxx]"
                )

        # TQ-4: Cost calculation template when cost evidence exists
        cost_section = ""
        if "cost_model" in artifacts:
            if _GTA_ENABLED:
                cost_section = (
                    "\nCOST CALCULATIONS:\n"
                    "- [Entity]: $[cost] per [unit] × [usage] "
                    "= $[total]/[period]\n"
                    "Include at least one worked cost example "
                    "from evidence data."
                )
            else:
                cost_section = (
                    "\nCOST CALCULATIONS:\n"
                    "- [Entity]: $[cost] per [unit] × [usage] "
                    "= $[total]/[period] [CITE:ev_xxx]\n"
                    "Include at least one worked cost example "
                    "from evidence data."
                )

        # decision_matrix template removed — LLM fabricates scores
        # instead of filling the template. Evidence-based ranking
        # table with citations serves the same purpose safely.
        matrix_section = ""

        prompt = (
            f"RESEARCH QUESTION: {self._query}\n"
            f"QUERY TYPE: {archetype} — requires {artifact_list}\n\n"
            f"{'EVIDENCE PASSAGES' if _HYBRID_EVIDENCE else 'ANALYTICAL CLAIMS'}"
            f" ({len(learnings)} learnings across "
            f"{len(clusters)} themes — "
            f"{'Reference passages by number [N] when making claims'if _HYBRID_EVIDENCE else 'ANSWER each question, do NOT restate it'}"
            f"):\n"
            f"{analytical_claims}\n\n"
            f"INSTRUCTIONS:\n\n"
            f"STEP 1 — INTENT BRIEF (write inside <intent> tags):\n"
            f"State in 3-4 sentences: what you will analyze, what "
            f"sub-questions you will answer, and what artifacts you "
            f"will produce. Do NOT list limitations — focus on what "
            f"you WILL deliver.\n\n"
            f"STEP 2 — ANALYTICAL SCAFFOLD using 5 lenses:\n\n"
            f"LENS 1 — EVIDENCE GATHERER: Key quantified findings"
            f"{'' if _GTA_ENABLED else ' with citations [CITE:ev_xxx]'}.\n"
            f"LENS 2 — MECHANISM EXPLORER: How and why "
            f"(causal chains).\n"
            f"{artifact_sections[0]}\n"
            f"LENS 4 — CRITIC: Contradictions, limitations, "
            f"caveats.\n"
            f"LENS 5 — HORIZON SCANNER: Emerging trends, gaps, "
            f"future directions.\n"
            f"{conditional_section}\n"
            f"{cost_section}\n"
            f"{matrix_section}\n\n"
            f"STEP 3 — GAP SEARCH QUERIES (output as JSON at the "
            f"very end):\n"
            f"```json\n"
            f'{{"gap_search_queries": ["query_1", "query_2"]}}\n'
            f"```\n"
            f"List 2-5 short, POSITIVE search queries for evidence "
            f"that is MISSING from the briefing. Use affirmative "
            f'phrasing ("maintenance cost data", "short-chain PFAS '
            f'removal rates") NOT negative ("no data on costs").\n\n'
            f"Do NOT rank subtypes of the same technology family as "
            f"separate entries. Be specific with numbers and "
            f"citations. Think carefully about cross-source reasoning.\n\n"
            f"PQ-1: Synthesize findings using comparative language. "
            f"Never restate an evidence claim as a standalone sentence "
            f"— always compare, contextualize, or evaluate it.\n"
            f"PQ-2: Cite 2+ sources in the SAME sentence for at least "
            f"3 sentences (cross-source synthesis).\n"
            f"PQ-3: For each lens, cross-reference with at least one "
            f"other lens. LENS 1 findings should connect to LENS 4 "
            f"limitations."
        )

        return prompt

    async def _generate_analytical_scaffold(
        self, briefing: dict, classification: dict | None = None,
    ) -> dict | str:
        """Generate analytical scaffold using reasoning model (Phase 4).

        When _ADAPTIVE_SCAFFOLD is enabled and classification is provided,
        uses the 5-lens prompt with intent brief and gap queries.
        Otherwise falls back to the legacy sub-question scaffold.

        Returns:
            dict with keys scaffold, intent_brief, gap_queries when
            adaptive mode is active; plain str otherwise.
        """
        # Use adaptive 5-lens prompt when classification available
        if _ADAPTIVE_SCAFFOLD and classification:
            prompt = self._build_scaffold_prompt(briefing, classification)
        else:
            # Legacy prompt (unchanged behavior)
            learnings = briefing.get("learnings", [])
            cluster_text = []
            for cluster in briefing.get("clusters", []):
                theme = cluster["theme"]
                indices = cluster["learning_indices"]
                facts = []
                for idx in indices:
                    if idx < len(learnings):
                        l = learnings[idx]
                        tier_tag = (
                            f"[{l['tier']}]" if l.get("tier") else ""
                        )
                        ev_ids = ", ".join(
                            l.get("evidence_ids", [])[:2],
                        )
                        if _GTA_ENABLED:
                            facts.append(
                                f"  - {tier_tag} {l['fact']} "
                                f"(refs: {ev_ids})"
                            )
                        else:
                            facts.append(
                                f"  - {tier_tag} {l['fact']} "
                                f"[{ev_ids}]"
                            )
                cluster_text.append(
                    f"**{theme}** ({len(indices)} learnings):\n"
                    + "\n".join(facts)
                )
            clustered_learnings = "\n\n".join(cluster_text)
            sub_questions = briefing.get("sub_questions", [])
            sq_text = "\n".join(
                f"  {i+1}. {q}" for i, q in enumerate(sub_questions)
            )
            matrix = briefing.get("comparison_matrix", "")
            matrix_section = (
                f"\nCOMPARISON MATRIX:\n{matrix}\n" if matrix else ""
            )
            prompt = (
                f"RESEARCH QUESTION: {self._query}\n\n"
                f"SUB-QUESTIONS:\n{sq_text}\n\n"
                f"EVIDENCE BRIEFING ({len(learnings)} learnings across "
                f"{len(briefing.get('clusters', []))} themes):\n"
                f"{clustered_learnings}\n"
                f"{matrix_section}\n"
                f"PRODUCE AN ANALYTICAL SCAFFOLD:\n"
                f"1. For each sub-question: what does the evidence say?"
                f"{'' if _GTA_ENABLED else ' (cite [CITE:ev_xxx])'}\n"
                f"2. Where do sources AGREE? Where do they CONTRADICT?\n"
                f"3. What TRADE-OFFS exist between the criteria?\n"
                f"4. What is the EVIDENCE-BASED ranking? "
                f"(with specific numbers)\n"
                f"5. What GAPS remain in the evidence?\n"
                f"6. Do NOT rank subtypes of the same technology family "
                f"as separate entries (e.g., nanofiltration IS a "
                f"high-pressure membrane — rank the family, note "
                f"subtypes within it)\n\n"
                f"This scaffold will be expanded into a full analysis. "
                f"Be specific with numbers and citations. "
                f"Think carefully about cross-source reasoning."
            )

        if _GTA_ENABLED:
            system = (
                "You are an analytical strategist. Think through the "
                "evidence and produce a research framework."
            )
        else:
            system = (
                "You are an analytical strategist. Think through the "
                "evidence and produce a research framework. "
                "Use [CITE:ev_xxx] citations."
            )

        try:
            response = await asyncio.wait_for(
                self._client.reason(
                    prompt=prompt,
                    system=system,
                    effort="high",
                    max_tokens=4096,
                    timeout=_SCAFFOLD_TIMEOUT,
                ),
                timeout=_SCAFFOLD_TIMEOUT + 15,
            )

            content = response.content.strip()
            if not content or len(content) <= 50:
                logger.warning(
                    "[8phase] Scaffold too short (%d chars), using fallback",
                    len(content),
                )
                fallback = self._build_fallback_scaffold(briefing)
                if _ADAPTIVE_SCAFFOLD and classification:
                    return {
                        "scaffold": fallback,
                        "intent_brief": "",
                        "gap_queries": [],
                    }
                return fallback

            # Parse adaptive scaffold components
            if _ADAPTIVE_SCAFFOLD and classification:
                intent_brief = ""
                intent_match = re.search(
                    r'<intent>(.*?)</intent>', content, re.DOTALL,
                )
                if intent_match:
                    intent_brief = intent_match.group(1).strip()

                gap_queries = []
                # Patch 2: safe JSON extraction from LLM response
                json_match = re.search(
                    r'```json\s*(\{.*?\})\s*```', content, re.DOTALL,
                )
                if json_match:
                    try:
                        parsed = json.loads(json_match.group(1))
                        gap_queries = parsed.get(
                            "gap_search_queries", [],
                        )
                    except json.JSONDecodeError:
                        logger.debug(
                            "[8phase] Could not parse gap queries JSON",
                        )

                # Strip intent tags and JSON block from scaffold
                scaffold = content
                if intent_match:
                    scaffold = scaffold.replace(
                        intent_match.group(0), "",
                    ).strip()
                if json_match:
                    scaffold = scaffold[:json_match.start()].strip()

                return {
                    "scaffold": scaffold,
                    "intent_brief": intent_brief,
                    "gap_queries": gap_queries,
                }

            return content

        except Exception as exc:
            logger.warning(
                "[8phase] Scaffold generation failed: %s: %s, "
                "using fallback",
                type(exc).__name__, str(exc)[:200],
            )

        # Fallback: programmatic scaffold from briefing
        fallback = self._build_fallback_scaffold(briefing)
        if _ADAPTIVE_SCAFFOLD and classification:
            return {
                "scaffold": fallback,
                "intent_brief": "",
                "gap_queries": [],
            }
        return fallback

    def _build_fallback_scaffold(self, briefing: dict) -> str:
        """Build a programmatic scaffold from briefing data.

        Used when reason() times out or fails.
        """
        lines = [f"## Analytical Framework: {self._query}\n"]

        # Sub-question answers from top learnings
        for sq in briefing.get("sub_questions", []):
            lines.append(f"### {sq}")
            # Find relevant learnings
            relevant = []
            sq_words = set(sq.lower().split())
            for l in briefing.get("learnings", [])[:30]:
                fact_words = set(l["fact"].lower().split())
                if len(sq_words & fact_words) >= 2:
                    relevant.append(l)
            for r in relevant[:3]:
                if _GTA_ENABLED:
                    ref_ids = ", ".join(
                        r.get("evidence_ids", [])[:1],
                    )
                    lines.append(
                        f"- {r['fact']} (refs: {ref_ids})",
                    )
                else:
                    ev_ids = ", ".join(
                        f"[CITE:{eid}]"
                        for eid in r.get("evidence_ids", [])[:1]
                    )
                    lines.append(f"- {r['fact']} {ev_ids}")
            lines.append("")

        # Top findings from each cluster
        lines.append("### Key Evidence Clusters")
        for cluster in briefing.get("clusters", [])[:5]:
            theme = cluster["theme"]
            indices = cluster["learning_indices"][:3]
            learnings = briefing.get("learnings", [])
            facts = []
            for idx in indices:
                if idx < len(learnings):
                    l = learnings[idx]
                    if _GTA_ENABLED:
                        ref = ", ".join(
                            l.get("evidence_ids", [])[:1],
                        )
                        facts.append(
                            f"  - {l['fact']} (refs: {ref})",
                        )
                    else:
                        ev = ", ".join(
                            f"[CITE:{eid}]"
                            for eid in l.get(
                                "evidence_ids", [],
                            )[:1]
                        )
                        facts.append(f"  - {l['fact']} {ev}")
            lines.append(f"**{theme}**:")
            lines.extend(facts)
            lines.append("")

        lines.append("### Gaps")
        lines.append("- Evidence gaps require further investigation")

        return "\n".join(lines)

    def _fill_evidence_gaps(
        self,
        gap_queries: list[str],
        briefing: dict,
    ) -> list[dict]:
        """Fill evidence gaps using embedding search (0 LLM calls).

        For each gap query, embeds it and searches the full evidence store
        by cosine similarity. Uses relative top-K (top 3 per query),
        filters evidence already in briefing learnings.
        """
        if not gap_queries:
            return []

        # Collect evidence IDs already in briefing
        briefing_eids = set()
        for l in briefing.get("learnings", []):
            briefing_eids.update(l.get("evidence_ids", []))

        # Build evidence vectors if not cached
        all_eids = list(self._evidence_store.keys())
        if not all_eids:
            return []

        all_statements = [
            self._evidence_store[eid].get("statement", "")
            for eid in all_eids
        ]
        try:
            ev_embeddings = embed_texts(all_statements)
            ev_matrix = np.array(ev_embeddings)
        except Exception as exc:
            logger.warning(
                "[gap-fill] Could not embed evidence: %s", str(exc)[:100],
            )
            return []

        gap_evidence = []
        max_gaps = min(len(gap_queries), 3)
        max_per_gap = 5

        for query_text in gap_queries[:max_gaps]:
            try:
                q_vec = np.array(embed_text(query_text))
            except Exception:
                continue

            # Cosine similarity against all evidence
            norms = np.linalg.norm(ev_matrix, axis=1)
            q_norm = np.linalg.norm(q_vec)
            if q_norm == 0:
                continue
            similarities = ev_matrix @ q_vec / (norms * q_norm + 1e-10)

            # Relative top-K: take top 3 per gap query
            top_indices = np.argsort(similarities)[::-1]
            count = 0
            for idx in top_indices:
                if count >= max_per_gap:
                    break
                eid = all_eids[idx]
                if eid in briefing_eids:
                    continue
                gap_evidence.append({
                    "evidence_id": eid,
                    "statement": self._evidence_store[eid].get(
                        "statement", "",
                    ),
                    "gap_query": query_text,
                    "similarity": float(similarities[idx]),
                })
                briefing_eids.add(eid)  # prevent duplicates across gaps
                count += 1

        logger.info(
            "[gap-fill] Found %d supplementary evidence from %d gap queries",
            len(gap_evidence), max_gaps,
        )
        return gap_evidence

    # -------------------------------------------------------------------
    # FIX-D8 + FIX-D9: Write prompt enrichment
    # -------------------------------------------------------------------

    def _build_enriched_cluster_summary(
        self, briefing: dict, top_n: int | None = None,
    ) -> str:
        """Build enriched cluster summary with analytical claims.

        Wave 2 RCS: Instead of raw facts, present analytical claims
        (questions) that force the LLM to construct original answers.
        Uses MMR-based selection for diverse evidence coverage.

        FIX-D8 origin: PaperQA2 RCS pattern.
        """
        if top_n is None:
            top_n = _EVIDENCE_PER_CLUSTER
        # Hybrid: numbered evidence passages (STORM pattern)
        if _HYBRID_EVIDENCE:
            passages, rmap = self._build_numbered_evidence_passages(
                briefing, top_n=top_n,
            )
            if passages:
                self._passage_reverse_map = rmap
                return passages
        # Delegate to analytical claims builder for consistency
        claims = self._build_analytical_claims(briefing, top_n=top_n)
        if claims:
            return claims
        # Fallback: original enriched summary if claims builder fails
        clusters = briefing.get("clusters", [])[:_MAX_CLUSTERS]
        learnings = briefing.get("learnings", [])
        if not clusters:
            return ""
        parts = []
        for c in clusters:
            theme = c.get("theme", "Unknown")
            ev_count = c.get("evidence_count", 0)
            indices = c.get("learning_indices", [])[:top_n]
            snippets = []
            for idx in indices:
                if idx < len(learnings):
                    learn = learnings[idx]
                    eids = learn.get("evidence_ids", [])[:2]
                    cite = f"[CITE:{eids[0]}]" if eids else ""
                    fact = learn.get("fact", "")[:120]
                    snippets.append(f"  - {fact} {cite}")
            snippet_text = "\n".join(snippets)
            if snippet_text:
                parts.append(
                    f"{theme} ({ev_count}):\n{snippet_text}",
                )
            else:
                parts.append(f"{theme} ({ev_count})")
        return "\n".join(parts)

    # -------------------------------------------------------------------
    # Wave 2: RCS — Analytical Claims (PaperQA2 / Step-DeepResearch)
    # -------------------------------------------------------------------

    def _build_analytical_claims(
        self, briefing: dict, top_n: int = 5,
    ) -> str:
        """Convert evidence briefing into analytical claim questions.

        PaperQA2 RCS pattern: never show raw facts to LLM — show questions
        that force the LLM to construct original analytical answers.
        Each claim includes grounding numbers and citation IDs so the
        scaffold/write LLM can reference specific data without copying.

        Args:
            briefing: Evidence briefing dict with learnings and clusters.
            top_n: Max learnings per cluster to convert.

        Returns:
            Formatted analytical claims string for prompt injection.
        """
        clusters = briefing.get("clusters", [])[:_MAX_CLUSTERS]
        learnings = briefing.get("learnings", [])
        if not clusters or not learnings:
            return ""

        claims_parts = []
        for c in clusters:
            theme = c.get("theme", "Unknown")
            indices = c.get("learning_indices", [])

            # MMR-based selection for diversity within cluster
            selected_indices = self._mmr_select_learnings(
                learnings, indices, top_n,
            )

            cluster_claims = []
            for idx in selected_indices:
                if idx >= len(learnings):
                    continue
                learn = learnings[idx]
                fact = learn.get("fact", "")
                eids = learn.get("evidence_ids", [])[:2]
                eid_str = ", ".join(eids) if eids else "unattributed"

                # Extract key metric via regex
                metric_match = re.search(
                    r'(\d+\.?\d*)\s*'
                    r'(%|mg/[Ll]|ppt|ppb|ppm|µg/[Ll]|ng/[Ll]|\$|'
                    r'kWh|MWh|µm|nm|mm|cm|MPa|GPa|°C|[Ll]/min)',
                    fact,
                )

                # Extract subject entity (first capitalized noun phrase)
                entity = self._extract_entity(fact)

                if metric_match:
                    number = metric_match.group(1)
                    unit = metric_match.group(2)
                    category = self._classify_metric(unit)
                    if _GTA_ENABLED:
                        # GTA: non-copyable metadata — no [CITE:] tokens
                        ref_str = ", ".join(eids)
                        cluster_claims.append(
                            f"  - What {category} does {entity} "
                            f"achieve? (value: {number}{unit}) "
                            f"(refs: {ref_str})"
                        )
                    else:
                        cite_refs = " ".join(
                            f"[CITE:{e}]" for e in eids
                        )
                        cluster_claims.append(
                            f"  - What {category} does {entity} "
                            f"achieve? "
                            f"(value: {number}{unit}) {cite_refs}"
                        )
                else:
                    # Qualitative fact — generate topical question
                    topic = theme.lower().rstrip(".")
                    if _GTA_ENABLED:
                        # GTA: neutral question + non-copyable refs
                        ref_str = ", ".join(eids)
                        cluster_claims.append(
                            f"  - What role does {entity} play "
                            f"in {topic}? (refs: {ref_str})"
                        )
                    else:
                        cite_refs = " ".join(
                            f"[CITE:{e}]" for e in eids
                        )
                        cluster_claims.append(
                            f"  - What evidence supports "
                            f"{entity}'s "
                            f"role in {topic}? {cite_refs}"
                        )

            if cluster_claims:
                claims_parts.append(
                    f"**{theme}**:\n" + "\n".join(cluster_claims)
                )

        result = "\n\n".join(claims_parts)
        # D2-FIX: Store analytical claims text for Jaccard echo detection
        self._analytical_claims_text = result
        return result

    # -------------------------------------------------------------------
    # Hybrid Evidence: numbered source passages (STORM/Attribute-First)
    # -------------------------------------------------------------------

    def _build_numbered_evidence_passages(
        self, briefing: dict, top_n: int = 5,
    ) -> tuple[str, dict[int, str]]:
        """Group evidence by cluster theme as numbered passages.

        STORM/OpenScholar/Attribute-First pattern: LLM sees raw
        evidence text with numbered markers [1], [2], ... instead
        of templated questions. Eliminates verb template leakage.

        Returns:
            (formatted_text, reverse_map) where reverse_map maps
            passage number (int) to evidence ID (str).
        """
        clusters = briefing.get("clusters", [])[:_MAX_CLUSTERS]
        learnings = briefing.get("learnings", [])
        if not clusters or not learnings:
            return "", {}

        passage_num = 0
        reverse_map: dict[int, str] = {}
        parts: list[str] = []

        for c in clusters:
            theme = c.get("theme", "Unknown")
            indices = c.get("learning_indices", [])

            selected = self._mmr_select_learnings(
                learnings, indices, top_n,
            )

            cluster_passages: list[str] = []
            for idx in selected:
                if idx >= len(learnings):
                    continue
                learn = learnings[idx]
                eids = learn.get("evidence_ids", [])[:2]
                if not eids:
                    continue

                eid = eids[0]
                ev = self._evidence_store.get(eid, {})
                # Prefer raw source text over paraphrased fact
                text = (
                    learn.get("original_statement", "")
                    or ev.get("statement", "")
                    or learn.get("fact", "")
                )
                if not text:
                    continue

                text = text[:200].rstrip()
                source_title = ev.get("source_title", "")
                tier = learn.get("tier", "")

                passage_num += 1
                reverse_map[passage_num] = eid

                source_tag = f" — {source_title}" if source_title else ""
                tier_tag = f" [{tier}]" if tier else ""
                cluster_passages.append(
                    f"  [{passage_num}]{tier_tag} {text}{source_tag}"
                )

            if cluster_passages:
                parts.append(
                    f"**{theme}**:\n" + "\n".join(cluster_passages)
                )

        result = "\n\n".join(parts)
        self._evidence_passages_text = result
        self._passage_reverse_map = reverse_map
        return result, reverse_map

    @staticmethod
    def _map_passage_citations(
        text: str, reverse_map: dict[int, str],
    ) -> str:
        """Map numbered passage references [N] to [CITE:ev_xxx].

        Handles: [N], [N, M], [N; M], adjacent [N][M].
        Skips: footnotes [^N], markdown links [text](url),
        table separators, unknown passage numbers.
        """
        if not reverse_map:
            return text

        def _replace_compound(m: re.Match) -> str:
            inner = m.group(1)
            nums = re.findall(r'\d+', inner)
            cites = []
            for n in nums:
                eid = reverse_map.get(int(n))
                if eid:
                    cites.append(f"[CITE:{eid}]")
            return "".join(cites) if cites else m.group(0)

        # Compound: [1, 2, 3] or [1; 2; 3]
        text = re.sub(
            r'(?<!\^)\[(\d+(?:\s*[,;]\s*\d+)+)\](?!\()',
            _replace_compound,
            text,
        )

        # Single: [N] — skip if preceded by ^ or followed by (
        def _replace_single(m: re.Match) -> str:
            n = int(m.group(1))
            eid = reverse_map.get(n)
            return f"[CITE:{eid}]" if eid else m.group(0)

        text = re.sub(
            r'(?<!\^)\[(\d+)\](?!\()',
            _replace_single,
            text,
        )

        # Deduplicate adjacent identical citations
        text = re.sub(
            r'(\[CITE:ev_[a-f0-9]+\])(?:\1)+',
            r'\1',
            text,
        )

        return text

    def _get_passage_number(self, eid: str) -> int | None:
        """Find passage number for an evidence ID."""
        for num, mapped_eid in self._passage_reverse_map.items():
            if mapped_eid == eid:
                return num
        return None

    @staticmethod
    def _extract_entity(fact: str) -> str:
        """Extract the subject entity from a fact string.

        Finds the first capitalized noun phrase (1-3 words), filtering
        out common sentence-initial words that aren't entities.
        Handles abbreviations (GAC, PFAS), PascalCase names, and
        hyphenated compounds (Cross-linked, Non-woven).
        """
        # P4 Fix 1: Hyphenated compound check BEFORE abbreviation match.
        # Prevents "Cross-linked" → "Cross" (abbreviation split).
        hyphen_candidates = re.findall(
            r'\b([A-Z][a-z]+-[A-Z]?[a-z]+(?:-[a-z]+)*)\b', fact,
        )
        for cand in hyphen_candidates:
            if cand.split("-")[0] in _ENTITY_PREFIXES:
                return cand

        # Match abbreviations (2+ uppercase letters) at start or mid-sentence
        abbrev_candidates = re.findall(
            r'\b([A-Z]{2,}(?:[- /][A-Z]{2,}){0,2})\b',
            fact,
        )
        for cand in abbrev_candidates:
            if cand not in _NON_ENTITIES and cand not in {"CITE"}:
                return cand

        # Match 1-3 capitalized words at the start or after punctuation
        candidates = re.findall(
            r'(?:^|(?<=[.!?]\s))([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})',
            fact,
        )
        # Also try mid-sentence capitalized phrases
        mid_candidates = re.findall(
            r'(?<=\s)([A-Z][A-Za-z]+(?:[- ][A-Z][A-Za-z]+){0,2})',
            fact,
        )
        all_candidates = candidates + mid_candidates
        for cand in all_candidates:
            first_word = cand.split()[0]
            if first_word not in _NON_ENTITIES:
                return cand
        # Fallback: first capitalized word or first meaningful word
        for w in fact.split()[:5]:
            clean = w.strip(".,;:!?()[]\"'")
            if len(clean) > 1 and clean[0].isupper():
                if clean not in _NON_ENTITIES:
                    return clean
        return "the subject"

    @staticmethod
    def _classify_metric(unit: str) -> str:
        """Classify a unit string into a metric category."""
        for pattern, category in _METRIC_CATEGORIES:
            if pattern.search(unit):
                return category
        return "performance characteristic"

    @staticmethod
    def _ngrams(text: str, n: int) -> set[tuple[str, ...]]:
        """Return set of word n-grams from *text* (for Jaccard).

        Strips punctuation from each word so 'levels.' == 'levels?'.
        """
        words = [
            w.strip('.,;:!?()[]"\'-') for w in text.split()
        ]
        words = [w for w in words if w]
        if len(words) < n:
            return set()
        return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}

    def _build_mandatory_numbers_section(self) -> str:
        """D3-FIX: Build a MANDATORY NUMERICAL DATA section from data_points.

        FACTS Grounding pattern — make numbers a STRUCTURAL requirement
        (schema/injection), not a soft prompt directive the LLM ignores
        for niche domains.

        Returns formatted section or empty string if no data points.
        """
        if resolve("PG_MANDATORY_NUMBERS_ENABLED") != "1":
            return ""
        data_points = self._notebook.data_points
        if not data_points:
            return ""
        # Deduplicate by (label, value, unit)
        seen: set[tuple[str, str, str]] = set()
        lines: list[str] = []
        for dp in data_points:
            label = dp.get("label", "unknown")
            value = str(dp.get("value", ""))
            unit = dp.get("unit", "")
            eid = dp.get("evidence_id", "")
            key = (label.lower(), value, unit.lower())
            if key in seen or not value:
                continue
            seen.add(key)
            if _GTA_ENABLED:
                ref = f" (refs: {eid})" if eid else ""
            else:
                ref = f" [CITE:{eid}]" if eid else ""
            lines.append(f"  - {label}: {value} {unit}{ref}")
            if len(lines) >= 20:
                break
        if not lines:
            return ""
        return (
            "\nMANDATORY NUMERICAL DATA — you MUST weave ALL of these "
            "into your analysis:\n"
            + "\n".join(lines) + "\n"
        )

    def _build_perspective_coverage_section(
        self, briefing: dict,
    ) -> str:
        """D4-FIX: Build COVERAGE REQUIREMENT section from perspectives.

        ACL 2025 aspect-based decomposition — enumerate all perspectives
        with evidence, require each to appear in the output.

        Returns formatted section or empty string if disabled/single perspective.
        """
        if resolve("PG_PERSPECTIVE_COVERAGE_ENABLED") != "1":
            return ""
        learnings = briefing.get("learnings", [])
        if not learnings:
            return ""
        # Group evidence IDs by perspective
        by_perspective: dict[str, list[str]] = {}
        for learn in learnings:
            persp = learn.get("perspective", "") or "General"
            eids = learn.get("evidence_ids", [])
            if persp:
                by_perspective.setdefault(persp, []).extend(eids)
        if len(by_perspective) <= 1:
            return ""
        lines: list[str] = []
        for persp, eids in sorted(
            by_perspective.items(),
            key=lambda x: len(x[1]), reverse=True,
        ):
            unique_eids = list(dict.fromkeys(eids))[:2]
            cite_refs = " ".join(f"[CITE:{e}]" for e in unique_eids)
            lines.append(
                f"  - {persp} ({len(eids)} evidence, "
                f"e.g. {cite_refs})"
            )
        return (
            "\nCOVERAGE REQUIREMENT — your analysis MUST cite evidence "
            "from ALL perspectives:\n"
            + "\n".join(lines) + "\n"
        )

    def _mmr_select_learnings(
        self,
        learnings: list[dict],
        indices: list[int],
        top_n: int,
    ) -> list[int]:
        """Select diverse learnings via Maximal Marginal Relevance.

        lambda=0.7: 70% relevance to query, 30% diversity penalty.
        Falls back to naive top-N if embedding fails.
        """
        valid_indices = [i for i in indices if i < len(learnings)]
        if len(valid_indices) <= top_n:
            return valid_indices

        # Get fact texts for embedding
        facts = [learnings[i].get("fact", "") for i in valid_indices]
        try:
            embeddings = embed_texts(facts)
            if embeddings is None or len(embeddings) != len(facts):
                logger.warning(
                    "[mmr] Embedding returned None/mismatch, "
                    "falling back to naive top-N",
                )
                return valid_indices[:top_n]
        except Exception as exc:
            logger.warning(
                "[mmr] embed_texts failed: %s — naive top-N fallback",
                type(exc).__name__,
            )
            return valid_indices[:top_n]

        # Embed query for relevance scoring
        try:
            query_emb = embed_text(self._query)
            if query_emb is None:
                logger.warning(
                    "[mmr] Query embedding None, naive top-N fallback",
                )
                return valid_indices[:top_n]
        except Exception as exc:
            logger.warning(
                "[mmr] embed_text failed: %s — naive top-N fallback",
                type(exc).__name__,
            )
            return valid_indices[:top_n]

        embeddings = np.array(embeddings)
        query_emb = np.array(query_emb)

        # Compute relevance scores (cosine similarity to query)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        normed = embeddings / norms
        q_norm = np.linalg.norm(query_emb)
        if q_norm > 0:
            query_normed = query_emb / q_norm
        else:
            return valid_indices[:top_n]
        relevance = normed @ query_normed

        # MMR selection
        mmr_lambda = 0.7
        selected: list[int] = []  # indices into valid_indices
        remaining = set(range(len(valid_indices)))

        for _ in range(top_n):
            best_score = -float("inf")
            best_idx = -1
            for idx in remaining:
                rel = relevance[idx]
                if selected:
                    # Max similarity to already selected
                    sel_embs = normed[selected]
                    sim_to_sel = float(np.max(sel_embs @ normed[idx]))
                else:
                    sim_to_sel = 0.0
                score = mmr_lambda * rel - (1 - mmr_lambda) * sim_to_sel
                if score > best_score:
                    best_score = score
                    best_idx = idx
            if best_idx < 0:
                break
            selected.append(best_idx)
            remaining.discard(best_idx)

        return [valid_indices[i] for i in selected]

    def _build_cross_source_facts(
        self, briefing: dict, jaccard_threshold: float = 0.25,
    ) -> str:
        """Find cross-source fact pairs for explicit cross-referencing.

        FIX-D9: Scans learnings across clusters for same-topic facts
        from different sources using word-set Jaccard. Produces
        explicit pairs the LLM can cite in the same sentence.
        TACL 2025: cross-source synthesis requires explicit pairs.
        """
        learnings = briefing.get("learnings", [])
        if len(learnings) < 2:
            return ""

        # Build (fact, source, evidence_ids) tuples
        fact_entries = []
        for learn in learnings:
            fact = learn.get("fact", "")
            eids = learn.get("evidence_ids", [])
            if not fact or not eids:
                continue
            # Derive source from evidence store
            eid = eids[0]
            ev = self._evidence_store.get(eid, {})
            source = ev.get("source_url", "") or ev.get(
                "source_title", "",
            )
            fact_entries.append({
                "fact": fact,
                "source": source,
                "eid": eid,
                "words": set(re.findall(r'[a-z]{4,}', fact.lower())),
            })

        # Find cross-source pairs with Jaccard > threshold
        pairs = []
        seen_pairs: set[tuple[str, str]] = set()
        for i, a in enumerate(fact_entries):
            if not a["words"]:
                continue
            for j, b in enumerate(fact_entries):
                if j <= i or not b["words"]:
                    continue
                # Must be from different sources
                if a["source"] == b["source"]:
                    continue
                pair_key = (
                    min(a["eid"], b["eid"]),
                    max(a["eid"], b["eid"]),
                )
                if pair_key in seen_pairs:
                    continue
                overlap = len(a["words"] & b["words"])
                union = len(a["words"] | b["words"])
                if union > 0 and overlap / union > jaccard_threshold:
                    pairs.append((a, b))
                    seen_pairs.add(pair_key)
                    if len(pairs) >= 5:
                        break
            if len(pairs) >= 5:
                break

        if not pairs:
            logger.info(
                "[cross-source] No overlapping facts found across "
                "sources",
            )
            return ""

        lines = [
            "\nCROSS-SOURCE FACTS (compare both sources in same "
            "sentence):",
        ]
        for a, b in pairs:
            if _GTA_ENABLED:
                lines.append(
                    f"- Source A ({a['eid']}): "
                    f"{a['fact'][:100]} "
                    f"vs Source B ({b['eid']}): "
                    f"{b['fact'][:100]}",
                )
            else:
                lines.append(
                    f"- Source A: {a['fact'][:100]} "
                    f"[CITE:{a['eid']}] "
                    f"vs Source B: {b['fact'][:100]} "
                    f"[CITE:{b['eid']}]",
                )
        return "\n".join(lines)

    # -------------------------------------------------------------------
    # Wave 3: Entity-linked cross-source synthesis pairs
    # -------------------------------------------------------------------

    def _build_cross_source_synthesis_pairs(
        self, briefing: dict,
    ) -> str:
        """Build entity-linked cross-source synthesis directives.

        Wave 3 (TACL 2025): Instead of word-overlap Jaccard, extract
        entities from facts, build entity→facts index, and find entities
        with facts from 2+ distinct sources. Includes exemplar sentences
        that LLMs can follow for cross-source synthesis.

        Falls back to old Jaccard-based _build_cross_source_facts() if
        entity extraction finds < 2 cross-source entities.
        """
        learnings = briefing.get("learnings", [])
        if len(learnings) < 2:
            return self._build_cross_source_facts(briefing)

        # Step 1: Extract entities and build entity-to-facts index
        entity_facts: dict[str, list[dict]] = {}
        for learn in learnings:
            fact = learn.get("fact", "")
            eids = learn.get("evidence_ids", [])
            if not fact or not eids:
                continue
            eid = eids[0]
            ev = self._evidence_store.get(eid, {})
            source = ev.get("source_url", "") or ev.get(
                "source_title", "",
            )
            if not source:
                continue

            # Extract entities (capitalized noun phrases, filtered)
            entity = self._extract_entity(fact)
            if entity and entity != "the subject":
                # Normalize: lowercase for grouping
                key = entity.lower().strip()
                entity_facts.setdefault(key, []).append({
                    "fact": fact,
                    "eid": eid,
                    "source": source,
                    "entity_display": entity,
                })

        # Step 2: Find cross-source entities (facts from 2+ sources)
        cross_entities: list[tuple[str, list[dict]]] = []
        for key, facts_list in entity_facts.items():
            sources = {f["source"] for f in facts_list}
            if len(sources) >= 2:
                cross_entities.append((key, facts_list))

        # Sort by fact count descending (richest cross-source entities)
        cross_entities.sort(key=lambda x: len(x[1]), reverse=True)

        if not cross_entities:
            # No cross-source entities — fall back to Jaccard-based pairs
            return self._build_cross_source_facts(briefing)

        # Step 3: Generate synthesis directives with exemplars
        lines = [
            "CROSS-SOURCE SYNTHESIS (write ONE sentence per "
            "directive citing BOTH sources):",
        ]
        directive_count = 0
        for key, facts_list in cross_entities[:8]:
            # Group by source, take one fact per source
            by_source: dict[str, dict] = {}
            for f in facts_list:
                src = f["source"]
                if src not in by_source:
                    by_source[src] = f
            if len(by_source) < 2:
                continue

            sources = list(by_source.values())[:2]
            a, b = sources[0], sources[1]
            entity_name = a["entity_display"]

            # Extract key numbers for exemplar
            num_a = re.search(
                r'(\d+\.?\d*\s*(?:%|mg|ppt|ppb|ppm|µm|nm|\$|kWh|MPa))',
                a["fact"],
            )
            num_b = re.search(
                r'(\d+\.?\d*\s*(?:%|mg|ppt|ppb|ppm|µm|nm|\$|kWh|MPa))',
                b["fact"],
            )

            lines.append(f"\nEntity: {entity_name}")
            lines.append(
                f"  Source A ({a['eid']}): "
                f"{a['fact'][:120]}"
            )
            lines.append(
                f"  Source B ({b['eid']}): "
                f"{b['fact'][:120]}"
            )

            # Exemplar sentence / directive
            if _HYBRID_EVIDENCE:
                # No exemplar verbs — passage-number directives
                num_a_p = self._get_passage_number(a['eid'])
                num_b_p = self._get_passage_number(b['eid'])
                if num_a_p and num_b_p:
                    lines.append(
                        f"  -> Compare [{num_a_p}] and "
                        f"[{num_b_p}] on {entity_name}"
                    )
                else:
                    lines.append(
                        f"  -> Compare findings on "
                        f"{entity_name} across both sources"
                    )
            elif _GTA_ENABLED:
                if num_a and num_b:
                    lines.append(
                        f"  -> WRITE: \"{entity_name} achieves "
                        f"{num_a.group(1)} while costing "
                        f"{num_b.group(1)}.\""
                    )
                else:
                    lines.append(
                        f"  -> WRITE: \"{entity_name} achieves "
                        f"[finding A], whereas [finding B].\""
                    )
            else:
                if num_a and num_b:
                    lines.append(
                        f"  -> WRITE: \"{entity_name} achieves "
                        f"{num_a.group(1)} [CITE:{a['eid']}] "
                        f"while costing {num_b.group(1)} "
                        f"[CITE:{b['eid']}].\""
                    )
                else:
                    lines.append(
                        f"  -> WRITE: \"{entity_name} "
                        f"demonstrates "
                        f"[finding A] [CITE:{a['eid']}], "
                        f"whereas "
                        f"[finding B] [CITE:{b['eid']}].\""
                    )

            directive_count += 1
            if directive_count >= 8:
                break

        if directive_count < 1:
            return self._build_cross_source_facts(briefing)

        logger.info(
            "[cross-source] Wave 3: %d entity-linked directives "
            "generated", directive_count,
        )
        return "\n".join(lines)

    def _count_cross_source_sentences(self, text: str) -> int:
        """Count sentences citing 2+ evidence from different sources.

        Wave 3: Used by quality gate and cross-source flag check.
        """
        count = 0
        cite_re = re.compile(r'\[CITE:(ev_[a-f0-9]+)\]')
        for sent_match in re.finditer(r'[^.!?]+[.!?]', text):
            sent = sent_match.group()
            cited_eids = cite_re.findall(sent)
            if len(cited_eids) < 2:
                continue
            # Check if citations come from different sources
            sources = set()
            for eid in cited_eids:
                ev = self._evidence_store.get(eid, {})
                src = ev.get("source_url", "") or ev.get(
                    "source_title", "",
                )
                if src:
                    sources.add(src)
            if len(sources) >= 2:
                count += 1
        return count

    # -------------------------------------------------------------------
    # Phase 5: WRITE — scaffold-based interpretation
    # -------------------------------------------------------------------

    async def _write_interpretation(
        self, scaffold: str, briefing: dict,
    ) -> str:
        """Write analytical prose FROM the scaffold (Phase 5).

        The LLM expands the scaffold into full prose. It never sees raw
        evidence statements, preventing verbatim parroting.
        """
        # Wave 2 RCS: Analytical claims in legacy write path
        cluster_summary = self._build_enriched_cluster_summary(briefing)

        # D3+D4: Structural enforcement sections
        mandatory_numbers = self._build_mandatory_numbers_section()
        perspective_coverage = self._build_perspective_coverage_section(
            briefing,
        )

        if _HYBRID_EVIDENCE:
            prompt = (
                f"You are a senior research analyst. Expand "
                f"this analytical scaffold into publication-"
                f"quality prose.\n\n"
                f"RESEARCH QUESTION: {self._query}\n\n"
                f"ANALYTICAL SCAFFOLD:\n{scaffold}\n\n"
                f"EVIDENCE PASSAGES:\n{cluster_summary}\n\n"
                f"{mandatory_numbers}"
                f"{perspective_coverage}"
                f"RULES:\n"
                f"1. Cite by passage number [N]\n"
                f"2. Synthesize — do NOT copy passage text\n"
                f"3. Write CROSS-SOURCE insights\n"
                f"4. Do NOT add claims not in the evidence\n"
                f"5. Evidence-based ranking\n"
                f"6. End with data gaps and limitations\n"
                f"7. Every body paragraph MUST discuss at "
                f"least 2 criteria\n"
                f"8. Include at least 5 numerical values with "
                f"units from evidence\n"
            )
            system = (
                "Expand the scaffold into analytical prose. "
                "Cite by passage number [N]. Synthesize "
                "findings. Do not invent new claims."
            )
        elif _GTA_ENABLED:
            prompt = (
                f"You are a senior research analyst. Expand this "
                f"analytical scaffold into publication-quality "
                f"prose.\n\n"
                f"RESEARCH QUESTION: {self._query}\n\n"
                f"ANALYTICAL SCAFFOLD:\n{scaffold}\n\n"
                f"ANALYTICAL CLAIMS:\n{cluster_summary}\n\n"
                f"{mandatory_numbers}"
                f"{perspective_coverage}"
                f"RULES:\n"
                f"1. EXPAND the scaffold into full analytical "
                f"paragraphs (800-1500 words)\n"
                f"2. Write analytical prose — do NOT include "
                f"citation markers (citations will be added "
                f"automatically)\n"
                f"3. Never restate a claim question as prose — "
                f"ANSWER it\n"
                f"4. Write CROSS-SOURCE insights ('Comparing X "
                f"and Y reveals...')\n"
                f"5. Do NOT add claims not in the scaffold (no "
                f"hallucination)\n"
                f"6. Include a clear ranking with evidence-backed "
                f"justification\n"
                f"7. End with data gaps and limitations\n"
                f"8. Do NOT mention 'scaffold' or 'framework' in "
                f"the output\n"
                f"9. Every body paragraph MUST discuss at least 2 "
                f"criteria (cost, performance, mechanism, "
                f"limitation, application)\n"
                f"10. Include at least 5 numerical values with "
                f"units from evidence — use exact values, do not "
                f"paraphrase numbers\n"
            )
            system = (
                "Expand the scaffold into analytical prose. Do not "
                "include citation markers — citations will be added "
                "automatically. Do not invent new claims. Be "
                "concise and analytical."
            )
        else:
            prompt = (
                f"You are a senior research analyst. Expand this "
                f"analytical scaffold into publication-quality "
                f"prose.\n\n"
                f"RESEARCH QUESTION: {self._query}\n\n"
                f"ANALYTICAL SCAFFOLD:\n{scaffold}\n\n"
                f"ANALYTICAL CLAIMS:\n{cluster_summary}\n\n"
                f"{mandatory_numbers}"
                f"{perspective_coverage}"
                f"RULES:\n"
                f"1. EXPAND the scaffold into full analytical "
                f"paragraphs (800-1500 words)\n"
                f"2. Preserve ALL citations [CITE:ev_xxx] from "
                f"the scaffold\n"
                f"3. For EVERY numerical claim, include the "
                f"citation\n"
                f"4. Never restate a claim question as prose — "
                f"ANSWER it\n"
                f"5. Write CROSS-SOURCE insights ('Comparing X "
                f"and Y reveals...')\n"
                f"6. Do NOT add claims not in the scaffold (no "
                f"hallucination)\n"
                f"7. Include a clear ranking with evidence-backed "
                f"justification\n"
                f"8. End with data gaps and limitations\n"
                f"9. ONLY cite evidence IDs starting with 'ev_'. "
                f"NEVER cite tool names\n"
                f"10. Do NOT mention 'scaffold' or 'framework' "
                f"in the output\n"
                f"11. Every body paragraph MUST discuss at least "
                f"2 criteria (cost, performance, mechanism, "
                f"limitation, application)\n"
                f"12. Include at least 5 numerical values with "
                f"units from evidence — use exact values, do not "
                f"paraphrase numbers\n"
            )
            system = (
                "Expand the scaffold into analytical prose. Every "
                "claim must have a [CITE:ev_xxx] citation from "
                "the scaffold. Do not invent new claims. Be "
                "concise and analytical."
            )

        interpret_timeout = int(
            os.getenv("PG_REACT_INTERPRET_TIMEOUT", "180"),
        )
        try:
            response = await asyncio.wait_for(
                self._client.generate(
                    prompt=prompt,
                    system=system,
                    max_tokens=8192,
                    temperature=0.3,
                    timeout=interpret_timeout,
                ),
                timeout=interpret_timeout + 30,
            )

            content = response.content.strip()
            if not content or len(content) < 100:
                logger.warning(
                    "[8phase] Write produced too little: %d chars",
                    len(content),
                )
                return ""

            # Remove phantom citations
            all_cited = re.findall(r'\[CITE:([^\]]+)\]', content)
            phantom_ids = [
                eid for eid in all_cited
                if eid not in self._evidence_store
            ]
            for pid in set(phantom_ids):
                content = content.replace(f"[CITE:{pid}]", "")

            valid_ids = [
                eid for eid in all_cited
                if eid in self._evidence_store
            ]

            # Add as notebook step
            step = AnalysisStep(
                step_number=self._notebook.step_count + 1,
                reasoning="8-phase scaffold-based interpretation",
                tool_name="interpret_results",
                result=ToolResult(
                    success=True,
                    tool_name="interpret_results",
                    markdown=content,
                    source_evidence_ids=list(set(valid_ids)),
                    insights=[
                        "Scaffold-based analysis with integrated criteria",
                    ],
                ),
                elapsed_seconds=0.0,
            )
            self._notebook.add_step(step)

            logger.info(
                "[8phase] Write complete: %d chars, %d citations "
                "(%d valid, %d phantom)",
                len(content), len(all_cited), len(valid_ids),
                len(phantom_ids),
            )

            return content

        except Exception as exc:
            logger.warning(
                "[8phase] Write failed: %s: %s",
                type(exc).__name__, str(exc)[:200],
            )
            return ""

    # -------------------------------------------------------------------
    # Phase 6 (new): WRITE + SELF-REFINE — merged draft/feedback/refine
    # -------------------------------------------------------------------

    def _get_required_flags(
        self,
        classification: dict | None,
        gap_queries: list[str] | None = None,
    ) -> list[str]:
        """Determine required boolean flags based on classification.

        Patch 5: has_gap_analysis only required when gap_queries exist.
        """
        artifacts = (classification or {}).get("artifacts", [])
        flags = [
            "all_numbers_cited",
            "has_explicit_tradeoffs",
        ]
        # C2 fix: only require cross-source when evidence has 3+ sources
        distinct_sources = len({
            self._evidence_store.get(eid, {}).get("source_url", "")
            for eid in self._evidence_ids[:50]
        } - {""})
        if distinct_sources >= 3:
            flags.append("has_cross_source_synthesis")
        if "comparison_table" in artifacts:
            flags.append("contains_comparison_table")
        if "conditional_recommendations" in artifacts:
            flags.append("contains_conditional_recommendations")
        if "evidence_based_ranking" in artifacts:
            flags.append("has_evidence_based_ranking")
        # Patch 5: only require gap analysis when gaps were identified
        if gap_queries:
            flags.append("has_gap_analysis")
        # TQ-4: cost calculations required when cost evidence exists
        cost_learnings = (classification or {}).get(
            "evidence_signals", {},
        ).get("cost_learnings", 0)
        if cost_learnings >= 2 or "cost_model" in artifacts:
            flags.append("has_cost_calculations")
        return flags

    def _programmatic_feedback(
        self, draft: str, required_flags: list[str],
    ) -> dict[str, bool]:
        """Programmatic boolean checklist — no LLM, pure regex.

        Used as fallback when LLM feedback times out. Stricter than
        LLM (no sycophancy risk) so false negatives drive refinement.
        """
        feedback = {}

        for flag in required_flags:
            if flag == "contains_comparison_table":
                # Strict markdown table: header + separator + >=2 data rows
                tables = re.findall(
                    r'\n\|[-:| ]+\|\n', draft,
                )
                table_lines = len(re.findall(
                    r'^\|.+\|$', draft, re.MULTILINE,
                ))
                # header + separator + at least 2 data rows = 4+ lines
                feedback[flag] = len(tables) >= 1 and table_lines >= 4

            elif flag == "contains_conditional_recommendations":
                # "If...then" patterns (bold or plain)
                bold_if = len(re.findall(
                    r'\*\*[Ii]f\*\*', draft,
                ))
                plain_if = len(re.findall(
                    r'(?:^|\. )[Ii]f\s+.{10,80}\s+then\s+',
                    draft, re.MULTILINE,
                ))
                # FIX-D3: Reject if brackets remain in conditional recs
                has_brackets = bool(re.search(
                    r'\*\*[Ii]f\*\*[^.]*\[[^\]]*\][^.]*'
                    r'(?:then|because)',
                    draft,
                ))
                feedback[flag] = (
                    (bold_if + plain_if) >= 2 and not has_brackets
                )

            elif flag == "all_numbers_cited":
                # Check ratio of numerical claims with nearby citations
                num_claims = re.findall(
                    r'\d+\.?\d*\s*(?:%|mg|ng|ppt|ppb|ppm|kWh|\$|MPa|'
                    r'µm|nm|m2|g/L|mg/g|billion|million)',
                    draft,
                )
                cited_nums = re.findall(
                    r'\d+\.?\d*\s*(?:%|mg|ng|ppt|ppb|ppm|kWh|\$|MPa|'
                    r'µm|nm|m2|g/L|mg/g|billion|million)'
                    r'[^.!?\n]{0,80}\[CITE:ev_[a-f0-9]+\]',
                    draft,
                )
                ratio = len(cited_nums) / max(len(num_claims), 1)
                feedback[flag] = ratio >= 0.6

            elif flag == "has_explicit_tradeoffs":
                tradeoff_markers = len(re.findall(
                    r'(?:trade-?off|however|although|whereas|'
                    r'disadvantage|drawback|limitation|conversely|'
                    r'in contrast)',
                    draft, re.IGNORECASE,
                ))
                feedback[flag] = tradeoff_markers >= 3

            elif flag == "has_evidence_based_ranking":
                # Numbered list or "ranks highest/first/second"
                has_numbered = bool(re.search(
                    r'(?:^|\n)\s*[1-3]\.\s+\*?\*?', draft,
                ))
                has_rank_words = bool(re.search(
                    r'rank(?:s|ed)?\s+(?:highest|first|second|third)',
                    draft, re.IGNORECASE,
                ))
                # FIX-D1: Also detect heading-style rankings
                has_heading = bool(re.search(
                    r'#{2,4}\s+.*(?:rank|Evidence.Based.Rank)',
                    draft, re.IGNORECASE,
                ))
                feedback[flag] = (
                    has_numbered or has_rank_words or has_heading
                )

            elif flag == "has_gap_analysis":
                gap_markers = len(re.findall(
                    r'(?:gap|limitation|missing|insufficient|'
                    r'further research|future\s+(?:research|work|'
                    r'studies))',
                    draft, re.IGNORECASE,
                ))
                feedback[flag] = gap_markers >= 2

            elif flag == "has_cost_calculations":
                # TQ-4: requires $...per/×/= patterns
                cost_patterns = len(re.findall(
                    r'\$[\d,.]+\s*(?:per|/|×|=|million|billion|'
                    r'annually|year|month)',
                    draft, re.IGNORECASE,
                ))
                feedback[flag] = cost_patterns >= 1

            elif flag == "has_cross_source_synthesis":
                # Wave 3: Count sentences with 2+ citations from
                # different sources
                cross_count = self._count_cross_source_sentences(draft)
                feedback[flag] = cross_count >= 3

            else:
                # Unknown flag — default to false to trigger refine
                feedback[flag] = False

        passing = sum(1 for v in feedback.values() if v)
        logger.info(
            "[self-refine] Programmatic feedback: %d/%d flags passing: %s",
            passing, len(required_flags),
            {k: v for k, v in feedback.items()},
        )
        return feedback

    def _get_refinement_feedback(
        self, draft: str, classification: dict | None,
        gap_queries: list[str] | None = None,
    ) -> dict[str, bool]:
        """Get boolean checklist feedback on draft — programmatic only.

        SR-1: LLM feedback deleted (0/15 succeeded historically).
        Programmatic checks are stricter, instant, and deterministic.
        """
        required_flags = self._get_required_flags(
            classification, gap_queries,
        )
        return self._programmatic_feedback(draft, required_flags)

    def _programmatic_refine(
        self, draft: str, feedback: dict[str, bool],
        briefing: dict, gap_evidence: list[dict] | None = None,
    ) -> str:
        """SR-2: Targeted programmatic patches — no LLM, instant.

        Instead of regenerating text, injects existing tool outputs
        and appends missing sections per failing flag.
        """
        failing = [
            flag for flag, passed in feedback.items() if not passed
        ]
        if not failing:
            return draft

        patches = []

        for flag in failing:
            if flag == "contains_comparison_table":
                table_patch = self._patch_comparison_table()
                if table_patch:
                    # Insert after ### Comparative or ### Analysis
                    # heading, or append if no heading found
                    heading_match = re.search(
                        r'(###\s+(?:Comparative|Analysis|Comparison)'
                        r'[^\n]*\n)',
                        draft, re.IGNORECASE,
                    )
                    if heading_match:
                        insert_pos = heading_match.end()
                        draft = (
                            draft[:insert_pos] + "\n"
                            + table_patch + "\n\n"
                            + draft[insert_pos:]
                        )
                    else:
                        # Insert before last section heading
                        last_heading = None
                        for m in re.finditer(
                            r'\n(###\s+[^\n]+\n)', draft,
                        ):
                            last_heading = m
                        if last_heading:
                            pos = last_heading.start()
                            draft = (
                                draft[:pos] + "\n\n"
                                + table_patch + "\n"
                                + draft[pos:]
                            )
                        else:
                            patches.append(table_patch)
            elif flag == "contains_conditional_recommendations":
                patches.append(self._patch_conditional_recs(briefing))
            elif flag == "all_numbers_cited":
                draft = self._patch_uncited_numbers(draft)
            elif flag == "has_explicit_tradeoffs":
                patches.append(self._patch_tradeoffs(briefing))
            elif flag == "has_evidence_based_ranking":
                patches.append(self._patch_ranking(draft))
            elif flag == "has_gap_analysis":
                gap_queries = []
                if isinstance(briefing, dict):
                    gap_queries = briefing.get(
                        "_gap_queries", [],
                    ) or (
                        self._notebook.steps[-1].result.statistics.get(
                            "gap_queries", [],
                        )
                        if self._notebook.steps
                        and self._notebook.steps[-1].result.statistics
                        else []
                    )
                patches.append(self._patch_gap_analysis(gap_queries))

        # Append non-empty patches to draft
        appended = [p for p in patches if p]
        if appended:
            draft = draft.rstrip() + "\n\n" + "\n\n".join(appended)

        logger.info(
            "[self-refine] Programmatic refine: %d flags failing, "
            "%d patches applied",
            len(failing), len(appended),
        )
        return draft

    def _patch_comparison_table(self) -> str:
        """Extract comparison_table tool output and format as markdown.

        FIX-D2: Validates table structure — discards if column count
        mismatch exceeds 1 between header and any data row.
        """
        for step in self._notebook.steps:
            if (
                step.tool_name == "comparison_table"
                and step.result.success
                and step.result.markdown
            ):
                table_md = step.result.markdown.strip()
                if "|" not in table_md:
                    continue
                # FIX-D2: Validate column consistency
                rows = [
                    r for r in table_md.split("\n")
                    if r.strip().startswith("|")
                ]
                if len(rows) >= 3:
                    header_cols = len([
                        c for c in rows[0].split("|") if c.strip()
                    ])
                    malformed = False
                    for row in rows[2:]:
                        row_cols = len([
                            c for c in row.split("|") if c.strip()
                        ])
                        if abs(row_cols - header_cols) > 1:
                            malformed = True
                            break
                    if malformed:
                        logger.warning(
                            "[patch-table] FIX-D2: Discarding "
                            "malformed table (column mismatch)",
                        )
                        return ""
                return f"### Comparative Analysis\n\n{table_md}"
        return ""

    def _patch_conditional_recs(self, briefing: dict) -> str:
        """Generate templated conditional recommendations from data.

        SR-2: Extracts from data_points grouped by label, then
        enriches with evidence from learnings.
        TQ-3: Uses actual breakpoints from data_points.
        """
        data_points = self._notebook.data_points

        # Primary path: group data_points by label
        by_label: dict[str, list[dict]] = {}
        for dp in data_points:
            label = dp.get("label", "")
            if label:
                by_label.setdefault(label, []).append(dp)

        # Fallback: if no data_points, extract from learnings
        learnings = briefing.get("learnings", [])
        if not by_label:
            entity_evidence: dict[str, list[dict]] = {}
            for learn in learnings:
                fact = learn.get("fact", "")
                entity_match = re.search(
                    r'\b([A-Z][a-zA-Z\-]+(?:\s+[A-Z][a-zA-Z\-]+)*)\b',
                    fact,
                )
                entity = (
                    entity_match.group(1)
                    if entity_match else "this approach"
                )
                eids = learn.get("evidence_ids", [])
                if eids:
                    entity_evidence.setdefault(entity, []).append({
                        "fact": fact,
                        "eid": eids[0],
                    })
            top_entities = sorted(
                entity_evidence.items(),
                key=lambda x: len(x[1]),
                reverse=True,
            )[:3]
            if not top_entities:
                return ""
            recs = ["### Conditional Recommendations\n"]
            for entity, evidence_list in top_entities:
                ev = evidence_list[0]
                claim = ev["fact"][:120]
                eid = ev["eid"]
                recs.append(
                    f"**If** the application requires the properties "
                    f"described for {entity}, **then** {entity} is "
                    f"recommended **because** {claim} "
                    f"[CITE:{eid}]"
                )
            return "\n\n".join(recs) if len(recs) > 1 else ""

        # Primary path: top 3 labels by data point count
        top_labels = sorted(
            by_label.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )[:3]

        # Build evidence lookup from learnings
        label_evidence: dict[str, dict] = {}
        for learn in learnings:
            fact = learn.get("fact", "")
            eids = learn.get("evidence_ids", [])
            if not eids:
                continue
            for label, _ in top_labels:
                if label.lower() in fact.lower():
                    label_evidence.setdefault(label, {
                        "fact": fact,
                        "eid": eids[0],
                    })

        recs = ["### Conditional Recommendations\n"]
        for label, dps in top_labels:
            # TQ-3/FIX-CRASH: Use actual breakpoints — type-safe
            best_dp = max(
                dps,
                key=lambda d: _safe_float(d.get("value")) or 0.0,
            )
            val = best_dp.get("value", "")
            unit = best_dp.get("unit", "")
            eid = best_dp.get("evidence_id", "")
            ev_info = label_evidence.get(label, {})
            claim = ev_info.get("fact", f"{label} data")[:120]
            cite_eid = ev_info.get("eid", eid)

            if val and unit:
                condition = (
                    f"the target requires ≥{val} {unit} performance"
                )
            else:
                condition = (
                    f"the application requires the properties "
                    f"described for {label}"
                )
            recs.append(
                f"**If** {condition}, **then** {label} is "
                f"recommended **because** {claim} "
                f"[CITE:{cite_eid}]"
            )

        return "\n\n".join(recs) if len(recs) > 1 else ""

    def _patch_uncited_numbers(self, draft: str) -> str:
        """Find numbers without nearby CITE and add citations."""
        num_pattern = re.compile(
            r'(\d+\.?\d*)\s*(%|mg|ng|ppt|ppb|ppm|kWh|\$|MPa|'
            r'µm|nm|m2|g/L|mg/g|billion|million)',
        )
        cite_pattern = re.compile(r'\[CITE:ev_[a-f0-9]+\]')

        lines = draft.split("\n")
        patched_lines = []
        for line in lines:
            for match in num_pattern.finditer(line):
                num_str = match.group(1)
                num_end = match.end()
                # Check if there's a CITE within 80 chars after
                after_window = line[num_end:num_end + 80]
                if cite_pattern.search(after_window):
                    continue
                # Search evidence store for this number
                for eid, ev in self._evidence_store.items():
                    ev_stmt = ev.get("statement", "")
                    if re.search(
                        r'(?<!\d)' + re.escape(num_str) + r'(?!\d)',
                        ev_stmt,
                    ):
                        # Insert citation after the unit
                        insert_pos = match.end()
                        line = (
                            line[:insert_pos]
                            + f" [CITE:{eid}]"
                            + line[insert_pos:]
                        )
                        break
            patched_lines.append(line)
        return "\n".join(patched_lines)

    def _patch_tradeoffs(self, briefing: dict) -> str:
        """Find opposing evidence and append trade-off sentences."""
        learnings = briefing.get("learnings", [])
        tradeoff_pairs = []

        for i, learn_a in enumerate(learnings):
            fact_a = learn_a.get("fact", "")
            eids_a = learn_a.get("evidence_ids", [])
            if not eids_a:
                continue
            for learn_b in learnings[i + 1:]:
                fact_b = learn_b.get("fact", "")
                eids_b = learn_b.get("evidence_ids", [])
                if not eids_b:
                    continue
                # Check for opposition markers
                if re.search(
                    r'(?:however|but|limitation|drawback|lower|'
                    r'higher cost|less|reduced)',
                    fact_b, re.IGNORECASE,
                ):
                    tradeoff_pairs.append((
                        fact_a[:100], eids_a[0],
                        fact_b[:100], eids_b[0],
                    ))
                    if len(tradeoff_pairs) >= 2:
                        break
            if len(tradeoff_pairs) >= 2:
                break

        if not tradeoff_pairs:
            return ""

        lines = ["### Key Trade-offs\n"]
        for fact_a, eid_a, fact_b, eid_b in tradeoff_pairs:
            lines.append(
                f"A key trade-off exists: while {fact_a} "
                f"[CITE:{eid_a}], {fact_b} [CITE:{eid_b}]."
            )
        return "\n\n".join(lines)

    def _patch_ranking(self, draft: str = "") -> str:
        """Extract ranking from rank_by_impact tool output.

        FIX-D1: Guards against duplicate ranking section. If the draft
        already contains a ranking heading, return empty string.
        """
        if draft and re.search(
            r'#{2,4}\s+.*(?:rank|Evidence.Based.Rank)',
            draft, re.IGNORECASE,
        ):
            logger.debug(
                "[patch-ranking] Draft already has ranking heading, "
                "skipping patch",
            )
            return ""
        for step in self._notebook.steps:
            if (
                step.tool_name == "rank_by_impact"
                and step.result.success
                and step.result.markdown
            ):
                return (
                    f"### Evidence-Based Ranking\n\n"
                    f"{step.result.markdown.strip()}"
                )

        # Fallback: build ranking from data points
        data_points = self._notebook.data_points
        if not data_points:
            return ""

        # Group by label, sort by value
        by_label: dict[str, list] = {}
        for dp in data_points:
            label = dp.get("label", "unknown")
            by_label.setdefault(label, []).append(dp)

        if len(by_label) < 2:
            return ""

        # FIX-CRASH: Rank by average value per label — type-safe via _safe_float
        ranked = []
        for label, dps in by_label.items():
            vals = [
                v for dp in dps
                if (v := _safe_float(dp.get("value"))) is not None
            ]
            avg = sum(vals) / max(len(vals), 1) if vals else 0.0
            eid = dps[0].get("evidence_id", "")
            ranked.append((label, avg, eid))
        ranked.sort(key=lambda x: x[1], reverse=True)

        lines = ["### Evidence-Based Ranking\n"]
        for i, (label, avg, eid) in enumerate(ranked[:5], 1):
            cite = f" [CITE:{eid}]" if eid else ""
            lines.append(f"{i}. **{label}** ({avg:.1f}){cite}")

        return "\n".join(lines)

    def _patch_gap_analysis(self, gap_queries: list[str]) -> str:
        """Format gap queries as prose gap analysis section."""
        if not gap_queries:
            return ""

        lines = [
            "### Data Gaps and Limitations\n",
            "The following evidence gaps were identified during "
            "analysis:\n",
        ]
        for gq in gap_queries[:5]:
            lines.append(f"- {gq}")
        lines.append(
            "\nFurther research is needed to address these gaps "
            "and strengthen the evidence base."
        )
        return "\n".join(lines)

    async def _write_and_refine(
        self, scaffold: str, briefing: dict,
        classification: dict | None,
        gap_evidence: list[dict],
        pipeline_start: float | None = None,
    ) -> str:
        """Write analytical output with SELF-REFINE loop.

        SR-1: Feedback is programmatic-only (no LLM, instant).
        SR-2: Refine is targeted patches (no LLM, instant).
        SR-3: Quality gate with budget-aware retry after loop.
        SR-4: Write prompt consolidated to 10 rules.
        """
        write_phase_start = time.monotonic()
        # SR-3 fix: use pipeline start for budget check, fallback
        # to write phase start if not provided
        _pipeline_start = pipeline_start or write_phase_start

        # Format gap evidence for write prompt
        gap_context = ""
        if gap_evidence:
            gap_lines = []
            for ge in gap_evidence[:_MAX_GAP_EVIDENCE]:
                if _GTA_ENABLED:
                    gap_lines.append(
                        f"- {ge['statement'][:200]} "
                        f"(refs: {ge['evidence_id']})"
                    )
                else:
                    gap_lines.append(
                        f"- {ge['statement'][:200]} "
                        f"[CITE:{ge['evidence_id']}]"
                    )
            gap_context = (
                "\n\nGAP-FILL EVIDENCE (use to address identified "
                "gaps — SYNTHESIZE these findings into your analysis, "
                "do NOT copy them verbatim as a list):\n"
                + "\n".join(gap_lines)
            )

        # Wave 2 RCS: Analytical claims instead of raw evidence themes
        cluster_summary = self._build_enriched_cluster_summary(briefing)

        # Wave 3: Entity-linked cross-source synthesis directives
        cross_source = self._build_cross_source_synthesis_pairs(briefing)

        # D3+D4: Structural enforcement sections
        mandatory_numbers = self._build_mandatory_numbers_section()
        perspective_coverage = self._build_perspective_coverage_section(
            briefing,
        )

        if _HYBRID_EVIDENCE:
            # Hybrid: numbered passages, LLM cites by [N]
            prompt = (
                f"You are a senior research analyst. Expand this "
                f"analytical scaffold into publication-quality "
                f"prose (800-1500 words).\n\n"
                f"RESEARCH QUESTION: {self._query}\n\n"
                f"ANALYTICAL SCAFFOLD:\n{scaffold}\n\n"
                f"SECTION 1 — EVIDENCE PASSAGES (synthesize "
                f"from these numbered sources — do NOT copy "
                f"text):\n{cluster_summary}\n\n"
                f"SECTION 2 — CROSS-SOURCE COMPARISONS:\n"
                f"{cross_source}\n\n"
                f"{mandatory_numbers}"
                f"{perspective_coverage}"
                f"RULES:\n"
                f"1. Every factual claim must cite its source "
                f"passage by number [N]\n"
                f"2. Synthesize — do NOT copy passage text "
                f"verbatim\n"
                f"3. Cross-source: ONE sentence comparing BOTH "
                f"sources per directive\n"
                f"4. Use comparative language (whereas, in "
                f"contrast, similarly)\n"
                f"5. Preserve exact units (ppt, ppb, ppm, "
                f"mg/L, MPa, µm, kWh, etc.)\n"
                f"6. Do NOT add claims not in the evidence\n"
                f"7. Evidence-based ranking (cite metrics)\n"
                f"8. Trade-offs explicitly (however, whereas)\n"
                f"9. Executive summary first paragraph\n"
                f"10. Conditional recs: **If** X **then** Y "
                f"**because** Z [N]\n"
                f"11. Every body paragraph MUST discuss at "
                f"least 2 criteria\n"
                f"12. Include at least 5 numerical values with "
                f"units from evidence\n"
                f"{gap_context}"
            )
            system = (
                "Expand the scaffold into analytical prose. "
                "Cite evidence by passage number [N]. "
                "Synthesize findings — do not copy passage text. "
                "Do not invent claims."
            )
        elif _GTA_ENABLED:
            # GTA: citation-free prose — citations added programmatically
            prompt = (
                f"You are a senior research analyst. Expand this "
                f"analytical scaffold into publication-quality prose "
                f"(800-1500 words).\n\n"
                f"RESEARCH QUESTION: {self._query}\n\n"
                f"ANALYTICAL SCAFFOLD:\n{scaffold}\n\n"
                f"SECTION 1 — ANALYTICAL CLAIMS (answer each "
                f"question in your own words):\n"
                f"{cluster_summary}\n\n"
                f"SECTION 2 — CROSS-SOURCE SYNTHESIS DIRECTIVES:\n"
                f"{cross_source}\n\n"
                f"{mandatory_numbers}"
                f"{perspective_coverage}"
                f"INSTRUCTIONS:\n"
                f"Phase 1 — ANSWER each analytical claim in your "
                f"own words using evidence values\n"
                f"Phase 2 — WEAVE cross-source sentences using the "
                f"directives above (minimum 4)\n"
                f"Phase 3 — CONNECT with transitions (compare, "
                f"contrast, evaluate)\n\n"
                f"RULES:\n"
                f"1. Write analytical prose — do NOT include "
                f"citation markers (citations will be added "
                f"automatically)\n"
                f"2. Never restate a claim question as prose — "
                f"ANSWER it\n"
                f"3. Cross-source: ONE sentence comparing BOTH "
                f"sources per directive\n"
                f"4. Use comparative language (whereas, in "
                f"contrast, similarly)\n"
                f"5. Preserve exact units (ppt, ppb, ppm, mg/L, "
                f"MPa, µm, kWh, etc.)\n"
                f"6. Do NOT add claims not in the scaffold\n"
                f"7. Evidence-based ranking (cite metrics, not "
                f"scores)\n"
                f"8. Trade-offs explicitly (however, whereas, in "
                f"contrast)\n"
                f"9. Executive summary first paragraph\n"
                f"10. Conditional recs: **If** X **then** Y "
                f"**because** Z\n"
                f"11. Every body paragraph MUST discuss at least 2 "
                f"criteria (cost, performance, mechanism, "
                f"limitation, application)\n"
                f"12. Include at least 5 numerical values with "
                f"units from evidence — use exact values, do not "
                f"paraphrase numbers\n"
                f"{gap_context}"
            )
            system = (
                "Expand the scaffold into analytical prose. ANSWER "
                "each analytical claim — do not restate the "
                "question. Do not invent claims. Do NOT include "
                "citation markers like [CITE:...] — citations will "
                "be added automatically after writing."
            )
        else:
            prompt = (
                f"You are a senior research analyst. Expand this "
                f"analytical scaffold into publication-quality prose "
                f"(800-1500 words).\n\n"
                f"RESEARCH QUESTION: {self._query}\n\n"
                f"ANALYTICAL SCAFFOLD:\n{scaffold}\n\n"
                f"SECTION 1 — ANALYTICAL CLAIMS (answer each "
                f"question in your own words):\n"
                f"{cluster_summary}\n\n"
                f"SECTION 2 — CROSS-SOURCE SYNTHESIS DIRECTIVES:\n"
                f"{cross_source}\n\n"
                f"{mandatory_numbers}"
                f"{perspective_coverage}"
                f"INSTRUCTIONS:\n"
                f"Phase 1 — ANSWER each analytical claim in your "
                f"own words using the cited evidence values\n"
                f"Phase 2 — WEAVE cross-source sentences using the "
                f"directives above (minimum 4)\n"
                f"Phase 3 — CONNECT with transitions (compare, "
                f"contrast, evaluate)\n\n"
                f"RULES:\n"
                f"1. Every numerical value must have "
                f"[CITE:ev_xxx]\n"
                f"2. Never restate a claim question as prose — "
                f"ANSWER it\n"
                f"3. Cross-source: ONE sentence citing BOTH "
                f"sources per directive\n"
                f"4. Use comparative language (whereas, in "
                f"contrast, similarly)\n"
                f"5. Preserve exact units (ppt, ppb, ppm, mg/L, "
                f"MPa, µm, kWh, etc.)\n"
                f"6. Do NOT add claims not in the scaffold\n"
                f"7. Evidence-based ranking (cite metrics, not "
                f"scores)\n"
                f"8. Trade-offs explicitly (however, whereas, in "
                f"contrast)\n"
                f"9. Executive summary first paragraph\n"
                f"10. Conditional recs: **If** X **then** Y "
                f"**because** Z [CITE:ev_xxx]\n"
                f"11. Every body paragraph MUST discuss at least 2 "
                f"criteria (cost, performance, mechanism, "
                f"limitation, application)\n"
                f"12. Include at least 5 numerical values with "
                f"units from evidence — use exact values, do not "
                f"paraphrase numbers\n"
                f"{gap_context}"
            )
            system = (
                "Expand the scaffold into analytical prose. ANSWER "
                "each analytical claim — do not restate the "
                "question. Every claim must have a [CITE:ev_xxx]. "
                "Do not invent claims. Write cross-source "
                "sentences citing 2+ sources."
            )

        write_timeout = int(
            resolve("PG_WRITE_TIMEOUT"),
        )

        try:
            response = await asyncio.wait_for(
                self._client.generate(
                    prompt=prompt,
                    system=system,
                    max_tokens=8192,
                    temperature=0.3,
                    timeout=write_timeout,
                ),
                timeout=write_timeout + 30,
            )
            current = response.content.strip()
        except Exception as exc:
            logger.warning(
                "[write-refine] Initial draft failed: %s: %s",
                type(exc).__name__, str(exc)[:200],
            )
            return ""

        if not current or len(current) < 100:
            logger.warning(
                "[write-refine] Draft too short: %d chars", len(current),
            )
            return ""

        # Strip leaked gap query JSON blocks from output
        current = re.sub(
            r'```json\s*\{[^}]*"gap_search_queries"[^}]*\}\s*```',
            '', current, flags=re.DOTALL,
        ).strip()

        # Remove phantom citations from initial draft
        all_cited = re.findall(r'\[CITE:([^\]]+)\]', current)
        for pid in set(all_cited):
            if pid not in self._evidence_store:
                current = current.replace(f"[CITE:{pid}]", "")

        valid_ids = [
            eid for eid in re.findall(
                r'\[CITE:(ev_[a-f0-9]+)\]', current,
            )
            if eid in self._evidence_store
        ]

        # Add initial draft as notebook step
        step = AnalysisStep(
            step_number=self._notebook.step_count + 1,
            reasoning="6-phase scaffold-based interpretation",
            tool_name="interpret_results",
            result=ToolResult(
                success=True,
                tool_name="interpret_results",
                markdown=current,
                source_evidence_ids=list(set(valid_ids)),
                insights=[
                    "Scaffold-based analysis with integrated criteria",
                ],
            ),
            elapsed_seconds=0.0,
        )
        self._notebook.add_step(step)

        logger.info(
            "[write-refine] Initial draft: %d chars, %d citations",
            len(current), len(valid_ids),
        )

        # SELF-REFINE loop (Loophole 2 fix: 1-2 passes, not 3-4)
        if not _SELF_REFINE_ENABLED:
            return current

        gap_queries = []
        if isinstance(classification, dict):
            gap_queries = classification.get("_gap_queries", [])

        # Inject gap_queries into briefing for _programmatic_refine
        briefing_with_gaps = dict(briefing)
        briefing_with_gaps["_gap_queries"] = gap_queries

        for iteration in range(_SELF_REFINE_MAX_ITERATIONS):
            # Feedback: programmatic boolean checklist (SR-1: instant)
            feedback = self._get_refinement_feedback(
                current, classification, gap_queries,
            )

            # Stopping: ALL required flags must be true
            required_flags = self._get_required_flags(
                classification, gap_queries,
            )
            all_satisfied = all(
                feedback.get(flag, False) for flag in required_flags
            )
            if all_satisfied:
                logger.info(
                    "[self-refine] All %d flags satisfied, stopping "
                    "at iteration %d",
                    len(required_flags), iteration,
                )
                break

            failing = [
                f for f, v in feedback.items() if not v
            ]
            logger.info(
                "[self-refine] Iteration %d: %d/%d flags passing, "
                "failing: %s",
                iteration, len(required_flags) - len(failing),
                len(required_flags), failing,
            )

            # SR-2: Programmatic refine — targeted patches, no LLM
            refined = self._programmatic_refine(
                current, feedback, briefing_with_gaps, gap_evidence,
            )

            # Length check: BYPASS if refined has tables (Loophole 3 fix)
            has_tables = bool(
                re.search(r'\n\|[-:| ]+\|\n', refined),
            )
            if not has_tables and len(refined) < 0.7 * len(current):
                logger.warning(
                    "[self-refine] Refined too short (%d vs %d) "
                    "and no tables, keeping current",
                    len(refined), len(current),
                )
                break

            current = refined

            # Remove phantom citations from refined version
            all_cited = re.findall(r'\[CITE:([^\]]+)\]', current)
            for pid in set(all_cited):
                if pid not in self._evidence_store:
                    current = current.replace(f"[CITE:{pid}]", "")

        # Hybrid: Map passage numbers [N] → [CITE:ev_xxx]
        if _HYBRID_EVIDENCE and self._passage_reverse_map:
            current = self._map_passage_citations(
                current, self._passage_reverse_map,
            )
            cite_count = len(
                re.findall(r'\[CITE:ev_[a-f0-9]+\]', current),
            )
            logger.info(
                "[write-refine] Hybrid passage mapping: %d "
                "citations", cite_count,
            )
            # GTA fallback for sentences without passage refs
            if _GTA_ENABLED:
                current = self._attribute_citations(current)

        # GTA: Strip LLM-generated citations then add programmatically
        elif _GTA_ENABLED:
            # LLM may ignore "no citation markers" instruction and
            # write [CITE:ev_xxx] anyway (often mid-word → D2).
            # Strip ALL before programmatic attribution.
            llm_cites = len(
                re.findall(r'\[CITE:ev_[a-f0-9]+\]', current),
            )
            if llm_cites > 0:
                current = re.sub(
                    r'\[CITE:ev_[a-f0-9]+\]', '', current,
                )
                # Clean up whitespace artifacts from removal
                current = re.sub(r'  +', ' ', current)
                current = re.sub(r' ([.,;:!?])', r'\1', current)
                logger.info(
                    "[write-refine] GTA: stripped %d LLM-generated "
                    "citations before attribution",
                    llm_cites,
                )
            current = self._attribute_citations(current)
            logger.info(
                "[write-refine] GTA attribution: %d citations",
                len(re.findall(r'\[CITE:ev_[a-f0-9]+\]', current)),
            )

        # SR-3: Quality gate with budget-aware retry
        current = await self._quality_gate(
            current, scaffold, briefing, classification,
            gap_evidence, cluster_summary, gap_context,
            write_timeout, start_time=_pipeline_start,
        )

        # Update notebook step with final version
        valid_ids = [
            eid for eid in re.findall(
                r'\[CITE:(ev_[a-f0-9]+)\]', current,
            )
            if eid in self._evidence_store
        ]
        for s in self._notebook.steps:
            if (
                s.tool_name == "interpret_results"
                and s.result.success
            ):
                s.result = ToolResult(
                    success=True,
                    tool_name="interpret_results",
                    markdown=current,
                    source_evidence_ids=list(set(valid_ids)),
                    insights=[
                        "Scaffold-based analysis (self-refined)",
                    ],
                )
                break

        return current

    async def _quality_gate(
        self,
        draft: str,
        scaffold: str,
        briefing: dict,
        classification: dict | None,
        gap_evidence: list[dict],
        cluster_summary: str,
        gap_context: str,
        write_timeout: int,
        start_time: float,
    ) -> str:
        """SR-3: Quality gate with budget-aware retry.

        Checks: word count ≥500, citation count ≥5, programmatic
        feedback ≥4/N flags, parroting ratio <0.35.
        If FAIL and time remains: retry generate() at temperature=0.5.
        """
        words = len(draft.split())
        cite_count = len(re.findall(r'\[CITE:ev_[a-f0-9]+\]', draft))

        gap_queries = []
        if isinstance(classification, dict):
            gap_queries = classification.get("_gap_queries", [])
        feedback = self._get_refinement_feedback(
            draft, classification, gap_queries,
        )
        required_flags = self._get_required_flags(
            classification, gap_queries,
        )
        passing = sum(1 for v in feedback.values() if v)

        # Parroting ratio check (3-gram Jaccard)
        parroting, parroted_count = self._compute_parroting_ratio(draft)

        # FIX-D7: Stricter parroting gate (ratio + absolute floor)
        parrot_threshold = float(
            resolve("PG_PARROTING_THRESHOLD"),
        )
        # WP-2.1 (CRITICAL-4): Lower absolute parroting count to 5
        # to catch DVS runs with 10-17 parroted sentences
        parrot_ok = (
            parroting < parrot_threshold and parroted_count < 5
        )

        # WP-2.1: Template echo detector — catches B1/B2/B3/B5 defects
        # where scaffold prompt patterns leak into output
        _echo_patterns = [
            # B1: "PE demonstrates is produced" etc.
            r'\b[A-Z]\w+\s+demonstrates?\s+(?:is|are|was|were|sees|'
            r'items|production|evaluation|activation|modification|'
            r'force|adhesion|strength|properties)\b',
            # B2: "evidence supports role"
            r'\b\w+\s+evidence\s+supports?\s+(?:general\s+)?'
            r'(?:\w+\s+)?role\b',
            # B3: "Evidence supports X's role"
            r'\bEvidence\s+supports?\s+\w+\'s\s+role\b',
            # B5: "leading to this gap is critical"
            r'\bleading\s+to\s+this\s+gap\s+is\s+critical\b',
        ]
        if resolve("PG_TEMPLATE_ECHO_GATE") == "1":
            echo_count = sum(
                len(re.findall(p, draft, re.IGNORECASE))
                for p in _echo_patterns
            )
        else:
            echo_count = 0
        echo_ok = echo_count < 2

        # WP-2.2: Grammar integrity check — mid-word cites + run-ons
        grammar_issues = 0
        grammar_issues += len(
            re.findall(r'[a-z]\[CITE:', draft),
        )
        grammar_issues += len(
            re.findall(r'\[CITE:ev_[a-f0-9]+\][a-z]', draft),
        )
        for sent in re.split(r'[.!?]\s+', draft):
            if len(sent.split()) > 80:
                grammar_issues += 1
        grammar_ok = grammar_issues < 3

        # WP-2.3: Phantom citation detector — always remove (never valid)
        draft = self._strip_phantom_citations(draft)
        # Recount after potential phantom removal
        cite_count = len(
            re.findall(r'\[CITE:ev_[a-f0-9]+\]', draft),
        )

        # C2 fix: cross-source already covered by has_cross_source_synthesis
        # flag — no separate gate check needed (avoids double-gating)
        gate_pass = (
            words >= 500
            and cite_count >= 5
            and passing >= min(4, len(required_flags))
            and parrot_ok
            and echo_ok
            and grammar_ok
        )

        cross_count = self._count_cross_source_sentences(draft)
        logger.info(
            "[quality-gate] words=%d cites=%d flags=%d/%d "
            "parrot=%.2f(count=%d) echo=%d grammar=%d "
            "cross_sents=%d → %s",
            words, cite_count, passing, len(required_flags),
            parroting, parroted_count, echo_count, grammar_issues,
            cross_count,
            "PASS" if gate_pass else "FAIL",
        )

        if gate_pass:
            return draft

        # CRITICAL-2: GTA re-attribution at lower threshold when
        # only citation count fails — no LLM retry needed
        if _GTA_ENABLED and cite_count < 5:
            other_checks_pass = (
                words >= 500
                and passing >= min(4, len(required_flags))
                and parrot_ok
                and echo_ok
                and grammar_ok
            )
            if other_checks_pass:
                lower_threshold = max(
                    sim_threshold - 0.10, 0.15,
                ) if (
                    sim_threshold := _GTA_THRESHOLD
                ) else 0.25
                # Strip existing citations and re-attribute
                draft_clean = re.sub(
                    r'\[CITE:ev_[a-f0-9]+\]', '', draft,
                )
                draft = self._attribute_citations(
                    draft_clean,
                    threshold_override=_GTA_THRESHOLD - 0.10,
                )
                new_cites = len(
                    re.findall(
                        r'\[CITE:ev_[a-f0-9]+\]', draft,
                    ),
                )
                logger.info(
                    "[quality-gate] GTA re-attribution at "
                    "threshold=%.2f: %d -> %d cites",
                    _GTA_THRESHOLD - 0.10, cite_count,
                    new_cites,
                )
                if new_cites >= 5:
                    return draft

        # Budget check: need 90s for retry (WP-4: lowered from 180s)
        pipeline_timeout = int(
            resolve("PG_REACT_TIMEOUT_SECONDS"),
        )
        elapsed = time.monotonic() - start_time
        if elapsed > pipeline_timeout - 90:
            logger.warning(
                "[quality-gate] FAIL but no budget for retry "
                "(%.0fs elapsed, need 90s)",
                elapsed,
            )
            # WP-2.1 (CRITICAL-2): Scrub echoes before returning
            # when no retry budget — removing broken sentences is
            # better than keeping them
            if echo_count >= 2:
                for p in _echo_patterns:
                    for m in re.finditer(
                        r'[^.!?\n]*' + p + r'[^.!?\n]*[.!?]',
                        draft, re.IGNORECASE,
                    ):
                        draft = draft.replace(m.group(), '', 1)
                draft = re.sub(r'  +', ' ', draft)
                draft = re.sub(r'\n\s*\n\s*\n', '\n\n', draft)
                logger.info(
                    "[quality-gate] Scrubbed %d echo sentences "
                    "(no retry budget)", echo_count,
                )
            return draft

        # Retry with different temperature
        logger.info(
            "[quality-gate] Retrying write at temperature=0.5 "
            "(%.0fs remaining)",
            pipeline_timeout - elapsed,
        )

        # Wave 2+3: Retry uses same RCS + cross-source prompting
        retry_cross = self._build_cross_source_synthesis_pairs(briefing)
        # D3+D4: Re-inject structural enforcement on retry
        retry_numbers = self._build_mandatory_numbers_section()
        retry_coverage = self._build_perspective_coverage_section(briefing)
        if _HYBRID_EVIDENCE:
            prompt = (
                f"You are a senior research analyst. Expand "
                f"this analytical scaffold into publication-"
                f"quality prose (800-1500 words).\n\n"
                f"RESEARCH QUESTION: {self._query}\n\n"
                f"ANALYTICAL SCAFFOLD:\n{scaffold}\n\n"
                f"EVIDENCE PASSAGES:\n{cluster_summary}\n\n"
                f"CROSS-SOURCE COMPARISONS:\n"
                f"{retry_cross}\n\n"
                f"{retry_numbers}"
                f"{retry_coverage}"
                f"RULES:\n"
                f"1. Cite by passage number [N]\n"
                f"2. Synthesize — do NOT copy\n"
                f"3. Cross-source: compare both sources\n"
                f"4. Comparative language\n"
                f"5. Preserve exact units\n"
                f"6. Evidence-based ranking\n"
                f"7. Explicit trade-offs\n"
                f"8. Executive summary first\n"
                f"9. Conditional recs: **If** X **then** Y "
                f"**because** Z [N]\n"
                f"10. At least 2 criteria per paragraph\n"
                f"11. At least 5 numerical values with units\n"
                f"{gap_context}"
            )
            retry_system = (
                "Cite by passage number [N]. Synthesize — "
                "do not copy. Be analytical."
            )
        elif _GTA_ENABLED:
            prompt = (
                f"You are a senior research analyst. Expand this "
                f"analytical scaffold into publication-quality "
                f"prose (800-1500 words).\n\n"
                f"RESEARCH QUESTION: {self._query}\n\n"
                f"ANALYTICAL SCAFFOLD:\n{scaffold}\n\n"
                f"ANALYTICAL CLAIMS:\n{cluster_summary}\n\n"
                f"CROSS-SOURCE DIRECTIVES:\n{retry_cross}\n\n"
                f"{retry_numbers}"
                f"{retry_coverage}"
                f"RULES:\n"
                f"1. Write analytical prose — do NOT include "
                f"citation markers\n"
                f"2. Never restate a claim question — ANSWER it\n"
                f"3. Cross-source: compare 2+ sources per "
                f"directive\n"
                f"4. Comparative language (whereas, in contrast)\n"
                f"5. Preserve exact units\n"
                f"6. Evidence-based ranking\n"
                f"7. Explicit trade-offs\n"
                f"8. Executive summary first paragraph\n"
                f"9. Conditional recs: **If** X **then** Y "
                f"**because** Z\n"
                f"10. Every body paragraph MUST discuss at least "
                f"2 criteria (cost, performance, mechanism, "
                f"limitation, application)\n"
                f"11. Include at least 5 numerical values with "
                f"units from evidence — use exact values\n"
                f"{gap_context}"
            )
            retry_system = (
                "ANSWER analytical claims — do not restate. "
                "Do NOT include citation markers. "
                "Write cross-source sentences. Be analytical."
            )
        else:
            prompt = (
                f"You are a senior research analyst. Expand this "
                f"analytical scaffold into publication-quality "
                f"prose (800-1500 words).\n\n"
                f"RESEARCH QUESTION: {self._query}\n\n"
                f"ANALYTICAL SCAFFOLD:\n{scaffold}\n\n"
                f"ANALYTICAL CLAIMS:\n{cluster_summary}\n\n"
                f"CROSS-SOURCE DIRECTIVES:\n{retry_cross}\n\n"
                f"{retry_numbers}"
                f"{retry_coverage}"
                f"RULES:\n"
                f"1. Cite EVERY numerical value with "
                f"[CITE:ev_xxx]\n"
                f"2. Never restate a claim question — ANSWER it\n"
                f"3. Cross-source: cite 2+ sources per "
                f"directive\n"
                f"4. Comparative language (whereas, in contrast)\n"
                f"5. Preserve exact units\n"
                f"6. Evidence-based ranking\n"
                f"7. Explicit trade-offs\n"
                f"8. Executive summary first paragraph\n"
                f"9. Conditional recs: **If** X **then** Y "
                f"**because** Z [CITE:ev_xxx]\n"
                f"10. Every body paragraph MUST discuss at least "
                f"2 criteria (cost, performance, mechanism, "
                f"limitation, application)\n"
                f"11. Include at least 5 numerical values with "
                f"units from evidence — use exact values, do "
                f"not paraphrase numbers\n"
                f"{gap_context}"
            )
            retry_system = (
                "ANSWER analytical claims — do not restate. "
                "Every claim must have [CITE:ev_xxx]. "
                "Write cross-source sentences. Be analytical."
            )

        try:
            retry_response = await asyncio.wait_for(
                self._client.generate(
                    prompt=prompt,
                    system=retry_system,
                    max_tokens=8192,
                    temperature=0.5,
                    timeout=write_timeout,
                ),
                timeout=write_timeout + 30,
            )
            retry_draft = retry_response.content.strip()
        except Exception as exc:
            logger.warning(
                "[quality-gate] Retry write failed: %s: %s",
                type(exc).__name__, str(exc)[:100],
            )
            return draft

        if not retry_draft or len(retry_draft) < 100:
            return draft

        # Hybrid: map passage numbers on retry draft
        if _HYBRID_EVIDENCE and self._passage_reverse_map:
            retry_draft = self._map_passage_citations(
                retry_draft, self._passage_reverse_map,
            )
        # GTA: attribute citations on retry draft
        if _GTA_ENABLED:
            retry_draft = self._attribute_citations(retry_draft)

        # Pick better draft by gate score
        retry_words = len(retry_draft.split())
        retry_cites = len(
            re.findall(r'\[CITE:ev_[a-f0-9]+\]', retry_draft),
        )
        retry_parrot, _ = self._compute_parroting_ratio(retry_draft)

        original_score = words + cite_count * 10 - parroting * 100
        retry_score = (
            retry_words + retry_cites * 10 - retry_parrot * 100
        )

        best_draft = (
            retry_draft if retry_score > original_score else draft
        )
        if retry_score > original_score:
            logger.info(
                "[quality-gate] Retry draft better: score %.0f > %.0f",
                retry_score, original_score,
            )
        else:
            logger.info(
                "[quality-gate] Original draft kept: score %.0f >= %.0f",
                original_score, retry_score,
            )

        # Bug-1 fix: Strip phantom citations from best_draft
        # (first draft was cleaned, but retry draft may have new ones)
        best_draft = self._strip_phantom_citations(best_draft)

        # WP-4: Fast-path emergency retry for severely underdeveloped
        # outputs (< 2500 chars). Uses shorter scaffold-only prompt
        # with max_tokens=4096 for a quick but complete output.
        # Runs even when retry was "better" — if both are short, the
        # simpler prompt may produce a longer, more complete output.
        if len(best_draft) < 2500:
            remaining = pipeline_timeout - (
                time.monotonic() - start_time
            )
            if remaining > 45:
                logger.info(
                    "[quality-gate] Emergency fast-path retry "
                    "(%d chars < 2500, %.0fs remaining)",
                    len(best_draft), remaining,
                )
                if _GTA_ENABLED:
                    fast_prompt = (
                        f"Write a comprehensive analytical "
                        f"report (800+ words) answering:\n\n"
                        f"RESEARCH QUESTION: {self._query}\n\n"
                        f"ANALYTICAL SCAFFOLD:\n{scaffold}\n\n"
                        f"Be thorough and specific. Do NOT "
                        f"include citation markers."
                    )
                else:
                    fast_prompt = (
                        f"Write a comprehensive analytical "
                        f"report (800+ words) answering:\n\n"
                        f"RESEARCH QUESTION: {self._query}\n\n"
                        f"ANALYTICAL SCAFFOLD:\n{scaffold}\n\n"
                        f"Cite every claim with [CITE:ev_xxx]. "
                        f"Be thorough and specific."
                    )
                fast_system = (
                    "Senior research analyst. Write analytical "
                    "prose without citation markers."
                    if _GTA_ENABLED
                    else "Senior research analyst. Cite all claims."
                )
                try:
                    fast_resp = await asyncio.wait_for(
                        self._client.generate(
                            prompt=fast_prompt,
                            system=fast_system,
                            max_tokens=4096,
                            temperature=0.3,
                            timeout=min(int(remaining) - 10, 60),
                        ),
                        timeout=min(remaining - 5, 65),
                    )
                    fast_draft = fast_resp.content.strip()
                    if fast_draft and len(fast_draft) > len(best_draft):
                        # GTA: attribute citations on fast-path
                        if _GTA_ENABLED:
                            fast_draft = self._attribute_citations(
                                fast_draft,
                            )
                        # Bug-1 fix: also clean fast-path draft
                        fast_draft = self._strip_phantom_citations(
                            fast_draft,
                        )
                        logger.info(
                            "[quality-gate] Fast-path produced "
                            "%d chars (was %d)",
                            len(fast_draft), len(best_draft),
                        )
                        return fast_draft
                except Exception as exc:
                    logger.warning(
                        "[quality-gate] Fast-path failed: %s",
                        str(exc)[:80],
                    )

        return best_draft

    def _strip_phantom_citations(self, text: str) -> str:
        """Remove citation tokens whose IDs are not in the evidence store.

        Phantom citations are NEVER valid — they reference non-existent
        evidence. Safe to run unconditionally on any draft.
        """
        all_cited = set(re.findall(r'\[CITE:([^\]]+)\]', text))
        phantoms = [
            c for c in all_cited if c not in self._evidence_store
        ]
        if phantoms:
            for cid in phantoms:
                text = text.replace(f"[CITE:{cid}]", "")
            text = re.sub(r'\s*,\s*\.', '.', text)
            text = re.sub(r'\s+\.', '.', text)
            logger.info(
                "[quality-gate] Stripped %d phantom citations: %s",
                len(phantoms),
                ", ".join(p[:16] for p in phantoms[:5]),
            )
        return text

    def _compute_parroting_ratio(
        self, text: str,
    ) -> tuple[float, int]:
        """Compute 3-gram Jaccard overlap between text and evidence.

        Wave 4 (DEER + PlagBench):
        - Domain-term exclusion: filter common domain words before
          building n-grams to focus Jaccard on structural words.
        - Cited-evidence-only: only check evidence IDs that appear as
          [CITE:ev_xxx] in the sentence (DEER backreference pattern).
        - Lower threshold: 0.50 → 0.35 (after domain exclusion).

        Returns:
            Tuple of (ratio, absolute_count) where ratio is
            parroted/checked and absolute_count is the raw number
            of parroted sentences.
        """
        sentences = re.split(r'[.!?]\s+', text)
        if not sentences:
            return 0.0, 0

        cite_re = re.compile(r'\[CITE:(ev_[a-f0-9]+)\]')
        # W4: configurable parroting Jaccard threshold
        jaccard_threshold = float(
            resolve("PG_PARROTING_JACCARD_THRESHOLD"),
        )
        parroted = 0
        checked = 0
        for sent in sentences:
            # Domain-term exclusion: filter before n-gram construction
            sent_words = [
                w for w in re.findall(r'[a-z]{4,}', sent.lower())
                if w not in _DOMAIN_TERMS
            ]
            if len(sent_words) < 5:
                continue
            checked += 1
            # Build 3-grams
            sent_ngrams = set()
            for i in range(len(sent_words) - 2):
                sent_ngrams.add(
                    (sent_words[i], sent_words[i + 1], sent_words[i + 2]),
                )
            if not sent_ngrams:
                continue

            # DEER: only check evidence cited in THIS sentence
            cited_eids = cite_re.findall(sent)
            check_eids = cited_eids if cited_eids else (
                self._evidence_ids[:100]
            )

            for eid in check_eids:
                ev = self._evidence_store.get(eid, {})
                ev_stmt = ev.get("statement", "")
                ev_words = [
                    w for w in re.findall(r'[a-z]{4,}', ev_stmt.lower())
                    if w not in _DOMAIN_TERMS
                ]
                ev_ngrams = set()
                for i in range(len(ev_words) - 2):
                    ev_ngrams.add(
                        (ev_words[i], ev_words[i + 1], ev_words[i + 2]),
                    )
                if not ev_ngrams:
                    continue
                overlap = len(sent_ngrams & ev_ngrams)
                union = len(sent_ngrams | ev_ngrams)
                if union > 0 and overlap / union > jaccard_threshold:
                    parroted += 1
                    break

        return parroted / max(checked, 1), parroted

    # -------------------------------------------------------------------
    # Wave 4: Structural sentence rewrite (replaces framing prefix)
    # -------------------------------------------------------------------

    @staticmethod
    def _structural_rewrite(sentence: str) -> str:
        """Rewrite a parroted sentence using structural transforms.

        Wave 4 (Process-Supervised Rewrite, arxiv:2509.15577):
        Two reliable transforms:
        B — Numeric Foregrounding: move number+unit to sentence start
        D — Causal Inversion: swap cause and effect clauses

        Citation positions are preserved via placeholder swap.
        """
        # Step 1: Protect citations with placeholders
        cite_re = re.compile(r'\[CITE:ev_[a-f0-9]+\]')
        cites = cite_re.findall(sentence)
        working = sentence
        placeholders = []
        for i, cite in enumerate(cites):
            placeholder = f"__CITE_{i}__"
            placeholders.append((placeholder, cite))
            working = working.replace(cite, placeholder, 1)

        rewritten = working

        # Transform B: Numeric Foregrounding (WP-1.1: gated, default OFF)
        # Creates defects A2 ("2 GPa" orphan), A3 ("99.Achieving 0%").
        # Disabled by default; re-enable via PG_TRANSFORM_B_ENABLED=1.
        _transform_b = resolve("PG_TRANSFORM_B_ENABLED") == "1"
        if _transform_b:
            num_match = re.search(
                r'(\d+\.?\d*)\s*(%|mg/[Ll]|ppt|ppb|ppm|µm|nm|mm|cm|'
                r'\$|kWh|MWh|MPa|GPa|°C|[Ll]/min|m³/h)',
                working,
            )
        else:
            num_match = None

        if num_match:
            number = num_match.group(1)
            unit = num_match.group(2)

            # Determine preposition based on unit
            if unit == "$":
                preposition = f"At a cost of ${number}"
            elif unit == "%":
                preposition = f"Achieving {number}%"
            else:
                preposition = f"At {number} {unit}"

            # Lowercase the original sentence and prepend
            body = working
            if body and body[0].isupper():
                body = body[0].lower() + body[1:]
            # Strip terminal punctuation from body for clean join
            body = body.rstrip(".")
            rewritten = f"{preposition}, {body}."

        elif re.search(
            r'\bbecause\b|\bdue to\b|\bresulting from\b',
            working, re.IGNORECASE,
        ):
            # Transform D: Causal Inversion
            # "X is effective because Y" → "Y leads to effective X"
            causal_match = re.search(
                r'^(.*?)\s+(?:because|due to|resulting from)\s+(.+)$',
                working, re.IGNORECASE,
            )
            if causal_match:
                result_clause = causal_match.group(1).strip()
                cause_clause = causal_match.group(2).strip()
                # Capitalize cause, lowercase result
                if cause_clause and cause_clause[0].islower():
                    cause_clause = (
                        cause_clause[0].upper() + cause_clause[1:]
                    )
                if result_clause and result_clause[0].isupper():
                    result_clause = (
                        result_clause[0].lower() + result_clause[1:]
                    )
                # Remove terminal punctuation from cause for joining
                cause_clause = cause_clause.rstrip(".,;:")
                rewritten = (
                    f"{cause_clause}, leading to {result_clause}"
                )
                if rewritten and rewritten[-1] not in ".!?":
                    rewritten += "."
        else:
            # Transform E: Active-to-passive voice rewrite (R7)
            # "The study shows significant improvement" →
            # "Significant improvement is shown by the study"
            #
            # Uses verb whitelist to avoid misidentifying nouns/
            # adjectives as verbs. Only fires when the captured
            # word is a known transitive verb.
            active_match = re.match(
                r'^((?:The|A|An|This|These|Each|Every)\s+'
                r'(?:\w+\s+)*?\w+)'
                r'\s+(\w+s)\s+(.+?)([.!?])$',
                working, re.IGNORECASE,
            )
            passive_applied = False
            if active_match:
                subject = active_match.group(1).strip()
                verb_raw = active_match.group(2).strip()
                obj_phrase = active_match.group(3).strip()
                terminal = active_match.group(4)

                # Validate: verb must be a known transitive verb
                verb_lower = verb_raw.lower()
                verb_stem = verb_lower.rstrip("s")
                # Also handle -es: "produces" → "produce"
                if verb_stem.endswith("e") and verb_lower.endswith(
                    "es",
                ):
                    verb_stem_alt = verb_stem
                else:
                    verb_stem_alt = None

                if verb_stem in _R7_TRANSITIVE_VERBS or (
                    verb_stem_alt
                    and verb_stem_alt in _R7_TRANSITIVE_VERBS
                ):
                    # Derive past participle
                    lookup = verb_stem
                    if (
                        lookup not in _R7_IRREGULAR_PP
                        and verb_stem_alt
                        and verb_stem_alt in _R7_IRREGULAR_PP
                    ):
                        lookup = verb_stem_alt
                    if lookup in _R7_IRREGULAR_PP:
                        pp = _R7_IRREGULAR_PP[lookup]
                    elif lookup.endswith("e"):
                        pp = lookup + "d"
                    else:
                        pp = lookup + "ed"

                    # Capitalize object, lowercase subject
                    if obj_phrase and obj_phrase[0].islower():
                        obj_phrase = (
                            obj_phrase[0].upper()
                            + obj_phrase[1:]
                        )
                    subj_lower = subject
                    if subj_lower and subj_lower[0].isupper():
                        subj_lower = (
                            subj_lower[0].lower()
                            + subj_lower[1:]
                        )

                    # WS-2 Fix A: Extract trailing adverbs from
                    # object phrase before building passive.
                    # "harmful pollutants effectively" →
                    # adverb "effectively" repositioned after aux.
                    obj_words = obj_phrase.rstrip(
                        ".,;:!? ",
                    ).split()
                    trailing_advs: list[str] = []
                    while (
                        obj_words
                        and obj_words[-1].lower().endswith("ly")
                        and len(obj_words[-1]) > 3
                        and obj_words[-1].lower()
                        not in _R7_SINGULAR_S
                    ):
                        trailing_advs.insert(0, obj_words.pop())
                    obj_phrase_clean = " ".join(obj_words)
                    if not obj_phrase_clean:
                        obj_phrase_clean = obj_phrase.rstrip(
                            ".,;:!? ",
                        )
                        trailing_advs = []
                    adv_str = (
                        " " + " ".join(trailing_advs)
                        if trailing_advs else ""
                    )

                    # WS-2 Fix B: Plural check on cleaned phrase.
                    # After extracting trailing adverbs, the LAST
                    # word of the clean phrase is the grammatical
                    # head (original heuristic, now safe from
                    # adverb interference).
                    aux = "is"
                    clean_words = obj_phrase_clean.split()
                    if clean_words:
                        last_w = clean_words[-1].lower().rstrip(
                            ".,;:!? ",
                        )
                        if (
                            last_w.endswith("s")
                            and last_w not in _R7_SINGULAR_S
                        ):
                            aux = "are"

                    rewritten = (
                        f"{obj_phrase_clean} {aux}{adv_str} "
                        f"{pp} by {subj_lower}{terminal}"
                    )
                    passive_applied = True

            if not passive_applied:
                # Fallback: try to extract any number and foreground
                # WP-1.1: Gated same as primary Transform B
                if _transform_b:
                    any_num = re.search(
                        r'(\d+\.?\d*)\s*'
                        r'(%|mg|ppt|ppb|ppm|µm|nm|\$|kWh|MPa|°C)',
                        working,
                    )
                else:
                    any_num = None
                if any_num:
                    number = any_num.group(1)
                    unit = any_num.group(2)
                    rest = working.replace(
                        any_num.group(0), "", 1,
                    ).strip()
                    rest = re.sub(r'^(?:,\s*|\s+)', '', rest)
                    if rest and rest[0].isupper():
                        rest = rest[0].lower() + rest[1:]
                    rewritten = f"With {number} {unit}, {rest}"
                    if rewritten and rewritten[-1] not in ".!?":
                        rewritten += "."

        # Step 3: Restore citations from placeholders
        for placeholder, cite in placeholders:
            rewritten = rewritten.replace(placeholder, cite)

        return rewritten

    @staticmethod
    def _synonym_rewrite(sentence: str, max_swaps: int = 3) -> str:
        """P1: Synonym substitution for parroting mitigation.

        BloomScrub pattern (arxiv:2504.16046): replace non-technical
        connectors/adverbs with synonyms to reduce embedding similarity
        while preserving domain meaning.

        CR2: Only non-technical terms are swapped. Domain terms
        (removal, concentration, treatment, etc.) are never changed.
        """
        # Skip verbatim-required sentences (patents, dollar figures, etc.)
        if _VERBATIM_REQUIRED.search(sentence):
            return sentence

        # Step 1: Protect citations with placeholders
        cite_re = re.compile(r'\[CITE:ev_[a-f0-9]+\]')
        cites = cite_re.findall(sentence)
        working = sentence
        cite_placeholders = []
        for i, cite in enumerate(cites):
            placeholder = f"__SYN_CITE_{i}__"
            cite_placeholders.append((placeholder, cite))
            working = working.replace(cite, placeholder, 1)

        # Step 2: Apply synonym substitutions (case-preserving)
        swaps = 0
        words = working.split()
        for wi, word in enumerate(words):
            if swaps >= max_swaps:
                break
            # Strip punctuation for lookup
            clean = word.strip(".,;:!?()[]\"'")
            lower = clean.lower()
            if lower in _SYNONYM_TABLE:
                replacement = _SYNONYM_TABLE[lower]
                # Preserve capitalization
                if clean[0].isupper():
                    replacement = replacement[0].upper() + replacement[1:]
                # Preserve surrounding punctuation
                words[wi] = word.replace(clean, replacement, 1)
                swaps += 1

        if swaps == 0:
            return sentence

        result = " ".join(words)

        # Step 3: Restore citations
        for placeholder, cite in cite_placeholders:
            result = result.replace(placeholder, cite)

        return result

    # -------------------------------------------------------------------
    # Generate-Then-Attribute: programmatic citation placement
    # -------------------------------------------------------------------

    def _attribute_citations(
        self,
        text: str,
        threshold_override: float | None = None,
    ) -> str:
        """Add citations at sentence boundaries using 3-strategy matching.

        Generate-Then-Attribute pattern (ACL 2024-2026): LLM writes clean
        prose, citations placed programmatically using number matching,
        keyword overlap, and embedding similarity.

        Strategies (descending priority):
        1. Number match: sentence number matches evidence number
        2. Keyword overlap: 3+ content words shared with evidence
        3. Embedding similarity: cosine sim >= threshold (fallback)

        Citations placed at sentence boundary (before period).
        Skips non-prose lines: tables, images, code blocks, headers.

        Args:
            text: Citation-free prose from LLM.
            threshold_override: Override embedding threshold (for
                quality gate re-attribution at lower threshold).

        Returns:
            Text with [CITE:ev_xxx] at sentence boundaries.
        """
        if not self._evidence_store:
            return text

        sim_threshold = (
            threshold_override
            if threshold_override is not None
            else _GTA_THRESHOLD
        )
        max_per_sent = _GTA_MAX_PER_SENTENCE
        keyword_min = _GTA_KEYWORD_MIN

        # Build evidence lookup structures
        all_eids = list(self._evidence_store.keys())
        all_stmts = [
            self._evidence_store[eid].get("statement", "")
            for eid in all_eids
        ]

        # Pre-extract numbers from each evidence (filter trivial 0-9)
        ev_numbers: dict[str, set[str]] = {}
        for eid, stmt in zip(all_eids, all_stmts):
            ev_numbers[eid] = {
                n for n in re.findall(r'\d+\.?\d*', stmt)
                if len(n) >= 2 or float(n) >= 10
            }

        # Pre-extract content words from each evidence
        _stopwords = frozenset({
            "the", "and", "for", "with", "from", "that", "this",
            "was", "were", "are", "been", "have", "has", "had",
            "not", "but", "which", "their", "they", "than",
            "can", "its", "also", "into", "more", "such",
            "about", "through", "between", "after", "before",
            "would", "could", "should", "will", "does", "did",
            "being", "each", "other", "some", "what", "when",
            "where", "while",
        })
        ev_words: dict[str, set[str]] = {}
        for eid, stmt in zip(all_eids, all_stmts):
            ev_words[eid] = {
                w for w in re.findall(r'[a-z]{4,}', stmt.lower())
                if w not in _stopwords
            }

        # Build embedding matrix lazily (only if needed)
        _ev_emb_matrix = None
        _ev_emb_norms = None

        def _get_ev_embeddings():
            nonlocal _ev_emb_matrix, _ev_emb_norms
            if _ev_emb_matrix is None:
                try:
                    embs = embed_texts(all_stmts)
                    _ev_emb_matrix = np.array(embs)
                    norms = np.linalg.norm(
                        _ev_emb_matrix, axis=1, keepdims=True,
                    )
                    _ev_emb_norms = _ev_emb_matrix / np.maximum(
                        norms, 1e-8,
                    )
                except Exception:
                    logger.debug(
                        "[GTA] embed_texts failed for evidence",
                        exc_info=True,
                    )
                    _ev_emb_matrix = np.zeros((0, 0))
                    _ev_emb_norms = np.zeros((0, 0))
            return _ev_emb_norms

        # Process text line by line
        output_lines = []
        in_code_block = False
        total_cites_added = 0

        for line in text.split("\n"):
            stripped = line.strip()

            # Toggle code block state
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                output_lines.append(line)
                continue

            # Skip non-prose lines (CRITICAL-6 fix)
            if (
                in_code_block
                or stripped.startswith("|")       # tables
                or stripped.startswith("!")        # images
                or stripped.startswith("#")        # headers
                or stripped.startswith("-")        # list items
                or stripped.startswith("*")        # list items
                or not stripped                    # empty
            ):
                output_lines.append(line)
                continue

            # Split line into sentences
            # Match sentence-ending punctuation while preserving
            # the structure for reassembly
            parts = re.split(r'([.!?](?:\s|$))', line)

            rebuilt = ""
            i = 0
            while i < len(parts):
                fragment = parts[i]
                # Check if next part is the delimiter
                delim = parts[i + 1] if i + 1 < len(parts) else ""
                sentence = fragment + delim

                if len(fragment.split()) < 3:
                    # Too short to be a meaningful sentence
                    rebuilt += sentence
                    i += 2 if delim else 1
                    continue

                # Find matching evidence for this sentence
                matched_eids: list[str] = []
                sent_lower = fragment.lower()

                # Strategy 1: Number matching (highest priority)
                # Filter out trivially common numbers (0-9)
                sent_nums = {
                    n for n in re.findall(r'\d+\.?\d*', fragment)
                    if len(n) >= 2 or float(n) >= 10
                }
                if sent_nums:
                    for eid in all_eids:
                        shared = sent_nums & ev_numbers[eid]
                        if shared and eid not in matched_eids:
                            matched_eids.append(eid)
                            if len(matched_eids) >= max_per_sent:
                                break

                # Strategy 2: Keyword overlap
                if len(matched_eids) < max_per_sent:
                    sent_words = {
                        w for w in re.findall(
                            r'[a-z]{4,}', sent_lower,
                        )
                        if w not in _stopwords
                    }
                    if sent_words:
                        kw_candidates: list[tuple[int, str]] = []
                        for eid in all_eids:
                            if eid in matched_eids:
                                continue
                            overlap = len(sent_words & ev_words[eid])
                            if overlap >= keyword_min:
                                kw_candidates.append((overlap, eid))
                        # Sort by overlap descending
                        kw_candidates.sort(reverse=True)
                        for _, eid in kw_candidates:
                            if eid not in matched_eids:
                                matched_eids.append(eid)
                                if len(matched_eids) >= max_per_sent:
                                    break

                # Strategy 3: Embedding similarity (fallback)
                if (
                    len(matched_eids) < max_per_sent
                    and len(fragment.split()) >= 5
                ):
                    ev_normed = _get_ev_embeddings()
                    if ev_normed.size > 0:
                        try:
                            sent_emb = np.array(
                                embed_texts([fragment]),
                            )
                            sent_norm = np.linalg.norm(
                                sent_emb, axis=1, keepdims=True,
                            )
                            sent_normed = sent_emb / np.maximum(
                                sent_norm, 1e-8,
                            )
                            sims = (sent_normed @ ev_normed.T)[0]
                            top_indices = np.argsort(sims)[::-1]
                            for si in top_indices:
                                if sims[si] < sim_threshold:
                                    break
                                eid = all_eids[si]
                                if eid not in matched_eids:
                                    matched_eids.append(eid)
                                    if (
                                        len(matched_eids)
                                        >= max_per_sent
                                    ):
                                        break
                        except Exception:
                            logger.debug(
                                "[GTA] Embedding match failed "
                                "for sentence",
                                exc_info=True,
                            )

                # Place citations at sentence boundary
                if matched_eids and delim:
                    cite_str = "".join(
                        f"[CITE:{eid}]"
                        for eid in matched_eids[:max_per_sent]
                    )
                    # Insert before the period/punctuation
                    rebuilt += fragment.rstrip() + " " + cite_str
                    rebuilt += delim
                    total_cites_added += len(
                        matched_eids[:max_per_sent],
                    )
                else:
                    rebuilt += sentence

                i += 2 if delim else 1

            output_lines.append(rebuilt)

        result = "\n".join(output_lines)
        logger.info(
            "[GTA] Attribution complete: %d citations added "
            "(threshold=%.2f)",
            total_cites_added, sim_threshold,
        )
        return result

    # -------------------------------------------------------------------
    # WS-5: CiteFix citation correction (ACL 2025 Industry)
    # -------------------------------------------------------------------

    def _fix_citations(self, text: str) -> str:
        """Correct misattributed citations using 3 strategies.

        ACL 2025 finding: 80% of "hallucinations" in RAG are incorrect
        citations, not fabricated facts. This method verifies each
        citation against its surrounding context and swaps to the best
        matching evidence when the original is wrong.

        Strategies (sequential, first match wins):
        1. Keyword matching: 3+ content words shared in 2-sentence window
        2. Semantic matching: embedding similarity > 0.50
        3. Number matching: numbers near citation must appear in evidence

        MODERATE-1 guard: P7 swaps are tracked and skipped to avoid
        undoing correct number-based fixes.
        """
        cite_pattern = re.compile(r'\[CITE:(ev_[a-f0-9]+)\]')
        all_cites = list(cite_pattern.finditer(text))
        if not all_cites:
            return text

        # Collect citation contexts: (eid, context_window, match_obj)
        cite_contexts: list[tuple[str, str, re.Match]] = []
        for cm in all_cites:
            eid = cm.group(1)
            if eid not in self._evidence_store:
                continue
            # 2-sentence window around citation
            sent_start = text.rfind('.', 0, cm.start())
            sent_start = sent_start + 1 if sent_start >= 0 else 0
            # Look for 2 sentence ends after citation
            first_end = text.find('.', cm.end())
            if first_end >= 0:
                second_end = text.find('.', first_end + 1)
                sent_end = (
                    second_end + 1 if second_end >= 0
                    else first_end + 1
                )
            else:
                sent_end = len(text)
            ctx_window = text[sent_start:sent_end].strip()
            if len(ctx_window) < 10:
                continue
            cite_contexts.append((eid, ctx_window, cm))

        if not cite_contexts:
            return text

        # Strategy 1: Keyword matching
        swaps: list[tuple[str, str]] = []  # (old_eid, new_eid)
        unresolved_indices: list[int] = []
        _stopwords = frozenset({
            "the", "and", "for", "with", "from", "that", "this",
            "was", "were", "are", "been", "have", "has", "had",
            "not", "but", "which", "their", "they", "than",
            "can", "its", "also", "into", "more", "such",
        })

        for idx, (eid, ctx, _cm) in enumerate(cite_contexts):
            ev = self._evidence_store.get(eid, {})
            ev_stmt = ev.get("statement", "").lower()
            ctx_lower = ctx.lower()

            # Extract content words (4+ chars, not stopwords)
            ctx_words = {
                w for w in re.findall(r'[a-z]{4,}', ctx_lower)
                if w not in _stopwords
            }
            ev_words = {
                w for w in re.findall(r'[a-z]{4,}', ev_stmt)
                if w not in _stopwords
            }
            overlap = ctx_words & ev_words

            if len(overlap) >= _CITEFIX_KEYWORD_MIN:
                continue  # Citation matches — no fix needed

            # Search all evidence for a better keyword match
            best_eid = None
            best_overlap = 0
            for cand_eid, cand_ev in self._evidence_store.items():
                if cand_eid == eid:
                    continue
                cand_stmt = cand_ev.get("statement", "").lower()
                cand_words = {
                    w for w in re.findall(r'[a-z]{4,}', cand_stmt)
                    if w not in _stopwords
                }
                cand_overlap = len(ctx_words & cand_words)
                if cand_overlap >= _CITEFIX_KEYWORD_MIN and (
                    cand_overlap > best_overlap
                ):
                    best_eid = cand_eid
                    best_overlap = cand_overlap

            if best_eid:
                swaps.append((eid, best_eid))
            else:
                unresolved_indices.append(idx)

        # Strategy 2: Semantic matching for unresolved citations
        if unresolved_indices and len(unresolved_indices) <= 50:
            try:
                unresolved_ctx = [
                    cite_contexts[i][1] for i in unresolved_indices
                ]
                unresolved_eids = [
                    cite_contexts[i][0] for i in unresolved_indices
                ]
                # Get all evidence statements
                all_ev_ids = list(self._evidence_store.keys())
                all_ev_stmts = [
                    self._evidence_store[eid_k].get("statement", "")
                    for eid_k in all_ev_ids
                ]
                # Batch embed
                all_texts = unresolved_ctx + all_ev_stmts
                all_embs = embed_texts(all_texts)
                n_ctx = len(unresolved_ctx)
                ctx_embs = np.array(all_embs[:n_ctx])
                ev_embs = np.array(all_embs[n_ctx:])
                # Cosine similarity matrix
                ctx_norms = np.linalg.norm(ctx_embs, axis=1, keepdims=True)
                ev_norms = np.linalg.norm(ev_embs, axis=1, keepdims=True)
                ctx_normed = ctx_embs / np.maximum(ctx_norms, 1e-8)
                ev_normed = ev_embs / np.maximum(ev_norms, 1e-8)
                sim_matrix = ctx_normed @ ev_normed.T

                still_unresolved: list[int] = []
                for j, orig_idx in enumerate(unresolved_indices):
                    orig_eid = unresolved_eids[j]
                    sims = sim_matrix[j]
                    # Find best match that isn't the current citation
                    sorted_indices = np.argsort(sims)[::-1]
                    for si in sorted_indices:
                        cand_eid = all_ev_ids[si]
                        if cand_eid == orig_eid:
                            continue
                        if sims[si] >= _CITEFIX_SEMANTIC_THRESHOLD:
                            swaps.append((orig_eid, cand_eid))
                            break
                    else:
                        still_unresolved.append(orig_idx)

                # Strategy 3: Number matching for remaining
                for orig_idx in still_unresolved:
                    eid_3, ctx_3, _cm_3 = cite_contexts[orig_idx]
                    ctx_nums = set(re.findall(
                        r'\d+\.?\d*', ctx_3,
                    ))
                    if not ctx_nums:
                        continue
                    for cand_eid, cand_ev in self._evidence_store.items():
                        if cand_eid == eid_3:
                            continue
                        cand_stmt = cand_ev.get("statement", "")
                        cand_nums = set(re.findall(
                            r'\d+\.?\d*', cand_stmt,
                        ))
                        shared_nums = ctx_nums & cand_nums
                        if shared_nums:
                            swaps.append((eid_3, cand_eid))
                            break
            except Exception:
                logger.debug(
                    "[CiteFix] Semantic/number matching failed",
                    exc_info=True,
                )

        # Apply swaps (deduplicate: each citation swapped at most once)
        if swaps:
            applied = 0
            seen_swaps: set[str] = set()
            for old_eid, new_eid in swaps:
                if old_eid in seen_swaps:
                    continue
                old_cite = f"[CITE:{old_eid}]"
                new_cite = f"[CITE:{new_eid}]"
                if old_cite in text:
                    text = text.replace(old_cite, new_cite, 1)
                    seen_swaps.add(old_eid)
                    applied += 1
                    logger.info(
                        "[CiteFix] Swapped citation: %s -> %s",
                        old_eid[:16], new_eid[:16],
                    )
            if applied > 0:
                logger.info(
                    "[CiteFix] Corrected %d citations (%d candidates)",
                    applied, len(swaps),
                )

        return text

    # -------------------------------------------------------------------
    # Phase 6 (legacy): CRITIQUE — structured quality check
    # -------------------------------------------------------------------

    async def _critique_interpretation(
        self, interpretation: str, briefing: dict,
    ) -> dict | None:
        """Critique interpretation for analytical quality (Phase 6).

        Uses reason() to evaluate against 5 substance dimensions.
        Returns structured critique dict with pass/fail per dimension.
        """
        sub_questions = briefing.get("sub_questions", [])
        sq_text = "\n".join(f"  - {q}" for q in sub_questions)

        prompt = (
            f"RESEARCH QUESTION: {self._query}\n\n"
            f"SUB-QUESTIONS THE ANALYSIS SHOULD ADDRESS:\n{sq_text}\n\n"
            f"ANALYSIS TO CRITIQUE:\n{interpretation}\n\n"
            f"Evaluate this analysis on 5 dimensions. For each, state "
            f"whether it PASSES or FAILS and list specific issues:\n\n"
            f"1. sub_question_coverage: Does it address ALL sub-questions?\n"
            f"2. cross_source_synthesis: Are there sentences combining "
            f"2+ sources? (look for multiple [CITE:] in one sentence)\n"
            f"3. integration: For multi-criteria queries, are criteria "
            f"discussed TOGETHER (not in separate sections)?\n"
            f"4. evidence_grounding: Does every numerical claim have a "
            f"[CITE:ev_xxx]?\n"
            f"5. analytical_depth: Are there trade-off identifications, "
            f"conditional recommendations, gap analyses?\n\n"
            f"Then decide: needs_rewrite = true if <=3 dimensions pass.\n"
            f"If rewrite needed, provide specific fix instructions."
        )

        system = (
            "You are a research quality auditor. Be strict but fair. "
            "Return valid JSON matching the InterpretationCritique schema."
        )

        try:
            response = await asyncio.wait_for(
                self._client.reason(
                    prompt=prompt,
                    system=system,
                    schema=InterpretationCritique,
                    # I-arch-003 (#1253): reasoning effort to MAX (was medium). max_tokens routes through
                    # openrouter_client so the reasoning-first floor (>=4096/16384) applies.
                    effort=os.environ.get("PG_CRITIQUE_REASONING_EFFORT", "high") or "high",
                    # F23 (I-arch-004 A3): env-overridable audit-critique cap; default keeps the
                    # historical literal 2048 (byte-identical when unset). CAP not target (§9.1.8).
                    max_tokens=int(os.environ.get("PG_AUDIT_CRITIQUE_MAX_TOKENS", "2048")),
                    timeout=_CRITIQUE_TIMEOUT,
                ),
                timeout=_CRITIQUE_TIMEOUT + 15,
            )

            # Parse the response
            content = response.content.strip()
            if hasattr(response, "_parsed") and response._parsed:
                critique_obj = response._parsed
            else:
                # Try to parse JSON from content
                try:
                    critique_obj = InterpretationCritique.model_validate_json(
                        content,
                    )
                except Exception:
                    # Try extracting JSON from content
                    json_match = re.search(
                        r'\{[\s\S]*\}', content,
                    )
                    if json_match:
                        critique_obj = InterpretationCritique.model_validate_json(
                            json_match.group(),
                        )
                    else:
                        logger.warning(
                            "[8phase] Could not parse critique response",
                        )
                        return self._programmatic_critique(
                            interpretation, briefing,
                        )

            return critique_obj.model_dump()

        except Exception as exc:
            logger.warning(
                "[8phase] Critique failed: %s: %s, using programmatic",
                type(exc).__name__, str(exc)[:200],
            )
            return self._programmatic_critique(interpretation, briefing)

    def _programmatic_critique(
        self, interpretation: str, briefing: dict,
    ) -> dict:
        """Programmatic fallback critique when LLM critique fails.

        Checks the 5 dimensions using regex and counting.
        """
        dims = []

        # 1. Sub-question coverage
        sub_questions = briefing.get("sub_questions", [])
        covered = 0
        for sq in sub_questions:
            sq_words = set(
                w for w in sq.lower().split() if len(w) > 3
            )
            interp_lower = interpretation.lower()
            overlap = sum(1 for w in sq_words if w in interp_lower)
            if overlap >= 2:
                covered += 1
        coverage_ratio = covered / max(len(sub_questions), 1)
        dims.append({
            "dimension": "sub_question_coverage",
            "passed": coverage_ratio >= 0.6,
            "issues": (
                [f"Only {covered}/{len(sub_questions)} sub-questions addressed"]
                if coverage_ratio < 0.6 else []
            ),
        })

        # 2. Cross-source synthesis
        cross_count = 0
        for sentence in re.split(r'[.!?]\s+', interpretation):
            cites = set(re.findall(r'\[CITE:(ev_[a-f0-9]+)\]', sentence))
            if len(cites) >= 2:
                cross_count += 1
        dims.append({
            "dimension": "cross_source_synthesis",
            "passed": cross_count >= 3,
            "issues": (
                [f"Only {cross_count} cross-source sentences (need >=3)"]
                if cross_count < 3 else []
            ),
        })

        # 3. Integration (multi-criteria in same paragraph)
        paragraphs = [
            p.strip() for p in interpretation.split("\n\n") if p.strip()
        ]
        criteria_words = {
            "cost", "price", "expensive", "affordable",
            "effective", "efficiency", "removal", "performance",
        }
        integrated_paragraphs = 0
        for para in paragraphs:
            para_lower = para.lower()
            criteria_found = sum(
                1 for w in criteria_words if w in para_lower
            )
            if criteria_found >= 3:
                integrated_paragraphs += 1
        integration_ratio = integrated_paragraphs / max(len(paragraphs), 1)
        dims.append({
            "dimension": "integration",
            "passed": integration_ratio >= 0.2 or len(sub_questions) < 3,
            "issues": (
                [f"Only {integrated_paragraphs}/{len(paragraphs)} paragraphs "
                 f"integrate multiple criteria"]
                if integration_ratio < 0.2 and len(sub_questions) >= 3 else []
            ),
        })

        # 4. Evidence grounding
        # Count numerical claims without citations
        num_claims = re.findall(
            r'\d+\.?\d*\s*(?:%|mg|ng|ppt|ppb|ppm|kWh|\$)',
            interpretation,
        )
        cited_nums = re.findall(
            r'\d+\.?\d*\s*(?:%|mg|ng|ppt|ppb|ppm|kWh|\$)[^.!?\n]*'
            r'\[CITE:ev_[a-f0-9]+\]',
            interpretation,
        )
        grounding_ratio = len(cited_nums) / max(len(num_claims), 1)
        dims.append({
            "dimension": "evidence_grounding",
            "passed": grounding_ratio >= 0.6,
            "issues": (
                [f"Only {len(cited_nums)}/{len(num_claims)} numerical "
                 f"claims have citations"]
                if grounding_ratio < 0.6 else []
            ),
        })

        # 5. Analytical depth
        depth_markers = [
            r'(?:however|although|while|whereas|despite)',
            r'(?:trade-?off|limitation|disadvantage|drawback)',
            r'(?:recommend|ranking|prefer|optimal|best suited)',
            r'(?:gap|limitation|missing|insufficient|unclear)',
        ]
        depth_count = sum(
            len(re.findall(p, interpretation, re.IGNORECASE))
            for p in depth_markers
        )
        dims.append({
            "dimension": "analytical_depth",
            "passed": depth_count >= 3,
            "issues": (
                [f"Only {depth_count} depth markers found (need >=3)"]
                if depth_count < 3 else []
            ),
        })

        passed_count = sum(1 for d in dims if d["passed"])
        needs_rewrite = passed_count <= 3

        all_issues = []
        for d in dims:
            all_issues.extend(d["issues"])

        return {
            "dimensions": dims,
            "needs_rewrite": needs_rewrite,
            "rewrite_instructions": (
                "Fix these issues: " + "; ".join(all_issues)
                if needs_rewrite else ""
            ),
        }

    # -------------------------------------------------------------------
    # Phase 7: REWRITE — fix critique issues
    # -------------------------------------------------------------------

    async def _rewrite_interpretation(
        self, interpretation: str, critique: dict, briefing: dict,
    ) -> str | None:
        """Rewrite interpretation to fix critique issues (Phase 7).

        Only called when critique.needs_rewrite == True.
        Returns rewritten text, or None if rewrite fails/is too short.
        """
        all_issues = []
        for dim in critique.get("dimensions", []):
            if not dim.get("passed", True):
                all_issues.extend(dim.get("issues", []))

        instructions = critique.get("rewrite_instructions", "")
        issue_list = "\n".join(f"- {issue}" for issue in all_issues)

        prompt = (
            f"ORIGINAL ANALYSIS:\n{interpretation}\n\n"
            f"CRITIQUE FINDINGS:\n{instructions}\n\n"
            f"REWRITE the analysis to fix these specific issues:\n"
            f"{issue_list}\n\n"
            f"RULES:\n"
            f"1. Preserve all existing CORRECT claims and citations\n"
            f"2. Fix ONLY the issues identified above\n"
            f"3. Do NOT shorten the analysis\n"
            f"4. Maintain [CITE:ev_xxx] format for all citations\n"
            f"5. Do NOT add claims without evidence\n"
            f"6. Target 800-1500 words\n"
        )

        system = (
            "Rewrite the analysis to fix the identified issues. "
            "Preserve correct claims and citations. Do not shorten."
        )

        try:
            response = await asyncio.wait_for(
                self._client.generate(
                    prompt=prompt,
                    system=system,
                    max_tokens=8192,
                    temperature=0.3,
                    timeout=_SCAFFOLD_TIMEOUT,
                ),
                timeout=_SCAFFOLD_TIMEOUT + 30,
            )

            rewritten = response.content.strip()

            # Safety: accept only if >= 70% of original length
            if len(rewritten) < 0.7 * len(interpretation):
                logger.warning(
                    "[8phase] Rewrite too short: %d vs %d (%.0f%%), keeping original",
                    len(rewritten), len(interpretation),
                    len(rewritten) / max(len(interpretation), 1) * 100,
                )
                return None

            # Remove phantom citations
            all_cited = re.findall(r'\[CITE:([^\]]+)\]', rewritten)
            for pid in set(all_cited):
                if pid not in self._evidence_store:
                    rewritten = rewritten.replace(f"[CITE:{pid}]", "")

            # Update the interpretation step in notebook
            for step in self._notebook.steps:
                if (
                    step.tool_name == "interpret_results"
                    and step.result.success
                ):
                    valid_ids = [
                        eid for eid in re.findall(
                            r'\[CITE:(ev_[a-f0-9]+)\]', rewritten,
                        )
                        if eid in self._evidence_store
                    ]
                    step.result = ToolResult(
                        success=True,
                        tool_name="interpret_results",
                        markdown=rewritten,
                        source_evidence_ids=list(set(valid_ids)),
                        insights=[
                            "Scaffold-based analysis (rewritten after critique)",
                        ],
                    )
                    break

            return rewritten

        except Exception as exc:
            logger.warning(
                "[8phase] Rewrite failed: %s: %s",
                type(exc).__name__, str(exc)[:200],
            )
            return None

    async def _plan_analysis(self) -> AnalysisPlan:
        """Plan analysis in ONE LLM call (ReWOO pattern).

        Returns an ordered list of tools to execute. Falls back to
        a deterministic plan [extract, stats, sql] on failure.
        """
        all_tools = self._registry.available_tools(has_data=True)
        evidence_count = len(self._evidence_ids)
        has_structured = any(
            self._evidence_store.get(eid, {}).get("structured_data")
            for eid in self._evidence_ids[:50]
        )

        prompt = (
            f"Plan analysis for: {self._query[:120]}\n"
            f"Evidence: {evidence_count} | Structured: {has_structured}\n"
            f"Tools: {', '.join(all_tools)}\n\n"
            f"Rules:\n"
            f"1. Always start with extract_numeric_data\n"
            f"2. Then statistical_summary or query_evidence_sql\n"
            f"3. Then comparison_table or meta_analysis\n"
            f"4. Max {_MAX_ITERATIONS} steps\n\n"
            f"Return ordered tool steps."
        )

        # INF-2: Cap plan timeout at 30s (fallback handles failure)
        plan_timeout = int(resolve("PG_PLAN_TIMEOUT"))
        plan = await asyncio.wait_for(
            self._client.generate_structured(
                prompt=prompt,
                schema=AnalysisPlan,
                system="Plan the analysis. Return an ordered list of tool steps.",
                max_tokens=512,
                timeout=plan_timeout,
            ),
            timeout=plan_timeout + 15,
        )

        # Filter to known tools only, cap at max iterations
        valid_steps = [
            step for step in plan.steps
            if step.tool_name in _KNOWN_TOOLS and step.tool_name != "stop"
        ]
        plan.steps = valid_steps[:_MAX_ITERATIONS]

        return plan

    # -------------------------------------------------------------------
    # Phase 6.25: Visual artifacts (VIZ-1, VIZ-2, VIZ-3)
    # -------------------------------------------------------------------

    async def _generate_charts(
        self,
        classification: dict | None,
        briefing: dict,
    ) -> str:
        """VIZ-1: Auto-generate matplotlib chart via execute_python.

        Only generates charts when data points have ≥3 entries with
        same unit AND ≥2 distinct labels. Returns markdown image embed.
        """
        data_points = self._notebook.data_points
        if not data_points:
            return ""

        archetype = (classification or {}).get("archetype", "general")
        if archetype == "mechanism":
            return ""  # Causal chains don't map to bar charts

        # Check chart-worthiness: group by unit, need ≥3 points + ≥2 labels
        by_unit: dict[str, list] = {}
        for dp in data_points:
            unit = dp.get("unit", "")
            if unit:
                by_unit.setdefault(unit, []).append(dp)

        best_unit = ""
        best_group = []
        for unit, group in by_unit.items():
            labels = set(dp.get("label", "") for dp in group)
            if len(group) >= 3 and len(labels) >= 2:
                if len(group) > len(best_group):
                    best_unit = unit
                    best_group = group

        if not best_group:
            return ""

        # Determine chart type
        chart_type = "barh"  # Default horizontal bar
        if archetype == "cost_analysis":
            chart_type = "bar"  # Grouped vertical bar

        # FIX-CRASH: Build data for the chart — type-safe via _safe_float
        labels = []
        values = []
        eids = []
        for dp in best_group[:15]:  # Cap at 15 bars
            label = dp.get("label", "unknown")[:30]
            float_val = _safe_float(dp.get("value"))
            eid = dp.get("evidence_id", "")
            if float_val is not None and label:
                labels.append(label)
                values.append(float_val)
                eids.append(eid)

        if len(labels) < 2:
            return ""

        # Generate chart via execute_python tool
        metric_name = best_group[0].get("metric", "Value")
        tool_def = self._registry.get_tool("execute_python")
        if not tool_def or not tool_def.execute:
            return ""

        chart_timeout = int(resolve("PG_CHART_TIMEOUT"))
        try:
            result = await asyncio.wait_for(
                tool_def.execute(
                    evidence_store=self._evidence_store,
                    data_points=data_points,
                    client=self._client,
                    question=(
                        f"Create a {'horizontal ' if chart_type == 'barh' else ''}"
                        f"bar chart comparing: "
                        f"labels={labels}, values={values}, "
                        f"unit='{best_unit}', metric='{metric_name}'. "
                        f"Use clear colors, annotate bars with values. "
                        f"Title: '{metric_name} by Entity'. "
                        f"Return as PNG."
                    ),
                    research_context=self._query,
                ),
                timeout=chart_timeout,
            )
        except Exception as exc:
            logger.warning(
                "[chart] execute_python failed: %s: %s",
                type(exc).__name__, str(exc)[:100],
            )
            return ""

        if not result.success or not result.charts:
            return ""

        # VIZ-2: Embed chart as base64 image reference
        chart = result.charts[0]
        b64 = chart.get("image_base64", "")
        if not b64:
            return ""

        chart_title = f"{metric_name} Comparison ({best_unit})"
        step = AnalysisStep(
            step_number=self._notebook.step_count + 1,
            reasoning=f"Auto-generated {chart_type} chart: {chart_title}",
            tool_name="auto_chart",
            result=ToolResult(
                success=True,
                tool_name="auto_chart",
                markdown=f"![{chart_title}](chart)",
                source_evidence_ids=eids[:10],
                charts=[chart],
                insights=[f"Chart: {chart_title}"],
            ),
            elapsed_seconds=0.0,
        )
        self._notebook.add_step(step)

        logger.info(
            "[chart] Generated %s chart: %d bars, %s",
            chart_type, len(labels), chart_title,
        )
        return f"\n![{chart_title}](data:image/png;base64,{b64})\n"

    def _generate_decision_flowchart(self, text: str) -> str:
        """VIZ-3: Text-based decision tree from conditional recs.

        Only generated when ≥2 **If** ... **then** patterns exist.
        Pure text, no Mermaid dependency, renders everywhere.
        """
        # Find conditional recommendations in the text
        if_then_pattern = re.compile(
            r'\*\*[Ii]f\*\*\s*(.{10,120}?)\s*\*\*then\*\*\s*'
            r'(.{5,80}?)\s*(?:\*\*because\*\*\s*)?'
            r'(.{0,120}?)(?:\[CITE:(ev_[a-f0-9]+)\])?'
            r'(?:\.|$)',
            re.DOTALL,
        )
        matches = list(if_then_pattern.finditer(text))

        if len(matches) < 2:
            return ""

        lines = [
            "### Decision Guide\n",
            "```",
        ]

        for i, match in enumerate(matches[:5]):
            condition = match.group(1).strip().rstrip(",")[:60]
            recommendation = match.group(2).strip().rstrip(",")[:40]
            eid = match.group(4) or ""
            cite = f" [CITE:{eid}]" if eid else ""

            prefix = "├─" if i < len(matches) - 1 else "└─"
            lines.append(
                f"  {prefix} {condition}? → {recommendation}{cite}"
            )

        lines.append("```")

        logger.info(
            "[decision-tree] Generated from %d conditional recs",
            len(matches),
        )
        return "\n".join(lines)

    # -------------------------------------------------------------------
    # Post-processing: cleanup LLM output defects
    # -------------------------------------------------------------------

    def _post_process_interpretation(self, text: str) -> str:
        """Clean up common LLM output defects.

        1. Remove duplicate sentences (DeRep pattern: cosine > 0.95)
        2. Strip meta-commentary about prompt rules/constraints
        3. Flag fabricated numbers not in any cited evidence
        """
        # D3: Normalize line endings (handles \r\n from Windows/mixed)
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # D1-FIX: Multi-layer CoT scrubber (must run FIRST, before any
        # line-based processing). Qwen 3.5 Plus via OpenRouter occasionally
        # leaks </think> tags into the content field.
        # Layer 1: Complete <think>...</think> blocks
        text = re.sub(
            r'<think>.*?</think>', '', text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        # Layer 2: Everything before orphan </think> (preamble leak)
        text = re.sub(
            r'^.*?</think>\s*', '', text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        # Layer 3: Orphan open/close tags
        text = re.sub(r'</?think>', '', text, flags=re.IGNORECASE)

        lines = text.split("\n")
        cleaned_lines = []

        # --- Fix 1: Remove duplicate sentences within each paragraph ---
        seen_sentences: set[str] = set()
        for line in lines:
            if not line.strip():
                cleaned_lines.append(line)
                continue

            sentences = re.split(r'(?<=[.!?])\s+', line)
            unique_sentences = []
            for sent in sentences:
                # Normalize for comparison: lowercase, strip citations
                norm = re.sub(
                    r'\[CITE:ev_[a-f0-9]+\]', '', sent,
                ).strip().lower()
                # R4: Short sentences (<25 chars or <5 words) are
                # exempt from dedup to protect domain phrases like
                # "GAC is effective". Long sentences always dedup.
                norm_words = norm.split()
                if len(norm) < 25 or len(norm_words) < 5:
                    unique_sentences.append(sent)
                    continue
                if norm not in seen_sentences:
                    seen_sentences.add(norm)
                    unique_sentences.append(sent)
                else:
                    logger.debug(
                        "[post-process] Removed duplicate: %s",
                        sent[:60],
                    )

            if unique_sentences:
                cleaned_lines.append(" ".join(unique_sentences))

        text = "\n".join(cleaned_lines)

        # --- Fix 1c: Remove intra-sentence redundancy ---
        # "superior uniformity...through processes that yield superior
        # uniformity" — find 4+ word phrases appearing twice, remove
        # the second occurrence with its connecting clause.
        new_lines = []
        for line in text.split("\n"):
            sentences = re.split(r'(?<=[.!?])\s+', line)
            deduped_sents = []
            for sent in sentences:
                words = sent.lower().split()
                if len(words) < 10:
                    deduped_sents.append(sent)
                    continue
                # Find any repeated multi-word phrase (>=8 chars)
                # in the sentence and remove the second clause
                # containing it
                cleaned = sent
                sent_lower = sent.lower()
                for phrase_len in range(6, 1, -1):
                    for i in range(len(words) - phrase_len):
                        phrase = " ".join(words[i:i + phrase_len])
                        if len(phrase) < 15:
                            continue
                        first_pos = sent_lower.find(phrase)
                        if first_pos < 0:
                            continue
                        second_pos = sent_lower.find(
                            phrase, first_pos + len(phrase),
                        )
                        if second_pos < 0:
                            continue
                        # Found duplicate phrase — remove the
                        # second occurrence with connectors
                        # Work on the original-case text
                        before = cleaned[:second_pos]
                        after = cleaned[second_pos + len(phrase):]
                        # Strip trailing connector before the dup
                        before = re.sub(
                            r'[,;]?\s*(?:through\s+)?'
                            r'(?:processes\s+that\s+)?'
                            r'(?:that\s+)?(?:which\s+)?'
                            r'(?:yielding\s+)?(?:yield\s+)?$',
                            '', before,
                        )
                        cleaned = before + after
                        logger.debug(
                            "[post-process] Removed intra-sentence "
                            "repeat: '%s'", phrase[:40],
                        )
                        break
                    else:
                        continue
                    break
                deduped_sents.append(cleaned)
            new_lines.append(" ".join(deduped_sents))
        text = "\n".join(new_lines)

        # --- Fix 1d: FIX-D5 — Near-duplicate sentence detection ---
        # Within each section (split by ### headings), compute word-level
        # 5-gram Jaccard between sentence pairs. If > 0.70, keep the
        # longer/more-cited sentence.
        # IMPORTANT: Process line-by-line to preserve paragraph breaks
        # and blank lines. Compare across lines within the same section.
        sections = re.split(r'(^#{2,4}\s+.+$)', text, flags=re.MULTILINE)
        rebuilt_sections = []

        def _word_5grams(s: str) -> set:
            words = re.findall(r'[a-z]{3,}', s.lower())
            return {
                tuple(words[i:i + 5])
                for i in range(len(words) - 4)
            } if len(words) >= 5 else set()

        for section_chunk in sections:
            if not section_chunk.strip() or re.match(
                r'^#{2,4}\s+', section_chunk,
            ):
                rebuilt_sections.append(section_chunk)
                continue

            # Collect all sentences across lines, tracking origin
            sec_lines = section_chunk.split("\n")
            all_sents: list[tuple[int, int, str]] = []
            for li, line in enumerate(sec_lines):
                if not line.strip():
                    continue
                sents = re.split(r'(?<=[.!?])\s+', line)
                for si, sent in enumerate(sents):
                    all_sents.append((li, si, sent))

            if len(all_sents) < 2:
                rebuilt_sections.append(section_chunk)
                continue

            # Build 5-gram sets
            gram_cache = {
                idx: _word_5grams(s) for idx, (_, _, s)
                in enumerate(all_sents)
            }

            # Mark sentences to remove (by their index in all_sents)
            to_remove: set[int] = set()
            for i in range(len(all_sents)):
                if i in to_remove:
                    continue
                g_i = gram_cache.get(i, set())
                if not g_i:
                    continue
                for j in range(i + 1, len(all_sents)):
                    if j in to_remove:
                        continue
                    g_j = gram_cache.get(j, set())
                    if not g_j:
                        continue
                    overlap = len(g_i & g_j)
                    union = len(g_i | g_j)
                    if union > 0 and overlap / union > 0.70:
                        si = all_sents[i][2]
                        sj = all_sents[j][2]
                        cite_i = len(re.findall(r'\[CITE:', si))
                        cite_j = len(re.findall(r'\[CITE:', sj))
                        if (
                            len(sj) > len(si)
                            or (len(sj) == len(si) and cite_j > cite_i)
                        ):
                            to_remove.add(i)
                            logger.debug(
                                "[post-process] FIX-D5: Near-dup "
                                "removed (Jaccard=%.2f): %s",
                                overlap / union, si[:60],
                            )
                            break
                        else:
                            to_remove.add(j)
                            logger.debug(
                                "[post-process] FIX-D5: Near-dup "
                                "removed (Jaccard=%.2f): %s",
                                overlap / union, sj[:60],
                            )

            if not to_remove:
                rebuilt_sections.append(section_chunk)
                continue

            # Build set of sentences to remove (by text)
            remove_texts = {all_sents[idx][2] for idx in to_remove}

            # Rebuild section line-by-line, preserving structure
            new_sec_lines = []
            for li, line in enumerate(sec_lines):
                if not line.strip():
                    new_sec_lines.append(line)
                    continue
                sents = re.split(r'(?<=[.!?])\s+', line)
                kept = [s for s in sents if s not in remove_texts]
                if kept:
                    new_sec_lines.append(" ".join(kept))
                # If all sentences on a line were removed, skip the
                # line entirely (don't append empty line)
            rebuilt_sections.append("\n".join(new_sec_lines))
        text = "\n".join(rebuilt_sections)

        # --- Fix 2: Strip meta-commentary about prompt rules ---
        meta_patterns = [
            r'[^.]*(?:to comply with|technology family constraints|'
            r'do not rank subtypes|scaffold rule|as instructed|'
            r'per the instructions|following the rules|'
            r'as specified in the prompt|per the scaffold)[^.]*\.',
        ]
        for pattern in meta_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        # --- Fix 2b: Strip leaked gap query JSON blocks ---
        text = re.sub(
            r'```json\s*\{[^}]*"gap_search_queries"[^}]*\}\s*```',
            '', text, flags=re.DOTALL,
        )

        # --- Fix 2c: Strip leaked scaffold lens labels ---
        text = re.sub(
            r'^#{1,4}\s*LENS\s+\d+\s*[—–-]\s*[A-Z ]+[^#\n]*$',
            '', text, flags=re.MULTILINE,
        )

        # --- Fix 2d: R6 — Inline lens label scrubber ---
        # "Lens 1 suggests" / "noted in Lens 4" leak into prose.
        # Fix 2c only catches heading-level labels; this catches
        # inline references. Two-pass: skip if scientific lens
        # context word appears in 30-char window before match.
        _lens_source = text  # Capture for closure (stable ref)

        def _replace_lens_ref(m: re.Match) -> str:
            start = max(0, m.start() - 30)
            before_window = _lens_source[start:m.start()].lower()
            if any(w in before_window for w in _R6_SCI_LENS_WORDS):
                return m.group(0)  # Genuine scientific lens
            return "the analysis"

        text = re.sub(
            r'\b[Ll]ens\s+\d+\b', _replace_lens_ref, text,
        )

        # --- P0: RCS template echo scrubber (RPO post-hoc rewriting) ---
        # CR8: MUST run BEFORE Wave 4 parroting detection so template
        # echoes are removed before synonym rewriting.
        for echo_match in _TEMPLATE_ECHO.finditer(text):
            matched = echo_match.group()
            if '[CITE:' in matched:
                # Has citation — strip template-echo clause, keep data
                cleaned = re.sub(
                    r'\b(?:performs?\s+regarding|role\s+in\s+\w+\s+'
                    r'regarding)\b',
                    'in the context of',
                    matched, flags=re.IGNORECASE,
                )
                text = text.replace(matched, cleaned, 1)
                logger.debug(
                    "[post-process] P0: Template echo clause cleaned: "
                    "%s", matched[:60],
                )
            else:
                # No citation — remove entire sentence (uncited noise)
                text = text.replace(matched, '', 1)
                logger.debug(
                    "[post-process] P0: Template echo removed: %s",
                    matched[:60],
                )

        # P0 Fix 3: Filler "X demonstrates Y" (no data, no citation)
        for filler_match in _FILLER_DEMONSTRATES.finditer(text):
            matched = filler_match.group()
            if '[CITE:' not in matched:
                text = text.replace(matched, '', 1)
                logger.debug(
                    "[post-process] P0: Filler demonstrates removed: "
                    "%s", matched[:60],
                )

        # D2-FIX: Broader template echo with two detection paths:
        # Path A (uncited): Jaccard > 0.30 against claims text
        # Path B (cited): Subject-predicate echo ("Bonding demonstrates
        #   bonding PE...") — subject word reappears in predicate text
        if _HYBRID_EVIDENCE:
            claims_text = (
                getattr(self, '_evidence_passages_text', '') or ''
            )
        else:
            claims_text = (
                getattr(self, '_analytical_claims_text', '') or ''
            )
        claims_3grams = (
            self._ngrams(claims_text.lower(), 3) if claims_text else set()
        )
        for echo_match in _TEMPLATE_ECHO_DEMONSTRATES.finditer(text):
            matched = echo_match.group(1)
            has_cite = '[CITE:' in matched

            if has_cite:
                # Path B: Detect subject-predicate echo even in cited
                # sentences. "Bonding demonstrates bonding PE and PP..."
                subj_m = re.match(
                    r'^([A-Za-z]+)\s+demonstrates?\s+', matched,
                )
                if subj_m:
                    subj_word = subj_m.group(1).lower()
                    after_m = re.search(
                        r'demonstrates?\s+(.+)', matched,
                        re.IGNORECASE,
                    )
                    if after_m:
                        pred_start = after_m.group(1)[:80].lower()
                        if subj_word in pred_start.split():
                            text = text.replace(matched, '', 1)
                            logger.debug(
                                "[post-process] D2: Cited template "
                                "echo (subj=%s) removed: %s",
                                subj_word, matched[:60],
                            )
                            continue
                # Genuine cited analytical sentence — keep it
                continue

            # Path A: Uncited — use Jaccard guard against claims text
            if claims_3grams:
                sent_3grams = self._ngrams(matched.lower(), 3)
                if sent_3grams:
                    intersection = sent_3grams & claims_3grams
                    union = sent_3grams | claims_3grams
                    jaccard = len(intersection) / max(len(union), 1)
                    if jaccard > 0.30:
                        text = text.replace(matched, '', 1)
                        logger.debug(
                            "[post-process] D2: Template echo "
                            "(jaccard=%.2f) removed: %s",
                            jaccard, matched[:60],
                        )

        # --- Fix 2d: FIX-D3 — Strip brackets from conditional recs ---
        # LLM sometimes keeps [scenario]/[evidence] brackets from prompt.
        # (?!CITE:) guard prevents stripping [CITE:ev_xxx] tokens.
        text = re.sub(
            r'\*\*If\*\*\s*\[(?!CITE:)([^\]]+)\]',
            lambda m: f'**If** {m.group(1)}', text,
        )
        text = re.sub(
            r'\*\*then\*\*\s*\[(?!CITE:)([^\]]+)\]',
            lambda m: f'**then** {m.group(1)}', text,
        )
        text = re.sub(
            r'\*\*because\*\*\s*\[(?!CITE:)([^\]]+)\]',
            lambda m: f'**because** {m.group(1)}', text,
        )

        # --- PQ-3: REMOVED (WP-5) ---
        # Filler removal was too aggressive — removed legitimate cited
        # sentences containing "provides" or "offers". Quality gate
        # template echo detector handles genuine filler better.

        # --- P2: Citation validation via embedding similarity ---
        # Post-hoc citation verification (SIGIR 2025 pattern).
        # CR3: threshold 0.15 catches clear failures (sem=-0.04, 0.15)
        # without risking false positives (valid pairs ≥0.41).
        cite_pattern = re.compile(r'\[CITE:(ev_[a-f0-9]+)\]')
        all_cite_matches = list(cite_pattern.finditer(text))
        if all_cite_matches and self._evidence_store:
            # Collect (claim_context, evidence_statement) pairs
            cite_pairs: list[tuple[str, str, str, int, int]] = []
            for cm in all_cite_matches:
                eid = cm.group(1)
                ev = self._evidence_store.get(eid, {})
                ev_stmt = ev.get("statement", "")
                if not ev_stmt:
                    continue
                # Extract enclosing sentence as claim context
                cs = text.rfind('.', 0, cm.start())
                cs = cs + 1 if cs >= 0 else 0
                ce = text.find('.', cm.end())
                ce = ce + 1 if ce >= 0 else len(text)
                claim_ctx = text[cs:ce].strip()
                if len(claim_ctx) < 10:
                    continue
                cite_pairs.append(
                    (claim_ctx, ev_stmt, eid, cm.start(), cm.end()),
                )

            if cite_pairs:
                # Batch embed all texts
                all_texts = []
                for claim_ctx, ev_stmt, _, _, _ in cite_pairs:
                    all_texts.append(claim_ctx)
                    all_texts.append(ev_stmt)
                try:
                    all_embeddings = embed_texts(all_texts)
                    # Compute cosine similarity for each pair
                    removed_cites = 0
                    for i, (
                        claim_ctx, ev_stmt, eid, cstart, cend,
                    ) in enumerate(cite_pairs):
                        emb_claim = np.array(all_embeddings[i * 2])
                        emb_ev = np.array(all_embeddings[i * 2 + 1])
                        norm_c = np.linalg.norm(emb_claim)
                        norm_e = np.linalg.norm(emb_ev)
                        if norm_c > 0 and norm_e > 0:
                            sim = float(
                                np.dot(emb_claim, emb_ev)
                                / (norm_c * norm_e)
                            )
                        else:
                            sim = 0.0

                        if sim < _CITE_VALIDATION_THRESHOLD:
                            # Remove this citation token
                            cite_token = f"[CITE:{eid}]"
                            text = text.replace(cite_token, '', 1)
                            removed_cites += 1
                            logger.warning(
                                "[post-process] P2: Removed mismatched "
                                "citation [CITE:%s] (sim=%.3f < %.2f): "
                                "%s",
                                eid[:16], sim,
                                _CITE_VALIDATION_THRESHOLD,
                                claim_ctx[:60],
                            )
                        elif sim < 0.30:
                            logger.info(
                                "[post-process] P2: Low-sim citation "
                                "kept [CITE:%s] (sim=%.3f): %s",
                                eid[:16], sim, claim_ctx[:60],
                            )
                    if removed_cites > 0:
                        logger.info(
                            "[post-process] P2: Removed %d mismatched "
                            "citations (threshold=%.2f)",
                            removed_cites,
                            _CITE_VALIDATION_THRESHOLD,
                        )
                        # WP-1.3: Clean up orphaned punctuation after
                        # P2 citation removal (" , ." → "." etc.)
                        text = re.sub(r'\s*,\s*\.', '.', text)
                        text = re.sub(r'\s+\.', '.', text)
                        # WP-1.3: Sentence-length guard — if removing
                        # citation leaves <15 chars of content, remove
                        # the entire sentence.
                        _short_sent = re.compile(
                            r'(?<=[.!?]\s|^)([^.!?\n]{1,14}[.!?])',
                        )
                        for sm in _short_sent.finditer(text):
                            s = sm.group(1)
                            non_cite = re.sub(
                                r'\[CITE:ev_[a-f0-9]+\]', '', s,
                            ).strip()
                            if len(non_cite) < 15:
                                text = text.replace(s, '', 1)
                                logger.debug(
                                    "[post-process] P2: Removed short "
                                    "residual: %s", s[:40],
                                )
                except Exception:
                    logger.debug(
                        "[post-process] P2: Embedding failed, "
                        "skipping citation validation",
                        exc_info=True,
                    )

        # --- Wave 4: Structural parroting detection + rewrite ---
        # Domain-term exclusion (PlagBench), cited-evidence-only (DEER).
        # TWO structural transforms: B: Numeric Foregrounding, D: Causal Inversion.
        _rewrite_jaccard = float(
            resolve("PG_PARROTING_JACCARD_THRESHOLD"),
        )
        parroted_count = 0
        parroted_rewrites: list[tuple[str, str]] = []
        cite_per_sent = re.compile(r'\[CITE:(ev_[a-f0-9]+)\]')
        for sent_match in re.finditer(r'[^.!?]+[.!?]', text):
            sent = sent_match.group().strip()
            # Domain-term exclusion before n-gram construction
            sent_words = [
                w for w in re.findall(r'[a-z]{4,}', sent.lower())
                if w not in _DOMAIN_TERMS
            ]
            if len(sent_words) < 5:
                continue
            # Build 3-grams
            sent_ngrams = set()
            for idx in range(len(sent_words) - 2):
                sent_ngrams.add(
                    (sent_words[idx], sent_words[idx + 1],
                     sent_words[idx + 2]),
                )
            if not sent_ngrams:
                continue
            # DEER: check cited evidence in this sentence
            cited_eids = cite_per_sent.findall(sent)
            for eid in cited_eids:
                ev = self._evidence_store.get(eid, {})
                ev_stmt = ev.get("statement", "")
                ev_words = [
                    w for w in re.findall(r'[a-z]{4,}', ev_stmt.lower())
                    if w not in _DOMAIN_TERMS
                ]
                ev_ngrams = set()
                for idx in range(len(ev_words) - 2):
                    ev_ngrams.add(
                        (ev_words[idx], ev_words[idx + 1],
                         ev_words[idx + 2]),
                    )
                if not ev_ngrams:
                    continue
                overlap = len(sent_ngrams & ev_ngrams)
                union = len(sent_ngrams | ev_ngrams)
                jaccard = overlap / union if union > 0 else 0.0
                if jaccard > _rewrite_jaccard:
                    parroted_count += 1
                    rewritten = self._structural_rewrite(sent)
                    # P1: If structural rewrite didn't change,
                    # try synonym substitution (BloomScrub)
                    if rewritten == sent:
                        rewritten = self._synonym_rewrite(sent)
                    if rewritten != sent:
                        parroted_rewrites.append((sent, rewritten))
                    logger.warning(
                        "[post-process] Wave 4: Parroted sentence "
                        "(Jaccard=%.2f vs %s): %s",
                        jaccard, eid[:16], sent[:60],
                    )
                    break  # One match per sentence is enough
        # Apply rewrites
        for original, rewritten in parroted_rewrites:
            text = text.replace(original, rewritten, 1)

        # P1 Fix 5: Embedding-based validation (BloomScrub phase 3).
        # After rewrite, check cosine similarity. If still > 0.75,
        # apply more aggressive synonym substitution (max_swaps=5).
        if parroted_rewrites:
            try:
                recheck_texts = []
                recheck_pairs: list[tuple[str, str]] = []
                for original, rewritten in parroted_rewrites:
                    if rewritten != original:
                        recheck_texts.extend([original, rewritten])
                        recheck_pairs.append((original, rewritten))
                if recheck_texts:
                    recheck_embs = embed_texts(recheck_texts)
                    for pi, (orig, rew) in enumerate(recheck_pairs):
                        emb_o = np.array(recheck_embs[pi * 2])
                        emb_r = np.array(recheck_embs[pi * 2 + 1])
                        n_o = np.linalg.norm(emb_o)
                        n_r = np.linalg.norm(emb_r)
                        if n_o > 0 and n_r > 0:
                            sim = float(
                                np.dot(emb_o, emb_r) / (n_o * n_r),
                            )
                        else:
                            sim = 0.0
                        if sim > 0.75:
                            # Still too similar — more synonyms
                            more_rew = self._synonym_rewrite(
                                rew, max_swaps=5,
                            )
                            if more_rew != rew:
                                text = text.replace(rew, more_rew, 1)
                                logger.debug(
                                    "[post-process] P1: Extra synonym "
                                    "pass (sim=%.2f): %s",
                                    sim, rew[:60],
                                )
            except Exception:
                logger.debug(
                    "[post-process] P1: Embedding validation failed",
                    exc_info=True,
                )

        if parroted_count > 0:
            logger.info(
                "[post-process] Wave 4: %d parroted sentences "
                "rewritten (%d transforms applied)",
                parroted_count, len(parroted_rewrites),
            )

        # --- P6: Grammar defect fixes ---
        # P6a: "leading to X are" malformation
        text = re.sub(
            r'leading to\s+(\w+)\s+(are|is)\b',
            r'\1 \2', text, flags=re.IGNORECASE,
        )
        # P6b: Missing article before adj+noun
        text = re.sub(
            r'\bis\s+(significant|important|critical|key|major|notable)'
            r'\s+(challenge|issue|concern|problem|factor|limitation)\b',
            r'is a \1 \2', text, flags=re.IGNORECASE,
        )

        # --- Fix 3: Fabricated number patterns ---
        fabricated_patterns = [
            (
                r'~?\s*100\s*%\s*improvement\s*(?:metric|rate|measure)',
                'near-complete improvement',
            ),
            (
                r'a\s+\d+%\s+improvement\s+metric',
                'a significant improvement',
            ),
        ]
        for pattern, replacement in fabricated_patterns:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        # --- Fix 3b: REMOVED (WP-5) ---
        # Fabricated decision matrix score removal was too aggressive —
        # removed "total score of X" even when evidence-backed. Template
        # echo detector (WP-2.1) handles fabricated matrices better.

        # --- WP-1.2: Standalone expanded-decimal detector ---
        # Catches numbers with 10+ digits anywhere in text (e.g.
        # "5700000000.0 USD"). These are LLM-expanded forms of
        # human-readable numbers like "$5.7 billion". Replace with
        # human form if found in evidence, otherwise remove.
        _expanded_dec_re = re.compile(r'\d[\d,]{9,}\.?\d*')
        for ed_match in _expanded_dec_re.finditer(text):
            ed_str = ed_match.group()
            ed_clean = ed_str.replace(",", "")
            try:
                ed_val = float(ed_clean)
            except ValueError:
                continue
            # Search evidence for human-readable form
            replaced = False
            for _eid, ev in self._evidence_store.items():
                ev_stmt = ev.get("statement", "")
                for sw, scale in [
                    ("trillion", 1e12), ("billion", 1e9),
                    ("million", 1e6), ("thousand", 1e3),
                ]:
                    if sw not in ev_stmt.lower():
                        continue
                    for ev_num in re.findall(r'\d+\.?\d*', ev_stmt):
                        try:
                            if abs(
                                ed_val - float(ev_num) * scale
                            ) / max(ed_val, 1) <= 0.05:
                                human = f"{ev_num} {sw}"
                                text = text.replace(ed_str, human, 1)
                                logger.info(
                                    "[post-process] WP-1.2: Expanded "
                                    "decimal %s → %s",
                                    ed_str, human,
                                )
                                replaced = True
                                break
                        except ValueError:
                            continue
                    if replaced:
                        break
                if replaced:
                    break
            if not replaced:
                text = text.replace(ed_str, "", 1)
                text = re.sub(r'  +', ' ', text)
                logger.info(
                    "[post-process] WP-1.2: Expanded decimal removed: "
                    "%s (no human form found)", ed_str,
                )

        # --- Fix 4: Number grounding check (FACTScore pattern) ---
        # For each [CITE:ev_xxx] with a nearby number, verify the number
        # exists as a standalone value in the cited evidence. If NOT,
        # remove the ungrounded numerical claim (safer than guessing
        # the correction — covers truncation, transposition, rounding,
        # and wrong-number-from-same-source errors).
        # Find ALL [CITE:ev_xxx] tokens first, then look for the
        # nearest number BEFORE each citation (within 30 chars).
        # This ensures we check the closest number, not the first.
        cite_positions = [
            (m.group(1), m.start(), m.end())
            for m in re.finditer(r'\[CITE:(ev_[a-f0-9]+)\]', text)
        ]
        # Collect ungrounded numbers (don't modify text during iteration)
        ungrounded = []
        for eid, cite_start, cite_end in cite_positions:
            ev = self._evidence_store.get(eid, {})
            ev_stmt = ev.get("statement", "")
            if not ev_stmt:
                continue

            # Look backwards from citation for the nearest number.
            # Stop at '[' to avoid matching digits inside [CITE:ev_xxx]
            # tokens from adjacent citations.
            window_start = max(0, cite_start - 30)
            before_cite = text[window_start:cite_start]
            # Trim to text after last '[' (exclude prior CITE tokens)
            last_bracket = before_cite.rfind(']')
            if last_bracket >= 0:
                before_cite = before_cite[last_bracket + 1:]
                window_start = window_start + last_bracket + 1
            # Find ALL numbers in the clean window, take LAST (closest)
            nums_in_window = list(re.finditer(
                r'\d+\.?\d*', before_cite,
            ))
            if not nums_in_window:
                continue
            last_num_match = nums_in_window[-1]
            num_str = last_num_match.group()
            num_abs_start = window_start + last_num_match.start()

            # WP-1.2: Decimal boundary fix — if the char before the
            # matched number is '.', extend backwards to capture the
            # integer part (prevents splitting "1.2 GPa" into "2 GPa").
            if num_abs_start > 0 and text[num_abs_start - 1] == '.':
                int_match = re.search(
                    r'(\d+)\.$',
                    text[max(0, num_abs_start - 15):num_abs_start],
                )
                if int_match:
                    full_num = int_match.group(1) + '.' + num_str
                    num_abs_start -= len(int_match.group(1)) + 1
                    num_str = full_num

            # Skip small numbers likely to be ordinals/list items,
            # BUT keep dollar amounts ($1 is meaningful)
            try:
                num_val = float(num_str)
                char_before = (
                    text[num_abs_start - 1] if num_abs_start > 0 else ""
                )
                if num_val < 2 and char_before != "$":
                    continue
            except (ValueError, IndexError):
                continue

            # Build the span for replacement (num...CITE)
            span = text[num_abs_start:cite_end]

            # Check if the number exists as a standalone value
            # (not as substring: "7" ≠ "70", "1" ≠ "1,000")
            num_in_evidence = bool(re.search(
                r'(?<!\d)' + re.escape(num_str) + r'(?!\d|,\d)',
                ev_stmt,
            ))
            if not num_in_evidence:
                ungrounded.append({
                    "num": num_str,
                    "eid": eid,
                    "span": span,
                    "ev_numbers": re.findall(
                        r'\d[\d,]*\.?\d*', ev_stmt,
                    ),
                })

        # Fix ungrounded numbers
        for item in ungrounded:
            num_str = item["num"]
            ev_numbers = item["ev_numbers"]

            # Strategy 1: If output number is a prefix of an evidence
            # number, it's truncation — fix it (7 → 70, 1 → 1,000)
            fixed = False
            for ev_num in ev_numbers:
                ev_num_clean = ev_num.replace(",", "")
                # Check: output is prefix of evidence number
                # Allow up to 4 extra chars (handles 1→1000, 7→70)
                if (
                    ev_num_clean.startswith(num_str)
                    and len(ev_num_clean) > len(num_str)
                    and len(ev_num_clean) <= len(num_str) + 4
                ):
                    old_span = item["span"]
                    fixed_span = old_span.replace(num_str, ev_num, 1)
                    text = text.replace(old_span, fixed_span, 1)
                    logger.info(
                        "[post-process] Fixed truncated number: "
                        "%s -> %s (from %s)",
                        num_str, ev_num, item["eid"][:16],
                    )
                    fixed = True
                    break

            if not fixed:
                # Strategy 2: Citation correction — if the number exists
                # in a DIFFERENT evidence piece, fix the citation
                # (covers wrong-source attribution like 250µm cited to
                # the 125µm source instead of the 250µm source).
                correct_eid = None
                for eid, ev in self._evidence_store.items():
                    ev_stmt = ev.get("statement", "")
                    if re.search(
                        r'(?<!\d)' + re.escape(num_str) + r'(?!\d)',
                        ev_stmt,
                    ):
                        correct_eid = eid
                        break

                if correct_eid and correct_eid != item["eid"]:
                    old_cite = f"[CITE:{item['eid']}]"
                    new_cite = f"[CITE:{correct_eid}]"
                    old_span = item["span"]
                    if old_cite in old_span:
                        fixed_span = old_span.replace(
                            old_cite, new_cite, 1,
                        )
                        text = text.replace(old_span, fixed_span, 1)
                        logger.info(
                            "[post-process] Fixed citation: %s -> %s "
                            "for number %s",
                            item["eid"][:16], correct_eid[:16], num_str,
                        )
                    else:
                        logger.warning(
                            "[post-process] Ungrounded number: %s not "
                            "in %s (correct source: %s)",
                            num_str, item["eid"][:16],
                            correct_eid[:16],
                        )
                else:
                    # Strategy 3 (P7): Check derivability — if the
                    # fabricated number is within 5% of an evidence
                    # number, keep it (likely a rounding). Otherwise
                    # remove the span (CR6: remove span, not sentence).
                    derivable = False
                    try:
                        fab_val = float(num_str)
                        for ev_num in ev_numbers:
                            ev_clean = ev_num.replace(",", "")
                            try:
                                ev_val = float(ev_clean)
                                if ev_val > 0 and abs(
                                    fab_val - ev_val
                                ) / ev_val <= 0.05:
                                    derivable = True
                                    break
                                # R3: Scale-transformation guard.
                                # "$5.7 billion" → 5700000000.0
                                # when evidence only has "5.7".
                                # Only allow when a scale word
                                # appears near the number in text.
                                for scale in (
                                    1e3, 1e6, 1e9, 1e12,
                                ):
                                    scaled = ev_val * scale
                                    if scaled > 0 and abs(
                                        fab_val - scaled
                                    ) / scaled <= 0.05:
                                        span_text = item["span"]
                                        num_pos = span_text.find(
                                            num_str,
                                        )
                                        if num_pos < 0:
                                            num_pos = len(span_text)
                                        window_start = max(
                                            0, num_pos - 40,
                                        )
                                        window = span_text[
                                            window_start:num_pos
                                        ].lower()
                                        if any(
                                            sw in window
                                            for sw in _R3_SCALE_WORDS
                                        ):
                                            # WP-1.2: Reject expanded
                                            # decimals (10+ digits).
                                            # "$5,700,000,000.0" is
                                            # derivable but ugly —
                                            # remove the span instead.
                                            clean_num = num_str.replace(
                                                ",", "",
                                            )
                                            if len(re.sub(
                                                r'[^0-9]', '',
                                                clean_num,
                                            )) >= 10:
                                                logger.info(
                                                    "[post-process] R3:"
                                                    " Expanded decimal "
                                                    "rejected: %s "
                                                    "(10+ digits)",
                                                    num_str,
                                                )
                                                break
                                            derivable = True
                                            logger.info(
                                                "[post-process] R3: "
                                                "Scale-transform "
                                                "match: %s ≈ %s × "
                                                "%s", num_str,
                                                ev_clean,
                                                f"{scale:.0e}",
                                            )
                                            break
                                    if derivable:
                                        break
                            except ValueError:
                                continue
                        if derivable:
                            break  # Exit ev_num loop early
                    except ValueError:
                        pass

                    if derivable:
                        logger.info(
                            "[post-process] P7: Derivable number %s "
                            "(within 5%% of evidence) — kept",
                            num_str,
                        )
                    else:
                        # Remove the span and clean up whitespace
                        text = text.replace(item["span"], "", 1)
                        text = re.sub(r'  +', ' ', text)
                        text = re.sub(r'\s+([.,;])', r'\1', text)
                        logger.warning(
                            "[post-process] P7: Fabricated number "
                            "removed: %s not in %s (evidence has: %s)",
                            num_str, item["eid"][:16],
                            ", ".join(ev_numbers[:5]),
                        )

        # --- WS-5: CiteFix citation correction (ACL 2025 Industry) ---
        # 80% of "hallucinations" in RAG are incorrect citations, not
        # fabricated facts. Three strategies: keyword, semantic, number.
        # Tracks P7 swaps to avoid undoing correct fixes (MODERATE-1).
        if resolve("PG_CITEFIX_ENABLED") == "1" and self._evidence_store:
            text = self._fix_citations(text)

        # --- Fix 5: Remove incomplete sentences + D4 dangling preps ---
        _dangling_preps = re.compile(
            r'\s+(?:of|for|with|to|from|by|in|on|at|as|into)\s*$',
        )
        sentences = text.split("\n")
        cleaned = []
        for line in sentences:
            stripped = line.rstrip()
            if not stripped:
                cleaned.append(line)
                continue
            # If line ends mid-word (no punctuation, no header, no list)
            if (
                stripped
                and not stripped[-1] in '.!?:"|)'
                and not stripped.startswith('#')
                and not stripped.startswith('|')
                and not stripped.startswith('-')
                and not stripped.startswith('*')
                and len(stripped) > 50
            ):
                # Find last complete sentence
                last_period = max(
                    stripped.rfind('. '),
                    stripped.rfind('? '),
                    stripped.rfind('! '),
                    stripped.rfind('.]'),
                )
                if last_period > 0:
                    stripped = stripped[:last_period + 1]
                    logger.info(
                        "[post-process] Trimmed incomplete sentence",
                    )
            # D4: Trim dangling prepositions after sentence trim
            stripped = _dangling_preps.sub('', stripped)
            cleaned.append(stripped)
        text = "\n".join(cleaned)

        # --- Fix 5b: FIX-D4 — Incomplete unit detector ---
        # Detects dangling measurement prefixes like "4.0 parts per"
        # without the completing unit word, and repairs from evidence.
        _incomplete_units = re.compile(
            r'(\d+\.?\d*)\s+(parts per|degrees|per cent|watts per|'
            r'grams per|liters per|meters per|milligrams per|'
            r'micrograms per)'
            r'(?!\s*(?:trillion|billion|million|thousand|hundred|'
            r'cent|minute|hour|day|year|liter|litre|gallon|unit|'
            r'meter|metre|kilogram|gram|mole|second|watt|square|'
            r'cubic))',
        )
        for m in _incomplete_units.finditer(text):
            num_str = m.group(1)
            prefix = m.group(2)
            full_span = m.group(0)
            # Search evidence for the complete phrase
            repaired = False
            for eid, ev in self._evidence_store.items():
                ev_stmt = ev.get("statement", "")
                # Look for "num prefix UNIT" in evidence
                ev_match = re.search(
                    re.escape(num_str) + r'\s+' + re.escape(prefix)
                    + r'\s+(\w+)',
                    ev_stmt, re.IGNORECASE,
                )
                if ev_match:
                    unit_word = ev_match.group(1)
                    fixed = f"{num_str} {prefix} {unit_word}"
                    text = text.replace(full_span, fixed, 1)
                    logger.info(
                        "[post-process] FIX-D4: Repaired unit: "
                        "'%s' -> '%s' (from %s)",
                        full_span, fixed, eid[:16],
                    )
                    repaired = True
                    break
            if not repaired:
                logger.warning(
                    "[post-process] FIX-D4: Incomplete unit '%s' "
                    "not found in evidence — kept as-is",
                    full_span,
                )

        # --- Fix 5c: R5 — PDF artifact repair ---
        # Double-word dedup (2+ char words, safelist legit doubles)
        def _dedup_double_word(m: re.Match) -> str:
            word = m.group(1)
            if word.lower() in _R5_LEGIT_DOUBLES:
                return m.group(0)  # Preserve legitimate doubles
            return word

        text = re.sub(
            r'\b(\w{2,})\s+\1\b', _dedup_double_word,
            text, flags=re.IGNORECASE,
        )
        # Dangling colon-number: "20-: 25.0" → "20-25.0"
        text = re.sub(r'(\d+)-:\s*(\d+)', r'\1-\2', text)
        # Orphaned dash-colon: standalone "-:" artifacts
        text = re.sub(r'\s+-:\s+', ' ', text)

        # --- Fix 5d: FIX-D6 — Unbalanced parentheses ---
        # Per-sentence: balance open/close parens.
        paren_lines = []
        for line in text.split("\n"):
            if line.startswith("#") or line.startswith("|"):
                paren_lines.append(line)
                continue
            sentences = re.split(r'(?<=[.!?])\s+', line)
            fixed_sents = []
            for sent in sentences:
                open_count = sent.count("(")
                close_count = sent.count(")")
                if open_count > close_count:
                    # Add missing ')' before terminal punctuation
                    diff = open_count - close_count
                    end_match = re.search(r'([.!?])$', sent)
                    if end_match:
                        sent = (
                            sent[:end_match.start()]
                            + ")" * diff
                            + end_match.group(1)
                        )
                    else:
                        sent = sent + ")" * diff
                elif close_count > open_count:
                    # Remove first unmatched ')'
                    diff = close_count - open_count
                    for _ in range(diff):
                        # Find the first ')' without a preceding '('
                        depth = 0
                        for ci, ch in enumerate(sent):
                            if ch == "(":
                                depth += 1
                            elif ch == ")":
                                if depth > 0:
                                    depth -= 1
                                else:
                                    sent = sent[:ci] + sent[ci + 1:]
                                    break
                fixed_sents.append(sent)
            paren_lines.append(" ".join(fixed_sents))
        text = "\n".join(paren_lines)

        # --- Fix 6: Table integrity + D5 identical columns + D7 matrix ---
        if _REFINER_ENABLED:
            table_blocks = re.findall(
                r'(\|[^\n]+\|\n\|[-:| ]+\|\n(?:\|[^\n]+\|\n)*)',
                text,
            )
            for table_block in table_blocks:
                rows = [
                    r for r in table_block.strip().split("\n")
                    if r.strip().startswith("|")
                ]
                data_rows = max(0, len(rows) - 2)
                if data_rows < 2:
                    logger.warning(
                        "[post-process] Sparse table: only %d data rows",
                        data_rows,
                    )
                # Check for empty/N/A cells
                for row in rows[2:]:
                    cells = [
                        c.strip() for c in row.split("|") if c.strip()
                    ]
                    empty_cells = sum(
                        1 for c in cells
                        if c in ("", "N/A", "-", "?", "n/a")
                    )
                    if empty_cells > 0:
                        logger.warning(
                            "[post-process] Table row has %d empty/N/A "
                            "cells: %s",
                            empty_cells, row.strip()[:80],
                        )

                # D5/TQ-2: Detect + annotate identical column values
                identical_cols = []
                if data_rows >= 3 and rows:
                    header_cells = [
                        c.strip() for c in rows[0].split("|") if c.strip()
                    ]
                    for col_idx in range(len(header_cells)):
                        col_values = set()
                        for row in rows[2:]:
                            cells = [
                                c.strip()
                                for c in row.split("|") if c.strip()
                            ]
                            if col_idx < len(cells):
                                col_values.add(cells[col_idx])
                        if len(col_values) < 2:
                            col_name = (
                                header_cells[col_idx]
                                if col_idx < len(header_cells)
                                else f"col{col_idx}"
                            )
                            identical_cols.append(col_name)
                            logger.warning(
                                "[post-process] D5: Column '%s' has "
                                "identical values across %d rows",
                                col_name, data_rows,
                            )
                if identical_cols:
                    annotation = (
                        "\n\n*(Note: "
                        + ", ".join(identical_cols)
                        + " — no differentiation in evidence)*"
                    )
                    text = text.replace(
                        table_block,
                        table_block.rstrip() + annotation,
                        1,
                    )

                # D7: Matrix false positive — require 2+ score-like
                # words in header to flag as decision matrix
                if rows:
                    header_lower = rows[0].lower()
                    score_words = sum(
                        1 for w in (
                            "weight", "score", "total", "rating",
                            "rank",
                        )
                        if w in header_lower
                    )
                    if score_words >= 2:
                        logger.warning(
                            "[post-process] D7: Table looks like a "
                            "fabricated decision matrix (header has "
                            "%d score-related columns)",
                            score_words,
                        )

        # --- TQ-1: Table cell verbosity trimming ---
        # Cells >60 chars: keep number+unit+qualifier (≤30 chars)
        def _trim_cell(cell_text: str) -> str:
            if len(cell_text) <= 60:
                return cell_text
            # Preserve citations
            cites = re.findall(r'\[CITE:ev_[a-f0-9]+\]', cell_text)
            cite_str = " ".join(cites)
            # Extract first number + unit + qualifier (up to 30 chars)
            num_match = re.search(
                r'(\d+\.?\d*\s*(?:%|mg|ng|ppt|ppb|ppm|kWh|\$|MPa|'
                r'µm|nm|m2|g/L|mg/g|billion|million|°C|bar|min|h|'
                r'L|mL|kg)(?:\s*[^\d\[]{0,25})?)',
                cell_text,
            )
            if num_match:
                core = num_match.group(1).strip()[:30]
                return f"{core} {cite_str}".strip()
            return cell_text[:30] + f"... {cite_str}".strip()

        table_line_pattern = re.compile(r'^\|(.+)\|$', re.MULTILINE)
        sep_pattern = re.compile(r'^\|[-:| ]+\|$', re.MULTILINE)
        new_lines = []
        for line in text.split("\n"):
            if (
                table_line_pattern.match(line.strip())
                and not sep_pattern.match(line.strip())
            ):
                cells = line.split("|")
                trimmed = []
                for cell in cells:
                    if cell.strip():
                        trimmed.append(f" {_trim_cell(cell.strip())} ")
                    else:
                        trimmed.append(cell)
                new_lines.append("|".join(trimmed))
            else:
                new_lines.append(line)
        text = "\n".join(new_lines)

        # --- WP-1.4: Normalize citation token whitespace before dedup ---
        # Catches "[ CITE: ev_xxx ]" variants the LLM sometimes produces.
        text = re.sub(
            r'\[\s*CITE\s*:\s*(ev_[a-f0-9]+)\s*\]',
            r'[CITE:\1]', text,
        )

        # --- D2: Remove duplicate adjacent CITE tokens (moved to end) ---
        # Catches 2+ adjacent identical CITE tokens introduced by
        # any prior fix. Must run LAST so no fix re-introduces dupes.
        text = re.sub(
            r'(\[CITE:ev_[a-f0-9]+\])(?:\s*\1)+',
            r'\1', text,
        )

        # Bug-1 fix: Strip phantom citations from ALL content
        # (including artifact sections appended after quality gate).
        # Same method used in quality gate, now also in post-processor
        # to catch phantoms in ranking/comparison/chart sections.
        text = self._strip_phantom_citations(text)

        # WP-1.3 (MODERATE-1): Remove bare numbered items unconditionally.
        # These come from P2 stripping citations from ranking entries
        # AND from LLM generating empty ranking slots directly.
        # Safe to run always — lines that are ONLY "N." are never valid.
        text = re.sub(r'^\s*\d+\.\s*$', '', text, flags=re.MULTILINE)

        # Clean up any double spaces or empty lines from removals
        text = re.sub(r'  +', ' ', text)
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)

        return text.strip()

    def _verify_claims(self, briefing: dict | None = None) -> dict:
        """Programmatic post-interpretation claim verification.

        Enhanced for 8-phase pipeline with optional briefing for:
        - Evidence coverage check (what % of clusters cited)
        - Restatement detection (Jaccard overlap = parroting)
        - Sub-question coverage

        Appends a verification step to the notebook with results.
        Returns a summary dict.
        """
        # Find the interpretation step
        interp_step = None
        for step in self._notebook.steps:
            if step.tool_name == "interpret_results" and step.result.success:
                interp_step = step
                break

        if not interp_step:
            return {}

        content = interp_step.result.markdown

        # Category mismatch check (reuses existing method)
        category_mismatches = self._verify_interpretation_claims(content)

        # Numerical presence check
        all_cites = re.findall(r'\[CITE:(ev_[a-f0-9]+)\]', content)
        pattern = re.compile(
            r'([^.!?\n]{10,120})\[CITE:(ev_[a-f0-9]+)\]'
        )

        total_checked = 0
        verified = 0
        for match in pattern.finditer(content):
            claim_text = match.group(1).strip()
            ev_id = match.group(2)

            if ev_id not in self._evidence_store:
                continue

            nums_in_claim = re.findall(r'(\d+\.?\d*)', claim_text)
            if not nums_in_claim:
                continue

            total_checked += 1
            ev_stmt = self._evidence_store[ev_id].get(
                "statement", "",
            ).lower()
            key_num = nums_in_claim[-1]  # Closest to citation

            if key_num in ev_stmt:
                verified += 1

        report = {
            "total_citations": len(all_cites),
            "unique_citations": len(set(all_cites)),
            "total_claims_checked": total_checked,
            "verified": verified,
            "mismatches": len(category_mismatches),
            "mismatch_details": category_mismatches[:10],
        }

        # Enhanced metrics when briefing is available
        if briefing:
            # Evidence coverage: what % of clusters have citations
            cited_eids = set(all_cites)
            clusters = briefing.get("clusters", [])
            learnings = briefing.get("learnings", [])
            clusters_cited = 0
            for cluster in clusters:
                cluster_eids = set()
                for idx in cluster.get("learning_indices", []):
                    if idx < len(learnings):
                        cluster_eids.update(
                            learnings[idx].get("evidence_ids", []),
                        )
                if cluster_eids & cited_eids:
                    clusters_cited += 1
            report["cluster_coverage"] = round(
                clusters_cited / max(len(clusters), 1), 3,
            )

            # Category coverage
            all_categories = set(
                l.get("category", "general") for l in learnings
            )
            cited_categories = set()
            for eid in cited_eids:
                ev = self._evidence_store.get(eid, {})
                cited_categories.add(ev.get("fact_category", "general"))
            report["category_coverage"] = round(
                len(cited_categories & all_categories)
                / max(len(all_categories), 1),
                3,
            )

            # Restatement detection (parroting)
            sentences = re.split(r'[.!?]\s+', content)
            parroted = 0
            for sent in sentences:
                sent_words = set(
                    w.lower() for w in re.findall(r'[a-z]{4,}', sent.lower())
                )
                if not sent_words:
                    continue
                for eid in self._evidence_ids[:200]:
                    ev = self._evidence_store.get(eid, {})
                    ev_stmt = ev.get("statement", "")
                    ev_words = set(
                        w.lower()
                        for w in re.findall(r'[a-z]{4,}', ev_stmt.lower())
                    )
                    if not ev_words:
                        continue
                    jaccard = (
                        len(sent_words & ev_words)
                        / max(len(sent_words | ev_words), 1)
                    )
                    if jaccard > 0.5:
                        parroted += 1
                        break
            report["parroting_ratio"] = round(
                parroted / max(len(sentences), 1), 3,
            )

            # Sub-question coverage
            sub_questions = briefing.get("sub_questions", [])
            sq_covered = 0
            for sq in sub_questions:
                sq_words = set(
                    w for w in sq.lower().split() if len(w) > 3
                )
                interp_lower = content.lower()
                overlap = sum(1 for w in sq_words if w in interp_lower)
                if overlap >= 2:
                    sq_covered += 1
            report["sub_question_coverage"] = round(
                sq_covered / max(len(sub_questions), 1), 3,
            )

        # Build verification report markdown
        report_lines = [
            "**Claim Verification Report:**",
            f"- Citations: {len(all_cites)} total, "
            f"{len(set(all_cites))} unique",
            f"- Numerical claims checked: {total_checked}",
            f"- Numbers verified in source: {verified}/{total_checked}",
            f"- Category mismatches: {len(category_mismatches)}",
        ]
        if briefing:
            report_lines.extend([
                f"- Cluster coverage: "
                f"{report.get('cluster_coverage', 0):.0%}",
                f"- Parroting ratio: "
                f"{report.get('parroting_ratio', 0):.0%}",
                f"- Sub-question coverage: "
                f"{report.get('sub_question_coverage', 0):.0%}",
            ])
        if category_mismatches:
            report_lines.append("\n**Category Mismatches:**")
            for mm in category_mismatches[:5]:
                report_lines.append(
                    f"- {mm['ev_id']}: claim \"{mm['claim'][:50]}\" "
                    f"({mm['claim_category']}) vs evidence "
                    f"\"{mm['ev_statement'][:50]}\" ({mm['ev_category']})"
                )

        verify_step = AnalysisStep(
            step_number=self._notebook.step_count + 1,
            reasoning="Programmatic claim-evidence verification",
            tool_name="verify_claims",
            result=ToolResult(
                success=True,
                tool_name="verify_claims",
                markdown="\n".join(report_lines),
                source_evidence_ids=list(set(all_cites))[:20],
                insights=[
                    f"Verified {verified}/{total_checked} numerical "
                    f"claims against source evidence",
                ],
                statistics=report,
            ),
            elapsed_seconds=0.0,
        )
        self._notebook.add_step(verify_step)

        return report

    # -------------------------------------------------------------------
    # ReAct loop helpers (legacy mode)
    # -------------------------------------------------------------------

    async def _decide(self, iteration: int) -> ReactDecision:
        """Ask the LLM which tool to use next."""
        available = self._registry.available_tools(self._notebook.has_data)
        tool_descriptions = self._registry.get_tool_descriptions(
            self._notebook.has_data,
        )
        notebook_summary = self._notebook.summary_for_llm()

        evidence_count = len(self._evidence_ids)
        has_structured = any(
            self._evidence_store.get(eid, {}).get("structured_data")
            for eid in self._evidence_ids[:50]
        )

        # Compact prompt — keep under 800 tokens to avoid Qwen timeouts
        # (Qwen 3.5 Plus latency spikes on 2nd+ structured calls)
        tools_short = ", ".join(available)
        done_tools = ", ".join(
            s.tool_name for s in self._notebook.steps if s.result.success
        ) or "none"
        dp_count = len(self._notebook.data_points)

        prompt = (
            f"Topic: {self._query[:120]}\n"
            f"Evidence: {evidence_count} pieces | "
            f"Data points: {dp_count} | "
            f"Structured data: {has_structured}\n"
            f"Done: {done_tools}\n"
            f"Available: {tools_short}\n\n"
            f"Rules:\n"
            f"1. extract_numeric_data FIRST if data points = 0\n"
            f"2. Don't repeat succeeded tools\n"
            f"3. Need: stats + comparison/meta before stop\n"
            f"4. Max {_MAX_ITERATIONS} steps\n\n"
            f"Pick one tool or 'stop'. Give reasoning."
        )

        system = (
            "Pick the next analysis tool. Respond with reasoning and action."
        )

        decision = await asyncio.wait_for(
            self._client.generate_structured(
                prompt=prompt,
                schema=ReactDecision,
                system=system,
                max_tokens=512,
                timeout=60,
            ),
            timeout=75,
        )

        # Validate the action is a known tool or "stop"
        if decision.action != "stop" and decision.action not in available:
            logger.warning(
                "[react] LLM picked unavailable tool '%s', mapping to fallback",
                decision.action,
            )
            if (
                not self._notebook.has_data
                and "extract_numeric_data" in available
            ):
                decision.action = "extract_numeric_data"
                decision.reasoning = (
                    f"Falling back to extract_numeric_data "
                    f"('{decision.action}' unavailable)"
                )
            elif available:
                decision.action = available[0]
                decision.reasoning = f"Falling back to {available[0]}"
            else:
                decision.action = "stop"

        return decision

    async def _execute_tool(
        self, iteration: int, decision: ReactDecision,
    ) -> AnalysisStep:
        """Execute a tool and return an AnalysisStep."""
        tool_def = self._registry.get_tool(decision.action)
        step_start = time.monotonic()

        if not tool_def or not tool_def.execute:
            return AnalysisStep(
                step_number=iteration,
                reasoning=decision.reasoning,
                tool_name=decision.action,
                result=ToolResult(
                    success=False,
                    tool_name=decision.action,
                    markdown=f"Unknown tool: {decision.action}",
                    error=f"Tool '{decision.action}' not found in registry",
                ),
                elapsed_seconds=0.0,
            )

        try:
            result = await asyncio.wait_for(
                tool_def.execute(
                    evidence_store=self._evidence_store,
                    data_points=self._notebook.data_points,
                    client=self._client,
                    **decision.action_input,
                ),
                timeout=_TOOL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            result = ToolResult(
                success=False,
                tool_name=decision.action,
                markdown=f"Tool timed out after {_TOOL_TIMEOUT}s",
                error=f"Timeout after {_TOOL_TIMEOUT}s",
            )
        except Exception as exc:
            result = ToolResult(
                success=False,
                tool_name=decision.action,
                markdown=f"Tool execution error: {str(exc)[:200]}",
                error=str(exc)[:500],
            )

        elapsed = time.monotonic() - step_start

        return AnalysisStep(
            step_number=iteration,
            reasoning=decision.reasoning,
            tool_name=decision.action,
            result=result,
            elapsed_seconds=round(elapsed, 3),
        )

    async def _run_fallback(self) -> None:
        """Deterministic minimal analysis without LLM decisions."""
        logger.info("[react] Running deterministic fallback analysis")

        # Step 1: Extract data
        await self._run_fallback_tool(
            "extract_numeric_data",
            "Fallback: extracting numeric data from evidence",
        )

        # Step 2: Statistical summary (if data available)
        if self._notebook.has_data:
            await self._run_fallback_tool(
                "statistical_summary",
                "Fallback: computing statistical summary",
            )

        # Step 3: SQL query (always works)
        await self._run_fallback_tool(
            "query_evidence_sql",
            "Fallback: SQL tier distribution",
        )

    async def _run_fallback_tool(
        self, tool_name: str, reasoning: str,
    ) -> None:
        """Execute a single tool as part of fallback analysis."""
        tool = self._registry.get_tool(tool_name)
        if not tool or not tool.execute:
            return
        try:
            result = await asyncio.wait_for(
                tool.execute(
                    evidence_store=self._evidence_store,
                    data_points=self._notebook.data_points,
                    client=self._client,
                ),
                timeout=_TOOL_TIMEOUT,
            )
            step = AnalysisStep(
                step_number=self._notebook.step_count + 1,
                reasoning=reasoning,
                tool_name=tool_name,
                result=result,
                elapsed_seconds=0.0,
            )
            self._notebook.add_step(step)
        except Exception as exc:
            logger.warning(
                "[react] Fallback %s failed: %s", tool_name, str(exc)[:200],
            )

    async def _interpret_results(self) -> None:
        """Use Qwen's reasoning to interpret raw tool outputs into insights.

        This is the critical step that separates "regex + scipy" from
        "analyst with reasoning." The LLM reads the raw extraction +
        statistics and produces:
        - Technology-level comparison (not URL-level)
        - Key findings with specific numbers and [CITE:ev_xxx] tokens
        - Cost-effectiveness ranking
        - Insights the section writer can directly use

        Uses generate() (prose mode) — NOT generate_structured() — because
        we want rich markdown with inline citations, not constrained JSON.
        """
        # Build evidence ID → short label mapping for the prompt
        ev_labels = {}
        for step in self._notebook.steps:
            if not step.result.success:
                continue
            for dp in step.result.data_points_produced:
                eid = dp.get("evidence_id", "")
                if eid and eid not in ev_labels:
                    # Build a useful label from the evidence
                    ev = self._evidence_store.get(eid, {})
                    title = ev.get("source_title", "")[:60]
                    ev_labels[eid] = title or eid[:16]

        # Collect data points with FULL evidence context (not truncated labels)
        # This prevents Qwen from misinterpreting "40% less expensive" as
        # "40% removal" — the full statement provides the semantic context.
        dp_lines = []
        seen_ev = set()
        for dp in self._notebook.data_points[:60]:
            eid = dp.get("evidence_id", "")
            value = dp.get("value", "")
            unit = dp.get("unit", "")

            # Pre-format large numbers for readability
            try:
                num = float(str(value).replace(",", ""))
                if abs(num) >= 1e9:
                    value = f"~${num / 1e9:.2f} billion" if unit == "USD" else f"~{num / 1e9:.2f}B"
                elif abs(num) >= 1e6:
                    value = f"~${num / 1e6:.1f} million" if unit == "USD" else f"~{num / 1e6:.1f}M"
            except (ValueError, TypeError):
                pass

            # Include the FULL evidence statement (not truncated label)
            # so Qwen can read "40% less expensive" not just "GAC was: 40%"
            ev = self._evidence_store.get(eid, {})
            stmt = ev.get("statement", "")[:150]

            if eid and eid not in seen_ev:
                dp_lines.append(
                    f"- {value} {unit} — \"{stmt}\" [{eid}]"
                )
                seen_ev.add(eid)
            elif eid:
                # Same evidence, different data point — just note the value
                dp_lines.append(f"  also: {value} {unit} [{eid}]")

        raw_data = "\n".join(dp_lines) if dp_lines else "No structured data."

        # Collect raw stats
        stats_text = ""
        for step in self._notebook.steps:
            if step.result.success and step.result.statistics:
                stats_text += (
                    f"\n{step.tool_name}: "
                    f"{json.dumps(step.result.statistics, default=str)[:300]}"
                )

        prompt = (
            f"You are a research analyst. Interpret the following raw data "
            f"to answer the research question.\n\n"
            f"RESEARCH QUESTION: {self._query}\n\n"
            f"RAW EXTRACTED DATA ({len(self._notebook.data_points)} points):\n"
            f"{raw_data}\n\n"
            f"STATISTICS:\n{stats_text}\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Group findings by TECHNOLOGY or METHOD (e.g., 'Reverse "
            f"Osmosis', 'Granular Activated Carbon', 'Ion Exchange'), NOT "
            f"by source URL\n"
            f"2. For each technology, state: effectiveness (with numbers), "
            f"cost (if available), limitations\n"
            f"3. Rank technologies by effectiveness AND affordability\n"
            f"4. For EVERY claim with a number, cite the source using "
            f"[CITE:ev_xxx] format with the evidence ID from the data\n"
            f"5. Identify what the data does NOT tell us (gaps)\n"
            f"6. Be specific — never say 'several studies show' without "
            f"numbers and citations\n"
            f"7. READ THE QUOTED STATEMENT carefully before interpreting "
            f"each number. '40% less expensive' is a COST metric, NOT a "
            f"removal rate. '7.2% CAGR' is market growth, NOT removal\n"
            f"8. Do NOT create false ranges from separate sources. If one "
            f"study reports 2 kWh and another reports 313 kWh, those are "
            f"TWO separate findings, not a '2-313 kWh range'\n"
            f"9. Format large numbers readably: $2.09 billion NOT "
            f"$2,089,500,000. Use B/M suffixes for billions/millions\n"
            f"10. ONLY cite evidence IDs starting with 'ev_'. NEVER cite "
            f"tool names\n\n"
            f"Produce 300-600 words of curated analysis with inline "
            f"citations. NO raw data dumps, NO tables — just analytical "
            f"prose with specific numbers."
        )

        system = (
            "You are a senior research analyst producing publication-quality "
            "insights. Every claim must have a specific number and a "
            "[CITE:ev_xxx] citation. Be concise, analytical, and critical."
        )

        interpret_timeout = int(os.getenv("PG_REACT_INTERPRET_TIMEOUT", "180"))
        try:
            response = await asyncio.wait_for(
                self._client.generate(
                    prompt=prompt,
                    system=system,
                    max_tokens=4096,
                    temperature=0.3,
                    timeout=interpret_timeout,
                ),
                timeout=interpret_timeout + 30,
            )

            content = response.content.strip()
            if not content or len(content) < 100:
                logger.warning(
                    "[react] Interpretation produced too little content: "
                    "%d chars", len(content),
                )
                return

            # Validate: extract ALL [CITE:xxx] tokens and check they exist
            all_cited = re.findall(r'\[CITE:([^\]]+)\]', content)
            valid_ids = [
                eid for eid in all_cited
                if eid in self._evidence_store
            ]
            phantom_ids = [
                eid for eid in all_cited
                if eid not in self._evidence_store
            ]

            if phantom_ids:
                logger.warning(
                    "[react] Interpretation has %d phantom citations: %s",
                    len(phantom_ids), phantom_ids[:5],
                )
                # Remove phantom citations from output
                for pid in set(phantom_ids):
                    content = content.replace(f"[CITE:{pid}]", "")

            # Post-interpretation claim verification: check that numbers
            # near each [CITE:ev_xxx] actually appear in that evidence.
            # This catches "40% removal" when evidence says "40% cheaper".
            mismatches = self._verify_interpretation_claims(content)
            if mismatches:
                logger.warning(
                    "[react] Interpretation has %d claim mismatches",
                    len(mismatches),
                )
                # Append warnings to the content so the section writer
                # can see which claims may be inaccurate
                warning_lines = ["\n\n**Verification Notes:**"]
                for mm in mismatches[:5]:
                    warning_lines.append(
                        f"- Claim \"{mm['claim'][:60]}\" cites {mm['ev_id'][:20]} "
                        f"which says: \"{mm['ev_statement'][:80]}\""
                    )
                content += "\n".join(warning_lines)

            # Add as the final step in the notebook
            step = AnalysisStep(
                step_number=self._notebook.step_count + 1,
                reasoning="LLM interpretation of raw analysis results",
                tool_name="interpret_results",
                result=ToolResult(
                    success=True,
                    tool_name="interpret_results",
                    markdown=content,
                    source_evidence_ids=list(set(valid_ids)),
                    insights=[
                        "LLM-synthesized analysis with per-claim citations",
                    ],
                ),
                elapsed_seconds=0.0,
            )
            self._notebook.add_step(step)

            logger.info(
                "[react] Interpretation complete: %d chars, %d citations "
                "(%d valid, %d phantom)",
                len(content), len(all_cited), len(valid_ids),
                len(phantom_ids),
            )

        except Exception as exc:
            logger.warning(
                "[react] Interpretation failed: %s: %s",
                type(exc).__name__, str(exc)[:200],
            )

    def _verify_interpretation_claims(self, content: str) -> list[dict]:
        """Lightweight post-interpretation verification.

        For each [CITE:ev_xxx] in the output, extract the number closest
        to it and check if that number appears in the cited evidence
        statement. If not, flag as a potential misinterpretation.

        This catches "GAC 40% removal" when evidence says "40% cheaper"
        because the number 40 IS in the evidence but the surrounding
        words don't match. For that we check if the claim sentence and
        evidence share a key descriptor (removal/cost/efficiency/etc).
        """
        mismatches = []

        # Find all citation contexts: text before [CITE:ev_xxx]
        pattern = re.compile(
            r'([^.!?\n]{10,120})\[CITE:(ev_[a-f0-9]+)\]'
        )

        for match in pattern.finditer(content):
            claim_text = match.group(1).strip()
            ev_id = match.group(2)

            if ev_id not in self._evidence_store:
                continue

            ev = self._evidence_store[ev_id]
            ev_stmt = ev.get("statement", "").lower()

            # Extract the key number from the claim (closest to the citation)
            nums_in_claim = re.findall(r'(\d+\.?\d*)', claim_text)
            if not nums_in_claim:
                continue

            # Check if the key number exists in the evidence
            key_num = nums_in_claim[-1]  # Closest to the citation
            if key_num not in ev_stmt:
                # Number not in evidence — might be derived (e.g. 15x)
                continue

            # Number IS in evidence — now check semantic match
            # Define category keywords
            cost_words = {"cost", "price", "expensive", "affordable",
                          "budget", "spending", "allocated", "funding",
                          "billion", "million", "usd", "$"}
            removal_words = {"removal", "removed", "efficiency", "reduction",
                             "achieved", "treatment", "filtration", "adsorption"}
            market_words = {"market", "share", "cagr", "growth", "valued",
                            "projected", "revenue"}

            claim_lower = claim_text.lower()
            claim_is_cost = any(w in claim_lower for w in cost_words)
            claim_is_removal = any(w in claim_lower for w in removal_words)
            claim_is_market = any(w in claim_lower for w in market_words)

            ev_is_cost = any(w in ev_stmt for w in cost_words)
            ev_is_removal = any(w in ev_stmt for w in removal_words)
            ev_is_market = any(w in ev_stmt for w in market_words)

            # Flag if categories don't match (cost claim citing removal ev)
            category_mismatch = False
            if claim_is_removal and ev_is_cost and not ev_is_removal:
                category_mismatch = True
            if claim_is_cost and ev_is_removal and not ev_is_cost:
                category_mismatch = True
            if claim_is_removal and ev_is_market and not ev_is_removal:
                category_mismatch = True

            if category_mismatch:
                mismatches.append({
                    "claim": claim_text,
                    "ev_id": ev_id,
                    "ev_statement": ev.get("statement", ""),
                    "claim_category": (
                        "cost" if claim_is_cost else
                        "removal" if claim_is_removal else
                        "market" if claim_is_market else "other"
                    ),
                    "ev_category": (
                        "cost" if ev_is_cost else
                        "removal" if ev_is_removal else
                        "market" if ev_is_market else "other"
                    ),
                })

        return mismatches

    def _is_sufficient(self) -> bool:
        """Check if analysis has enough results to stop.

        Requires at least 3 successful steps AND both statistics and
        a comparison/meta tool. This prevents early stopping after
        just extract + stats.
        """
        successful = [
            s for s in self._notebook.steps if s.result.success
        ]

        if len(successful) < 3:
            return False

        has_stats = any(
            s.tool_name in ("statistical_summary", "query_evidence_sql")
            for s in successful
        )
        has_comparison = any(
            s.tool_name in (
                "comparison_table", "meta_analysis", "execute_python",
                "rank_by_impact",
            )
            for s in successful
        )

        return has_stats and has_comparison
