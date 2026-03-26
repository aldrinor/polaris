"""
Micro test suite: Edge cases for citation format robustness.
Tests: real hash IDs, 10+ evidence, revision pass, key findings,
       expansion, mixed tiers, table generation.

Run: python -u scripts/pg_micro_test_edge.py
"""
import asyncio
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

QUERY = (
    "What are the proven health benefits and risks of intermittent "
    "fasting based on clinical research and meta-analyses?"
)

# Real-style evidence with hash IDs (matching pipeline format)
EVIDENCE_LARGE = [
    {"evidence_id": "ev_eff465049a4c1c62", "statement": "Intermittent fasting significantly reduced fasting blood sugar with SMD of -0.51 (95% CI: -0.81, -0.20; p=0.001).", "quote": "intermittent fasting significantly reduced fasting blood sugar with a standard mean difference of -0.51", "source_url": "https://pubmed.ncbi.nlm.nih.gov/38001", "source_title": "Meta-analysis of IF on glycemic control (2024)", "tier": "GOLD", "verified": True},
    {"evidence_id": "ev_9edaab09c9102777", "statement": "Time-restricted eating reduced fasting glucose by -0.74 mmol/L (95% CI: -1.13 to -0.36).", "quote": "time-restricted eating significantly reduced fasting glucose with a mean difference of negative 0.74 mmol/L", "source_url": "https://pubmed.ncbi.nlm.nih.gov/37002", "source_title": "Systematic review of TRE metabolic markers (2023)", "tier": "GOLD", "verified": True},
    {"evidence_id": "ev_a53d3f36f849f834", "statement": "IF with eating window under 8 hours linked to 135% higher heart disease death risk.", "quote": "intermittent fasting with an eating window under 8 hours was linked to a 135% higher heart disease death risk", "source_url": "https://newsroom.heart.org/2024/03", "source_title": "AHA epidemiological study on TRE and mortality (2024)", "tier": "SILVER", "verified": True},
    {"evidence_id": "ev_2837197afe21984f", "statement": "Fasting insulin reduced by -7.46 pmol/L in fasting-based strategies.", "quote": "fasting-based strategies improved insulin sensitivity with significant fasting insulin reduction of negative 7.46 pmol/L", "source_url": "https://pubmed.ncbi.nlm.nih.gov/36003", "source_title": "Insulin sensitivity meta-analysis (2023)", "tier": "GOLD", "verified": True},
    {"evidence_id": "ev_1431ee89275c1a88", "statement": "HbA1c decreased by 0.12% between baseline and 3 months with TRE vs 0.02% in controls.", "quote": "HbA1c decreased by 0.12 percent between baseline and 3 months with time-restricted eating while controls saw a decrease of only 0.02 percent", "source_url": "https://pubmed.ncbi.nlm.nih.gov/39004", "source_title": "RCT of TRE on glycated hemoglobin (2024)", "tier": "GOLD", "verified": True},
    {"evidence_id": "ev_48d9f006d5799c6e", "statement": "Adults restricting eating to 8-hour period had 91% increase in cardiovascular mortality risk.", "quote": "restricting eating to an 8-hour period was associated with a 91 percent increase in cardiovascular mortality risk", "source_url": "https://newsroom.heart.org/2024/03b", "source_title": "NHANES longitudinal analysis (2024)", "tier": "SILVER", "verified": False},
    {"evidence_id": "ev_bdbbcfde60e0f68a", "statement": "Short-term IF produced systolic blood pressure drop of 9.67 +/- 1 mmHg in adult RCTs.", "quote": "individuals who did short-term intermittent fasting had a drop in systolic blood pressure by 9.67 plus or minus 1 mmHg", "source_url": "https://pubmed.ncbi.nlm.nih.gov/38005", "source_title": "BP meta-analysis of IF RCTs (2024)", "tier": "GOLD", "verified": True},
    {"evidence_id": "ev_06f41310999ecc74", "statement": "4:3 IF showed 2.89 kg greater weight loss than daily caloric restriction at 12 months.", "quote": "4 to 3 intermittent fasting showed 2.89 kg greater weight loss than daily caloric restriction at 12 months", "source_url": "https://pubmed.ncbi.nlm.nih.gov/37006", "source_title": "Long-term IF vs CR comparison trial (2023)", "tier": "GOLD", "verified": True},
    {"evidence_id": "ev_6af0d81f7a07fa80", "statement": "Weight loss difference between IF and continuous restriction was -0.61 kg (95% CI: -1.70 to 0.47), statistically equivalent.", "quote": "weight loss difference between intermittent and continuous restriction was negative 0.61 kg with a 95 percent confidence interval from negative 1.70 to 0.47", "source_url": "https://pubmed.ncbi.nlm.nih.gov/36007", "source_title": "Cochrane review of IF for weight management (2023)", "tier": "GOLD", "verified": True},
    {"evidence_id": "ev_cc1234567890abcd", "statement": "Daily IF helps people lose weight equivalent to about 250 calories a day or half a pound a week.", "quote": "daily intermittent fasting helps people lose weight equivalent to about 250 calories a day or half a pound a week", "source_url": "https://health.usnews.com/if-weight", "source_title": "US News Health overview of IF caloric impact", "tier": "BRONZE", "verified": False},
    {"evidence_id": "ev_dd0987654321fedc", "statement": "An umbrella review of 11 meta-analyses identified 104 unique outcomes, only 6 statistically significant with moderate-to-high evidence.", "quote": "an umbrella review encompassing 11 meta-analyses of randomized clinical trials identified 104 unique outcomes associated with intermittent fasting", "source_url": "https://pubmed.ncbi.nlm.nih.gov/39008", "source_title": "Umbrella review of IF and obesity outcomes (2024)", "tier": "GOLD", "verified": True},
]


def format_evidence(evidence: list[dict]) -> str:
    lines = []
    for e in evidence:
        tier = e.get("tier", "BRONZE")
        verified = "[VERIFIED]" if e.get("verified") else "[UNVERIFIED]"
        lines.append(
            f"Evidence ID: {e['evidence_id']}\n"
            f"  Tier: {tier} {verified}\n"
            f"  Statement: {e['statement']}\n"
            f"  Quote: \"{e['quote']}\"\n"
            f"  Source: {e['source_title']}\n"
            f"  URL: {e['source_url']}\n"
        )
    return "\n".join(lines)


def analyze_citations(content: str, evidence: list[dict]) -> dict:
    """Analyze citation format, accuracy, and coverage."""
    cite_matches = re.findall(r"\[CITE:(ev_[a-f0-9_]+)\]", content)
    src_matches = re.findall(r"\[SRC-\d+\]", content)
    bracket_matches = re.findall(r"\[(\d+)\]", content)

    valid_ids = {e["evidence_id"] for e in evidence}
    cited_ids = set(cite_matches)
    hallucinated = cited_ids - valid_ids
    coverage = len(cited_ids & valid_ids) / len(valid_ids) if valid_ids else 0

    return {
        "cite_count": len(cite_matches),
        "src_count": len(src_matches),
        "bracket_count": len(bracket_matches),
        "unique_cited": len(cited_ids),
        "valid_cited": len(cited_ids & valid_ids),
        "hallucinated_ids": hallucinated,
        "coverage": coverage,
        "word_count": len(content.split()),
        "format_ok": len(cite_matches) > 0 and len(src_matches) == 0,
    }


async def run_tests():
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient
    from src.polaris_graph.retrieval.synthesis_prompts import build_section_writer_prompt
    from src.polaris_graph.synthesis.section_writer import SECTION_SYSTEM_PROMPT

    client = OpenRouterClient()
    results = {}

    # ===================================================================
    # TEST A: 11 evidence pieces with real hash IDs (analytical prompt)
    # ===================================================================
    print("=" * 70)
    print("TEST A: 11 evidence, real hash IDs, analytical prompt")
    print("=" * 70)

    evidence_text = format_evidence(EVIDENCE_LARGE)
    system = build_section_writer_prompt(
        n_evidence=len(EVIDENCE_LARGE),
        suggested_words=min(200 + len(EVIDENCE_LARGE) * 80, 2000),
    )
    prompt = (
        f"SECTION TITLE: Metabolic Benefits versus Cardiovascular Risk\n"
        f"RESEARCH QUESTION: {QUERY}\n\n"
        f"EVIDENCE:\n{evidence_text}\n\n"
        f"Write this section. Every factual claim MUST include a "
        f"[CITE:evidence_id] marker referencing the specific evidence piece."
    )

    r = await client.generate(prompt=prompt, system=system, max_tokens=3000, temperature=0.4)
    stats = analyze_citations(r.content, EVIDENCE_LARGE)
    results["A"] = stats

    print(f"\n{r.content[:1000]}...")
    print(f"\n--- Stats: CITE={stats['cite_count']}, SRC={stats['src_count']}, "
          f"coverage={stats['coverage']:.0%}, hallucinated={stats['hallucinated_ids']}, "
          f"words={stats['word_count']}")
    print(f"--- PASS: {stats['format_ok']}")

    # ===================================================================
    # TEST B: Revision/rewrite (simulate citation density failure)
    # ===================================================================
    print("\n" + "=" * 70)
    print("TEST B: Citation density revision (rewrite undercited prose)")
    print("=" * 70)

    # Simulate a section with NO citations that needs rewriting
    undercited_content = (
        "Intermittent fasting has been shown to reduce blood sugar levels. "
        "Time-restricted eating protocols also demonstrate glucose improvements. "
        "However, epidemiological data raises concerns about cardiovascular mortality "
        "in individuals with very short eating windows. The contradiction between "
        "metabolic benefits and mortality risk remains unresolved."
    )
    revision_prompt = (
        f"The following section has too few citations (0 citations in "
        f"{len(undercited_content.split())} words). "
        f"Rewrite it so that EVERY factual claim has a [CITE:evidence_id] marker. "
        f"Target at least 1 citation per 2 sentences. Keep the same content and length.\n\n"
        f"SECTION:\n{undercited_content}\n\n"
        f"AVAILABLE EVIDENCE:\n{format_evidence(EVIDENCE_LARGE[:5])}"
    )
    r2 = await client.generate(prompt=revision_prompt, system=system, max_tokens=2000, temperature=0.4)
    stats2 = analyze_citations(r2.content, EVIDENCE_LARGE[:5])
    results["B"] = stats2

    print(f"\n{r2.content[:800]}...")
    print(f"\n--- Stats: CITE={stats2['cite_count']}, SRC={stats2['src_count']}, "
          f"hallucinated={stats2['hallucinated_ids']}")
    print(f"--- PASS: {stats2['format_ok']}")

    # ===================================================================
    # TEST C: Key Findings generation (separate call)
    # ===================================================================
    print("\n" + "=" * 70)
    print("TEST C: Key Findings bullet generation")
    print("=" * 70)

    kf_prompt = (
        f"Based on this section content, write a **Key Findings** subsection "
        f"with 3-5 bullet points. Each bullet MUST include a [CITE:evidence_id] "
        f"marker from the evidence used in this section.\n\n"
        f"SECTION CONTENT:\n{r.content[:2000]}\n\n"
        f"Output ONLY the Key Findings block in this exact format:\n"
        f"**Key Findings:**\n"
        f"- Finding 1 [CITE:ev_xxx]\n"
        f"- Finding 2 [CITE:ev_yyy]\n"
        f"- Finding 3 [CITE:ev_zzz]"
    )
    r3 = await client.generate(prompt=kf_prompt, system=system, max_tokens=1000, temperature=0.3)
    stats3 = analyze_citations(r3.content, EVIDENCE_LARGE)
    results["C"] = stats3

    print(f"\n{r3.content}")
    print(f"\n--- Stats: CITE={stats3['cite_count']}, SRC={stats3['src_count']}, "
          f"hallucinated={stats3['hallucinated_ids']}")
    print(f"--- PASS: {stats3['format_ok']}")

    # ===================================================================
    # TEST D: Expansion (add words to existing section)
    # ===================================================================
    print("\n" + "=" * 70)
    print("TEST D: Section expansion (add 200 words)")
    print("=" * 70)

    expand_evidence = EVIDENCE_LARGE[5:9]  # 4 unused evidence
    expand_prompt = (
        f"EXISTING SECTION CONTENT:\n{r.content[:1500]}\n\n"
        f"NEW EVIDENCE TO INCORPORATE:\n{format_evidence(expand_evidence)}\n\n"
        f"TASK: Write 200 additional words to ADD to the end of the existing content above.\n"
        f"Do NOT repeat or rewrite any existing content. Only write NEW paragraphs.\n"
        f"Every factual claim MUST include a [CITE:evidence_id] marker.\n"
        f"Use transition phrases to connect smoothly to the existing content."
    )
    r4 = await client.generate(prompt=expand_prompt, system=system, max_tokens=1500, temperature=0.4)
    stats4 = analyze_citations(r4.content, expand_evidence)
    results["D"] = stats4

    print(f"\n{r4.content[:800]}...")
    print(f"\n--- Stats: CITE={stats4['cite_count']}, SRC={stats4['src_count']}, "
          f"hallucinated={stats4['hallucinated_ids']}")
    print(f"--- PASS: {stats4['format_ok']}")

    # ===================================================================
    # TEST E: SECTION_SYSTEM_PROMPT (v1 fallback path)
    # ===================================================================
    print("\n" + "=" * 70)
    print("TEST E: v1 SECTION_SYSTEM_PROMPT path (fallback)")
    print("=" * 70)

    system_v1 = SECTION_SYSTEM_PROMPT.format(
        n_evidence=len(EVIDENCE_LARGE),
        suggested_words=1200,
    )
    prompt_v1 = (
        f"SECTION TITLE: Weight Management Outcomes\n"
        f"RESEARCH QUESTION: {QUERY}\n\n"
        f"EVIDENCE:\n{format_evidence(EVIDENCE_LARGE[5:])}\n\n"
        f"Write this section. Every factual claim MUST include a "
        f"[CITE:evidence_id] marker referencing the specific evidence piece."
    )
    r5 = await client.generate(prompt=prompt_v1, system=system_v1, max_tokens=2000, temperature=0.4)
    stats5 = analyze_citations(r5.content, EVIDENCE_LARGE[5:])
    results["E"] = stats5

    print(f"\n{r5.content[:800]}...")
    print(f"\n--- Stats: CITE={stats5['cite_count']}, SRC={stats5['src_count']}, "
          f"hallucinated={stats5['hallucinated_ids']}")
    print(f"--- PASS: {stats5['format_ok']}")

    # ===================================================================
    # SUMMARY
    # ===================================================================
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    all_pass = True
    for name, s in results.items():
        passed = s["format_ok"]
        if not passed:
            all_pass = False
        print(
            f"  Test {name}: CITE={s['cite_count']:>3}, SRC={s['src_count']:>2}, "
            f"[N]={s['bracket_count']:>2}, coverage={s['coverage']:>5.0%}, "
            f"halluc={len(s['hallucinated_ids'])}, words={s['word_count']:>4}  "
            f"{'PASS' if passed else 'FAIL'}"
        )

    print(f"\n  ALL PASS: {all_pass}")


if __name__ == "__main__":
    asyncio.run(run_tests())
