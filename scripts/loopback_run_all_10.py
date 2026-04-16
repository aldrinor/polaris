"""Run all 10 loopback vectors sequentially, collect D3 metrics.

Usage: python scripts/loopback_run_all_10.py

Requires loopback_auto_universal.py running in background.
"""
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

TOPICS_FILE = ROOT / "scripts" / "pg_loopback_topics.json"
OUTPUT_DIR = ROOT / "outputs" / "polaris_graph"


def load_topics() -> list[dict]:
    with open(TOPICS_FILE, encoding="utf-8") as f:
        return json.load(f)["topics"]


def audit_d3(vector_id: str) -> dict:
    """Audit D3 URL canonicalization for one completed vector."""
    json_path = OUTPUT_DIR / f"{vector_id}.json"
    md_path = OUTPUT_DIR / f"{vector_id}_report.md"

    if not json_path.exists():
        return {"vector_id": vector_id, "status": "MISSING_JSON"}
    if not md_path.exists():
        return {"vector_id": vector_id, "status": "MISSING_REPORT"}

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    with open(md_path, encoding="utf-8") as f:
        report = f.read()

    bib = data.get("bibliography", [])
    urls = [b.get("url", "") for b in bib]
    distinct_urls = len(set(urls))
    total_bib = len(bib)

    # Normalize for near-duplicate detection
    def norm(u):
        return u.lower().rstrip("/").replace("www.", "").replace("https://", "").replace("http://", "").split("?")[0]
    norm_urls = [norm(u) for u in urls]
    from collections import Counter
    dupes = [(u, c) for u, c in Counter(norm_urls).items() if c > 1]

    # Citation cross-check
    idx = report.find("## References")
    prose = report[:idx] if idx > 0 else report
    bib_text = report[idx:] if idx > 0 else ""
    prose_cites = set(int(m.group(1)) for m in re.finditer(r"\[(\d+)\]", prose))
    bib_ids = set(int(m.group(1)) for m in re.finditer(r"^\[(\d+)\] ", bib_text, re.MULTILINE))
    phantom = sorted(prose_cites - bib_ids)
    orphaned = sorted(bib_ids - prose_cites)

    # Hallucination signals
    halluc_kw = ["Zhong", "NHANES", "PMID", "Science Media Centre", "Burg-Peet"]
    halluc_hits = {kw: prose.count(kw) for kw in halluc_kw if prose.count(kw) > 0}

    ha = data.get("hallucination_audit", [])
    ha_populated = len(ha) > 0 if isinstance(ha, list) else bool(ha)

    qm = data.get("quality_metrics", {})

    return {
        "vector_id": vector_id,
        "status": data.get("status", "unknown"),
        "bib_entries": total_bib,
        "distinct_urls": distinct_urls,
        "near_dupes": dupes,
        "prose_cites": sorted(prose_cites),
        "phantom_cites": phantom,
        "orphaned_bib": orphaned,
        "halluc_signals": halluc_hits,
        "halluc_audit_populated": ha_populated,
        "words": qm.get("total_words", 0),
        "citations": qm.get("total_citations", 0),
        "faithfulness": data.get("faithfulness_score", 0),
    }


async def run_one(topic: dict) -> dict:
    vid = topic["vector_id"]
    query = topic["query"]
    app = topic.get("application", "Systematic Review")
    region = topic.get("region", "GLOBAL")

    print(f"\n{'='*60}")
    print(f"  {vid}: {query[:60]}...")
    print(f"{'='*60}")

    start = time.time()

    # Set env vars matching pg_loopback_full_scale.py
    os.environ["PG_LOOPBACK_MODE"] = "1"
    os.environ["PG_MAX_ITERATIONS"] = "4"
    os.environ["PG_QUERIES_PER_VECTOR"] = "30"
    os.environ["PG_AGENTIC_MAX_ROUNDS"] = "5"
    os.environ["PG_AGENTIC_MIN_ROUNDS"] = "2"
    os.environ["PG_AGENTIC_PAGES_PER_ROUND"] = "6"
    os.environ["PG_MAX_SOURCES_TO_ANALYZE"] = "60"
    os.environ["PG_MAX_EVIDENCE_TO_EXTRACT"] = "400"
    os.environ["PG_MAX_EVIDENCE_FOR_VERIFY"] = "2000"
    os.environ["PG_MAX_EVIDENCE_FOR_SYNTHESIS"] = "1000"
    os.environ["PG_VERIFY_BATCH_SIZE"] = "10"
    os.environ["PG_STORM_ROUNDS_PER_PERSPECTIVE"] = "3"
    os.environ["PG_STORM_CONCURRENCY"] = "2"
    os.environ["PG_MAX_OUTLINE_SECTIONS"] = "8"
    os.environ["PG_MAX_SECTIONS"] = "8"
    os.environ["PG_SECTION_WRITE_CONCURRENCY"] = "2"
    os.environ["PG_SYNTHESIS_MAX_EXPANSION_PASSES"] = "2"
    os.environ["PG_MAX_EXECUTION_MINUTES"] = "1440"
    os.environ["PG_BUDGET_GUARD_USD"] = "40"
    # All timeouts large for loopback
    for k in ["PG_ANALYSIS_BATCH_TIMEOUT", "PG_STORM_INTERVIEW_TIMEOUT",
              "PG_AGENTIC_ANALYSIS_TIMEOUT_SECONDS", "PG_VERIFY_BATCH_TIMEOUT",
              "PG_VERIFY_PER_CALL_TIMEOUT", "PG_CLUSTER_BATCH_TIMEOUT",
              "PG_SECTION_WRITE_TIMEOUT", "PG_PLANNER_TIMEOUT",
              "PG_REACT_TIMEOUT_SECONDS", "PG_WRITE_TIMEOUT",
              "PG_STRUCTURED_DATA_TOTAL_TIMEOUT", "PG_LLM_TIMEOUT_SECONDS",
              "PG_LLM_LONG_TIMEOUT_SECONDS", "PG_WIKI_OUTLINE_TIMEOUT",
              "PG_WIKI_ABSTRACT_TIMEOUT", "PG_WIKI_COMPOSE_TIMEOUT",
              "PG_QUESTION_DECOMP_TIMEOUT", "PG_OUTLINE_TIMEOUT",
              "PG_MOST_TOTAL_TIMEOUT"]:
        os.environ[k] = "7200"
    os.environ["PG_VERIFY_GATHER_TIMEOUT"] = "28800"
    os.environ["PG_AGENTIC_MAX_TIME_SECONDS"] = "72000"
    os.environ["PG_STORM_MAX_TIME_SECONDS"] = "72000"
    os.environ["PG_AGENTIC_FETCH_TIMEOUT"] = "180"
    os.environ["PG_LOOPBACK_TIMEOUT_SEC"] = "14400"

    from dotenv import load_dotenv
    load_dotenv(override=False)

    try:
        from src.polaris_graph.graph import build_and_run
        result = await build_and_run(
            vector_id=vid, query=query, application=app,
            region=region, stage=1, max_iterations=4, max_execution_minutes=1440,
        )
        elapsed = time.time() - start
        status = result.get("status", "unknown")
        print(f"  {vid} completed in {elapsed:.0f}s ({elapsed/60:.1f}min) — status={status}")
    except Exception as exc:
        elapsed = time.time() - start
        print(f"  {vid} CRASHED after {elapsed:.0f}s: {exc}")
        import traceback
        traceback.print_exc()

    return audit_d3(vid)


async def main():
    topics = load_topics()
    print(f"Loaded {len(topics)} topics from {TOPICS_FILE}")

    results = []
    for topic in topics:
        r = await run_one(topic)
        results.append(r)
        print(f"  D3 audit: {r['vector_id']} — bib={r.get('bib_entries')}, "
              f"distinct={r.get('distinct_urls')}, dupes={len(r.get('near_dupes', []))}, "
              f"phantom={r.get('phantom_cites')}, halluc={r.get('halluc_signals')}, "
              f"audit_populated={r.get('halluc_audit_populated')}")

    # Summary
    print(f"\n{'='*60}")
    print(f"  10-VECTOR D3 SUMMARY")
    print(f"{'='*60}")
    for r in results:
        status = "PASS" if not r.get("near_dupes") and not r.get("phantom_cites") and not r.get("halluc_signals") else "FAIL"
        print(f"  {r['vector_id']}: {status} — bib={r.get('bib_entries',0)}, dupes={len(r.get('near_dupes',[]))}, "
              f"phantom={len(r.get('phantom_cites',[]))}, halluc={len(r.get('halluc_signals',{}))}, "
              f"audit={r.get('halluc_audit_populated')}")

    # Write results
    out_path = ROOT / "outputs" / "loopback_10_vector_d3_audit.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    asyncio.run(main())
