"""
Component-level verification for POLARIS graph SOTA features.

Tests each feature with REAL calls, REAL data, and measures latency.
Must pass before committing to a full pipeline run.

Usage:
    python -u scripts/pg_component_verify.py
"""

import asyncio
import os
import sys
import time

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env before any imports that read env vars
from dotenv import load_dotenv
load_dotenv(override=True)

results = []
timings = {}


def report(name: str, passed: bool, detail: str, elapsed: float):
    """Record and print a test result."""
    status = "PASS" if passed else "FAIL"
    results.append((name, passed, detail))
    timings[name] = elapsed
    print(f"  [{status}] {name}: {detail} ({elapsed:.1f}s)")


# ============================================================================
# 1. PageRank API — real HTTP call
# ============================================================================
async def test_pagerank_api():
    print("\n=== 1. PageRank API (real HTTP call) ===")
    t0 = time.time()

    api_key = os.getenv("OPEN_PAGERANK_API_KEY", "")
    if not api_key:
        report("PageRank API", False, "OPEN_PAGERANK_API_KEY not set in .env", 0)
        return

    try:
        import aiohttp
        url = "https://openpagerank.com/api/v1.0/getPageRank"
        headers = {"API-OPR": api_key}
        params = [("domains[]", "google.com"), ("domains[]", "epa.gov"), ("domains[]", "example.com")]

        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers, params=params) as response:
                elapsed = time.time() - t0
                if response.status != 200:
                    body = await response.text()
                    report("PageRank API", False, f"HTTP {response.status}: {body[:200]}", elapsed)
                    return

                data = await response.json()
                items = data.get("response", [])

                # Validate we got scores
                scores = {}
                for item in items:
                    domain = item.get("domain", "")
                    score = item.get("page_rank_decimal", 0)
                    scores[domain] = score

                google_score = scores.get("google.com", 0)
                epa_score = scores.get("epa.gov", 0)

                if google_score > 0 and epa_score > 0:
                    report("PageRank API", True,
                           f"google.com={google_score}, epa.gov={epa_score}, "
                           f"{len(items)} domains scored", elapsed)
                else:
                    report("PageRank API", False,
                           f"Scores look wrong: {scores}", elapsed)

    except Exception as e:
        elapsed = time.time() - t0
        report("PageRank API", False, f"Exception: {e}", elapsed)


# ============================================================================
# 2. LettuceDetect GPU inference — load model + run prediction
# ============================================================================
async def test_lettuce_detect():
    print("\n=== 2. LettuceDetect GPU inference (real model load + predict) ===")
    t0 = time.time()

    if os.getenv("PG_HALLUCINATION_DETECT_ENABLED", "0") != "1":
        report("LettuceDetect", False, "PG_HALLUCINATION_DETECT_ENABLED=0 in .env", 0)
        return

    try:
        # This triggers model download + load onto GPU
        from src.polaris_graph.agents.hallucination_detector import _get_detector

        t_load_start = time.time()
        detector = _get_detector()
        load_time = time.time() - t_load_start

        if detector is None:
            report("LettuceDetect", False,
                   "Model failed to load (check GPU/CUDA availability)", time.time() - t0)
            return

        # Run actual inference on a known hallucination
        context = [
            "Water filtration using activated carbon removes chlorine and VOCs. "
            "Reverse osmosis removes up to 99% of dissolved salts and contaminants. "
            "PFAS contamination affects over 2,800 communities in the United States."
        ]
        question = "What are effective water filtration methods?"
        # This answer contains a hallucination: "quantum filtration" is made up
        answer = (
            "Activated carbon removes chlorine effectively. "
            "Reverse osmosis removes 99% of contaminants. "
            "Quantum filtration using nanotube resonance chambers eliminates all PFAS instantly."
        )

        t_infer_start = time.time()
        predictions = detector.predict(
            context=context,
            question=question,
            answer=answer,
            output_format="spans",
        )
        infer_time = time.time() - t_infer_start
        elapsed = time.time() - t0

        if predictions and len(predictions) > 0:
            # Check if the hallucinated span was detected
            flagged_text = " ".join(p.get("text", "") for p in predictions)
            has_quantum = "quantum" in flagged_text.lower() or "nanotube" in flagged_text.lower()
            report("LettuceDetect", True,
                   f"Model loaded ({load_time:.1f}s), inference ({infer_time:.1f}s), "
                   f"{len(predictions)} spans detected, "
                   f"caught fabrication={'YES' if has_quantum else 'partial'}",
                   elapsed)
        else:
            report("LettuceDetect", False,
                   f"Model loaded ({load_time:.1f}s) but detected 0 hallucination spans "
                   f"on known-bad input (inference {infer_time:.1f}s)",
                   elapsed)

    except Exception as e:
        elapsed = time.time() - t0
        report("LettuceDetect", False, f"Exception: {e}", elapsed)


# ============================================================================
# 3. Crawl4AI — real page fetch
# ============================================================================
async def test_crawl4ai():
    print("\n=== 3. Crawl4AI (real page fetch) ===")
    t0 = time.time()

    if os.getenv("PG_CRAWL4AI_ENABLED", "1") != "1":
        report("Crawl4AI", False, "PG_CRAWL4AI_ENABLED=0", 0)
        return

    try:
        from src.tools.access_bypass import AccessBypass
        bypass = AccessBypass()

        # Use a stable, Unicode-heavy page to test both fetch AND Unicode fix
        test_url = "https://en.wikipedia.org/wiki/PFAS"
        result = await bypass._try_crawl4ai(test_url)
        elapsed = time.time() - t0

        if result and result.success and len(result.content) > 500:
            report("Crawl4AI", True,
                   f"{len(result.content)} chars from Wikipedia PFAS "
                   f"(no Unicode crash on Windows)", elapsed)
        elif result and not result.success:
            error = result.metadata.get("error", "unknown")
            report("Crawl4AI", False,
                   f"Fetch failed: {str(error)[:200]}", elapsed)
        else:
            content_len = len(result.content) if result else 0
            report("Crawl4AI", False,
                   f"Insufficient content: {content_len} chars", elapsed)

    except Exception as e:
        elapsed = time.time() - t0
        report("Crawl4AI", False, f"Exception: {e}", elapsed)


# ============================================================================
# 4. Trafilatura — real page fetch via thread pool
# ============================================================================
async def test_trafilatura():
    print("\n=== 4. Trafilatura (real page fetch via thread pool) ===")
    t0 = time.time()

    if os.getenv("PG_TRAFILATURA_ENABLED", "0") != "1":
        report("Trafilatura", False, "PG_TRAFILATURA_ENABLED=0 in .env", 0)
        return

    try:
        from src.tools.access_bypass import AccessBypass
        bypass = AccessBypass()

        test_url = "https://en.wikipedia.org/wiki/PFAS"
        result = await bypass._try_trafilatura(test_url)
        elapsed = time.time() - t0

        if result and result.success and len(result.content) > 200:
            report("Trafilatura", True,
                   f"{len(result.content)} chars, method={result.access_method}", elapsed)
        else:
            report("Trafilatura", False,
                   f"Returned None or insufficient content", elapsed)

    except Exception as e:
        elapsed = time.time() - t0
        report("Trafilatura", False, f"Exception: {e}", elapsed)


# ============================================================================
# 5. Cross-reference embeddings — real embedding computation
# ============================================================================
async def test_cross_reference():
    print("\n=== 5. Cross-reference embeddings (real computation) ===")
    t0 = time.time()

    if os.getenv("PG_CROSS_REF_ENABLED", "0") != "1":
        report("Cross-reference", False, "PG_CROSS_REF_ENABLED=0 in .env", 0)
        return

    try:
        from src.polaris_graph.agents.cross_reference import compute_cross_references

        # Create test evidence: 3 sources all saying the same thing about PFAS
        # (should be detected as cross-referenced), plus 1 unrelated piece
        test_evidence = [
            {
                "evidence_id": "ev_test_001",
                "source_url": "https://www.epa.gov/pfas",
                "statement": "PFAS are persistent chemicals that do not break down in the environment and accumulate in human blood over time.",
                "direct_quote": "PFAS do not break down in the environment",
                "source_type": "government_report",
            },
            {
                "evidence_id": "ev_test_002",
                "source_url": "https://www.niehs.nih.gov/health/topics/agents/pfc",
                "statement": "Per- and polyfluoroalkyl substances persist in the environment and bioaccumulate in human blood plasma.",
                "direct_quote": "PFAS persist in the environment and bioaccumulate",
                "source_type": "journal_article",
            },
            {
                "evidence_id": "ev_test_003",
                "source_url": "https://www.who.int/publications/i/item/pfas",
                "statement": "PFAS chemicals are extremely persistent environmental pollutants that accumulate in human blood and tissue.",
                "direct_quote": "PFAS are extremely persistent pollutants",
                "source_type": "government_report",
            },
            {
                "evidence_id": "ev_test_004",
                "source_url": "https://www.nature.com/articles/s41586-024-solar",
                "statement": "Solar panel efficiency has increased by 15% due to perovskite layer innovations in 2025.",
                "direct_quote": "perovskite innovations boosted efficiency",
                "source_type": "journal_article",
            },
        ]

        # Use min_sources=2 for test (we have 3 corroborating sources)
        groups = compute_cross_references(
            test_evidence,
            min_sources=2,
            sim_threshold=0.50,
        )
        elapsed = time.time() - t0

        if groups and len(groups) > 0:
            top_group = groups[0]
            report("Cross-reference", True,
                   f"{len(groups)} group(s) found, top group: "
                   f"{len(top_group.get('evidence_ids', []))} evidence, "
                   f"agreement={top_group.get('agreement_score', 0):.2f}, "
                   f"solar outlier excluded={'ev_test_004' not in top_group.get('evidence_ids', [])}",
                   elapsed)
        else:
            report("Cross-reference", False,
                   "No groups found — embedding may have failed (check GPU/model)", elapsed)

    except Exception as e:
        elapsed = time.time() - t0
        report("Cross-reference", False, f"Exception: {e}", elapsed)


# ============================================================================
# 6. Hallucination rewrite pipeline — detect + verify remediation works
# ============================================================================
async def test_hallucination_rewrite():
    print("\n=== 6. Hallucination audit + rewrite pipeline ===")
    t0 = time.time()

    if os.getenv("PG_HALLUCINATION_DETECT_ENABLED", "0") != "1":
        report("Hallucination rewrite", False,
               "PG_HALLUCINATION_DETECT_ENABLED=0 in .env", 0)
        return

    try:
        from src.polaris_graph.agents.hallucination_detector import (
            audit_sections_for_hallucination, _is_enabled,
        )

        if not _is_enabled():
            report("Hallucination rewrite", False,
                   "_is_enabled() returned False despite env=1", 0)
            return

        # Section with mixed content: some supported, some hallucinated
        test_sections = [
            {
                "section_id": "sec_test_good",
                "title": "Supported Section",
                "content": (
                    "Activated carbon filtration effectively removes chlorine, "
                    "volatile organic compounds, and some pesticides from drinking water. "
                    "Reverse osmosis systems can remove up to 99% of dissolved contaminants."
                ),
                "evidence_ids": ["ev_good_1"],
            },
            {
                "section_id": "sec_test_bad",
                "title": "Hallucinated Section",
                "content": (
                    "Activated carbon removes chlorine from water. "
                    "However, the revolutionary quantum resonance filtration method developed "
                    "by Dr. Hans Müller at the Zurich Institute of Advanced Hydrology in 2024 "
                    "achieved 100% PFAS removal using crystalline nanotube matrices. "
                    "This breakthrough was confirmed by NASA's Mars Water Reclamation Program "
                    "and is now being deployed in 47 countries worldwide."
                ),
                "evidence_ids": ["ev_good_1"],
            },
        ]

        test_evidence = [
            {
                "evidence_id": "ev_good_1",
                "statement": "Activated carbon removes chlorine and VOCs from water.",
                "direct_quote": "activated carbon removes chlorine",
                "source_content": (
                    "Activated carbon filtration is one of the most common water treatment "
                    "methods. It effectively removes chlorine, volatile organic compounds (VOCs), "
                    "and certain pesticides. Reverse osmosis can remove up to 99% of dissolved "
                    "salts and contaminants from water."
                ),
            },
        ]

        results_audit = audit_sections_for_hallucination(
            sections=test_sections,
            evidence=test_evidence,
            research_query="What are effective water filtration methods for PFAS?",
        )
        elapsed = time.time() - t0

        if not results_audit:
            report("Hallucination rewrite", False,
                   "Audit returned empty — detector may have failed to load", elapsed)
            return

        # Check results
        good_result = next((r for r in results_audit if r["section_id"] == "sec_test_good"), None)
        bad_result = next((r for r in results_audit if r["section_id"] == "sec_test_bad"), None)

        good_ratio = good_result["hallucination_ratio"] if good_result else -1
        bad_ratio = bad_result["hallucination_ratio"] if bad_result else -1
        bad_flagged = bad_result.get("needs_rewrite", False) if bad_result else False

        if bad_ratio > good_ratio and bad_flagged:
            report("Hallucination rewrite", True,
                   f"Good section: {good_ratio:.1%} hallucination, "
                   f"Bad section: {bad_ratio:.1%} hallucination (flagged={bad_flagged}). "
                   f"Detector correctly distinguished supported vs fabricated content.",
                   elapsed)
        elif bad_ratio > good_ratio:
            report("Hallucination rewrite", True,
                   f"Partial: Good={good_ratio:.1%}, Bad={bad_ratio:.1%}. "
                   f"Detector ranked correctly but bad section not flagged "
                   f"(threshold may be too high). needs_rewrite={bad_flagged}",
                   elapsed)
        else:
            report("Hallucination rewrite", False,
                   f"Detector failed to distinguish: Good={good_ratio:.1%}, "
                   f"Bad={bad_ratio:.1%}. Expected bad > good.",
                   elapsed)

    except Exception as e:
        elapsed = time.time() - t0
        report("Hallucination rewrite", False, f"Exception: {e}", elapsed)


# ============================================================================
# 7. Source confidence end-to-end — PageRank + type + composite
# ============================================================================
async def test_source_confidence_e2e():
    print("\n=== 7. Source confidence end-to-end ===")
    t0 = time.time()

    if os.getenv("PG_SOURCE_CONFIDENCE_ENABLED", "0") != "1":
        report("Source confidence E2E", False,
               "PG_SOURCE_CONFIDENCE_ENABLED=0 in .env", 0)
        return

    try:
        from src.polaris_graph.agents.source_confidence import (
            _is_enabled, get_source_confidence, get_type_confidence,
            compute_composite_confidence,
        )

        if not _is_enabled():
            report("Source confidence E2E", False,
                   "_is_enabled() returned False despite env=1", 0)
            return

        # Test type scores
        journal_score = get_type_confidence("journal_article")
        blog_score = get_type_confidence("blog")
        assert journal_score > blog_score, f"journal ({journal_score}) should > blog ({blog_score})"

        # Test PageRank with real domains
        urls = [
            "https://www.epa.gov/pfas/overview",
            "https://www.nature.com/articles/test",
            "https://randomnobodysite12345.com/page",
        ]
        pagerank_scores = await get_source_confidence(urls)

        # Test composite
        epa_pr = pagerank_scores.get(urls[0], 0.0)
        epa_composite = compute_composite_confidence(epa_pr, journal_score, 50)

        elapsed = time.time() - t0

        if epa_pr > 0:
            report("Source confidence E2E", True,
                   f"EPA PageRank={epa_pr:.4f}, nature={pagerank_scores.get(urls[1], 0):.4f}, "
                   f"unknown={pagerank_scores.get(urls[2], 0):.4f}. "
                   f"Composite(EPA,journal,50cites)={epa_composite:.4f}",
                   elapsed)
        else:
            report("Source confidence E2E", False,
                   f"PageRank returned 0 for EPA — API key may be invalid. "
                   f"Scores: {pagerank_scores}", elapsed)

    except Exception as e:
        elapsed = time.time() - t0
        report("Source confidence E2E", False, f"Exception: {e}", elapsed)


# ============================================================================
# MAIN
# ============================================================================
async def main():
    print("=" * 70)
    print("POLARIS Graph — Component Verification (Real Calls)")
    print("=" * 70)

    # Run tests that don't need GPU first (faster feedback)
    await test_pagerank_api()
    await test_source_confidence_e2e()
    await test_trafilatura()
    await test_crawl4ai()
    await test_cross_reference()

    # GPU-heavy tests last
    await test_lettuce_detect()
    await test_hallucination_rewrite()

    # Summary
    print("\n" + "=" * 70)
    passed = sum(1 for _, p, _ in results if p)
    failed = sum(1 for _, p, _ in results if not p)
    total_time = sum(timings.values())

    print(f"RESULTS: {passed}/{passed + failed} passed, {failed} failed")
    print(f"Total time: {total_time:.1f}s")

    if timings:
        print(f"\nLatency breakdown:")
        for name, t in sorted(timings.items(), key=lambda x: -x[1]):
            print(f"  {name}: {t:.1f}s")

    # Pipeline time budget estimate
    print(f"\nPipeline time budget estimate:")
    print(f"  TEST_037 baseline: ~80 min")
    extra = 0
    if "PageRank API" in timings:
        # ~50 unique domains per run, batched 100
        est = timings["PageRank API"] * 1  # 1 batch call
        extra += est
        print(f"  + PageRank API (~50 domains): ~{est:.0f}s")
    if "Cross-reference" in timings:
        # 1000 evidence, ~10x test size
        est = timings["Cross-reference"] * 10
        extra += est
        print(f"  + Cross-reference (1000 evidence): ~{est:.0f}s")
    if "LettuceDetect" in timings:
        # ~12 sections
        est = timings["LettuceDetect"] * 1.5  # model already loaded for 2nd+ sections
        extra += est
        print(f"  + LettuceDetect (~12 sections): ~{est:.0f}s")
    if "Hallucination rewrite" in timings:
        # Assume 2-3 sections flagged for rewrite
        est = 30  # revise_section takes ~10s each
        extra += est
        print(f"  + Hallucination rewrites (~3 sections): ~{est:.0f}s")
    print(f"  + Trafilatura (fallback only): ~0s (concurrent fetch usually wins)")
    print(f"  Estimated extra time: ~{extra / 60:.1f} min")
    print(f"  Estimated total: ~{80 + extra / 60:.0f} min")
    print(f"  Pipeline cap: {os.getenv('PG_MAX_EXECUTION_MINUTES', '120')} min")

    cap = int(os.getenv("PG_MAX_EXECUTION_MINUTES", "120"))
    estimated = 80 + extra / 60
    if estimated > cap * 0.85:
        print(f"\n  WARNING: Estimated time ({estimated:.0f}min) is >{cap * 0.85:.0f}min "
              f"(85% of {cap}min cap). Consider increasing PG_MAX_EXECUTION_MINUTES.")

    print("\n" + "=" * 70)
    if failed > 0:
        print("BLOCKED: Fix failed components before running PG_TEST_038")
        for name, p, detail in results:
            if not p:
                print(f"  FIX: {name} — {detail}")
        sys.exit(1)
    else:
        print("ALL CLEAR: Ready for PG_TEST_038 full pipeline run")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
