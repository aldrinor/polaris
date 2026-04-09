"""
Phase 0B: Wiki Composition Proof-of-Concept

Takes TEST_090's existing evidence, groups by topic similarity to outline sections,
composes each section from ONLY the assigned claims with pre-resolved citations,
assembles a report, and runs G-Eval.

This proves whether structured composition (wiki pattern) improves faithfulness
over the current pipeline architecture — WITHOUT building any infrastructure.

Cost: ~$1 (10 compose calls + G-Eval). Time: ~15 min.
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.polaris_graph.llm.openrouter_client import OpenRouterClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger(__name__)

SOURCE_FILE = "outputs/polaris_graph/PG_TEST_090.json"
OUTPUT_FILE = "outputs/polaris_graph/PG_TEST_090_wiki_proof.json"
REPORT_FILE = "outputs/polaris_graph/PG_TEST_090_wiki_proof_report.md"


def group_evidence_by_section(evidence: list[dict], sections: list[dict]) -> dict[str, list[dict]]:
    """
    Group evidence by section using keyword overlap (no embeddings needed).
    Each evidence piece goes to the section whose title+description best matches
    the evidence statement. Evidence can go to multiple sections if relevant.
    """
    section_evidence: dict[str, list[dict]] = {s["section_id"]: [] for s in sections}

    for ev in evidence:
        statement = ev.get("statement", "").lower()
        quote = ev.get("direct_quote", "").lower()
        text = f"{statement} {quote}"

        # Score each section by keyword overlap
        scores = []
        for sec in sections:
            title = sec.get("title", "").lower()
            desc = sec.get("description", "").lower()
            keywords = set(re.findall(r'\b[a-z]{4,}\b', f"{title} {desc}"))
            evidence_words = set(re.findall(r'\b[a-z]{4,}\b', text))
            overlap = len(keywords & evidence_words)
            scores.append((sec["section_id"], overlap))

        # Assign to top 2 matching sections (evidence can be relevant to multiple)
        scores.sort(key=lambda x: x[1], reverse=True)
        for sid, score in scores[:2]:
            if score >= 2:  # At least 2 keyword overlaps
                section_evidence[sid].append(ev)

    # Log distribution
    for sid, evs in section_evidence.items():
        sec_title = next((s["title"] for s in sections if s["section_id"] == sid), "?")
        logger.info(f"  {sid}: {len(evs)} evidence → {sec_title[:50]}")

    return section_evidence


def format_claims_for_compose(evidence: list[dict]) -> tuple[str, list[dict]]:
    """
    Format evidence as numbered claims with pre-resolved citations.
    Returns (formatted_text, bibliography_entries).
    """
    # Dedup by source URL, keeping best evidence per source
    by_url: dict[str, list[dict]] = {}
    for ev in evidence:
        url = ev.get("source_url", "")
        if url not in by_url:
            by_url[url] = []
        by_url[url].append(ev)

    # Build bibliography (one entry per unique source)
    bibliography = []
    url_to_refnum = {}
    for i, (url, evs) in enumerate(by_url.items(), 1):
        best = max(evs, key=lambda e: e.get("relevance_score", 0))
        bibliography.append({
            "ref_num": i,
            "url": url,
            "title": best.get("source_title", "Unknown"),
            "authors": best.get("authors", []),
            "year": best.get("year"),
            "doi": best.get("doi"),
        })
        url_to_refnum[url] = i

    # Format claims with [REF:N]
    lines = []
    for ev in evidence:
        ref_num = url_to_refnum.get(ev.get("source_url", ""), 0)
        statement = ev.get("statement", "")
        quote = ev.get("direct_quote", "")
        if statement and ref_num:
            lines.append(f"- CLAIM: {statement} [REF:{ref_num}]")
            if quote and quote != statement:
                lines.append(f"  QUOTE: \"{quote[:200]}\"")

    return "\n".join(lines), bibliography


COMPOSE_SYSTEM = """You are a senior academic researcher writing a section of a systematic review.

RULES:
1. Write ONLY from the CLAIMS provided below. Do not add facts, statistics, or findings not in the claims.
2. Every factual statement MUST include its [REF:N] citation from the claims.
3. You MAY add interpretive commentary ("These findings suggest...", "Taken together...") WITHOUT citations — but only for synthesis, never for new facts.
4. Write in third person, academic register.
5. Include a "**Key Findings**" section at the end with 3-5 bullet points summarizing the most important claims.
6. Target 800-1500 words.
7. Do NOT use "Evidence suggests that" as a sentence opener.
8. Do NOT include chain-of-thought, planning, or meta-commentary about the writing process.
"""


async def compose_section(
    client: OpenRouterClient,
    section_title: str,
    section_description: str,
    claims_text: str,
    section_order: int,
    total_sections: int,
    prev_summary: str = "",
) -> str:
    """Compose one section from pre-cited claims."""
    context_block = ""
    if prev_summary:
        context_block = f"\nPREVIOUS SECTIONS COVERED:\n{prev_summary}\nDo NOT repeat these points.\n"

    prompt = f"""Write section {section_order}/{total_sections}: "{section_title}"

Section focus: {section_description}
{context_block}
CLAIMS (use ONLY these, cite with [REF:N]):
{claims_text}

Write the section now. Every factual claim must have [REF:N]. Target 800-1500 words."""

    result = await client.generate(
        prompt=prompt,
        system=COMPOSE_SYSTEM,
        max_tokens=4096,
        temperature=0.3,
    )
    return result.content


async def run_proof():
    """Main proof-of-concept execution."""
    logger.info("=" * 60)
    logger.info("Phase 0B: Wiki Composition Proof-of-Concept")
    logger.info("=" * 60)

    # Load TEST_090 data
    with open(SOURCE_FILE) as f:
        data = json.load(f)

    evidence = data["evidence"]
    outline = data["section_outline"]
    query = data["original_query"]

    logger.info(f"Query: {query[:80]}")
    logger.info(f"Evidence: {len(evidence)} pieces ({sum(1 for e in evidence if e.get('quality_tier') == 'GOLD')} GOLD, "
                f"{sum(1 for e in evidence if e.get('quality_tier') == 'SILVER')} SILVER)")
    logger.info(f"Sections: {len(outline)}")

    # Filter to GOLD + SILVER only
    quality_evidence = [e for e in evidence if e.get("quality_tier") in ("GOLD", "SILVER")]
    logger.info(f"After quality filter: {len(quality_evidence)} evidence (GOLD+SILVER only)")

    # Group evidence by section
    logger.info("\nGrouping evidence by section (keyword overlap):")
    section_evidence = group_evidence_by_section(quality_evidence, outline)

    # Initialize LLM client
    client = OpenRouterClient()

    # Compose each section sequentially
    sections = []
    all_bibliography = []
    prev_summary = ""
    start_time = time.time()

    for i, sec in enumerate(outline):
        sid = sec["section_id"]
        title = sec["title"]
        desc = sec.get("description", title)
        evs = section_evidence.get(sid, [])

        if not evs:
            logger.warning(f"Section {sid} '{title[:40]}' has 0 evidence — skipping")
            continue

        claims_text, bib = format_claims_for_compose(evs)
        all_bibliography.extend(bib)

        logger.info(f"\nComposing {sid}: '{title[:50]}' ({len(evs)} evidence, {len(bib)} sources)")

        try:
            content = await compose_section(
                client=client,
                section_title=title,
                section_description=desc,
                claims_text=claims_text,
                section_order=i + 1,
                total_sections=len(outline),
                prev_summary=prev_summary,
            )
        except (ValueError, Exception) as exc:
            logger.warning(f"Section {sid} compose failed: {exc} — skipping")
            continue

        # Convert [REF:N] to [N] (deterministic)
        content = re.sub(r'\[REF:(\d+)\]', r'[\1]', content)

        # Count citations
        cite_count = len(re.findall(r'\[\d+\]', content))
        word_count = len(content.split())

        sections.append({
            "section_id": sid,
            "title": title,
            "content": content,
            "word_count": word_count,
            "citation_count": cite_count,
            "evidence_ids": [e.get("evidence_id", "") for e in evs],
        })

        logger.info(f"  → {word_count} words, {cite_count} citations")

        # Build summary for next section
        # Extract first 2 sentences as summary
        sentences = re.split(r'(?<=[.!?])\s+', content)
        prev_summary += f"- {title}: {' '.join(sentences[:2])}\n"

    elapsed = time.time() - start_time

    # Dedup bibliography by URL
    seen_urls = set()
    unique_bib = []
    for b in all_bibliography:
        if b["url"] not in seen_urls:
            seen_urls.add(b["url"])
            unique_bib.append(b)

    # Re-number bibliography
    for i, b in enumerate(unique_bib, 1):
        b["ref_num"] = i

    # Assemble report
    total_words = sum(s["word_count"] for s in sections)
    total_cites = sum(s["citation_count"] for s in sections)

    report_md = f"# {query}\n\n"
    for s in sections:
        report_md += f"## {s['title']}\n\n{s['content']}\n\n"
    report_md += "## References\n\n"
    for b in unique_bib:
        authors = ", ".join(b.get("authors", [])[:3]) if b.get("authors") else "Unknown"
        year = b.get("year", "n.d.")
        report_md += f"[{b['ref_num']}] {authors} ({year}). {b['title'][:80]}. {b['url']}\n\n"

    # Build output JSON (G-Eval compatible)
    output = {
        "vector_id": "PG_TEST_090_WIKI_PROOF",
        "original_query": query,
        "sections": sections,
        "final_report": report_md,
        "bibliography": unique_bib,
        "quality_metrics": {
            "total_words": total_words,
            "total_sections": len(sections),
            "total_citations": total_cites,
            "unique_sources": len(unique_bib),
            "faithfulness_score": None,  # To be filled by G-Eval
            "total_evidence": len(quality_evidence),
            "gold_evidence": sum(1 for e in quality_evidence if e.get("quality_tier") == "GOLD"),
            "silver_evidence": sum(1 for e in quality_evidence if e.get("quality_tier") == "SILVER"),
        },
        "evidence": quality_evidence,
        "llm_usage": {
            "total_cost_usd": client.usage.total_cost_usd,
            "total_calls": client.usage.total_calls,
        },
    }

    # Save
    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report_md)

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 0B RESULTS")
    logger.info("=" * 60)
    logger.info(f"Sections composed: {len(sections)}/{len(outline)}")
    logger.info(f"Total words: {total_words}")
    logger.info(f"Total citations: {total_cites}")
    logger.info(f"Unique sources: {len(unique_bib)}")
    logger.info(f"Cost: ${client.usage.total_cost_usd:.4f}")
    logger.info(f"Time: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    logger.info(f"Output: {OUTPUT_FILE}")
    logger.info(f"Report: {REPORT_FILE}")

    # Per-section summary
    logger.info("\nPer-section breakdown:")
    for s in sections:
        logger.info(f"  {s['section_id']}: {s['word_count']}w, {s['citation_count']} cites — {s['title'][:50]}")

    # Compare with TEST_090
    logger.info("\nComparison with TEST_090:")
    logger.info(f"  TEST_090: {data['quality_metrics']['total_words']}w, "
                f"{sum(s.get('citation_count', len(re.findall(r'\\[\\d+\\]', s.get('content','')))) for s in data['sections'])} total cites, "
                f"30 unique sources")
    logger.info(f"  WIKI_PROOF: {total_words}w, {total_cites} total cites, {len(unique_bib)} unique sources")

    zero_cite_sections = sum(1 for s in sections if s["citation_count"] == 0)
    logger.info(f"  TEST_090 zero-cite sections: 3")
    logger.info(f"  WIKI_PROOF zero-cite sections: {zero_cite_sections}")

    logger.info(f"\nNext: Run G-Eval → python -u scripts/eval_geval.py {OUTPUT_FILE}")

    return output


if __name__ == "__main__":
    asyncio.run(run_proof())
