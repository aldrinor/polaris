"""
Wiki Composer — generates the final report from wiki pages.

Each section is composed from pre-cited claims (citations already resolved at
wiki build time). No [CITE:ev_xxx] markers. No late-binding resolution. No
citation stripping. The LLM writes prose from structured claims, and a
deterministic regex converts [REF:N] → [N].

Sections are composed SEQUENTIALLY with context passing to prevent
cross-section repetition and maintain narrative flow.
"""

import logging
import os
import re
from typing import Any

from src.polaris_graph.llm.openrouter_client import OpenRouterClient
from src.polaris_graph.wiki.wiki_builder import WikiResult

logger = logging.getLogger(__name__)

MAX_CLAIMS_PER_SECTION = int(os.getenv("PG_WIKI_MAX_CLAIMS_PER_SECTION", "20"))
THIN_SECTION_THRESHOLD = int(os.getenv("PG_WIKI_THIN_THRESHOLD", "5"))
TARGET_WORDS_DEFAULT = int(os.getenv("PG_WIKI_TARGET_WORDS", "1200"))
COMPOSE_TIMEOUT = int(os.getenv("PG_WIKI_COMPOSE_TIMEOUT", "120"))
COMPOSE_MAX_TOKENS = int(os.getenv("PG_WIKI_COMPOSE_MAX_TOKENS", "8192"))
ABSTRACT_MAX_TOKENS = int(os.getenv("PG_WIKI_ABSTRACT_MAX_TOKENS", "1536"))

# 5-lens analytical scaffold (from v3 react_agent.py)
# Adds structural depth to section composition: Evidence/Mechanism/
# Comparison/Critique/Horizon. Targets analytical depth + completeness
# without sacrificing wiki's pre-cited claim constraint.
WIKI_5LENS_ENABLED = os.getenv("PG_WIKI_5LENS", "0") == "1"


# ── System Prompt ────────────────────────────────────────────────────

def _load_base_rules() -> str:
    """Load base composition rules from config/prompts/base_rules.md if available."""
    from pathlib import Path
    base_path = Path("config/prompts/base_rules.md")
    if base_path.exists():
        return base_path.read_text(encoding="utf-8").strip()
    return ""


def _build_compose_system() -> str:
    """Build the full system prompt with base rules + wiki-specific rules."""
    base_rules = _load_base_rules()
    base_block = f"\nBASE RULES FROM PROJECT:\n{base_rules}\n" if base_rules else ""

    # 5-lens analytical scaffold (from v3 react_agent.py) — forces diverse
    # analytical angles in each section, targeting depth + completeness
    five_lens_block = ""
    if WIKI_5LENS_ENABLED:
        five_lens_block = """

ANALYTICAL SCAFFOLD — Cover 5 angles in each section (integrated prose, NOT explicit headers):

LENS 1 — EVIDENCE: Key quantified findings. EVERY numeric finding MUST include the effect size AND its confidence interval (or sample size and p-value) when the source provides them. Do not state a number without its statistical context. Example: "removal efficiency reached 92% (95% CI 87-95%, n=342) [REF:3]" — not "removal efficiency reached 92% [REF:3]". Every number gets [REF:N].

LENS 2 — MECHANISM: How and why the observed effects occur. Causal chains. Physiological/biological pathways. Cite supporting mechanistic studies with [REF:N].

LENS 3 — COMPARISON: Contrast findings across studies, populations, protocols, or interventions. Highlight where evidence converges vs diverges. Use comparative language.

LENS 4 — CRITIQUE: Contradictions, limitations, caveats, methodological concerns. Which studies disagree? What populations are underrepresented? What are the boundaries of applicability?

LENS 5 — HORIZON: Gaps in current knowledge. What questions remain unanswered? What would future research need to establish?

POST-QUALITY REQUIREMENTS:
PQ-1: Synthesize findings using COMPARATIVE language. Never restate an evidence claim as a standalone sentence — always compare, contextualize, or evaluate it against other evidence.
PQ-2: Cite 2+ sources in the SAME sentence for at least 3 sentences per section (cross-source synthesis). Example: "Weight loss of 5-7% was observed across protocols [REF:3][REF:8], though the magnitude varied by population age [REF:12]."
PQ-3: Cross-reference lenses: LENS 1 findings should connect to LENS 4 limitations. For example, an effect-size finding should be followed by its methodological caveat.
PQ-4: Statistical grading. When the source provides confidence intervals, p-values, or sample sizes, the prose MUST report them inline with the finding. Strip "approximately" and similar hedges from numbers that have CIs available — the CI is the hedge.
"""

    return f"""You are a senior academic researcher writing a section of a systematic review.
{base_block}{five_lens_block}
ABSOLUTE RULES:
1. Write ONLY from the CLAIMS provided below. Do NOT add facts, statistics, or findings not in the claims.
2. Every factual statement MUST include its [REF:N] citation from the claims.
3. Interpretive commentary ("Taken together...", "These findings indicate...") is allowed WITHOUT citations — but NEVER introduce new factual claims uncited.

FIX-HALLUC-1 — ABSOLUTE HALLUCINATION BAN (wiki composer):
Use ONLY the CLAIMS provided. Do NOT pull from training knowledge, do NOT recall studies,
papers, PMIDs, author names, sample sizes, regulatory bodies, or quoted expert reactions
unless the specific fact is present in one of the CLAIMS and tagged with a [REF:N] marker.
Under NO circumstance may the prose invent or recall: PMIDs, DOIs, author names (e.g.,
"Zhong et al.", "Manoogian"), sample sizes (e.g., "20,078 adults"), follow-up durations,
percent risk ratios (e.g., "91%"), study locations, cohort names, regulatory agency positions
(FDA/EFSA/EMA/FTC/Health Canada), media outlets (e.g., "Science Media Centre"), or expert
critiques — unless the specific fact comes from a CLAIM with a [REF:N] marker. If the prose
needs such a fact and no claim supports it, write a neutral qualitative sentence without
specifics (e.g., "observational data have raised long-term safety questions") rather than
fabricating a number or proper noun. Sections containing uncited specific numbers or
uncited named entities WILL BE REJECTED by the post-synthesis audit.

FORWARD-PROMISE RULE (wiki composer): Do NOT enumerate topics the review "will cover"
unless subsequent sections in the claim set actually cover them. Do not introduce axes,
frameworks, or specific studies that are not anchored in the provided CLAIMS.
4. Write in third person, academic register. No first person.
5. Include a **Key Findings** section at the end with 3-5 bullet points summarizing the most important claims, each with [REF:N] citations.
6. Generate comparison TABLES (markdown) when claims compare two or more interventions or outcomes.
7. Do NOT use "Evidence suggests that" or "Studies have shown that" as sentence openers.
8. Do NOT include chain-of-thought, planning, reasoning, or meta-commentary about the writing process.
9. Do NOT repeat claims from PREVIOUS SECTIONS (listed below if any).
10. Every paragraph must have at least one [REF:N] citation. No citation deserts.
11. Target citation density: at least 3 citations per 100 words. Spread citations evenly — do not cluster all citations in one paragraph.
12. When citing a specific number, percentage, or statistic, the citation MUST appear immediately after the number (e.g., "reduced HbA1c by 0.5% [REF:3]").
13. SOURCE DIVERSITY: Use AT LEAST 60% of the unique sources available in the CLAIMS list. If 14 unique sources are present, your prose must cite at least 8 distinct [REF:N] numbers. Under-citing means missed evidence — integrate underused sources rather than recycling a few."""


COMPOSE_SYSTEM = _build_compose_system()


# ── Prompt Fragments ─────────────────────────────────────────────────

def _load_prompt_fragment(section_title: str) -> str:
    """Load domain-specific prompt fragment based on section topic."""
    from pathlib import Path

    prompts_dir = Path("config/prompts")
    title_lower = section_title.lower()

    fragment_map = {
        "safety": "fragment_safety.md",
        "adverse": "fragment_safety.md",
        "risk": "fragment_safety.md",
        "clinical": "fragment_clinical.md",
        "outcome": "fragment_clinical.md",
        "comparison": "fragment_comparison.md",
        "comparative": "fragment_comparison.md",
        "mechanism": "fragment_mechanism.md",
        "pathway": "fragment_mechanism.md",
        "method": "fragment_methodology.md",
        "quality": "fragment_methodology.md",
        "evidence gap": "fragment_methodology.md",
    }

    for keyword, filename in fragment_map.items():
        if keyword in title_lower:
            fpath = prompts_dir / filename
            if fpath.exists():
                return fpath.read_text(encoding="utf-8").strip()

    return ""


# ── Section Composition ──────────────────────────────────────────────


def _format_claims_for_prompt(claims: list[dict]) -> str:
    """Format claims as numbered input for the LLM."""
    lines = []
    dropped_no_ref = 0
    dropped_no_statement = 0
    for claim in claims:
        ref = claim.get("ref_num", 0)
        statement = claim.get("statement", "")
        quote = claim.get("direct_quote", "")

        if not statement:
            dropped_no_statement += 1
            continue
        if not ref:
            # Was previously silent. Loud now so upstream url_to_ref
            # mismatches surface as a warning rather than a zero-citation
            # section with hallucinated prose.
            dropped_no_ref += 1
            continue
        lines.append(f"CLAIM [REF:{ref}]: {statement}")
        if quote and quote.lower() != statement.lower():
            lines.append(f"  QUOTE: \"{quote[:200]}\"")

    if dropped_no_ref or dropped_no_statement:
        logger.warning(
            "[wiki-compose] _format_claims_for_prompt dropped %d claims: "
            "%d without ref_num, %d without statement (of %d total)",
            dropped_no_ref + dropped_no_statement,
            dropped_no_ref, dropped_no_statement, len(claims),
        )

    return "\n".join(lines)


async def _compose_one_section(
    client: OpenRouterClient,
    section_title: str,
    section_description: str,
    claims: list[dict],
    section_order: int,
    total_sections: int,
    prev_summaries: str,
    query: str,
    unsupported_spans: list[str] | None = None,
) -> str:
    """Compose one report section from pre-cited claims."""
    # Sort by relevance (best evidence first)
    sorted_claims = sorted(
        claims, key=lambda c: c.get("relevance_score", 0), reverse=True,
    )

    # Cap claims for context window
    if len(sorted_claims) > MAX_CLAIMS_PER_SECTION:
        sorted_claims = sorted_claims[:MAX_CLAIMS_PER_SECTION]

    claims_text = _format_claims_for_prompt(sorted_claims)

    # FIX-DIVERSITY: compute the source-diversity floor for THIS section.
    # G-Eval found sections under-citing their available source pool
    # (e.g., 4 of 14 = 29%). Composer prompt now reports the concrete floor.
    unique_refs_available = len({c.get("ref_num", 0) for c in sorted_claims if c.get("ref_num")})
    diversity_floor = max(1, int(unique_refs_available * 0.6))

    # Determine target words
    if len(sorted_claims) < THIN_SECTION_THRESHOLD:
        target_words = "300-500"
        thin_note = (
            "\nNOTE: Limited evidence available for this section. Write a concise "
            "section focusing on what IS known. Acknowledge evidence gaps explicitly."
        )
    else:
        target_words = str(TARGET_WORDS_DEFAULT)
        thin_note = ""

    # Load domain fragment
    domain_fragment = _load_prompt_fragment(section_title)
    if domain_fragment:
        domain_fragment = f"\nDOMAIN GUIDANCE:\n{domain_fragment}\n"

    # Build previous sections context
    prev_block = ""
    transition_directive = ""
    if prev_summaries:
        prev_block = f"\nPREVIOUS SECTIONS (do NOT repeat their content):\n{prev_summaries}\n"
        # FIX-COHERENCE: Force an explicit bridge from the prior section.
        # G-Eval coherence dropped to 7/10 because adjacent sections jumped
        # topics without connecting language. The prompt now requires a
        # transition sentence in the FIRST paragraph that names the prior
        # section and explains the conceptual link to this one.
        if section_order > 1:
            transition_directive = (
                f"\nTRANSITION REQUIREMENT: The first paragraph MUST open with one\n"
                f"sentence that bridges from the prior section to this section.\n"
                f"Name what was just covered, then explain why this section follows\n"
                f"as a logical next step. Vary your bridging language across sections —\n"
                f"do not start every section with the same phrase. Examples of\n"
                f"acceptable openers (use a different one each time): \"Whereas the\n"
                f"prior section established X, this section turns to Y...\", \"With X\n"
                f"now characterized, the next question is Y...\", \"Given the X just\n"
                f"described, we now address Y...\", \"The X reviewed above raises a\n"
                f"second question: Y...\". This transition sentence does NOT need a\n"
                f"citation.\n"
            )

    # FIX-HALLUC-REMEDIATE: When rewriting a flagged section, inject the
    # specific unsupported spans so the LLM knows what to avoid.
    remediation_block = ""
    if unsupported_spans:
        span_list = "\n".join(f"  - {s}" for s in unsupported_spans[:10])
        remediation_block = (
            f"\nREMEDIATION — REWRITE MODE: A prior draft of this section was audited "
            f"by an NLI hallucination detector and the following sentences were flagged "
            f"as UNSUPPORTED by the provided claims:\n{span_list}\n\n"
            f"Do NOT include these sentences or similar unsupported claims in your "
            f"rewrite. Write ONLY from the CLAIMS below. If a topic cannot be "
            f"substantiated by a claim, omit it entirely rather than stating it "
            f"without a [REF:N] citation.\n"
        )

    prompt = (
        f"Write section {section_order}/{total_sections}: \"{section_title}\"\n"
        f"of a systematic review answering: \"{query}\"\n"
        f"\nSection focus: {section_description}\n"
        f"{thin_note}"
        f"{domain_fragment}"
        f"{remediation_block}"
        f"{prev_block}"
        f"{transition_directive}"
        f"\nCLAIMS (use ONLY these, cite with [REF:N]):\n"
        f"{claims_text}\n"
        f"\nSOURCE DIVERSITY FLOOR: this section has {unique_refs_available} unique sources\n"
        f"in the claims. Your composed prose MUST cite at least {diversity_floor} of\n"
        f"them (60% floor). Recycling fewer is a quality defect.\n"
        f"\nWrite the section now. Target {target_words} words."
    )

    result = await client.generate(
        prompt=prompt,
        system=COMPOSE_SYSTEM,
        max_tokens=COMPOSE_MAX_TOKENS,
        temperature=0.3,
        timeout=COMPOSE_TIMEOUT,
        reasoning_exclude=True,
    )

    return result.content


# ── Report Composition ───────────────────────────────────────────────


async def compose_from_wiki(
    client: OpenRouterClient,
    wiki_result: WikiResult,
    query: str,
    outline: list[dict],
) -> dict:
    """
    Compose a full report from wiki pages.

    Returns a dict matching the exact contract of synthesize_report():
    final_report, sections, bibliography, quality_metrics, etc.
    """
    from src.polaris_graph.synthesis.section_writer import _scrub_cot

    sections = []
    prev_summaries = ""
    section_evidence_map: dict[str, list[str]] = {}
    failed_sections: list[str] = []

    total_sections = len(outline)

    for i, sec in enumerate(outline):
        sid = sec.get("section_id", f"s{i:02d}")
        title = sec.get("title", "Unknown")
        description = sec.get("description", title)
        claims = wiki_result.section_claims.get(sid, [])

        if not claims:
            logger.warning("[wiki-compose] Section %s '%s' has 0 claims — skipping", sid, title[:40])
            failed_sections.append(sid)
            continue

        logger.info(
            "[wiki-compose] Composing %s: '%s' (%d claims, %d sources)",
            sid, title[:50], len(claims),
            len({c.get("source_url") for c in claims}),
        )

        # Track which evidence was provided
        section_evidence_map[sid] = [
            c.get("evidence_id", "") for c in claims if c.get("evidence_id")
        ]

        # Compose with retry. Both exceptions AND empty content trigger retry —
        # reasoning models (gpt-5/o3) sometimes return HTTP 200 with empty content
        # when the reasoning budget consumes the full token allowance.
        content = ""
        for attempt in range(2):
            try:
                content = await _compose_one_section(
                    client=client,
                    section_title=title,
                    section_description=description,
                    claims=claims,
                    section_order=i + 1,
                    total_sections=total_sections,
                    prev_summaries=prev_summaries,
                    query=query,
                )
                if content and content.strip():
                    break
                # Empty content — log and retry (or fail on second attempt)
                if attempt == 0:
                    logger.warning(
                        "[wiki-compose] Section %s attempt 1 returned empty content "
                        "(possible reasoning budget overflow) — retrying",
                        sid,
                    )
                else:
                    logger.error(
                        "[wiki-compose] Section %s returned empty content twice — skipping",
                        sid,
                    )
                    failed_sections.append(sid)
            except Exception as exc:
                if attempt == 0:
                    logger.warning(
                        "[wiki-compose] Section %s attempt 1 failed: %s — retrying",
                        sid, str(exc)[:100],
                    )
                else:
                    logger.error(
                        "[wiki-compose] Section %s failed after 2 attempts: %s — skipping",
                        sid, str(exc)[:100],
                    )
                    failed_sections.append(sid)

        if not content or not content.strip():
            continue

        # Scrub CoT leakage
        content = _scrub_cot(content)

        # Deterministic citation resolution.
        # Models intermittently emit [REF:N], [CITE:N], or [Ref:N] despite the
        # system prompt — collapse all numeric variants to canonical [N].
        # Validated against gpt-4o-mini output (Section 3 leaked [CITE:N]).
        content = re.sub(r"\[(?:REF|CITE|Ref|Cite|ref|cite):(\d+)\]", r"[\1]", content)

        # Remove duplicate section headers the LLM may have generated
        # (the assembler adds ## Title, so strip any leading # Title from content)
        content = re.sub(
            r"^\s*#{1,3}\s+" + re.escape(title[:30]) + r"[^\n]*\n+",
            "",
            content,
            count=1,
            flags=re.IGNORECASE,
        )
        content = content.lstrip()

        # Count metrics
        word_count = len(content.split())
        citation_nums = re.findall(r"\[(\d+)\]", content)
        unique_citations = sorted(set(int(n) for n in citation_nums))

        sections.append({
            "section_id": sid,
            "title": title,
            "content": content,
            "word_count": word_count,
            "citation_ids": [f"[{n}]" for n in unique_citations],
            "evidence_ids": section_evidence_map.get(sid, []),
        })

        logger.info("  → %d words, %d citations", word_count, len(unique_citations))

        # Build summary for next section context (text + cited REFs)
        sentences = re.split(r"(?<=[.!?])\s+", content)
        summary = " ".join(sentences[:2]) if sentences else ""
        cited_refs = ", ".join(f"[{n}]" for n in unique_citations[:10])
        prev_summaries += f"- {title}: {summary[:200]} (cited: {cited_refs})\n"

    # ── Generate abstract ────────────────────────────────────────
    abstract = await _compose_abstract(client, query, sections, wiki_result.bibliography)

    # ── Assemble final report ────────────────────────────────────
    final_report = _assemble_report(query, abstract, sections, wiki_result.bibliography)

    # ── Partial failure check ────────────────────────────────────
    composed_count = len(sections)
    if composed_count < total_sections * 0.5 and total_sections > 0:
        logger.error(
            "[wiki-compose] PARTIAL FAILURE: only %d/%d sections composed",
            composed_count, total_sections,
        )
        status = "partial_failure"
    else:
        status = "complete"

    # ── Quality metrics (reuse existing compute_quality_metrics) ──
    total_words = sum(s["word_count"] for s in sections)
    total_citations = sum(len(s["citation_ids"]) for s in sections)
    unique_sources = len(wiki_result.bibliography)
    zero_cite_sections = sum(1 for s in sections if not s["citation_ids"])

    # Build quality metrics inline (compute_quality_metrics expects TypedDict
    # EvidencePiece/ReportSection which our wiki dicts don't match exactly)
    all_evidence = wiki_result.unassigned_evidence + [
        c for cl in wiki_result.section_claims.values() for c in cl
    ]
    gold_count = sum(1 for e in all_evidence if e.get("quality_tier") == "GOLD")
    silver_count = sum(1 for e in all_evidence if e.get("quality_tier") == "SILVER")

    # W3.11: Use the canonical faithfulness helper so state.faithfulness_score
    # and quality_metrics.faithfulness_score stay in sync. Computed from the
    # actual claims assigned into wiki sections — same definition both paths
    # use. The earlier -1.0 sentinel was a "G-Eval does it externally" stub
    # but in practice callers treated it as a bug (dual source of truth).
    from src.polaris_graph.agents.synthesizer import compute_faithfulness
    _wiki_claims = [
        c for cl in wiki_result.section_claims.values() for c in cl
    ]
    _wiki_faith = compute_faithfulness(_wiki_claims)

    quality = {
        "total_words": total_words,
        "total_sections": len(sections),
        "total_citations": total_citations,
        "unique_sources": unique_sources,
        "total_evidence": len(all_evidence),
        "gold_evidence": gold_count,
        "silver_evidence": silver_count,
        "bronze_evidence": len(all_evidence) - gold_count - silver_count,
        "faithfulness_score": _wiki_faith,
        "avg_citations_per_section": (
            total_citations / max(len(sections), 1)
        ),
    }

    # Augment with wiki-specific metrics
    quality["zero_cite_sections"] = zero_cite_sections
    quality["failed_sections"] = len(failed_sections)
    quality["wiki_claims"] = wiki_result.stats.get("total_claims_in_wiki", 0)

    # Quality gate check (log, don't block)
    gate_failures = []
    if total_words < 2000:
        gate_failures.append(f"words={total_words}<2000")
    if total_citations < 5:
        gate_failures.append(f"citations={total_citations}<5")
    if unique_sources < 5:
        gate_failures.append(f"sources={unique_sources}<5")
    if zero_cite_sections > 0:
        gate_failures.append(f"zero_cite_sections={zero_cite_sections}")

    gate_result = "passed" if not gate_failures else f"failed: {', '.join(gate_failures)}"
    if gate_failures:
        logger.warning("[wiki-compose] Quality gate: %s", gate_result)
    else:
        logger.info("[wiki-compose] Quality gate: PASSED")

    # ── Build evidence chain (RAGAS compatibility — full fields) ──
    evidence_chain = []
    for claims in wiki_result.section_claims.values():
        for claim in claims:
            evidence_chain.append({
                "evidence_id": claim.get("evidence_id", ""),
                "source_url": claim.get("source_url", ""),
                "source_title": claim.get("source_title", ""),
                "source_type": claim.get("source_type", ""),
                "statement": claim.get("statement", ""),
                "direct_quote": claim.get("direct_quote", ""),
                "quality_tier": claim.get("quality_tier", ""),
                "relevance_score": claim.get("relevance_score", 0.0),
                "perspective": claim.get("perspective", ""),
                "methodology": claim.get("methodology", ""),
                "conditions": claim.get("conditions", ""),
                "limitations": claim.get("limitations", ""),
                "strength_signals": claim.get("strength_signals", []),
                "year": claim.get("year"),
                "authors": claim.get("authors", []),
                "doi": claim.get("doi"),
            })

    # ── Build section_outline for output ─────────────────────────
    section_outline = [
        {
            "section_id": s.get("section_id", ""),
            "title": s.get("title", ""),
            "description": s.get("description", ""),
            "evidence_ids": s.get("evidence_ids", []),
            "target_words": s.get("target_words", TARGET_WORDS_DEFAULT),
            "order": s.get("order", i),
        }
        for i, s in enumerate(outline)
    ]

    logger.info(
        "[wiki-compose] Report complete: %d words, %d citations, %d sources, gate=%s",
        total_words, total_citations, unique_sources, gate_result,
    )

    # FIX-HALLUC-WIKI-WIRE: Run post-synthesis hallucination audit on composed
    # sections. The detector was previously only wired to synthesizer.py, so
    # wiki-composed reports went unchecked regardless of the env flag.
    hallucination_audit: list[dict] = []
    try:
        from src.polaris_graph.agents.hallucination_detector import (
            audit_sections_for_hallucination,
            _is_enabled as _halluc_enabled,
        )
        if _halluc_enabled():
            audit_sections = [
                {
                    "section_id": s.get("section_id", ""),
                    "title": s.get("title", ""),
                    "content": s.get("content", ""),
                    "evidence_ids": s.get("evidence_ids", []),
                }
                for s in sections
            ]
            hallucination_audit = audit_sections_for_hallucination(
                sections=audit_sections,
                evidence=evidence_chain,
                research_query=query,
            ) or []
            if hallucination_audit:
                flagged = sum(1 for r in hallucination_audit if r.get("needs_rewrite"))
                avg = sum(r.get("hallucination_ratio", 0) for r in hallucination_audit) / len(hallucination_audit)
                logger.info(
                    "[wiki-compose] Hallucination audit: %d sections audited, avg unsupported %.1f%%, %d flagged for rewrite",
                    len(hallucination_audit), avg * 100, flagged,
                )

                # FIX-HALLUC-REMEDIATE: Re-compose flagged sections with stricter
                # anti-hallucination emphasis. The synthesizer.py path has this via
                # revise_section(); wiki_composer was missing it entirely.
                if flagged > 0:
                    flagged_ids = {
                        r["section_id"]
                        for r in hallucination_audit
                        if r.get("needs_rewrite")
                    }
                    # Collect the unsupported spans per section for targeted guidance
                    flagged_spans_map = {}
                    for r in hallucination_audit:
                        if r.get("needs_rewrite"):
                            flagged_spans_map[r["section_id"]] = [
                                s.get("text", "")[:120]
                                for s in r.get("hallucinated_spans", [])[:5]
                            ]

                    rewrite_count = 0
                    _remediate_timeout = int(os.getenv("PG_SECTION_WRITE_TIMEOUT", "300"))
                    for i, sec in enumerate(sections):
                        sid = sec.get("section_id", "")
                        if sid not in flagged_ids:
                            continue
                        # Find matching outline entry and claims
                        sec_outline = next(
                            (s for s in outline if s.get("section_id") == sid), None
                        )
                        if not sec_outline:
                            continue
                        sec_claims = wiki_result.section_claims.get(sid, [])
                        if not sec_claims:
                            continue
                        unsupported_examples = flagged_spans_map.get(sid, [])
                        logger.info(
                            "[wiki-compose] REMEDIATE: Re-composing section '%s' "
                            "(%d unsupported spans flagged)",
                            sec.get("title", "")[:40],
                            len(unsupported_examples),
                        )
                        try:
                            import asyncio as _aio
                            revised_content = await _aio.wait_for(
                                _compose_one_section(
                                    client=client,
                                    section_title=sec.get("title", ""),
                                    section_description=sec_outline.get("description", ""),
                                    claims=sec_claims,
                                    section_order=sec_outline.get("order", i + 1),
                                    total_sections=len(outline),
                                    prev_summaries="",
                                    query=query,
                                    unsupported_spans=unsupported_examples,
                                ),
                                timeout=_remediate_timeout,
                            )
                            if revised_content and len(revised_content.split()) >= 50:
                                sections[i]["content"] = _scrub_cot(revised_content)
                                rewrite_count += 1
                                logger.info(
                                    "[wiki-compose] REMEDIATE: Rewrote '%s' (%d words)",
                                    sec.get("title", "")[:40],
                                    len(revised_content.split()),
                                )
                        except Exception as _rev_exc:
                            logger.warning(
                                "[wiki-compose] REMEDIATE: Rewrite failed for '%s': %s — keeping original",
                                sec.get("title", "")[:40],
                                str(_rev_exc)[:200],
                            )
                    if rewrite_count > 0:
                        # Reassemble report with rewritten sections
                        # Extract abstract from existing report (between "## Abstract" and first section)
                        import re as _re
                        _abstract_match = _re.search(
                            r"## Abstract\s*\n\n(.*?)(?=\n## [^R])", final_report, _re.DOTALL,
                        )
                        _abstract_text = _abstract_match.group(1).strip() if _abstract_match else ""
                        final_report = _assemble_report(
                            query=query,
                            abstract=_abstract_text,
                            sections=sections,
                            bibliography=wiki_result.bibliography,
                        )
                        logger.info(
                            "[wiki-compose] REMEDIATE: %d/%d flagged sections rewritten",
                            rewrite_count, flagged,
                        )
        else:
            logger.info("[wiki-compose] Hallucination audit disabled (PG_HALLUCINATION_DETECT_ENABLED=0)")
    except Exception as _halluc_exc:
        logger.warning(
            "[wiki-compose] Hallucination audit failed: %s", str(_halluc_exc)[:200],
        )

    return {
        "section_outline": section_outline,
        "sections": sections,
        "bibliography": wiki_result.bibliography,
        "evidence_chain": evidence_chain,
        "draft_report": final_report,
        "final_report": final_report,
        "evidence_clusters": [],
        "quality_metrics": quality,
        "status": status,
        "converged": status == "complete" and not gate_failures,
        "convergence_reason": f"wiki_synthesis: {gate_result}",
        "quality_gate_result": gate_result,
        "section_evidence_map": section_evidence_map,
        "expansion_passes_used": 0,
        "hallucination_audit": hallucination_audit,
        "gap_queries": [],
    }


# ── Abstract ─────────────────────────────────────────────────────────


async def _compose_abstract(
    client: OpenRouterClient,
    query: str,
    sections: list[dict],
    bibliography: list[dict],
) -> str:
    """Generate a grounded abstract from section summaries."""
    summaries = "\n".join(
        f"- {s['title']}: {s['content'][:300]}..."
        for s in sections
    )

    prompt = (
        f"Write a 200-word abstract for a systematic review answering: \"{query}\"\n\n"
        f"Section summaries:\n{summaries}\n\n"
        f"RULES:\n"
        f"- Include 2-3 key quantitative findings, each followed by a citation\n"
        f"  in the form [3] where 3 is a real number from 1 to {len(bibliography)}\n"
        f"- NEVER write the literal token [N] — this is a placeholder, not a citation\n"
        f"- State the scope (number of sources, topics covered)\n"
        f"- Note major limitations or evidence gaps\n"
        f"- Academic register, third person\n"
        f"- Do NOT include chain-of-thought or planning"
    )

    try:
        result = await client.generate(
            prompt=prompt,
            system="You are an academic researcher writing a concise abstract.",
            max_tokens=ABSTRACT_MAX_TOKENS,
            temperature=0.2,
            timeout=int(os.getenv("PG_WIKI_ABSTRACT_TIMEOUT", "60")),
            reasoning_exclude=True,
        )
        abstract = result.content
        # Scrub CoT
        from src.polaris_graph.synthesis.section_writer import _scrub_cot
        abstract = _scrub_cot(abstract)
        # Resolve any prefixed citations (REF/CITE) → bare [N]
        abstract = re.sub(r"\[(?:REF|CITE|Ref|Cite|ref|cite):(\d+)\]", r"[\1]", abstract)
        # Strip literal [N] placeholders if model still emits them
        abstract = re.sub(r"\[N\]", "", abstract)
        return abstract
    except Exception as exc:
        logger.warning("[wiki-compose] Abstract generation failed: %s", str(exc)[:100])
        # Fallback: first sentence of each section
        fallback = " ".join(
            re.split(r"(?<=[.!?])\s+", s["content"])[0]
            for s in sections[:3]
        )
        return fallback


# ── Report Assembly ──────────────────────────────────────────────────


def _assemble_report(
    query: str,
    abstract: str,
    sections: list[dict],
    bibliography: list[dict],
) -> str:
    """Assemble final markdown report from sections + bibliography."""
    parts = [f"# {query}", ""]

    if abstract:
        parts.extend(["## Abstract", "", abstract, ""])

    for section in sections:
        parts.extend([
            f"## {section['title']}",
            "",
            section["content"],
            "",
        ])

    parts.extend(["## References", ""])
    for bib in bibliography:
        authors = ", ".join(bib.get("authors", [])[:3]) if bib.get("authors") else "Unknown"
        year = bib.get("year", "n.d.")
        title = bib.get("title", "Unknown")[:100]
        url = bib.get("url", "")
        doi = f" DOI: {bib['doi']}" if bib.get("doi") else ""
        parts.append(f"[{bib['ref_num']}] {authors} ({year}). {title}.{doi} {url}")
        parts.append("")

    return "\n".join(parts)
