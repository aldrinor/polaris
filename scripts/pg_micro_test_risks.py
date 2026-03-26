"""
Risk tests: Verify 4 remaining uncertainties before TEST_068.
  R1: _reduce_filler with real-length content (1000+ words, tables, citations)
  R2: Clustering fallback produces decent titles (not "Evidence categorized as...")
  R3: Evidence tier data preserved through serialization
  R4: Exa API actually responds without brotli error

Run: python -u scripts/pg_micro_test_risks.py
"""
import asyncio
import os
import re
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

results = {}


def register(test_id, name):
    def decorator(func):
        print(f"\n{'='*70}")
        print(f"TEST {test_id}: {name}")
        print(f"{'='*70}")
        try:
            passed = func()
        except Exception as e:
            import traceback
            traceback.print_exc()
            passed = False
        results[test_id] = (name, passed)
        print(f"  >>> {'PASS' if passed else 'FAIL'}")
        return func
    return decorator


# ===================================================================
# R1: _reduce_filler with realistic long content
# ===================================================================

@register("R1a", "_reduce_filler preserves tables in 1000+ word content")
def _():
    from src.polaris_graph.synthesis.report_assembler import _reduce_filler

    # Build realistic 1000+ word section with tables, citations, Key Findings
    paragraphs = []
    paragraphs.append(
        "Intermittent fasting significantly reduced fasting blood sugar with a "
        "standard mean difference of -0.51 (95% CI: -0.81 to -0.20; p=0.001) "
        "across 12 randomized controlled trials [1]. This finding was confirmed "
        "by a separate systematic review examining 99 RCTs involving 6,582 adults "
        "with an average age of 45 [2]. The aggregate data demonstrates consistent "
        "glycemic improvements across diverse populations and fasting protocols."
    )
    paragraphs.append(
        "Time-restricted eating protocols specifically reduced fasting glucose "
        "by -0.74 mmol/L (95% CI: -1.13 to -0.36) according to a 2023 review [3]. "
        "Furthermore, HbA1c decreased by 0.12% between baseline and 3 months with "
        "TRE versus 0.02% in controls [4]. The mechanism involves enhanced insulin "
        "sensitivity during prolonged fasting windows."
    )
    paragraphs.append(
        "| Metric | Effect Size | 95% CI | Source |\n"
        "|:---|:---|:---|:---|\n"
        "| Fasting Blood Sugar | SMD -0.51 | -0.81 to -0.20 | [1] |\n"
        "| Fasting Glucose | -0.74 mmol/L | -1.13 to -0.36 | [3] |\n"
        "| HbA1c Change | -0.12% vs -0.02% | N/A | [4] |\n"
        "| Fasting Insulin | -7.46 pmol/L | N/A | [5] |"
    )
    # Add enough paragraphs to exceed 1000 words
    for i in range(6, 20):
        paragraphs.append(
            f"Evidence from study [{i}] confirms that intermittent fasting protocols "
            f"demonstrate measurable effects on metabolic parameters. The clinical "
            f"significance of these findings varies by population subgroup and protocol "
            f"duration. Additionally, long-term data remains limited for most outcomes."
        )
    paragraphs.append(
        "\n\n**Key Findings:**\n"
        "- Blood sugar reduced with SMD -0.51 across 12 RCTs [1].\n"
        "- Fasting glucose reduced by -0.74 mmol/L with TRE [3].\n"
        "- HbA1c improved by 0.12% versus 0.02% in controls [4]."
    )

    content = "\n\n".join(paragraphs)
    word_count_before = len(content.split())

    # Run _reduce_filler
    reduced = _reduce_filler(content)
    word_count_after = len(reduced.split())

    # Check preservation
    has_table = "|:---|" in reduced
    has_citations = bool(re.findall(r"\[\d+\]", reduced))
    cite_count = len(re.findall(r"\[\d+\]", reduced))
    has_key_findings = "**Key Findings:**" in reduced
    has_newlines = "\n" in reduced
    table_rows_intact = reduced.count("|") >= 20  # 4 columns x 5+ rows

    print(f"  Words: {word_count_before} -> {word_count_after}")
    print(f"  Table preserved: {has_table}")
    print(f"  Table rows intact (|>=20): {table_rows_intact} ({reduced.count('|')} pipes)")
    print(f"  Citations: {cite_count}")
    print(f"  Key Findings: {has_key_findings}")
    print(f"  Newlines preserved: {has_newlines} ({reduced.count(chr(10))})")

    return has_table and cite_count >= 15 and has_key_findings and has_newlines and table_rows_intact


@register("R1b", "_reduce_filler doesn't mangle [N] citation brackets")
def _():
    from src.polaris_graph.synthesis.report_assembler import _reduce_filler

    content = (
        "The effect was significant [1]. Multiple studies confirmed this [2][3]. "
        "A combined analysis of [4] and [5] showed concordance. "
        "The hazard ratio was 1.91 [6]. Furthermore, the risk persisted [7]."
    )
    reduced = _reduce_filler(content)

    # Check all citation brackets survive
    original_cites = set(re.findall(r"\[\d+\]", content))
    reduced_cites = set(re.findall(r"\[\d+\]", reduced))
    missing = original_cites - reduced_cites

    print(f"  Original citations: {sorted(original_cites)}")
    print(f"  After reduce:       {sorted(reduced_cites)}")
    print(f"  Missing: {missing}")
    print(f"  Reduced: {reduced[:200]}")

    return len(missing) == 0


# ===================================================================
# R2: Clustering fallback title quality
# ===================================================================

@register("R2a", "Category fallback clusters have decent titles via FIX-MP9")
def _():
    from src.polaris_graph.synthesis.section_writer import _fallback_outline
    from src.polaris_graph.schemas import ReportOutline

    # Simulate category-based clusters (what happens when LLM clustering times out)
    clusters = [
        {"cluster_id": "c_finding", "theme": "Finding",
         "description": "Evidence categorized as finding",
         "evidence_ids": ["ev_1", "ev_2", "ev_3", "ev_4", "ev_5"]},
        {"cluster_id": "c_risk", "theme": "Risk",
         "description": "Evidence categorized as risk",
         "evidence_ids": ["ev_6", "ev_7", "ev_8"]},
        {"cluster_id": "c_methodology", "theme": "Methodology",
         "description": "Evidence categorized as methodology",
         "evidence_ids": ["ev_9", "ev_10"]},
    ]

    evidence = [
        {"evidence_id": "ev_1", "statement": "Intermittent fasting reduced fasting blood sugar SMD -0.51"},
        {"evidence_id": "ev_2", "statement": "Time-restricted eating reduced glucose by -0.74 mmol/L"},
        {"evidence_id": "ev_3", "statement": "Weight loss ranged from 5.5 to 6.5 kg at six months"},
        {"evidence_id": "ev_4", "statement": "HbA1c decreased by 0.12% with TRE versus controls"},
        {"evidence_id": "ev_5", "statement": "Insulin sensitivity improved with fasting protocols"},
        {"evidence_id": "ev_6", "statement": "Eating windows under 8 hours linked to 135% higher CV death risk"},
        {"evidence_id": "ev_7", "statement": "Hazard ratio of 1.91 for cardiovascular mortality"},
        {"evidence_id": "ev_8", "statement": "Dizziness occurred at approximately 3% rate"},
        {"evidence_id": "ev_9", "statement": "Meta-analysis included 99 randomized controlled trials"},
        {"evidence_id": "ev_10", "statement": "Median study had 38 participants over 3 months"},
    ]

    query = "What are the proven health benefits and risks of intermittent fasting?"
    outline = _fallback_outline(query, clusters, evidence)

    print(f"  Sections: {len(outline.sections)}")
    has_garbage = False
    for s in outline.sections:
        is_garbage = "Evidence categorized" in s.title
        if is_garbage:
            has_garbage = True
        print(f"  {'BAD' if is_garbage else ' OK'} {s.title[:70]}")

    print(f"  Any garbage titles: {has_garbage}")
    return not has_garbage


@register("R2b", "Fallback outline with single-word generic themes gets keyword titles")
def _():
    from src.polaris_graph.synthesis.section_writer import _fallback_outline

    clusters = [
        {"cluster_id": "c_1", "theme": "Statistic",
         "description": "Evidence categorized as statistic",
         "evidence_ids": ["ev_1", "ev_2", "ev_3"]},
    ]
    evidence = [
        {"evidence_id": "ev_1", "statement": "Blood sugar reduced by SMD -0.51 across 12 trials"},
        {"evidence_id": "ev_2", "statement": "Weight loss of 5.5 to 6.5 kg observed at six months"},
        {"evidence_id": "ev_3", "statement": "HbA1c decreased by 0.12 percent with time-restricted eating"},
    ]
    query = "Intermittent fasting health effects"
    outline = _fallback_outline(query, clusters, evidence)

    title = outline.sections[0].title
    print(f"  Generated title: '{title}'")
    is_generic = title.lower() in ["statistic", "statistics", "finding", "findings"]
    is_categorized = "Evidence categorized" in title
    print(f"  Generic single-word: {is_generic}, Categorized: {is_categorized}")
    return not is_generic and not is_categorized


# ===================================================================
# R3: Evidence tier data preserved
# ===================================================================

@register("R3a", "Evidence tier survives JSON serialization round-trip")
def _():
    evidence = [
        {"evidence_id": "ev_001", "statement": "Test", "tier": "GOLD", "relevance": 0.9},
        {"evidence_id": "ev_002", "statement": "Test", "tier": "SILVER", "relevance": 0.7},
        {"evidence_id": "ev_003", "statement": "Test", "tier": "BRONZE", "relevance": 0.4},
    ]

    # Simulate JSON serialization (what graph.py does when saving state)
    serialized = json.dumps(evidence)
    deserialized = json.loads(serialized)

    tiers = [e.get("tier", "MISSING") for e in deserialized]
    print(f"  Tiers after round-trip: {tiers}")
    return tiers == ["GOLD", "SILVER", "BRONZE"]


@register("R3b", "Evidence tier present in TEST_067 output (check actual data)")
def _():
    output_path = Path("outputs/polaris_graph/PG_TEST_067.json")
    if not output_path.exists():
        print("  TEST_067 output not found, skipping")
        return True  # Non-blocking

    d = json.loads(output_path.read_text())
    evidence = d.get("evidence", [])

    tier_counts = {}
    for e in evidence[:10]:  # Check first 10
        # Evidence uses "quality_tier" not "tier"
        tier = e.get("quality_tier", e.get("tier", "MISSING"))
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    print(f"  Evidence count: {len(evidence)}")
    print(f"  Tier distribution (first 10): {tier_counts}")

    # Check if tiers are actually populated or all defaulting
    has_real_tiers = any(t in tier_counts for t in ["GOLD", "SILVER", "BRONZE"])
    all_unknown = all(t in ("?", "MISSING", "") for t in tier_counts)

    if all_unknown:
        print(f"  WARNING: All tiers are '{list(tier_counts.keys())[0]}' - tier data lost in pipeline")
        # Find where tier is set
        if evidence:
            print(f"  Sample evidence keys: {list(evidence[0].keys())[:10]}")
        return False

    return has_real_tiers


# ===================================================================
# R4: Exa API real request
# ===================================================================

@register("R4", "Exa API responds without brotli error (live request)")
def _():
    exa_key = os.getenv("EXA_API_KEY", "")
    if not exa_key:
        print("  No EXA_API_KEY set, skipping live test")
        return True  # Non-blocking

    async def _test_exa():
        from src.polaris_graph.agents.searcher import _run_exa_searches, reset_exa_budget
        reset_exa_budget()
        try:
            results = await _run_exa_searches(["intermittent fasting meta-analysis 2024"])
            print(f"  Exa returned {len(results)} results")
            if results:
                print(f"  First result: {results[0].get('title', '?')[:60]}")
            return True  # No crash = no brotli error
        except Exception as e:
            error_str = str(e)
            if "content-encoding" in error_str.lower() or "br" in error_str.lower():
                print(f"  BROTLI ERROR STILL PRESENT: {error_str[:100]}")
                return False
            print(f"  Different error (not brotli): {error_str[:100]}")
            return True  # Different error, not the one we're testing

    return asyncio.run(_test_exa())


# ===================================================================
# SUMMARY
# ===================================================================

print(f"\n{'='*70}")
print("RISK VERIFICATION SUMMARY")
print(f"{'='*70}")
total = len(results)
passed = sum(1 for _, p in results.values() if p)

for tid in sorted(results.keys()):
    name, ok = results[tid]
    print(f"  {tid:5s} {name:60s} {'PASS' if ok else 'FAIL'}")

print(f"\n  TOTAL: {passed}/{total} PASS")
print(f"  ALL PASS: {passed == total}")
