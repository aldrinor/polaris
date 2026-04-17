"""Medium-scope loopback run: richer than pg_loopback_minimal but still
fits in one operator session. Exercises every node under realistic load
with all ZCV bug fixes in place (BUG-70, BUG-5, BUG-3).

Scale:
- PG_MAX_ITERATIONS=2          (vs minimal=1)
- PG_QUERIES_PER_VECTOR=20     (vs minimal=10)
- PG_AGENTIC_MAX_ROUNDS=3      (vs minimal=2)
- PG_MAX_SOURCES_TO_ANALYZE=20 (vs minimal=10)
- PG_STORM_ROUNDS_PER_PERSPECTIVE=2 (vs minimal=1)
- PG_MAX_OUTLINE_SECTIONS=6    (vs minimal=4)
- PG_SYNTHESIS_MAX_EXPANSION_PASSES=1 (vs minimal=0)

Estimated LLM calls: ~60-80. Expect ~30-45 Tier B/C operator calls.
External search cost: ~$0.20 (Serper + S2).
"""
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

os.environ["PG_LOOPBACK_MODE"] = "1"
os.environ["PG_MAX_ITERATIONS"] = "2"
os.environ["PG_QUERIES_PER_VECTOR"] = "20"
os.environ["PG_AGENTIC_MAX_ROUNDS"] = "3"
os.environ["PG_AGENTIC_MIN_ROUNDS"] = "2"
os.environ["PG_AGENTIC_PAGES_PER_ROUND"] = "3"
os.environ["PG_MAX_SOURCES_TO_ANALYZE"] = "20"
os.environ["PG_MAX_EVIDENCE_TO_EXTRACT"] = "120"
os.environ["PG_MAX_EVIDENCE_FOR_VERIFY"] = "120"
os.environ["PG_MAX_EVIDENCE_FOR_SYNTHESIS"] = "100"
os.environ["PG_VERIFY_BATCH_SIZE"] = "10"
os.environ["PG_STORM_ROUNDS_PER_PERSPECTIVE"] = "2"
os.environ["PG_STORM_CONCURRENCY"] = "2"
os.environ["PG_MAX_OUTLINE_SECTIONS"] = "6"
os.environ["PG_MAX_SECTIONS"] = "6"
os.environ["PG_SECTION_WRITE_CONCURRENCY"] = "2"
os.environ["PG_SYNTHESIS_MAX_EXPANSION_PASSES"] = "1"
os.environ["PG_MAX_EXECUTION_MINUTES"] = "1440"
os.environ["PG_BUDGET_GUARD_USD"] = "5"

for k in [
    "PG_ANALYSIS_BATCH_TIMEOUT", "PG_STORM_INTERVIEW_TIMEOUT",
    "PG_AGENTIC_ANALYSIS_TIMEOUT_SECONDS", "PG_VERIFY_BATCH_TIMEOUT",
    "PG_VERIFY_PER_CALL_TIMEOUT", "PG_CLUSTER_BATCH_TIMEOUT",
    "PG_SECTION_WRITE_TIMEOUT", "PG_PLANNER_TIMEOUT",
    "PG_REACT_TIMEOUT_SECONDS", "PG_WRITE_TIMEOUT",
    "PG_STRUCTURED_DATA_TOTAL_TIMEOUT", "PG_LLM_TIMEOUT_SECONDS",
    "PG_LLM_LONG_TIMEOUT_SECONDS", "PG_MOST_TOTAL_TIMEOUT",
]:
    os.environ[k] = "3600"
os.environ["PG_VERIFY_GATHER_TIMEOUT"] = "14400"
os.environ["PG_AGENTIC_MAX_TIME_SECONDS"] = "36000"
os.environ["PG_STORM_MAX_TIME_SECONDS"] = "36000"
os.environ["PG_AGENTIC_FETCH_TIMEOUT"] = "180"
os.environ["PG_LOOPBACK_TIMEOUT_SEC"] = "7200"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(override=False)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/pg_loopback_medium.log", mode="w", encoding="utf-8"),
    ],
)

VECTOR_ID = "PG_LOOPBACK_MED"


async def main():
    from src.polaris_graph.graph import build_and_run

    print("=" * 70, flush=True)
    print(f"  {VECTOR_ID}: LOOPBACK MEDIUM — 2 iter, 20 sources, 3 STORM rounds, 6 sections", flush=True)
    print("=" * 70, flush=True)

    start = time.time()
    try:
        result = await build_and_run(
            vector_id=VECTOR_ID,
            query="What are the proven health benefits and risks of intermittent fasting?",
            application="Evidence-Based Health Research",
            region="GLOBAL",
            stage=1,
            max_iterations=2,
            max_execution_minutes=240,
        )
        elapsed = time.time() - start
        print(flush=True)
        print("=" * 70, flush=True)
        print(f"  {VECTOR_ID} COMPLETED in {elapsed:.0f}s ({elapsed/60:.1f} min)", flush=True)
        qm = result.get("quality_metrics") or {}
        print(f"  status: {result.get('status')}", flush=True)
        print(f"  evidence: {len(result.get('evidence', []))}", flush=True)
        print(f"  claims: {len(result.get('claims', []))}", flush=True)
        print(f"  total_words: {qm.get('total_words', 0)}", flush=True)
        print(f"  total_citations: {qm.get('total_citations', 0)}", flush=True)
        print(f"  unique_sources: {qm.get('unique_sources', 0)}", flush=True)
        print(f"  faith: {qm.get('faithfulness_score', 0)}", flush=True)
        print(f"  perspective_entropy: {result.get('perspective_entropy')}", flush=True)
        ha = result.get('hallucination_audit')
        if isinstance(ha, list):
            print(f"  hallucination_audit: {len(ha)} sections, avg_ratio={sum(r.get('hallucination_ratio',0) for r in ha)/max(1,len(ha)):.2f}", flush=True)
        print("=" * 70, flush=True)
    except Exception as exc:
        elapsed = time.time() - start
        print(f"\n  {VECTOR_ID} FAILED after {elapsed:.0f}s: {exc}", flush=True)
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    asyncio.run(main())
