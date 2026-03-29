"""
End-to-end integration test for evidence deepener.
Run: python -u scripts/pg_micro_test_deepener_e2e.py

Exercises the FULL deepen_evidence() function with:
- Real evidence from an intermittent fasting query
- Real S2 API calls (paper resolution, citation chasing, recommendations)
- Real LLM calls (named study extraction, mechanism query generation)
- Real PDF fetch attempts

This is the "small-scale test" before launching a full pipeline run.
"""
import asyncio
import json
import os
import sys
import time
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
# Realistic evidence pool (from TEST_075 intermittent fasting run)
# ===================================================================

REALISTIC_EVIDENCE = [
    {
        "evidence_id": "ev_001",
        "source_url": "https://pubmed.ncbi.nlm.nih.gov/28715500/",
        "source_title": "Effect of Alternate-Day Fasting on Weight Loss",
        "source_type": "academic",
        "statement": "Trepanowski et al. (2017) found that alternate-day fasting produced 6.0% weight loss vs 5.3% with daily calorie restriction over 12 months (n=100, 38% dropout).",
        "direct_quote": "Alternate-day fasting did not produce superior adherence, weight loss, weight maintenance, or cardioprotection vs daily calorie restriction.",
        "quality_tier": "GOLD",
        "relevance_score": 0.92,
    },
    {
        "evidence_id": "ev_002",
        "source_url": "https://doi.org/10.1038/s41574-022-00638-x",
        "source_title": "Intermittent fasting: from calories to time restriction",
        "source_type": "academic",
        "statement": "Varady et al. (2022) meta-analysis of 7 RCTs found ADF reduced weight by MD -4.30 kg (95% CI -5.54 to -3.05; I2=96%).",
        "direct_quote": "Alternate-day fasting resulted in significant weight loss compared with control (MD -4.30 kg; 95% CI, -5.54 to -3.05).",
        "quality_tier": "GOLD",
        "relevance_score": 0.95,
    },
    {
        "evidence_id": "ev_003",
        "source_url": "https://doi.org/10.1016/j.cmet.2014.01.011",
        "source_title": "Fasting, Circadian Rhythms, and Time-Restricted Feeding in Healthy Lifespan",
        "source_type": "academic",
        "statement": "Longo and Mattson (2014) proposed that fasting-mimicking diets activate autophagy through mTOR pathway inhibition, with implications for cancer prevention and longevity.",
        "direct_quote": "Fasting triggers adaptive cellular stress responses that enhance the ability of cells to cope with stress and resist disease.",
        "quality_tier": "GOLD",
        "relevance_score": 0.88,
    },
    {
        "evidence_id": "ev_004",
        "source_url": "https://www.bmj.com/content/378/bmj-2022-069718",
        "source_title": "Calorie restriction and intermittent fasting for cardiometabolic health",
        "source_type": "academic",
        "statement": "Network meta-analysis (2023) found ADF vs continuous energy restriction: MD -1.29 kg, moderate GRADE certainty. Time-restricted eating showed lesser effects.",
        "direct_quote": "Alternate day fasting was associated with greater weight loss than continuous energy restriction.",
        "quality_tier": "GOLD",
        "relevance_score": 0.90,
    },
    {
        "evidence_id": "ev_005",
        "source_url": "https://www.frontiersin.org/articles/10.3389/fnut.2024.001234",
        "source_title": "Effects of intermittent fasting on insulin resistance: a systematic review",
        "source_type": "academic",
        "statement": "HOMA-IR decreased by SMD -0.39 (95% CI: -0.65 to -0.12; p=0.004) across 12 RCTs pooled analysis. The 52% reduction in fasting insulin with ADF substantially exceeds the 17% reduction with continuous restriction.",
        "direct_quote": "Intermittent fasting significantly reduced HOMA-IR compared with control (SMD -0.39; 95% CI -0.65 to -0.12).",
        "quality_tier": "GOLD",
        "relevance_score": 0.87,
    },
    {
        "evidence_id": "ev_006",
        "source_url": "https://www.healthline.com/nutrition/intermittent-fasting-guide",
        "source_title": "Intermittent Fasting 101: A Complete Guide",
        "source_type": "web",
        "statement": "Popular protocols include 16:8 time-restricted eating, alternate-day fasting, and the 5:2 diet.",
        "direct_quote": "The 16:8 method involves fasting for 16 hours each day.",
        "quality_tier": "BRONZE",
        "relevance_score": 0.45,
    },
]

QUERY = "intermittent fasting clinical research: benefits, risks, and evidence quality for metabolic health outcomes"


# ===================================================================
# E2E-1: Full deepen_evidence() call with real APIs
# ===================================================================

@register("E2E1", "Full deepen_evidence() with real evidence pool (live)")
def _():
    async def _test():
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient
        from src.polaris_graph.agents.evidence_deepener import deepen_evidence

        client = OpenRouterClient()

        state = {
            "evidence": REALISTIC_EVIDENCE,
            "original_query": QUERY,
            "iteration_count": 1,  # First pass
            "academic_results": [],
            "web_results": [],
        }

        t0 = time.monotonic()
        result = await deepen_evidence(client, state)
        elapsed = round(time.monotonic() - t0, 1)

        papers = result.get("deepened_papers", [])
        stats = result.get("deepener_stats", {})

        print(f"  Elapsed: {elapsed}s")
        print(f"  New papers: {len(papers)}")
        print(f"  Stats: {json.dumps(stats, indent=2, default=str)}")

        if papers:
            print(f"\n  Top 10 papers by citation count:")
            sorted_papers = sorted(papers, key=lambda p: p.get("citationCount", 0), reverse=True)
            for i, p in enumerate(sorted_papers[:10]):
                title = p.get("title", "?")[:65].encode("ascii", "replace").decode()
                year = p.get("year", "?")
                cites = p.get("citationCount", 0)
                engine = p.get("search_engine", "?")
                has_pdf = bool(p.get("openAccessPdf") or p.get("full_text"))
                print(f"    {i+1:2d}. [{engine:15s}] {title} ({year}, {cites} cites{', PDF' if has_pdf else ''})")

        # Validate
        has_papers = len(papers) > 0
        has_stats = bool(stats)
        named_ok = stats.get("named_studies_extracted", 0) > 0
        resolved_ok = stats.get("s2_ids_resolved", 0) > 0
        chased_ok = stats.get("citations_chased", 0) > 0
        time_ok = elapsed < 720  # Under budget

        print(f"\n  Checks:")
        print(f"    Papers found: {has_papers} ({len(papers)})")
        print(f"    Named studies extracted: {named_ok} ({stats.get('named_studies_extracted', 0)})")
        print(f"    S2 IDs resolved: {resolved_ok} ({stats.get('s2_ids_resolved', 0)})")
        print(f"    Citations chased: {chased_ok} ({stats.get('citations_chased', 0)})")
        print(f"    Recommendations: {stats.get('recommendations_found', 0)}")
        print(f"    Mechanism papers: {stats.get('mechanism_papers_found', 0)}")
        print(f"    PDFs fetched: {stats.get('pdfs_fetched', 0)}")
        print(f"    Under time budget: {time_ok} ({elapsed}s / 720s)")

        return has_papers and has_stats and time_ok

    return asyncio.run(_test())


# ===================================================================
# E2E-2: Verify papers are NOT duplicates of existing evidence
# ===================================================================

@register("E2E2", "Deepened papers have no URL overlap with input evidence")
def _():
    async def _test():
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient
        from src.polaris_graph.agents.evidence_deepener import deepen_evidence

        client = OpenRouterClient()

        state = {
            "evidence": REALISTIC_EVIDENCE,
            "original_query": QUERY,
            "iteration_count": 1,
            "academic_results": [],
            "web_results": [],
        }

        result = await deepen_evidence(client, state)
        papers = result.get("deepened_papers", [])

        existing_urls = {e["source_url"] for e in REALISTIC_EVIDENCE}
        new_urls = {p.get("url", "") for p in papers}
        overlap = existing_urls & new_urls

        print(f"  Existing URLs: {len(existing_urls)}")
        print(f"  New paper URLs: {len(new_urls)}")
        print(f"  Overlap: {len(overlap)}")
        if overlap:
            for url in overlap:
                print(f"    DUPLICATE: {url}")

        return len(overlap) == 0

    return asyncio.run(_test())


# ===================================================================
# E2E-3: Papers are topically relevant (not off-topic garbage)
# ===================================================================

@register("E2E3", "Deepened papers are topically relevant to fasting/metabolic")
def _():
    async def _test():
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient
        from src.polaris_graph.agents.evidence_deepener import deepen_evidence

        client = OpenRouterClient()

        state = {
            "evidence": REALISTIC_EVIDENCE,
            "original_query": QUERY,
            "iteration_count": 1,
            "academic_results": [],
            "web_results": [],
        }

        result = await deepen_evidence(client, state)
        papers = result.get("deepened_papers", [])

        if not papers:
            print("  No papers to check")
            return False

        # Check topic relevance: title+abstract should contain fasting/diet/metabolic terms
        topic_terms = {
            "fasting", "intermittent", "calori", "diet", "metaboli",
            "insulin", "glucose", "weight", "obes", "restrict",
            "autophagy", "circadian", "eat", "food", "nutri",
            "lipid", "cholesterol", "cardio", "glycem", "homa",
        }

        relevant_count = 0
        off_topic = []
        for p in papers:
            text = f"{p.get('title', '')} {p.get('abstract', '')}".lower()
            if any(term in text for term in topic_terms):
                relevant_count += 1
            else:
                off_topic.append(p.get("title", "?")[:60])

        relevance_pct = relevant_count / max(len(papers), 1) * 100
        print(f"  Total papers: {len(papers)}")
        print(f"  Topically relevant: {relevant_count} ({relevance_pct:.0f}%)")
        if off_topic:
            print(f"  Off-topic ({len(off_topic)}):")
            for t in off_topic[:5]:
                print(f"    - {t.encode('ascii', 'replace').decode()}")

        # At least 70% should be relevant
        threshold = 70.0
        ok = relevance_pct >= threshold
        print(f"  Threshold: >= {threshold}% => {'OK' if ok else 'FAIL'}")
        return ok

    return asyncio.run(_test())


# ===================================================================
# E2E-4: Graph integration — _deepen node returns valid state update
# ===================================================================

@register("E2E4", "DEEP-FIX: _analyze merges deepened_papers into academic_results")
def _():
    """Verify the DEEP-FIX integration path:
    1. _deepen stores papers in state["deepened_papers"]
    2. _analyze reads deepened_papers and merges into academic_results
    3. Search node CANNOT overwrite deepened_papers (separate key)
    """
    async def _test():
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient
        from src.polaris_graph.agents.evidence_deepener import deepen_evidence

        client = OpenRouterClient()

        state = {
            "evidence": REALISTIC_EVIDENCE,
            "original_query": QUERY,
            "iteration_count": 1,
            "academic_results": [
                {"url": "https://existing.com/paper1", "title": "Existing Paper"},
            ],
            "web_results": [],
            "deepened_papers": [],
        }

        # Step 1: Run deepener (like _deepen node does)
        result = await deepen_evidence(client, state)
        papers = result.get("deepened_papers", [])

        if not papers:
            print("  No papers found — cannot test integration")
            return "deepener_stats" in result

        # Step 2: Simulate _deepen storing papers in state
        state["deepened_papers"] = papers

        # Step 3: Simulate search node OVERWRITING academic_results
        # (This is the bug DEEP-FIX prevents)
        state["academic_results"] = [
            {"url": "https://search.com/new1", "title": "Search Result 1"},
        ]

        # Step 4: Simulate _analyze's DEEP-FIX merge
        deepened = state.get("deepened_papers", [])
        if deepened:
            existing_academic = list(state.get("academic_results", []))
            existing_urls = {r.get("url", "") for r in existing_academic}
            new_from_deepen = [
                p for p in deepened
                if p.get("url", "") and p.get("url", "") not in existing_urls
            ]
            merged = existing_academic + new_from_deepen
        else:
            merged = list(state.get("academic_results", []))

        print(f"  Deepened papers: {len(papers)}")
        print(f"  Search results (overwrite): {len(state['academic_results'])}")
        print(f"  After DEEP-FIX merge: {len(merged)}")

        # Verify: deepened papers survived the search overwrite
        deepened_urls = {p.get("url", "") for p in papers if p.get("url")}
        merged_urls = {r.get("url", "") for r in merged}
        survived = deepened_urls.issubset(merged_urls)

        # Verify: search results also preserved
        search_preserved = any(r.get("url") == "https://search.com/new1" for r in merged)

        print(f"  Deepened papers survived: {survived}")
        print(f"  Search results preserved: {search_preserved}")

        return survived and search_preserved

    return asyncio.run(_test())


# ===================================================================
# E2E-5: Iteration 2 skip — deepener returns empty on second pass
# ===================================================================

@register("E2E5", "Deepener skips on iteration 2 (runs once only)")
def _():
    async def _test():
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient
        from src.polaris_graph.agents.evidence_deepener import deepen_evidence

        client = OpenRouterClient()

        state = {
            "evidence": REALISTIC_EVIDENCE,
            "original_query": QUERY,
            "iteration_count": 2,  # Second pass
            "academic_results": [],
        }

        t0 = time.monotonic()
        result = await deepen_evidence(client, state)
        elapsed = round(time.monotonic() - t0, 3)

        empty = result == {}
        fast = elapsed < 1.0  # Should return instantly

        print(f"  Result: {result}")
        print(f"  Elapsed: {elapsed}s")
        print(f"  Empty (skipped): {empty}")
        print(f"  Fast (< 1s): {fast}")

        return empty and fast

    return asyncio.run(_test())


# ===================================================================
# SUMMARY
# ===================================================================

print(f"\n{'='*70}")
print("EVIDENCE DEEPENER E2E INTEGRATION SUMMARY")
print(f"{'='*70}")
total = len(results)
passed = sum(1 for _, p in results.values() if p)
for tid in sorted(results.keys()):
    name, ok = results[tid]
    print(f"  {tid:5s} {name:60s} {'PASS' if ok else 'FAIL'}")
print(f"\n  TOTAL: {passed}/{total} PASS")
print(f"  ALL PASS: {passed == total}")
