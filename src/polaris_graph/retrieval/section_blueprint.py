"""Section Blueprint (v2 Loophole L5).

Cross-section evidence assignment BEFORE parallel section writers begin.
Prevents the "everyone cites the same 5 sources" problem.

The blueprint:
    1. Takes the outline (sections) + scored evidence pool
    2. Assigns primary/secondary evidence to each section via embedding similarity
       using search_keywords (Fix #2) not just title/description
    3. Enforces minimum evidence per section (or marks section as THIN)
    4. Core Source Bypass (Fix #3): high-authority evidence (standards, highly cited
       papers) bypasses the max-sections cap and is broadcast as global context
    5. Normal evidence capped at max_sections_per_evidence to reduce redundancy
    6. Provides the SourceRegistry mapping for consistent citation IDs

Thread-safe: section writers read their assignment; no writes after build.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
from dotenv import load_dotenv

from src.polaris_graph.retrieval.pooled_embedder import embed_with_pooling
from src.polaris_graph.retrieval.source_registry import SourceRegistry

load_dotenv()

logger = logging.getLogger("polaris_graph")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

# Fix R3-#5: Words-per-evidence-chunk for dynamic word budget
WORDS_PER_EVIDENCE_CHUNK = int(os.getenv("PG_WORDS_PER_EVIDENCE_CHUNK", "120"))


# I-deepfix-001 F5 (#1344): per-section WORD budget tracks the FULL routed basket payload.
#
# ``effective_target_words`` clamps the budget to ``min(outline_target, evidence_count * 120)``. The
# ``min(outline_target, ..)`` CEILING throttles a rich facet: once F1 routes 40 verified baskets to a
# section, the writer should develop one verified sentence per basket, but the ceiling caps the budget
# at the generic outline target (e.g. 800), truncating the payload. When this flag is ON the ceiling
# is dropped so the word budget tracks the full evidence payload (a 40-basket facet develops fully; a
# thin section still stays short via the evidence_count term). Read at CALL time (monkeypatch-testable).
# Default-OFF => the exact legacy ``min(target, evidence_budget)`` clamp (byte-identical).
def _word_budget_tracks_payload() -> bool:
    """True iff PG_WORD_BUDGET_TRACKS_PAYLOAD removes the ``min(target_words, ..)`` CEILING from
    ``effective_target_words`` so the per-section word budget tracks the full routed basket payload
    (F5). Default-OFF => the legacy clamp (byte-identical)."""
    return os.getenv("PG_WORD_BUDGET_TRACKS_PAYLOAD", "0").strip().lower() not in (
        "", "0", "false", "off", "no",
    )

# Fix R3-#2: Placeholder for sections with zero evidence
EMPTY_SECTION_PLACEHOLDER = (
    "> [!NOTE]\n"
    "> No reliable evidence was retrieved for this section. "
    "This topic requires additional primary sources.\n"
)


@dataclass
class SectionSpec:
    """Specification for a single section with its evidence assignment."""

    section_id: str
    title: str
    description: str = ""
    search_keywords: str = ""       # Fix #2: LLM-generated routing keywords
    target_words: int = 800         # outline target (may be overridden by effective_target_words)
    assigned_evidence_ids: list[str] = field(default_factory=list)
    secondary_evidence_ids: list[str] = field(default_factory=list)
    global_context_ids: list[str] = field(default_factory=list)  # Fix #3: core sources
    is_thin: bool = False           # True if below min_evidence_per_section
    is_empty: bool = False          # Fix R3-#2: True if 0 evidence (skip LLM entirely)
    evidence_count: int = 0
    avg_relevance: float = 0.0

    @property
    def effective_target_words(self) -> int:
        """Fix R3-#5: Dynamic word budget based on evidence payload.

        Prevents the target-word contradiction: if the blueprint routes only
        2 chunks (~150 words of data) to a section with target_words=800,
        the LLM is forced to hallucinate 650 words of filler.

        Formula: min(outline_target, evidence_count * WORDS_PER_EVIDENCE_CHUNK)
        Minimum floor of 150 words to avoid degenerate sections.
        """
        if self.evidence_count == 0:
            return 0
        evidence_budget = self.evidence_count * WORDS_PER_EVIDENCE_CHUNK
        # I-deepfix-001 F5 (#1344): when payload-tracking is ON the min(target_words, ..) CEILING is
        # dropped so a facet with many routed baskets develops fully (one verified sentence per basket).
        # Default-OFF => the exact legacy min(target, evidence_budget) clamp (byte-identical).
        if _word_budget_tracks_payload():
            return max(150, evidence_budget)
        return max(150, min(self.target_words, evidence_budget))

    @property
    def should_skip_llm(self) -> bool:
        """Fix R3-#2: True if this section has no evidence and should not invoke LLM.

        If True, the section writer should emit EMPTY_SECTION_PLACEHOLDER
        instead of calling the LLM, and the quality gate regex check should
        be skipped for this section.
        """
        return self.is_empty or self.evidence_count == 0


@dataclass
class BlueprintStats:
    """Statistics from the blueprint build process."""

    total_sections: int = 0
    total_evidence: int = 0
    thin_sections: int = 0
    avg_evidence_per_section: float = 0.0
    max_evidence_per_section: int = 0
    min_evidence_per_section: int = 0
    unassigned_evidence: int = 0
    multi_assigned_evidence: int = 0  # assigned to >1 section


# ---------------------------------------------------------------------------
# Section Blueprint
# ---------------------------------------------------------------------------

class SectionBlueprint:
    """Cross-section evidence assignment engine (L5).

    Given an outline and a scored evidence pool, assigns evidence to sections
    using embedding similarity.

    Fix #2 — Asymmetric Routing: If sections have `search_keywords` (generated
    by the outline LLM), we embed those keywords instead of the section
    title/description. This solves the vocabulary mismatch between abstract
    section titles ("Comparison of epoxy adhesion methods") and dense empirical
    evidence ("The 20mm dolly separated at 4.2 MPa").

    Fix #3 — Core Source Bypass: Evidence from high-authority sources
    (score >= core_source_threshold) bypasses the max_sections_per_evidence
    cap. These are broadcast as `global_context_ids` to ALL sections that
    score above secondary_threshold. An ASTM standard or seminal paper
    must be available to Introduction, Methodology, Equipment, AND Conclusion.
    """

    def __init__(
        self,
        min_evidence_per_section: int = 5,
        max_sections_per_evidence: int = 2,
        max_chunks_per_section: int = int(
            os.getenv("PG_BLUEPRINT_MAX_CHUNKS_PER_SECTION", "15")
        ),
        primary_threshold: float = 0.40,
        secondary_threshold: float = 0.25,
        core_source_threshold: float = float(
            os.getenv("PG_BLUEPRINT_CORE_SOURCE_THRESHOLD", "0.85")
        ),
    ) -> None:
        self._min_per_section = min_evidence_per_section
        self._max_per_evidence = max_sections_per_evidence
        self._max_per_section = max_chunks_per_section
        self._primary_threshold = primary_threshold
        self._secondary_threshold = secondary_threshold
        self._core_source_threshold = core_source_threshold

        # Lazy-loaded
        self._embed_fn = None

    def build(
        self,
        sections: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        registry: SourceRegistry,
    ) -> tuple[list[SectionSpec], BlueprintStats]:
        """Build the section blueprint.

        Args:
            sections: List of outline sections with title, description,
                      target_words, and optionally search_keywords (Fix #2).
            evidence: List of EvidencePiece-compatible dicts (from CRAG retriever).
            registry: Global source registry for citation ID mapping.

        Returns:
            (specs, stats) — list of SectionSpec with evidence assigned, plus stats.
        """
        if not sections or not evidence:
            return [], BlueprintStats()

        embed = self._get_embed_fn()

        # Fix #2: Use search_keywords for routing if available,
        # fall back to title + description
        section_texts = []
        for s in sections:
            keywords = s.get("search_keywords", "").strip()
            if keywords:
                # Embed the LLM-generated routing keywords
                section_texts.append(keywords)
            else:
                section_texts.append(
                    f"{s.get('title', '')}. {s.get('description', '')}"
                )

        # Build evidence texts (use statement or direct_quote)
        evidence_texts = [
            e.get("statement") or e.get("direct_quote", "")
            for e in evidence
        ]

        # Fix R4-#1: Use pooled embedding for texts exceeding model's
        # 256-token max_seq_length. Evidence chunks are 1024+ tokens;
        # without pooling, the model truncates and all chunks from the
        # same document produce near-identical embeddings.
        all_texts = section_texts + evidence_texts
        all_embeddings = embed_with_pooling(all_texts, embed)

        n_sections = len(sections)
        section_vecs = np.array(all_embeddings[:n_sections], dtype=np.float32)
        evidence_vecs = np.array(all_embeddings[n_sections:], dtype=np.float32)

        # Normalize for cosine similarity
        section_norms = np.linalg.norm(section_vecs, axis=1, keepdims=True)
        section_norms = np.where(section_norms < 1e-8, 1.0, section_norms)
        section_vecs = section_vecs / section_norms

        evidence_norms = np.linalg.norm(evidence_vecs, axis=1, keepdims=True)
        evidence_norms = np.where(evidence_norms < 1e-8, 1.0, evidence_norms)
        evidence_vecs = evidence_vecs / evidence_norms

        # Similarity matrix: (n_sections, n_evidence)
        sim_matrix = section_vecs @ evidence_vecs.T

        # Fix #3: Identify core sources that bypass the max-sections cap
        core_evidence_indices = set()
        for ev_idx, ev in enumerate(evidence):
            authority = ev.get("source_confidence", 0.0) or 0.0
            relevance = ev.get("relevance_score", 0.0) or 0.0
            # Core source: high authority OR exceptionally high relevance
            if authority >= self._core_source_threshold or relevance >= self._core_source_threshold:
                core_evidence_indices.add(ev_idx)

        if core_evidence_indices:
            logger.info(
                "Blueprint: %d core sources bypass max-sections cap (threshold=%.2f)",
                len(core_evidence_indices), self._core_source_threshold,
            )

        # Track how many sections each NON-CORE evidence is assigned to
        evidence_assignment_count = [0] * len(evidence)

        # Build SectionSpec for each section
        specs: list[SectionSpec] = []
        for sec_idx, sec in enumerate(sections):
            scores = sim_matrix[sec_idx]
            ranked_indices = np.argsort(-scores)

            primary_ids: list[str] = []
            secondary_ids: list[str] = []
            global_ctx_ids: list[str] = []

            for ev_idx in ranked_indices:
                ev_idx = int(ev_idx)
                score = float(scores[ev_idx])
                ev_id = evidence[ev_idx].get("evidence_id", "")
                is_core = ev_idx in core_evidence_indices

                # Fix #3: Core sources skip the assignment cap
                if is_core:
                    if score >= self._secondary_threshold:
                        global_ctx_ids.append(ev_id)
                    continue  # don't count against cap or add to primary/secondary

                # Normal evidence: respect max_sections cap
                if evidence_assignment_count[ev_idx] >= self._max_per_evidence:
                    continue

                if score >= self._primary_threshold:
                    primary_ids.append(ev_id)
                    evidence_assignment_count[ev_idx] += 1
                elif score >= self._secondary_threshold:
                    secondary_ids.append(ev_id)
                    evidence_assignment_count[ev_idx] += 1

            # Fix R2-#2 (Context Bomb): Hard cap on total evidence per section.
            # Without this, 60 core chunks from an ASTM standard × 15 sections
            # = 900,000+ tokens sent to the API in one burst.
            # Strategy: keep all global context up to cap, then fill with primary,
            # then secondary. This prioritizes core sources over filler.
            raw_total = len(global_ctx_ids) + len(primary_ids) + len(secondary_ids)
            if raw_total > self._max_per_section:
                budget = self._max_per_section
                # Allocate: global first, then primary, then secondary
                g = global_ctx_ids[:budget]
                budget -= len(g)
                p = primary_ids[:budget] if budget > 0 else []
                budget -= len(p)
                s = secondary_ids[:budget] if budget > 0 else []
                global_ctx_ids, primary_ids, secondary_ids = g, p, s
                logger.debug(
                    "Section %s capped: %d -> %d chunks (g=%d, p=%d, s=%d)",
                    sec.get("section_id", sec_idx),
                    raw_total, len(g) + len(p) + len(s),
                    len(g), len(p), len(s),
                )

            total = len(primary_ids) + len(secondary_ids) + len(global_ctx_ids)
            relevant_indices = [
                int(i) for i in ranked_indices[:max(total, 1)]
            ]
            avg_rel = float(np.mean([scores[i] for i in relevant_indices])) if total > 0 else 0.0

            spec = SectionSpec(
                section_id=sec.get("section_id", f"sec_{sec_idx:02d}"),
                title=sec.get("title", f"Section {sec_idx + 1}"),
                description=sec.get("description", ""),
                search_keywords=sec.get("search_keywords", ""),
                target_words=sec.get("target_words", 800),
                assigned_evidence_ids=primary_ids,
                secondary_evidence_ids=secondary_ids,
                global_context_ids=global_ctx_ids,
                is_thin=total < self._min_per_section,
                is_empty=total == 0,
                evidence_count=total,
                avg_relevance=round(avg_rel, 4),
            )
            if spec.is_empty:
                logger.warning(
                    "Section '%s' has 0 evidence — will emit placeholder, skip LLM",
                    spec.title,
                )
            specs.append(spec)

        # Stats
        counts = [s.evidence_count for s in specs]
        unassigned = sum(1 for c in evidence_assignment_count if c == 0)
        multi = sum(1 for c in evidence_assignment_count if c > 1)

        stats = BlueprintStats(
            total_sections=len(specs),
            total_evidence=len(evidence),
            thin_sections=sum(1 for s in specs if s.is_thin),
            avg_evidence_per_section=round(float(np.mean(counts)), 1) if counts else 0.0,
            max_evidence_per_section=max(counts) if counts else 0,
            min_evidence_per_section=min(counts) if counts else 0,
            unassigned_evidence=unassigned,
            multi_assigned_evidence=multi,
        )

        logger.info(
            "Blueprint: %d sections, %d evidence (%d core), %d thin, %.1f avg/section, %d unassigned",
            stats.total_sections, stats.total_evidence, len(core_evidence_indices),
            stats.thin_sections, stats.avg_evidence_per_section, stats.unassigned_evidence,
        )

        return specs, stats

    def get_evidence_for_section(
        self,
        spec: SectionSpec,
        evidence_pool: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Retrieve the actual evidence dicts for a section spec.

        Returns assigned evidence in order: global context first (core sources),
        then primary, then secondary.

        IMPORTANT (Fix #4 — Attention Dilution):
            When building the synthesis prompt, group these by source_url/SRC-NNN
            and print source metadata ONCE per source, followed by all chunks.
            Do NOT repeat title+abstract per chunk.
        """
        by_id = {e["evidence_id"]: e for e in evidence_pool}

        result: list[dict[str, Any]] = []
        # Global context (core sources) first — highest authority
        for eid in spec.global_context_ids:
            if eid in by_id:
                result.append(by_id[eid])
        for eid in spec.assigned_evidence_ids:
            if eid in by_id:
                result.append(by_id[eid])
        for eid in spec.secondary_evidence_ids:
            if eid in by_id:
                result.append(by_id[eid])
        return result

    @staticmethod
    def group_evidence_by_source(
        evidence: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Group evidence chunks by source URL for prompt building.

        Fix #4 — Attention Dilution: The synthesis prompt builder should
        call this to group chunks, then print source metadata ONCE followed
        by all chunks from that source. This avoids repeating the same
        300-word abstract 8 times when 8 chunks from one paper are routed
        to the same section.
        """
        groups: dict[str, list[dict[str, Any]]] = {}
        for ev in evidence:
            url = ev.get("source_url", "unknown")
            if url not in groups:
                groups[url] = []
            groups[url].append(ev)
        return groups

    # -- Internal ----------------------------------------------------------

    def _get_embed_fn(self):
        """Lazy-load embedding function."""
        if self._embed_fn is None:
            from src.utils.embedding_service import embed_texts
            self._embed_fn = embed_texts
        return self._embed_fn
