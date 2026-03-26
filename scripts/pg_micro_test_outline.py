"""
Micro test: Clustering + Outline generation with 11 evidence pieces.
Tests whether ClusterPlan and ReportOutline succeed or timeout/fallback.

Run: python -u scripts/pg_micro_test_outline.py
"""
import asyncio
import os
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

QUERY = (
    "What are the proven health benefits and risks of intermittent "
    "fasting based on clinical research and meta-analyses?"
)

# Same 11 evidence from edge test
EVIDENCE = [
    {"evidence_id": "ev_eff465049a4c1c62", "statement": "Intermittent fasting significantly reduced fasting blood sugar with SMD of -0.51 (95% CI: -0.81, -0.20; p=0.001).", "source_title": "Meta-analysis of IF on glycemic control (2024)", "tier": "GOLD", "fact_category": "finding", "relevance": 0.92},
    {"evidence_id": "ev_9edaab09c9102777", "statement": "Time-restricted eating reduced fasting glucose by -0.74 mmol/L (95% CI: -1.13 to -0.36).", "source_title": "Systematic review of TRE metabolic markers (2023)", "tier": "GOLD", "fact_category": "finding", "relevance": 0.88},
    {"evidence_id": "ev_a53d3f36f849f834", "statement": "IF with eating window under 8 hours linked to 135% higher heart disease death risk.", "source_title": "AHA epidemiological study on TRE and mortality (2024)", "tier": "SILVER", "fact_category": "risk", "relevance": 0.85},
    {"evidence_id": "ev_2837197afe21984f", "statement": "Fasting insulin reduced by -7.46 pmol/L in fasting-based strategies.", "source_title": "Insulin sensitivity meta-analysis (2023)", "tier": "GOLD", "fact_category": "finding", "relevance": 0.90},
    {"evidence_id": "ev_1431ee89275c1a88", "statement": "HbA1c decreased by 0.12% between baseline and 3 months with TRE vs 0.02% in controls.", "source_title": "RCT of TRE on glycated hemoglobin (2024)", "tier": "GOLD", "fact_category": "statistic", "relevance": 0.87},
    {"evidence_id": "ev_48d9f006d5799c6e", "statement": "Adults restricting eating to 8-hour period had 91% increase in cardiovascular mortality risk.", "source_title": "NHANES longitudinal analysis (2024)", "tier": "SILVER", "fact_category": "risk", "relevance": 0.83},
    {"evidence_id": "ev_bdbbcfde60e0f68a", "statement": "Short-term IF produced systolic blood pressure drop of 9.67 +/- 1 mmHg in adult RCTs.", "source_title": "BP meta-analysis of IF RCTs (2024)", "tier": "GOLD", "fact_category": "finding", "relevance": 0.86},
    {"evidence_id": "ev_06f41310999ecc74", "statement": "4:3 IF showed 2.89 kg greater weight loss than daily caloric restriction at 12 months.", "source_title": "Long-term IF vs CR comparison trial (2023)", "tier": "GOLD", "fact_category": "statistic", "relevance": 0.88},
    {"evidence_id": "ev_6af0d81f7a07fa80", "statement": "Weight loss difference between IF and continuous restriction was -0.61 kg (95% CI: -1.70 to 0.47), statistically equivalent.", "source_title": "Cochrane review of IF for weight management (2023)", "tier": "GOLD", "fact_category": "conclusion", "relevance": 0.85},
    {"evidence_id": "ev_cc1234567890abcd", "statement": "Daily IF helps people lose weight equivalent to about 250 calories a day or half a pound a week.", "source_title": "US News Health overview of IF caloric impact", "tier": "BRONZE", "fact_category": "description", "relevance": 0.60},
    {"evidence_id": "ev_dd0987654321fedc", "statement": "An umbrella review of 11 meta-analyses identified 104 unique outcomes, only 6 statistically significant with moderate-to-high evidence.", "source_title": "Umbrella review of IF and obesity outcomes (2024)", "tier": "GOLD", "fact_category": "methodology", "relevance": 0.91},
]


async def test_clustering():
    """Test LLM clustering with 11 evidence pieces."""
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient
    from src.polaris_graph.schemas import ClusterPlan

    client = OpenRouterClient()

    # Build evidence text for clustering (matching synthesizer format)
    ev_lines = []
    for i, e in enumerate(EVIDENCE):
        ev_lines.append(
            f"{i+1}. ({e['tier']}, rel={e['relevance']:.2f}) "
            f"{e['statement'][:200]}"
        )
    evidence_text = "\n".join(ev_lines)

    cluster_prompt = (
        f"You are clustering evidence for a research report.\n"
        f"RESEARCH QUESTION: {QUERY}\n\n"
        f"EVIDENCE ({len(EVIDENCE)} pieces):\n{evidence_text}\n\n"
        f"TASK: Group these {len(EVIDENCE)} evidence pieces into 4-8 thematic clusters.\n"
        f"Each cluster should map to a report section with a descriptive title.\n"
        f"Every evidence piece must be assigned to exactly one cluster.\n"
        f"Use evidence numbers (1-{len(EVIDENCE)}) as IDs.\n\n"
        f"Return valid JSON only."
    )

    print("=" * 70)
    print("TEST F: LLM Clustering (ClusterPlan schema)")
    print("=" * 70)

    t0 = time.time()
    try:
        result = await client.generate_structured(
            prompt=cluster_prompt,
            schema=ClusterPlan,
            max_tokens=4096,
            timeout=120,
        )
        elapsed = time.time() - t0
        print(f"\nClustering succeeded in {elapsed:.1f}s")

        clusters = result.clusters if hasattr(result, 'clusters') else []
        print(f"Clusters: {len(clusters)}")
        total_assigned = 0
        for c in clusters:
            theme = getattr(c, 'theme', getattr(c, 'label', '?'))
            eids = getattr(c, 'evidence_ids', [])
            total_assigned += len(eids)
            print(f"  - {theme}: {len(eids)} evidence")
        print(f"Total assigned: {total_assigned}/{len(EVIDENCE)}")
        cluster_pass = len(clusters) >= 3 and total_assigned >= len(EVIDENCE) * 0.8
        print(f"PASS: {cluster_pass}")

    except Exception as exc:
        elapsed = time.time() - t0
        print(f"\nClustering FAILED in {elapsed:.1f}s: {exc}")
        cluster_pass = False

    # ===================================================================
    # TEST G: Outline from clusters (or STORM outline)
    # ===================================================================
    print("\n" + "=" * 70)
    print("TEST G: Outline Generation (ReportOutline schema)")
    print("=" * 70)

    from src.polaris_graph.schemas import ReportOutline

    outline_prompt = (
        f"You are a research outline architect.\n"
        f"RESEARCH QUESTION: {QUERY}\n\n"
        f"Create a report outline with 6-10 sections that comprehensively addresses "
        f"this research question. Each section should have:\n"
        f"- A descriptive, specific title (NOT generic like 'Findings' or 'Discussion')\n"
        f"- A 1-2 sentence description of what the section covers\n"
        f"- Logical ordering from background → evidence → analysis → implications\n\n"
        f"AVAILABLE EVIDENCE THEMES:\n"
        f"1. Glycemic control improvements (blood sugar, insulin, HbA1c)\n"
        f"2. Cardiovascular risks (mortality, blood pressure)\n"
        f"3. Weight management comparisons (IF vs calorie restriction)\n"
        f"4. Evidence quality assessment (umbrella reviews, meta-analyses)\n"
        f"5. Behavioral mechanisms (caloric reduction, eating windows)\n\n"
        f"Return valid JSON only."
    )

    t0 = time.time()
    try:
        outline = await client.generate_structured(
            prompt=outline_prompt,
            schema=ReportOutline,
            max_tokens=4096,
            timeout=120,
        )
        elapsed = time.time() - t0
        print(f"\nOutline succeeded in {elapsed:.1f}s")

        sections = outline.sections if hasattr(outline, 'sections') else []
        print(f"Sections: {len(sections)}")
        for s in sections:
            title = getattr(s, 'title', '?')
            desc = getattr(s, 'description', '')[:60]
            print(f"  {getattr(s, 'order', '?')}. {title}")
            if desc:
                print(f"     {desc}")

        # Check for generic/garbage titles
        generic_words = {"finding", "evidence", "discussion", "analysis", "results", "data", "section"}
        bad_titles = [
            s for s in sections
            if getattr(s, 'title', '').lower().split(':')[0].strip().rstrip('s') in generic_words
            or "Evidence categorized" in getattr(s, 'title', '')
        ]
        outline_pass = len(sections) >= 5 and len(bad_titles) == 0
        print(f"\nGeneric/garbage titles: {len(bad_titles)}")
        print(f"PASS: {outline_pass}")

    except Exception as exc:
        elapsed = time.time() - t0
        print(f"\nOutline FAILED in {elapsed:.1f}s: {exc}")
        outline_pass = False

    # ===================================================================
    # SUMMARY
    # ===================================================================
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Test F (Clustering): {'PASS' if cluster_pass else 'FAIL'}")
    print(f"  Test G (Outline):    {'PASS' if outline_pass else 'FAIL'}")
    print(f"  ALL PASS: {cluster_pass and outline_pass}")


if __name__ == "__main__":
    asyncio.run(test_clustering())
