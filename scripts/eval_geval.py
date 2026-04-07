"""G-Eval style LLM-as-Judge evaluation for research reports.

Uses per-section evaluation to avoid truncation bias.
Industrial-grade: based on DeepEval G-Eval + RAGAS + FActScore patterns.
"""

import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Max chars per LLM eval call (GLM-5 has 1M context but we keep it reasonable)
MAX_EVAL_CHARS = 30000


async def _eval_one(client, dim_name: str, prompt: str, system: str, weight: float) -> dict:
    """Run one evaluation dimension."""
    try:
        response = await asyncio.wait_for(
            client.generate(
                prompt=prompt,
                system=system,
                max_tokens=1024,
                temperature=0.3,
            ),
            timeout=180,
        )
        text = response.content.strip()
        score_match = re.search(r'SCORE:\s*(\d+)', text)
        score = int(score_match.group(1)) if score_match else 5
        reason_match = re.search(r'REASONING:\s*(.+?)(?=ISSUES:|$)', text, re.DOTALL)
        reasoning = reason_match.group(1).strip() if reason_match else text[:300]
        issues_match = re.search(r'ISSUES:\s*(.+?)$', text, re.DOTALL)
        issues = issues_match.group(1).strip() if issues_match else ""
        return {
            "score": score, "weight": weight,
            "weighted": round(score * weight, 2),
            "reasoning": reasoning[:400], "issues": issues[:400],
        }
    except Exception as exc:
        logger.error(f"  {dim_name}: FAILED - {str(exc)[:100]}")
        return {"score": 0, "weight": weight, "weighted": 0, "error": str(exc)[:200]}


async def evaluate_report(report_path: str):
    """Run G-Eval on a research report — per-section to avoid truncation."""
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient

    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    report_text = data.get("final_report", "")
    sections = data.get("sections", data.get("report_sections", []))
    bibliography = data.get("bibliography", [])

    if not report_text:
        logger.error("No final_report in JSON")
        return

    client = OpenRouterClient()
    results = {}
    total_weighted = 0.0
    system = "You are an expert research report evaluator. Be critical and specific. Do not inflate scores."

    # ================================================================
    # 1. FAITHFULNESS — evaluate per-section, average scores
    # ================================================================
    logger.info("Evaluating FAITHFULNESS (per-section)...")
    faith_scores = []
    for i, sec in enumerate(sections):
        title = sec.get("title", "")
        content = sec.get("content", "")[:8000]
        if len(content.split()) < 50:
            continue
        prompt = f"""Evaluate FAITHFULNESS of this research report section.

For each factual claim, check: is it supported by a citation [N]?
Are numbers and effect sizes accurately attributed?

Score 1-10:
- 10: Every claim cited, numbers match
- 7-9: Most claims cited, minor gaps
- 4-6: Multiple uncited factual claims
- 1-3: Widespread unsupported claims

SECTION "{title}":
{content}

Output: SCORE: [1-10]
REASONING: [2-3 sentences]
ISSUES: [Specific uncited claims, or "None found"]"""
        r = await _eval_one(client, f"faith_{i}", prompt, system, 0.20)
        faith_scores.append(r["score"])
        logger.info(f"  Section {i+1} '{title[:40]}': {r['score']}/10")

    avg_faith = sum(faith_scores) / max(len(faith_scores), 1)
    results["faithfulness"] = {
        "score": round(avg_faith), "weight": 0.20,
        "weighted": round(avg_faith * 0.20, 2),
        "reasoning": f"Average across {len(faith_scores)} sections: {avg_faith:.1f}/10",
        "per_section": faith_scores,
    }
    total_weighted += avg_faith * 0.20
    logger.info(f"  FAITHFULNESS average: {avg_faith:.1f}/10")

    # ================================================================
    # 2. COHERENCE — section openings/closings + transitions
    # ================================================================
    logger.info("\nEvaluating COHERENCE...")
    structure = []
    for i, sec in enumerate(sections):
        content = sec.get("content", "")
        sents = re.split(r'(?<=[.!?])\s+', content)
        first = sents[0][:250] if sents else ""
        last = sents[-1][:250] if len(sents) > 1 else ""
        structure.append(
            f"Section {i+1}: {sec.get('title','')}\n"
            f"  Words: {len(content.split())}\n"
            f"  Opening: {first}\n"
            f"  Closing: {last}"
        )
    prompt = f"""Evaluate COHERENCE of this research report structure.

Check: logical flow between sections, transition sentences, narrative arc,
cross-references, no abrupt topic jumps.

Score 1-10:
- 10: Perfect flow, smooth transitions
- 7-9: Good flow, minor gaps
- 4-6: Fragmented, weak transitions
- 1-3: Incoherent

REPORT STRUCTURE ({len(sections)} sections):
{chr(10).join(structure)}

Output: SCORE: [1-10]
REASONING: [2-3 sentences]
ISSUES: [Specific flow problems, or "None found"]"""
    r = await _eval_one(client, "coherence", prompt, system, 0.15)
    results["coherence"] = r
    total_weighted += r["weighted"]
    logger.info(f"  COHERENCE: {r['score']}/10")

    # ================================================================
    # 3. ANALYTICAL DEPTH — sample 3 sections (largest ones)
    # ================================================================
    logger.info("\nEvaluating ANALYTICAL DEPTH...")
    sorted_secs = sorted(sections, key=lambda s: len(s.get("content", "")), reverse=True)
    sample_text = "\n\n---\n\n".join(
        f"## {s.get('title','')}\n{s.get('content','')[:5000]}"
        for s in sorted_secs[:3]
    )
    prompt = f"""Evaluate ANALYTICAL DEPTH of this research report (3 largest sections shown).

A deep report: COMPARES studies, EXPLAINS mechanisms, IDENTIFIES contradictions,
CONTEXTUALIZES with clinical significance, uses GRADE ratings with CIs.

Score 1-10:
- 10: Deep synthesis with comparisons, mechanisms, contradictions, GRADE
- 7-9: Good analysis, most elements present
- 4-6: Mostly descriptive
- 1-3: Pure listing

REPORT SAMPLE:
{sample_text[:MAX_EVAL_CHARS]}

Output: SCORE: [1-10]
REASONING: [2-3 sentences]
ISSUES: [Where analysis is shallow, or "None found"]"""
    r = await _eval_one(client, "analytical_depth", prompt, system, 0.20)
    results["analytical_depth"] = r
    total_weighted += r["weighted"]
    logger.info(f"  ANALYTICAL DEPTH: {r['score']}/10")

    # ================================================================
    # 4. CITATION QUALITY — full bibliography + per-section cite counts
    # ================================================================
    logger.info("\nEvaluating CITATION QUALITY...")
    cite_summary = []
    for i, sec in enumerate(sections):
        content = sec.get("content", "")
        n_cites = len(re.findall(r'\[\d+\]', content))
        n_words = len(content.split())
        cite_summary.append(f"  Section {i+1} '{sec.get('title','')[:40]}': {n_words}w, {n_cites} citations")

    bib_text = "\n".join(
        f"  [{b.get('citation_number', i+1)}] {b.get('title', b.get('formatted','')[:100])}"
        f" | {b.get('url','')[:60]}"
        for i, b in enumerate(bibliography[:25])
    )

    prompt = f"""Evaluate CITATION QUALITY of this research report.

Check: citation diversity, placement, bibliography completeness,
uncited claims, balance across sections.

CITATION DISTRIBUTION:
{chr(10).join(cite_summary)}

BIBLIOGRAPHY ({len(bibliography)} entries):
{bib_text}

Score 1-10:
- 10: Diverse, well-placed, complete bibliography, balanced
- 7-9: Good with minor gaps
- 4-6: Clustering, missing citations, poor bibliography
- 1-3: Sparse or absent

Output: SCORE: [1-10]
REASONING: [2-3 sentences]
ISSUES: [Specific problems, or "None found"]"""
    r = await _eval_one(client, "citation_quality", prompt, system, 0.15)
    results["citation_quality"] = r
    total_weighted += r["weighted"]
    logger.info(f"  CITATION QUALITY: {r['score']}/10")

    # ================================================================
    # 5. COMPLETENESS — section titles + topic checklist
    # ================================================================
    logger.info("\nEvaluating COMPLETENESS...")
    section_list = "\n".join(
        f"  {i+1}. {s.get('title','')} ({len(s.get('content','').split())} words)"
        for i, s in enumerate(sections)
    )
    # Sample from later sections (which truncation missed before)
    later_sample = "\n".join(
        s.get("content", "")[:2000]
        for s in sections[len(sections)//2:]
    )
    prompt = f"""Evaluate COMPLETENESS of this report on "health benefits and risks of intermittent fasting."

Required topics: IF protocols (TRE, ADF, 5:2), weight loss with effect sizes,
metabolic/cardiovascular outcomes, safety/adverse effects, contraindications,
methodological limitations, mechanisms (autophagy, insulin), comparison to calorie restriction.

REPORT SECTIONS:
{section_list}

SAMPLE FROM LATER SECTIONS:
{later_sample[:10000]}

Score 1-10:
- 10: All major topics covered
- 7-9: Most covered, minor gaps
- 4-6: Several important topics missing
- 1-3: Major gaps

Output: SCORE: [1-10]
REASONING: [2-3 sentences]
ISSUES: [Missing topics, or "None found"]"""
    r = await _eval_one(client, "completeness", prompt, system, 0.15)
    results["completeness"] = r
    total_weighted += r["weighted"]
    logger.info(f"  COMPLETENESS: {r['score']}/10")

    # ================================================================
    # 6. WRITING QUALITY — sample from multiple sections
    # ================================================================
    logger.info("\nEvaluating WRITING QUALITY...")
    # Take 1000 words from section 1, 3, and last
    samples = []
    for idx in [0, min(2, len(sections)-1), len(sections)-1]:
        if idx < len(sections):
            c = sections[idx].get("content", "")
            samples.append(c[:3000])
    writing_sample = "\n\n---\n\n".join(samples)

    prompt = f"""Evaluate WRITING QUALITY of this research report.

Check: academic register, grammar (subject-verb agreement, modals),
no AI artifacts, appropriate hedging, clear language, effective tables.

Score 1-10:
- 10: Publication-ready
- 7-9: Strong with minor issues
- 4-6: Noticeable errors
- 1-3: Poor writing

REPORT SAMPLES (from sections 1, 3, and last):
{writing_sample[:MAX_EVAL_CHARS]}

Output: SCORE: [1-10]
REASONING: [2-3 sentences]
ISSUES: [Specific problems, or "None found"]"""
    r = await _eval_one(client, "writing_quality", prompt, system, 0.15)
    results["writing_quality"] = r
    total_weighted += r["weighted"]
    logger.info(f"  WRITING QUALITY: {r['score']}/10")

    # ================================================================
    # TOTAL
    # ================================================================
    total = round(total_weighted * 10, 1)
    logger.info(f"\n{'='*60}")
    logger.info(f"  G-EVAL TOTAL: {total}/100")
    logger.info(f"{'='*60}")

    output_path = report_path.replace(".json", "_geval.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"total": total, "dimensions": results}, f, indent=2)
    logger.info(f"  Saved to: {output_path}")

    return total, results


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "outputs/polaris_graph/PG_TEST_089.json"
    asyncio.run(evaluate_report(path))
