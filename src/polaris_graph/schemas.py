"""
Pydantic schemas for polaris graph structured LLM outputs.

These are the contracts between the LLM and the pipeline.
Used with OpenRouter's json_schema response_format.
"""

import json
import logging
import os
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Query Planning
# ---------------------------------------------------------------------------

class SubQuery(BaseModel):
    """A single sub-query for search."""

    query: str = Field(description="The search query string")
    intent: str = Field(description="What this query is trying to find", default="")
    source_preference: str = Field(
        description="Preferred source type: 'web', 'academic', 'both'",
        default="both",
    )
    perspective: str = Field(
        description="STORM perspective: Scientific, Regulatory, Industry, "
        "Economic, Public_Health, Historical, Regional, "
        "Methodological, Emerging_Trends",
        default="General",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_subquery_fields(cls, data):
        """FIX-GEMMA4: Handle alternative field names from different models."""
        if isinstance(data, dict):
            for alt in ("description", "purpose", "goal", "objective"):
                if alt in data and "intent" not in data:
                    data["intent"] = data.pop(alt)
            for alt in ("search_query", "text", "q"):
                if alt in data and "query" not in data:
                    data["query"] = data.pop(alt)
            if data.get("intent") is None:
                data["intent"] = ""
            if data.get("source_preference") is None:
                data["source_preference"] = "both"
        elif isinstance(data, str):
            data = {"query": data, "intent": ""}
        return data


class QueryPlan(BaseModel):
    """Full query plan output from the planner."""

    analysis: str = Field(
        description="Brief analysis of the research question",
        default="",
    )
    search_strategy: str = Field(
        description="Overall strategy: 'broad', 'deep', 'academic_focus'",
        default="broad",
    )
    sub_queries: list[SubQuery] = Field(
        description="List of sub-queries to execute",
        default_factory=list,
    )
    key_concepts: list[str] = Field(
        description="Key concepts and entities to look for",
        default_factory=list,
    )
    expected_source_types: list[str] = Field(
        description="Expected types of sources: journal, government, industry, etc.",
        default_factory=list,
    )
    perspective_coverage: dict[str, int] = Field(
        description="Count of queries per STORM perspective",
        default_factory=dict,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """Handle LLM variant field names and nulls."""
        if isinstance(data, dict):
            for alt in ("queries", "search_queries"):
                if alt in data and "sub_queries" not in data:
                    data["sub_queries"] = data.pop(alt)
            for alt in ("strategy", "approach"):
                if alt in data and "search_strategy" not in data:
                    data["search_strategy"] = data.pop(alt)
            for alt in ("concepts", "key_terms", "keywords"):
                if alt in data and "key_concepts" not in data:
                    data["key_concepts"] = data.pop(alt)
            # Null defaults
            if data.get("search_strategy") is None:
                data["search_strategy"] = "broad"
            if data.get("sub_queries") is None:
                data["sub_queries"] = []
            if data.get("key_concepts") is None:
                data["key_concepts"] = []
            if data.get("expected_source_types") is None:
                data["expected_source_types"] = []
            if data.get("perspective_coverage") is None:
                data["perspective_coverage"] = {}
            # FIX-GEMMA4: Coerce list to dict for perspective_coverage
            pc = data.get("perspective_coverage")
            if isinstance(pc, list):
                data["perspective_coverage"] = {str(p): 1 for p in pc if p}
        return data

    @model_validator(mode="after")
    def reject_empty_queries(self):
        """FIX-SD2: Reject empty query plans — forces LLM retry."""
        if not self.sub_queries:
            raise ValueError(
                "QueryPlan.sub_queries is empty — LLM must generate at least 1 query"
            )
        return self


# ---------------------------------------------------------------------------
# Evidence Extraction
# ---------------------------------------------------------------------------

class AtomicFact(BaseModel):
    """A single atomic fact extracted from a source."""

    statement: str = Field(
        description="The factual claim, one sentence",
        default="",
    )
    direct_quote: str = Field(
        description="Exact quote from source supporting this fact",
        default="",
    )
    fact_category: str = Field(
        description="Category: statistic, measurement, causal_link, "
        "named_entity, date_time, regulatory_threshold, "
        "standard_reference, geographic, methodology",
        default="other",
    )
    relevance_score: float = Field(
        description="Relevance to the research question, 0.0 to 1.0",
        default=0.1,
    )
    confidence: float = Field(
        description="Confidence that this fact is correctly extracted, 0.0 to 1.0",
        default=0.1,
    )
    perspective: str = Field(
        description="STORM research perspective: Scientific, Regulatory, Industry, "
        "Economic, Public_Health, Historical, Regional, Methodological, Emerging_Trends",
        default="Scientific",
    )
    # MESH-UNIT3: surface forms of key named entities mentioned in the
    # fact. Populated by the wiki mesh extraction path (claim_extract.py)
    # which asks the LLM for this list as part of ANALYSIS_SYSTEM + a
    # mesh-side suffix. Legacy production extraction does NOT set this
    # field — the `normalize_field_names` validator below defaults it to
    # `[]` so backward-compat holds for all 40+ prior runs.
    entities: list[str] = Field(
        description="Key named entities (compounds, methods, organizations, "
        "metrics) mentioned in this fact. Used by the wiki mesh entity "
        "canonicalization pass. Optional; legacy data defaults to [].",
        default_factory=list,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """LLM uses variant field names and returns null — normalize them."""
        if isinstance(data, dict):
            # Map alternative names for statement
            for alt in (
                "claim", "description", "text", "finding",
                "fact_statement", "fact", "fact_text", "content",
            ):
                if alt in data and "statement" not in data:
                    data["statement"] = data.pop(alt)
            # If still no statement, construct from direct_quote
            if "statement" not in data and "direct_quote" in data and data["direct_quote"]:
                data["statement"] = str(data["direct_quote"])[:200]
            # Map alternative names for direct_quote
            for alt in ("quote", "excerpt", "source_quote", "evidence"):
                if alt in data and "direct_quote" not in data:
                    data["direct_quote"] = data.pop(alt)
            # FIX-303: Normalize perspective field
            for alt in ("research_perspective", "category_perspective", "viewpoint"):
                if alt in data and "perspective" not in data:
                    data["perspective"] = data.pop(alt)
            # MESH-UNIT3: normalize `entities` list. Accept list, None, or
            # string (comma-separated). Anything else → []. This is
            # load-bearing for backward compat: legacy production data
            # has no `entities` key at all, so `data.get("entities")` is
            # None and we default to [].
            for alt in ("entity_mentions", "named_entities", "mentions"):
                if alt in data and "entities" not in data:
                    data["entities"] = data.pop(alt)
            raw_entities = data.get("entities")
            if raw_entities is None:
                data["entities"] = []
            elif isinstance(raw_entities, str):
                data["entities"] = [
                    e.strip() for e in raw_entities.split(",") if e.strip()
                ]
            elif isinstance(raw_entities, list):
                # Coerce each element to a trimmed non-empty string.
                data["entities"] = [
                    str(e).strip() for e in raw_entities
                    if e is not None and str(e).strip()
                ]
            else:
                # Unknown type (dict, int, etc.) — fall back to []
                data["entities"] = []
            # Replace null values with safe defaults — SF-04: unknown scores
            # default to LOW (0.1), not MID (0.5), to avoid inflating BRONZE
            # evidence to SILVER-quality scores.
            # AREA-9: Log warnings when null values received (silent default detection)
            _null_defaults = {
                "statement": "",
                "direct_quote": "",
                "fact_category": "other",
                "relevance_score": 0.1,
                "confidence": 0.1,
                "perspective": "Scientific",
            }
            _warn_on_null = {"relevance_score", "confidence"}
            for field, default in _null_defaults.items():
                if data.get(field) is None:
                    if field in _warn_on_null:
                        logger.warning(
                            "[polaris graph] AREA-9: AtomicFact.%s is null for "
                            "'%s' — defaulting to %.1f (LLM returned null score)",
                            field,
                            str(data.get("statement", ""))[:60],
                            default,
                        )
                    data[field] = default
        return data

    @field_validator("relevance_score", "confidence", mode="before")
    @classmethod
    def clamp_scores(cls, v):
        """Clamp to 0-1 range; parse strings; LLM sometimes returns percentages (0-100)."""
        if isinstance(v, (int, float)):
            if v > 1.0:
                return v / 100.0
            return max(0.0, min(1.0, float(v)))
        # SF-05: Parse string scores before defaulting (e.g. "0.8" → 0.8)
        if isinstance(v, str):
            try:
                parsed = float(v)
                if parsed > 1.0:
                    return parsed / 100.0
                return max(0.0, min(1.0, parsed))
            except (ValueError, TypeError):
                logger.warning("[polaris graph] Non-numeric score '%s', defaulting to 0.1", v)
                return 0.1
        logger.warning("[polaris graph] Unexpected score type %s, defaulting to 0.1", type(v).__name__)
        return 0.1


class SourceAnalysis(BaseModel):
    """Analysis of a single source document."""

    source_url: str = Field(description="URL of the source")
    source_title: str = Field(description="Title of the source")
    source_type: str = Field(
        description="Type: journal_article, government_report, "
        "industry_report, news, standard, patent, book, other",
        default="web",
    )
    source_quality: float = Field(
        description="Overall quality score 0.0 to 1.0",
        default=0.1,
    )
    overall_relevance: float = Field(
        description="Overall relevance to the research question, 0.0 to 1.0",
        default=0.1,
    )
    year: Optional[int] = Field(description="Publication year, 0 if unknown", default=0)
    authors: list[str] = Field(
        description="Author names", default_factory=list
    )
    venue: str = Field(description="Publication venue", default="")
    doi: str = Field(description="DOI if available", default="")
    atomic_facts: list[AtomicFact] = Field(
        description="All atomic facts extracted from this source",
        default_factory=list,
    )
    evidence_summary: str = Field(
        description="Brief summary of what this source contributes",
        default="",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """LLM uses variant field names and returns null — normalize them."""
        if isinstance(data, dict):
            # FIX-GEMMA4: Map alternative names for source_url
            for alt in ("url", "link", "page_url"):
                if alt in data and "source_url" not in data:
                    data["source_url"] = data.pop(alt)
            # FIX-GEMMA4: Map alternative names for source_title
            for alt in ("title", "page_title", "name", "document_title"):
                if alt in data and "source_title" not in data:
                    data["source_title"] = data.pop(alt)
            # FIX-GEMMA4: Map alternative names for source_type
            for alt in ("type", "document_type", "content_type"):
                if alt in data and "source_type" not in data:
                    data["source_type"] = data.pop(alt)
            # Map alternative names for atomic_facts
            for alt in (
                "relevant_facts", "extracted_facts", "facts",
                "evidence_facts", "key_facts", "findings",
            ):
                if alt in data and "atomic_facts" not in data:
                    data["atomic_facts"] = data.pop(alt)
            # FIX-SCHEMA-1: Coerce authors from string to list
            # LLM sometimes returns "Smith J, Jones A" instead of ["Smith J", "Jones A"]
            authors_val = data.get("authors")
            if isinstance(authors_val, str):
                data["authors"] = [a.strip() for a in authors_val.split(",") if a.strip()]
            # FIX-SCHEMA-2: Coerce atomic_facts items from strings to dicts
            # LLM sometimes simplifies facts to plain strings
            facts = data.get("atomic_facts")
            if isinstance(facts, list):
                coerced = []
                for f in facts:
                    if isinstance(f, str) and f.strip():
                        coerced.append({
                            "statement": f.strip(),
                            "direct_quote": f.strip()[:200],
                            "fact_category": "other",
                            "relevance_score": 0.1,
                            "confidence": 0.1,
                        })
                    else:
                        coerced.append(f)
                data["atomic_facts"] = coerced
            # FIX-SCHEMA-3: Coerce source_quality/overall_relevance from word strings
            # LLM sometimes returns "high", "moderate", "low" instead of floats
            _word_to_score = {
                "high": 0.8, "very high": 0.9, "excellent": 0.95,
                "moderate": 0.5, "medium": 0.5, "average": 0.5,
                "low": 0.2, "very low": 0.1, "poor": 0.1,
            }
            for score_field in ("source_quality", "overall_relevance"):
                val = data.get(score_field)
                if isinstance(val, str):
                    lower = val.strip().lower()
                    if lower in _word_to_score:
                        data[score_field] = _word_to_score[lower]
                    else:
                        try:
                            data[score_field] = float(val)
                        except (ValueError, TypeError):
                            logger.warning(
                                "[polaris graph] FIX-SD1: SourceAnalysis.%s is non-numeric "
                                "string '%s' — defaulting to 0.1",
                                score_field,
                                val[:60],
                            )
                            data[score_field] = 0.1
            # FIX-STORM-TYPE: Coerce evidence_summary from list/dict to string
            ev_summary = data.get("evidence_summary")
            if isinstance(ev_summary, list):
                data["evidence_summary"] = "; ".join(
                    str(item)[:200] for item in ev_summary if item
                )
            elif isinstance(ev_summary, dict):
                data["evidence_summary"] = "; ".join(
                    f"{k}: {v}" for k, v in ev_summary.items()
                )[:1000]
            # Map alternative names for evidence_summary
            for alt in ("summary", "source_summary"):
                if alt in data and "evidence_summary" not in data:
                    data["evidence_summary"] = data.pop(alt)
            # Replace null values with safe defaults (LLM frequently returns null)
            # AREA-9: Log warnings for score fields defaulting (silent default detection)
            # W3.6: When source_quality/overall_relevance are null, use a
            # type-informed default instead of a flat 0.1. A source that
            # survived retrieval + fetch + extraction is almost never
            # 0.1-quality; flat 0.1 punishes downstream ranking unfairly.
            _stype = data.get("source_type") or "web"
            _fact_count = len(data.get("atomic_facts") or [])
            _type_quality_prior = {
                "journal_article": 0.75,
                "government_report": 0.65,
                "standard": 0.65,
                "industry_report": 0.45,
                "news": 0.35,
                "book": 0.55,
                "patent": 0.50,
                "web": 0.30,
                "other": 0.30,
            }
            _q_default = _type_quality_prior.get(_stype, 0.30)
            # Relevance: if any facts were extracted the source was at least
            # tangentially on-topic; scale by fact count up to 0.6.
            _r_default = min(0.30 + 0.06 * _fact_count, 0.60) if _fact_count else 0.25

            _null_defaults = {
                "source_type": "web",
                "source_quality": _q_default,
                "overall_relevance": _r_default,
                "year": 0,
                "authors": [],
                "venue": "",
                "doi": "",
                "evidence_summary": "",
                "atomic_facts": [],
            }
            _warn_on_null = {"source_quality", "overall_relevance"}
            for field, default in _null_defaults.items():
                if data.get(field) is None:
                    if field in _warn_on_null:
                        logger.warning(
                            "[polaris graph] AREA-9/W3.6: SourceAnalysis.%s is null for "
                            "'%s' — type-informed default %.2f (type=%s, facts=%d)",
                            field,
                            str(data.get("source_url", ""))[:60],
                            default,
                            _stype,
                            _fact_count,
                        )
                    data[field] = default
        return data

    @field_validator("atomic_facts", mode="after")
    @classmethod
    def cap_atomic_facts(cls, v: list) -> list:
        """EXT-2: Deterministic cap at 15 facts per source.

        Sort by relevance_score descending, keep top 15.
        Pattern from atomic_decomposer.py:204.
        """
        max_facts = int(os.getenv("PG_MAX_FACTS_PER_SOURCE", "15"))
        if len(v) <= max_facts:
            return v
        # Sort by relevance descending, keep top max_facts
        sorted_facts = sorted(
            v,
            key=lambda f: getattr(f, "relevance_score", 0.0)
            if hasattr(f, "relevance_score")
            else (f.get("relevance_score", 0.0) if isinstance(f, dict) else 0.0),
            reverse=True,
        )
        logger.info(
            "[polaris graph] EXT-2: Capped atomic_facts %d -> %d (sorted by relevance)",
            len(v), max_facts,
        )
        return sorted_facts[:max_facts]


class SourceAnalysisBatch(BaseModel):
    """Batch of source analyses."""

    analyses: list[SourceAnalysis] = Field(
        description="Analysis results for each source",
        default_factory=list,
    )

    @model_validator(mode="before")
    @classmethod
    def filter_invalid_analyses(cls, data):
        """Skip individual analyses that fail validation instead of failing the batch.

        FIX-SCHEMA-7: Secondary defense — if analyses is a string (FIX-SCHEMA-6
        regex missed), try to reconstruct the array from top-level keys.
        """
        if isinstance(data, dict):
            # FIX-GEMMA4: Map alternative names for analyses
            for alt in ("results", "source_analyses", "analysis_results",
                        "sources", "source_results"):
                if alt in data and "analyses" not in data:
                    data["analyses"] = data.pop(alt)
            if data.get("analyses") is None:
                data["analyses"] = []
        if isinstance(data, dict) and "analyses" in data:
            raw = data["analyses"]
            # FIX-3 + FIX-SCHEMA-7: If analyses is a string, try to parse it
            # as JSON first (recovers full arrays), then fall back to top-level
            # key recovery (recovers single analysis).
            if isinstance(raw, str):
                logger.error(
                    "[polaris graph] FIX-SCHEMA-7: analyses is STRING (%d chars, "
                    "first 20: %r) — attempting multi-strategy recovery.",
                    len(raw), raw[:20],
                )
                recovered_from_json = False

                # FIX-3: Strategy 0 — try json.loads on the raw string.
                # Handles cases where analyses is a serialized JSON array
                # e.g. ":[{...}, {...}]" or "[{...}]"
                try:
                    # Strip leading punctuation artifacts (e.g. ":[" prefix)
                    clean_raw = raw.lstrip(":").strip()
                    parsed_raw = json.loads(clean_raw)
                    if isinstance(parsed_raw, list):
                        data["analyses"] = parsed_raw
                        recovered_from_json = True
                        logger.info(
                            "[polaris graph] FIX-3: Recovered %d analyses from "
                            "JSON string parsing",
                            len(parsed_raw),
                        )
                    elif isinstance(parsed_raw, dict):
                        data["analyses"] = [parsed_raw]
                        recovered_from_json = True
                        logger.info(
                            "[polaris graph] FIX-3: Recovered 1 analysis from "
                            "JSON string parsing (dict)",
                        )
                except (json.JSONDecodeError, ValueError):
                    pass

                # FIX-SCHEMA-7: Strategy 1 — recover from top-level keys
                if not recovered_from_json:
                    recovery_keys = {
                        "source_url", "source_title", "source_type",
                        "source_quality", "overall_relevance", "year",
                        "authors", "venue", "doi", "atomic_facts",
                        "evidence_summary",
                    }
                    recovered = {k: v for k, v in data.items() if k in recovery_keys}
                    if recovered.get("source_url"):
                        data["analyses"] = [recovered]
                        # Clean recovered keys from top level
                        for k in recovery_keys:
                            data.pop(k, None)
                        logger.info(
                            "[polaris graph] FIX-SCHEMA-7: Recovered 1 analysis from "
                            "top-level keys: %s",
                            recovered.get("source_url", "?")[:60],
                        )
                    else:
                        logger.error(
                            "[polaris graph] FIX-SD4: SourceAnalysisBatch string recovery "
                            "FAILED — no source_url in top-level keys. Raw preview: %r",
                            raw[:300],
                        )
                        data["analyses"] = []

            valid = []
            dropped = 0
            original_count = len(data["analyses"])
            for item in data["analyses"]:
                if not isinstance(item, dict):
                    dropped += 1
                    continue
                try:
                    SourceAnalysis.model_validate(item)
                    valid.append(item)
                except Exception as exc:
                    dropped += 1
                    logger.warning(
                        "[polaris graph] AREA-9: Dropped analysis for '%s': %s",
                        item.get("source_url", "?")[:60],
                        str(exc)[:200],
                    )
            if dropped > 0:
                logger.warning(
                    "[polaris graph] AREA-9: SourceAnalysisBatch dropped %d/%d analyses",
                    dropped, original_count,
                )
            data["analyses"] = valid
        return data


# ---------------------------------------------------------------------------
# Evidence Clustering
# ---------------------------------------------------------------------------

class EvidenceCluster(BaseModel):
    """A cluster of related evidence pieces."""

    cluster_id: str = Field(description="Unique cluster identifier")
    theme: str = Field(description="Theme or topic of this cluster")
    description: str = Field(
        description="Brief description of what this cluster covers"
    )
    evidence_ids: list[str] = Field(
        description="IDs of evidence pieces in this cluster",
        default_factory=list,
    )
    strength: str = Field(
        description="Evidence strength: 'strong', 'moderate', 'weak'",
        default="moderate",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_cluster_fields(cls, data):
        """FIX-CITE-2 + FIX-GEMMA4: Normalize variant field names for clusters."""
        if isinstance(data, dict):
            # section_title / title / name → theme
            for alt in ("section_title", "title", "name", "topic", "label", "heading"):
                if alt in data and "theme" not in data:
                    data["theme"] = data.pop(alt)
            # id / index / number → cluster_id
            for alt in ("id", "index", "number", "group_id"):
                if alt in data and "cluster_id" not in data:
                    data["cluster_id"] = str(data.pop(alt))
            # FIX-GEMMA4: Map alternative names for description
            for alt in ("summary", "overview", "detail", "content"):
                if alt in data and "description" not in data:
                    data["description"] = data.pop(alt)
            # FIX-GEMMA4: Map alternative names for evidence_ids
            for alt in ("members", "items", "ids", "member_ids", "evidence"):
                if alt in data and "evidence_ids" not in data:
                    data["evidence_ids"] = data.pop(alt)
            # FIX-GEMMA4: Map alternative names for strength
            for alt in ("evidence_strength", "quality", "confidence"):
                if alt in data and "strength" not in data:
                    data["strength"] = data.pop(alt)
            # Auto-generate cluster_id from theme if missing
            if "cluster_id" not in data and "theme" in data:
                data["cluster_id"] = f"c_{data['theme'][:20].lower().replace(' ', '_')}"
            # Null defaults
            if data.get("evidence_ids") is None:
                data["evidence_ids"] = []
            if data.get("strength") is None:
                data["strength"] = "moderate"
        return data

    @field_validator("cluster_id", mode="before")
    @classmethod
    def coerce_cluster_id(cls, v):
        """LLM sometimes returns int cluster IDs instead of strings."""
        return str(v)

    @field_validator("evidence_ids", mode="before")
    @classmethod
    def coerce_evidence_ids(cls, v):
        """Coerce any int evidence IDs to strings."""
        if isinstance(v, list):
            return [str(x) for x in v]
        return v


class ClusterPlan(BaseModel):
    """Plan for organizing evidence into clusters."""

    clusters: list[EvidenceCluster] = Field(
        description="Evidence clusters organized by theme"
    )
    uncovered_aspects: list[str] = Field(
        description="Aspects of the query not well-covered by evidence",
        default_factory=list,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """FIX-GEMMA4: Handle alternative field names from different models."""
        if isinstance(data, dict):
            for alt in ("groups", "categories", "themes", "evidence_clusters"):
                if alt in data and "clusters" not in data:
                    data["clusters"] = data.pop(alt)
            for alt in ("gaps", "missing_aspects", "uncovered", "not_covered"):
                if alt in data and "uncovered_aspects" not in data:
                    data["uncovered_aspects"] = data.pop(alt)
            if data.get("clusters") is None:
                data["clusters"] = []
            if data.get("uncovered_aspects") is None:
                data["uncovered_aspects"] = []
        return data


# ---------------------------------------------------------------------------
# Map-Reduce Clustering (SOTA pattern — GraphRAG / LLMxMapReduce)
# ---------------------------------------------------------------------------

class ThemeResult(BaseModel):
    """A single theme identified from a batch of evidence.

    Used by the map step of map-reduce clustering. Each batch of ~100
    evidence pieces produces 5-8 themes with evidence assignments and
    helpfulness scores.
    """

    theme: str = Field(description="Theme or topic label")
    description: str = Field(
        description="Brief description of what this theme covers",
        default="",
    )
    evidence_ids: list[str] = Field(
        description="IDs of evidence pieces belonging to this theme",
        default_factory=list,
    )
    key_claims: list[str] = Field(
        description="Top 3 representative claims for this theme",
        default_factory=list,
    )
    helpfulness: int = Field(
        description="GraphRAG-style helpfulness score 0-100",
        default=50,
        ge=0,
        le=100,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """FIX-GEMMA4: Handle alternative field names from different models."""
        if isinstance(data, dict):
            for alt in ("title", "name", "topic", "label", "section_title"):
                if alt in data and "theme" not in data:
                    data["theme"] = data.pop(alt)
            for alt in ("summary", "overview", "detail", "content"):
                if alt in data and "description" not in data:
                    data["description"] = data.pop(alt)
            for alt in ("ids", "members", "items", "evidence", "member_ids"):
                if alt in data and "evidence_ids" not in data:
                    data["evidence_ids"] = data.pop(alt)
            for alt in ("claims", "representative_claims", "top_claims"):
                if alt in data and "key_claims" not in data:
                    data["key_claims"] = data.pop(alt)
            for alt in ("score", "relevance_score", "importance"):
                if alt in data and "helpfulness" not in data:
                    data["helpfulness"] = data.pop(alt)
            # Null defaults
            if data.get("description") is None:
                data["description"] = ""
            if data.get("evidence_ids") is None:
                data["evidence_ids"] = []
            if data.get("key_claims") is None:
                data["key_claims"] = []
            if data.get("helpfulness") is None:
                data["helpfulness"] = 50
        return data

    @field_validator("evidence_ids", mode="before")
    @classmethod
    def coerce_evidence_ids(cls, v):
        """Coerce any int evidence IDs to strings."""
        if isinstance(v, list):
            return [str(x) for x in v]
        return v

    @field_validator("helpfulness", mode="before")
    @classmethod
    def coerce_helpfulness(cls, v):
        """Handle string/float helpfulness values."""
        if isinstance(v, str):
            try:
                return int(float(v))
            except (ValueError, TypeError):
                return 50
        if isinstance(v, float):
            return int(v)
        return v


class BatchClusterResult(BaseModel):
    """Result of clustering a single batch of evidence (map step).

    Each batch produces 5-8 local themes that are later merged in
    the reduce step to form the final ClusterPlan.
    """

    themes: list[ThemeResult] = Field(
        description="Themes identified in this batch",
        default_factory=list,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """Handle LLM variant field names and nulls."""
        if isinstance(data, dict):
            for alt in ("clusters", "groups", "categories", "topics"):
                if alt in data and "themes" not in data:
                    data["themes"] = data.pop(alt)
            if data.get("themes") is None:
                data["themes"] = []
        return data


# ---------------------------------------------------------------------------
# Claim Verification
# ---------------------------------------------------------------------------

class ClaimVerification(BaseModel):
    """Verification result for a single claim.

    AREA-1: Reasoning field removed — reasoning now happens in
    reasoning_content (model's chain-of-thought), not duplicated in JSON output.
    This cuts output tokens per batch by ~30%.
    """

    claim: str = Field(description="The claim being verified")
    verdict: str = Field(
        description="Verdict: 'SUPPORTED', 'PARTIALLY_SUPPORTED', 'NOT_SUPPORTED'"
    )
    confidence: float = Field(
        description="Verification confidence 0.0 to 1.0",
        default=0.0,
    )
    supporting_evidence: list[str] = Field(
        description="Evidence IDs that support this claim",
        default_factory=list,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_and_strip_legacy(cls, data):
        """FIX-GEMMA4: Normalize field names + strip legacy reasoning field."""
        if isinstance(data, dict):
            # Accept but discard reasoning field (backward compat)
            data.pop("reasoning", None)
            # Map alternative names for verdict
            for alt in ("is_faithful", "result", "status", "judgment", "judgement", "verification"):
                if alt in data and "verdict" not in data:
                    val = data.pop(alt)
                    # Coerce bool is_faithful to verdict string
                    if isinstance(val, bool):
                        data["verdict"] = "SUPPORTED" if val else "NOT_SUPPORTED"
                    else:
                        data["verdict"] = val
            # Map alternative names for claim
            for alt in ("statement", "text", "assertion"):
                if alt in data and "claim" not in data:
                    data["claim"] = data.pop(alt)
            # Map alternative names for supporting_evidence
            for alt in ("evidence", "evidence_ids", "sources", "support"):
                if alt in data and "supporting_evidence" not in data:
                    data["supporting_evidence"] = data.pop(alt)
            # Null defaults
            if data.get("confidence") is None:
                data["confidence"] = 0.0
            if data.get("supporting_evidence") is None:
                data["supporting_evidence"] = []
            # Normalize verdict strings
            v = data.get("verdict")
            if isinstance(v, str):
                v_upper = v.strip().upper().replace(" ", "_")
                _aliases = {
                    "TRUE": "SUPPORTED", "YES": "SUPPORTED", "CONFIRMED": "SUPPORTED",
                    "PARTIAL": "PARTIALLY_SUPPORTED", "PARTIALLY": "PARTIALLY_SUPPORTED",
                    "FALSE": "NOT_SUPPORTED", "NO": "NOT_SUPPORTED",
                    "UNSUPPORTED": "NOT_SUPPORTED", "REFUTED": "NOT_SUPPORTED",
                }
                if v_upper in _aliases:
                    data["verdict"] = _aliases[v_upper]
                elif v_upper in ("SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED"):
                    data["verdict"] = v_upper
        return data


class VerificationBatch(BaseModel):
    """Batch verification results."""

    verifications: list[ClaimVerification] = Field(
        description="Verification results for each claim",
        default_factory=list,
    )
    overall_faithfulness: float = Field(
        description="Overall faithfulness score 0.0 to 1.0",
        default=0.0,
    )

    @model_validator(mode="before")
    @classmethod
    def filter_invalid_verifications(cls, data):
        """Skip individual verifications that fail validation.

        FIX-V2: Multi-strategy string recovery for spurious-quote patterns.
        FIX-GEMMA4: Normalize alternative field names before processing.
        """
        if isinstance(data, dict):
            # FIX-GEMMA4: Map alternative names for verifications
            for alt in ("results", "claims", "verification_results", "claim_verifications"):
                if alt in data and "verifications" not in data:
                    data["verifications"] = data.pop(alt)
            # Map alternative names for overall_faithfulness
            for alt in ("faithfulness", "faithfulness_score", "overall_score", "score"):
                if alt in data and "overall_faithfulness" not in data:
                    data["overall_faithfulness"] = data.pop(alt)
            if data.get("overall_faithfulness") is None:
                data["overall_faithfulness"] = 0.0
            if data.get("verifications") is None:
                data["verifications"] = []
        if isinstance(data, dict) and "verifications" in data:
            raw = data["verifications"]
            if isinstance(raw, str):
                logger.error(
                    "[polaris graph] FIX-V2: verifications is STRING (%d chars) "
                    "— attempting multi-strategy recovery",
                    len(raw),
                )
                recovered_list = None

                # Strategy 1: Try json.loads on the string directly
                try:
                    parsed_raw = json.loads(raw)
                    if isinstance(parsed_raw, list):
                        recovered_list = parsed_raw
                        logger.info(
                            "[polaris graph] FIX-V2: Strategy 1 (json.loads) recovered "
                            "%d verifications from string",
                            len(recovered_list),
                        )
                except (json.JSONDecodeError, ValueError):
                    pass

                # Strategy 2: Extract embedded JSON objects from string
                if recovered_list is None:
                    import re as _re
                    json_objects = _re.findall(r'\{[^{}]+\}', raw)
                    if json_objects:
                        candidates = []
                        for obj_str in json_objects:
                            try:
                                obj = json.loads(obj_str)
                                if isinstance(obj, dict) and (
                                    obj.get("claim") or obj.get("verdict")
                                ):
                                    candidates.append(obj)
                            except (json.JSONDecodeError, ValueError):
                                continue
                        if candidates:
                            recovered_list = candidates
                            logger.info(
                                "[polaris graph] FIX-V2: Strategy 2 (regex extract) "
                                "recovered %d verifications from string",
                                len(recovered_list),
                            )

                # Strategy 3: Try recovery from top-level sibling keys
                if recovered_list is None:
                    recovery_keys = {"claim", "verdict", "confidence", "supporting_evidence"}
                    recovered = {k: v for k, v in data.items() if k in recovery_keys}
                    if recovered.get("claim"):
                        recovered_list = [recovered]
                        for k in recovery_keys:
                            data.pop(k, None)
                        logger.info(
                            "[polaris graph] FIX-V2: Strategy 3 (top-level keys) "
                            "recovered 1 verification",
                        )

                if recovered_list:
                    data["verifications"] = recovered_list
                else:
                    logger.error(
                        "[polaris graph] FIX-V2: All recovery strategies failed for "
                        "verifications string (%d chars, preview: %r)",
                        len(raw), raw[:200],
                    )
                    data["verifications"] = []
            valid = []
            dropped = 0
            original_count = len(data["verifications"])
            for item in data["verifications"]:
                if not isinstance(item, dict):
                    dropped += 1
                    continue
                try:
                    ClaimVerification.model_validate(item)
                    valid.append(item)
                except Exception as exc:
                    dropped += 1
                    logger.warning(
                        "[polaris graph] Dropped invalid verification: %s",
                        str(exc)[:200],
                    )
            if dropped > 0:
                logger.warning(
                    "[polaris graph] AREA-9: VerificationBatch dropped %d/%d verifications",
                    dropped, original_count,
                )
            data["verifications"] = valid
        return data


# ---------------------------------------------------------------------------
# Report Synthesis
# ---------------------------------------------------------------------------

class SectionOutlineItem(BaseModel):
    """Outline for a single report section."""

    section_id: str = Field(description="Unique section ID like 's01', 's02'")
    title: str = Field(description="Section title")
    description: str = Field(
        description="What this section should cover"
    )
    search_keywords: str = Field(
        description=(
            "Comma-separated domain-specific keywords and units for routing "
            "evidence to this section. Include technical terms, measurement "
            "units, method names, and material names that evidence chunks "
            "would contain. E.g. 'epoxy, MPa, dolly, ASTM D4541, peel strength, "
            "cohesive failure'. Do NOT repeat the section title."
        ),
        default="",
    )
    evidence_ids: list[str] = Field(
        description="Evidence IDs to cite in this section",
        default_factory=list,
    )
    target_words: int = Field(
        description="Target word count for this section, between 200-1000",
        default=600,
    )
    order: int = Field(description="Section order in the report", default=0)
    analytical_focus: Optional[str] = Field(
        description="RC-3: Primary analytical operation for this section "
        "(aggregate, compare, explain, tabulate, challenge)",
        default=None,
    )

    @field_validator("title")
    @classmethod
    def validate_section_title(cls, v: str) -> str:
        """FIX-5 + FIX-MP8: Reject generic placeholder titles.

        Fallback outlines sometimes produce titles like "Statistic", "Citation",
        or "Descriptive" that are too generic for a deep research report.
        Append a descriptive suffix to make them informative.

        FIX-MP8: Expanded from 13 stems to 23+, added single-word catch-all,
        and added minimum 3-content-word rule. In PG_TEST_033, 4 generic titles
        ("Statistic", "Finding", "Citation", "Descriptive") slipped through.
        """
        # FIX-MP8: Expanded generic stems list (catches "Citation", "Descriptive", etc.)
        generic_stems = {
            "introduction", "methodology", "method", "result",
            "discussion", "conclusion", "summary", "overview",
            "background", "analysis", "finding", "statistic",
            "recommendation", "citation", "descriptive", "reference",
            "data", "evidence", "information", "detail", "note",
            "section", "topic", "theme",
        }
        words = v.strip().split()
        if len(words) == 1:
            stem = words[0].lower().rstrip("s")
            if stem in generic_stems:
                return f"{v}: Key Findings and Analysis"

        # FIX-MP8: Titles with fewer than 3 content words are too vague
        # (stopwords don't count: "the", "of", "and", "in", "a", "for", "to")
        stopwords = {"the", "of", "and", "in", "a", "an", "for", "to", "on", "at", "by", "with"}
        content_words = [w for w in words if w.lower() not in stopwords and len(w) > 1]
        if len(content_words) < 3 and len(words) <= 3:
            stem_check = " ".join(w.lower().rstrip("s") for w in content_words)
            # Only fix if content words are all generic
            if all(w.lower().rstrip("s") in generic_stems for w in content_words):
                return f"{v}: Detailed Analysis and Implications"

        # FIX-OUTLINE: Check 2-word generic combinations from fallback outlines
        two_word_generics = {
            "risk factor", "key finding", "main result", "data analysis",
            "general discussion", "industry classification", "product information",
        }
        if len(words) == 2:
            normalized = " ".join(w.lower() for w in words)
            normalized_stripped = " ".join(w.lower().rstrip("s") for w in words)
            if normalized in two_word_generics or normalized_stripped in two_word_generics:
                return f"{v}: Detailed Analysis and Implications"
        return v

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """LLM uses variant field names — normalize them.

        FIX-CITE-2: Also normalize section_title → title (Qwen 3.5 Plus
        consistently returns section_title instead of title).
        FIX-GEMMA4: Add Gemma 4 alternatives (subpoints, word_count, etc.)
        """
        if isinstance(data, dict):
            # FIX-CITE-2: section_title / heading / name → title
            for alt in ("section_title", "heading", "name"):
                if alt in data and "title" not in data:
                    data["title"] = data.pop(alt)
            # FIX-GEMMA4: Map alternative names for description
            for alt in ("subpoints", "bullet_points", "content", "summary",
                        "overview", "scope", "coverage", "details"):
                if alt in data and "description" not in data:
                    val = data.pop(alt)
                    # Coerce list to comma-separated string
                    if isinstance(val, list):
                        data["description"] = "; ".join(str(x) for x in val)
                    else:
                        data["description"] = str(val)
            # Map section_number → section_id
            for alt in ("section_number", "id", "number"):
                if alt in data and "section_id" not in data:
                    data["section_id"] = str(data.pop(alt))
            # Ensure section_id is a string
            if "section_id" in data:
                data["section_id"] = str(data["section_id"])
            # Map order variants
            for alt in ("section_order", "position", "index"):
                if alt in data and "order" not in data:
                    data["order"] = data.pop(alt)
            # FIX-GEMMA4: Map alternative names for target_words
            for alt in ("word_count", "target_word_count", "words", "length"):
                if alt in data and "target_words" not in data:
                    data["target_words"] = data.pop(alt)
            # FIX-GEMMA4: Map alternative names for search_keywords
            for alt in ("keywords", "search_terms", "key_terms", "routing_keywords"):
                if alt in data and "search_keywords" not in data:
                    val = data.pop(alt)
                    # Coerce list to comma-separated string
                    if isinstance(val, list):
                        data["search_keywords"] = ", ".join(str(x) for x in val)
                    else:
                        data["search_keywords"] = str(val)
            # FIX-GEMMA4: Map alternative names for evidence_ids
            for alt in ("evidence", "sources", "source_ids", "references"):
                if alt in data and "evidence_ids" not in data:
                    data["evidence_ids"] = data.pop(alt)
            # FIX-GEMMA4: Map alternative names for analytical_focus
            for alt in ("focus", "analysis_type", "approach"):
                if alt in data and "analytical_focus" not in data:
                    data["analytical_focus"] = data.pop(alt)
            # Coerce evidence_ids elements to strings
            if "evidence_ids" in data and isinstance(data["evidence_ids"], list):
                data["evidence_ids"] = [str(x) for x in data["evidence_ids"]]
            # Null defaults
            if data.get("description") is None:
                data["description"] = ""
            if data.get("search_keywords") is None:
                data["search_keywords"] = ""
            if data.get("evidence_ids") is None:
                data["evidence_ids"] = []
            if data.get("target_words") is None:
                data["target_words"] = 600
        return data


class ReportOutline(BaseModel):
    """Complete report outline."""

    title: str = Field(description="Report title")
    abstract: str = Field(
        description="150-250 word abstract summarizing key findings",
        default="",
    )
    sections: list[SectionOutlineItem] = Field(
        description="Ordered list of sections",
        default_factory=list,
    )
    total_target_words: int = Field(
        description="Total target word count",
        default=8000,
    )

    @model_validator(mode="before")
    @classmethod
    def filter_invalid_sections(cls, data):
        """Skip individual sections that fail validation instead of failing.

        FIX-T4: Also handles SectionOutlineItem instances (from _fallback_outline)
        which are not dicts but valid section objects.

        FIX-CITE-2: Normalize alternative key names from Qwen 3.5 Plus.
        The LLM returns 'report_outline', 'outline_sections', 'outline'
        instead of 'sections'. Map them before validation.
        """
        if isinstance(data, dict):
            # FIX-CITE-2: Normalize sections key
            if "sections" not in data:
                for alt in ("report_outline", "outline_sections", "outline",
                            "section_list", "report_sections", "chapters", "parts"):
                    if alt in data and isinstance(data[alt], list):
                        data["sections"] = data.pop(alt)
                        break
            # FIX-CITE-2: Normalize title key
            if "title" not in data:
                for alt in ("report_title", "research_question", "heading",
                            "name", "document_title"):
                    if alt in data:
                        data["title"] = data.pop(alt)
                        break
            # FIX-GEMMA4: Normalize abstract key
            for alt in ("summary", "overview", "executive_summary", "abstract_text"):
                if alt in data and "abstract" not in data:
                    data["abstract"] = data.pop(alt)
            # FIX-GEMMA4: Normalize total_target_words key
            for alt in ("target_words", "total_words", "word_count", "target_word_count"):
                if alt in data and "total_target_words" not in data:
                    data["total_target_words"] = data.pop(alt)
            # Null defaults
            if data.get("abstract") is None:
                data["abstract"] = ""
            if data.get("total_target_words") is None:
                data["total_target_words"] = 8000
            if data.get("sections") is None:
                data["sections"] = []
        if isinstance(data, dict) and "sections" in data:
            valid = []
            for i, item in enumerate(data["sections"]):
                # FIX-T4: Accept SectionOutlineItem instances (e.g. from _fallback_outline)
                if isinstance(item, SectionOutlineItem):
                    valid.append(item.model_dump())
                    continue
                if not isinstance(item, dict):
                    continue
                # Auto-assign section_id if completely missing
                if not any(k in item for k in ("section_id", "section_number", "id", "number")):
                    item["section_id"] = f"s{i+1:02d}"
                # Auto-assign order if missing
                if "order" not in item and "section_order" not in item:
                    item["order"] = i + 1
                try:
                    SectionOutlineItem.model_validate(item)
                    valid.append(item)
                except Exception as exc:
                    logger.warning(
                        "[polaris graph] Dropped invalid section '%s': %s",
                        item.get("title", "?")[:40],
                        str(exc)[:200],
                    )
            data["sections"] = valid
        return data

    @model_validator(mode="after")
    def reject_empty_sections(self):
        """FIX-SD2: Reject empty outlines — forces LLM retry."""
        if not self.sections:
            raise ValueError(
                "ReportOutline.sections is empty — LLM must generate at least 1 section"
            )
        return self


class SectionDraft(BaseModel):
    """Draft of a single report section."""

    section_id: str = Field(description="Section ID matching the outline")
    title: str = Field(description="Section title")
    content: str = Field(
        description="Section content with [CITE:evidence_id] markers"
    )
    claims_made: list[str] = Field(
        default_factory=list,
        description="List of factual claims made in this section",
    )
    evidence_ids: list[str] = Field(
        default_factory=list,
        description="Evidence IDs used in this section",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """FIX-GEMMA4: Handle alternative field names from different models."""
        if isinstance(data, dict):
            # Map alternative names for content
            for alt in ("text", "body", "section_content", "draft", "markdown",
                        "section_text", "prose"):
                if alt in data and "content" not in data:
                    data["content"] = data.pop(alt)
            # Map alternative names for title
            for alt in ("section_title", "heading", "name"):
                if alt in data and "title" not in data:
                    data["title"] = data.pop(alt)
            # Map alternative names for section_id
            for alt in ("section_number", "id", "number"):
                if alt in data and "section_id" not in data:
                    data["section_id"] = str(data.pop(alt))
            # Map alternative names for claims_made
            for alt in ("claims", "factual_claims", "assertions"):
                if alt in data and "claims_made" not in data:
                    data["claims_made"] = data.pop(alt)
            # Map alternative names for evidence_ids
            for alt in ("evidence", "sources", "source_ids", "references", "cited_evidence"):
                if alt in data and "evidence_ids" not in data:
                    data["evidence_ids"] = data.pop(alt)
            # Ensure section_id is a string
            if "section_id" in data:
                data["section_id"] = str(data["section_id"])
            # Coerce evidence_ids elements to strings
            if "evidence_ids" in data and isinstance(data["evidence_ids"], list):
                data["evidence_ids"] = [str(x) for x in data["evidence_ids"]]
            # Null defaults
            if data.get("content") is None:
                data["content"] = ""
            if data.get("claims_made") is None:
                data["claims_made"] = []
            if data.get("evidence_ids") is None:
                data["evidence_ids"] = []
        return data


# ---------------------------------------------------------------------------
# RC-3: Question-Driven Report Planning (v3 Hybrid)
# ---------------------------------------------------------------------------

class ResearchSubQuestion(BaseModel):
    """A single sub-question decomposed from the research query."""

    question: str = Field(description="The sub-question a reader would ask")
    rationale: str = Field(
        description="Why a reader would care about this question",
        default="",
    )
    analytical_focus: str = Field(
        description="Primary analytical operation: aggregate, compare, explain, tabulate, challenge",
        default="explain",
    )
    expected_depth: str = Field(
        description="How deep this question should be explored: deep, moderate, brief",
        default="moderate",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """FIX-GEMMA4: Handle alternative field names from different models."""
        if isinstance(data, dict):
            for alt in ("sub_question", "text", "query", "research_question"):
                if alt in data and "question" not in data:
                    data["question"] = data.pop(alt)
            for alt in ("reason", "justification", "explanation", "why"):
                if alt in data and "rationale" not in data:
                    data["rationale"] = data.pop(alt)
            for alt in ("focus", "analysis_type", "operation", "approach"):
                if alt in data and "analytical_focus" not in data:
                    data["analytical_focus"] = data.pop(alt)
            for alt in ("depth", "detail_level", "coverage_depth"):
                if alt in data and "expected_depth" not in data:
                    data["expected_depth"] = data.pop(alt)
            if data.get("rationale") is None:
                data["rationale"] = ""
            if data.get("analytical_focus") is None:
                data["analytical_focus"] = "explain"
            if data.get("expected_depth") is None:
                data["expected_depth"] = "moderate"
        return data

    @field_validator("analytical_focus", mode="before")
    @classmethod
    def validate_analytical_focus(cls, v):
        valid = {"aggregate", "compare", "explain", "tabulate", "challenge"}
        if isinstance(v, str) and v.lower().strip() in valid:
            return v.lower().strip()
        return "explain"

    @field_validator("expected_depth", mode="before")
    @classmethod
    def validate_expected_depth(cls, v):
        valid = {"deep", "moderate", "brief"}
        if isinstance(v, str) and v.lower().strip() in valid:
            return v.lower().strip()
        return "moderate"


class QuestionDecomposition(BaseModel):
    """Decomposition of a research query into reader sub-questions."""

    questions: list[ResearchSubQuestion] = Field(
        description="6-10 sub-questions that a reader would want answered",
        default_factory=list,
    )
    narrative_flow: str = Field(
        description="How the questions build on each other logically",
        default="",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """FIX-GEMMA4: Handle alternative field names from different models."""
        if isinstance(data, dict):
            for alt in ("sub_questions", "research_questions", "decomposition",
                        "question_list", "reader_questions"):
                if alt in data and "questions" not in data:
                    data["questions"] = data.pop(alt)
            for alt in ("flow", "logic", "logical_flow", "narrative",
                        "question_flow", "structure"):
                if alt in data and "narrative_flow" not in data:
                    data["narrative_flow"] = data.pop(alt)
            if data.get("questions") is None:
                data["questions"] = []
            if data.get("narrative_flow") is None:
                data["narrative_flow"] = ""
        return data


# ---------------------------------------------------------------------------
# RC-1: Structured Evidence Cards (v3 Hybrid)
# ---------------------------------------------------------------------------

class ComparableMetric(BaseModel):
    """A single quantitative metric extracted from evidence for cross-study comparison."""

    metric_name: str = Field(
        description="Name of the metric, e.g. removal_efficiency, cost_per_kg, contact_time",
    )
    value: float = Field(description="Numeric value of the metric")
    unit: str = Field(description="Unit of measurement, e.g. %, mg/L, minutes", default="")
    condition: str = Field(
        description="Experimental conditions, e.g. pH 5.5, 25C",
        default="",
    )
    entity: str = Field(
        description="Entity being measured, e.g. Pb(II), rice husk biochar",
        default="",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """FIX-GEMMA4: Handle alternative field names from different models."""
        if isinstance(data, dict):
            for alt in ("name", "metric", "measure", "parameter"):
                if alt in data and "metric_name" not in data:
                    data["metric_name"] = data.pop(alt)
            for alt in ("measurement", "result", "numeric_value", "amount"):
                if alt in data and "value" not in data:
                    data["value"] = data.pop(alt)
            for alt in ("units", "measurement_unit", "uom"):
                if alt in data and "unit" not in data:
                    data["unit"] = data.pop(alt)
            for alt in ("conditions", "experimental_conditions", "parameters"):
                if alt in data and "condition" not in data:
                    data["condition"] = data.pop(alt)
            for alt in ("subject", "target", "item", "material"):
                if alt in data and "entity" not in data:
                    data["entity"] = data.pop(alt)
            if data.get("unit") is None:
                data["unit"] = ""
            if data.get("condition") is None:
                data["condition"] = ""
            if data.get("entity") is None:
                data["entity"] = ""
        return data

    @field_validator("value", mode="before")
    @classmethod
    def coerce_value(cls, v):
        if isinstance(v, str):
            try:
                return float(v.replace(",", ""))
            except (ValueError, TypeError):
                return 0.0
        if isinstance(v, (int, float)):
            return float(v)
        return 0.0


class EvidenceCardEnrichment(BaseModel):
    """Post-extraction enrichment for a single evidence piece."""

    evidence_id: str = Field(description="ID of the evidence piece being enriched")
    methodology: str = Field(
        description="How the finding was obtained (experimental method, study design)",
        default="",
    )
    conditions: str = Field(
        description="Experimental or study parameters (temperature, pH, sample size)",
        default="",
    )
    limitations: str = Field(
        description="Known limitations of this finding",
        default="",
    )
    strength_signals: list[str] = Field(
        description="Quality signals: peer_reviewed, large_sample, replicated, meta_analysis",
        default_factory=list,
    )
    comparable_metrics: list[ComparableMetric] = Field(
        description="Quantitative metrics that can be compared across studies",
        default_factory=list,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """FIX-GEMMA4: Handle alternative field names from different models."""
        if isinstance(data, dict):
            for alt in ("id", "ev_id", "source_id"):
                if alt in data and "evidence_id" not in data:
                    data["evidence_id"] = str(data.pop(alt))
            for alt in ("method", "study_design", "research_method"):
                if alt in data and "methodology" not in data:
                    data["methodology"] = data.pop(alt)
            for alt in ("parameters", "experimental_conditions", "study_conditions"):
                if alt in data and "conditions" not in data:
                    data["conditions"] = data.pop(alt)
            for alt in ("weaknesses", "caveats", "known_limitations"):
                if alt in data and "limitations" not in data:
                    data["limitations"] = data.pop(alt)
            for alt in ("quality_signals", "signals", "strength_indicators"):
                if alt in data and "strength_signals" not in data:
                    data["strength_signals"] = data.pop(alt)
            for alt in ("metrics", "quantitative_metrics", "measurements"):
                if alt in data and "comparable_metrics" not in data:
                    data["comparable_metrics"] = data.pop(alt)
            # Ensure evidence_id is a string
            if "evidence_id" in data:
                data["evidence_id"] = str(data["evidence_id"])
            # Null defaults
            if data.get("methodology") is None:
                data["methodology"] = ""
            if data.get("conditions") is None:
                data["conditions"] = ""
            if data.get("limitations") is None:
                data["limitations"] = ""
            if data.get("strength_signals") is None:
                data["strength_signals"] = []
            if data.get("comparable_metrics") is None:
                data["comparable_metrics"] = []
        return data


class EvidenceCardBatch(BaseModel):
    """Batch of evidence card enrichments from a single LLM call."""

    cards: list[EvidenceCardEnrichment] = Field(
        description="Enrichment data for each evidence piece in the batch",
        default_factory=list,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        if isinstance(data, dict):
            for alt in ("enrichments", "evidence_cards", "results"):
                if alt in data and "cards" not in data:
                    data["cards"] = data.pop(alt)
            if data.get("cards") is None:
                data["cards"] = []
        return data


# ---------------------------------------------------------------------------
# FIX-E: Global Evidence Assignment (Two-Pass Synthesis)
# ---------------------------------------------------------------------------


class SectionEvidenceAssignment(BaseModel):
    """Evidence assignment for a single section."""

    section_id: str = Field(description="Section ID from the outline")
    primary_ids: list[int] = Field(
        description="Short IDs of evidence primarily relevant to this section",
        default_factory=list,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """FIX-GEMMA4: Handle alternative field names from different models."""
        if isinstance(data, dict):
            for alt in ("section_number", "id", "number"):
                if alt in data and "section_id" not in data:
                    data["section_id"] = str(data.pop(alt))
            for alt in ("evidence_ids", "ids", "assigned_ids", "relevant_ids"):
                if alt in data and "primary_ids" not in data:
                    data["primary_ids"] = data.pop(alt)
            if "section_id" in data:
                data["section_id"] = str(data["section_id"])
            if data.get("primary_ids") is None:
                data["primary_ids"] = []
        return data


class GlobalEvidenceAssignment(BaseModel):
    """LLM-generated global evidence-to-section assignment.

    Pass 1 of two-pass synthesis: the LLM sees ALL evidence summaries
    and assigns each piece to its most relevant section. Evidence marked
    as cross-section is visible to ALL section writers.
    """

    assignments: list[SectionEvidenceAssignment] = Field(
        description="Per-section evidence assignments",
        default_factory=list,
    )
    cross_section_ids: list[int] = Field(
        description="Short IDs of evidence relevant to multiple sections",
        default_factory=list,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """FIX-GEMMA4: Handle alternative field names from different models."""
        if isinstance(data, dict):
            for alt in ("section_assignments", "evidence_assignments",
                        "sections", "per_section"):
                if alt in data and "assignments" not in data:
                    data["assignments"] = data.pop(alt)
            for alt in ("cross_section", "shared_ids", "common_ids",
                        "multi_section_ids", "global_ids"):
                if alt in data and "cross_section_ids" not in data:
                    data["cross_section_ids"] = data.pop(alt)
            if data.get("assignments") is None:
                data["assignments"] = []
            if data.get("cross_section_ids") is None:
                data["cross_section_ids"] = []
        return data


# ---------------------------------------------------------------------------
# Citation Mapping
# ---------------------------------------------------------------------------

class CitationMapping(BaseModel):
    """Mapping from evidence ID to bibliography entry."""

    evidence_id: str = Field(description="The evidence ID referenced")
    citation_number: int = Field(description="Citation number in report")
    is_grounded: bool = Field(
        description="Whether this citation is properly grounded in evidence"
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """FIX-GEMMA4: Handle alternative field names from different models."""
        if isinstance(data, dict):
            for alt in ("id", "ev_id", "source_id"):
                if alt in data and "evidence_id" not in data:
                    data["evidence_id"] = str(data.pop(alt))
            for alt in ("number", "cite_number", "ref_number", "index"):
                if alt in data and "citation_number" not in data:
                    data["citation_number"] = data.pop(alt)
            for alt in ("grounded", "is_valid", "valid", "verified"):
                if alt in data and "is_grounded" not in data:
                    data["is_grounded"] = data.pop(alt)
            if "evidence_id" in data:
                data["evidence_id"] = str(data["evidence_id"])
        return data


class CitationAudit(BaseModel):
    """Full citation audit results."""

    mappings: list[CitationMapping] = Field(
        description="All citation mappings"
    )
    ungrounded_claims: list[str] = Field(
        description="Claims that lack proper evidence grounding",
        default_factory=list,
    )
    bibliography_entries: list[str] = Field(
        description="Formatted bibliography entries in order"
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """FIX-GEMMA4: Handle alternative field names from different models."""
        if isinstance(data, dict):
            for alt in ("citation_mappings", "citations", "citation_map"):
                if alt in data and "mappings" not in data:
                    data["mappings"] = data.pop(alt)
            for alt in ("unsupported_claims", "ungrounded", "missing_evidence"):
                if alt in data and "ungrounded_claims" not in data:
                    data["ungrounded_claims"] = data.pop(alt)
            for alt in ("bibliography", "references", "ref_entries", "bib_entries"):
                if alt in data and "bibliography_entries" not in data:
                    data["bibliography_entries"] = data.pop(alt)
            if data.get("ungrounded_claims") is None:
                data["ungrounded_claims"] = []
            if data.get("mappings") is None:
                data["mappings"] = []
            if data.get("bibliography_entries") is None:
                data["bibliography_entries"] = []
        return data


# ---------------------------------------------------------------------------
# Gap Analysis
# ---------------------------------------------------------------------------

class GapAnalysis(BaseModel):
    """Analysis of evidence gaps."""

    gaps: list[str] = Field(
        description="Identified gaps in evidence coverage",
        default_factory=list,
    )
    gap_severity: str = Field(
        description="Overall severity: 'critical', 'moderate', 'minor'",
        default="moderate",
    )
    suggested_queries: list[str] = Field(
        description="Additional queries to fill the gaps",
        default_factory=list,
    )
    should_iterate: bool = Field(
        description="Whether another iteration is needed to fill gaps",
        default=True,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """Handle LLM variant field names and nulls.

        FIX-GEMMA4: Added Gemma 4 alternatives for gaps and should_iterate.
        """
        if isinstance(data, dict):
            # Map gap variants
            for alt in ("evidence_gaps", "missing", "coverage_gaps",
                        "identified_gaps", "gap_list"):
                if alt in data and "gaps" not in data:
                    data["gaps"] = data.pop(alt)
            # Map severity variants
            for alt in ("severity", "overall_severity"):
                if alt in data and "gap_severity" not in data:
                    data["gap_severity"] = data.pop(alt)
            # Map query variants
            for alt in ("queries", "additional_queries", "follow_up_queries",
                        "search_queries", "recommended_queries"):
                if alt in data and "suggested_queries" not in data:
                    data["suggested_queries"] = data.pop(alt)
            # Map should_iterate variants
            for alt in ("needs_iteration", "iterate", "continue",
                        "needs_more_evidence", "requires_iteration"):
                if alt in data and "should_iterate" not in data:
                    data["should_iterate"] = data.pop(alt)
            # Null defaults
            if data.get("gap_severity") is None:
                data["gap_severity"] = "moderate"
            if data.get("gaps") is None:
                data["gaps"] = []
            if data.get("suggested_queries") is None:
                data["suggested_queries"] = []
            if data.get("should_iterate") is None:
                data["should_iterate"] = True
        return data


# ---------------------------------------------------------------------------
# GEMINI-ARCH: Cluster Viability Assessment
# ---------------------------------------------------------------------------

class ClusterAssessment(BaseModel):
    """GEMINI-ARCH 1C: Reasoning-based cluster viability assessment.

    Replaces hard-coded PG_MIN_CITATIONS_PER_SECTION threshold with
    model reasoning about whether a cluster warrants a full section.
    """

    decision: str = Field(
        description="FULL_SECTION, BRIEF, MERGE, or DROP",
        default="FULL_SECTION",
    )
    reasoning: str = Field(
        description="Explanation for the viability decision",
        default="",
    )
    merge_target: str = Field(
        description="Theme name to merge into (if decision is MERGE)",
        default="",
    )
    key_claims: list[str] = Field(
        description="Extractable claims from this cluster's evidence",
        default_factory=list,
    )
    has_structured_data: bool = Field(
        description="Whether numbers, comparisons, or time-series data is present",
        default=False,
    )
    data_type: str = Field(
        description="Type of structured data: comparison, time_series, measurement, ranking, none",
        default="none",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """FIX-GEMMA4: Handle alternative field names from different models."""
        if isinstance(data, dict):
            for alt in ("verdict", "result", "assessment", "action"):
                if alt in data and "decision" not in data:
                    data["decision"] = data.pop(alt)
            for alt in ("explanation", "rationale", "justification"):
                if alt in data and "reasoning" not in data:
                    data["reasoning"] = data.pop(alt)
            for alt in ("target", "merge_into", "merge_with"):
                if alt in data and "merge_target" not in data:
                    data["merge_target"] = data.pop(alt)
            for alt in ("claims", "main_claims", "extractable_claims"):
                if alt in data and "key_claims" not in data:
                    data["key_claims"] = data.pop(alt)
            for alt in ("structured_data", "has_data", "contains_data"):
                if alt in data and "has_structured_data" not in data:
                    data["has_structured_data"] = data.pop(alt)
            for alt in ("structured_data_type", "data_category"):
                if alt in data and "data_type" not in data:
                    data["data_type"] = data.pop(alt)
            # Null defaults
            if data.get("reasoning") is None:
                data["reasoning"] = ""
            if data.get("merge_target") is None:
                data["merge_target"] = ""
            if data.get("key_claims") is None:
                data["key_claims"] = []
        return data

    @field_validator("decision", mode="before")
    @classmethod
    def normalize_decision(cls, v):
        if isinstance(v, str):
            v = v.strip().upper()
            valid = {"FULL_SECTION", "BRIEF", "MERGE", "DROP"}
            if v in valid:
                return v
            # Fuzzy match
            for opt in valid:
                if opt in v:
                    return opt
        return "FULL_SECTION"


# ---------------------------------------------------------------------------
# GEMINI-ARCH: Structured Data Extraction (Phase 2B)
# ---------------------------------------------------------------------------

class StructuredDataPoint(BaseModel):
    """A single structured data point extracted from evidence.

    Used for table and chart generation in the GEMINI-ARCH pipeline.
    """

    data_type: str = Field(
        description="Type: statistic, comparison, time_series, measurement, ranking",
        default="statistic",
    )
    label: str = Field(description="What is being measured", default="")
    value: str = Field(description="The measured value", default="")
    year: str = Field(description="Year of measurement if available", default="")
    unit: str = Field(description="Unit of measurement", default="")
    context: str = Field(description="Brief context for the data point", default="")
    evidence_id: str = Field(description="Source evidence ID", default="")
    source_url: str = Field(description="Source URL", default="")

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """FIX-GEMMA4: Handle alternative field names from different models."""
        if isinstance(data, dict):
            for alt in ("type", "category", "kind"):
                if alt in data and "data_type" not in data:
                    data["data_type"] = data.pop(alt)
            for alt in ("name", "metric", "description", "metric_name"):
                if alt in data and "label" not in data:
                    data["label"] = data.pop(alt)
            for alt in ("measurement", "result", "amount", "numeric_value"):
                if alt in data and "value" not in data:
                    data["value"] = data.pop(alt)
            for alt in ("date", "period", "time"):
                if alt in data and "year" not in data:
                    data["year"] = data.pop(alt)
            for alt in ("units", "measurement_unit", "uom"):
                if alt in data and "unit" not in data:
                    data["unit"] = data.pop(alt)
            for alt in ("note", "details", "explanation"):
                if alt in data and "context" not in data:
                    data["context"] = data.pop(alt)
            for alt in ("ev_id", "source_id", "id"):
                if alt in data and "evidence_id" not in data:
                    data["evidence_id"] = str(data.pop(alt))
            for alt in ("url", "source", "link"):
                if alt in data and "source_url" not in data:
                    data["source_url"] = data.pop(alt)
            # Ensure string types
            if "evidence_id" in data:
                data["evidence_id"] = str(data.get("evidence_id", ""))
        return data

    @field_validator("value", mode="before")
    @classmethod
    def coerce_value_to_str(cls, v):
        """LLM returns numeric values as int/float — coerce to str."""
        if v is None:
            return ""
        if not isinstance(v, str):
            return str(v)
        return v

    @field_validator("data_type", mode="before")
    @classmethod
    def normalize_data_type(cls, v):
        if isinstance(v, str):
            v = v.strip().lower()
            valid = {"statistic", "comparison", "time_series", "measurement", "ranking"}
            if v in valid:
                return v
        return "statistic"


class StructuredDataExtraction(BaseModel):
    """Structured data extraction results from a source analysis batch.

    Extracted alongside atomic facts during evidence analysis.
    """

    data_points: list[StructuredDataPoint] = Field(
        description="Extracted structured data points",
        default_factory=list,
    )
    has_comparison_data: bool = Field(
        description="Whether the source compares multiple entities",
        default=False,
    )
    has_time_series: bool = Field(
        description="Whether the source contains temporal data trends",
        default=False,
    )
    comparison_entities: list[str] = Field(
        description="Entities being compared (if has_comparison_data)",
        default_factory=list,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_and_wrap(cls, data):
        """FIX-GEMMA4: Handle alternative field names + bare list wrapping."""
        if isinstance(data, list):
            return {"data_points": data}
        if isinstance(data, dict):
            for alt in ("points", "results", "extracted_data", "data",
                        "structured_data", "extractions"):
                if alt in data and "data_points" not in data:
                    data["data_points"] = data.pop(alt)
            for alt in ("has_comparisons", "comparison_data"):
                if alt in data and "has_comparison_data" not in data:
                    data["has_comparison_data"] = data.pop(alt)
            for alt in ("has_temporal_data", "has_trends", "temporal_data"):
                if alt in data and "has_time_series" not in data:
                    data["has_time_series"] = data.pop(alt)
            for alt in ("entities", "compared_entities", "subjects"):
                if alt in data and "comparison_entities" not in data:
                    data["comparison_entities"] = data.pop(alt)
            if data.get("data_points") is None:
                data["data_points"] = []
            if data.get("comparison_entities") is None:
                data["comparison_entities"] = []
        return data


# ---------------------------------------------------------------------------
# Quality Assessment
# ---------------------------------------------------------------------------

class QualityAssessment(BaseModel):
    """Quality assessment of the final report."""

    faithfulness_score: float = Field(default=0.0)
    coverage_score: float = Field(default=0.0)
    coherence_score: float = Field(default=0.0)
    citation_density: float = Field(
        description="Citations per 100 words"
    )
    issues: list[str] = Field(
        description="Quality issues found",
        default_factory=list,
    )
    overall_grade: str = Field(
        description="Grade: 'A', 'B', 'C', 'D', 'F'"
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """FIX-GEMMA4: Handle alternative field names from different models."""
        if isinstance(data, dict):
            for alt in ("faithfulness", "faith_score"):
                if alt in data and "faithfulness_score" not in data:
                    data["faithfulness_score"] = data.pop(alt)
            for alt in ("coverage", "completeness_score", "completeness"):
                if alt in data and "coverage_score" not in data:
                    data["coverage_score"] = data.pop(alt)
            for alt in ("coherence", "readability_score", "readability"):
                if alt in data and "coherence_score" not in data:
                    data["coherence_score"] = data.pop(alt)
            for alt in ("density", "citations_per_100_words", "cite_density"):
                if alt in data and "citation_density" not in data:
                    data["citation_density"] = data.pop(alt)
            for alt in ("problems", "quality_issues", "findings", "defects"):
                if alt in data and "issues" not in data:
                    data["issues"] = data.pop(alt)
            for alt in ("grade", "score", "rating", "overall_rating"):
                if alt in data and "overall_grade" not in data:
                    data["overall_grade"] = data.pop(alt)
            # Null defaults
            if data.get("issues") is None:
                data["issues"] = []
            if data.get("faithfulness_score") is None:
                data["faithfulness_score"] = 0.0
            if data.get("coverage_score") is None:
                data["coverage_score"] = 0.0
            if data.get("coherence_score") is None:
                data["coherence_score"] = 0.0
        return data


# ---------------------------------------------------------------------------
# Search Refinement (Adaptive Search)
# ---------------------------------------------------------------------------

class AgenticRoundAnalysis(BaseModel):
    """LLM contract for the agentic search loop 'Reason' step.

    After each round of searches, the LLM analyzes results and decides
    whether to continue searching or converge. Generates targeted
    follow-up queries informed by what was found so far.
    """

    key_findings: list[str] = Field(
        description="3-5 key findings from the latest round",
        default_factory=list,
    )
    perspective_gaps: list[str] = Field(
        description="Underrepresented STORM perspectives in current results",
        default_factory=list,
    )
    web_queries: list[str] = Field(
        description="3-6 web queries for the next round",
        default_factory=list,
    )
    academic_queries: list[str] = Field(
        description="1-3 Semantic Scholar queries using precise terminology",
        default_factory=list,
    )
    exa_queries: list[str] = Field(
        description="0-1 semantic queries for Exa neural search",
        default_factory=list,
    )
    convergence_assessment: str = Field(
        description="Assessment: 'expanding', 'narrowing', or 'saturated'",
        default="expanding",
    )
    should_continue: bool = Field(
        description="Whether another search round is needed",
        default=True,
    )
    reasoning: str = Field(
        description="Brief rationale for the convergence assessment",
        default="",
    )
    knowledge_gaps: list[str] = Field(
        description="Specific knowledge gaps identified from reading content",
        default_factory=list,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """Handle LLM variant field names and nulls."""
        if isinstance(data, dict):
            for alt in ("findings", "results", "key_results"):
                if alt in data and "key_findings" not in data:
                    data["key_findings"] = data.pop(alt)
            for alt in ("gaps", "missing_perspectives", "underrepresented"):
                if alt in data and "perspective_gaps" not in data:
                    data["perspective_gaps"] = data.pop(alt)
            for alt in ("web_search_queries", "search_queries", "follow_up_web"):
                if alt in data and "web_queries" not in data:
                    data["web_queries"] = data.pop(alt)
            for alt in ("s2_queries", "scholar_queries", "follow_up_academic"):
                if alt in data and "academic_queries" not in data:
                    data["academic_queries"] = data.pop(alt)
            for alt in ("semantic_queries", "neural_queries", "follow_up_exa"):
                if alt in data and "exa_queries" not in data:
                    data["exa_queries"] = data.pop(alt)
            for alt in ("assessment", "status", "convergence"):
                if alt in data and "convergence_assessment" not in data:
                    data["convergence_assessment"] = data.pop(alt)
            for alt in ("continue", "continue_searching", "needs_more"):
                if alt in data and "should_continue" not in data:
                    data["should_continue"] = data.pop(alt)
            for alt in ("rationale", "explanation"):
                if alt in data and "reasoning" not in data:
                    data["reasoning"] = data.pop(alt)
            for alt in ("gaps_in_knowledge", "missing_knowledge", "content_gaps", "information_gaps"):
                if alt in data and "knowledge_gaps" not in data:
                    data["knowledge_gaps"] = data.pop(alt)
            # W3.10: Coerce common LLM shape errors so the three validation
            # errors we see in production (list-typed fields arriving as
            # string/dict, should_continue as string "true"/"false",
            # convergence_assessment using a non-enum synonym) stop failing.
            _list_fields = (
                "key_findings", "perspective_gaps", "web_queries",
                "academic_queries", "exa_queries", "knowledge_gaps",
            )
            for field_name in _list_fields:
                val = data.get(field_name)
                if val is None:
                    data[field_name] = []
                elif isinstance(val, str):
                    parts = [p.strip() for p in val.split("\n") if p.strip()]
                    if len(parts) <= 1:
                        parts = [p.strip() for p in val.split(";") if p.strip()]
                    data[field_name] = parts
                elif isinstance(val, dict):
                    data[field_name] = [str(v) for v in val.values() if v]
            # Coerce should_continue: accept strings / ints / lowercase bools.
            sc = data.get("should_continue")
            if isinstance(sc, str):
                data["should_continue"] = sc.strip().lower() in ("true", "yes", "1", "continue")
            elif isinstance(sc, (int, float)):
                data["should_continue"] = bool(sc)
            elif sc is None:
                data["should_continue"] = True
            # Normalize convergence_assessment to the expected vocabulary.
            ca = data.get("convergence_assessment")
            # BUG-13 (#1262): the LLM intermittently emits convergence_assessment
            # as a DICT (e.g. {"assessment": "saturated", "confidence": 0.8} or
            # {"state": "narrowing", "reasoning": "..."}) instead of a bare
            # string. Previously only None/str were handled here, so the dict
            # fell through to the field's `str` validation, triggering a
            # ValidationError -> JSON-repair scramble that self-recovered but
            # was fragile. Coerce the dict to its canonical string form FIRST,
            # then let the existing string-mapping branch below normalize it to
            # the {expanding,narrowing,saturated} vocabulary exactly as if the
            # model had sent the equivalent bare string. FAITHFULNESS-SAFE:
            # convergence_assessment is an advisory agentic-loop control signal
            # (keep searching vs. converge), never a faithfulness verdict or a
            # citation/claim; this only hardens input parsing and cannot drop,
            # alter, or relax any verified claim or hard gate.
            if isinstance(ca, dict):
                _ca_candidate = ""
                for _k in ("assessment", "convergence_assessment",
                           "convergence", "status", "state", "value", "label"):
                    _v = ca.get(_k)
                    if isinstance(_v, str) and _v.strip():
                        _ca_candidate = _v
                        break
                if not _ca_candidate:
                    # No recognized key holds a usable string: join any string
                    # values so a vocabulary token embedded in the dict (e.g.
                    # {"summary": "results are saturated"}) is still detectable.
                    _ca_candidate = " ".join(
                        _v for _v in ca.values() if isinstance(_v, str) and _v.strip()
                    )
                ca = _ca_candidate
            if ca is None:
                data["convergence_assessment"] = "expanding"
            elif isinstance(ca, str):
                _ca_lower = ca.strip().lower()
                _ca_map = {
                    "saturated": "saturated",
                    "converged": "saturated",
                    "converging": "saturated",
                    "narrowing": "narrowing",
                    "refining": "narrowing",
                    "expanding": "expanding",
                    "exploring": "expanding",
                    "broadening": "expanding",
                }
                data["convergence_assessment"] = _ca_map.get(_ca_lower, "expanding")
            if data.get("reasoning") is None:
                data["reasoning"] = ""
            elif not isinstance(data.get("reasoning"), str):
                data["reasoning"] = str(data["reasoning"])
        return data


class PageResearchNote(BaseModel):
    """LLM output for per-page comprehension during agentic search.

    Each page read during the search loop is summarized into a research note
    capturing key findings, perspectives covered, and knowledge contribution.
    """

    url: str = Field(description="URL of the page")
    title: str = Field(description="Title of the page", default="")
    summary: str = Field(
        description="150-200 word research summary focused on findings relevant to query",
        default="",
    )
    perspectives: list[str] = Field(
        description="STORM perspectives covered by this page",
        default_factory=list,
    )
    key_facts: list[str] = Field(
        description="3-5 specific facts/data points with numbers, dates, or named entities",
        default_factory=list,
    )
    knowledge_contribution: str = Field(
        description="What new understanding this page adds to the research",
        default="",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """Handle LLM variant field names and nulls."""
        if isinstance(data, dict):
            for alt in ("page_url", "source_url", "link"):
                if alt in data and "url" not in data:
                    data["url"] = data.pop(alt)
            for alt in ("page_title", "source_title", "name"):
                if alt in data and "title" not in data:
                    data["title"] = data.pop(alt)
            for alt in ("page_summary", "research_summary", "content_summary"):
                if alt in data and "summary" not in data:
                    data["summary"] = data.pop(alt)
            for alt in ("storm_perspectives", "covered_perspectives", "perspective_tags"):
                if alt in data and "perspectives" not in data:
                    data["perspectives"] = data.pop(alt)
            for alt in ("facts", "data_points", "specific_facts"):
                if alt in data and "key_facts" not in data:
                    data["key_facts"] = data.pop(alt)
            for alt in ("contribution", "new_knowledge", "new_understanding"):
                if alt in data and "knowledge_contribution" not in data:
                    data["knowledge_contribution"] = data.pop(alt)
            _null_defaults = {
                "url": "",
                "title": "",
                "summary": "",
                "perspectives": [],
                "key_facts": [],
                "knowledge_contribution": "",
            }
            for field, default in _null_defaults.items():
                if data.get(field) is None:
                    data[field] = default
        return data


class PageSummaryBatch(BaseModel):
    """Batch wrapper for page research notes with invalid-note filtering."""

    notes: list[PageResearchNote] = Field(
        description="Research notes for each page read",
        default_factory=list,
    )

    @model_validator(mode="before")
    @classmethod
    def filter_invalid_notes(cls, data):
        """Skip individual notes that fail validation instead of failing the batch.

        FIX-SCHEMA-7: Secondary defense for spurious-quote string array.
        FIX-GEMMA4: Normalize alternative field names before processing.
        """
        if isinstance(data, dict):
            # FIX-GEMMA4: Map alternative names for notes
            for alt in ("pages", "research_notes", "page_notes",
                        "summaries", "page_summaries", "results"):
                if alt in data and "notes" not in data:
                    data["notes"] = data.pop(alt)
            if data.get("notes") is None:
                data["notes"] = []
        if isinstance(data, dict) and "notes" in data:
            raw = data["notes"]
            if isinstance(raw, str):
                logger.error(
                    "[polaris graph] FIX-SCHEMA-7: notes is STRING (%d chars) "
                    "— FIX-SCHEMA-6 missed this pattern!",
                    len(raw),
                )
                recovery_keys = {"url", "title", "key_findings", "methodology_details",
                                 "data_points", "limitations", "relevance_assessment"}
                recovered = {k: v for k, v in data.items() if k in recovery_keys}
                if recovered.get("url"):
                    data["notes"] = [recovered]
                    for k in recovery_keys:
                        data.pop(k, None)
                else:
                    data["notes"] = []
            valid = []
            dropped = 0
            original_count = len(data["notes"])
            for item in data["notes"]:
                if not isinstance(item, dict):
                    dropped += 1
                    continue
                try:
                    PageResearchNote.model_validate(item)
                    valid.append(item)
                except Exception as exc:
                    dropped += 1
                    logger.warning(
                        "[polaris graph] Dropped invalid page note for '%s': %s",
                        item.get("url", "?")[:60],
                        str(exc)[:200],
                    )
            if dropped > 0:
                logger.warning(
                    "[polaris graph] AREA-9: PageSummaryBatch dropped %d/%d notes",
                    dropped, original_count,
                )
            data["notes"] = valid
        return data


class SeedQueryPlan(BaseModel):
    """Lightweight plan for 9 seed queries (1 per STORM perspective).

    Used by plan_seed_queries() to generate the initial seed queries
    for the agentic search loop. Reuses existing SubQuery model.
    """

    analysis: str = Field(
        description="Brief analysis of the research question",
        default="",
    )
    sub_queries: list[SubQuery] = Field(
        description="Exactly 9 seed queries, 1 per STORM perspective",
        default_factory=list,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """Handle LLM variant field names and nulls."""
        if isinstance(data, dict):
            for alt in ("queries", "search_queries", "seed_queries"):
                if alt in data and "sub_queries" not in data:
                    data["sub_queries"] = data.pop(alt)
            if data.get("sub_queries") is None:
                data["sub_queries"] = []
            if data.get("analysis") is None:
                data["analysis"] = ""
        return data


class SearchRefinement(BaseModel):
    """LLM output for mid-search refinement.

    Used between adaptive search rounds to generate follow-up queries
    informed by what was found in previous rounds.
    """

    observations: list[str] = Field(
        description="Key findings from results so far",
        default_factory=list,
    )
    refinement_queries: list[str] = Field(
        description="5-10 follow-up search queries to fill gaps",
        default_factory=list,
    )
    perspective_gaps: list[str] = Field(
        description="Underrepresented STORM perspectives in current results",
        default_factory=list,
    )
    promising_directions: list[str] = Field(
        description="Topics worth deeper investigation based on results",
        default_factory=list,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """Handle LLM variant field names and nulls."""
        if isinstance(data, dict):
            for alt in ("queries", "follow_up_queries", "new_queries"):
                if alt in data and "refinement_queries" not in data:
                    data["refinement_queries"] = data.pop(alt)
            for alt in ("findings", "key_observations", "results_summary"):
                if alt in data and "observations" not in data:
                    data["observations"] = data.pop(alt)
            for alt in ("gaps", "missing_perspectives"):
                if alt in data and "perspective_gaps" not in data:
                    data["perspective_gaps"] = data.pop(alt)
            for alt in ("directions", "promising_topics"):
                if alt in data and "promising_directions" not in data:
                    data["promising_directions"] = data.pop(alt)
            # Null defaults
            for field in ("observations", "refinement_queries", "perspective_gaps", "promising_directions"):
                if data.get(field) is None:
                    data[field] = []
        return data


# ---------------------------------------------------------------------------
# MoST: Molecular Structure of Thought (arXiv 2601.06002)
# ---------------------------------------------------------------------------

class ReflectionResult(BaseModel):
    """Output of cross-section reflection for a single section."""

    section_id: str = Field(description="Section ID being reflected on")
    contradictions: list[dict] = Field(
        default_factory=list,
        description="Contradictions detected with other sections",
    )
    redundancies: list[dict] = Field(
        default_factory=list,
        description="Redundant content detected with other sections",
    )
    cross_references: list[dict] = Field(
        default_factory=list,
        description="Cross-references that should be made explicit",
    )
    revision_needed: bool = Field(
        default=False,
        description="Whether this section needs revision based on reflection",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """FIX-GEMMA4: Handle alternative field names from different models."""
        if isinstance(data, dict):
            for alt in ("section_number", "id", "number"):
                if alt in data and "section_id" not in data:
                    data["section_id"] = str(data.pop(alt))
            for alt in ("conflicts", "inconsistencies"):
                if alt in data and "contradictions" not in data:
                    data["contradictions"] = data.pop(alt)
            for alt in ("duplicates", "overlaps", "repeated_content"):
                if alt in data and "redundancies" not in data:
                    data["redundancies"] = data.pop(alt)
            for alt in ("references", "links", "related_sections"):
                if alt in data and "cross_references" not in data:
                    data["cross_references"] = data.pop(alt)
            for alt in ("needs_revision", "requires_revision", "should_revise"):
                if alt in data and "revision_needed" not in data:
                    data["revision_needed"] = data.pop(alt)
            if "section_id" in data:
                data["section_id"] = str(data["section_id"])
            if data.get("contradictions") is None:
                data["contradictions"] = []
            if data.get("redundancies") is None:
                data["redundancies"] = []
            if data.get("cross_references") is None:
                data["cross_references"] = []
        return data


class ExplorationResult(BaseModel):
    """Output of evidence exploration for a single section."""

    section_id: str = Field(description="Section ID being enriched")
    new_evidence_ids: list[str] = Field(
        default_factory=list,
        description="Evidence IDs newly assigned to this section",
    )
    sentences_added: int = Field(
        default=0,
        description="Number of new sentences added from unused evidence",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data):
        """FIX-GEMMA4: Handle alternative field names from different models."""
        if isinstance(data, dict):
            for alt in ("section_number", "id", "number"):
                if alt in data and "section_id" not in data:
                    data["section_id"] = str(data.pop(alt))
            for alt in ("evidence_ids", "added_evidence", "assigned_ids"):
                if alt in data and "new_evidence_ids" not in data:
                    data["new_evidence_ids"] = data.pop(alt)
            for alt in ("added_sentences", "new_sentences", "sentence_count"):
                if alt in data and "sentences_added" not in data:
                    data["sentences_added"] = data.pop(alt)
            if "section_id" in data:
                data["section_id"] = str(data["section_id"])
            if data.get("new_evidence_ids") is None:
                data["new_evidence_ids"] = []
            if data.get("sentences_added") is None:
                data["sentences_added"] = 0
            # Coerce evidence_ids to strings
            if isinstance(data.get("new_evidence_ids"), list):
                data["new_evidence_ids"] = [str(x) for x in data["new_evidence_ids"]]
        return data
