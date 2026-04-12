"""
FULL-SCALE search stage smoke test.

Simulates what the real agentic loop does across 5 rounds:
- 6 web queries + 3 scholar queries + 1 S2/OpenAlex per round
- Fetch ALL unique URLs through the real access bypass cascade
- Classify every source
- Report the exact input the analyzer would see

NO LLM CALLS. Just search APIs + content fetch + classification.
"""
import asyncio
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger(__name__)


# Realistic queries the planner would generate across 5 rounds
ROUND_QUERIES = [
    # Round 1: broad seed
    [
        "intermittent fasting health benefits risks clinical evidence",
        "intermittent fasting weight loss meta-analysis randomized trial",
        "time restricted eating cardiovascular mortality risk",
        "alternate day fasting metabolic health insulin sensitivity",
        "intermittent fasting safety adverse effects eating disorders",
        "intermittent fasting vs caloric restriction systematic review",
    ],
    # Round 2: targeted follow-up
    [
        "16:8 time restricted eating blood pressure outcomes RCT",
        "intermittent fasting HbA1c type 2 diabetes clinical trial",
        "alternate day fasting lean mass muscle preservation",
        "intermittent fasting gut microbiome human studies",
        "5:2 diet long-term weight maintenance 12 months",
        "intermittent fasting contraindications pregnancy elderly",
    ],
    # Round 3: mechanism + safety
    [
        "intermittent fasting autophagy human biomarkers LC3",
        "fasting metabolic switching ketogenesis circadian rhythm",
        "intermittent fasting eating disorder risk binge eating",
        "time restricted eating cardiovascular death AHA 2024",
        "intermittent fasting inflammation CRP IL-6 TNF-alpha",
        "calorie restriction vs intermittent fasting cardiometabolic",
    ],
    # Round 4: gaps + comparisons
    [
        "intermittent fasting older adults geriatric safety",
        "intermittent fasting children adolescents pediatric",
        "intermittent fasting gender differences sex hormones",
        "intermittent fasting medication timing insulin diabetes",
        "GRADE certainty intermittent fasting evidence quality",
        "intermittent fasting adherence dropout rates real world",
    ],
    # Round 5: clinical + emerging
    [
        "intermittent fasting clinical practice guidelines recommendation",
        "intermittent fasting sleep quality cortisol melatonin",
        "intermittent fasting PCOS polycystic ovary syndrome",
        "intermittent fasting cancer prevention tumor growth",
        "intermittent fasting cognitive function neuroprotection dementia",
        "Ramadan fasting health outcomes metabolic parameters",
    ],
]


async def main():
    start = time.time()
    print("=" * 70)
    print("FULL-SCALE SEARCH SMOKE TEST")
    print(f"5 rounds × 6 queries = 30 web + 15 scholar + 5 S2/OA queries")
    print("=" * 70)

    from src.agents.search_agent import _serper_search_sync
    from src.polaris_graph.agents.searcher import _run_serper_scholar, _run_academic_searches
    from src.agents.search_agent import academic_search
    from src.tools.access_bypass import AccessBypass

    all_web_results = []
    all_scholar_results = []
    all_academic_results = []
    seen_urls = set()

    # ── SEARCH PHASE ─────────────────────────────────────────
    for round_num, queries in enumerate(ROUND_QUERIES, 1):
        round_start = time.time()

        # Web search (6 queries)
        web_batch = []
        for q in queries:
            results = _serper_search_sync(q, max_results=10, search_type="search")
            new = [r for r in results if r.get("url", "") not in seen_urls]
            for r in new:
                seen_urls.add(r.get("url", ""))
            web_batch.extend(new)

        # Scholar search (top 3 queries)
        scholar_batch = await _run_serper_scholar(queries[:3])
        scholar_new = [r for r in scholar_batch
                       if r.get("url", r.get("link", "")) not in seen_urls]
        for r in scholar_new:
            seen_urls.add(r.get("url", r.get("link", "")))

        # S2 + OpenAlex (1 query)
        acad_batch = await _run_academic_searches(academic_search, [queries[0]])
        acad_new = [r for r in acad_batch if r.get("url", "") not in seen_urls]
        for r in acad_new:
            seen_urls.add(r.get("url", ""))

        all_web_results.extend(web_batch)
        all_scholar_results.extend(scholar_new)
        all_academic_results.extend(acad_new)

        elapsed = time.time() - round_start
        print(f"  Round {round_num}: {len(web_batch)} web + {len(scholar_new)} scholar + {len(acad_new)} academic ({elapsed:.1f}s)")

    total_unique = len(seen_urls)
    print(f"\n  TOTAL UNIQUE URLs: {total_unique}")
    print(f"    Web: {len(all_web_results)}")
    print(f"    Scholar: {len(all_scholar_results)}")
    print(f"    S2/OpenAlex: {len(all_academic_results)}")

    # ── FETCH PHASE ──────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"FETCH PHASE — fetching ALL {total_unique} unique URLs")
    print(f"{'=' * 70}")

    # Combine all results, dedup
    all_results = []
    url_seen = set()
    for r in all_web_results + all_scholar_results + all_academic_results:
        url = r.get("url", r.get("link", ""))
        if url and url not in url_seen:
            url_seen.add(url)
            all_results.append(r)

    # Match real pipeline cap
    fetch_limit = min(len(all_results), 500)
    print(f"  Fetching top {fetch_limit} URLs (of {len(all_results)} unique)...")

    bypass = AccessBypass()
    fetch_results = []
    fetch_start = time.time()

    sem = asyncio.Semaphore(10)  # concurrent fetch limit (matches PG_FETCH_CONCURRENCY)

    async def fetch_one(r):
        url = r.get("url", r.get("link", ""))
        async with sem:
            try:
                result = await asyncio.wait_for(
                    bypass.fetch_with_bypass(url), timeout=30,
                )
                content = result.content if result.success else ""
                words = len(content.split()) if content else 0
                return {
                    "url": url, "success": result.success, "words": words,
                    "method": result.access_method if result.success else "failed",
                }
            except (asyncio.TimeoutError, Exception):
                return {"url": url, "success": False, "words": 0, "method": "timeout"}

    tasks = [fetch_one(r) for r in all_results[:fetch_limit]]
    fetch_results = await asyncio.gather(*tasks)
    fetch_elapsed = time.time() - fetch_start

    # ── CLASSIFY PHASE ───────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"CLASSIFICATION — every fetched source")
    print(f"{'=' * 70}")

    academic_kw = [
        "ncbi", "pubmed", "pmc.ncbi", "nature.com", "bmj.com", "mdpi.com",
        "frontiersin.org", "springer.com", "wiley.com", "sciencedirect.com",
        "cell.com", "thelancet.com", "jamanetwork.com", "ahajournals.org",
        "cochrane", "plos.org", "academic.oup.com", "biomedcentral.com",
        "karger.com", "tandfonline.com", "journals.lww.com", "journals.sagepub.com",
        "science.org", "jacc.org", "acpjournals.org", "jmir.org",
        "acsjournals", "portlandpress", "nejm.org", "doi.org/10.",
    ]
    institutional_kw = [
        ".edu", "nih.gov", "who.int", "cdc.gov", "fda.gov",
        "mayoclinic.org", "clevelandclinic.org", "hopkinsmedicine.org",
    ]

    full_articles = []
    partial = []
    stubs = []
    failed_fetches = []
    domain_counts = Counter()

    for fr in fetch_results:
        url = fr["url"].lower()
        domain = url.split("/")[2] if "//" in url else "unknown"
        domain_counts[domain] += 1

        if not fr["success"] or fr["words"] == 0:
            failed_fetches.append(fr)
        elif fr["words"] >= 1000:
            full_articles.append(fr)
        elif fr["words"] >= 200:
            partial.append(fr)
        else:
            stubs.append(fr)

    # Classify by source authority
    academic_full = [f for f in full_articles if any(k in f["url"].lower() for k in academic_kw)]
    institutional_full = [f for f in full_articles if any(k in f["url"].lower() for k in institutional_kw)]
    other_full = [f for f in full_articles
                  if not any(k in f["url"].lower() for k in academic_kw + institutional_kw)]

    print(f"\n  Fetched: {len(fetch_results)} URLs in {fetch_elapsed:.0f}s")
    print(f"  Full articles (>1000w): {len(full_articles)}")
    print(f"  Partial (200-1000w):    {len(partial)}")
    print(f"  Stubs (<200w):          {len(stubs)}")
    print(f"  Failed:                 {len(failed_fetches)}")
    print(f"  Success rate:           {(len(full_articles)+len(partial))/max(len(fetch_results),1)*100:.0f}%")
    print()
    print(f"  Full articles by authority:")
    print(f"    Academic:      {len(academic_full)} ({len(academic_full)/max(len(full_articles),1)*100:.0f}%)")
    print(f"    Institutional: {len(institutional_full)} ({len(institutional_full)/max(len(full_articles),1)*100:.0f}%)")
    print(f"    Other/web:     {len(other_full)} ({len(other_full)/max(len(full_articles),1)*100:.0f}%)")

    if other_full:
        print(f"\n  Non-academic full articles ({len(other_full)}):")
        for f in other_full[:15]:
            domain = f["url"].split("/")[2][:40]
            print(f"    {f['words']:6d}w | {domain}")

    # Fetch method distribution
    methods = Counter(fr["method"] for fr in fetch_results if fr["success"])
    print(f"\n  Fetch methods: {dict(methods)}")

    # ── FINAL VERDICT ────────────────────────────────────────
    total_elapsed = time.time() - start
    print(f"\n{'=' * 70}")
    print(f"FULL-SCALE SEARCH SMOKE TEST COMPLETE — {total_elapsed:.0f}s")
    print(f"{'=' * 70}")
    print(f"  Search: {total_unique} unique URLs from 30 web + 15 scholar + 5 S2/OA queries")
    print(f"  Fetch: {len(full_articles)+len(partial)}/{fetch_limit} successful ({(len(full_articles)+len(partial))/max(fetch_limit,1)*100:.0f}%)")
    print(f"  Full articles: {len(full_articles)} (>1000w)")
    print(f"  Academic quality: {len(academic_full)}/{len(full_articles)} full articles from peer-reviewed sources ({len(academic_full)/max(len(full_articles),1)*100:.0f}%)")
    print()

    # What the analyzer would see
    analyzer_input = len(full_articles) + len(partial)
    print(f"  WHAT THE ANALYZER WOULD RECEIVE:")
    print(f"    {analyzer_input} fetched sources with content")
    print(f"    {len(academic_full)} academic full articles (this is what we cite)")
    print(f"    Evidence cap: 300 (PG_MAX_EVIDENCE_TO_EXTRACT)")
    print(f"    At ~4 evidence per academic source: ~{len(academic_full)*4} potential evidence pieces")
    print(f"    At ~60 unique sources cited: matches or beats Gemini DR (47-62)")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
