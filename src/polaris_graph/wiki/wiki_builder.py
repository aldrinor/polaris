"""
Wiki Builder — converts evidence + outline into persistent wiki pages.

The wiki is the INTERMEDIATE ARTIFACT between raw evidence and the report.
Evidence is assigned to sections by embedding similarity (not front-to-back
allocation), eliminating the evidence starvation problem.

Each wiki page contains pre-cited claims: every claim already has its source
URL, direct quote, and global bibliography number. No late-binding citation
resolution needed.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

WIKI_BASE_DIR = Path(os.getenv("PG_WIKI_DIR", "wiki"))
OUTLINE_MAX_SECTIONS = int(os.getenv("PG_WIKI_MAX_SECTIONS", "10"))
MIN_SIMILARITY = float(os.getenv("PG_WIKI_MIN_SIMILARITY", "0.3"))
STARVATION_MIN_CLAIMS = int(os.getenv("PG_WIKI_STARVATION_MIN", "3"))
DEDUP_THRESHOLD = float(os.getenv("PG_WIKI_DEDUP_THRESHOLD", "0.85"))


@dataclass
class WikiResult:
    """Output of build_wiki(): everything the composer needs."""

    wiki_path: str
    section_claims: dict[str, list[dict]]
    bibliography: list[dict]
    stats: dict
    unassigned_evidence: list[dict] = field(default_factory=list)
    # FIX-COMPLETENESS: Augmented outline is exposed so callers can iterate
    # over the SAME sections that section_claims was built against. The
    # builder may add synthesis sections that weren't in the input outline.
    outline: list[dict] = field(default_factory=list)


async def generate_outline_for_wiki(
    client: Any,
    query: str,
    evidence: list[dict],
) -> list[dict]:
    """Generate a section outline from query + evidence when no outline exists in state.

    This is needed because the outline is normally generated inside synthesize_report(),
    which we're replacing. The wiki path needs an outline to assign evidence to sections.

    Returns a list of dicts with section_id, title, description.
    """
    # Build evidence summary for the LLM
    ev_statements = []
    for i, ev in enumerate(evidence[:50]):  # Cap at 50 for context window
        statement = ev.get("statement", "")
        tier = ev.get("quality_tier", "?")
        if statement:
            ev_statements.append(f"  {i+1}. [{tier}] {statement[:150]}")

    evidence_block = "\n".join(ev_statements)
    target_sections = min(OUTLINE_MAX_SECTIONS, max(5, len(evidence) // 5))

    prompt = (
        f"Create a {target_sections}-section outline for a systematic review answering:\n"
        f"\"{query}\"\n\n"
        f"Available evidence ({len(evidence)} pieces, showing top {min(50, len(evidence))}):\n"
        f"{evidence_block}\n\n"
        f"RULES:\n"
        f"1. Return ONLY a JSON array of objects: [{{\"section_id\": \"s01\", \"title\": \"...\", \"description\": \"...\"}}]\n"
        f"2. Include sections for: benefits, risks/safety, mechanisms, methodology, and comparisons\n"
        f"3. Each section must have a clear, specific title (not generic)\n"
        f"4. Descriptions should be 1-2 sentences explaining the section's focus\n"
        f"5. Order from general to specific: definition → findings → safety → methodology → implications\n"
        f"6. Do NOT include chain-of-thought or explanation — ONLY the JSON array\n"
    )

    try:
        result = await client.generate(
            prompt=prompt,
            system="You are a research outline planner. Return ONLY valid JSON.",
            max_tokens=2048,
            temperature=0.2,
            timeout=int(os.getenv("PG_WIKI_OUTLINE_TIMEOUT", "60")),
        )

        import json as json_module
        content = result.content.strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()

        sections = json_module.loads(content)
        if isinstance(sections, list) and len(sections) >= 3:
            # Ensure section_ids
            for i, sec in enumerate(sections):
                if "section_id" not in sec:
                    sec["section_id"] = f"s{i+1:02d}"
                if "description" not in sec:
                    sec["description"] = sec.get("title", "")
            # FIX-1: guarantee a Risks section for risk-bearing queries, even
            # when the LLM ignored the prompt rule at line 77.
            sections = _ensure_risks_section(sections, query)
            logger.info("[wiki] Generated outline: %d sections from LLM", len(sections))
            return sections

    except Exception as exc:
        logger.warning("[wiki] Outline generation failed: %s", str(exc)[:100])

    # Fallback: generate a standard outline without LLM
    logger.info("[wiki] Using fallback outline (8 standard sections)")
    fallback = [
        {"section_id": "s01", "title": "Overview and Definitions", "description": f"Introduction to {query[:50]}"},
        {"section_id": "s02", "title": "Key Findings and Benefits", "description": "Primary positive outcomes from clinical evidence"},
        {"section_id": "s03", "title": "Mechanisms of Action", "description": "Biological and physiological mechanisms"},
        {"section_id": "s04", "title": "Comparative Analysis", "description": "Comparison with alternative approaches"},
        {"section_id": "s05", "title": "Safety Profile and Risks", "description": "Adverse effects, contraindications, and safety data"},
        {"section_id": "s06", "title": "Special Populations", "description": "Effects in specific demographic or clinical groups"},
        {"section_id": "s07", "title": "Research Quality and Limitations", "description": "Study design quality, evidence gaps, and methodological concerns"},
        {"section_id": "s08", "title": "Clinical Implications", "description": "Practical recommendations and future research directions"},
    ]
    return _ensure_risks_section(fallback, query)


_RISK_QUERY_TERMS = (
    " risk", " risks",
    " harm", " harms", "harmful",
    " adverse", "adverse event", "adverse effect",
    " side effect", "side-effect", " side effects",
    " safety", " safe ", "dangerous", "danger",
    "contraindication", "toxicity", "toxic",
    "downside", "drawback", "concern",
)


def _query_demands_risks_section(query: str) -> bool:
    """Detect whether the research query explicitly asks about risks/harms/safety.

    FIX-1: If the query names risk-related axes, the outline must include a
    dedicated Risks/Safety section. A B-question ("benefits AND risks?") that
    produces a benefits-only report is a systematic axis-coverage failure.
    Detection is deliberately permissive — false positives (a Risks section
    where none was strictly needed) cost far less than false negatives (the
    medium loopback defect: 100% missing risks axis).
    """
    if not query:
        return False
    q = " " + query.lower().strip() + " "
    return any(term in q for term in _RISK_QUERY_TERMS)


def _has_risks_section(outline: list[dict]) -> bool:
    """Check whether the outline already contains a risks/safety/adverse-effect section."""
    markers = (
        "risk", "safety", "adverse", "side effect", "side-effect",
        "harm", "contraindication", "toxicity",
    )
    for sec in outline:
        title = (sec.get("title") or "").lower()
        desc = (sec.get("description") or "").lower()
        # Require a substantive match: the marker must be in the title,
        # or in the description together with a second marker. Avoids
        # false-match on a section that merely mentions "safety" in passing.
        if any(m in title for m in markers):
            return True
        desc_hits = sum(1 for m in markers if m in desc)
        if desc_hits >= 2:
            return True
    return False


def _ensure_risks_section(outline: list[dict], query: str) -> list[dict]:
    """FIX-1: Inject a mandatory Risks/Safety section when the query demands it.

    Root cause of the medium-loopback defect: the query asked for benefits AND
    risks, but the LLM-generated outline omitted risks and the downstream
    synthesizer inherited the omission. Guarantee axis coverage at the outline
    layer so single-LLM-call variance cannot drop the axis.

    Idempotent: does nothing if the outline already has a risks-like section,
    or if the query does not mention risks.
    """
    if not outline:
        return outline
    if not _query_demands_risks_section(query):
        return outline
    if _has_risks_section(outline):
        return outline

    existing_ids = {s.get("section_id", "") for s in outline}
    next_idx = len(outline) + 1
    while f"s{next_idx:02d}" in existing_ids:
        next_idx += 1

    risks_section = {
        "section_id": f"s{next_idx:02d}",
        "title": "Risks, Adverse Effects, and Safety Considerations",
        "description": (
            "Enumerate documented harms, adverse events, contraindications, "
            "and population-specific cautions reported in the evidence base. "
            "Cover both common side-effects (e.g. gastrointestinal, "
            "neurological, metabolic) and severe or long-term risks. Note "
            "where the evidence base is thin, where risk-quantification is "
            "absent, and which populations were excluded from trials."
        ),
    }
    augmented = list(outline) + [risks_section]
    logger.info(
        "[wiki] FIX-1: Injected mandatory Risks section (query mentioned risks/harms/safety; "
        "outline had %d sections, now %d)",
        len(outline), len(augmented),
    )
    return augmented


def _ensure_synthesis_sections(outline: list[dict]) -> list[dict]:
    """Augment the outline with mandatory synthesis sections if missing.

    G-Eval analysis across 4 cross-domain runs (PFAS, fasting, adhesion,
    DVS-PEI) found that completeness scores 6/10 instead of 9/10 whenever
    the outline lacks explicit sections for:
      1. Comparative synthesis / trade-off analysis
      2. Practical implementation considerations
      3. Knowledge gaps and future research

    The PFAS run scored 9/10 because its outline happened to include all
    three. Adding them universally lifts completeness ~3pts (= ~+0.45
    weighted G-Eval points each, ~+1.4 total).

    Detection is keyword-based on section titles. If a synthesis-flavored
    section already exists, we do not add a duplicate.
    """
    if not outline:
        return outline

    # Strict detection: only count titles that are CROSS-CUTTING synthesis
    # sections, not section-specific discussions of similar topics. We test
    # against the lowercased title as a whole — match ONLY if the title
    # clearly indicates a synthesis/cross-cutting section.
    titles = [s.get("title", "").lower() for s in outline]

    def _is_synthesis_title(title: str, kind: str) -> bool:
        """Check if a section title is a synthesis section of the given kind."""
        if kind == "comparative":
            # Must be cross-cutting comparison: "Comparative Synthesis",
            # "Comparative Analysis", "Trade-off Analysis", "Techno-Economic"
            return any(p in title for p in (
                "comparative synthesis", "comparative analysis", "comparative effectiveness",
                "trade-off", "tradeoff", "techno-economic", "cost-benefit",
                "comparative evaluation", "selection guide",
            ))
        if kind == "practical":
            # Must be deployment-focused, not "practical implications"
            return any(p in title for p in (
                "implementation", "deployment", "scalability", "operational complexity",
                "real-world", "field application", "practical implementation",
            ))
        if kind == "gaps":
            # Must be cross-cutting gaps, not section-specific limitations
            return any(p in title for p in (
                "knowledge gap", "knowledge gaps", "research gap", "evidence gap",
                "future direction", "future research", "open question",
                "knowledge gaps and future", "limitations and future",
            ))
        return False

    has_comparative = any(_is_synthesis_title(t, "comparative") for t in titles)
    has_practical = any(_is_synthesis_title(t, "practical") for t in titles)
    has_gaps = any(_is_synthesis_title(t, "gaps") for t in titles)

    augmented = list(outline)
    next_idx = len(outline) + 1

    if not has_comparative:
        augmented.append({
            "section_id": f"s{next_idx:02d}",
            "title": "Comparative Synthesis and Trade-off Analysis",
            "description": (
                "Cross-cutting synthesis comparing the approaches/findings from prior "
                "sections. Identify where evidence converges, where studies disagree, "
                "and what trade-offs distinguish the leading options. Use comparative "
                "language and reference specific findings from earlier sections."
            ),
        })
        next_idx += 1

    if not has_practical:
        augmented.append({
            "section_id": f"s{next_idx:02d}",
            "title": "Practical Implementation Considerations",
            "description": (
                "Real-world deployment factors: cost, scalability, regulatory context, "
                "operational complexity, infrastructure requirements, and stakeholder "
                "constraints. What does it take to actually use these findings?"
            ),
        })
        next_idx += 1

    if not has_gaps:
        augmented.append({
            "section_id": f"s{next_idx:02d}",
            "title": "Knowledge Gaps and Future Research Directions",
            "description": (
                "Open questions, limitations of the current evidence base, populations "
                "or conditions underrepresented in the literature, and the most "
                "important next experiments or studies needed to advance the field."
            ),
        })
        next_idx += 1

    if len(augmented) > len(outline):
        added = len(augmented) - len(outline)
        logger.info(
            "[wiki] Outline augmented with %d synthesis section(s) (had %d, now %d)",
            added, len(outline), len(augmented),
        )
    return augmented


def build_wiki(
    evidence: list[dict],
    outline: list[dict],
    query: str,
    vector_id: str,
) -> WikiResult:
    """
    Build a persistent wiki from evidence and outline.

    1. Augment outline with synthesis sections if missing
    2. Filter to GOLD + SILVER evidence
    3. Assign evidence to sections by embedding similarity
    4. Guard against starvation (fallback for thin sections)
    5. Dedup within sections
    6. Build global bibliography
    7. Write wiki files to disk
    8. Return WikiResult for composer
    """
    if not outline:
        logger.warning(
            "[wiki] No outline provided — this is expected on first synthesis. "
            "Outline will be generated by the wiki graph entry point."
        )

    # FIX-COMPLETENESS: Ensure outline has comparative/practical/gaps sections.
    # Cross-domain G-Eval found completeness drops from 9 to 6 whenever these
    # are missing. The PFAS outline had them; the others didn't.
    outline = _ensure_synthesis_sections(outline)

    # FIX-1: Ensure a Risks/Safety section exists when the query demands one.
    # If the query asks for benefits AND risks, the outline must cover both.
    outline = _ensure_risks_section(outline, query)

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Step 1: Quality filter ──────────────────────────────────────
    quality_evidence = [
        e for e in evidence
        if e.get("quality_tier") in ("GOLD", "SILVER")
    ]
    filtered_count = len(evidence) - len(quality_evidence)
    logger.info(
        "[wiki] Quality filter: %d → %d evidence (removed %d BRONZE/UNVERIFIED)",
        len(evidence), len(quality_evidence), filtered_count,
    )

    if not quality_evidence:
        logger.warning("[wiki] No GOLD/SILVER evidence — using all evidence as fallback")
        quality_evidence = list(evidence)

    if not quality_evidence:
        logger.error("[wiki] No evidence at all — cannot build wiki")
        return WikiResult(
            wiki_path="",
            section_claims={},
            bibliography=[],
            stats={"total_evidence": 0, "error": "no_evidence"},
        )

    # ── Step 1b: Source authority gate (PageRank-based, ADAPTIVE) ──
    #
    # The analyzer already computes sig_authority (PageRank + source type boost)
    # for every evidence piece. Analysis of PG_WIKI_002 showed:
    #   - Good (peer-reviewed) avg sig_authority = 0.948
    #   - Bad (blogs/garbage) avg sig_authority = 0.381
    #   - At threshold 0.5: ALL 21 good kept, ALL 24 bad killed, zero errors
    #
    # FIX-GENERALIZATION: The hard 0.5 threshold works for academic-heavy topics
    # (PFAS, medical) but kills 86% of evidence on engineering/industry topics
    # (adhesion testing, materials standards) where vendor docs and standards
    # bodies have lower PageRank but are still authoritative for the domain.
    #
    # Adaptive strategy: pick the threshold that keeps at least
    # max(num_sections * 8, 50) evidence pieces. Walks down from 0.5 to 0.0.
    authority_gate_default = float(os.getenv("PG_WIKI_AUTHORITY_GATE", "0.5"))
    num_sections_target = max(len(outline), 1)
    min_post_gate = max(num_sections_target * 8, 50)

    # Sort by authority descending so we can compute the cutoff
    sorted_by_auth = sorted(
        quality_evidence,
        key=lambda e: e.get("sig_authority", 0.5),
        reverse=True,
    )
    before_auth = len(quality_evidence)

    # Default-gate pass first
    high_auth = [e for e in sorted_by_auth if e.get("sig_authority", 0.5) >= authority_gate_default]

    if len(high_auth) >= min_post_gate:
        # Plenty of high-authority evidence — use the strict gate
        quality_evidence = high_auth
        applied_gate = authority_gate_default
    else:
        # Adaptive: take top-N to hit the floor, but never include evidence
        # below sig_authority 0.30 (still excludes obvious blog garbage)
        FLOOR = 0.30
        quality_evidence = [
            e for e in sorted_by_auth[:max(min_post_gate, len(high_auth))]
            if e.get("sig_authority", 0.5) >= FLOOR
        ]
        applied_gate = quality_evidence[-1].get("sig_authority", FLOOR) if quality_evidence else FLOOR
        logger.info(
            "[wiki] Authority gate adaptive: strict 0.5 kept only %d/%d (need %d). "
            "Lowered to %.2f to keep %d evidence (floor=%.2f)",
            len(high_auth), before_auth, min_post_gate, applied_gate, len(quality_evidence), FLOOR,
        )

    auth_filtered = before_auth - len(quality_evidence)
    if auth_filtered and applied_gate >= authority_gate_default:
        logger.info(
            "[wiki] Authority gate (sig_authority >= %.2f): removed %d/%d evidence",
            applied_gate, auth_filtered, before_auth,
        )

    # Safety: if even the adaptive gate killed everything, fall back
    if not quality_evidence and before_auth > 0:
        logger.warning("[wiki] Authority gate killed ALL evidence — falling back to unfiltered")
        quality_evidence = [
            e for e in evidence
            if e.get("quality_tier") in ("GOLD", "SILVER")
        ]

    # Also remove retracted sources
    try:
        from src.polaris_graph.wiki.source_quality import enrich_evidence_with_quality
        quality_evidence = enrich_evidence_with_quality(quality_evidence)
        retracted = [e for e in quality_evidence if e.get("is_retracted")]
        if retracted:
            logger.warning("[wiki] Removed %d retracted sources", len(retracted))
            quality_evidence = [e for e in quality_evidence if not e.get("is_retracted")]
    except Exception as exc:
        logger.warning("[wiki] Source quality enrichment failed: %s", str(exc)[:100])

    # ── Step 2: Embedding-based assignment ──────────────────────────
    section_claims = _assign_evidence_by_embedding(quality_evidence, outline)

    # ── Step 3: Starvation guard ────────────────────────────────────
    assigned_ids = set()
    for claims in section_claims.values():
        for c in claims:
            assigned_ids.add(c.get("evidence_id"))

    unassigned = [
        e for e in quality_evidence
        if e.get("evidence_id") not in assigned_ids
    ]

    starved_sections = [
        sid for sid, claims in section_claims.items()
        if len(claims) < STARVATION_MIN_CLAIMS
    ]

    if starved_sections and unassigned:
        logger.info(
            "[wiki] Starvation guard: %d sections below %d claims, %d unassigned evidence",
            len(starved_sections), STARVATION_MIN_CLAIMS, len(unassigned),
        )
        _fill_starved_sections(
            section_claims, starved_sections, unassigned, outline,
        )

    # Second pass: steal from overfilled sections to fill empty ones.
    # This handles meta-sections like "Research Quality" or "Clinical Implications"
    # that don't match specific evidence but need claims to compose from.
    still_starved = [
        sid for sid, claims in section_claims.items()
        if len(claims) < STARVATION_MIN_CLAIMS
    ]
    if still_starved:
        # Find sections with the most claims (donors)
        overfilled = sorted(
            section_claims.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )

        for starved_sid in still_starved:
            need = STARVATION_MIN_CLAIMS - len(section_claims[starved_sid])
            donated = 0
            for donor_sid, donor_claims in overfilled:
                if donor_sid == starved_sid:
                    continue
                # Only steal if donor has more than fair share
                while (
                    len(section_claims[donor_sid]) > STARVATION_MIN_CLAIMS
                    and donated < need
                    and section_claims[donor_sid]
                ):
                    # Steal the LEAST relevant claim from the donor
                    worst_idx = min(
                        range(len(section_claims[donor_sid])),
                        key=lambda j: section_claims[donor_sid][j].get("relevance_score", 0),
                    )
                    stolen = section_claims[donor_sid].pop(worst_idx)
                    section_claims[starved_sid].append(stolen)
                    donated += 1

                if donated >= need:
                    break

            if donated:
                logger.info(
                    "[wiki] Starvation redistribution: donated %d claims to %s (from overfilled sections)",
                    donated, starved_sid,
                )

    # ── Step 3.5: Risk quorum ───────────────────────────────────────
    # FIX-RISK-QUORUM: sections whose title/description names risks or
    # adverse effects MUST receive at least PG_RISK_QUORUM_MIN risk-axis
    # evidence pieces. The embedding assignment above is Jaccard-like and
    # can route risk evidence to non-risk sections if the section titles
    # overlap more on other terms. Force-fill risk sections here.
    _RISK_SECTION_TERMS = (
        "risk", "adverse", "safety", "harm", "side effect",
        "side-effect", "contraindicat",
    )
    _RISK_EV_CATEGORIES = {
        "risk", "adverse_event", "contraindication", "safety",
    }
    _RISK_EV_KEYWORDS = (
        "adverse", "contraindicat", "side effect", "side-effect",
        "hypoglyc", "disorder", "eating disorder", "bone density",
        "muscle loss", "lean body mass", "pregnancy", "pregnant",
        "adolescent", "teen", "mortality", "harm",
        "dizziness", "nausea", "irritab",
    )

    def _is_risk_ev(ev: dict) -> bool:
        cat = (ev.get("fact_category", "") or "").lower()
        if cat in _RISK_EV_CATEGORIES:
            return True
        if ev.get("risk_axis_retained") is True:
            return True
        blob = (
            (ev.get("statement", "") or "")
            + " "
            + (ev.get("direct_quote", "") or "")
        ).lower()
        return any(k in blob for k in _RISK_EV_KEYWORDS)

    quorum_min = int(os.getenv("PG_RISK_QUORUM_MIN", "2"))
    quorum_injected = 0
    for section in outline:
        sid = section.get("section_id", "")
        if not sid:
            continue
        title_desc = (
            f"{section.get('title', '')} {section.get('description', '')}"
        ).lower()
        if not any(t in title_desc for t in _RISK_SECTION_TERMS):
            continue
        current = section_claims.get(sid, [])
        already_in = {
            c.get("evidence_id") for c in current if c.get("evidence_id")
        }
        current_risk_count = sum(1 for c in current if _is_risk_ev(c))
        needed = max(0, quorum_min - current_risk_count)
        if needed == 0:
            continue
        # Pull candidates from quality_evidence sorted by relevance.
        candidates = [
            e for e in quality_evidence
            if e.get("evidence_id") not in already_in and _is_risk_ev(e)
        ]
        candidates.sort(
            key=lambda e: e.get("relevance_score", 0.0), reverse=True,
        )
        for ev in candidates[:needed]:
            section_claims[sid].append(ev)
            quorum_injected += 1

    if quorum_injected > 0:
        logger.info(
            "[wiki] FIX-RISK-QUORUM: Injected %d risk-axis evidence pieces "
            "into risk/safety-titled sections (min=%d each)",
            quorum_injected, quorum_min,
        )

    # ── Step 4: Dedup within sections ───────────────────────────────
    total_deduped = 0
    for sid in section_claims:
        before = len(section_claims[sid])
        section_claims[sid] = _dedup_claims(section_claims[sid])
        total_deduped += before - len(section_claims[sid])

    if total_deduped:
        logger.info("[wiki] Dedup removed %d duplicate claims across sections", total_deduped)

    # ── Step 5: Build global bibliography ───────────────────────────
    bibliography = _build_bibliography(section_claims)

    # Attach bib numbers to each claim.
    # W3.9 canonicalized bibliography keys (strip www/trailing slash/tracking
    # params), so the lookup MUST canonicalize the claim's source_url too or
    # every claim gets ref_num=0 and wiki_composer silently drops them from
    # the prompt (zero-citation sections).
    from src.polaris_graph.synthesis.citation_mapper import _canonicalize_url
    url_to_ref = {b["url"]: b["ref_num"] for b in bibliography}
    unmapped_count = 0
    for claims in section_claims.values():
        for claim in claims:
            raw_url = claim.get("source_url", "")
            canonical = _canonicalize_url(raw_url) or raw_url
            ref = url_to_ref.get(canonical, 0)
            claim["ref_num"] = ref
            if not ref and raw_url:
                unmapped_count += 1
    if unmapped_count:
        logger.warning(
            "[wiki] %d claims failed URL→ref_num lookup — they will be "
            "dropped from the composer prompt. Bib keys: %s",
            unmapped_count, list(url_to_ref.keys())[:3],
        )

    # ── Step 6: Write wiki to disk ──────────────────────────────────
    wiki_path = WIKI_BASE_DIR / vector_id
    _write_wiki_to_disk(
        wiki_path, section_claims, bibliography, outline, query, now_str,
    )

    # ── Step 7: Build stats and return ──────────────────────────────
    total_claims = sum(len(c) for c in section_claims.values())
    stats = {
        "total_evidence_input": len(evidence),
        "quality_filtered": len(quality_evidence),
        "total_claims_in_wiki": total_claims,
        "total_sources": len(bibliography),
        "sections_with_claims": sum(1 for c in section_claims.values() if c),
        "total_sections": len(outline),
        "deduped_count": total_deduped,
        "unassigned_count": len(unassigned),
        "starved_sections_fixed": len(starved_sections),
    }

    logger.info(
        "[wiki] Built wiki: %d claims across %d sections from %d sources → %s",
        total_claims, stats["sections_with_claims"], len(bibliography), wiki_path,
    )

    for sid, claims in section_claims.items():
        sec_title = _find_section_title(outline, sid)
        sources = len({c.get("source_url") for c in claims})
        logger.info("  %s: %d claims, %d sources — %s", sid, len(claims), sources, sec_title[:50])

    return WikiResult(
        wiki_path=str(wiki_path),
        section_claims=section_claims,
        bibliography=bibliography,
        stats=stats,
        unassigned_evidence=unassigned,
        outline=outline,
    )


# ── Evidence Assignment ─────────────────────────────────────────────


def _assign_evidence_by_embedding(
    evidence: list[dict],
    outline: list[dict],
) -> dict[str, list[dict]]:
    """Assign evidence to outline sections using embedding cosine similarity."""
    from src.utils.embedding_service import embed_texts

    section_claims: dict[str, list[dict]] = {
        s.get("section_id", f"s{i:02d}"): []
        for i, s in enumerate(outline)
    }

    if not evidence or not outline:
        return section_claims

    # Build texts for embedding
    # BUG-3 FIX: include the STORM perspective tag in the evidence text so the
    # embedding picks up not just the statement content but the perspective it
    # belongs to (Public_Health, Regulatory, Economic, etc.). Sections whose
    # title/description reference a specific perspective (safety,
    # regulation, cost) can then match perspective-tagged evidence even when
    # the statement wording is generic-sounding.
    evidence_texts = [
        f"[{e.get('perspective', 'Scientific')}] {e.get('statement', '')} {e.get('direct_quote', '')[:200]}"
        for e in evidence
    ]
    section_texts = [
        f"{s.get('title', '')} {s.get('description', '')}"
        for s in outline
    ]

    # Embed everything in two batch calls
    try:
        evidence_embeddings = embed_texts(evidence_texts)
        section_embeddings = embed_texts(section_texts)
    except Exception as exc:
        logger.warning("[wiki] Embedding failed (%s) — falling back to keyword matching", exc)
        return _assign_evidence_by_keywords(evidence, outline)

    # Cosine similarity matrix: (num_evidence, num_sections)
    ev_matrix = np.array(evidence_embeddings)
    sec_matrix = np.array(section_embeddings)

    # Normalize
    ev_norms = np.linalg.norm(ev_matrix, axis=1, keepdims=True)
    sec_norms = np.linalg.norm(sec_matrix, axis=1, keepdims=True)
    ev_norms[ev_norms == 0] = 1.0
    sec_norms[sec_norms == 0] = 1.0
    ev_normed = ev_matrix / ev_norms
    sec_normed = sec_matrix / sec_norms

    similarity = ev_normed @ sec_normed.T  # (num_evidence, num_sections)

    section_ids = list(section_claims.keys())
    num_sections = len(section_ids)
    num_evidence = len(evidence)

    # Fair-share cap: prevent broad sections from absorbing everything
    fair_share = max(8, int(num_evidence / max(num_sections, 1) * 1.5))
    logger.info(
        "[wiki] Evidence assignment: %d evidence → %d sections (fair-share cap=%d)",
        num_evidence, num_sections, fair_share,
    )

    # Sort evidence by their best similarity score descending so high-confidence
    # assignments happen first (they're less likely to need redistribution)
    evidence_order = np.argsort(-np.max(similarity, axis=1))

    for i in evidence_order:
        ev = evidence[int(i)]
        # Try sections in order of similarity (best first)
        ranked_sections = np.argsort(similarity[int(i)])[::-1]

        assigned = False
        for sec_idx in ranked_sections:
            sec_idx = int(sec_idx)
            score = float(similarity[int(i), sec_idx])
            if score < MIN_SIMILARITY:
                break  # No more sections above threshold

            sid = section_ids[sec_idx]
            if len(section_claims[sid]) < fair_share:
                section_claims[sid].append(ev)
                assigned = True
                break

        # If all sections above threshold are full, assign to least-filled section
        # that has ANY similarity (>0.1) — prevents losing evidence entirely
        if not assigned:
            least_filled = sorted(
                range(num_sections),
                key=lambda idx: len(section_claims[section_ids[idx]]),
            )
            for sec_idx in least_filled:
                score = float(similarity[int(i), sec_idx])
                if score >= 0.1:
                    section_claims[section_ids[sec_idx]].append(ev)
                    assigned = True
                    break

    return section_claims


def _assign_evidence_by_keywords(
    evidence: list[dict],
    outline: list[dict],
) -> dict[str, list[dict]]:
    """Fallback: keyword overlap assignment (from Phase 0B)."""
    section_claims: dict[str, list[dict]] = {
        s.get("section_id", f"s{i:02d}"): []
        for i, s in enumerate(outline)
    }

    for ev in evidence:
        text = f"{ev.get('statement', '')} {ev.get('direct_quote', '')}".lower()
        ev_words = set(re.findall(r"\b[a-z]{4,}\b", text))

        scores = []
        for s in outline:
            sid = s.get("section_id", "")
            sec_text = f"{s.get('title', '')} {s.get('description', '')}".lower()
            sec_words = set(re.findall(r"\b[a-z]{4,}\b", sec_text))
            overlap = len(ev_words & sec_words)
            scores.append((sid, overlap))

        scores.sort(key=lambda x: x[1], reverse=True)
        for sid, score in scores[:2]:
            if score >= 2:
                section_claims[sid].append(ev)

    return section_claims


def _fill_starved_sections(
    section_claims: dict[str, list[dict]],
    starved_sids: list[str],
    unassigned: list[dict],
    outline: list[dict],
) -> None:
    """Fill sections with <STARVATION_MIN_CLAIMS from unassigned pool."""
    from src.utils.embedding_service import embed_texts

    if not unassigned:
        return

    unassigned_texts = [
        f"{e.get('statement', '')} {e.get('direct_quote', '')[:200]}"
        for e in unassigned
    ]

    try:
        un_embeddings = embed_texts(unassigned_texts)
    except Exception:
        return

    un_matrix = np.array(un_embeddings)
    un_norms = np.linalg.norm(un_matrix, axis=1, keepdims=True)
    un_norms[un_norms == 0] = 1.0
    un_normed = un_matrix / un_norms

    for sid in starved_sids:
        sec = next((s for s in outline if s.get("section_id") == sid), None)
        if not sec:
            continue

        sec_text = f"{sec.get('title', '')} {sec.get('description', '')}"
        try:
            sec_emb = np.array(embed_texts([sec_text])[0])
        except Exception:
            continue

        sec_norm = np.linalg.norm(sec_emb)
        if sec_norm == 0:
            continue
        sec_normed = sec_emb / sec_norm

        scores = un_normed @ sec_normed  # (num_unassigned,)
        top_indices = np.argsort(scores)[::-1]

        need = STARVATION_MIN_CLAIMS - len(section_claims[sid])
        added = 0
        for idx in top_indices:
            if added >= need:
                break
            if float(scores[idx]) >= 0.2:
                section_claims[sid].append(unassigned[int(idx)])
                added += 1

        if added:
            logger.info("[wiki] Starvation fix: added %d claims to %s", added, sid)


# ── Deduplication ────────────────────────────────────────────────────


def _dedup_claims(claims: list[dict]) -> list[dict]:
    """Remove near-duplicate claims within a section."""
    if len(claims) <= 1:
        return claims

    # Simple approach: same source URL + high statement similarity → dedup
    seen: list[dict] = []
    for claim in claims:
        is_dup = False
        for existing in seen:
            if (
                claim.get("source_url") == existing.get("source_url")
                and _text_similarity(
                    claim.get("statement", ""),
                    existing.get("statement", ""),
                ) > DEDUP_THRESHOLD
            ):
                is_dup = True
                break
        if not is_dup:
            seen.append(claim)

    return seen


def _text_similarity(a: str, b: str) -> float:
    """Quick Jaccard word similarity (no embeddings needed for dedup)."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = len(words_a & words_b)
    union = len(words_a | words_b)
    return intersection / union if union else 0.0


# ── Bibliography ─────────────────────────────────────────────────────


def _build_bibliography(section_claims: dict[str, list[dict]]) -> list[dict]:
    """Build global bibliography from all claims, one entry per unique URL.

    W3.9: Dedup by canonical URL (scheme/host/www/trailing-slash/tracking
    params normalized) so http vs https or www vs non-www variants of the
    same page don't produce duplicate bibliography entries.
    """
    from src.polaris_graph.synthesis.citation_mapper import _canonicalize_url

    url_to_best: dict[str, dict] = {}
    url_to_evidence_ids: dict[str, list[str]] = {}
    # Keep one canonical → display-url mapping so we preserve the nicer URL
    # (usually the https / no-www one) in the final bibliography entry.
    canonical_to_display: dict[str, str] = {}

    for claims in section_claims.values():
        for claim in claims:
            url = claim.get("source_url", "")
            if not url:
                continue
            canonical = _canonicalize_url(url) or url
            # Prefer the canonical form as the display url, falling back to
            # first-seen if canonicalization produced an empty string.
            if canonical not in canonical_to_display:
                canonical_to_display[canonical] = canonical or url
            # Track all evidence IDs for this source
            eid = claim.get("evidence_id", "")
            if canonical not in url_to_evidence_ids:
                url_to_evidence_ids[canonical] = []
            if eid and eid not in url_to_evidence_ids[canonical]:
                url_to_evidence_ids[canonical].append(eid)
            # Track best evidence for metadata
            if canonical not in url_to_best:
                url_to_best[canonical] = claim
            elif claim.get("relevance_score", 0) > url_to_best[canonical].get("relevance_score", 0):
                url_to_best[canonical] = claim

    # FIX-DEDUP-PAPER: collapse entries that point to the same paper at
    # different URLs (publisher vs PMC mirror vs DOI). The first-pass URL
    # canonicalization handles www/http/trailing-slash variants but cannot
    # detect that `thelancet.com/.../PIIS2589-5370(24)00098-1` and
    # `pmc.ncbi.nlm.nih.gov/articles/PMC10945168` are the same article. We
    # merge by DOI and by PMID (extracted from PMC URLs) when available.
    def _extract_pmid(u: str) -> str:
        m = re.search(r"/articles/PMC(\d+)", u or "")
        return f"pmc{m.group(1)}" if m else ""

    def _extract_regulatory_id(u: str) -> str:
        """PATCH-C: Collapse FDA/EMA labels across revisions.

        FDA accessdata.fda.gov path structure:
          /drugsatfda_docs/label/<YEAR>/<NDC>s<REV>lbl.pdf
        The <NDC> (application number) identifies the drug, not the
        revision. Four WEGOVY labels 215256s000/s007/s024/s033 all share
        NDC=215256 and should collapse to one bibliography entry, as
        observed in PG_LB_SA_01 which cited [26][27][28][29] for four
        revisions of the same document.

        EMA ema.europa.eu path structure:
          /en/documents/product-information/<product>-epar-product-information_en.pdf
        The <product> slug identifies the drug across revisions.
        """
        # FDA: capture application number before 's<rev>'
        m = re.search(
            r"/drugsatfda_docs/label/\d+/(\d+)s\d+lbl\.pdf",
            u or "",
            re.IGNORECASE,
        )
        if m:
            return f"fda-{m.group(1)}"
        # EMA: capture product slug before '-epar-product-information'
        m = re.search(
            r"/product-information/([^/]+?)-epar-product-information",
            u or "",
            re.IGNORECASE,
        )
        if m:
            return f"ema-{m.group(1).lower()}"
        return ""

    def _extract_doi(best_claim: dict, url: str) -> str:
        doi = (best_claim.get("doi", "") or "").strip().lower()
        if doi:
            return doi
        # Also accept DOI embedded in URL
        m = re.search(r"10\.\d{4,9}/[^\s\?#]+", url or "")
        return (m.group(0).lower() if m else "")

    # PATCH-D: OpenAlex work_id lookup for academic sources. Gives us
    # (a) a canonical work_id that collapses publisher + PMC + repo
    # mirrors into one work, and (b) a source type classification
    # (journal/preprint/repository/...) for the authority-tier gate.
    # Results cached in SQLite; misses are also cached so we don't
    # hammer the API on repeated failed lookups within a session.
    openalex_map: dict[str, object] = {}
    try:
        from src.polaris_graph.tools import openalex_client as _oa
        if _oa.ENABLED:
            for canonical, best in url_to_best.items():
                url_display = canonical_to_display.get(canonical, canonical)
                doi = _extract_doi(best, url_display)
                title = best.get("source_title", "") or ""
                w = _oa.canonicalize_sync(doi=doi, title=title)
                openalex_map[canonical] = w
    except Exception as _oa_exc:
        logger.debug("[wiki] OpenAlex batch lookup failed: %s", str(_oa_exc)[:200])

    paper_key_to_canonical: dict[str, str] = {}
    canonical_to_merge_targets: dict[str, list[str]] = {}
    for canonical, best in url_to_best.items():
        url_display = canonical_to_display.get(canonical, canonical)
        doi = _extract_doi(best, url_display)
        pmid = _extract_pmid(url_display)
        regulatory = _extract_regulatory_id(url_display)
        oa_work = openalex_map.get(canonical)
        oa_work_id = getattr(oa_work, "work_id", "") if oa_work else ""
        # PATCH-D: local extractors (DOI, PMID, FDA setid) take priority
        # because they're deterministic and collide cleanly. OpenAlex
        # work_id is a FALLBACK for sources without any local extractable
        # identity — OpenAlex can return different work_ids for the same
        # paper when titles differ, so using it as primary would miss
        # DOI-based duplicates it doesn't index consistently.
        paper_key = doi or pmid or regulatory or oa_work_id
        if not paper_key:
            continue
        if paper_key not in paper_key_to_canonical:
            paper_key_to_canonical[paper_key] = canonical
            canonical_to_merge_targets[canonical] = []
        else:
            primary = paper_key_to_canonical[paper_key]
            canonical_to_merge_targets.setdefault(primary, []).append(canonical)

    # Decide which canonicals to keep (primaries) vs merge away.
    primaries = {
        paper_key_to_canonical[k]
        for k in paper_key_to_canonical
    }
    merged_away = {
        c
        for targets in canonical_to_merge_targets.values()
        for c in targets
    }

    bibliography = []
    next_ref_num = 1
    for canonical, best in url_to_best.items():
        if canonical in merged_away:
            continue
        url = canonical_to_display.get(canonical, best.get("source_url", canonical))
        authors = best.get("authors", [])
        authors_str = ", ".join(authors[:3]) if authors else "Unknown"
        year = best.get("year", "n.d.")
        title = best.get("source_title", "Unknown")
        doi = best.get("doi", "")
        doi_str = f" DOI: {doi}" if doi else ""

        # Merge evidence_ids from any duplicate canonicals that collapse here.
        merged_ev_ids = list(url_to_evidence_ids.get(canonical, []))
        for dup in canonical_to_merge_targets.get(canonical, []):
            for eid in url_to_evidence_ids.get(dup, []):
                if eid not in merged_ev_ids:
                    merged_ev_ids.append(eid)

        # PATCH-D: attach OpenAlex-derived authority fields. UNKNOWN is
        # used when OpenAlex has no record of the source (which is itself
        # a signal — legitimate academic sources are almost always
        # indexed; law firms, Medium blogs, and telehealth marketing
        # pages are not). Downstream tier-gate can demote UNKNOWN to
        # BRONZE if needed.
        _oa_w = openalex_map.get(canonical)
        _oa_work_id = getattr(_oa_w, "work_id", "") if _oa_w else ""
        _oa_type = getattr(_oa_w, "type", "") if _oa_w else ""
        _oa_source_type = getattr(_oa_w, "source_type", "") if _oa_w else ""
        _oa_tier = _oa_w.authority_tier() if _oa_w else "UNKNOWN"

        bibliography.append({
            "ref_num": next_ref_num,
            "citation_number": next_ref_num,
            "url": url,
            "title": title,
            "authors": authors,
            "year": year,
            "doi": doi,
            "source_type": best.get("source_type", "web"),
            "evidence_ids": merged_ev_ids,
            "formatted": f"{authors_str} ({year}). {title[:100]}.{doi_str} {url}",
            # PATCH-D: OpenAlex authority fields
            "openalex_id": _oa_work_id,
            "publication_type": _oa_type,             # article/preprint/book-chapter/...
            "source_type_normalized": _oa_source_type,  # journal/repository/...
            "authority_tier": _oa_tier,               # GOLD/SILVER/BRONZE/BLOCKED/UNKNOWN
        })
        next_ref_num += 1

    if merged_away:
        logger.info(
            "[wiki] FIX-DEDUP-PAPER: Collapsed %d duplicate bibliography "
            "entries (same DOI/PMID at different URLs)",
            len(merged_away),
        )

    return bibliography


# ── Disk I/O ─────────────────────────────────────────────────────────


def _write_wiki_to_disk(
    wiki_path: Path,
    section_claims: dict[str, list[dict]],
    bibliography: list[dict],
    outline: list[dict],
    query: str,
    now_str: str,
) -> None:
    """Write wiki markdown files to disk."""
    wiki_path.mkdir(parents=True, exist_ok=True)
    topics_dir = wiki_path / "topics"
    topics_dir.mkdir(exist_ok=True)

    # ── index.md ────────────────────────────────────────────────
    total_claims = sum(len(c) for c in section_claims.values())
    index_lines = [
        f"# Wiki Index",
        f"",
        f"> Query: {query}",
        f"> Built: {now_str}",
        f"> Total claims: {total_claims} | Sources: {len(bibliography)}",
        f"",
        f"## Sections",
        f"",
    ]

    for sec in outline:
        sid = sec.get("section_id", "")
        title = sec.get("title", "Unknown")
        slug = _slugify(title)
        claims = section_claims.get(sid, [])
        sources = len({c.get("source_url") for c in claims})
        index_lines.append(f"- [{title}](topics/{slug}.md) — {len(claims)} claims, {sources} sources")

    (wiki_path / "index.md").write_text("\n".join(index_lines), encoding="utf-8")

    # ── topics/*.md ─────────────────────────────────────────────
    for sec in outline:
        sid = sec.get("section_id", "")
        title = sec.get("title", "Unknown")
        slug = _slugify(title)
        claims = section_claims.get(sid, [])

        lines = [
            f"---",
            f"title: \"{title}\"",
            f"section_id: {sid}",
            f"claim_count: {len(claims)}",
            f"source_count: {len({c.get('source_url') for c in claims})}",
            f"created: {now_str}",
            f"---",
            f"",
            f"# {title}",
            f"",
        ]

        for j, claim in enumerate(claims, 1):
            ref_num = claim.get("ref_num", 0)
            lines.append(f"### Claim {j}")
            lines.append(f"- **Statement**: {claim.get('statement', '')} [REF:{ref_num}]")
            quote = claim.get("direct_quote", "")
            if quote:
                lines.append(f"- **Quote**: \"{quote[:250]}\"")
            lines.append(f"- **Source**: [{claim.get('source_title', 'Unknown')[:80]}]({claim.get('source_url', '')})")
            lines.append(f"- **Tier**: {claim.get('quality_tier', '?')} | Relevance: {claim.get('relevance_score', 0):.2f}")
            lines.append("")

        (topics_dir / f"{slug}.md").write_text("\n".join(lines), encoding="utf-8")

    # ── bibliography.md ─────────────────────────────────────────
    bib_lines = ["# Bibliography", ""]
    for b in bibliography:
        authors = ", ".join(b.get("authors", [])[:3]) if b.get("authors") else "Unknown"
        year = b.get("year", "n.d.")
        doi_str = f" DOI: {b['doi']}" if b.get("doi") else ""
        bib_lines.append(f"[{b['ref_num']}] {authors} ({year}). {b['title'][:100]}.{doi_str}")
        bib_lines.append(f"    URL: {b['url']}")
        bib_lines.append("")

    (wiki_path / "bibliography.md").write_text("\n".join(bib_lines), encoding="utf-8")

    # ── log.md ──────────────────────────────────────────────────
    log_lines = [
        f"# Wiki Log",
        f"",
        f"## [{now_str}] create | Wiki built",
        f"- Query: {query}",
        f"- Evidence: {total_claims} claims from {len(bibliography)} sources",
        f"- Sections: {sum(1 for c in section_claims.values() if c)}/{len(outline)}",
        f"",
    ]

    (wiki_path / "log.md").write_text("\n".join(log_lines), encoding="utf-8")


# ── Helpers ──────────────────────────────────────────────────────────


def _slugify(title: str) -> str:
    """Convert section title to filename slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return slug[:60]


def _find_section_title(outline: list[dict], section_id: str) -> str:
    """Find section title by ID."""
    for s in outline:
        if s.get("section_id") == section_id:
            return s.get("title", "Unknown")
    return "Unknown"
