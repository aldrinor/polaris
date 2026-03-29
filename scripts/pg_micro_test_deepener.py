"""
Micro tests for evidence deepener module.
Run: python -u scripts/pg_micro_test_deepener.py

Tests both offline (code/regex) and online (S2 API) functionality.
"""
import asyncio
import os
import re
import sys
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
# TEST 1: Module imports and feature flag
# ===================================================================

@register("D01", "Evidence deepener imports cleanly")
def _():
    from src.polaris_graph.agents.evidence_deepener import (
        deepen_evidence,
        PG_EVIDENCE_DEEPENER,
        PG_DEEPENER_EVIDENCE_CAP,
        PG_DEEPENER_TIMEOUT,
        _extract_doi,
        _is_academic_url,
        _filter_by_query_relevance,
        _normalize_s2_paper,
        _fallback_mechanism_queries,
    )
    print(f"  PG_EVIDENCE_DEEPENER={PG_EVIDENCE_DEEPENER}")
    print(f"  PG_DEEPENER_EVIDENCE_CAP={PG_DEEPENER_EVIDENCE_CAP}")
    print(f"  PG_DEEPENER_TIMEOUT={PG_DEEPENER_TIMEOUT}")
    return True


# ===================================================================
# TEST 2: DOI extraction from URLs
# ===================================================================

@register("D02", "DOI extraction from various URL formats")
def _():
    from src.polaris_graph.agents.evidence_deepener import _extract_doi

    cases = [
        ("https://doi.org/10.1001/jama.2024.12345", "10.1001/jama.2024.12345"),
        ("https://dx.doi.org/10.1038/nature12345", "10.1038/nature12345"),
        ("https://www.sciencedirect.com/science/article/pii/S0140?doi=10.1016/j.cell.2024.01", "10.1016/j.cell.2024.01"),
        ("https://pubmed.ncbi.nlm.nih.gov/12345678/", ""),
        ("https://www.google.com/search?q=fasting", ""),
    ]

    all_ok = True
    for url, expected in cases:
        actual = _extract_doi(url)
        ok = actual == expected
        if not ok:
            all_ok = False
        print(f"  {'OK' if ok else 'FAIL'}: {url[:60]} => '{actual}' (expected '{expected}')")

    return all_ok


# ===================================================================
# TEST 3: Academic URL detection
# ===================================================================

@register("D03", "Academic URL detection")
def _():
    from src.polaris_graph.agents.evidence_deepener import _is_academic_url

    academic = [
        "https://doi.org/10.1001/jama.2024.12345",
        "https://pubmed.ncbi.nlm.nih.gov/12345678/",
        "https://arxiv.org/abs/2401.12345",
        "https://www.nature.com/articles/s41591-024-01234-5",
        "https://www.frontiersin.org/articles/10.3389/fnut.2024.001",
        "https://www.mdpi.com/2072-6643/16/5/123",
    ]
    non_academic = [
        "https://www.healthline.com/nutrition/fasting",
        "https://www.webmd.com/diet/intermittent-fasting",
        "https://en.wikipedia.org/wiki/Fasting",
        "https://www.reddit.com/r/fasting",
    ]

    all_ok = True
    for url in academic:
        ok = _is_academic_url(url)
        if not ok:
            all_ok = False
        print(f"  {'OK' if ok else 'FAIL'}: Academic: {url[:60]} => {ok}")

    for url in non_academic:
        ok = not _is_academic_url(url)
        if not ok:
            all_ok = False
        print(f"  {'OK' if ok else 'FAIL'}: Non-academic: {url[:60]} => {not ok}")

    return all_ok


# ===================================================================
# TEST 4: S2 paper normalization
# ===================================================================

@register("D04", "S2 paper normalization format")
def _():
    from src.polaris_graph.agents.evidence_deepener import _normalize_s2_paper

    raw = {
        "paperId": "abc123",
        "title": "Effects of Intermittent Fasting on Metabolic Health",
        "abstract": "This study examines...",
        "url": "https://semanticscholar.org/paper/abc123",
        "year": 2024,
        "authors": [{"name": "John Smith"}, {"name": "Jane Doe"}],
        "citationCount": 42,
        "venue": "JAMA",
        "openAccessPdf": {"url": "https://example.com/paper.pdf"},
        "fieldsOfStudy": ["Medicine", "Biology"],
    }

    result = _normalize_s2_paper(raw)
    checks = [
        ("paperId", result.get("paperId") == "abc123"),
        ("title", "Intermittent Fasting" in result.get("title", "")),
        ("url uses OA PDF", result.get("url") == "https://example.com/paper.pdf"),
        ("openAccessPdf", result.get("openAccessPdf") == "https://example.com/paper.pdf"),
        ("authors list", result.get("authors") == ["John Smith", "Jane Doe"]),
        ("source_type", result.get("source_type") == "academic"),
        ("search_engine", result.get("search_engine") == "s2_deepener"),
    ]

    all_ok = True
    for name, ok in checks:
        if not ok:
            all_ok = False
        print(f"  {'OK' if ok else 'FAIL'}: {name}")

    # Test without OA PDF — should fallback to url
    raw2 = dict(raw)
    raw2["openAccessPdf"] = None
    result2 = _normalize_s2_paper(raw2)
    url_ok = result2.get("url") == "https://semanticscholar.org/paper/abc123"
    print(f"  {'OK' if url_ok else 'FAIL'}: url fallback (no OA PDF)")

    return all_ok and url_ok


# ===================================================================
# TEST 5: Query relevance filtering
# ===================================================================

@register("D05", "Query relevance filtering")
def _():
    from src.polaris_graph.agents.evidence_deepener import _filter_by_query_relevance

    query = "intermittent fasting metabolic health clinical trials"
    papers = [
        {"title": "Intermittent Fasting and Metabolic Syndrome", "abstract": "A clinical trial...", "citationCount": 100},
        {"title": "Deep Learning for Image Recognition", "abstract": "Neural networks...", "citationCount": 500},
        {"title": "Fasting and Insulin Resistance", "abstract": "Clinical trial shows metabolic improvements...", "citationCount": 50},
        {"title": "Quantum Computing Advances", "abstract": "Qubits and entanglement...", "citationCount": 200},
    ]

    filtered = _filter_by_query_relevance(papers, query)
    titles = [p["title"] for p in filtered]

    has_fasting = any("Fasting" in t for t in titles)
    no_quantum = "Quantum Computing Advances" not in titles
    no_deep = "Deep Learning for Image Recognition" not in titles

    print(f"  Filtered: {len(filtered)} papers")
    for t in titles:
        print(f"    - {t}")
    print(f"  Has fasting papers: {has_fasting}")
    print(f"  No quantum: {no_quantum}")
    print(f"  No deep learning: {no_deep}")

    return has_fasting and no_quantum and no_deep


# ===================================================================
# TEST 6: Fallback mechanism queries
# ===================================================================

@register("D06", "Fallback mechanism query generation")
def _():
    from src.polaris_graph.agents.evidence_deepener import _fallback_mechanism_queries

    queries = _fallback_mechanism_queries("intermittent fasting metabolic health")
    lines = [l.strip() for l in queries.strip().split("\n") if l.strip()]

    print(f"  Generated {len(lines)} queries:")
    for q in lines:
        print(f"    - {q}")

    has_mechanism = any("mechanism" in q.lower() for q in lines)
    has_5 = len(lines) >= 5

    print(f"  Has 'mechanism': {has_mechanism}")
    print(f"  Has 5 queries: {has_5}")

    return has_mechanism and has_5


# ===================================================================
# TEST 7: Evidence cap enforcement
# ===================================================================

@register("D07", "Evidence cap at PG_DEEPENER_EVIDENCE_CAP")
def _():
    from src.polaris_graph.agents.evidence_deepener import (
        _finalize, PG_DEEPENER_EVIDENCE_CAP,
    )

    # Create 200 fake papers (over cap)
    papers = [
        {
            "paperId": f"paper_{i}",
            "url": f"https://example.com/paper_{i}",
            "title": f"Paper {i}",
            "citationCount": 200 - i,  # Descending citation count
        }
        for i in range(200)
    ]

    result = _finalize(papers, {}, 0.0, None, set())
    new_papers = result.get("deepened_papers", [])

    capped_ok = len(new_papers) == PG_DEEPENER_EVIDENCE_CAP
    # Most cited should be first
    first_cites = new_papers[0].get("citationCount", 0) if new_papers else 0
    order_ok = first_cites == 200

    print(f"  Input: {len(papers)} papers")
    print(f"  Output: {len(new_papers)} papers (cap={PG_DEEPENER_EVIDENCE_CAP})")
    print(f"  First paper citations: {first_cites} (should be 200)")
    print(f"  Capped OK: {capped_ok}")
    print(f"  Order OK: {order_ok}")

    return capped_ok and order_ok


# ===================================================================
# TEST 8: Dedup against existing evidence
# ===================================================================

@register("D08", "Dedup against existing evidence URLs")
def _():
    from src.polaris_graph.agents.evidence_deepener import _finalize

    papers = [
        {"paperId": "new1", "url": "https://example.com/new1", "title": "New 1", "citationCount": 10},
        {"paperId": "dup1", "url": "https://example.com/existing1", "title": "Dup 1", "citationCount": 50},
        {"paperId": "new2", "url": "https://example.com/new2", "title": "New 2", "citationCount": 20},
    ]
    existing_urls = {"https://example.com/existing1", "https://example.com/existing2"}

    result = _finalize(papers, {}, 0.0, None, existing_urls)
    new_papers = result.get("deepened_papers", [])
    urls = [p.get("url") for p in new_papers]

    no_dup = "https://example.com/existing1" not in urls
    has_new = len(new_papers) == 2

    print(f"  Input: {len(papers)} papers, {len(existing_urls)} existing URLs")
    print(f"  Output: {len(new_papers)} new papers")
    print(f"  No duplicates: {no_dup}")
    print(f"  Has 2 new: {has_new}")

    return no_dup and has_new


# ===================================================================
# TEST 9: Graph has deepen_evidence node wired correctly
# ===================================================================

@register("D09", "Graph has deepen_evidence node with correct edges")
def _():
    from src.polaris_graph.graph import build_graph
    g = build_graph()
    nodes = list(g.nodes.keys())

    has_node = "deepen_evidence" in nodes
    # Check ordering: verify → deepen_evidence → evaluate
    verify_idx = nodes.index("verify") if "verify" in nodes else -1
    deepen_idx = nodes.index("deepen_evidence") if "deepen_evidence" in nodes else -1
    evaluate_idx = nodes.index("evaluate") if "evaluate" in nodes else -1

    order_ok = verify_idx < deepen_idx < evaluate_idx

    print(f"  Nodes: {nodes}")
    print(f"  Has deepen_evidence: {has_node}")
    print(f"  Order (verify < deepen < evaluate): {order_ok}")
    print(f"  Indices: verify={verify_idx}, deepen={deepen_idx}, evaluate={evaluate_idx}")

    return has_node and order_ok


# ===================================================================
# TEST 10: State fields exist
# ===================================================================

@register("D10", "ResearchState has deepener fields")
def _():
    from src.polaris_graph.state import ResearchState, create_initial_state

    # Check TypedDict annotations
    annotations = ResearchState.__annotations__
    has_papers = "deepened_papers" in annotations
    has_stats = "deepener_stats" in annotations

    # Check initial state
    state = create_initial_state("v1", "test query", "app", "us")
    papers_init = state.get("deepened_papers", None)
    stats_init = state.get("deepener_stats", None)

    print(f"  TypedDict has deepened_papers: {has_papers}")
    print(f"  TypedDict has deepener_stats: {has_stats}")
    print(f"  Initial deepened_papers: {papers_init}")
    print(f"  Initial deepener_stats: {stats_init}")

    return has_papers and has_stats and papers_init == [] and stats_init == {}


# ===================================================================
# TEST 11: Feature flag bypass (disabled)
# ===================================================================

@register("D11", "Feature flag bypass returns empty when disabled")
def _():
    import os
    # Temporarily disable
    original = os.environ.get("PG_EVIDENCE_DEEPENER", "")
    os.environ["PG_EVIDENCE_DEEPENER"] = "0"

    try:
        # Re-import to pick up new env value
        import importlib
        import src.polaris_graph.agents.evidence_deepener as mod
        importlib.reload(mod)

        async def _test():
            from src.polaris_graph.llm.openrouter_client import OpenRouterClient
            client = OpenRouterClient()
            state = {"evidence": [{"statement": "test"}], "original_query": "test", "iteration_count": 0}
            result = await mod.deepen_evidence(client, state)
            return result

        result = asyncio.run(_test())
        empty_ok = result == {}
        print(f"  Result when disabled: {result}")
        print(f"  Empty: {empty_ok}")
        return empty_ok
    finally:
        if original:
            os.environ["PG_EVIDENCE_DEEPENER"] = original
        else:
            os.environ.pop("PG_EVIDENCE_DEEPENER", None)
        # Reload with original setting
        import importlib
        import src.polaris_graph.agents.evidence_deepener as mod
        importlib.reload(mod)


# ===================================================================
# TEST 12: S2 paper ID resolution (LIVE API)
# ===================================================================

@register("D12", "S2 paper ID resolution (live API — PMID + search)")
def _():
    s2_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    if not s2_key:
        print("  SKIP: No SEMANTIC_SCHOLAR_API_KEY")
        return True  # Skip, not fail

    async def _test():
        from src.polaris_graph.agents.evidence_deepener import _resolve_single_url

        # Test PMID resolution (Trepanowski 2017 IF RCT)
        paper_id = await _resolve_single_url(
            "https://pubmed.ncbi.nlm.nih.gov/28715500/",
            s2_key,
        )
        print(f"  PMID resolution: paperId='{paper_id[:20]}...'")

        # Test ArXiv resolution
        paper_id2 = await _resolve_single_url(
            "https://arxiv.org/abs/2301.00234",
            s2_key,
        )
        print(f"  ArXiv resolution: paperId='{paper_id2[:20] if paper_id2 else 'empty'}'")

        # At least PMID should work
        return bool(paper_id)

    return asyncio.run(_test())


# ===================================================================
# TEST 13: S2 search (LIVE API)
# ===================================================================

@register("D13", "S2 search for named study (live API)")
def _():
    s2_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    if not s2_key:
        print("  SKIP: No SEMANTIC_SCHOLAR_API_KEY")
        return True

    async def _test():
        import aiohttp
        from src.polaris_graph.agents.evidence_deepener import _s2_search

        headers = {"x-api-key": s2_key}
        timeout = aiohttp.ClientTimeout(total=30)
        results = await _s2_search(
            "Trepanowski alternate day fasting randomized",
            headers, timeout, limit=3,
        )
        print(f"  Results: {len(results)}")
        for r in results[:3]:
            print(f"    - {r.get('title', '')[:80]} ({r.get('year', '?')})")
        return len(results) > 0

    return asyncio.run(_test())


# ===================================================================
# TEST 14: Named study extraction (LIVE LLM)
# ===================================================================

@register("D14", "Named study extraction from evidence (live LLM)")
def _():
    async def _test():
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient
        from src.polaris_graph.agents.evidence_deepener import _extract_named_studies

        client = OpenRouterClient()
        evidence = [
            {"statement": "Trepanowski et al. (2017) found that alternate-day fasting produced similar weight loss to daily calorie restriction in a 12-month RCT."},
            {"statement": "The meta-analysis by Varady et al. (2022) showed a mean weight loss of 4.3 kg with ADF across 7 trials."},
            {"statement": "Longo and Mattson (2014) proposed that fasting-mimicking diets activate autophagy through mTOR inhibition."},
            {"statement": "HOMA-IR decreased by SMD -0.39 in pooled analysis."},
        ]

        studies = await _extract_named_studies(client, evidence, "intermittent fasting clinical trials")
        print(f"  Extracted {len(studies)} named studies:")
        for s in studies:
            print(f"    - {s.get('author', '?')} | {s.get('year', '?')} | {s.get('description', '')[:50]}")

        # Should find at least Trepanowski, Varady, Longo
        authors = [s.get("author", "").lower() for s in studies]
        has_trepanowski = any("trepanowski" in a for a in authors)
        has_varady = any("varady" in a for a in authors)
        has_longo = any("longo" in a for a in authors)

        print(f"  Trepanowski: {has_trepanowski}")
        print(f"  Varady: {has_varady}")
        print(f"  Longo: {has_longo}")

        return len(studies) >= 2 and (has_trepanowski or has_varady)

    return asyncio.run(_test())


# ===================================================================
# TEST 15: Mechanism query generation (LIVE LLM)
# ===================================================================

@register("D15", "Mechanism query generation (live LLM)")
def _():
    async def _test():
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient
        from src.polaris_graph.agents.evidence_deepener import _mechanism_search

        client = OpenRouterClient()
        s2_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
        if not s2_key:
            print("  SKIP: No S2 key")
            return True

        papers = await _mechanism_search(client, "intermittent fasting metabolic health", s2_key)
        print(f"  Found {len(papers)} mechanism papers:")
        for p in papers[:5]:
            print(f"    - {p.get('title', '')[:70]} ({p.get('year', '?')})")

        return len(papers) > 0

    return asyncio.run(_test())


# ===================================================================
# SUMMARY
# ===================================================================

print(f"\n{'='*70}")
print("EVIDENCE DEEPENER VERIFICATION SUMMARY")
print(f"{'='*70}")
total = len(results)
passed = sum(1 for _, p in results.values() if p)
for tid in sorted(results.keys()):
    name, ok = results[tid]
    print(f"  {tid:5s} {name:60s} {'PASS' if ok else 'FAIL'}")
print(f"\n  TOTAL: {passed}/{total} PASS")
print(f"  ALL PASS: {passed == total}")
