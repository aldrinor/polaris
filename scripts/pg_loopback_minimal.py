"""Minimal-scope loopback preflight: exercise every code path with the FEWEST
possible LLM calls. Pipeline halts at every LLM call, prompt is written to
loopback/pending/, response is written to loopback/responses/ by the operator
(Claude Code session). Zero OpenRouter cost; external search/fetch cost ~$0.10.

Caps overridden in-process so .env doesn't need to be touched:
- PG_MAX_ITERATIONS=1  (single iteration; covers core path, skips gap-search re-iter)
- PG_QUERIES_PER_VECTOR=10
- PG_AGENTIC_MAX_ROUNDS=2
- PG_AGENTIC_MIN_ROUNDS=1
- PG_AGENTIC_PAGES_PER_ROUND=2
- PG_MAX_SOURCES_TO_ANALYZE=10
- PG_MAX_EVIDENCE_TO_EXTRACT=50
- PG_MAX_EVIDENCE_FOR_VERIFY=50
- PG_MAX_EVIDENCE_FOR_SYNTHESIS=50
- PG_VERIFY_BATCH_SIZE=10
- PG_STORM_ROUNDS_PER_PERSPECTIVE=1
- PG_MAX_OUTLINE_SECTIONS=4
- PG_SECTION_WRITE_CONCURRENCY=2
- PG_SYNTHESIS_MAX_EXPANSION_PASSES=0  (skip expansion to save calls)

Estimated LLM calls: ~25-40 total. ~5-10 conversation turns to process.
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

# Force tiny scope BEFORE any imports that read env at module load time
os.environ["PG_LOOPBACK_MODE"] = "1"
os.environ["PG_MAX_ITERATIONS"] = "1"
os.environ["PG_QUERIES_PER_VECTOR"] = "10"
os.environ["PG_AGENTIC_MAX_ROUNDS"] = "2"
os.environ["PG_AGENTIC_MIN_ROUNDS"] = "1"
os.environ["PG_AGENTIC_PAGES_PER_ROUND"] = "2"
os.environ["PG_MAX_SOURCES_TO_ANALYZE"] = "10"
os.environ["PG_MAX_EVIDENCE_TO_EXTRACT"] = "50"
os.environ["PG_MAX_EVIDENCE_FOR_VERIFY"] = "50"
os.environ["PG_MAX_EVIDENCE_FOR_SYNTHESIS"] = "50"
os.environ["PG_VERIFY_BATCH_SIZE"] = "10"
os.environ["PG_STORM_ROUNDS_PER_PERSPECTIVE"] = "1"
os.environ["PG_STORM_CONCURRENCY"] = "2"
os.environ["PG_MAX_OUTLINE_SECTIONS"] = "4"
os.environ["PG_MAX_SECTIONS"] = "4"
os.environ["PG_SECTION_WRITE_CONCURRENCY"] = "2"
os.environ["PG_SYNTHESIS_MAX_EXPANSION_PASSES"] = "0"
os.environ["PG_MAX_EXECUTION_MINUTES"] = "1440"  # 24h — loopback is slow
os.environ["PG_BUDGET_GUARD_USD"] = "5"

# LOOPBACK LATENCY OVERRIDES — sub-agent responses take 30-60s vs GLM ~5s.
# Every pipeline timeout must be generous enough that retries don't cascade.
os.environ["PG_ANALYSIS_BATCH_TIMEOUT"] = "3600"
os.environ["PG_STORM_INTERVIEW_TIMEOUT"] = "3600"
os.environ["PG_AGENTIC_ANALYSIS_TIMEOUT_SECONDS"] = "3600"
os.environ["PG_VERIFY_BATCH_TIMEOUT"] = "3600"
os.environ["PG_VERIFY_PER_CALL_TIMEOUT"] = "3600"
os.environ["PG_VERIFY_GATHER_TIMEOUT"] = "14400"
os.environ["PG_CLUSTER_BATCH_TIMEOUT"] = "3600"
os.environ["PG_SECTION_WRITE_TIMEOUT"] = "3600"
os.environ["PG_AGENTIC_MAX_TIME_SECONDS"] = "36000"
os.environ["PG_STORM_MAX_TIME_SECONDS"] = "36000"
os.environ["PG_MOST_TOTAL_TIMEOUT"] = "3600"
os.environ["PG_AGENTIC_FETCH_TIMEOUT"] = "120"
os.environ["PG_LOOPBACK_TIMEOUT_SEC"] = "7200"
os.environ["PG_PLANNER_TIMEOUT"] = "3600"
os.environ["PG_REACT_TIMEOUT_SECONDS"] = "3600"
os.environ["PG_WRITE_TIMEOUT"] = "3600"
os.environ["PG_STRUCTURED_DATA_TOTAL_TIMEOUT"] = "3600"
os.environ["PG_LLM_TIMEOUT_SECONDS"] = "3600"
os.environ["PG_LLM_LONG_TIMEOUT_SECONDS"] = "3600"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(override=False)  # don't override our os.environ scope

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/pg_loopback_minimal.log", mode="w", encoding="utf-8"),
    ],
)

VECTOR_ID = "PG_LOOPBACK_MIN"


async def main():
    from src.polaris_graph.graph import build_and_run

    print("=" * 70, flush=True)
    print(f"  {VECTOR_ID}: LOOPBACK MINIMAL — code-path sweep, zero LLM cost", flush=True)
    print("=" * 70, flush=True)

    start = time.time()
    try:
        result = await build_and_run(
            vector_id=VECTOR_ID,
            query="What are the proven health benefits and risks of intermittent fasting?",
            application="Evidence-Based Health Research",
            region="GLOBAL",
            stage=1,
            max_iterations=1,
            max_execution_minutes=120,
        )
        elapsed = time.time() - start
        print(flush=True)
        print("=" * 70, flush=True)
        print(f"  {VECTOR_ID} COMPLETED in {elapsed:.0f}s", flush=True)
        print(f"  status: {result.get('status')}", flush=True)
        qm = result.get("quality_metrics") or {}
        print(f"  evidence: {len(result.get('evidence', []))}", flush=True)
        print(f"  claims: {len(result.get('claims', []))}", flush=True)
        print(f"  total_words: {qm.get('total_words', 0)}", flush=True)
        print(f"  total_citations: {qm.get('total_citations', 0)}", flush=True)
        print(f"  faith: {qm.get('faithfulness_score', 0)}", flush=True)
        print(f"  llm calls: {(result.get('llm_usage') or {}).get('total_calls', 0)}", flush=True)
        print("=" * 70, flush=True)
    except Exception as exc:
        elapsed = time.time() - start
        print(f"\n  {VECTOR_ID} FAILED after {elapsed:.0f}s: {exc}", flush=True)
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(main())
