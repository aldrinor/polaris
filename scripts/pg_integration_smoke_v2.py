"""Full integration smoke test v2 — REAL data through REAL pipeline at realistic scale."""
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PG_WIKI_ENABLED"] = "1"
os.environ["PG_WIKI_5LENS"] = "1"
from dotenv import load_dotenv
load_dotenv()
os.environ["PG_WIKI_ENABLED"] = "1"
os.environ["PG_WIKI_5LENS"] = "1"

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger(__name__)


async def main():
    start = time.time()
    print("=" * 70)
    print("INTEGRATION SMOKE TEST v2 — REAL data, realistic scale")
    print("=" * 70)

    results = {}

    # ──────────────────────────────────────────────────────────
    # STAGE 1: Scholar search at realistic volume (6 queries)
    # ──────────────────────────────────────────────────────────
    print("\n[STAGE 1] Serper Scholar — 6 queries...")
    from src.polaris_graph.agents.searcher import _run_serper_scholar
    scholar_queries = [
        "intermittent fasting health benefits risks clinical evidence",
        "intermittent fasting weight loss meta-analysis randomized trial",
        "time restricted eating cardiovascular mortality risk",
        "alternate day fasting metabolic health insulin sensitivity",
        "intermittent fasting safety adverse effects eating disorders",
        "intermittent fasting vs caloric restriction systematic review",
    ]
    scholar_results = await _run_serper_scholar(scholar_queries)
    scholar_urls = [r.get("url", r.get("link", "")) for r in scholar_results]
    print(f"  Total results: {len(scholar_results)}")
    print(f"  Unique URLs: {len(set(scholar_urls))}")

    academic_kw = ["ncbi", "pubmed", "nature.com", "bmj.com", "mdpi.com",
                   "frontiersin.org", "springer.com", "wiley.com", "sciencedirect.com",
                   "jamanetwork.com", "thelancet.com", "academic.oup.com", "cell.com",
                   "ahajournals.org", "cochrane", "plos.org", "karger.com",
                   "acsjournals", "onlinelibrary.wiley", "biomedcentral"]
    acad_count = sum(1 for u in scholar_urls if any(k in u.lower() for k in academic_kw))
    print(f"  Academic: {acad_count}/{len(scholar_results)} ({acad_count/max(len(scholar_results),1)*100:.0f}%)")
    results["scholar"] = {"total": len(scholar_results), "academic_pct": acad_count / max(len(scholar_results), 1)}

    # ──────────────────────────────────────────────────────────
    # STAGE 2: S2 parallel with OpenAlex (real query)
    # ──────────────────────────────────────────────────────────
    print("\n[STAGE 2] S2 + OpenAlex parallel...")
    from src.polaris_graph.agents.searcher import _run_academic_searches
    from src.agents.search_agent import academic_search
    acad_results = await _run_academic_searches(
        academic_search,
        ["intermittent fasting clinical trials health outcomes"],
    )
    acad_urls = [r.get("url", "") for r in acad_results]
    print(f"  Total results: {len(acad_results)}")
    print(f"  Unique URLs: {len(set(acad_urls))}")
    results["s2_openalex"] = {"total": len(acad_results)}

    # ──────────────────────────────────────────────────────────
    # STAGE 3: Dedup across Scholar + S2/OpenAlex
    # ──────────────────────────────────────────────────────────
    print("\n[STAGE 3] Dedup across all search results...")
    all_urls = set()
    for r in scholar_results:
        all_urls.add(r.get("url", r.get("link", "")))
    for r in acad_results:
        all_urls.add(r.get("url", ""))
    all_urls.discard("")
    overlap = len(scholar_urls) + len(acad_urls) - len(all_urls)
    print(f"  Scholar URLs: {len(set(scholar_urls))}")
    print(f"  S2/OA URLs: {len(set(acad_urls))}")
    print(f"  Combined unique: {len(all_urls)}")
    print(f"  Overlap: {overlap}")

    # ──────────────────────────────────────────────────────────
    # STAGE 4: Fetch top 20 Scholar URLs through FULL cascade
    # ──────────────────────────────────────────────────────────
    print("\n[STAGE 4] Fetch 20 Scholar URLs (full Crawl4AI/Jina/Sci-Hub cascade)...")
    from src.tools.access_bypass import AccessBypass
    bypass = AccessBypass()
    fetch_urls = list(set(scholar_urls))[:20]

    fetch_results = []
    for url in fetch_urls:
        try:
            result = await asyncio.wait_for(
                bypass.fetch_with_bypass(url),
                timeout=30,
            )
            content = result.content if result.success else ""
            words = len(content.split()) if content else 0
            method = result.access_method if result.success else "failed"

            # Content quality check
            has_abstract = "abstract" in content.lower()[:3000] if content else False
            has_methods = "method" in content.lower() if content else False
            has_results = "result" in content.lower() if content else False

            fetch_results.append({
                "url": url, "success": result.success, "words": words,
                "method": method, "has_abstract": has_abstract,
                "has_methods": has_methods, "has_results": has_results,
            })

            domain = url.split("/")[2][:30]
            if words > 1000:
                status = "FULL"
            elif words > 200:
                status = "PARTIAL"
            elif words > 0:
                status = "STUB"
            else:
                status = "FAILED"
            print(f"  {status:8s} {words:6d}w | {method:20s} | {domain}")

        except asyncio.TimeoutError:
            domain = url.split("/")[2][:30]
            print(f"  TIMEOUT        | {'timeout':20s} | {domain}")
            fetch_results.append({"url": url, "success": False, "words": 0, "method": "timeout"})
        except Exception as e:
            domain = url.split("/")[2][:30]
            print(f"  ERROR          | {str(e)[:20]:20s} | {domain}")
            fetch_results.append({"url": url, "success": False, "words": 0, "method": "error"})

    # Fetch summary
    successful = [f for f in fetch_results if f["success"] and f["words"] > 200]
    full_articles = [f for f in fetch_results if f["words"] > 1000]
    print(f"\n  Fetch summary: {len(successful)}/{len(fetch_results)} successful (>{200}w)")
    print(f"  Full articles (>1000w): {len(full_articles)}/{len(fetch_results)}")
    print(f"  Methods: {', '.join(set(f['method'] for f in fetch_results if f['success']))}")
    results["fetch"] = {
        "total": len(fetch_results),
        "successful": len(successful),
        "full_articles": len(full_articles),
        "success_rate": len(successful) / max(len(fetch_results), 1),
    }

    # ──────────────────────────────────────────────────────────
    # STAGE 5: Sci-Hub on 5 paywalled DOIs
    # ──────────────────────────────────────────────────────────
    # Sci-Hub is DISABLED by default (legal/provenance, I-faith-002); CORE
    # (core.ac.uk) is the legal OA full-text source. This stage runs ONLY on
    # explicit operator opt-in (PG_SCIHUB_ENABLED=1) so the smoke never issues
    # a sci-hub.* request by default.
    print("\n[STAGE 5] Sci-Hub on 5 paywalled DOIs...")
    dois = [
        ("10.1056/NEJMra1905136", "NEJM"),
        ("10.1038/s41574-022-00638-x", "Nature Rev Endo"),
        ("10.1016/j.cmet.2014.06.010", "Cell Metabolism"),
        ("10.1161/CIRCULATIONAHA.122.063741", "Circulation"),
        ("10.1016/j.cels.2015.10.014", "Cell Systems"),
    ]
    scihub_success = 0
    if os.getenv("PG_SCIHUB_ENABLED", "0") != "1":
        print("  SKIP: Sci-Hub disabled (PG_SCIHUB_ENABLED!=1); legal/provenance.")
        results["scihub"] = {"total": len(dois), "success": 0, "skipped": True}
    else:
        for doi, journal in dois:
            try:
                r = await asyncio.wait_for(
                    bypass._try_scihub(f"https://doi.org/{doi}"),
                    timeout=25,
                )
                if r.success and len(r.content) > 500:
                    print(f"  PASS {len(r.content):6d} chars | {r.access_method:15s} | {journal}")
                    scihub_success += 1
                else:
                    print(f"  FAIL             | {r.metadata.get('error', '?')[:30]:30s} | {journal}")
            except asyncio.TimeoutError:
                print(f"  TIMEOUT          | {'timeout':30s} | {journal}")
            except Exception as e:
                print(f"  ERROR            | {str(e)[:30]:30s} | {journal}")
        print(f"  Sci-Hub success: {scihub_success}/{len(dois)}")
        results["scihub"] = {"total": len(dois), "success": scihub_success}

    # ──────────────────────────────────────────────────────────
    # STAGE 6: Format compatibility check
    # ──────────────────────────────────────────────────────────
    print("\n[STAGE 6] Format compatibility (Scholar result → analyzer expectations)...")
    required_fields = ["url", "title", "snippet"]
    optional_fields = ["source_type", "year", "cited_by", "authors"]
    if scholar_results:
        sample = scholar_results[0]
        missing_req = [f for f in required_fields if f not in sample]
        present_opt = [f for f in optional_fields if f in sample]
        print(f"  Sample keys: {sorted(sample.keys())}")
        print(f"  Required fields missing: {missing_req if missing_req else 'None'}")
        print(f"  Optional fields present: {present_opt}")
        if not missing_req:
            print("  PASS: format compatible")
        else:
            print(f"  FAIL: missing {missing_req}")
    results["format"] = {"missing": missing_req if scholar_results else ["no results"]}

    # ──────────────────────────────────────────────────────────
    # STAGE 7: Wiki builder on REAL fetched content metadata
    # ──────────────────────────────────────────────────────────
    print("\n[STAGE 7] Wiki builder on real source metadata...")
    # Build evidence-like dicts from actual fetch results
    real_evidence = []
    for i, fr in enumerate(fetch_results):
        if not fr["success"] or fr["words"] < 100:
            continue
        real_evidence.append({
            "evidence_id": f"ev_real_{i:04d}",
            "source_url": fr["url"],
            "source_title": f"Academic Paper {i}",
            "source_type": "academic",
            "statement": f"Evidence from fetched academic source ({fr['words']} words)",
            "direct_quote": "Significant findings were observed in the study population",
            "quality_tier": "GOLD" if fr["words"] > 1000 else "SILVER",
            "relevance_score": 0.75,
            "sig_authority": 0.85,
            "year": 2024,
        })

    if len(real_evidence) >= 5:
        outline = [
            {"section_id": "s01", "title": "Overview", "description": "Introduction"},
            {"section_id": "s02", "title": "Findings", "description": "Key findings"},
            {"section_id": "s03", "title": "Safety", "description": "Safety and risks"},
        ]
        from src.polaris_graph.wiki.wiki_builder import build_wiki
        wiki = build_wiki(
            evidence=real_evidence, outline=outline,
            query="IF health benefits", vector_id="SMOKE_V2_REAL",
        )
        claims = sum(len(c) for c in wiki.section_claims.values())
        bib = len(wiki.bibliography)
        print(f"  Real evidence used: {len(real_evidence)}")
        print(f"  Wiki claims: {claims}")
        print(f"  Bibliography: {bib}")
        print(f"  PASS" if claims > 0 and bib > 0 else "  FAIL")
    else:
        print(f"  Only {len(real_evidence)} evidence from fetches — too few for wiki test")
        print("  SKIP (not enough fetched content)")
    results["wiki_real"] = {"evidence": len(real_evidence)}

    # ──────────────────────────────────────────────────────────
    # VERDICT
    # ──────────────────────────────────────────────────────────
    elapsed = time.time() - start
    print("\n" + "=" * 70)
    print(f"INTEGRATION TEST COMPLETE — {elapsed:.0f}s")
    print("=" * 70)

    issues = []
    if results["scholar"]["academic_pct"] < 0.6:
        issues.append(f"Scholar academic rate too low: {results['scholar']['academic_pct']*100:.0f}%")
    if results["fetch"]["success_rate"] < 0.3:
        issues.append(f"Fetch success rate too low: {results['fetch']['success_rate']*100:.0f}%")
    # Sci-Hub is DISABLED by default now (legal/provenance, I-faith-002); a
    # skipped stage is NOT an issue — only flag zero-retrieval when the
    # operator explicitly opted in (PG_SCIHUB_ENABLED=1).
    if not results["scihub"].get("skipped") and results["scihub"]["success"] == 0:
        issues.append("Sci-Hub returned nothing")
    if results.get("format", {}).get("missing"):
        issues.append(f"Scholar format incompatible: missing {results['format']['missing']}")

    if not issues:
        print("STATUS: READY FOR FULL RUN")
        print(f"  Scholar: {results['scholar']['total']} results, {results['scholar']['academic_pct']*100:.0f}% academic")
        print(f"  Fetch: {results['fetch']['successful']}/{results['fetch']['total']} successful, {results['fetch']['full_articles']} full articles")
        print(f"  Sci-Hub: {results['scihub']['success']}/{results['scihub']['total']} paywalled papers retrieved")
        print(f"  S2+OA: {results['s2_openalex']['total']} parallel results")
    else:
        print("STATUS: ISSUES FOUND")
        for iss in issues:
            print(f"  - {iss}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
