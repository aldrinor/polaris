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

    return f"""You are a senior academic researcher writing a section of a systematic review.
{base_block}
ABSOLUTE RULES:
1. Write ONLY from the CLAIMS provided below. Do NOT add facts, statistics, or findings not in the claims.
2. Every factual statement MUST include its [REF:N] citation from the claims.
3. Interpretive commentary ("Taken together...", "These findings indicate...") is allowed WITHOUT citations — but NEVER introduce new factual claims uncited.
4. Write in third person, academic register. No first person.
5. Include a **Key Findings** section at the end with 3-5 bullet points summarizing the most important claims, each with [REF:N] citations.
6. Generate comparison TABLES (markdown) when claims compare two or more interventions or outcomes.
7. Do NOT use "Evidence suggests that" or "Studies have shown that" as sentence openers.
8. Do NOT include chain-of-thought, planning, reasoning, or meta-commentary about the writing process.
9. Do NOT repeat claims from PREVIOUS SECTIONS (listed below if any).
10. Every paragraph must have at least one [REF:N] citation. No citation deserts."""


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
    for claim in claims:
        ref = claim.get("ref_num", 0)
        statement = claim.get("statement", "")
        quote = claim.get("direct_quote", "")

        if statement and ref:
            lines.append(f"CLAIM [REF:{ref}]: {statement}")
            if quote and quote.lower() != statement.lower():
                lines.append(f"  QUOTE: \"{quote[:200]}\"")

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
    if prev_summaries:
        prev_block = f"\nPREVIOUS SECTIONS (do NOT repeat):\n{prev_summaries}\n"

    prompt = (
        f"Write section {section_order}/{total_sections}: \"{section_title}\"\n"
        f"of a systematic review answering: \"{query}\"\n"
        f"\nSection focus: {section_description}\n"
        f"{thin_note}"
        f"{domain_fragment}"
        f"{prev_block}"
        f"\nCLAIMS (use ONLY these, cite with [REF:N]):\n"
        f"{claims_text}\n"
        f"\nWrite the section now. Target {target_words} words."
    )

    result = await client.generate(
        prompt=prompt,
        system=COMPOSE_SYSTEM,
        max_tokens=4096,
        temperature=0.3,
        timeout=COMPOSE_TIMEOUT,
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

        # Compose with retry
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
                break
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

        if not content:
            continue

        # Scrub CoT leakage
        content = _scrub_cot(content)

        # Deterministic citation resolution: [REF:N] → [N]
        content = re.sub(r"\[REF:(\d+)\]", r"[\1]", content)

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

    quality = {
        "total_words": total_words,
        "total_sections": len(sections),
        "total_citations": total_citations,
        "unique_sources": unique_sources,
        "total_evidence": len(all_evidence),
        "gold_evidence": gold_count,
        "silver_evidence": silver_count,
        "bronze_evidence": len(all_evidence) - gold_count - silver_count,
        "faithfulness_score": -1.0,  # G-Eval computes this externally
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
        "hallucination_audit": {},
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
        f"- Include 2-3 key quantitative findings with [N] citations\n"
        f"- State the scope (number of sources, topics covered)\n"
        f"- Note major limitations or evidence gaps\n"
        f"- Academic register, third person\n"
        f"- Do NOT include chain-of-thought or planning"
    )

    try:
        result = await client.generate(
            prompt=prompt,
            system="You are an academic researcher writing a concise abstract.",
            max_tokens=1024,
            temperature=0.2,
            timeout=60,
        )
        abstract = result.content
        # Scrub CoT
        from src.polaris_graph.synthesis.section_writer import _scrub_cot
        abstract = _scrub_cot(abstract)
        # Convert [REF:N] → [N] in case LLM uses that format
        abstract = re.sub(r"\[REF:(\d+)\]", r"[\1]", abstract)
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
